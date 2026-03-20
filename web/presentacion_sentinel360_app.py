import subprocess
import sys
import base64
import heapq
import re
import json
import socket
import os
import html
from pathlib import Path

# Asegurar que el proyecto está en el path para importar config
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# Asegurar que el proyecto raíz está en el PYTHONPATH.
# Streamlit ejecuta el script dentro de `web/`, por lo que `config.py` (en la raíz)
# puede no ser importable si no añadimos el directorio padre.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import (  # type: ignore
    MONGO_URI,
    MONGO_DB,
    MONGO_AGGREGATED_COLLECTION,
    MONGO_ANOMALIES_COLLECTION,
)

import pymongo

MONGO_INCIDENTS_COLLECTION = "incidents"
MONGO_DECISIONS_COLLECTION = "decisions"

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
PAGE_LABELS = [
    "0 · Arranque de servicios",
    "1 · Fase I – Ingesta",
    "2 · Fase II – Limpieza y enriquecimiento",
    "3 · Fase II – Grafos",
    "4 · Fase III – Streaming + anomalías",
    "5 · Entorno visual (Superset / Grafana / Airflow)",
    "6 · Dashboard (Retrasos / Anomalías)",
    "6.1 · Incidencias y decisiones",
    "6.2 · Histórico y SLA",
    "7 · Documentación (buscador)",
]

# Parámetros por defecto para la simulación de grafos / incidencias.
# Desarrollador: puedes ajustarlos aquí si quieres cambiar el modelo base.
GRAPH_BASE_DISTANCE_KM = 300.0
GRAPH_BASE_DURATION_MIN = 240.0  # 4h
GRAPH_ALT_DISTANCE_FACTOR = 1.10  # ruta alternativa 10% más larga
GRAPH_ALT_DURATION_FACTOR = 0.90  # algo más fluida que la ruta afectada
GRAPH_FUEL_COST_EUR_PER_KM = 1.2
GRAPH_DELAY_COST_EUR_PER_MIN = 2.0


