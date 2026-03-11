#!/bin/bash
# Comprueba que la ingesta GPS (NiFi → HDFS, Kafka) ha funcionado.
# Uso: ./scripts/verificar_ingesta_gps.sh
# Ver también: ingest/FLUJO_GPS_README.md (sección "Comprobación de datos")

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

HDFS_RAW="/user/hadoop/proyecto/raw"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-192.168.99.10:9092}"

echo "=== Verificación ingesta GPS (NiFi → HDFS, Kafka) ==="
echo ""

# 1. HDFS raw
echo "1. HDFS raw ($HDFS_RAW):"
if hdfs dfs -test -d "$HDFS_RAW" 2>/dev/null; then
  COUNT=$(hdfs dfs -ls "$HDFS_RAW" 2>/dev/null | grep -v "^Found" | grep -c "^-" || true)
  if [ "${COUNT:-0}" -gt 0 ]; then
    echo "   [OK] $COUNT archivo(s) en raw"
    hdfs dfs -ls "$HDFS_RAW" 2>/dev/null | tail -5
  else
    echo "   [VACÍO] No hay archivos. Ejecuta el flujo NiFi y copia datos en /home/hadoop/data/gps_logs/"
  fi
else
  echo "   [FALTA] Directorio no existe. Ejecutar: ./scripts/setup_hdfs.sh"
fi
echo ""

# 2. Topics Kafka
echo "2. Topics Kafka ($KAFKA_BOOTSTRAP):"
for d in /home/hadoop/software/kafka_2.13-4.1.1 /usr/local/kafka /opt/kafka "$HOME/kafka"; do
  [ -d "$d" ] && [ -x "$d/bin/kafka-topics.sh" ] && export KAFKA_HOME="$d" && break
done
KAFKA_HOME="${KAFKA_HOME:-/home/hadoop/software/kafka_2.13-4.1.1}"

if [ -x "$KAFKA_HOME/bin/kafka-topics.sh" ]; then
  for topic in raw-data filtered-data; do
    if "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$KAFKA_BOOTSTRAP" --list 2>/dev/null | grep -qx "$topic"; then
      echo "   [OK] topic $topic"
    else
      echo "   [FALTA] topic $topic"
    fi
  done
else
  echo "   [SKIP] kafka-topics.sh no encontrado"
fi
echo ""

# 3. MongoDB (aviso: NiFi no escribe en MongoDB)
echo "3. MongoDB (aggregated_delays):"
echo "   NOTA: MongoDB se llena desde Spark streaming (delays_windowed.py), no desde NiFi."
echo "   Para comprobar: mongosh --eval \"db.getSiblingDB('transport').aggregated_delays.find().limit(5)\""
echo ""
echo "=== Fin verificación ==="
