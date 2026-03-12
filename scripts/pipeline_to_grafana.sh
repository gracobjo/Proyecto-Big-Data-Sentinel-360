#!/bin/bash
# Lleva los datos del pipeline (MongoDB aggregated_delays) a MariaDB para que
# Grafana muestre KPIs reales. Ejecutar desde la raíz del proyecto.
#
# Requisitos:
#  - MongoDB con datos en transport.aggregated_delays (p. ej. tras delays_windowed.py)
#  - MariaDB Docker levantado (puerto 3307 en host)
#  - Tablas KPI creadas en MariaDB (02_create_kpi_tables.sql)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# MariaDB en Docker: desde el host usamos 127.0.0.1:3307 (docker-compose mapea 3307:3306)
export MARIA_DB_HOST="${MARIA_DB_HOST:-127.0.0.1}"
export MARIA_DB_PORT="${MARIA_DB_PORT:-3307}"
export MARIA_DB_USER="${MARIA_DB_USER:-sentinel}"
export MARIA_DB_PASSWORD="${MARIA_DB_PASSWORD:-sentinel_password}"
export MARIA_DB_NAME="${MARIA_DB_NAME:-sentinel360_analytics}"
# MongoDB (clúster o local)
export MONGO_URI="${MONGO_URI:-mongodb://192.168.99.10:27017}"
export MONGO_DB="${MONGO_DB:-transport}"

echo "=== Pipeline → Grafana (MongoDB → MariaDB) ==="
echo "  MariaDB: $MARIA_DB_HOST:$MARIA_DB_PORT"
echo "  MongoDB: $MONGO_URI"
echo ""

# Comprobar que las tablas existen en MariaDB
if ! python3 -c "
import os
import sqlalchemy
from sqlalchemy import text
uri = os.environ.get('MARIA_DB_URI') or f\"mysql+pymysql://{os.environ['MARIA_DB_USER']}:{os.environ['MARIA_DB_PASSWORD']}@{os.environ['MARIA_DB_HOST']}:{os.environ['MARIA_DB_PORT']}/{os.environ['MARIA_DB_NAME']}\"
engine = sqlalchemy.create_engine(uri)
with engine.connect() as c:
    r = c.execute(text(\"SELECT 1 FROM information_schema.tables WHERE table_schema='sentinel360_analytics' AND table_name='kpi_delays_by_warehouse' LIMIT 1\"))
    if not r.fetchone():
        raise SystemExit('Tablas no encontradas. Crea antes: docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql')
" 2>/dev/null; then
  echo "Crea las tablas en MariaDB:"
  echo "  docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql"
  exit 1
fi

echo "Cargando KPIs desde MongoDB a MariaDB..."
pip install -q pymysql sqlalchemy pandas 2>/dev/null || true
python3 scripts/mongo_to_mariadb_kpi.py --source mongo

echo ""
echo "Listo. Los paneles de Grafana (últimos 30 días) deberían mostrar datos del pipeline."
echo "Si Grafana sigue en 'No data', reinicia Grafana y comprueba el datasource:"
echo "  docker compose -f docker/docker-compose.yml restart grafana"
echo "  Grafana → Configuration → Data sources → Sentinel360 MariaDB → Save & test"