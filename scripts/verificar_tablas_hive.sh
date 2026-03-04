#!/bin/bash
# Comprueba si las tablas de la base Hive 'transport' tienen datos.
# Uso: ./scripts/verificar_tablas_hive.sh
# Requiere: HiveServer2 en marcha, beeline en PATH.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BEELINE_OPTS="-u jdbc:hive2://localhost:10000 -n hadoop"
echo "=== Comprobando tablas Hive (transport) ==="
echo ""

for tabla in warehouses routes events_raw aggregated_delays; do
  n=$(beeline $BEELINE_OPTS --silent=true --outputformat=tsv2 -e "USE transport; SELECT COUNT(*) FROM $tabla;" 2>/dev/null | tail -1)
  if [ -n "$n" ] && [ "$n" -eq "$n" ] 2>/dev/null; then
    echo "  $tabla: $n registros"
  else
    echo "  $tabla: (error o sin conexión)"
  fi
done

echo ""
echo "HDFS (datos que alimentan las tablas EXTERNAL):"
echo "  warehouses:  $(hdfs dfs -ls /user/hadoop/proyecto/warehouses/ 2>/dev/null | grep -c '^-' || echo 0) fichero(s)"
echo "  routes:      $(hdfs dfs -ls /user/hadoop/proyecto/routes/ 2>/dev/null | grep -c '^-' || echo 0) fichero(s)"
echo "  raw:         $(hdfs dfs -ls /user/hadoop/proyecto/raw/ 2>/dev/null | grep -c '^-' || echo 0) fichero(s)"
echo ""
echo "Para poblar warehouses y routes: ./scripts/ingest_from_local.sh"
echo "Para aggregated_delays: ejecutar job Spark write_to_hive_and_mongo.py (Fase III)"
