#!/usr/bin/env python3
"""
Inserta datos de ejemplo en las tablas de KPIs de MariaDB para que los
dashboards de Grafana (y Superset) muestren algo en la demo.

Uso:
  python scripts/seed_kpi_demo_data.py

Si usas Docker y falla la conexión (Access denied), usa en su lugar:
  ./scripts/seed_kpi_demo_via_docker.sh

Requisitos:
  - MariaDB con la base sentinel360_analytics y tablas creadas
    (docs/sql_entorno_visual/01_create_db_and_user.sql y 02_create_kpi_tables.sql)
  - Conexión: por defecto localhost:3306, usuario sentinel (config.py o env)
"""
import os
import sys
from datetime import datetime, timedelta

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# URI para MariaDB: forzar 127.0.0.1 cuando el host sea localhost (evita "Access denied" con Docker)
def _build_uri():
    if os.environ.get("MARIA_DB_URI"):
        uri = os.environ["MARIA_DB_URI"]
        if "localhost" in uri.split("@")[1].split("/")[0].split(":")[0]:
            uri = uri.replace("localhost", "127.0.0.1", 1)
        return uri
    try:
        from config import MARIA_DB_HOST, MARIA_DB_PORT, MARIA_DB_USER, MARIA_DB_PASSWORD, MARIA_DB_NAME
        _h = (MARIA_DB_HOST or "localhost").strip()
        _host = "127.0.0.1" if _h in ("localhost", "127.0.0.1") else _h
        return f"mysql+pymysql://{MARIA_DB_USER}:{MARIA_DB_PASSWORD}@{_host}:{MARIA_DB_PORT}/{MARIA_DB_NAME}"
    except ImportError:
        return "mysql+pymysql://sentinel:sentinel_password@127.0.0.1:3306/sentinel360_analytics"

MARIA_DB_URI = _build_uri()

import pandas as pd
import sqlalchemy
from sqlalchemy import text


def main():
    engine = sqlalchemy.create_engine(MARIA_DB_URI)

    try:
        conn = engine.connect()
    except Exception as e:
        if "Access denied" in str(e) or "1045" in str(e):
            print("Error: MariaDB rechazó la conexión (usuario/contraseña o host).")
            print("Si usas Docker, ejecuta esto para crear usuario en localhost y 127.0.0.1:")
            print()
            for line in [
                "docker exec sentinel360-mariadb mysql -u root -proot_password -e \\",
                "  \"CREATE USER IF NOT EXISTS 'sentinel'@'localhost' IDENTIFIED BY 'sentinel_password';\"",
                "docker exec sentinel360-mariadb mysql -u root -proot_password -e \\",
                "  \"GRANT ALL ON sentinel360_analytics.* TO 'sentinel'@'localhost'; FLUSH PRIVILEGES;\"",
            ]:
                print(" ", line)
            print("\nLuego: python scripts/seed_kpi_demo_data.py")
        raise
    conn.close()

    # Comprobar que las tablas existen
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'sentinel360_analytics' AND table_name = 'kpi_delays_by_warehouse'"
        ))
        if r.scalar() == 0:
            print("Las tablas no existen. Ejecuta antes:")
            print("  mysql -u root -p < docs/sql_entorno_visual/01_create_db_and_user.sql")
            print("  mysql -u sentinel -p sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql")
            print("O desde el contenedor MariaDB:")
            print("  docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password < docs/sql_entorno_visual/02_create_kpi_tables.sql")
            sys.exit(1)

    # Generar ventanas de los últimos 7 días (Grafana suele usar "now-7d" por defecto)
    now = datetime.utcnow()
    warehouses = ["WH-MAD", "WH-BCN", "WH-VLC", "WH-BIL", "WH-SEV"]
    rows_wh = []
    for d in range(7):
        for h in range(0, 24, 3):  # cada 3 horas
            window_start = now - timedelta(days=d, hours=h)
            window_end = window_start + timedelta(minutes=15)
            for i, wh in enumerate(warehouses):
                # Variar un poco los retrasos por almacén
                base_delay = 5.0 + (i * 3) + (d * 0.5)
                rows_wh.append({
                    "warehouse_id": wh,
                    "window_start": window_start,
                    "window_end": window_end,
                    "trips_count": 10 + (d * 2) + i,
                    "delayed_trips": 2 + d + i,
                    "avg_delay_minutes": round(base_delay + (h % 5), 2),
                    "max_delay_minutes": round(base_delay * 2 + 5, 2),
                })

    df_wh = pd.DataFrame(rows_wh)
    now_ts = datetime.utcnow()
    df_wh["created_at"] = now_ts
    df_wh["updated_at"] = now_ts
    df_wh.to_sql("kpi_delays_by_warehouse", con=engine, if_exists="append", index=False)
    print(f"Insertadas {len(df_wh)} filas en kpi_delays_by_warehouse.")

    # Opcional: unos pocos por vehículo
    vehicles = [f"V-{i:03d}" for i in range(1, 11)]
    rows_v = []
    for d in range(3):
        for h in range(0, 24, 6):
            window_start = now - timedelta(days=d, hours=h)
            window_end = window_start + timedelta(minutes=15)
            for v in vehicles:
                rows_v.append({
                    "vehicle_id": v,
                    "window_start": window_start,
                    "window_end": window_end,
                    "trips_count": 2,
                    "delayed_trips": 1,
                    "avg_delay_minutes": round(3.0 + (hash(v) % 10) / 2, 2),
                    "max_delay_minutes": round(8.0 + (hash(v) % 5), 2),
                })
    df_v = pd.DataFrame(rows_v)
    df_v["created_at"] = now_ts
    df_v["updated_at"] = now_ts
    df_v.to_sql("kpi_delays_by_vehicle", con=engine, if_exists="append", index=False)
    print(f"Insertadas {len(df_v)} filas en kpi_delays_by_vehicle.")

    print("Listo. Recarga los paneles de Grafana (intervalo de tiempo: últimos 7 días).")


if __name__ == "__main__":
    main()