def run_command(cmd: str, extra_env: dict[str, str] | None = None) -> str:
    """
    Ejecuta un comando de shell desde la raíz del proyecto y devuelve stdout+stderr.
    No lanza excepción si falla: devolvemos el error en texto para mostrarlo en Streamlit.
    """
    try:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        completed = subprocess.run(
            ["bash", "-lc", f"source ~/.bashrc >/dev/null 2>&1 || true; {cmd}"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        return completed.stdout
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        return f"Error ejecutando comando:\n{exc}"


def run_command_streaming(cmd: str, output_slot, extra_env: dict[str, str] | None = None) -> str:
    """
    Ejecuta un comando mostrando stdout/stderr en tiempo real en Streamlit.
    Devuelve la salida completa al finalizar.
    """
    try:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            ["bash", "-lc", f"source ~/.bashrc >/dev/null 2>&1 || true; {cmd}"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        lines: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                lines.append(line)
                # Mostrar las últimas líneas para evitar renderizados enormes.
                tail = "".join(lines[-200:])
                safe_tail = html.escape(tail if tail else "Ejecutando...")
                output_slot.markdown(
                    (
                        "<div style='max-height:320px; overflow:auto; "
                        "white-space:pre-wrap; word-break:break-word; "
                        "font-family:monospace; font-size:0.85rem; "
                        "padding:0.75rem; border:1px solid #30363d; border-radius:0.5rem;'>"
                        f"{safe_tail}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
        return_code = proc.wait()
        output = "".join(lines)
        if return_code != 0:
            output += f"\n[exit_code={return_code}]"
        return output
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        return f"Error ejecutando comando en streaming:\n{exc}"


def render_log_output(
    label: str,
    content: str,
    *,
    key: str,
    height: int = 280,
    download_name: str | None = None,
) -> None:
    """
    Renderiza logs en un cuadro con scroll y fácil de copiar.
    """
    st.text_area(
        label,
        value=content or "",
        height=height,
        key=key,
    )
    if download_name:
        st.download_button(
            label="Descargar log (.txt)",
            data=(content or "").encode("utf-8"),
            file_name=download_name,
            mime="text/plain",
            key=f"{key}_download",
        )


def is_yarn_resource_manager_up(host: str = "hadoop", port: int = 8032, timeout_s: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def is_port_open(host: str, port: int, timeout_s: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def is_any_endpoint_up(endpoints: list[tuple[str, int]], timeout_s: float = 1.5) -> bool:
    return any(is_port_open(h, p, timeout_s=timeout_s) for h, p in endpoints)


def build_service_health_dashboard() -> pd.DataFrame:
    checks = [
        {
            "Servicio": "HDFS NameNode",
            "Estado": "OK" if is_any_endpoint_up([("hadoop", 9000), ("127.0.0.1", 9000)]) else "NO",
            "Endpoint": "hadoop:9000 / 127.0.0.1:9000",
        },
        {
            "Servicio": "YARN ResourceManager",
            "Estado": "OK" if is_yarn_resource_manager_up() else "NO",
            "Endpoint": "hadoop:8032",
        },
        {
            "Servicio": "Kafka Broker",
            "Estado": "OK" if is_any_endpoint_up([("hadoop", 9092), ("127.0.0.1", 9092)]) else "NO",
            "Endpoint": "hadoop:9092 / 127.0.0.1:9092",
        },
        {
            "Servicio": "MariaDB (XAMPP)",
            "Estado": "OK" if is_port_open("127.0.0.1", 3306) else "NO",
            "Endpoint": "127.0.0.1:3306",
        },
        {
            "Servicio": "MongoDB",
            "Estado": "OK" if is_port_open("127.0.0.1", 27017) else "NO",
            "Endpoint": "127.0.0.1:27017",
        },
        {
            "Servicio": "HiveServer2",
            "Estado": "OK" if is_port_open("127.0.0.1", 10000) else "NO",
            "Endpoint": "127.0.0.1:10000",
        },
        {
            "Servicio": "NiFi UI",
            "Estado": "OK" if is_any_endpoint_up([("127.0.0.1", 8443), ("127.0.0.1", 8080)]) else "NO",
            "Endpoint": "127.0.0.1:8443 / 127.0.0.1:8080",
        },
    ]
    return pd.DataFrame(checks)


def spark_submit_cmd(script_path: str, *args: str, force_local: bool = False) -> str:
    local_flag = "--local " if force_local else ""
    arg_str = " ".join(str(a) for a in args if str(a).strip())
    suffix = f" {arg_str}" if arg_str else ""
    return f"./scripts/run_spark_submit.sh {local_flag}{script_path}{suffix}"


SPARK_PROFILE_SEGURO = "Seguro (evitar reinicios)"
SPARK_PROFILE_NORMAL = "Normal"
SPARK_PROFILE_OPTIONS = (SPARK_PROFILE_SEGURO, SPARK_PROFILE_NORMAL)


def spark_resource_env_for_profile(profile: str) -> dict[str, str]:
    """
    Variables de entorno consumidas por `scripts/run_spark_submit.sh` para limitar
    CPU/memoria y reducir reinicios del host en equipos de laboratorio.
    """
    if profile == SPARK_PROFILE_SEGURO:
        return {
            "SPARK_LOCAL_CORES": "2",
            "SPARK_LOCAL_DRIVER_MEMORY": "1G",
            "SPARK_EXECUTOR_CORES": "1",
            "SPARK_EXECUTOR_MEMORY": "1G",
            "SPARK_DRIVER_MEMORY": "1G",
            "SPARK_SQL_SHUFFLE_PARTITIONS": "24",
            "SPARK_DEFAULT_PARALLELISM": "6",
            "NUM_EXECUTORS": "1",
        }
    return {
        "SPARK_LOCAL_CORES": "4",
        "SPARK_LOCAL_DRIVER_MEMORY": "2G",
        "SPARK_EXECUTOR_CORES": "2",
        "SPARK_EXECUTOR_MEMORY": "2G",
        "SPARK_DRIVER_MEMORY": "2G",
        "SPARK_SQL_SHUFFLE_PARTITIONS": "48",
        "SPARK_DEFAULT_PARALLELISM": "12",
        "NUM_EXECUTORS": "2",
    }


def load_sample_data():
    gps_path = DATA_SAMPLE_DIR / "gps_events.csv"
    wh_path = DATA_SAMPLE_DIR / "warehouses.csv"
    routes_path = DATA_SAMPLE_DIR / "routes.csv"

    gps_df = pd.read_csv(gps_path) if gps_path.exists() else None
    wh_df = pd.read_csv(wh_path) if wh_path.exists() else None
    routes_df = (
        pd.read_csv(routes_path, comment="#") if routes_path.exists() else None
    )
    return gps_df, wh_df, routes_df


def _latest_file_by_pattern(base_dir: Path, pattern: str) -> Path | None:
    files = list(base_dir.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _load_latest_airflow_run_df(dag_ids: list[str], max_rows: int = 15) -> pd.DataFrame:
    """
    Devuelve un dataframe con las últimas ejecuciones encontradas en reports/airflow.
    """
    reports_base = PROJECT_ROOT / "reports" / "airflow"
    rows: list[dict] = []
    if not reports_base.exists():
        return pd.DataFrame()

    for dag_id in dag_ids:
        dag_dir = reports_base / dag_id
        if not dag_dir.exists():
            continue
        for fp in dag_dir.glob("*.json"):
            if fp.name == "LATEST.json":
                continue
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows.append(
                {
                    "dag_id": data.get("dag_id") or dag_id,
                    "run_id": data.get("run_id"),
                    "state": str(data.get("state") or "").replace("DagRunState.", ""),
                    "start_date": data.get("start_date"),
                    "end_date": data.get("end_date"),
                    "generated_at_utc": data.get("generated_at_utc"),
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["dag_id", "run_id"], keep="last")
    for c in ["generated_at_utc", "start_date", "end_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df.sort_values(by="generated_at_utc", ascending=False).head(max_rows)


def _load_recent_weather_ingest(max_rows: int = 100) -> pd.DataFrame:
    weather_dir = PROJECT_ROOT / "data" / "ingest" / "weather"
    latest = _latest_file_by_pattern(weather_dir, "weather_*.json")
    if latest is None:
        return pd.DataFrame()
    try:
        raw = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame()
    if isinstance(raw, list):
        df = pd.json_normalize(raw)
    elif isinstance(raw, dict):
        df = pd.json_normalize([raw])
    else:
        return pd.DataFrame()
    if not df.empty:
        df.insert(0, "source_file", latest.name)
    return df.head(max_rows)


def _latest_weather_file_info() -> tuple[Path | None, pd.Timestamp | None]:
    weather_dir = PROJECT_ROOT / "data" / "ingest" / "weather"
    latest = _latest_file_by_pattern(weather_dir, "weather_*.json")
    if latest is None:
        return None, None
    ts = pd.Timestamp(latest.stat().st_mtime, unit="s", tz="UTC")
    return latest, ts


def _recent_weather_files(max_items: int = 5) -> pd.DataFrame:
    weather_dir = PROJECT_ROOT / "data" / "ingest" / "weather"
    if not weather_dir.exists():
        return pd.DataFrame()
    files = [p for p in weather_dir.glob("weather_*.json") if p.is_file()]
    if not files:
        return pd.DataFrame()
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:max_items]
    rows = []
    for fp in files:
        rows.append(
            {
                "file": fp.name,
                "modified_local": _format_local_ts(pd.Timestamp(fp.stat().st_mtime, unit="s", tz="UTC")),
                "size_bytes": fp.stat().st_size,
            }
        )
    return pd.DataFrame(rows)


def _format_local_ts(ts: pd.Timestamp | None) -> str:
    if ts is None or pd.isna(ts):
        return "N/D"
    try:
        return ts.tz_convert("Europe/Madrid").strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts)


def _to_utc_timestamp(ts: pd.Timestamp) -> pd.Timestamp:
    """
    Normaliza un Timestamp a UTC soportando valores naive y tz-aware.
    """
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _latest_fase_i_artifact_timestamp() -> tuple[pd.Timestamp | None, str]:
    """
    Busca la marca temporal más reciente de artefactos típicos de Fase I.
    """
    candidates = [
        PROJECT_ROOT / "data" / "sample" / "gps_events.csv",
        PROJECT_ROOT / "data" / "sample" / "gps_events.json",
        PROJECT_ROOT / "data" / "ingest" / "weather",
        Path("/home/hadoop/data/gps_logs"),
    ]
    latest_ts: pd.Timestamp | None = None
    latest_src = "N/D"
    for p in candidates:
        if not p.exists():
            continue
        if p.is_dir():
            files = [f for f in p.iterdir() if f.is_file()]
            if not files:
                continue
            fp = max(files, key=lambda x: x.stat().st_mtime)
            mtime = pd.Timestamp(fp.stat().st_mtime, unit="s", tz="UTC")
            src = str(fp)
        else:
            mtime = pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC")
            src = str(p)
        if latest_ts is None or mtime > latest_ts:
            latest_ts = mtime
            latest_src = src
    return latest_ts, latest_src


def _summarize_gps_file(path: Path) -> dict[str, str]:
    """
    Devuelve metadatos del fichero GPS para validar si está actualizado.
    """
    if not path.exists():
        return {"mtime": "N/D", "ts_min": "N/D", "ts_max": "N/D", "rows": "0"}

    mtime = _format_local_ts(pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC"))
    try:
        if path.suffix.lower() == ".json":
            df = pd.read_json(path, lines=True)
        else:
            df = pd.read_csv(path)
    except Exception:
        return {"mtime": mtime, "ts_min": "N/D", "ts_max": "N/D", "rows": "N/D"}

    rows = str(len(df))
    if "ts" not in df.columns or df.empty:
        return {"mtime": mtime, "ts_min": "N/D", "ts_max": "N/D", "rows": rows}

    ts = pd.to_datetime(df["ts"], format="ISO8601", errors="coerce", utc=True).dropna()
    if ts.empty:
        return {"mtime": mtime, "ts_min": "N/D", "ts_max": "N/D", "rows": rows}

    return {
        "mtime": mtime,
        "ts_min": _format_local_ts(ts.min()),
        "ts_max": _format_local_ts(ts.max()),
        "rows": rows,
    }


def get_mongo_client() -> pymongo.MongoClient:
    # Fail-fast para UX: no bloquear ~30s si Mongo no está levantado
    return pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)


def get_store() -> dict:
    """
    Pequeño "store" persistente para modo demo (sin Mongo).
    """
    if "control_tower_store" not in st.session_state:
        st.session_state["control_tower_store"] = {
            "incidents": [],
            "decisions": [],
        }
    return st.session_state["control_tower_store"]


def _now_iso() -> str:
    return pd.Timestamp.utcnow().isoformat(timespec="seconds")


def compute_status(agg_df: pd.DataFrame | None, anom_df: pd.DataFrame | None) -> tuple[str, str]:
    """
    Devuelve (label, color_hex) en base a reglas simples para operación diaria.
    """
    if agg_df is None or agg_df.empty:
        return ("SIN DATOS", "#6c757d")

    avg_delay = float(agg_df.get("avg_delay_min", pd.Series([0.0])).mean())
    anom_ratio = 0.0
    if anom_df is not None and not anom_df.empty and agg_df is not None and not agg_df.empty:
        # Aproximación: anomalías / filas de agregados mostradas
        anom_ratio = min(1.0, len(anom_df) / max(1, len(agg_df)))

    if avg_delay >= 45 or anom_ratio >= 0.20:
        return ("CRÍTICO", "#dc3545")
    if avg_delay >= 20 or anom_ratio >= 0.08:
        return ("DEGRADADO", "#fd7e14")
    return ("NORMAL", "#198754")


def estimate_delay_cost_eur(agg_df: pd.DataFrame | None, delay_cost_eur_per_min: float) -> float:
    if agg_df is None or agg_df.empty:
        return 0.0
    if {"avg_delay_min", "vehicle_count"}.issubset(agg_df.columns):
        return float((agg_df["avg_delay_min"] * agg_df["vehicle_count"]).sum() * delay_cost_eur_per_min)
    if "avg_delay_min" in agg_df.columns:
        return float(agg_df["avg_delay_min"].sum() * delay_cost_eur_per_min)
    return 0.0


def _ensure_demo_incidents_from_anomalies(anom_df: pd.DataFrame | None) -> None:
    store = get_store()
    if store.get("incidents"):
        return
    if anom_df is None or anom_df.empty:
        return
    # Crear incidencias “activas” a partir de anomalías (demo)
    for i, row in anom_df.head(20).iterrows():
        store["incidents"].append(
            {
                "incident_id": f"INC-DEMO-{i}",
                "created_at": _now_iso(),
                "status": "nueva",
                "severity": float(row.get("avg_delay_min", 0) or 0),
                "warehouse_id": str(row.get("warehouse_id", "") or ""),
                "window_start": str(row.get("window_start", "") or ""),
                "reason": "Anomalía detectada (K-Means)",
                "asignado_a": "",
            }
        )


def upsert_incident(*, db: pymongo.database.Database | None, incident: dict) -> None:
    """
    Inserta/actualiza incidencia en Mongo si está disponible; si no, en store demo.
    """
    if db is None:
        store = get_store()
        existing = [x for x in store["incidents"] if x.get("incident_id") == incident.get("incident_id")]
        if existing:
            idx = store["incidents"].index(existing[0])
            store["incidents"][idx] = incident
        else:
            store["incidents"].append(incident)
        return
    coll = db[MONGO_INCIDENTS_COLLECTION]
    coll.update_one({"incident_id": incident.get("incident_id")}, {"$set": incident}, upsert=True)


def add_decision(*, db: pymongo.database.Database | None, decision: dict) -> None:
    if db is None:
        store = get_store()
        store["decisions"].append(decision)
        return
    coll = db[MONGO_DECISIONS_COLLECTION]
    coll.insert_one(decision)


def render_search_highlight(context_text: str) -> None:
    """
    Si el usuario ha usado el buscador lateral, muestra un pequeño
    recuadro explicando por qué esta etapa es relevante para el término.
    """
    term = str(st.session_state.get("sidebar_search_term", "") or "").strip()
    if not term:
        return

    st.markdown(
        f"""
<div style="border-left: 4px solid #4b8bf4; padding: 0.5rem 0.75rem; background-color: #f2f6ff; margin-bottom: 0.75rem;">
<strong>Buscador KDD</strong> – Has buscado <span style="background-color:#fff3bf;"><strong>{term}</strong></span>.
Esta etapa está relacionada porque {context_text}.
</div>
""",
        unsafe_allow_html=True,
    )

def render_admin_actions(agg_df: pd.DataFrame | None, anom_df: pd.DataFrame | None) -> None:
    """
    Controles tipo 'backoffice' que ilustran qué podría hacer
    un usuario administrativo explotando el dato.
    """
    st.markdown("### Acciones típicas de un usuario administrativo")
    st.markdown(
        """
        Piensa en esta sección como un **backoffice ligero** integrado en el dashboard:

        - Botones de **consulta rápida** (¿qué almacenes van peor hoy?).
        - Botones de **informes** (resumen ejecutivo para comité, exportar a CSV/PDF, etc.).
        """
    )

    st.markdown("#### Opciones de consulta e informes")
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        umbral = st.slider(
            "Umbral de retraso medio (min) para considerar 'crítico'",
            min_value=5,
            max_value=120,
            value=30,
            step=5,
            key="umbral_critico_admin",
        )

    with col2:
        if st.button("Ver ventanas críticas (retraso > umbral)", key="btn_ventanas_criticas"):
            if agg_df is not None and not agg_df.empty and "avg_delay_min" in agg_df.columns:
                crit_df = agg_df[agg_df["avg_delay_min"] > umbral]
                if not crit_df.empty:
                    st.subheader("Ventanas críticas por retraso medio")
                    st.dataframe(crit_df)
                else:
                    st.info("Con los datos actuales no hay ventanas por encima del umbral seleccionado.")
            else:
                st.warning("No hay datos agregados cargados para aplicar este filtro.")

    with col3:
        if st.button("Top 5 almacenes con más retrasos", key="btn_top5_almacenes"):
            if agg_df is not None and not agg_df.empty and {
                "warehouse_id",
                "avg_delay_min",
            }.issubset(agg_df.columns):
                resumen = (
                    agg_df.groupby("warehouse_id")["avg_delay_min"]
                    .mean()
                    .sort_values(ascending=False)
                    .head(5)
                    .reset_index()
                )
                resumen.columns = ["warehouse_id", "retraso_medio_min"]
                st.subheader("Top 5 almacenes por retraso medio")
                st.dataframe(resumen)
            else:
                st.warning("No hay datos suficientes para calcular el Top 5 de almacenes.")

    if st.button("Generar informe ejecutivo (simulado)", key="btn_informe_ejecutivo"):
        st.subheader("Resumen ejecutivo (ejemplo)")
        if agg_df is not None and not agg_df.empty:
            max_delay = agg_df.get("avg_delay_min", pd.Series(dtype=float)).max()
            total_registros = len(agg_df)
            st.markdown(
                f"""
                - **Registros de retrasos analizados**: `{total_registros}`.
                - **Retraso medio máximo observado**: `{max_delay:.1f}` minutos.

                Un usuario administrativo podría exportar este resumen a PDF/PowerPoint
                o incluirlo en un informe diario de calidad de servicio.
                """
            )
        else:
            st.markdown(
                """
                No hay datos reales cargados, pero aquí se mostraría un
                **resumen ejecutivo** con:

                - Volumen de envíos afectados.
                - Top almacenes problemáticos.
                - Evolución del retraso medio semana a semana.
                """
            )

        if anom_df is not None and not anom_df.empty:
            total_anom = len(anom_df)
            st.markdown(f"- **Ventanas marcadas como anómalas**: `{total_anom}`.")


def navigate_to(page_label: str) -> None:
    """
    Cambia de pestaña dentro de la propia app sin perder la URL.
    """
    st.session_state["sidebar_page"] = page_label


def render_top_nav(current_label: str) -> None:
    """
    Muestra controles de navegación anterior/siguiente al inicio de cada página.
    """
    if current_label not in PAGE_LABELS:
        return
    idx = PAGE_LABELS.index(current_label)
    cols = st.columns(3)
    with cols[0]:
        if idx > 0:
            st.button(
                f"← {PAGE_LABELS[idx - 1]}",
                key=f"topnav_prev_{idx}",
                on_click=navigate_to,
                args=(PAGE_LABELS[idx - 1],),
            )
    with cols[2]:
        if idx < len(PAGE_LABELS) - 1:
            st.button(
                f"{PAGE_LABELS[idx + 1]} →",
                key=f"topnav_next_{idx}",
                on_click=navigate_to,
                args=(PAGE_LABELS[idx + 1],),
            )


def show_text_file_preview(path: Path, label: str, max_lines: int = 5) -> None:
    """
    Muestra un resumen de un fichero de texto (primeras y últimas N líneas).
    Si el fichero tiene <= 2 * max_lines, se muestra completo.
    """
    if not path.exists():
        st.info(f"No se ha encontrado `{path.relative_to(PROJECT_ROOT)}`.")
        return

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        st.warning(f"No se ha podido leer `{path}`: {exc}")
        return

    lines = content.splitlines()
    if len(lines) <= max_lines * 2:
        preview = "\n".join(lines)
    else:
        head = "\n".join(lines[:max_lines])
        tail = "\n".join(lines[-max_lines:])
        preview = f"{head}\n...\n{tail}"

    suffix = path.suffix.lower()
    if suffix == ".json":
        language = "json"
    elif suffix in {".md", ".markdown"}:
        language = "markdown"
    else:
        language = "text"

    with st.expander(label):
        st.code(preview, language=language)


def page_arranque_servicios():
    st.header("0 · Arranque de servicios del clúster")
    render_top_nav("0 · Arranque de servicios")
    render_search_highlight(
        "aquí se gestionan los **servicios base del clúster** (HDFS, Kafka, Hive, MongoDB, NiFi, MariaDB) y se relaciona con la orquestación posterior en **Airflow**."
    )
    st.info(
        "**Si el equipo reinicia con frecuencia:** en las pestañas que lanzan Spark (Fase II, Grafos, Fase III) "
        "usa el perfil **Seguro (evitar reinicios)** y deja activado el modo local cuando YARN falle. "
        "Evita arrancar todo el stack y lanzar jobs pesados al mismo tiempo."
    )
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD**

        Antes de empezar con la Fase I (ingesta) necesitamos tener levantado todo el
        **stack de servicios** del proyecto:

        - HDFS y YARN (almacenamiento distribuido y ejecución de Spark).
        - Kafka (cola de eventos para GPS y alertas).
        - Hive (metastore y consultas SQL sobre HDFS).
        - MongoDB y MariaDB (capas de almacenamiento analítico).
        - NiFi y servicios auxiliares documentados en el documento `docs/ARRANQUE_SERVICIOS.md`
          (consultable más abajo desde esta misma pestaña).

        Esta pestaña debe ejecutarse **en el nodo donde están instalados los servicios**
        (por ejemplo, la máquina `hadoop` del clúster).

        - **Entrada**: configuración ya preparada en los scripts del proyecto.
        - **Salida**: servicios arriba y verificados para poder seguir con las fases KDD.
        """
    )
    st.subheader("Cuadro de mando de servicios (tiempo real)")
    col_refresh, col_hint = st.columns([1, 2])
    with col_refresh:
        if st.button("Actualizar estado", key="refresh_service_dashboard"):
            st.rerun()
    with col_hint:
        st.caption("Semáforo rápido para validar si el stack base está listo antes de ejecutar fases KDD.")

    health_df = build_service_health_dashboard()
    ok_count = int((health_df["Estado"] == "OK").sum())
    total_count = int(len(health_df))
    no_count = total_count - ok_count
    c1, c2, c3 = st.columns(3)
    c1.metric("Servicios OK", f"{ok_count}/{total_count}")
    c2.metric("Servicios NO", f"{no_count}")
    c3.metric("Disponibilidad", f"{(ok_count / max(1, total_count)) * 100:.0f}%")
    st.dataframe(health_df, width="stretch", hide_index=True)
    if no_count > 0:
        st.warning("Hay servicios pendientes. Arranca servicios o revisa puertos antes de seguir con las fases.")
    else:
        st.success("Stack base operativo. Puedes continuar con Fase I/Fase II/Fase III.")

    docs_path = PROJECT_ROOT / "docs" / "ARRANQUE_SERVICIOS.md"
    if docs_path.exists():
        with st.expander("Ver detalle de arranque de servicios (`docs/ARRANQUE_SERVICIOS.md`)"):
            st.markdown(docs_path.read_text(encoding="utf-8"))
    else:
        st.info("No se ha encontrado `docs/ARRANQUE_SERVICIOS.md` en el proyecto.")

    st.subheader("Comando que se va a ejecutar")
    st.code("SENTINEL360_SKIP_SUDO_STARTS=1 ./scripts/start_servicios.sh", language="bash")

    st.markdown(
        """
        **¿Qué hace `start_servicios.sh`?**

        - **Objetivo**: levantar de forma ordenada los servicios base del clúster
          (HDFS, YARN, Kafka, Hive, MongoDB, MariaDB, NiFi, etc.).
        - **Entrada**: configuración del entorno (variables como `HADOOP_HOME`, `HIVE_HOME`,
          rutas de logs, etc.) ya definida en el propio script y en el sistema.
        - **Salida**:
          - Servicios arrancados si todo va bien.
          - Ficheros de log actualizados (por ejemplo en `logs/`) para diagnosticar errores.
        """
    )

    if st.button("Arrancar servicios (start_servicios.sh)"):
        st.subheader("Salida en tiempo real")
        live_output = st.empty()
        with st.spinner("Arrancando servicios..."):
            output = run_command_streaming(
                "./scripts/start_servicios.sh",
                live_output,
                extra_env={"SENTINEL360_SKIP_SUDO_STARTS": "1"},
            )
        st.subheader("Salida del script")
        render_log_output(
            "Log de `start_servicios.sh`",
            output,
            key="log_start_servicios",
            download_name="start_servicios.log.txt",
        )
        if "Arráncalo manualmente" in output or "omite sudo" in output:
            st.warning(
                "Se ha ejecutado en modo no interactivo (sin sudo). "
                "Si MariaDB/XAMPP no estaba arriba, arráncalo en terminal con: "
                "`sudo /opt/lampp/lampp startmysql`"
            )

    st.subheader("Comprobación rápida de puertos críticos")
    st.code(
        'nc -z -w2 127.0.0.1 3306 && echo "MariaDB OK" || echo "MariaDB NO"\n'
        'nc -z -w2 127.0.0.1 27017 && echo "Mongo OK" || echo "Mongo NO"\n'
        'nc -z -w2 127.0.0.1 10000 && echo "HiveServer2 OK" || echo "HiveServer2 NO"',
        language="bash",
    )
    if st.button("Verificar puertos (3306/27017/10000)"):
        with st.spinner("Comprobando puertos de servicios..."):
            checks_output = run_command(
                'nc -z -w2 127.0.0.1 3306 && echo "MariaDB OK" || echo "MariaDB NO"; '
                'nc -z -w2 127.0.0.1 27017 && echo "Mongo OK" || echo "Mongo NO"; '
                'nc -z -w2 127.0.0.1 10000 && echo "HiveServer2 OK" || echo "HiveServer2 NO"'
            )
        render_log_output(
            "Resultado de comprobación de puertos",
            checks_output,
            key="log_health_ports",
            download_name="healthcheck_puertos.log.txt",
        )

    st.subheader("Ejecutar todo desde Airflow")
    st.markdown(
        "Puedes **orquestar todo el pipeline** (arranque de servicios, ingesta, Kafka, Hive, Spark batch/streaming, dashboards) desde **Apache Airflow**. "
        "Arranca Airflow con `bash ./scripts/start_airflow.sh`, configura `dags_folder` en `airflow.cfg` apuntando a la carpeta `airflow/` del proyecto y dispara los DAGs en el orden indicado en la documentación."
    )
    airflow_docs_path = PROJECT_ROOT / "docs" / "AIRFLOW_DAGS.md"
    if airflow_docs_path.exists():
        st.markdown("- **Documentación completa**: `docs/AIRFLOW_DAGS.md`")
        with st.expander("Ver documentación de Airflow (`docs/AIRFLOW_DAGS.md`)"):
            st.markdown(airflow_docs_path.read_text(encoding="utf-8"))
    else:
        st.info("No se ha encontrado `docs/AIRFLOW_DAGS.md` en el proyecto.")

    show_text_file_preview(
        SCRIPTS_DIR / "start_servicios.sh",
        "Ver contenido de `scripts/start_servicios.sh`",
    )

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    st.button(
        "Ir a 1 · Fase I – Ingesta",
        key="nav_0_to_1",
        on_click=navigate_to,
        args=("1 · Fase I – Ingesta",),
    )


def page_fase_i_ingesta():
    st.header("1 · Fase I – Ingesta (NiFi → Kafka + HDFS raw)")
    render_top_nav("1 · Fase I – Ingesta")
    render_search_highlight(
        "en esta fase se **ingestan los logs GPS y los datos de OpenWeather** con NiFi, se publican en **Kafka** y se dejan copias en **HDFS raw**."
    )
    st.info(
        "Esta fase no ejecuta Spark desde el front. Si tras la ingesta el equipo queda inestable, "
        "al pasar a **Fase II / Grafos / Fase III** elige el perfil **Seguro (evitar reinicios)** y evita jobs pesados en paralelo."
    )
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase I – Selección e ingesta de datos)**

        En esta etapa preparamos las **rutas en HDFS** y los **datos de ejemplo** para que NiFi
        pueda leer los logs GPS y publicar en Kafka (`raw-data` / `filtered-data`), dejando además
        una copia *raw* en HDFS.

        - **Entrada**:
          - Ficheros de ejemplo en `data/sample/gps_events.*`.
          - Configuración del flujo NiFi (`ingest/gps_transport_flow_importable.json`).
        - **Transformación**:
          - Copia de datos maestros y logs al HDFS del proyecto.
          - Preparación de directorios esperados por NiFi.
        - **Salida esperada**:
          - Directorios `raw` poblados en HDFS.
          - Flujo NiFi listo para leer esos datos y mandarlos a Kafka.

        Más detalle de esta fase en `docs/INGEST/` y en `docs/KDD_FASES.md`.
        """
    )
    st.subheader("Trazabilidad temporal de Fase I")
    now_ts = _to_utc_timestamp(pd.Timestamp.utcnow())
    latest_f1_ts, latest_f1_src = _latest_fase_i_artifact_timestamp()
    cts1, cts2 = st.columns(2)
    with cts1:
        st.metric("Hora actual del panel", _format_local_ts(now_ts))
    with cts2:
        st.metric("Última evidencia real Fase I", _format_local_ts(latest_f1_ts))
    st.caption(f"Fuente de evidencia detectada: `{latest_f1_src}`")

    # Documentación relacionada accesible desde la propia pestaña
    ingest_docs = [
        ("docs/KDD_FASES.md", "Ver resumen de fases KDD (`docs/KDD_FASES.md`)"),
        ("ingest/FLUJO_GPS_README.md", "Ver flujo de ingesta GPS (`ingest/FLUJO_GPS_README.md`)"),
        ("ingest/nifi/FASE_I_INGESTA.md", "Detalle NiFi Fase I (`ingest/nifi/FASE_I_INGESTA.md`)"),
        ("ingest/nifi/RESOLVER_ERRORES_FLUJO_GPS.md", "Resolver errores flujo GPS (`ingest/nifi/RESOLVER_ERRORES_FLUJO_GPS.md`)"),
    ]
    for rel_path, label in ingest_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    st.subheader("Vista previa de ficheros de entrada")
    gps_json_path = PROJECT_ROOT / "data" / "sample" / "gps_events.json"
    gps_meta = _summarize_gps_file(gps_json_path)
    st.caption(
        "GPS (verificación) -> "
        f"modificado: {gps_meta['mtime']} | "
        f"rango ts: {gps_meta['ts_min']} -> {gps_meta['ts_max']} | "
        f"filas: {gps_meta['rows']}"
    )
    show_text_file_preview(
        gps_json_path,
        "Muestra de `data/sample/gps_events.json` (5 primeras y 5 últimas líneas si es largo)",
    )
    nifi_flow_path = PROJECT_ROOT / "ingest" / "gps_transport_flow_importable.json"
    show_text_file_preview(
        nifi_flow_path,
        "Muestra de `ingest/gps_transport_flow_importable.json` (definición flujo NiFi)",
    )

    nifi_png = PROJECT_ROOT / "ingest" / "capturas" / "grupoProcesadores.png"
    if nifi_png.exists():
        st.subheader("Vista del grupo de procesadores NiFi")
        st.image(
            str(nifi_png),
            caption=(
                "Grupo de procesadores NiFi para la Fase I: "
                "GetFile → UpdateAttribute → PutHDFS + SplitText → "
                "EvaluateJsonPath → RouteOnAttribute → PublishKafka raw/filtered"
            ),
        )

    st.subheader("NiFi UI (comprobación y arranque)")
    st.markdown(
        "- URL recomendada: [https://localhost:8443/nifi](https://localhost:8443/nifi)\n"
        "- Fallback HTTP (si aplica): [http://localhost:8080/nifi](http://localhost:8080/nifi)"
    )
    nifi_up = is_any_endpoint_up([("127.0.0.1", 8443), ("127.0.0.1", 8080)])
    st.metric("Estado NiFi UI", "OK" if nifi_up else "NO DISPONIBLE")
    col_nifi1, col_nifi2 = st.columns(2)
    with col_nifi1:
        if st.button("Comprobar NiFi UI ahora", key="check_nifi_ui_f1"):
            check_out = run_command(
                'nc -z -w2 127.0.0.1 8443 && echo "NiFi HTTPS OK (8443)" || echo "NiFi HTTPS NO (8443)"; '
                'nc -z -w2 127.0.0.1 8080 && echo "NiFi HTTP OK (8080)" || echo "NiFi HTTP NO (8080)"'
            )
            render_log_output(
                "Resultado comprobación NiFi UI",
                check_out,
                key="log_check_nifi_ui_f1",
                download_name="check_nifi_ui.log.txt",
            )
    with col_nifi2:
        if st.button("Arrancar NiFi desde front", key="start_nifi_from_front_f1"):
            st.subheader("Salida en tiempo real (NiFi)")
            slot_nifi = st.empty()
            with st.spinner("Intentando arrancar NiFi..."):
                nifi_out = run_command_streaming(
                    'if [ -x "/opt/nifi/nifi-2.7.2/bin/nifi.sh" ]; then '
                    '/opt/nifi/nifi-2.7.2/bin/nifi.sh start; '
                    'elif [ -x "/usr/local/nifi/bin/nifi.sh" ]; then '
                    '/usr/local/nifi/bin/nifi.sh start; '
                    'else echo "No se encontró nifi.sh en rutas conocidas."; fi',
                    slot_nifi,
                )
            render_log_output(
                "Log arranque NiFi",
                nifi_out,
                key="log_start_nifi_f1",
                download_name="start_nifi.log.txt",
            )

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/setup_hdfs.sh\n"
        "./scripts/preparar_ingesta_nifi.sh\n",
        language="bash",
    )

    st.markdown(
        """
        **¿Qué hacen estos scripts?**

        - `setup_hdfs.sh`:
          - **Objetivo**: crear en HDFS las rutas necesarias para el proyecto
            (raw, processed, maestros, etc.).
          - **Entrada**: estructura de rutas definida en el propio script y en `config.py`.
          - **Salida**: directorios creados en HDFS, listos para recibir datos desde NiFi y Spark.
        - `preparar_ingesta_nifi.sh`:
          - **Objetivo**: copiar datos de ejemplo y dejar preparada la carpeta de entrada
            que NiFi vigila (por ejemplo `gps_logs` en el nodo hadoop).
          - **Entrada**: ficheros de `data/sample` (como `gps_events.json`).
          - **Salida**: ficheros ubicados en el directorio de entrada que usa el flujo NiFi.
        """
    )

    show_text_file_preview(
        SCRIPTS_DIR / "setup_hdfs.sh",
        "Ver contenido de `scripts/setup_hdfs.sh`",
    )
    show_text_file_preview(
        SCRIPTS_DIR / "preparar_ingesta_nifi.sh",
        "Ver contenido de `scripts/preparar_ingesta_nifi.sh`",
    )

    st.markdown(
        "**Requisito:** tener el clúster levantado (HDFS, etc.). Si no, ve a **0 · Arranque de servicios** y pulsa *Arrancar servicios*."
    )
    if st.button("Ejecutar comandos de Fase I"):
        with st.spinner("Ejecutando scripts de Fase I..."):
            output = run_command("./scripts/setup_hdfs.sh && ./scripts/preparar_ingesta_nifi.sh")
        st.subheader("Salida de los scripts")
        render_log_output(
            "Log de Fase I",
            output,
            key="log_fase_i",
            download_name="fase_i.log.txt",
        )
        if "Connection refused" in output or "No se puede conectar a HDFS" in output:
            st.warning(
                "HDFS no está disponible. Arranca antes los servicios desde la pestaña **0 · Arranque de servicios** "
                "(botón *Arrancar servicios*) o ejecuta en terminal: `./scripts/start_servicios.sh`."
            )
        # Fuerza rerender para refrescar timestamps/evidencias tras ejecutar la fase.
        st.rerun()

    st.subheader("Comprobar ingesta en HDFS (sin salir del front)")
    st.code(
        "hdfs dfs -ls /user/hadoop/proyecto/raw\n"
        "hdfs dfs -ls /user/hadoop/proyecto/warehouses\n"
        "hdfs dfs -ls /user/hadoop/proyecto/routes\n"
        "hdfs dfs -du -h /user/hadoop/proyecto/raw",
        language="bash",
    )
    if st.button("Verificar datos en HDFS ahora", key="fase1_check_hdfs_now"):
        with st.spinner("Comprobando rutas y datos en HDFS..."):
            hdfs_check_output = run_command(
                "hdfs dfs -ls /user/hadoop/proyecto/raw 2>&1; "
                "hdfs dfs -ls /user/hadoop/proyecto/warehouses 2>&1; "
                "hdfs dfs -ls /user/hadoop/proyecto/routes 2>&1; "
                "hdfs dfs -du -h /user/hadoop/proyecto/raw 2>&1; "
                "echo '--- MUESTRA (raw/gps_events.json) ---'; "
                "hdfs dfs -cat /user/hadoop/proyecto/raw/gps_events.json 2>/dev/null | sed -n '1,3p' || true"
            )
        render_log_output(
            "Resultado comprobación HDFS (Fase I)",
            hdfs_check_output,
            key="log_fase1_hdfs_check",
            download_name="fase1_hdfs_check.log.txt",
        )

    st.subheader("Datos generados por la ejecución (si existen)")
    weather_df = _load_recent_weather_ingest(max_rows=50)
    weather_fp, weather_ts = _latest_weather_file_info()
    now_ts = _to_utc_timestamp(pd.Timestamp.utcnow())
    if not weather_df.empty:
        st.markdown("**Última captura meteorológica (`data/ingest/weather`)**")
        st.caption(
            "Archivo usado: "
            f"`{weather_fp.name if weather_fp else 'N/D'}` | "
            f"modificado: `{_format_local_ts(weather_ts)}`"
        )
        if weather_ts is not None:
            age_hours = float((now_ts - weather_ts).total_seconds() / 3600.0)
            if age_hours > 6:
                st.warning(
                    f"La captura meteorológica visible tiene {age_hours:.1f} h de antigüedad. "
                    "Si acabas de ejecutar Fase I pero no se lanzó OpenWeather, este bloque puede quedar desactualizado."
                )
        st.dataframe(weather_df, width="stretch")
    else:
        st.info(
            "Aún no se han encontrado ficheros en `data/ingest/weather/`. "
            "Ejecuta la ingesta para que aparezcan aquí."
        )
    recent_weather_df = _recent_weather_files(max_items=5)
    if not recent_weather_df.empty:
        st.markdown("**Últimos ficheros meteorológicos detectados**")
        st.dataframe(recent_weather_df, width="stretch", hide_index=True)
    st.caption(
        "Nota: ejecutar `setup_hdfs.sh + preparar_ingesta_nifi.sh` no garantiza refrescar OpenWeather. "
        "Para actualizar este bloque, ejecuta la ingesta OpenWeather explícitamente."
    )
    st.markdown("**Actualizar OpenWeather manualmente**")
    ow_key_default = os.environ.get("OPENWEATHER_API_KEY", "")
    ow_api_key = st.text_input(
        "API key de OpenWeather",
        value=ow_key_default,
        type="password",
        help="Necesaria para ejecutar scripts/ingest_openweather.py desde este front.",
        key="fase1_openweather_api_key",
    )
    ow_no_kafka = st.checkbox(
        "Solo guardar fichero local (sin enviar a Kafka)",
        value=False,
        key="fase1_openweather_no_kafka",
    )
    if st.button("Actualizar OpenWeather ahora", key="fase1_refresh_weather_now"):
        if not str(ow_api_key).strip():
            st.error(
                "Falta la API key de OpenWeather. "
                "Introduce la clave en este campo o exporta `OPENWEATHER_API_KEY` en tu entorno."
            )
            return
        st.subheader("Salida en tiempo real (OpenWeather)")
        weather_slot = st.empty()
        with st.spinner("Lanzando scripts/ingest_openweather.py ..."):
            weather_cmd = "python3 scripts/ingest_openweather.py"
            if ow_no_kafka:
                weather_cmd += " --no-kafka"
            weather_out = run_command_streaming(
                weather_cmd,
                weather_slot,
                extra_env={"OPENWEATHER_API_KEY": ow_api_key.strip()},
            )
        render_log_output(
            "Log de ingest_openweather.py",
            weather_out,
            key="log_ingest_openweather_f1",
            download_name="fase_i_openweather.log.txt",
        )
        m = re.search(r"Guardado:\s*(.+)", weather_out)
        if m:
            st.success(f"Nuevo fichero meteorológico generado: `{m.group(1).strip()}`")
        if "OPENWEATHER_API_KEY no definida" in weather_out or "[exit_code=" in weather_out:
            st.warning("La actualización de OpenWeather no terminó correctamente. Revisa el log.")
        st.rerun()

    fase_i_runs_df = _load_latest_airflow_run_df(
        dag_ids=["sentinel360_fase_I_ingesta", "sentinel360_fase_i_ingesta"],
        max_rows=10,
    )
    if not fase_i_runs_df.empty:
        st.markdown("**Últimas ejecuciones de Airflow detectadas para Fase I**")
        st.dataframe(fase_i_runs_df, width="stretch", hide_index=True)

    has_real_fase_i_data = (latest_f1_ts is not None) or (not weather_df.empty) or (not fase_i_runs_df.empty)
    if has_real_fase_i_data:
        st.info(
            "Datos reales detectados para Fase I: se ocultan los bloques de datos de ejemplo para evitar confusión."
        )
    else:
        st.subheader("Fallback: datos de ejemplo (data/sample)")
        gps_df, wh_df, routes_df = load_sample_data()
        if gps_df is not None:
            st.markdown("**Muestra de eventos GPS (`gps_events.csv`)**")
            st.dataframe(gps_df.head())
        else:
            st.info("No se ha encontrado `data/sample/gps_events.csv`.")

        st.markdown(
            """
            ### Cargar nuevos ficheros de ejemplo (GPS / rutas)

            Aquí puedes **probar otros ficheros de entrada** sin tocar el repositorio:

            - **GPS (`gps_events`)**:
              - Formatos soportados en el pipeline: **CSV o JSON**.
              - Campos típicos (ver `data/sample/README.md`):
                - `event_id`, `vehicle_id`, `ts` (timestamp ISO), `lat`, `lon`, `speed`, `warehouse_id`, `route_id`, `delay_minutes`.
              - El pipeline de limpieza (`clean_and_normalize.py`) está preparado para leer
                `gps_events*.csv` o `gps_events*.json` en la carpeta *raw* de HDFS.
            - **Rutas (`routes.csv`)**:
              - Formato actual soportado: **CSV**.
              - Estructura esperada:
                - `route_id`, `from_warehouse_id`, `to_warehouse_id`, `distance_km`, `avg_duration_min`.
              - Se usa como maestro de rutas en Hive/GraphFrames (no en JSON en la versión actual).

            Los ficheros que subas aquí se usan **solo para visualización en la demo**.  
            Para que entren en el pipeline real, deberás copiarlos después a `data/sample/`
            y/o subirlos a HDFS con los scripts de ingesta (`ingest_from_local.sh`, etc.).
            """
        )

        st.subheader("Subir nuevo fichero de GPS")
        gps_upload = st.file_uploader(
            "Sube un fichero de eventos GPS (CSV o JSON)",
            type=["csv", "json"],
            key="upload_gps_events",
        )
        if gps_upload is not None:
            try:
                if gps_upload.name.lower().endswith(".json"):
                    gps_new = pd.read_json(gps_upload)
                else:
                    gps_new = pd.read_csv(gps_upload)
                st.markdown("**Vista previa del fichero GPS subido**")
                st.dataframe(gps_new.head())
                st.info(
                    "Para usar este fichero en el pipeline real, guárdalo como "
                    "`gps_events.csv` o `gps_events.json` en `data/sample/` y "
                    "ejecuta después los scripts de ingesta para copiarlo a HDFS."
                )
            except Exception as exc:  # pragma: no cover - lectura interactiva
                st.error(f"No se ha podido leer el fichero GPS subido: {exc}")

        st.subheader("Subir nuevo fichero de rutas")
        routes_upload = st.file_uploader(
            "Sube un fichero de rutas (CSV)",
            type=["csv"],
            key="upload_routes",
        )
        if routes_upload is not None:
            try:
                routes_new = pd.read_csv(routes_upload)
                st.markdown("**Vista previa del fichero de rutas subido**")
                st.dataframe(routes_new.head())
                # Guardamos una copia en sesión para que otras pestañas (como grafos)
                # puedan usar las nuevas rutas sin tocar el CSV del repo.
                st.session_state["routes_override_df"] = routes_new
                st.info(
                    "El catálogo de rutas debe estar en CSV con columnas como "
                    "`route_id`, `from_warehouse_id`, `to_warehouse_id`, "
                    "`distance_km`, `avg_duration_min`. "
                    "Para usarlo en el pipeline, guárdalo como `routes.csv` en "
                    "`data/sample/` y vuelve a ejecutar los scripts de ingesta/Hive."
                )
            except Exception as exc:  # pragma: no cover
                st.error(f"No se ha podido leer el fichero de rutas subido: {exc}")

        st.subheader("Subir nuevo fichero de almacenes")
        wh_upload = st.file_uploader(
            "Sube un fichero de almacenes (CSV con `warehouse_id`, `name`, `city`, `country`, `lat`, `lon`, `capacity`)",
            type=["csv"],
            key="upload_warehouses",
        )
        if wh_upload is not None:
            try:
                wh_new = pd.read_csv(wh_upload)
                st.markdown("**Vista previa del fichero de almacenes subido**")
                st.dataframe(wh_new.head())
                st.session_state["warehouses_override_df"] = wh_new
                st.info(
                    "Para usar este fichero en el pipeline, guárdalo como `warehouses.csv` "
                    "en `data/sample/` y vuelve a ejecutar los scripts de ingesta/Hive. "
                    "Mientras tanto, la visualización de grafos y mapas usará esta versión en memoria."
                )
            except Exception as exc:  # pragma: no cover
                st.error(f"No se ha podido leer el fichero de almacenes subido: {exc}")

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 0 · Arranque de servicios",
            key="nav_1_to_0",
            on_click=navigate_to,
            args=("0 · Arranque de servicios",),
        )
    with cols[1]:
        st.button(
            "Ir a 2 · Fase II – Limpieza y enriquecimiento",
            key="nav_1_to_2",
            on_click=navigate_to,
            args=("2 · Fase II – Limpieza y enriquecimiento",),
        )


def page_fase_ii_limpieza_enriquecimiento():
    st.header("2 · Fase II – Limpieza y enriquecimiento")
    render_top_nav("2 · Fase II – Limpieza y enriquecimiento")
    render_search_highlight(
        "aquí **Spark** limpia y enriquece los datos de GPS con maestros de **rutas** y **almacenes**, preparando las tablas en **Hive**."
    )
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase II – Preprocesamiento y transformación)**

        Desde aquí se lanzan los jobs Spark de **limpieza** y **enriquecimiento** de los datos
        que vienen de la Fase I:

        - `clean_and_normalize.py`: normaliza y limpia los datos brutos en HDFS (`raw` → `cleaned`).
        - `enrich_with_hive.py`: cruza datos limpios con maestros de Hive (`warehouses`) y genera `enriched`.

        - **Entrada**:
          - Datos *raw* en HDFS (`/user/hadoop/proyecto/raw` y rutas definidas en `config.py`).
          - Tablas Hive de maestros (`warehouses`, `routes`).
        - **Transformación**:
          - Limpieza de columnas problemáticas, normalización de tipos y valores.
          - Join con almacenes/rutas para enriquecer los eventos.
        - **Salida esperada**:
          - Directorios `procesado/cleaned` y `procesado/enriched` en HDFS (ficheros Parquet).

        Para más detalle técnico, ver `docs/FASE_II_PREPROCESAMIENTO.md` y `docs/PROBAR_PIPELINE.md`.
        """
    )

    # Documentación técnica de apoyo para esta fase
    fase2_docs = [
        ("docs/FASE_II_PREPROCESAMIENTO.md", "Fase II – Preprocesamiento (`docs/FASE_II_PREPROCESAMIENTO.md`)"),
        ("docs/PROBAR_PIPELINE.md", "Cómo probar el pipeline (`docs/PROBAR_PIPELINE.md`)"),
    ]
    for rel_path, label in fase2_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py\n"
        "./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py\n",
        language="bash",
    )
    yarn_up = is_yarn_resource_manager_up()
    force_local = st.checkbox(
        "Forzar modo local de Spark (sin YARN)",
        value=not yarn_up,
        key="fase2_force_local",
        help="Recomendado si YARN no está disponible o si los jobs quedan en reintentos.",
    )
    resource_profile = st.selectbox(
        "Perfil de recursos Spark",
        options=list(SPARK_PROFILE_OPTIONS),
        index=0,
        key="fase2_resource_profile",
        help="Usa 'Seguro' si el equipo se reinicia o se queda sin memoria durante Fase II.",
    )
    spark_env = spark_resource_env_for_profile(resource_profile)
    # En perfil seguro priorizamos estabilidad: forzamos ejecución local para evitar
    # fallos YARN/AM en entornos con red/recursos inestables tras reinicios.
    force_local_effective = force_local or (resource_profile == SPARK_PROFILE_SEGURO)
    if resource_profile == SPARK_PROFILE_SEGURO and not force_local:
        st.info("Perfil seguro activo: Spark se ejecutará en modo local automáticamente.")
    if not yarn_up:
        st.warning("YARN ResourceManager no responde en `hadoop:8032`. Se recomienda `--local`.")

    st.markdown(
        """
        **¿Qué hace `run_spark_submit.sh` en esta fase?**

        - **Objetivo general**: encapsular la llamada a `spark-submit` con la configuración del clúster
          (YARN, jars adicionales, versión de Python, etc.) para no repetir opciones en cada comando.
        - **Entradas**:
          - El script Python a ejecutar (`spark/cleaning/clean_and_normalize.py`, `spark/cleaning/enrich_with_hive.py`, etc.).
          - Parámetros opcionales como `--local` para ejecutar sin YARN (ver `docs/PROBAR_PIPELINE.md`).
        - **Salidas**:
          - Jobs Spark ejecutados en el clúster (o en modo local).
          - Logs de Spark accesibles desde la consola y desde la UI de YARN.
        """
    )

    show_text_file_preview(
        SCRIPTS_DIR / "run_spark_submit.sh",
        "Ver contenido de `scripts/run_spark_submit.sh`",
    )

    if st.button("Lanzar limpieza + enriquecimiento (Spark)"):
        st.subheader("Salida en tiempo real")
        live_output = st.empty()
        with st.spinner("Lanzando jobs Spark de limpieza y enriquecimiento..."):
            cmd_clean = spark_submit_cmd(
                "spark/cleaning/clean_and_normalize.py",
                force_local=force_local_effective,
            )
            cmd_enrich = spark_submit_cmd(
                "spark/cleaning/enrich_with_hive.py",
                force_local=force_local_effective,
            )
            output = run_command_streaming(
                f"{cmd_clean} && {cmd_enrich}",
                live_output,
                extra_env=spark_env,
            )
        st.subheader("Salida final de Spark submit")
        render_log_output(
            "Log de Spark submit (Fase II)",
            output,
            key="log_fase_ii_spark",
            download_name="fase_ii_spark.log.txt",
        )

    st.subheader("Ejecuciones reales detectadas para Fase II")
    fase_ii_runs_df = _load_latest_airflow_run_df(
        dag_ids=["sentinel360_fase_II_preprocesamiento", "sentinel360_fase_ii_preprocesamiento"],
        max_rows=12,
    )
    if not fase_ii_runs_df.empty:
        st.dataframe(fase_ii_runs_df, width="stretch", hide_index=True)
    else:
        st.info("Aún no hay reportes de ejecuciones para Fase II en `reports/airflow`.")

    st.subheader("Validar éxito (Airflow + HDFS)")
    st.markdown(
        """
        **Qué comprueba esto**

        - **Airflow**: contenido reciente de `reports/airflow/.../LATEST.md` (estado del DAG si el reporte se actualizó).
        - **HDFS**: que existan salidas en `procesado/cleaned` y `procesado/enriched` (Parquet).
        - **Logs locales**: últimos ficheros en `reports/logs/` (ej. ejecuciones Spark guardadas manualmente).

        Un run en la tabla anterior con `state=running` y `end_date=None` puede ser histórico incompleto; la validación HDFS confirma si hay datos reales escritos.
        """
    )
    st.code(
        "# Ver reporte Airflow (Fase II)\n"
        "sed -n '1,80p' reports/airflow/sentinel360_fase_II_preprocesamiento/LATEST.md 2>/dev/null || "
        "sed -n '1,80p' reports/airflow/sentinel360_fase_ii_preprocesamiento/LATEST.md\n\n"
        "# Ver artefactos HDFS\n"
        "hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned\n"
        "hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched\n"
        "hdfs dfs -du -h /user/hadoop/proyecto/procesado/cleaned\n"
        "hdfs dfs -du -h /user/hadoop/proyecto/procesado/enriched\n\n"
        "# Logs locales recientes\n"
        "ls -lt reports/logs 2>/dev/null | head -8",
        language="bash",
    )
    if st.button("Ejecutar validación ahora (Fase II)", key="fase2_validate_success"):
        with st.spinner("Comprobando Airflow, HDFS y logs..."):
            validate_cmd = (
                'echo "=== Airflow LATEST.md (Fase II) ==="; '
                "for d in reports/airflow/sentinel360_fase_II_preprocesamiento "
                "reports/airflow/sentinel360_fase_ii_preprocesamiento; do "
                'if [ -f "$d/LATEST.md" ]; then echo "--- $d/LATEST.md ---"; '
                "sed -n '1,80p' \"$d/LATEST.md\"; fi; done; "
                'echo ""; echo "=== HDFS cleaned ==="; '
                "hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned 2>&1; "
                'echo ""; echo "=== HDFS enriched ==="; '
                "hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched 2>&1; "
                'echo ""; echo "=== HDFS du cleaned ==="; '
                "hdfs dfs -du -h /user/hadoop/proyecto/procesado/cleaned 2>&1; "
                'echo ""; echo "=== HDFS du enriched ==="; '
                "hdfs dfs -du -h /user/hadoop/proyecto/procesado/enriched 2>&1; "
                'echo ""; echo "=== reports/logs (últimos) ==="; '
                "ls -lt reports/logs 2>/dev/null | head -8 || echo '(sin carpeta reports/logs)'"
            )
            validate_out = run_command(validate_cmd)
        render_log_output(
            "Resultado validación Fase II (éxito técnico)",
            validate_out,
            key="log_fase2_validate",
            download_name="fase_ii_validacion_ok.log.txt",
        )

    # Si el usuario ha subido una versión de almacenes o rutas, la usamos aquí
    wh_df_override = st.session_state.get("warehouses_override_df")
    routes_df_override = st.session_state.get("routes_override_df")

    gps_df, wh_df, routes_df = load_sample_data()
    if wh_df_override is not None:
        wh_df = wh_df_override
    if routes_df_override is not None:
        routes_df = routes_df_override
    if wh_df is not None:
        st.subheader("Maestro de almacenes activo")
        st.dataframe(wh_df)
        if {"lat", "lon"}.issubset(wh_df.columns):
            st.map(wh_df.rename(columns={"lat": "latitude", "lon": "longitude"}))

    if routes_df is not None:
        st.subheader("Maestro de rutas activo")
        st.dataframe(routes_df)

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 1 · Fase I – Ingesta",
            key="nav_2_to_1",
            on_click=navigate_to,
            args=("1 · Fase I – Ingesta",),
        )
    with cols[1]:
        st.button(
            "Ir a 3 · Fase II – Grafos",
            key="nav_2_to_3",
            on_click=navigate_to,
            args=("3 · Fase II – Grafos",),
        )


def page_fase_ii_grafos():
    st.header("3 · Fase II – Grafos (GraphFrames)")
    render_top_nav("3 · Fase II – Grafos")
    render_search_highlight(
        "esta vista muestra la **topología híbrida de rutas**, los grafos con **GraphFrames**, la búsqueda de **rutas alternativas** y el impacto de incidencias (nieve, atascos) en costes."
    )
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase II – Modelado como grafo)**

        Esta pestaña acompaña el **análisis de grafos** sobre la red de transporte:

        - `transport_graph.py` construye el grafo almacenes–rutas y calcula shortest paths y componentes.
        - `ver_grafos_resultados.py` permite inspeccionar resultados y generar `grafo.png`.

        - **Entrada**:
          - Datos enriquecidos en HDFS (`procesado/enriched`).
          - Definiciones de almacenes y rutas en Hive.
        - **Transformación**:
          - Construcción de un grafo dirigido con GraphFrames.
          - Cálculo de componentes conectados y caminos mínimos.
        - **Salida esperada**:
          - Resultados en `procesado/graph` (Parquet).
          - Imagen `grafo.png` como apoyo visual para la demo.

        Aquí también simulamos **qué pasa cuando cae una ruta** y cómo
        afectan las **incidencias de tráfico o meteorología** (nieve, atascos, lluvia)
        al coste de transporte y a la búsqueda de rutas alternativas.
        """
    )

    # --- Mapa de España con todos los almacenes y rutas (visible al entrar en la pestaña) ---
    st.subheader("Mapa de España: almacenes y rutas (Sentinel360)")
    st.markdown(
        "Rutas del maestro (`routes.csv`) sobre mapa de España. "
        "Cada marcador es un almacén; las líneas representan las rutas entre ellos (azul = rutas; rojo = ruta seleccionada más abajo)."
    )
    gps_df_map, wh_df_map, routes_df_map = load_sample_data()
    wh_override = st.session_state.get("warehouses_override_df")
    if wh_override is not None:
        wh_df_map = wh_override
    routes_override = st.session_state.get("routes_override_df")
    if routes_override is not None:
        routes_df_map = routes_override

    if wh_df_map is not None and {"warehouse_id", "lat", "lon"}.issubset(wh_df_map.columns) and routes_df_map is not None and {"from_warehouse_id", "to_warehouse_id"}.issubset(routes_df_map.columns):
        base_cols = ["warehouse_id", "lat", "lon"]
        extra_cols = [c for c in ["name", "city"] if c in wh_df_map.columns]
        wh_coords_map = wh_df_map[base_cols + extra_cols].dropna(subset=["lat", "lon"])
        rutas_map = routes_df_map.dropna(subset=["from_warehouse_id", "to_warehouse_id"]).copy()
        rutas_map["from_warehouse_id"] = rutas_map["from_warehouse_id"].astype(str)
        rutas_map["to_warehouse_id"] = rutas_map["to_warehouse_id"].astype(str)
        rutas_map = rutas_map[rutas_map["from_warehouse_id"].str.startswith("WH-") & rutas_map["to_warehouse_id"].str.startswith("WH-")]
        merged_from = rutas_map.merge(wh_coords_map, left_on="from_warehouse_id", right_on="warehouse_id", how="left")
        merged_full = merged_from.merge(wh_coords_map, left_on="to_warehouse_id", right_on="warehouse_id", how="left", suffixes=("_from", "_to"))
        cols_line = ["from_warehouse_id", "to_warehouse_id", "lat_from", "lon_from", "lat_to", "lon_to"]
        if "distance_km" in merged_full.columns:
            cols_line.insert(2, "distance_km")
        lines_map = merged_full[cols_line].dropna(subset=["lat_from", "lon_from", "lat_to", "lon_to"])

        if not lines_map.empty:
            m_espana = folium.Map(location=[40.0, -3.7], zoom_start=5, tiles="OpenStreetMap")
            try:
                folium.raster_layers.WmsTileLayer(
                    url="https://www.ign.es/wms-inspire/mapa-raster",
                    name="IGN Mapa Raster",
                    fmt="image/png",
                    transparent=True,
                    version="1.3.0",
                    layers="mtn_rasterizado",
                    attr="© IGN España",
                    control=True,
                ).add_to(m_espana)
            except Exception:
                pass  # Si el WMS falla, el mapa sigue con OpenStreetMap
            for _, row in wh_coords_map.iterrows():
                parts = [str(row["warehouse_id"])]
                if "city" in row and not pd.isna(row.get("city")):
                    parts.append(str(row["city"]))
                tooltip = " – ".join(parts)
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=6,
                    color="#0066CC",
                    fill=True,
                    fill_color="#0066CC",
                    fill_opacity=0.9,
                    tooltip=tooltip,
                ).add_to(m_espana)
            for _, row in lines_map.iterrows():
                dist = row.get("distance_km") if "distance_km" in lines_map.columns else None
                label = f"{row['from_warehouse_id']} → {row['to_warehouse_id']}"
                if dist is not None and not pd.isna(dist):
                    try:
                        label += f" ({float(dist):.0f} km)"
                    except (TypeError, ValueError):
                        pass
                folium.PolyLine(
                    locations=[
                        [float(row["lat_from"]), float(row["lon_from"])],
                        [float(row["lat_to"]), float(row["lon_to"])],
                    ],
                    color="#0080FF",
                    weight=2,
                    opacity=0.6,
                    tooltip=label,
                ).add_to(m_espana)
            folium.LayerControl().add_to(m_espana)
            # Contenedor con altura fija para evitar espacio en blanco bajo el mapa (streamlit-folium)
            try:
                map_container = st.container(height=535, border=False)
            except TypeError:
                map_container = st.container()
            with map_container:
                st_folium(m_espana, width=900, height=500, key="mapa_espana_grafos")
        else:
            st.info("No se han podido dibujar rutas en el mapa (faltan coordenadas en algunos almacenes de las rutas).")
    else:
        st.info("Para ver el mapa hacen falta `warehouses.csv` (con warehouse_id, lat, lon) y `routes.csv` (con from_warehouse_id, to_warehouse_id).")

    st.markdown("---")
    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/graph/transport_graph.py\n"
        "python scripts/ver_grafos_resultados.py --viz\n",
        language="bash",
    )
    yarn_up = is_yarn_resource_manager_up()
    force_local = st.checkbox(
        "Forzar modo local de Spark (grafos)",
        value=not yarn_up,
        key="fase2_graph_force_local",
    )
    graph_resource_profile = st.selectbox(
        "Perfil de recursos Spark (grafos)",
        options=list(SPARK_PROFILE_OPTIONS),
        index=0,
        key="fase2_graph_resource_profile",
        help="Usa 'Seguro' si el equipo se reinicia durante GraphFrames o visualización.",
    )
    graph_spark_env = spark_resource_env_for_profile(graph_resource_profile)
    force_local_graph_effective = force_local or (graph_resource_profile == SPARK_PROFILE_SEGURO)
    if graph_resource_profile == SPARK_PROFILE_SEGURO and not force_local:
        st.info("Perfil seguro activo en grafos: Spark se ejecutará en modo local automáticamente.")
    if not yarn_up:
        st.warning("YARN ResourceManager no responde en `hadoop:8032`. Se recomienda `--local`.")

    grafo_png = PROJECT_ROOT / "grafo.png"
    if st.button("Lanzar análisis de grafos"):
        st.subheader("Salida en tiempo real (grafos)")
        live_output = st.empty()
        prev_mtime = grafo_png.stat().st_mtime if grafo_png.exists() else None
        with st.spinner("Lanzando Spark (GraphFrames) y generación de grafo..."):
            cmd_graph = spark_submit_cmd(
                "spark/graph/transport_graph.py",
                force_local=force_local_graph_effective,
            )
            output = run_command_streaming(
                f"{cmd_graph} && "
                f"{sys.executable} scripts/ver_grafos_resultados.py --viz",
                live_output,
                extra_env=graph_spark_env,
            )
        st.subheader("Salida final de comandos de grafos")
        render_log_output(
            "Log de grafos",
            output,
            key="log_grafos",
            download_name="fase_ii_grafos.log.txt",
        )

        new_mtime = grafo_png.stat().st_mtime if grafo_png.exists() else None
        if "[exit_code=" in output:
            st.error("La ejecución de grafos terminó con error. Revisa la salida final.")
        elif new_mtime is None:
            st.warning("El comando terminó, pero no se encontró `grafo.png`.")
        elif prev_mtime is None or (new_mtime > prev_mtime):
            st.success("Grafo regenerado correctamente.")
        else:
            st.info("El proceso terminó bien, pero `grafo.png` no cambió respecto a la versión anterior.")

    if grafo_png.exists():
        st.subheader("Imagen del grafo (`grafo.png`)")
        # Leemos bytes para evitar caché por ruta y ver la versión más reciente.
        st.image(grafo_png.read_bytes())
    else:
        st.info("Aún no se ha generado `grafo.png`. Ejecuta `ver_grafos_resultados.py --viz` primero.")

    st.markdown("---")
    st.subheader("Simulación de incidencias en rutas y coste añadido")
    st.markdown(
        """
        Esta sección es un **what-if** para explicar al usuario final:

        - Qué pasa si **cae una ruta** principal.
        - Cómo se calcula un **coste añadido** por desvío (minutos extra, distancia extra).
        - Cómo influyen **nieve, lluvia o atascos** sobre los tiempos de viaje.

        Los valores son de ejemplo, pero ilustran la lógica que luego
        se podría alimentar con datos reales de retrasos (`aggregated_delays`)
        y del maestro de rutas (`routes.csv`).
        """
    )

    # Inicialización de parámetros persistentes de simulación (para botón ACEPTAR / CANCELAR)
    if "graph_sim_params" not in st.session_state:
        st.session_state["graph_sim_params"] = {
            "fuel_cost": float(GRAPH_FUEL_COST_EUR_PER_KM),
            "delay_cost": float(GRAPH_DELAY_COST_EUR_PER_MIN),
        }

    with st.expander("¿Cómo se calculan exactamente estos costes? (para curiosos y desarrolladores)"):
        st.markdown(
            f"""
            **Modelo simplificado de cálculo**

            1. Partimos de una **duración base** de la ruta en minutos:
               - Por defecto: `{GRAPH_BASE_DURATION_MIN:.0f}` min (4 horas), o
               - Si existe `routes.csv`, usamos la media de `avg_duration_min`.
            2. Para cada tipo de incidencia definimos un **factor de impacto** fijo
               (más alto para nieve/atasco grave que para lluvia).
            3. Transformamos la severidad seleccionada (0–100 %) en un factor entre 0 y 1.
            4. El **incremento porcentual** de duración es `factor_tipo * factor_severidad`.
            5. Calculamos:
               - `dur_afectada = dur_base * (1 + incremento_pct)`
               - `coste_extra_min = dur_afectada - dur_base`
            6. Suponemos una **ruta alternativa**:
               - Distancia = `dist_base * {GRAPH_ALT_DISTANCE_FACTOR:.2f}` (algo más larga).
               - Duración = `dur_afectada * {GRAPH_ALT_DURATION_FACTOR:.2f}` (ligeramente más fluida).

            Además, estimamos un **coste económico** muy sencillo:

            - Coste de combustible ≈ `distancia_km * coste_combustible_eur_km`
            - Coste de retraso ≈ `minutos_retraso * coste_retraso_eur_min`

            Los valores por defecto para estos costes están definidos al inicio
            de este fichero en las constantes:

            - `GRAPH_FUEL_COST_EUR_PER_KM` (actualmente `{GRAPH_FUEL_COST_EUR_PER_KM:.2f} €/km`)
            - `GRAPH_DELAY_COST_EUR_PER_MIN` (actualmente `{GRAPH_DELAY_COST_EUR_PER_MIN:.2f} €/min`)

            Si eres desarrollador/a, puedes ajustar estas constantes directamente
            en `presentacion_sentinel360_app.py` para cambiar el modelo base.
            """
    )

    # Intentamos usar las rutas reales si existen; si no, inventamos unas de ejemplo.
    # Si el usuario ha subido un CSV de rutas en la Fase I, lo priorizamos.
    routes_df_demo = st.session_state.get("routes_override_df")
    if routes_df_demo is None:
        _, _, routes_df_demo = load_sample_data()

    if routes_df_demo is not None and "route_id" in routes_df_demo.columns:
        rutas_disponibles = routes_df_demo["route_id"].astype(str).unique().tolist()
    else:
        rutas_disponibles = ["MAD-BCN-A1", "MAD-ZAR-A2", "BCN-ZAR-AP2"]

    col_ruta, col_incidencia = st.columns(2)
    with col_ruta:
        ruta_sel = st.selectbox(
            "Ruta principal afectada",
            options=rutas_disponibles,
            help="Ruta cuya caída queremos analizar (p. ej. carretera principal entre dos hubs).",
        )

    with col_incidencia:
        tipo_incidencia = st.selectbox(
            "Tipo de incidencia",
            options=["Sin incidencia", "Nieve", "Lluvia intensa", "Atasco grave", "Obras"],
        )

    severidad = st.slider(
        "Severidad de la incidencia",
        min_value=0,
        max_value=100,
        value=40,
        step=10,
        help="0 = sin efecto, 100 = impacto máximo (carretera prácticamente inservible).",
    )

    # Modelo simplificado de impacto: factor multiplicador sobre la duración base
    factores_base = {
        "Sin incidencia": 0.0,
        "Lluvia intensa": 0.2,
        "Nieve": 0.4,
        "Atasco grave": 0.5,
        "Obras": 0.3,
    }
    factor_tipo = factores_base.get(tipo_incidencia, 0.0)
    factor_severidad = severidad / 100.0

    # Supongamos una ruta base de 300 km y 240 minutos (4h) si no tenemos dato real
    dur_base_min = GRAPH_BASE_DURATION_MIN
    dist_base_km = GRAPH_BASE_DISTANCE_KM

    if routes_df_demo is not None and {"distance_km", "avg_duration_min"}.issubset(routes_df_demo.columns):
        # Tomamos valores medios como referencia general de la red
        dur_base_min = float(routes_df_demo["avg_duration_min"].mean())
        dist_base_km = float(routes_df_demo["distance_km"].mean())

    incremento_pct = factor_tipo * factor_severidad  # p. ej. 0.4 * 0.7 = +28%
    dur_afectada = dur_base_min * (1.0 + incremento_pct)
    coste_extra_min = dur_afectada - dur_base_min

    # Supongamos que la ruta alternativa es un 10% más larga en distancia
    dist_alt_km = dist_base_km * GRAPH_ALT_DISTANCE_FACTOR
    dur_alt_min = dur_afectada * GRAPH_ALT_DURATION_FACTOR  # algo más fluida

    st.markdown("#### Parámetros económicos de la simulación")
    col_coste1, col_coste2 = st.columns(2)
    with col_coste1:
        coste_combustible = st.number_input(
            "Coste combustible (€/km)",
            min_value=0.0,
            value=float(st.session_state["graph_sim_params"]["fuel_cost"]),
            step=0.1,
            key="fuel_cost_input",
        )
    with col_coste2:
        coste_retraso = st.number_input(
            "Coste de retraso (€/min)",
            min_value=0.0,
            value=float(st.session_state["graph_sim_params"]["delay_cost"]),
            step=0.5,
            key="delay_cost_input",
        )

    col_btn_ok, col_btn_cancel = st.columns(2)
    with col_btn_ok:
        if st.button("✔ ACEPTAR cambios de costes", key="btn_accept_econ"):
            st.session_state["graph_sim_params"]["fuel_cost"] = float(
                st.session_state.get("fuel_cost_input", coste_combustible)
            )
            st.session_state["graph_sim_params"]["delay_cost"] = float(
                st.session_state.get("delay_cost_input", coste_retraso)
            )
            st.success("Parámetros económicos actualizados para la simulación.")
    with col_btn_cancel:
        if st.button("✖ CANCELAR cambios", key="btn_cancel_econ"):
            # Restauramos los valores almacenados y forzamos que los inputs se sincronicen en el siguiente render
            st.session_state["fuel_cost_input"] = st.session_state["graph_sim_params"]["fuel_cost"]
            st.session_state["delay_cost_input"] = st.session_state["graph_sim_params"]["delay_cost"]
            st.info("Se han descartado los cambios y se han restaurado los valores anteriores.")

    # Usamos SIEMPRE los valores confirmados (en session_state) para los cálculos
    coste_combustible = float(st.session_state["graph_sim_params"]["fuel_cost"])
    coste_retraso = float(st.session_state["graph_sim_params"]["delay_cost"])

    coste_base_comb = dist_base_km * coste_combustible
    coste_alt_comb = dist_alt_km * coste_combustible
    coste_retraso_eur = coste_extra_min * coste_retraso

    st.markdown(
        f"""
        - **Ruta seleccionada**: `{ruta_sel}`  
        - **Duración base estimada**: `{dur_base_min:.1f}` minutos  
        - **Duración con incidencia ({tipo_incidencia}, severidad {severidad}%)**: `{dur_afectada:.1f}` minutos  
        - **Coste añadido estimado de retraso**: `+{coste_extra_min:.1f}` min (`≈ {coste_retraso_eur:.1f} €` por envío)  
        - **Coste combustible ruta base**: `{coste_base_comb:.1f} €`  
        - **Coste combustible ruta alternativa**: `{coste_alt_comb:.1f} €`
        """
    )

    df_escenarios = pd.DataFrame(
        {
            "escenario": ["Ruta base", "Ruta afectada", "Ruta alternativa"],
            "duracion_min": [dur_base_min, dur_afectada, dur_alt_min],
        }
    ).set_index("escenario")

    st.markdown("**Comparativa de duración por escenario (minutos)**")
    st.bar_chart(df_escenarios, height=260)

    # Si tenemos maestro de rutas, mostramos las posibles alternativas entre almacenes
    if routes_df_demo is not None and {
        "from_warehouse_id",
        "to_warehouse_id",
        "distance_km",
        "avg_duration_min",
    }.issubset(routes_df_demo.columns):
        st.markdown("---")
        st.subheader("Rutas alternativas entre almacenes (a partir de `routes.csv`)")

        # Limpieza previa: nos quedamos solo con filas de rutas que tengan ids válidos
        # (no NaN ni textos libres como "Ciudad Real", etc.) y se parezcan a códigos de almacén.
        rutas_validas = routes_df_demo.dropna(
            subset=["from_warehouse_id", "to_warehouse_id"]
        ).copy()
        rutas_validas["from_warehouse_id"] = rutas_validas["from_warehouse_id"].astype(str)
        rutas_validas["to_warehouse_id"] = rutas_validas["to_warehouse_id"].astype(str)
        rutas_validas = rutas_validas[
            rutas_validas["from_warehouse_id"].str.startswith("WH-")
            & rutas_validas["to_warehouse_id"].str.startswith("WH-")
        ]

        # Construimos etiquetas descriptivas para los warehouses (id + nombre + ciudad)
        # para que el usuario vea "Ciudad Real – WH-CIUD-CAP" en lugar de solo el código.
        _, wh_df_map, _ = load_sample_data()
        wh_df_override = st.session_state.get("warehouses_override_df")
        if wh_df_override is not None:
            wh_df_map = wh_df_override

        origenes_ids = sorted(
            rutas_validas["from_warehouse_id"].astype(str).unique().tolist()
        )
        destinos_ids = sorted(
            rutas_validas["to_warehouse_id"].astype(str).unique().tolist()
        )

        def build_labels(ids: list[str]) -> tuple[list[str], dict[str, str]]:
            id_to_label: dict[str, str] = {}
            for wid in ids:
                if wh_df_map is not None and "warehouse_id" in wh_df_map.columns:
                    row = wh_df_map[wh_df_map["warehouse_id"].astype(str) == wid].head(1)
                    if not row.empty:
                        name = str(row.iloc[0].get("name", "") or "")
                        city = str(row.iloc[0].get("city", "") or "")
                        parts = []
                        if city:
                            parts.append(city)
                        if name:
                            parts.append(name)
                        parts.append(f"[{wid}]")
                        label = " – ".join(parts)
                        id_to_label[wid] = label
                        continue
                # Fallback: solo el id
                id_to_label[wid] = wid
            labels = [id_to_label[wid] for wid in ids]
            return labels, id_to_label

        origenes_labels, origenes_map = build_labels(origenes_ids)
        destinos_labels, destinos_map = build_labels(destinos_ids)

        col_o, col_d = st.columns(2)
        with col_o:
            origen_label = st.selectbox(
                "Almacén de origen",
                options=origenes_labels,
                key="sim_origen",
            )
            # Recuperamos el id interno a partir de la etiqueta elegida
            wh_origen = next(
                wid for wid, label in origenes_map.items() if label == origen_label
            )
        with col_d:
            destino_label = st.selectbox(
                "Almacén de destino",
                options=destinos_labels,
                key="sim_destino",
            )
            wh_destino = next(
                wid for wid, label in destinos_map.items() if label == destino_label
            )

        # Rutas directas entre ese origen/destino
        rutas_directas = rutas_validas[
            (rutas_validas["from_warehouse_id"] == wh_origen)
            & (rutas_validas["to_warehouse_id"] == wh_destino)
        ]

        # Prepararemos una lista de aristas seleccionadas (origen, destino) para resaltar en el mapa:
        selected_path_edges: list[tuple[str, str]] = []

        # Construimos también mapas id -> etiqueta descriptiva para warehouses y rutas
        wh_label_cache: dict[str, str] = {}
        if wh_df_map is not None and "warehouse_id" in wh_df_map.columns:
            for _, r in wh_df_map.iterrows():
                wid = str(r.get("warehouse_id", ""))
                if not wid:
                    continue
                name = str(r.get("name", "") or "")
                city = str(r.get("city", "") or "")
                parts = []
                if city:
                    parts.append(city)
                if name:
                    parts.append(name)
                parts.append(f"[{wid}]")
                wh_label_cache[wid] = " – ".join(parts)

        def wh_desc(wid: str) -> str:
            return wh_label_cache.get(wid, wid)

        def route_desc(row: pd.Series) -> str:
            rid = str(row.get("route_id", ""))
            u = str(row.get("from_warehouse_id", ""))
            v = str(row.get("to_warehouse_id", ""))
            return f"{rid} : {wh_desc(u)} → {wh_desc(v)}"

        if not rutas_directas.empty:
            st.markdown("**Rutas directas disponibles entre estos almacenes**")
            df_dir = rutas_directas.copy()
            df_dir["from_desc"] = df_dir["from_warehouse_id"].map(wh_desc)
            df_dir["to_desc"] = df_dir["to_warehouse_id"].map(wh_desc)
            df_dir["route_desc"] = df_dir.apply(route_desc, axis=1)
            st.dataframe(
                df_dir[
                    [
                        "route_id",
                        "route_desc",
                        "from_warehouse_id",
                        "from_desc",
                        "to_warehouse_id",
                        "to_desc",
                        "distance_km",
                        "avg_duration_min",
                    ]
                ]
            )
            selected_path_edges.append((wh_origen, wh_destino))
        else:
            # No hay ruta directa: buscamos una ruta multi-tramo (camino más corto por distancia_km)
            st.info(
                "No hay una ruta directa en el maestro entre estos almacenes. "
                "Buscando una ruta multi-tramo alternativa a través de otros hubs…"
            )

            # Construimos un grafo no dirigido con peso = distance_km
            adj: dict[str, list[tuple[str, float, str]]] = {}
            for _, r in rutas_validas.iterrows():
                u = r["from_warehouse_id"]
                v = r["to_warehouse_id"]
                d_km = float(r.get("distance_km", 1.0) or 1.0)
                rid = str(r.get("route_id", ""))
                adj.setdefault(u, []).append((v, d_km, rid))
                adj.setdefault(v, []).append((u, d_km, rid))

            def shortest_path(start: str, goal: str) -> list[tuple[str, str, str, float]]:
                if start not in adj or goal not in adj:
                    return []
                dist: dict[str, float] = {start: 0.0}
                prev: dict[str, tuple[str, str]] = {}  # nodo -> (previo, route_id)
                heap: list[tuple[float, str]] = [(0.0, start)]

                while heap:
                    cur_d, u = heapq.heappop(heap)
                    if u == goal:
                        break
                    if cur_d > dist.get(u, float("inf")):
                        continue
                    for v, w, rid in adj.get(u, []):
                        nd = cur_d + w
                        if nd < dist.get(v, float("inf")):
                            dist[v] = nd
                            prev[v] = (u, rid)
                            heapq.heappush(heap, (nd, v))

                if goal not in dist:
                    return []

                # Reconstruimos el camino desde goal hacia start
                path_nodes: list[tuple[str, str]] = []
                node = goal
                while node != start:
                    prev_node, rid = prev[node]
                    path_nodes.append((prev_node, node))
                    node = prev_node
                path_nodes.reverse()

                # Enriquecemos cada tramo con route_id y distance_km
                detalles: list[tuple[str, str, str, float]] = []
                for u, v in path_nodes:
                    match = rutas_validas[
                        (rutas_validas["from_warehouse_id"] == u)
                        & (rutas_validas["to_warehouse_id"] == v)
                    ].head(1)
                    if match.empty:
                        match = rutas_validas[
                            (rutas_validas["from_warehouse_id"] == v)
                            & (rutas_validas["to_warehouse_id"] == u)
                        ].head(1)
                    if not match.empty:
                        rid = str(match.iloc[0].get("route_id", ""))
                        d_km = float(match.iloc[0].get("distance_km", 1.0) or 1.0)
                    else:
                        rid = ""
                        d_km = 0.0
                    detalles.append((u, v, rid, d_km))
                return detalles

            tramos = shortest_path(wh_origen, wh_destino)
            if tramos:
                st.markdown("**Ruta multi-tramo sugerida (camino más corto por distancia total)**")
                df_tramos = pd.DataFrame(
                    tramos, columns=["from_warehouse_id", "to_warehouse_id", "route_id", "distance_km"]
                )
                df_tramos["from_desc"] = df_tramos["from_warehouse_id"].map(wh_desc)
                df_tramos["to_desc"] = df_tramos["to_warehouse_id"].map(wh_desc)
                df_tramos["route_desc"] = df_tramos.apply(route_desc, axis=1)
                df_tramos["distancia_acumulada_km"] = df_tramos["distance_km"].cumsum()
                st.dataframe(
                    df_tramos[
                        [
                            "route_id",
                            "route_desc",
                            "from_warehouse_id",
                            "from_desc",
                            "to_warehouse_id",
                            "to_desc",
                            "distance_km",
                            "distancia_acumulada_km",
                        ]
                    ]
                )
                selected_path_edges = [(u, v) for (u, v, _, _) in tramos]
            else:
                st.info(
                    "Tampoco se ha encontrado un camino multi-tramo entre estos almacenes "
                    "con las rutas disponibles en `routes.csv`."
                )

        # Rutas alternativas que salen del mismo origen hacia otros almacenes
        rutas_alt = rutas_validas[
            (rutas_validas["from_warehouse_id"] == wh_origen)
            & (rutas_validas["to_warehouse_id"] != wh_destino)
        ]
        if not rutas_alt.empty:
            st.markdown(
                f"**Otras rutas alternativas que salen de `{wh_origen}` hacia almacenes intermedios**"
            )
            df_alt = rutas_alt.copy()
            df_alt["from_desc"] = df_alt["from_warehouse_id"].map(wh_desc)
            df_alt["to_desc"] = df_alt["to_warehouse_id"].map(wh_desc)
            df_alt["route_desc"] = df_alt.apply(route_desc, axis=1)
            st.dataframe(
                df_alt[
                    [
                        "route_id",
                        "route_desc",
                        "from_warehouse_id",
                        "from_desc",
                        "to_warehouse_id",
                        "to_desc",
                        "distance_km",
                        "avg_duration_min",
                    ]
                ]
            )

        # Mapa de España con rutas trazadas (usa siempre la versión actual de routes_df_demo)
        st.markdown(
            "**Mapa de España con las rutas del maestro actual**  "
            "_(la ruta seleccionada se resalta; el resto se muestra difuminada)_"
        )

        # Necesitamos las coordenadas de los almacenes para dibujar líneas
        gps_df, wh_df_map, _ = load_sample_data()
        if wh_df_map is not None and {"warehouse_id", "lat", "lon"}.issubset(wh_df_map.columns):
            # Incluimos también nombre y ciudad para poder mostrar descripciones en el mapa
            base_cols = ["warehouse_id", "lat", "lon"]
            extra_cols = [c for c in ["name", "city"] if c in wh_df_map.columns]
            wh_coords = wh_df_map[base_cols + extra_cols].dropna(subset=["lat", "lon"])
            merged_from = rutas_validas.merge(
                wh_coords,
                left_on="from_warehouse_id",
                right_on="warehouse_id",
                how="left",
                suffixes=("", "_from"),
            )
            merged_full = merged_from.merge(
                wh_coords,
                left_on="to_warehouse_id",
                right_on="warehouse_id",
                how="left",
                suffixes=("_from", "_to"),
            )

            lines_df = merged_full[
                ["route_id", "from_warehouse_id", "to_warehouse_id", "lat_from", "lon_from", "lat_to", "lon_to"]
            ].dropna(subset=["lat_from", "lon_from", "lat_to", "lon_to"])

            if not lines_df.empty:
                # Mapa centrado en España usando OpenStreetMap (sin necesidad de API key)
                m = folium.Map(location=[40.0, -3.7], zoom_start=5, tiles="OpenStreetMap")

                # Capa opcional del IGN (WMS) para dar más contexto geográfico
                folium.raster_layers.WmsTileLayer(
                    url="https://www.ign.es/wms-inspire/mapa-raster",
                    name="IGN Mapa Raster",
                    fmt="image/png",
                    transparent=True,
                    version="1.3.0",
                    layers="mtn_rasterizado",
                    attr="© Instituto Geográfico Nacional de España",
                    control=True,
                ).add_to(m)

                # Marcadores de almacenes, con descripción en tooltip
                for _, row in wh_coords.iterrows():
                    desc_parts = [str(row["warehouse_id"])]
                    if "name" in row and not pd.isna(row["name"]):
                        desc_parts.append(str(row["name"]))
                    if "city" in row and not pd.isna(row["city"]):
                        desc_parts.append(f"({row['city']})")
                    tooltip = " - ".join(desc_parts)

                    folium.CircleMarker(
                        location=[row["lat"], row["lon"]],
                        radius=5,
                        color="#00C846",
                        fill=True,
                        fill_color="#00C846",
                        fill_opacity=0.9,
                        tooltip=tooltip,
                    ).add_to(m)

                # Conjunto de aristas seleccionadas (para resaltado en el mapa)
                selected_edges_set = {
                    (u, v) for (u, v) in selected_path_edges
                } | {(v, u) for (u, v) in selected_path_edges}

                # Líneas de rutas, con tooltip descriptivo.
                # Los tramos de la ruta seleccionada se resaltan; el resto se dibuja difuminado.
                for _, row in lines_df.iterrows():
                    edge = (row["from_warehouse_id"], row["to_warehouse_id"])
                    is_selected = edge in selected_edges_set
                    route_label = f"{row['route_id']} : {row['from_warehouse_id']} → {row['to_warehouse_id']}"
                    color = "#FF0000" if is_selected else "#0080FF"
                    weight = 5 if is_selected else 2
                    opacity = 0.9 if is_selected else 0.25

                    folium.PolyLine(
                        locations=[
                            [row["lat_from"], row["lon_from"]],
                            [row["lat_to"], row["lon_to"]],
                        ],
                        color=color,
                        weight=weight,
                        opacity=opacity,
                        tooltip=route_label,
                    ).add_to(m)

                folium.LayerControl().add_to(m)
                st_folium(m, width=900, height=500)
            else:
                st.info(
                    "No se han podido dibujar líneas porque faltan coordenadas lat/lon "
                    "para algunas rutas o almacenes."
                )
        else:
            st.info(
                "No se encuentra `warehouses.csv` con columnas `warehouse_id`, `lat`, `lon`, "
                "por lo que no es posible dibujar el mapa de rutas."
            )

    st.info(
        "En una versión completa, estos factores de impacto podrían aprenderse "
        "a partir del histórico de retrasos (Spark + MongoDB) y de eventos "
        "externos de tráfico/meteorología, en lugar de ser parámetros fijos."
    )

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 2 · Fase II – Limpieza y enriquecimiento",
            key="nav_3_to_2",
            on_click=navigate_to,
            args=("2 · Fase II – Limpieza y enriquecimiento",),
        )
    with cols[1]:
        st.button(
            "Ir a 4 · Fase III – Streaming + anomalías",
            key="nav_3_to_4",
            on_click=navigate_to,
            args=("4 · Fase III – Streaming + anomalías",),
        )


