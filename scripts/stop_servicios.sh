#!/bin/bash
# Detiene los servicios arrancados por start_servicios.sh (Kafka, MongoDB, opcional History Server, NiFi).
# HDFS/YARN no se paran por defecto (clúster compartido). Usar STOP_HADOOP=1 para pararlos.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export KAFKA_HOME="${KAFKA_HOME:-/usr/local/kafka}"
export SPARK_HOME="${SPARK_HOME:-/usr/local/spark}"
export HADOOP_HOME="${HADOOP_HOME:-/usr/local/hadoop}"
export NIFI_HOME="${NIFI_HOME:-/usr/local/nifi}"

RED='\033[0;31m'
VERDE='\033[0;32m'
NC='\033[0m'
log_ok()   { echo -e "${VERDE}[OK]${NC} $1"; }
log_info() { echo "[*] $1"; }

echo "=== Deteniendo servicios ==="
echo ""

# Kafka
if pgrep -f "kafka.Kafka" >/dev/null 2>&1; then
  pkill -f "kafka.Kafka" 2>/dev/null || true
  sleep 2
  pgrep -f "kafka.Kafka" >/dev/null 2>&1 && log_info "Kafka: proceso aún activo (kill -9 si hace falta)" || log_ok "Kafka detenido"
else
  log_info "Kafka no estaba en marcha"
fi

# MongoDB (solo si lo arrancamos nosotros con nohup; systemctl no lo tocamos)
if pgrep -x mongod >/dev/null 2>&1; then
  log_info "MongoDB en ejecución. Parar con: sudo systemctl stop mongod  o  pkill mongod"
  # pkill mongod 2>/dev/null && log_ok "MongoDB detenido" || true
fi

# Spark History Server
if [ -x "$SPARK_HOME/sbin/stop-history-server.sh" ]; then
  "$SPARK_HOME/sbin/stop-history-server.sh" 2>/dev/null && log_ok "Spark History Server detenido" || true
fi

# NiFi
if [ -x "$NIFI_HOME/bin/nifi.sh" ]; then
  "$NIFI_HOME/bin/nifi.sh" stop 2>/dev/null && log_ok "NiFi detenido" || true
fi

# Hive (metastore + hiveserver2 si los arrancamos con start_servicios.sh)
if pgrep -f "HiveServer2" >/dev/null 2>&1; then
  pkill -f "HiveServer2" 2>/dev/null && sleep 1 && log_ok "HiveServer2 detenido" || true
fi
if pgrep -f "HiveMetaStore" >/dev/null 2>&1; then
  pkill -f "HiveMetaStore" 2>/dev/null && sleep 1 && log_ok "Hive Metastore detenido" || true
fi

# Hadoop (solo si se pide)
if [ "${STOP_HADOOP:-0}" = "1" ]; then
  [ -x "$HADOOP_HOME/sbin/stop-yarn.sh" ] && "$HADOOP_HOME/sbin/stop-yarn.sh" && log_ok "YARN detenido"
  [ -x "$HADOOP_HOME/sbin/stop-dfs.sh" ]  && "$HADOOP_HOME/sbin/stop-dfs.sh"  && log_ok "HDFS detenido"
else
  log_info "HDFS/YARN no se detienen (STOP_HADOOP=1 para pararlos)"
fi

echo ""
echo "Listo."
