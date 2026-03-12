#!/bin/bash
# Inserta datos de ejemplo en MariaDB del contenedor Docker sin conectar desde el host.
# Uso: ./scripts/seed_kpi_demo_via_docker.sh
# Requiere: tablas creadas (02_create_kpi_tables.sql).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

CONTAINER="${MARIADB_CONTAINER:-sentinel360-mariadb}"
USER="${MARIA_DB_USER:-sentinel}"
PASS="${MARIA_DB_PASSWORD:-sentinel_password}"
DB="${MARIA_DB_NAME:-sentinel360_analytics}"

echo "Comprobando tablas en $CONTAINER..."
if ! docker exec "$CONTAINER" mysql -u "$USER" -p"$PASS" "$DB" -e "SELECT 1 FROM kpi_delays_by_warehouse LIMIT 1" 2>/dev/null; then
  echo "Crea antes las tablas:"
  echo "  docker exec -i $CONTAINER mysql -u $USER -p$PASS $DB < docs/sql_entorno_visual/02_create_kpi_tables.sql"
  exit 1
fi

echo "Generando e insertando datos de ejemplo..."
python3 << 'PYEOF' | docker exec -i "$CONTAINER" mysql -u "$USER" -p"$PASS" "$DB"
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
warehouses = ["WH-MAD", "WH-BCN", "WH-VLC", "WH-BIL", "WH-SEV"]
for d in range(7):
    for h in range(0, 24, 3):
        window_start = now - timedelta(days=d, hours=h)
        window_end = window_start + timedelta(minutes=15)
        for i, wh in enumerate(warehouses):
            base_delay = 5.0 + (i * 3) + (d * 0.5)
            delay_avg = round(base_delay + (h % 5), 2)
            delay_max = round(base_delay * 2 + 5, 2)
            trips = 10 + (d * 2) + i
            delayed = 2 + d + i
            ws = window_start.strftime("%Y-%m-%d %H:%M:%S")
            we = window_end.strftime("%Y-%m-%d %H:%M:%S")
            print(f"INSERT INTO kpi_delays_by_warehouse (warehouse_id,window_start,window_end,trips_count,delayed_trips,avg_delay_minutes,max_delay_minutes) VALUES ('{wh}','{ws}','{we}',{trips},{delayed},{delay_avg},{delay_max});")
for d in range(3):
    for h in range(0, 24, 6):
        window_start = now - timedelta(days=d, hours=h)
        window_end = window_start + timedelta(minutes=15)
        for v in [f"V-{i:03d}" for i in range(1, 11)]:
            delay_avg = round(3.0 + (hash(v) % 10) / 2, 2)
            delay_max = round(8.0 + (hash(v) % 5), 2)
            ws = window_start.strftime("%Y-%m-%d %H:%M:%S")
            we = window_end.strftime("%Y-%m-%d %H:%M:%S")
            print(f"INSERT INTO kpi_delays_by_vehicle (vehicle_id,window_start,window_end,trips_count,delayed_trips,avg_delay_minutes,max_delay_minutes) VALUES ('{v}','{ws}','{we}',2,1,{delay_avg},{delay_max});")
PYEOF

echo "Listo. Recarga los paneles de Grafana (intervalo: últimos 7 días)."