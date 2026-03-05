#!/bin/bash
# Crea la base Hive 'transport' y todas las tablas de Sentinel360 (01 a 05).
# Ejecutar desde la raíz del proyecto. Requiere: HiveServer2 y metastore en marcha, MariaDB para metastore.
# Uso: ./scripts/crear_tablas_hive.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BEELINE_OPTS="-u jdbc:hive2://localhost:10000 -n hadoop"

echo "=== Creando base y tablas Hive (transport) ==="
echo ""

for sql in hive/schema/01_warehouses.sql hive/schema/02_routes.sql hive/schema/03_events_raw.sql hive/schema/04_aggregated_reporting.sql hive/schema/05_reporte_diario.sql; do
  if [ ! -f "$sql" ]; then
    echo "[?] No encontrado: $sql"
    continue
  fi
  echo "  Ejecutando $sql ..."
  beeline $BEELINE_OPTS -f "$sql" --silent=true 2>/dev/null || beeline $BEELINE_OPTS -f "$sql"
  echo "  [OK] $sql"
done

echo ""
echo "Listo. Comprobar con:"
echo "  beeline $BEELINE_OPTS -e \"USE transport; SHOW TABLES;\""
echo "  ./scripts/verificar_tablas_hive.sh"
echo ""
echo "Poblar datos maestros (warehouses, routes, raw): ./scripts/ingest_from_local.sh"