def page_fase_iii_streaming_anomalias():
    st.header("4 · Fase III – Streaming de retrasos y anomalías")
    render_top_nav("4 · Fase III – Streaming + anomalías")
    render_search_highlight(
        "en esta fase se ejecuta el **streaming de retrasos**, se calculan ventanas agregadas y se detectan **anomalías** con K-Means, guardando resultados en **MongoDB** e **Hive**."
    )
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase III – Minería de datos / explotación en tiempo casi real)**

        Desde aquí puedes lanzar:

        - `delays_windowed.py` (Spark Streaming): lee de Kafka (`raw-data` o ficheros), calcula retrasos
          por ventana y escribe en Hive + MongoDB, generando alertas al topic `alerts`.
        - `anomaly_detection.py` (batch): detecta anomalías sobre los agregados y escribe en MongoDB + Kafka.

        - **Entrada**:
          - Eventos de GPS ya normalizados (desde Kafka o desde ficheros en HDFS).
          - Agregados de retrasos generados por el propio streaming.
        - **Transformación**:
          - Cálculo de métricas de retrasos por ventana temporal.
          - Aplicación de modelos de ML (K-Means) para detectar comportamientos anómalos.
        - **Salida esperada**:
          - Tabla Hive `aggregated_delays`.
          - Colecciones MongoDB con agregados y anomalías.
          - Mensajes de alerta en el topic Kafka `alerts`.

        Esta etapa es la que conecta el *pipeline técnico* con los **casos de uso de monitorización
        y alertas** que luego se verán reflejados en los dashboards.
        """
    )

    # Documentación adicional para Fase III
    fase3_docs = [
        ("docs/FASE_III_STREAMING.md", "Fase III – Streaming y carga multicapa (`docs/FASE_III_STREAMING.md`)"),
    ]
    for rel_path, label in fase3_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    modo_stream = st.selectbox("Modo de entrada para `delays_windowed.py`", ["kafka", "file"])

    st.subheader("Comandos de esta fase")
    st.code(
        f"./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {modo_stream}\n"
        "./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py\n",
        language="bash",
    )
    yarn_up = is_yarn_resource_manager_up()
    force_local = st.checkbox(
        "Forzar modo local de Spark (streaming/anomalías)",
        value=not yarn_up,
        key="fase3_force_local",
    )
    fase3_resource_profile = st.selectbox(
        "Perfil de recursos Spark (Fase III)",
        options=list(SPARK_PROFILE_OPTIONS),
        index=0,
        key="fase3_resource_profile",
        help="Usa 'Seguro' si el equipo se reinicia durante streaming o detección de anomalías.",
    )
    fase3_spark_env = spark_resource_env_for_profile(fase3_resource_profile)
    force_local_fase3_effective = force_local or (fase3_resource_profile == SPARK_PROFILE_SEGURO)
    if fase3_resource_profile == SPARK_PROFILE_SEGURO and not force_local:
        st.info("Perfil seguro activo en Fase III: Spark se ejecutará en modo local automáticamente.")
    if not yarn_up:
        st.warning("YARN ResourceManager no responde en `hadoop:8032`. Se recomienda `--local`.")

    st.subheader("Monitorización en vivo (Spark UI / YARN / Kafka)")
    st.markdown(
        """
        Durante la ejecución de streaming puedes revisar:

        - **Spark UI**: progreso de jobs/stages y métricas de la consulta activa.
        - **YARN UI**: aplicaciones en ejecución, estado y logs de contenedores.
        - **Kafka topics**: presencia/configuración de `raw-data`, `filtered-data` y `alerts`.
        """
    )
    st.markdown(
        "\n".join(
            [
                "- [Spark UI (local)](http://localhost:4040)",
                "- [Spark UI (nodo hadoop)](http://hadoop:4040)",
                "- [YARN ResourceManager UI](http://hadoop:8088)",
            ]
        )
    )
    st.code(
        "kafka-topics.sh --bootstrap-server hadoop:9092 --list\n"
        "kafka-topics.sh --bootstrap-server hadoop:9092 --describe --topic raw-data\n"
        "kafka-topics.sh --bootstrap-server hadoop:9092 --describe --topic filtered-data\n"
        "kafka-topics.sh --bootstrap-server hadoop:9092 --describe --topic alerts\n",
        language="bash",
    )
    if st.button("Comprobar monitorización Spark/YARN/Kafka", key="fase3_live_monitor_check"):
        with st.spinner("Comprobando UIs, puertos y topics..."):
            monitor_cmd = (
                'echo "=== Puertos de monitorización ==="; '
                "ss -tln 2>/dev/null | awk '/:4040|:8088|:9092/ {print}'; "
                'echo ""; echo "=== Spark UI (localhost:4040) ==="; '
                "curl -sS --max-time 2 http://localhost:4040 2>/dev/null | sed -n '1,5p' || echo 'No accesible'; "
                'echo ""; echo "=== YARN UI (hadoop:8088) ==="; '
                "curl -sS --max-time 2 http://hadoop:8088/ws/v1/cluster/info 2>/dev/null | sed -n '1,20p' || echo 'No accesible'; "
                'echo ""; echo "=== Kafka topics (list) ==="; '
                "(kafka-topics.sh --bootstrap-server hadoop:9092 --list 2>/dev/null "
                "|| /usr/local/kafka/bin/kafka-topics.sh --bootstrap-server hadoop:9092 --list 2>/dev/null "
                "|| echo 'No se pudo ejecutar kafka-topics.sh') | sort; "
                'echo ""; echo "=== Kafka describe (raw-data, filtered-data, alerts) ==="; '
                "for t in raw-data filtered-data alerts; do "
                "echo \"-- $t --\"; "
                "(kafka-topics.sh --bootstrap-server hadoop:9092 --describe --topic \"$t\" 2>/dev/null "
                "|| /usr/local/kafka/bin/kafka-topics.sh --bootstrap-server hadoop:9092 --describe --topic \"$t\" 2>/dev/null "
                "|| echo 'No disponible'); "
                "done"
            )
            monitor_output = run_command(monitor_cmd)
        render_log_output(
            "Resultado monitorización en vivo (Fase III)",
            monitor_output,
            key="log_fase_iii_live_monitor",
            download_name="fase_iii_monitorizacion_vivo.log.txt",
        )

    if st.button("Lanzar streaming de retrasos"):
        with st.spinner("Lanzando Spark Streaming (delays_windowed.py)..."):
            output = run_command(
                spark_submit_cmd(
                    "spark/streaming/delays_windowed.py",
                    modo_stream,
                    force_local=force_local_fase3_effective,
                ),
                extra_env=fase3_spark_env,
            )
        st.subheader("Salida de delays_windowed.py")
        render_log_output(
            "Log de delays_windowed.py",
            output,
            key="log_fase_iii_streaming",
            download_name="fase_iii_streaming.log.txt",
        )

    if st.button("Lanzar detección de anomalías (batch)"):
        with st.spinner("Lanzando Spark ML (anomaly_detection.py)..."):
            output = run_command(
                spark_submit_cmd(
                    "spark/ml/anomaly_detection.py",
                    force_local=force_local_fase3_effective,
                ),
                extra_env=fase3_spark_env,
            )
        st.subheader("Salida de anomaly_detection.py")
        render_log_output(
            "Log de anomaly_detection.py",
            output,
            key="log_fase_iii_anomalias",
            download_name="fase_iii_anomalias.log.txt",
        )

    st.subheader("Cuadros reconstruidos con datos obtenidos (MongoDB)")
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        db = client[MONGO_DB]
        agg_docs = list(
            db[MONGO_AGGREGATED_COLLECTION]
            .find({}, {"_id": 0})
            .sort("window_start", -1)
            .limit(200)
        )
        anom_docs = list(
            db[MONGO_ANOMALIES_COLLECTION]
            .find({}, {"_id": 0})
            .sort("window_start", -1)
            .limit(200)
        )
        agg_df = pd.DataFrame(agg_docs)
        anom_df = pd.DataFrame(anom_docs)
        if not agg_df.empty:
            if "window_start" in agg_df.columns:
                agg_df["window_start"] = pd.to_datetime(agg_df["window_start"], errors="coerce", utc=True)
            st.markdown("**Agregados de retrasos (últimas ventanas)**")
            st.dataframe(agg_df.head(50), width="stretch")
        else:
            st.info("Sin agregados en MongoDB todavía.")

        if not anom_df.empty:
            if "window_start" in anom_df.columns:
                anom_df["window_start"] = pd.to_datetime(anom_df["window_start"], errors="coerce", utc=True)
            st.markdown("**Anomalías detectadas (últimas ventanas)**")
            st.dataframe(anom_df.head(50), width="stretch")
        else:
            st.info("Sin anomalías en MongoDB todavía.")
    except Exception as exc:  # pragma: no cover - UI interactiva
        st.warning(
            "No se ha podido reconstruir cuadros desde MongoDB en esta fase. "
            f"Detalle: {exc}"
        )

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 3 · Fase II – Grafos",
            key="nav_4_to_3",
            on_click=navigate_to,
            args=("3 · Fase II – Grafos",),
        )
    with cols[1]:
        st.button(
            "Ir a 5 · Entorno visual",
            key="nav_4_to_5",
            on_click=navigate_to,
            args=("5 · Entorno visual (Superset / Grafana / Airflow)",),
        )


def page_entorno_visual():
    st.header("5 · Entorno visual (Superset / Grafana / Airflow)")
    render_top_nav("5 · Entorno visual (Superset / Grafana / Airflow)")
    render_search_highlight(
        "aquí se documentan los **dashboards** en Superset/Grafana y la **orquestación con Airflow**, incluyendo los DAGs que automatizan el pipeline KDD."
    )

    img_candidates = [
        PROJECT_ROOT / "sentinel360v2.png",
        PROJECT_ROOT / "Sentinel360.png",
        PROJECT_ROOT.parent / "sentinel360v2.png",
    ]
    img_path = next((p for p in img_candidates if p.exists()), None)
    if img_path is not None:
        st.subheader("Arquitectura Sentinel360")
        st.image(
            str(img_path),
            caption="Arquitectura Sentinel360 – vista general",
        )
        if st.button(
            "Comenzar recorrido KDD desde esta arquitectura",
            key="hero_nav_5_to_0",
        ):
            navigate_to("0 · Arranque de servicios")

    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Presentación de resultados)** – última etapa del ciclo.

        Sentinel360 ya utiliza **Superset** y **Grafana** para los dashboards finales que consumen
        los datos generados en las fases anteriores.

        Esta pestaña sirve como “hub” con enlaces y recordatorio de los KPIs que se alimentan
        desde Spark y MongoDB hacia MariaDB (`sentinel360_analytics`).

        - **Entrada**:
          - Tablas y vistas en MariaDB y otras fuentes configuradas para Superset/Grafana.
        - **Transformación**:
          - Construcción de dashboards, gráficos de retrasos, tablas de anomalías y KPIs de negocio.
        - **Salida esperada**:
          - Cuadros de mando navegables por usuarios de negocio para tomar decisiones.

        Usa esta pestaña como transición entre el **pipeline de datos** y la **capa de presentación**
        que verá el usuario final.
        """
    )

    st.subheader("Orquestación con Airflow (vista ejecutiva)")
    st.markdown(
        """
        Además de lanzar scripts manualmente desde esta interfaz, Sentinel360 dispone de
        **DAGs de Airflow** que orquestan el pipeline de forma desasistida:

        - `sentinel360_infra_start` / `sentinel360_infra_stop`: levantan/paran el clúster (HDFS, Kafka, Mongo, MariaDB, NiFi, etc.).
        - `sentinel360_fase_I_ingesta`: prepara NiFi/Kafka, genera GPS sintético + OpenWeather y deja datos listos en raw.
        - `sentinel360_fase_II_preprocesamiento`: ejecuta limpieza, enriquecimiento y grafo de transporte (Spark + Hive).
        - `sentinel360_fase_III_batch` / `sentinel360_fase_III_streaming`: calculan agregados de retrasos, anomalías y KPIs.
        - `sentinel360_dashboards_levantar` / `sentinel360_dashboards_exportar`: levantan Superset/Grafana y exportan datos de Hive/Mongo a MariaDB para los cuadros de mando.

        De este modo, el **entorno visual** (Superset/Grafana) puede alimentarse automáticamente,
        sin que el usuario tenga que recordar el orden exacto de scripts.
        """
    )

    airflow_md = PROJECT_ROOT / "docs" / "AIRFLOW_DAGS.md"
    if airflow_md.exists():
        st.markdown("- **Detalle técnico de los DAGs de Airflow**: `docs/AIRFLOW_DAGS.md`")
        with st.expander("Ver descripción completa de los DAGs (`docs/AIRFLOW_DAGS.md`)"):
            st.markdown(airflow_md.read_text(encoding="utf-8"))

    st.markdown("**Evidencias descargables (reportes de ejecuciones Airflow)**")
    st.markdown(
        """
        Cuando un DAG termina, la última tarea `reporte_ejecucion` genera un fichero Markdown en:

        - `reports/airflow/<dag_id>/LATEST.md` (último reporte)
        - `reports/airflow/<dag_id>/<run_id>_*.md` (histórico)

        Esto sirve como **evidencia** para documentar que se han ejecutado las tareas paso a paso.
        """
    )
    reports_base = PROJECT_ROOT / "reports" / "airflow"
    if reports_base.exists():
        dag_dirs = sorted([p for p in reports_base.iterdir() if p.is_dir()], key=lambda p: p.name)
        if dag_dirs:
            dag_sel = st.selectbox(
                "Selecciona DAG para ver/descargar su último reporte",
                options=[p.name for p in dag_dirs],
                key="airflow_reports_dag_select",
            )
            latest = reports_base / dag_sel / "LATEST.md"
            if latest.exists():
                md_text = latest.read_text(encoding="utf-8", errors="ignore")
                with st.expander("Ver reporte (LATEST.md)"):
                    st.markdown(md_text)
                st.download_button(
                    label="Descargar reporte (Markdown)",
                    data=md_text.encode("utf-8"),
                    file_name=f"airflow_report_{dag_sel}_LATEST.md",
                    mime="text/markdown",
                )
            else:
                st.info("Aún no hay `LATEST.md` para este DAG. Ejecuta el DAG al menos una vez.")
        else:
            st.info("No hay subcarpetas de reportes todavía. Ejecuta algún DAG para generarlas.")
    else:
        st.info("Aún no existe `reports/airflow/`. Se creará automáticamente tras ejecutar un DAG.")

    if airflow_md.exists():
        st.markdown("**Ejemplo de DAG batch `sentinel360_fase_III_batch` (tareas principales):**")
        st.code(
            """with DAG(
    dag_id="sentinel360_fase_III_batch",
    default_args=DEFAULT_ARGS,
    schedule_interval=None,
    catchup=False,
) as dag:
    load_aggregated_delays = BashOperator(
        task_id="load_aggregated_delays",
        bash_command=spark_task("spark/streaming/write_to_hive_and_mongo.py"),
    )
    detect_anomalies_batch = BashOperator(
        task_id="detect_anomalies_batch",
        bash_command=spark_task("spark/ml/anomaly_detection.py"),
    )
    export_kpis_to_mariadb = BashOperator(
        task_id="export_kpis_to_mariadb",
        bash_command="python3 scripts/mongo_to_mariadb_kpi.py --source mongo",
    )

    load_aggregated_delays >> detect_anomalies_batch >> export_kpis_to_mariadb
""",
            language="python",
        )

        st.markdown("**Esquema de dependencias (simplificado):**")
        st.code(
            """sentinel360_infra_start
    → sentinel360_fase_I_ingesta
        → sentinel360_fase_II_preprocesamiento
            → sentinel360_fase_III_batch / sentinel360_fase_III_streaming
                → sentinel360_dashboards_exportar
                    → dashboards en Superset / Grafana
""",
            language="text",
        )

    st.subheader("Cómo levantar y solucionar fallos")
    st.markdown(
        "Guía rápida: **levantar** Superset y Grafana con Docker y **qué hacer cuando algo falla** "
        "(error 500 en Superset, driver MySQL, conexión a MariaDB, paneles sin datos en Grafana). "
        "Incluye los scripts `init_superset.sh`, `verificar_conexion_superset_mariadb.sh` y el flujo de datos para Grafana."
    )
    docs_dir = PROJECT_ROOT / "docs"
    levantar_doc = docs_dir / "DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md"
    if levantar_doc.exists():
        st.markdown("- **Levantar dashboards y solucionar fallos**: `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`")
        with st.expander("Ver `DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`"):
            st.markdown(levantar_doc.read_text(encoding="utf-8"))
    else:
        st.markdown("- **Levantar dashboards y solucionar fallos**: `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md` *(no encontrado)*")

    st.subheader("Documentación de dashboards")
    doc_files = [
        ("PRESENTACION_ENTORNO_VISUAL.md", "Presentación del entorno visual"),
        ("SUPERSET_DASHBOARDS.md", "Dashboards Superset"),
        ("GRAFANA_DASHBOARDS.md", "Dashboards Grafana"),
    ]
    for filename, desc in doc_files:
        doc_path = docs_dir / filename
        if doc_path.exists():
            st.markdown(f"- **{desc}**: `docs/{filename}`")
            with st.expander(f"Ver `{filename}`"):
                st.markdown(doc_path.read_text(encoding="utf-8"))
        else:
            st.markdown(f"- **{desc}**: `docs/{filename}` *(no encontrado)*")

    st.info(
        "Para la demo: `cd docker && docker compose up -d mariadb superset grafana`. "
        "Si Superset da 500, ejecuta `./scripts/init_superset.sh`. "
        "Detalle completo en `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`. "
        "Para orquestar todo el pipeline (servicios, ingesta, Spark, dashboards) desde Airflow, ver la pestaña **0 · Arranque de servicios** → «Ejecutar todo desde Airflow» y `docs/AIRFLOW_DAGS.md`."
    )

    st.subheader("Material de presentación")
    pptx_candidates = [
        PROJECT_ROOT / "Sentinel360_Proactive_Logistics_Intelligence.pptx",
        PROJECT_ROOT.parent / "Sentinel360_Proactive_Logistics_Intelligence.pptx",
    ]
    pptx_path = next((p for p in pptx_candidates if p.exists()), None)
    if pptx_path is not None:
        try:
            pptx_bytes = pptx_path.read_bytes()
            st.download_button(
                label="Descargar presentación Sentinel360 (PPTX)",
                data=pptx_bytes,
                file_name=pptx_path.name,
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"No se ha podido preparar la descarga de la presentación: {exc}")
    else:
        st.info(
            "No se ha encontrado `Sentinel360_Proactive_Logistics_Intelligence.pptx` "
            "en el proyecto ni en el directorio padre."
        )

    pdf_candidates = [
        PROJECT_ROOT / "Sentinel360_Proactive_Logistics_Intelligence.pdf",
        PROJECT_ROOT.parent / "Sentinel360_Proactive_Logistics_Intelligence.pdf",
    ]
    pdf_path = next((p for p in pdf_candidates if p.exists()), None)
    if pdf_path is not None:
        st.markdown("#### Descargar versión PDF de la presentación")
        try:
            pdf_bytes = pdf_path.read_bytes()
            st.download_button(
                label="Descargar presentación Sentinel360 (PDF)",
                data=pdf_bytes,
                file_name=pdf_path.name,
                mime="application/pdf",
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"No se ha podido preparar la descarga en PDF: {exc}")


