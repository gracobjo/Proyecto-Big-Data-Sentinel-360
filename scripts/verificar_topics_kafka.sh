#!/bin/bash
# Comprueba que los dos topics de Sentinel360 (raw-data, filtered-data) existen en Kafka.
# Uso: ./scripts/verificar_topics_kafka.sh   (ejecutar desde la raíz del proyecto)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BOOTSTRAP="${KAFKA_BOOTSTRAP:-192.168.99.10:9092}"

# Kafka instalado (prioridad: variable, luego rutas habituales)
if [ -z "$KAFKA_HOME" ] || [ ! -x "$KAFKA_HOME/bin/kafka-topics.sh" ]; then
  for d in /home/hadoop/software/kafka_2.13-4.1.1 /usr/local/kafka /opt/kafka "$HOME/kafka"; do
    [ -d "$d" ] && [ -x "$d/bin/kafka-topics.sh" ] && export KAFKA_HOME="$d" && break
  done
fi
export KAFKA_HOME="${KAFKA_HOME:-/home/hadoop/software/kafka_2.13-4.1.1}"

if [ ! -x "$KAFKA_HOME/bin/kafka-topics.sh" ]; then
  echo "No se encontró kafka-topics.sh en KAFKA_HOME=$KAFKA_HOME"
  echo "Exporta KAFKA_HOME o instala Kafka en una de las rutas habituales."
  exit 1
fi

echo "=== Topics de Sentinel360 (broker $BOOTSTRAP) ==="
echo ""

for topic in raw-data filtered-data; do
  if "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --list 2>/dev/null | grep -qx "$topic"; then
    echo "[OK] $topic"
  else
    echo "[FALTA] $topic  (crear con: ./scripts/preparar_ingesta_nifi.sh)"
  fi
done

echo ""
echo "Listado completo de temas en el broker:"
"$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --list 2>/dev/null || echo "No se pudo conectar al broker."
