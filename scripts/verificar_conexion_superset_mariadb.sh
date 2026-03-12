#!/bin/bash
# Comprueba que Superset pueda conectar a MariaDB (misma red Docker).
# Uso: ./scripts/verificar_conexion_superset_mariadb.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

MARIADB_CONTAINER="${MARIADB_CONTAINER:-sentinel360-mariadb}"
SUPERSET_CONTAINER="${SUPERSET_CONTAINER:-sentinel360-superset}"
USER="${MARIA_DB_USER:-sentinel}"
PASS="${MARIA_DB_PASSWORD:-sentinel_password}"
DB="${MARIA_DB_NAME:-sentinel360_analytics}"

echo "1. Comprobando que MariaDB está en marcha..."
if ! docker exec "$MARIADB_CONTAINER" mysql -u root -proot_password -e "SELECT 1" &>/dev/null; then
  echo "   ERROR: MariaDB no responde. ¿Está levantado? docker compose up -d mariadb"
  exit 1
fi
echo "   OK"

echo "2. Asegurando usuario sentinel@'%' y base de datos..."
docker exec -i "$MARIADB_CONTAINER" mysql -u root -proot_password < docs/sql_entorno_visual/01_create_db_and_user.sql
echo "   OK"

echo "3. Probando conexión desde el contenedor de Superset (mariadb:3306)..."
docker exec "$SUPERSET_CONTAINER" /app/.venv/bin/python3 -c "
import sys
try:
    import pymysql
    c = pymysql.connect(host='mariadb', port=3306, user='$USER', password='$PASS', database='$DB')
    c.close()
    print('   OK: Conexión correcta desde Superset a MariaDB.')
except Exception as e:
    print('   ERROR:', e, file=sys.stderr)
    sys.exit(1)
" || { echo "   Si falla, revisa que el contenedor superset esté en la misma red que mariadb."; exit 1; }

echo ""
echo "Si este script termina bien, en Superset usa esta URI:"
echo "  mysql+pymysql://$USER:$PASS@mariadb:3306/$DB"
echo ""