def page_dashboard_kpis():
    st.header("6 · Dashboard (Control Tower – operación diaria)")
    render_top_nav("6 · Dashboard (Retrasos / Anomalías)")
    render_search_highlight(
        "este es el **cuadro de mando operativo** (Control Tower) para monitorizar retrasos, anomalías e incidencias en tiempo casi real."
    )
    st.markdown(
        """
        Esta pestaña está pensada para **usuarios finales** (no técnicos):

        - Permite explorar los **retrasos agregados** por almacén y ventana de tiempo.
        - Muestra las **anomalías** detectadas por el modelo K-Means.

        Los datos proceden de MongoDB:

        - `transport.aggregated_delays` (ventanas de 15 min con `avg_delay_min` y `vehicle_count`).
        - `transport.anomalies` (ventanas marcadas como anómalas por el modelo).
        """
    )

    # Consultas equivalentes en Hive (histórico) para que el usuario final (y el desarrollador)
    # puedan copiar/pegar y auditar datos fuera del dashboard.
    with st.expander("Ver consultas equivalentes en Hive (histórico, copiable a terminal)"):
        st.markdown("**beeline (ejemplo de conexión)**")
        st.code(
            """beeline -u "jdbc:hive2://<HOST_HIVE>:10000/transport" -n <USUARIO>""",
            language="bash",
        )

        st.markdown("**Histórico: retrasos por ventana (transport.aggregated_delays)**")
        st.code(
            """USE transport;

SELECT
  window_start,
  window_end,
  warehouse_id,
  avg_delay_min,
  vehicle_count
FROM aggregated_delays
ORDER BY window_start, warehouse_id
LIMIT 200;""",
            language="sql",
        )

        st.markdown("**Histórico por almacén y rango de fechas (ejemplo)**")
        st.code(
            """USE transport;

SELECT
  window_start,
  avg_delay_min,
  vehicle_count
FROM aggregated_delays
WHERE warehouse_id = 'WH-MAD-CAP'
  AND window_start >= '2025-05-01 00:00:00'
  AND window_start <  '2025-06-01 00:00:00'
ORDER BY window_start;""",
            language="sql",
        )

        st.markdown("**Informe: Top 5 almacenes por retraso medio (histórico)**")
        st.code(
            """USE transport;

SELECT
  warehouse_id,
  AVG(avg_delay_min) AS retraso_medio_min,
  SUM(vehicle_count) AS vehiculos_totales
FROM aggregated_delays
GROUP BY warehouse_id
ORDER BY retraso_medio_min DESC
LIMIT 5;""",
            language="sql",
        )

        st.markdown("**Informe: ventanas críticas por umbral (ejemplo 30 min)**")
        st.code(
            """USE transport;

SELECT
  window_start,
  window_end,
  warehouse_id,
  avg_delay_min,
  vehicle_count
FROM aggregated_delays
WHERE avg_delay_min > 30
ORDER BY avg_delay_min DESC
LIMIT 200;""",
            language="sql",
        )

    st.markdown("### Filtros globales")
    colf1, colf2, colf3, colf4 = st.columns([1.2, 1.2, 1, 1])
    with colf1:
        time_scope = st.selectbox(
            "Ventana temporal",
            options=["Últimas 2h", "Últimas 6h", "Últimas 24h", "Todo (según límite)"],
            index=1,
            key="ct_time_scope",
        )
    with colf2:
        min_sev = st.slider("Severidad mínima (min retraso)", 0, 120, 20, 5, key="ct_min_sev")
    with colf3:
        max_rows = st.slider("Máx. filas (operación)", min_value=50, max_value=1000, value=200, step=50, key="ct_max_rows")
    with colf4:
        st.button(
            "Ir a Incidencias →",
            key="ct_nav_incidents",
            on_click=navigate_to,
            args=("6.1 · Incidencias y decisiones",),
        )

    st.markdown("---")

    # Inicializamos dataframes como None para poder reutilizarlos en la
    # sección de acciones administrativas (modo real o modo demo).
    agg_df: pd.DataFrame | None = None
    anom_df: pd.DataFrame | None = None

    try:
        client = get_mongo_client()
        client.admin.command("ping")
        db = client[MONGO_DB]
    except Exception as exc:  # pragma: no cover
        st.error(
            "No se ha podido conectar a MongoDB. "
            "Para usar este dashboard necesitas MongoDB levantado y accesible."
        )
        st.markdown(f"**URI configurada**: `{MONGO_URI}`")
        st.markdown("Arranque rápido (si tienes Docker):")
        st.code("docker run -d --name mongo -p 27017:27017 mongo:7", language="bash")
        st.text(f"Detalle del error: {exc}")

        st.markdown("---")
        st.markdown(
            """
            ### Modo demo (sin MongoDB)

            A continuación se muestra un **ejemplo realista** de cómo se vería
            este dashboard en producción, con datos de retrasos y anomalías ya cargados.
            """
        )

        # Ejemplos de consultas equivalentes, aunque estemos sin conexión real
        with st.expander("Ver ejemplo de consulta sobre MongoDB (aggregated_delays)"):
            st.markdown("**Python (PyMongo)**")
            st.code(
                f"""from pymongo import MongoClient

client = MongoClient("{MONGO_URI}")
db = client["{MONGO_DB}"]
coll = db["{MONGO_AGGREGATED_COLLECTION}"]

docs = list(
    coll.find({{}}, {{"_id": 0}})
        .sort("window_start", 1)
        .limit(200)
)
""",
                language="python",
            )
            st.markdown("**mongosh**")
            st.code(
                f"""mongo "{MONGO_URI}" --eval '
db.getSiblingDB("{MONGO_DB}").{MONGO_AGGREGATED_COLLECTION}.find(
  {{}},
  {{ _id: 0 }}
).sort({{ window_start: 1 }}).limit(200)
'""",
                language="bash",
            )

        with st.expander("Ver ejemplo de consulta sobre MongoDB (anomalies)"):
            st.markdown("**Python (PyMongo)**")
            st.code(
                f"""from pymongo import MongoClient

client = MongoClient("{MONGO_URI}")
db = client["{MONGO_DB}"]
coll = db["{MONGO_ANOMALIES_COLLECTION}"]

docs = list(
    coll.find({{"anomaly_flag": True}}, {{"_id": 0}})
        .sort("window_start", 1)
        .limit(200)
)
""",
                language="python",
            )
            st.markdown("**mongosh**")
            st.code(
                f"""mongo "{MONGO_URI}" --eval '
db.getSiblingDB("{MONGO_DB}").{MONGO_ANOMALIES_COLLECTION}.find(
  {{ anomaly_flag: true }},
  {{ _id: 0 }}
).sort({{ window_start: 1 }}).limit(200)
'""",
                language="bash",
            )

        # Datos de ejemplo para ilustrar el comportamiento
        agg_demo = [
            {
                "warehouse_id": "WH-MAD-01",
                "window_start": "2025-05-01T08:00:00",
                "avg_delay_min": 12.5,
                "vehicle_count": 34,
            },
            {
                "warehouse_id": "WH-MAD-01",
                "window_start": "2025-05-01T08:15:00",
                "avg_delay_min": 28.0,
                "vehicle_count": 27,
            },
            {
                "warehouse_id": "WH-BCN-02",
                "window_start": "2025-05-01T08:00:00",
                "avg_delay_min": 5.0,
                "vehicle_count": 19,
            },
            {
                "warehouse_id": "WH-BCN-02",
                "window_start": "2025-05-01T08:15:00",
                "avg_delay_min": 42.0,
                "vehicle_count": 22,
            },
        ]
        anom_demo = [
            {
                "warehouse_id": "WH-BCN-02",
                "window_start": "2025-05-01T08:15:00",
                "avg_delay_min": 42.0,
                "vehicle_count": 22,
                "cluster": 3,
                "anomaly_flag": True,
                "reason": "Retraso muy superior al histórico para esta franja",
            }
        ]

        agg_df = pd.DataFrame(agg_demo)
        agg_df["window_start"] = pd.to_datetime(agg_df["window_start"])
        anom_df = pd.DataFrame(anom_demo)
        anom_df["window_start"] = pd.to_datetime(anom_df["window_start"])

        st.subheader("Retrasos agregados por almacén (ejemplo)")
        st.dataframe(agg_df)
        st.line_chart(
            agg_df.set_index("window_start")[["avg_delay_min"]].sort_index(),
            height=250,
        )

        st.subheader("Ventanas marcadas como anómalas (ejemplo)")
        st.dataframe(anom_df)

        _ensure_demo_incidents_from_anomalies(anom_df)
        incidents_demo = get_store().get("incidents", [])
        incidents_filtered_demo = [
            x for x in incidents_demo
            if float(x.get("severity", 0) or 0) >= float(st.session_state.get("ct_min_sev", 0))
        ]

        st.markdown("---")
        st.subheader("Mapa operativo y panel de alertas (demo)")
        map_col_d, alert_col_d = st.columns([1.5, 1])
        with map_col_d:
            ventanas_d = sorted(agg_df["window_start"].dt.to_pydatetime())
            if ventanas_d:
                ventana_sel_d = st.selectbox(
                    "Ventana 15 min",
                    options=ventanas_d,
                    format_func=lambda dt: dt.strftime("%Y-%m-%d %H:%M"),
                    key="ct_map_ventana_demo",
                )
                sel_mask_d = agg_df["window_start"] == ventana_sel_d
                agg_win_d = agg_df[sel_mask_d].copy()
                if not agg_win_d.empty:
                    _, wh_df_map_d, _ = load_sample_data()
                    if st.session_state.get("warehouses_override_df") is not None:
                        wh_df_map_d = st.session_state["warehouses_override_df"]
                    if wh_df_map_d is not None and {"warehouse_id", "lat", "lon"}.issubset(wh_df_map_d.columns):
                        merged_d = agg_win_d.merge(
                            wh_df_map_d[["warehouse_id", "lat", "lon"]],
                            on="warehouse_id",
                            how="left",
                        ).dropna(subset=["lat", "lon"])
                        if not merged_d.empty:
                            m_d = folium.Map(location=[40.0, -3.7], zoom_start=5, tiles="OpenStreetMap")
                            for _, row in merged_d.iterrows():
                                tooltip_d = f"Almacén: {row['warehouse_id']}\nRetraso: {row.get('avg_delay_min', 'N/A')} min"
                                folium.CircleMarker(
                                    location=[row["lat"], row["lon"]],
                                    radius=6,
                                    color="#FF8800" if row.get("avg_delay_min", 0) > 20 else "#00C846",
                                    fill=True,
                                    fill_opacity=0.9,
                                    tooltip=tooltip_d,
                                ).add_to(m_d)
                            st_folium(m_d, width=None, height=420)
            else:
                st.info("Sin ventanas en el ejemplo.")
        with alert_col_d:
            st.markdown("**Alertas activas (demo)**")
            if incidents_filtered_demo:
                for inc in incidents_filtered_demo[:15]:
                    st.caption(f"`{inc.get('incident_id')}` · {inc.get('warehouse_id')} · **{inc.get('asignado_a') or '—'}**")
                sel_id_d = st.selectbox("Abrir", [str(x.get("incident_id")) for x in incidents_filtered_demo], key="ct_incident_select_demo")
                op_name_d = st.text_input("Operador", value="admin", key="ct_operator_name_demo")
                if st.button("Ver detalle →", key="ct_open_incident_demo"):
                    st.session_state["selected_incident_id"] = sel_id_d
                    navigate_to("6.1 · Incidencias y decisiones")
                if st.button("Asignar a mí", key="ct_assign_me_demo"):
                    t = next((x for x in incidents_filtered_demo if str(x.get("incident_id")) == sel_id_d), None)
                    if t:
                        t["asignado_a"] = op_name_d or "admin"
                        t["updated_at"] = _now_iso()
                        upsert_incident(db=None, incident=t)
                    st.success("Asignado.")
            else:
                st.info("No hay alertas en demo.")

        render_admin_actions(agg_df, anom_df)
        return

    st.subheader("KPIs y situación operativa")
    agg_coll = db[MONGO_AGGREGATED_COLLECTION]

    # Obtener lista de almacenes disponibles (warehouse_id)
    try:
        warehouse_ids = sorted(
            {
                d.get("warehouse_id")
                for d in agg_coll.find({}, {"warehouse_id": 1, "_id": 0}).limit(500)
                if d.get("warehouse_id")
            }
        )
    except Exception as exc:  # pragma: no cover
        st.warning(f"No se pudo leer la lista de almacenes desde MongoDB: {exc}")
        warehouse_ids = []
    selected_wh = st.selectbox(
        "Ámbito operativo: almacén",
        options=["(Todos)"] + warehouse_ids,
        help="Para operación diaria, filtra rápidamente el mapa, alertas y series temporales.",
    )

    # Filtro simple de número máximo de registros para la vista
    # (se controla desde los filtros globales del Control Tower)
    max_rows = int(st.session_state.get("ct_max_rows", 200))

    query: dict = {}
    if selected_wh != "(Todos)":
        query["warehouse_id"] = selected_wh

    # Mostrar la consulta equivalente que se va a ejecutar (para copiar/pegar)
    with st.expander("Ver consulta equivalente sobre MongoDB (copiable a terminal)"):
        filtro_str = "{}" if not query else str(query)
        st.markdown("**Python (PyMongo)**")
        st.code(
            f"""from pymongo import MongoClient

client = MongoClient("{MONGO_URI}")
db = client["{MONGO_DB}"]
coll = db["{MONGO_AGGREGATED_COLLECTION}"]

docs = list(
    coll.find({filtro_str}, {{"_id": 0}})
        .sort("window_start", 1)
        .limit({max_rows})
)
""",
            language="python",
        )
        st.markdown("**mongosh**")
        st.code(
            f"""mongo "{MONGO_URI}" --eval '
db.getSiblingDB("{MONGO_DB}").{MONGO_AGGREGATED_COLLECTION}.find(
  {filtro_str},
  {{ _id: 0 }}
).sort({{ window_start: 1 }}).limit({max_rows})
'""",
            language="bash",
        )

    try:
        agg_docs = list(
            agg_coll.find(query, {"_id": 0})
            .sort("window_start", 1)
            .limit(max_rows)
        )
    except Exception as exc:  # pragma: no cover
        st.error(f"No se pudieron cargar los agregados desde MongoDB: {exc}")
        agg_docs = []
    if agg_docs:
        agg_df = pd.DataFrame(agg_docs)
        if "window_start" in agg_df.columns:
            agg_df["window_start"] = pd.to_datetime(agg_df["window_start"])

        # Métricas adicionales para optimización de transporte
        if {"avg_delay_min", "vehicle_count"}.issubset(agg_df.columns):
            # Evitar división por cero
            agg_df["delay_per_vehicle_min"] = agg_df.apply(
                lambda r: (r["avg_delay_min"] / r["vehicle_count"])
                if r.get("vehicle_count", 0) not in (0, None)
                else 0.0,
                axis=1,
            )

        # Barra superior: estado y KPIs live
        status_label, status_color = compute_status(agg_df, anom_df)
        delay_cost = estimate_delay_cost_eur(agg_df, GRAPH_DELAY_COST_EUR_PER_MIN)
        vehicle_active = int(agg_df.get("vehicle_count", pd.Series([0])).sum()) if agg_df is not None else 0
        avg_delay = float(agg_df.get("avg_delay_min", pd.Series([0.0])).mean()) if agg_df is not None else 0.0

        k1, k2, k3, k4 = st.columns([1, 1, 1, 1.2])
        with k1:
            st.metric("Retraso medio (min)", f"{avg_delay:.1f}")
        with k2:
            st.metric("Vehículos activos (suma)", f"{vehicle_active}")
        with k3:
            st.markdown(
                f"""
<div style="padding: 0.5rem 0.75rem; border-radius: 0.5rem; background: {status_color}; color: white; font-weight: 700; text-align:center;">
ESTADO: {status_label}
</div>
""",
                unsafe_allow_html=True,
            )
        with k4:
            st.metric("Coste estimado retraso (€)", f"{delay_cost:,.0f}")

        st.markdown("**Operación (tabla de retrasos con métricas)**")
        st.dataframe(agg_df)

        if {"window_start", "avg_delay_min"}.issubset(agg_df.columns):
            st.markdown("**Tendencia (últimas ventanas mostradas)**")
            st.line_chart(agg_df.set_index("window_start")[["avg_delay_min"]].sort_index(), height=220)
    else:
        st.info("No se han encontrado agregados de retrasos con los filtros actuales.")

    st.subheader("Ventanas marcadas como anómalas (K-Means)")
    anom_coll = db[MONGO_ANOMALIES_COLLECTION]

    anom_query: dict = {"anomaly_flag": True}
    if selected_wh != "(Todos)":
        anom_query["warehouse_id"] = selected_wh

    with st.expander("Ver consulta equivalente sobre MongoDB para anomalías"):
        filtro_anom_str = str(anom_query)
        st.markdown("**Python (PyMongo)**")
        st.code(
            f"""from pymongo import MongoClient

client = MongoClient("{MONGO_URI}")
db = client["{MONGO_DB}"]
coll = db["{MONGO_ANOMALIES_COLLECTION}"]

docs = list(
    coll.find({filtro_anom_str}, {{"_id": 0}})
        .sort("window_start", 1)
        .limit({max_rows})
)
""",
            language="python",
        )
        st.markdown("**mongosh**")
        st.code(
            f"""mongo "{MONGO_URI}" --eval '
db.getSiblingDB("{MONGO_DB}").{MONGO_ANOMALIES_COLLECTION}.find(
  {filtro_anom_str},
  {{ _id: 0 }}
).sort({{ window_start: 1 }}).limit({max_rows})
'""",
            language="bash",
        )

    try:
        anom_docs = list(
            anom_coll.find(anom_query, {"_id": 0})
            .sort("window_start", 1)
            .limit(max_rows)
        )
    except Exception as exc:  # pragma: no cover
        st.error(f"No se pudieron cargar las anomalías desde MongoDB: {exc}")
        anom_docs = []
    if anom_docs:
        anom_df = pd.DataFrame(anom_docs)
        if "window_start" in anom_df.columns:
            anom_df["window_start"] = pd.to_datetime(anom_df["window_start"])
        st.dataframe(anom_df)
    else:
        st.info("No se han encontrado anomalías para los filtros actuales.")

    # Mongo disponible: leer incidencias; si no, modo demo (derivar de anomalías)
    incidents: list[dict] = []
    try:
        inc_coll = db[MONGO_INCIDENTS_COLLECTION]
        incidents = list(
            inc_coll.find(
                {"status": {"$in": ["nueva", "en_curso"]}},
                {"_id": 0},
            ).sort("created_at", -1).limit(50)
        )
    except Exception:
        _ensure_demo_incidents_from_anomalies(anom_df)
        incidents = get_store().get("incidents", [])

    incidents_filtered = [
        x for x in incidents if float(x.get("severity", 0) or 0) >= float(st.session_state.get("ct_min_sev", 0))
    ]

    st.markdown("---")
    st.subheader("Mapa operativo y panel de alertas")
    map_col, alert_col = st.columns([1.5, 1])

    with map_col:
        if agg_df is not None and not agg_df.empty and "window_start" in agg_df.columns:
            ventanas = sorted(agg_df["window_start"].dt.to_pydatetime())
            if ventanas:
                ventana_sel = st.selectbox(
                    "Ventana 15 min",
                    options=ventanas,
                    format_func=lambda dt: dt.strftime("%Y-%m-%d %H:%M"),
                    key="ct_map_ventana",
                )
                sel_mask = agg_df["window_start"] == ventana_sel
                agg_win = agg_df[sel_mask].copy()
                if not agg_win.empty:
                    _, wh_df_map, _ = load_sample_data()
                    wh_df_override = st.session_state.get("warehouses_override_df")
                    if wh_df_override is not None:
                        wh_df_map = wh_df_override
                    if wh_df_map is not None and {"warehouse_id", "lat", "lon"}.issubset(wh_df_map.columns):
                        merged = agg_win.merge(
                            wh_df_map[["warehouse_id", "lat", "lon"]],
                            on="warehouse_id",
                            how="left",
                        ).dropna(subset=["lat", "lon"])
                        if not merged.empty:
                            m = folium.Map(location=[40.0, -3.7], zoom_start=5, tiles="OpenStreetMap")
                            for _, row in merged.iterrows():
                                tooltip = (
                                    f"Almacén: {row['warehouse_id']}\n"
                                    f"Vehículos: {row.get('vehicle_count', 'N/A')}\n"
                                    f"Retraso medio: {row.get('avg_delay_min', 'N/A')} min"
                                )
                                folium.CircleMarker(
                                    location=[row["lat"], row["lon"]],
                                    radius=5 + float(row.get("vehicle_count", 1)) * 0.3,
                                    color="#FF8800" if row.get("avg_delay_min", 0) > 0 else "#00C846",
                                    fill=True,
                                    fill_opacity=0.9,
                                    tooltip=tooltip,
                                ).add_to(m)
                            st_folium(m, width=None, height=420)
                        else:
                            st.info("Sin coordenadas para esta ventana.")
                    else:
                        st.info("Falta warehouses con lat/lon.")
            else:
                st.info("Sin ventanas en los datos.")
        else:
            st.info("Carga datos de retrasos para ver el mapa por ventana.")

    with alert_col:
        st.markdown("**Alertas activas**")
        if incidents_filtered:
            for inc in incidents_filtered[:15]:
                inc_id = str(inc.get("incident_id", ""))
                asignado = str(inc.get("asignado_a", "") or "—")
                sev = inc.get("severity", 0)
                wh = str(inc.get("warehouse_id", "") or "—")
                st.markdown(
                    f"`{inc_id}` · {wh} · {sev:.0f} min · **{asignado or '—'}**"
                )
            sel_id = st.selectbox(
                "Abrir incidencia",
                options=[str(x.get("incident_id")) for x in incidents_filtered],
                key="ct_incident_select",
            )
            op_name = st.text_input(
                "Operador (para Asignar a mí)",
                value=str(st.session_state.get("operator_name", "admin")),
                key="ct_operator_name",
            )
            if op_name:
                st.session_state["operator_name"] = op_name
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("Ver detalle →", key="ct_open_incident"):
                    st.session_state["selected_incident_id"] = sel_id
                    navigate_to("6.1 · Incidencias y decisiones")
            with c_b:
                if st.button("Asignar a mí", key="ct_assign_me"):
                    target = next((x for x in incidents_filtered if str(x.get("incident_id")) == sel_id), None)
                    if target:
                        target["asignado_a"] = op_name or "admin"
                        target["updated_at"] = _now_iso()
                        upsert_incident(db=db, incident=target)
                    st.success("Asignado.")
        else:
            st.info("No hay alertas activas.")

    # Zona de explotación administrativa (modo real con MongoDB)
    render_admin_actions(agg_df, anom_df)

    client.close()


