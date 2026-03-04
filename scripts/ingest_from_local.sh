#!/bin/bash
# Copiar datos locales a HDFS raw (clúster: 192.168.99.10)
# Uso: ./scripts/ingest_from_local.sh
# Requiere: hdfs en PATH (ej. /usr/local/hadoop/bin en PATH)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
USER="${HDFS_USER:-hadoop}"
RAW="${PROJECT_ROOT}/data/sample"
# Ruta HDFS del proyecto (NameNode configurado en core-site.xml)
HDFS_RAW="/user/${USER}/proyecto/raw"

if [ ! -d "$RAW" ]; then
  echo "No existe $RAW. Genera datos con: python data/sample/generate_gps_logs.py"
  exit 1
fi
HDFS_WH="/user/${USER}/proyecto/warehouses"
HDFS_ROUTES="/user/${USER}/proyecto/routes"
hdfs dfs -mkdir -p "$HDFS_RAW" "$HDFS_WH" "$HDFS_ROUTES"
# Raw: eventos GPS
hdfs dfs -put -f "$RAW"/*.csv "$HDFS_RAW/" 2>/dev/null || true
hdfs dfs -put -f "$RAW"/*.json "$HDFS_RAW/" 2>/dev/null || true
# Maestros: warehouses y routes (para GraphFrames y Hive)
[ -f "$RAW/warehouses.csv" ] && hdfs dfs -put -f "$RAW/warehouses.csv" "$HDFS_WH/"
[ -f "$RAW/routes.csv" ]     && hdfs dfs -put -f "$RAW/routes.csv" "$HDFS_ROUTES/"
echo "Datos copiados a $HDFS_RAW, $HDFS_WH, $HDFS_ROUTES"
hdfs dfs -ls "$HDFS_RAW"
