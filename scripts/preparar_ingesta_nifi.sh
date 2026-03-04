#!/bin/bash
# Prepara el entorno para la ingesta en NiFi: directorio GPS, datos de prueba y temas Kafka.
# Ejecutar desde la raíz de Sentinel360: ./scripts/preparar_ingesta_nifi.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

KAFKA_HOME="${KAFKA_HOME:-/home/hadoop/software/kafka_2.13-4.1.1}"
BOOTSTRAP="192.168.99.10:9092"
GPS_DIR="/home/hadoop/data/gps_logs"

echo "=== Preparando ingesta NiFi ==="
echo ""

# 1. Directorio que vigila el flujo GPS (GetFile)
mkdir -p "$GPS_DIR"
echo "[OK] Directorio: $GPS_DIR"

# 2. Generar datos de prueba y copiar al directorio de ingesta
if [ -f "data/sample/generate_gps_logs.py" ]; then
  python3 data/sample/generate_gps_logs.py
  cp -f data/sample/gps_events.csv data/sample/gps_events.json "$GPS_DIR/" 2>/dev/null || true
  echo "[OK] Datos GPS copiados a $GPS_DIR"
else
  echo "[?] No existe data/sample/generate_gps_logs.py; crea archivos .json/.csv en $GPS_DIR a mano"
fi

# 3. Temas Kafka (raw-data y filtered-data)
if [ -d "$KAFKA_HOME" ] && [ -x "$KAFKA_HOME/bin/kafka-topics.sh" ]; then
  for topic in raw-data filtered-data; do
    "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists --topic "$topic" --partitions 3 --replication-factor 1 2>/dev/null && echo "[OK] Tema Kafka: $topic" || echo "[?] Tema $topic (puede existir ya)"
  done
else
  echo "[?] Kafka no encontrado en $KAFKA_HOME; crea los temas a mano: raw-data, filtered-data"
fi

echo ""
echo "=== Siguiente: en la UI de NiFi ==="
echo "  1. Importar flujo: menú (icono +) → Import flow → elegir: ingest/gps_transport_flow_importable.json"
echo "  2. Habilitar Controller Service: en el grupo importado → Config (engranaje) → Controller Services → Kafka3ConnectionService → Enable"
echo "  3. Arrancar el proceso: en el grupo → Start"
echo "  4. (Opcional) GetFile usa $GPS_DIR; para usar data/sample de Sentinel360, edita GetFile → Input Directory"
echo ""
echo "  UI NiFi: https://localhost:8443/nifi"
echo "  Ver mensajes en Kafka: $KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server $BOOTSTRAP --topic filtered-data --from-beginning --max-messages 5"