def page_incidencias_decisiones() -> None:
    st.header("6.1 · Incidencias y decisiones (operación)")
    render_top_nav("6.1 · Incidencias y decisiones")
    render_search_highlight(
        "aquí se gestionan **incidencias activas** y se registran **decisiones operativas** (ruta alternativa, escalado, etc.) con evidencias."
    )

    selected_id = str(st.session_state.get("selected_incident_id", "") or "")

    db: pymongo.database.Database | None = None
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        db = client[MONGO_DB]
    except Exception:
        db = None

    incidents: list[dict]
    decisions: list[dict]
    if db is None:
        store = get_store()
        incidents = list(store.get("incidents", []))
        decisions = list(store.get("decisions", []))
    else:
        incidents = list(db[MONGO_INCIDENTS_COLLECTION].find({}, {"_id": 0}).sort("created_at", -1).limit(200))
        decisions = list(db[MONGO_DECISIONS_COLLECTION].find({}, {"_id": 0}).sort("created_at", -1).limit(500))

    if not incidents:
        st.info("No hay incidencias registradas todavía. Vuelve al Control Tower y genera/recibe alertas.")
        return

    options = [str(x.get("incident_id")) for x in incidents]
    if selected_id and selected_id in options:
        idx = options.index(selected_id)
    else:
        idx = 0
        selected_id = options[0]

    incident_id = st.selectbox("Selecciona incidencia", options=options, index=idx, key="inc_sel")
    inc = next((x for x in incidents if str(x.get("incident_id")) == str(incident_id)), {})

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.subheader("Detalle")
        st.json(inc)
    with c2:
        st.subheader("Workflow")
        asignado_a = st.text_input(
            "Asignado a",
            value=str(inc.get("asignado_a", "") or ""),
            placeholder="Operador o equipo",
            key="inc_asignado_a",
        )
        new_status = st.selectbox(
            "Estado",
            options=["nueva", "en_curso", "resuelta"],
            index=["nueva", "en_curso", "resuelta"].index(str(inc.get("status", "nueva"))),
            key="inc_status",
        )
        if st.button("Guardar estado", key="inc_save_status"):
            inc["status"] = new_status
            inc["asignado_a"] = asignado_a.strip()
            inc["updated_at"] = _now_iso()
            upsert_incident(db=db, incident=inc)
            st.success("Estado actualizado.")

    st.markdown("---")
    st.subheader("Registrar decisión operativa")
    col_d1, col_d2, col_d3 = st.columns([1.2, 1, 1])
    with col_d1:
        action = st.selectbox(
            "Acción",
            options=["Reasignar ruta", "Escalar incidencia", "Avisar a almacén", "Sin acción (monitorizar)"],
            key="dec_action",
        )
        notes = st.text_area("Notas (qué se decide y por qué)", key="dec_notes", height=120)
    with col_d2:
        alt_route = st.text_input("Ruta alternativa sugerida (texto)", key="dec_alt_route")
        est_minutes_saved = st.number_input("Minutos estimados ganados (+) o perdidos (-)", value=0, step=5, key="dec_min_delta")
    with col_d3:
        est_cost_delta = st.number_input("Impacto estimado (€)", value=0, step=50, key="dec_cost_delta")
        operator = st.text_input("Operador", value=str(st.session_state.get("operator_name", "admin")), key="dec_operator")

    if st.button("Aplicar/registrar decisión", key="dec_apply"):
        decision = {
            "decision_id": f"DEC-{incident_id}-{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')}",
            "created_at": _now_iso(),
            "incident_id": incident_id,
            "action": action,
            "alt_route": alt_route,
            "minutes_delta": float(est_minutes_saved),
            "cost_delta_eur": float(est_cost_delta),
            "operator": operator,
            "notes": notes,
        }
        add_decision(db=db, decision=decision)
        st.success("Decisión registrada.")

    st.markdown("---")
    st.subheader("Histórico de decisiones (descargable)")
    dec_inc = [d for d in decisions if str(d.get("incident_id")) == str(incident_id)]
    if dec_inc:
        dec_df = pd.DataFrame(dec_inc)
        st.dataframe(dec_df, hide_index=True)
        st.download_button(
            "Descargar decisiones (CSV)",
            data=dec_df.to_csv(index=False).encode("utf-8"),
            file_name=f"decisions_{incident_id}.csv",
            mime="text/csv",
        )
    else:
        st.info("Aún no hay decisiones registradas para esta incidencia.")

    if db is not None:
        try:
            client.close()
        except Exception:
            pass


