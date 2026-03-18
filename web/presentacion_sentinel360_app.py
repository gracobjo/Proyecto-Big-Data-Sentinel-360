import subprocess
import sys
import base64
import heapq
from pathlib import Path

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

from config import (  # type: ignore
    MONGO_URI,
    MONGO_DB,
    MONGO_AGGREGATED_COLLECTION,
    MONGO_ANOMALIES_COLLECTION,
)

import pymongo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
]

# Parámetros por defecto para la simulación de grafos / incidencias.
# Desarrollador: puedes ajustarlos aquí si quieres cambiar el modelo base.
GRAPH_BASE_DISTANCE_KM = 300.0
GRAPH_BASE_DURATION_MIN = 240.0  # 4h
GRAPH_ALT_DISTANCE_FACTOR = 1.10  # ruta alternativa 10% más larga
GRAPH_ALT_DURATION_FACTOR = 0.90  # algo más fluida que la ruta afectada
GRAPH_FUEL_COST_EUR_PER_KM = 1.2
GRAPH_DELAY_COST_EUR_PER_MIN = 2.0


def run_command(cmd: str) -> str:
    """
    Ejecuta un comando de shell desde la raíz del proyecto y devuelve stdout+stderr.
    No lanza excepción si falla: devolvemos el error en texto para mostrarlo en Streamlit.
    """
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return completed.stdout
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        return f"Error ejecutando comando:\n{exc}"


def load_sample_data():
    gps_path = DATA_SAMPLE_DIR / "gps_events.csv"
    wh_path = DATA_SAMPLE_DIR / "warehouses.csv"
    routes_path = DATA_SAMPLE_DIR / "routes.csv"

    gps_df = pd.read_csv(gps_path) if gps_path.exists() else None
    wh_df = pd.read_csv(wh_path) if wh_path.exists() else None
    routes_df = pd.read_csv(routes_path) if routes_path.exists() else None
    return gps_df, wh_df, routes_df


