#!/bin/bash
# Crea los temas Kafka del proyecto si no existen (raw-data, filtered-data, alerts).
# Uso: ./scripts/ensure_kafka_topics.sh
# Requiere: Kafka en marcha, KAFKA_HOME o Kafka en PATH.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS:-192.168.99.10:9092}"
if [ -z "$KAFKA_HOME" ] || [ ! -x "$KAFKA_HOME/bin/kafka-topics.sh" ]; then
  for d in /usr/local/kafka "$HOME/software/kafka_2.13-4.1.1" "$HOME/software/kafka_2."*; do
    [ -d "$d" ] && [ -x "$d/bin/kafka-topics.sh" ] && export KAFKA_HOME="$d" && break
  done
fi
[ -z "$KAFKA_HOME" ] && { echo "KAFKA_HOME no encontrado"; exit 1; }

for topic in raw-data filtered-data alerts; do
  "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists --topic "$topic" --partitions 3 --replication-factor 1 2>/dev/null && echo "[OK] Tema: $topic" || echo "[?] Tema $topic (puede existir ya)"
done
echo "Listo. Listar temas: $KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server $BOOTSTRAP --list"