def page_historico_sla() -> None:
    st.header("6.2 · Histórico y SLA (mejora continua)")
    render_top_nav("6.2 · Histórico y SLA")
    render_search_highlight(
        "aquí se consulta el **histórico** (preferentemente en Hive) para análisis semanal/mensual y cumplimiento de SLA."
    )

    st.markdown(
        """
        Esta vista está pensada para:

        - **Tendencias** (semanal/mensual) por almacén y ruta.
        - **Cumplimiento SLA** (por ejemplo: % ventanas con retraso medio < umbral).
        - **Comparativas** vs periodo anterior.
        """
    )

    umbral_sla = st.slider("Umbral SLA (min de retraso medio)", 5, 120, 30, 5, key="sla_threshold")
    st.markdown("**Consulta recomendada en Hive (histórico)**")
    st.code(
        f"""USE transport;

SELECT
  warehouse_id,
  AVG(avg_delay_min) AS retraso_medio_min,
  SUM(CASE WHEN avg_delay_min < {umbral_sla} THEN 1 ELSE 0 END) / COUNT(1) AS pct_en_sla
FROM aggregated_delays
WHERE window_start >= date_sub(current_timestamp(), 7)
GROUP BY warehouse_id
ORDER BY retraso_medio_min DESC
LIMIT 50;""",
        language="sql",
    )

    st.info(
        "En esta demo, el histórico completo depende de Hive. Si no está disponible, "
        "puedes usar el Control Tower (Mongo) para operación diaria."
    )