def get_mongo_client() -> pymongo.MongoClient:
    # Fail-fast para UX: no bloquear ~30s si Mongo no está levantado
    return pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)


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

    docs_path = PROJECT_ROOT / "docs" / "ARRANQUE_SERVICIOS.md"
    if docs_path.exists():
        with st.expander("Ver detalle de arranque de servicios (`docs/ARRANQUE_SERVICIOS.md`)"):
            st.markdown(docs_path.read_text(encoding="utf-8"))
    else:
        st.info("No se ha encontrado `docs/ARRANQUE_SERVICIOS.md` en el proyecto.")

    st.subheader("Comando que se va a ejecutar")
    st.code("./scripts/start_servicios.sh", language="bash")

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
        with st.spinner("Arrancando servicios..."):
            output = run_command("./scripts/start_servicios.sh")
        st.subheader("Salida del script")
        st.text(output)

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

    if st.button("Ejecutar comandos de Fase I"):
        with st.spinner("Ejecutando scripts de Fase I..."):
            output = run_command("./scripts/setup_hdfs.sh && ./scripts/preparar_ingesta_nifi.sh")
        st.subheader("Salida de los scripts")
        st.text(output)

    st.subheader("Datos de ejemplo (data/sample)")
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
        with st.spinner("Lanzando jobs Spark de limpieza y enriquecimiento..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py && "
                "./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py"
            )
        st.subheader("Salida de Spark submit")
        st.text(output)

    # Si el usuario ha subido una versión de almacenes o rutas, la usamos aquí
    wh_df_override = st.session_state.get("warehouses_override_df")
    routes_df_override = st.session_state.get("routes_override_df")

    gps_df, wh_df, routes_df = load_sample_data()
    if wh_df_override is not None:
        wh_df = wh_df_override
    if routes_df_override is not None:
        routes_df = routes_df_override
    if wh_df is not None:
        st.subheader("Almacenes (`warehouses.csv`)")
        st.dataframe(wh_df)
        if {"lat", "lon"}.issubset(wh_df.columns):
            st.map(wh_df.rename(columns={"lat": "latitude", "lon": "longitude"}))

    if routes_df is not None:
        st.subheader("Rutas (`routes.csv`)")
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

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/graph/transport_graph.py\n"
        "python scripts/ver_grafos_resultados.py --viz\n",
        language="bash",
    )

    if st.button("Lanzar análisis de grafos"):
        with st.spinner("Lanzando Spark (GraphFrames) y generación de grafo..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/graph/transport_graph.py && "
                f"{sys.executable} scripts/ver_grafos_resultados.py --viz"
            )
        st.subheader("Salida de comandos de grafos")
        st.text(output)

    grafo_png = PROJECT_ROOT / "grafo.png"
    if grafo_png.exists():
        st.subheader("Imagen del grafo (`grafo.png`)")
        st.image(str(grafo_png))
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

    if st.button("Lanzar streaming de retrasos"):
        with st.spinner("Lanzando Spark Streaming (delays_windowed.py)..."):
            output = run_command(
                f"./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {modo_stream}"
            )
        st.subheader("Salida de delays_windowed.py")
        st.text(output)

    if st.button("Lanzar detección de anomalías (batch)"):
        with st.spinner("Lanzando Spark ML (anomaly_detection.py)..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py"
            )
        st.subheader("Salida de anomaly_detection.py")
        st.text(output)

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
        - `sentinel360_fase_i_ingesta`: prepara NiFi/Kafka, genera GPS sintético + OpenWeather y deja datos listos en raw.
        - `sentinel360_fase_ii_preprocesamiento`: ejecuta limpieza, enriquecimiento y grafo de transporte (Spark + Hive).
        - `sentinel360_fase_iii_batch` / `sentinel360_fase_iii_streaming`: calculan agregados de retrasos, anomalías y KPIs.
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
        st.markdown("**Ejemplo de DAG batch `sentinel360_fase_iii_batch` (tareas principales):**")
        st.code(
            """with DAG(
    dag_id="sentinel360_fase_iii_batch",
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
    → sentinel360_fase_i_ingesta
        → sentinel360_fase_ii_preprocesamiento
            → sentinel360_fase_iii_batch / sentinel360_fase_iii_streaming
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
    st.header("6 · Dashboard de retrasos y anomalías")
    render_search_highlight(
        "este es el **cuadro de mando final** para consultar retrasos, anomalías y KPIs, tanto en modo demo como contra **MongoDB/Hive** reales."
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

        render_admin_actions(agg_df, anom_df)
        return

    st.subheader("Retrasos agregados por almacén")
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
        "Selecciona almacén (warehouse_id)",
        options=["(Todos)"] + warehouse_ids,
    )

    # Filtro simple de número máximo de registros para la vista
    max_rows = st.slider("Número máximo de filas a mostrar", min_value=50, max_value=1000, value=200, step=50)

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

        st.markdown("**Tabla de retrasos con métricas de optimización**")
        st.dataframe(agg_df)

        if {"window_start", "avg_delay_min"}.issubset(agg_df.columns):
            st.markdown("**Evolución del retraso medio por ventana (15 min)**")
            st.line_chart(
                agg_df.set_index("window_start")[["avg_delay_min"]].sort_index(),
                height=250,
            )
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

    # Mapa de posiciones de vehículos por ventana de 15 minutos (vista agregada por almacén)
    if agg_df is not None and not agg_df.empty and "window_start" in agg_df.columns:
        st.markdown("---")
        st.subheader("Posición agregada de vehículos por almacén y ventana (15 min)")
        ventanas = sorted(agg_df["window_start"].dt.to_pydatetime())
        if ventanas:
            ventana_sel = st.selectbox(
                "Selecciona una ventana de 15 minutos",
                options=ventanas,
                format_func=lambda dt: dt.strftime("%Y-%m-%d %H:%M"),
            )

            sel_mask = agg_df["window_start"] == ventana_sel
            agg_win = agg_df[sel_mask].copy()

            if not agg_win.empty:
                # Enriquecer con coordenadas de almacenes para pintarlos en el mapa
                _, wh_df_map, _ = load_sample_data()
                wh_df_override = st.session_state.get("warehouses_override_df")
                if wh_df_override is not None:
                    wh_df_map = wh_df_override

                if wh_df_map is not None and {"warehouse_id", "lat", "lon"}.issubset(
                    wh_df_map.columns
                ):
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
                                f"Retraso medio: {row.get('avg_delay_min', 'N/A')} min\n"
                                f"Retraso por vehículo: {row.get('delay_per_vehicle_min', 0):.1f} min"
                            )
                            folium.CircleMarker(
                                location=[row["lat"], row["lon"]],
                                radius=5
                                + float(row.get("vehicle_count", 1)) * 0.3,  # más grande si hay más vehículos
                                color="#FF8800" if row.get("avg_delay_min", 0) > 0 else "#00C846",
                                fill=True,
                                fill_opacity=0.9,
                                tooltip=tooltip,
                            ).add_to(m)

                        st_folium(m, width=900, height=500)
                    else:
                        st.info(
                            "No se puede mostrar el mapa porque no hay almacenes con coordenadas "
                            "para esta ventana."
                        )
                else:
                    st.info(
                        "No se ha encontrado un `warehouses.csv` con columnas `warehouse_id`, `lat`, `lon` "
                        "para poder posicionar los vehículos en el mapa."
                    )

    # Zona de explotación administrativa (modo real con MongoDB)
    render_admin_actions(agg_df, anom_df)

    client.close()


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

