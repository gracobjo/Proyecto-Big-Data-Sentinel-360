#!/usr/bin/env python3
"""
Exporta a MariaDB los resultados de las consultas Hive más relevantes para Sentinel360:
- aggregated_delays (ventanas 15 min por almacén)
- reporte_diario_retrasos (resumen diario por almacén; se genera antes si hace falta)

Requisitos: HiveServer2 en marcha, MariaDB con tablas kpi_hive_aggregated_delays y
kpi_hive_reporte_diario (ver docs/sql_entorno_visual/02_create_kpi_tables.sql).
Uso: python3 scripts/export_hive_to_mariadb.py [--dias N]
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from config import MARIA_DB_URI, MARIA_DB_HOST, MARIA_DB_PORT, MARIA_DB_USER, MARIA_DB_PASSWORD, MARIA_DB_NAME
except ImportError:
    MARIA_DB_HOST = os.environ.get("MARIA_DB_HOST", "127.0.0.1")
    MARIA_DB_PORT = int(os.environ.get("MARIA_DB_PORT", "3307"))
    MARIA_DB_USER = os.environ.get("MARIA_DB_USER", "sentinel")
    MARIA_DB_PASSWORD = os.environ.get("MARIA_DB_PASSWORD", "sentinel_password")
    MARIA_DB_NAME = os.environ.get("MARIA_DB_NAME", "sentinel360_analytics")
    MARIA_DB_URI = f"mysql+pymysql://{MARIA_DB_USER}:{MARIA_DB_PASSWORD}@{MARIA_DB_HOST}:{MARIA_DB_PORT}/{MARIA_DB_NAME}"

BEELINE_OPTS = os.environ.get("BEELINE_OPTS", "-u jdbc:hive2://localhost:10000 -n hadoop")
BEELINE_CMD = os.environ.get("BEELINE_CMD", "beeline")


def run_beeline_query(query: str) -> str:
    """Ejecuta una consulta en Hive vía beeline y devuelve la salida (tab-separated)."""
    cmd = [BEELINE_CMD] + BEELINE_OPTS.split() + ["--silent=true", "--outputformat=tsv2", "-e", query]
    try:
        out = subprocess.run(
            cmd,
            cwd=str(_project_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if out.returncode != 0:
            print(f"Beeline stderr: {out.stderr}", file=sys.stderr)
            raise RuntimeError(f"beeline falló con código {out.returncode}")
        return out.stdout
    except FileNotFoundError:
        raise RuntimeError("No se encontró 'beeline'. Asegúrate de tener Hive en el PATH.")


def parse_tsv(out: str, skip_header: bool = True):
    """Convierte salida tsv de beeline en filas (listas)."""
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if skip_header and lines:
        lines = lines[1:]
    for line in lines:
        yield [c.strip() for c in line.split("\t")]


def export_aggregated_delays(dias: int = 7) -> None:
    """Exporta aggregated_delays (últimos N días) a MariaDB kpi_hive_aggregated_delays."""
    import sqlalchemy
    from sqlalchemy import text

    query = f"SELECT window_start, window_end, warehouse_id, avg_delay_min, vehicle_count FROM transport.aggregated_delays WHERE window_start >= date_sub(current_timestamp(), {dias}) ORDER BY window_start, warehouse_id"
    out = run_beeline_query(query)
    rows = list(parse_tsv(out))
    if not rows:
        print("No hay filas en aggregated_delays para el periodo indicado.")
        return

    engine = sqlalchemy.create_engine(MARIA_DB_URI)
    # Truncar o borrar datos recientes para idempotencia (opcional: DELETE WHERE window_start >= ...)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM kpi_hive_aggregated_delays"))
        conn.commit()
    # Insertar
    def _safe_int(s):
        if not s or not str(s).strip():
            return 0
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    def _safe_float(s):
        if not s or not str(s).strip():
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    with engine.connect() as conn:
        for r in rows:
            if len(r) < 5:
                continue
            conn.execute(
                text(
                    "INSERT INTO kpi_hive_aggregated_delays (window_start, window_end, warehouse_id, avg_delay_min, vehicle_count) "
                    "VALUES (:ws, :we, :wh, :avg, :vc)"
                ),
                {"ws": r[0], "we": r[1], "wh": (r[2] or "")[:64], "avg": _safe_float(r[3]), "vc": _safe_int(r[4])},
            )
        conn.commit()
    print(f"Exportadas {len(rows)} filas de aggregated_delays a kpi_hive_aggregated_delays.")


def run_reporte_diario_hive() -> None:
    """Ejecuta el INSERT de reporte diario en Hive (reporte_diario.sql)."""
    reporte_sql = _project_root / "hive" / "queries" / "reporte_diario.sql"
    if not reporte_sql.exists():
        print(f"No encontrado {reporte_sql}, se omite reporte diario.")
        return
    with open(reporte_sql) as f:
        query = f.read()
    run_beeline_query(query)
    print("Reporte diario ejecutado en Hive (reporte_diario_retrasos).")


def export_reporte_diario(dias: int = 30) -> None:
    """Exporta reporte_diario_retrasos desde Hive a MariaDB kpi_hive_reporte_diario."""
    import sqlalchemy
    from sqlalchemy import text

    run_reporte_diario_hive()
    query = f"SELECT fecha_reportado, warehouse_id, total_vehiculos, avg_retraso_min, ventanas_15min FROM transport.reporte_diario_retrasos WHERE fecha_reportado >= date_sub(current_date, {dias}) ORDER BY fecha_reportado, warehouse_id"
    out = run_beeline_query(query)
    rows = list(parse_tsv(out))
    if not rows:
        print("No hay filas en reporte_diario_retrasos.")
        return

    engine = sqlalchemy.create_engine(MARIA_DB_URI)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM kpi_hive_reporte_diario"))
        conn.commit()
    def _safe_int(s):
        if not s or not str(s).strip():
            return 0
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    def _safe_float(s):
        if not s or not str(s).strip():
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    with engine.connect() as conn:
        for r in rows:
            if len(r) < 5:
                continue
            conn.execute(
                text(
                    "INSERT INTO kpi_hive_reporte_diario (fecha_reportado, warehouse_id, total_vehiculos, avg_retraso_min, ventanas_15min) "
                    "VALUES (:fecha, :wh, :tv, :avg, :v15)"
                ),
                {"fecha": r[0], "wh": (r[1] or "")[:64], "tv": _safe_int(r[2]), "avg": _safe_float(r[3]), "v15": _safe_int(r[4])},
            )
        conn.commit()
    print(f"Exportadas {len(rows)} filas de reporte_diario_retrasos a kpi_hive_reporte_diario.")


def main():
    parser = argparse.ArgumentParser(description="Exportar consultas Hive a MariaDB para dashboards.")
    parser.add_argument("--dias", type=int, default=7, help="Días de histórico para aggregated_delays (default 7).")
    parser.add_argument("--solo-agregados", action="store_true", help="Solo exportar aggregated_delays.")
    parser.add_argument("--solo-reporte", action="store_true", help="Solo exportar reporte diario.")
    args = parser.parse_args()

    if not args.solo_reporte:
        export_aggregated_delays(dias=args.dias)
    if not args.solo_agregados:
        export_reporte_diario(dias=30)


if __name__ == "__main__":
    main()