def _iter_markdown_files(scope: str) -> list[Path]:
    scopes: dict[str, list[Path]] = {
        "docs (recomendado)": [PROJECT_ROOT / "docs"],
        "ingest + nifi": [PROJECT_ROOT / "ingest"],
        "hive + hdfs": [PROJECT_ROOT / "hive", PROJECT_ROOT / "hdfs"],
        "repo completo": [PROJECT_ROOT],
    }
    roots = scopes.get(scope, [PROJECT_ROOT / "docs"])
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend([p for p in root.rglob("*.md") if p.is_file()])
    files = sorted(files, key=lambda p: (0 if str(p).startswith(str(PROJECT_ROOT / "docs")) else 1, str(p)))
    return files


def _score_doc_match(*, query_terms: list[str], path: Path, text: str) -> float:
    if not query_terms:
        return 0.0
    rel = str(path.relative_to(PROJECT_ROOT)).lower()
    text_l = text.lower()

    score = 0.0
    for t in query_terms:
        if not t:
            continue
        if t in rel:
            score += 12.0
        cnt = text_l.count(t)
        score += min(20.0, cnt * 1.5)

    if all(t in text_l or t in rel for t in query_terms):
        score += 8.0

    if str(path).startswith(str(PROJECT_ROOT / "docs")):
        score += 4.0
    return score


def page_documentacion_busqueda() -> None:
    st.header("7 · Documentación (buscador tipo retrieval)")
    render_top_nav("7 · Documentación (buscador)")
    render_search_highlight(
        "esta vista permite encontrar **rápido** el `.md` relevante (por ejemplo: Codespaces, Airflow, Kafka, Hive, Grafana…)."
    )
    st.markdown(
        """
        Este buscador funciona como la parte de **recuperación** de un RAG (retrieval):
        busca en ficheros `.md` del repositorio y ordena por relevancia.
        """
    )

    c1, c2, c3 = st.columns([1.6, 1, 1])
    with c1:
        query = st.text_input(
            "Buscar en documentación",
            placeholder="Ej: codespaces, airflow, kafka topics, hive, grafana…",
            key="docs_query",
        )
    with c2:
        scope = st.selectbox(
            "Ámbito",
            options=["docs (recomendado)", "ingest + nifi", "hive + hdfs", "repo completo"],
            index=0,
            key="docs_scope",
        )
    with c3:
        max_results = st.number_input("Resultados", min_value=5, max_value=50, value=15, step=5, key="docs_max_results")

    if not query.strip():
        st.info("Escribe un término de búsqueda para localizar el `.md` más relevante.")
        st.markdown("Sugerencia: también tienes un índice en `docs/README.md`.")
        return

    query_norm = re.sub(r"\s+", " ", query.strip().lower())
    terms = [t for t in re.split(r"[\\s,;:/\\-]+", query_norm) if len(t) >= 3]
    if not terms:
        st.warning("La búsqueda es demasiado corta. Prueba con términos de 3+ caracteres.")
        return

    files = _iter_markdown_files(scope)
    results: list[tuple[float, Path, str]] = []

    for p in files:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        score = _score_doc_match(query_terms=terms, path=p, text=txt)
        if score <= 0:
            continue
        snippet = ""
        for line in txt.splitlines():
            l = line.strip()
            if not l:
                continue
            ll = l.lower()
            if any(t in ll for t in terms):
                snippet = l[:240]
                break
        results.append((score, p, snippet))

    if not results:
        st.warning("No se encontraron coincidencias. Prueba con otros términos o cambia el ámbito.")
        return

    results = sorted(results, key=lambda x: x[0], reverse=True)[: int(max_results)]
    st.markdown(f"**Top {len(results)} resultados** (ámbito: `{scope}`)")

    st.caption(
        "Cada resultado muestra una previa corta. Puedes desplegar el detalle o descargar el `.md` completo."
    )

    for score, path, snippet in results:
        rel = str(path.relative_to(PROJECT_ROOT))
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - interactivo
            st.error(f"No se pudo leer `{rel}`: {exc}")
            continue

        # Previa: primeras N líneas
        lines = content.splitlines()
        max_preview_lines = 40
        if len(lines) > max_preview_lines:
            preview = "\n".join(lines[:max_preview_lines]) + "\n\n..."
        else:
            preview = "\n".join(lines)

        with st.expander(f"{rel}  ·  score {score:.1f}", expanded=False):
            if snippet:
                st.markdown(f"**Snippet:** {snippet}")
                st.markdown("---")

            st.markdown("**Previa (primeras líneas):**")
            st.markdown(preview)

            st.download_button(
                "Descargar `.md` completo",
                data=content.encode("utf-8"),
                file_name=path.name,
                mime="text/markdown",
                key=f"dl_{rel}",
            )


def main():
    st.set_page_config(
        page_title="Sentinel360 – Presentación KDD",
        layout="wide",
    )
    st.sidebar.title("Sentinel360 – Demo KDD")
    st.sidebar.markdown("Selecciona la etapa del ciclo KDD:")
    st.sidebar.markdown(
        "[Repositorio en GitHub]("
        "https://github.com/gracobjo/Proyecto-Big-Data-Sentinel-360"
        ")"
    )

    # Buscador semántico ligero por etapas (UX mejorada)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Buscador de conceptos (KDD)**")
    search_term = st.sidebar.text_input(
        "Escribe una palabra clave (ej. 'grafos', 'airflow', 'retrasos', 'k-means')",
        key="sidebar_search_term",
    )

    search_results: list[tuple[str, str]] = []
    if search_term:
        term = search_term.lower()
        # Índice muy ligero: mapeo de etapas a descripciones/keywords
        page_index: dict[str, str] = {
            "0 · Arranque de servicios": "infraestructura servicios hdfs yarn kafka hive mongodb mariadb nifi airflow dags start stop cluster",
            "1 · Fase I – Ingesta": "fase i ingesta nifi kafka hdfs raw gps openweather flujo getfile publishkafka",
            "2 · Fase II – Limpieza y enriquecimiento": "fase ii limpieza preprocesamiento spark hive enriched cleaned warehouses routes",
            "3 · Fase II – Grafos": "grafos graphframes rutas almacenes shortest path topologia estrella hibrida simulacion incidencias costes mapa",
            "4 · Fase III – Streaming + anomalías": "streaming retrasos ventanas aggregated_delays kafka alerts k-means anomaly_detection spark ml",
            "5 · Entorno visual (Superset / Grafana / Airflow)": "dashboards superset grafana airflow dags orquestacion kpi mariadb export",
            "6 · Dashboard (Retrasos / Anomalías)": "dashboard final retrasos anomalías consultas mongo hive informes top 5 mapa posiciones",
            "6.1 · Incidencias y decisiones": "incidencias alertas decisiones workflow operador reasignar ruta escalar evidencias",
            "6.2 · Histórico y SLA": "historico sla otif tendencias semanal mensual hive cumplimiento comparativas",
            "7 · Documentación (buscador)": "documentacion docs markdown md buscar busqueda retrieval rag codespaces airflow kafka hive grafana superset",
        }
        for label, keywords in page_index.items():
            if term in keywords:
                search_results.append(
                    (
                        label,
                        keywords,
                    )
                )

        if search_results:
            st.sidebar.markdown("Resultados de búsqueda:")
            for label, _ in search_results:
                st.sidebar.button(
                    f"Ir a: {label}",
                    key=f"search_nav_{label}",
                    on_click=navigate_to,
                    args=(label,),
                )
        else:
            st.sidebar.caption("Sin coincidencias para este término.")

    pages = {
        "0 · Arranque de servicios": page_arranque_servicios,
        "1 · Fase I – Ingesta": page_fase_i_ingesta,
        "2 · Fase II – Limpieza y enriquecimiento": page_fase_ii_limpieza_enriquecimiento,
        "3 · Fase II – Grafos": page_fase_ii_grafos,
        "4 · Fase III – Streaming + anomalías": page_fase_iii_streaming_anomalias,
        "5 · Entorno visual (Superset / Grafana / Airflow)": page_entorno_visual,
        "6 · Dashboard (Retrasos / Anomalías)": page_dashboard_kpis,
        "6.1 · Incidencias y decisiones": page_incidencias_decisiones,
        "6.2 · Histórico y SLA": page_historico_sla,
        "7 · Documentación (buscador)": page_documentacion_busqueda,
    }

    page_names = list(pages.keys())
    if "sidebar_page" not in st.session_state:
        st.session_state["sidebar_page"] = page_names[0]

    st.sidebar.radio(
        "Etapa",
        page_names,
        key="sidebar_page",
    )

    pages[st.session_state["sidebar_page"]]()


if __name__ == "__main__":
    main()

