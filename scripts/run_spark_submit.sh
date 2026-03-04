#!/bin/bash
# Lanzar jobs Spark en modo distribuido (YARN, 2 ejecutores en nodo1/nodo2)
# Uso: ./scripts/run_spark_submit.sh <script.py> [arg1 [arg2 ...]]
# Ejemplo: ./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
# Requiere: SPARK_HOME y ejecutar desde la raíz de Sentinel360 (para --py-files config.py)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

SPARK_SCRIPT="$1"
if [ -z "$SPARK_SCRIPT" ]; then
  echo "Uso: $0 <script.py> [arg1 [arg2 ...]]"
  echo "Ejemplos:"
  echo "  $0 spark/cleaning/clean_and_normalize.py"
  echo "  $0 spark/graph/transport_graph.py"
  echo "  $0 spark/streaming/delays_windowed.py kafka"
  exit 1
fi
shift
EXTRA_ARGS=("$@")

# Ruta a Spark (ajustar si tu instalación está en otro sitio)
SPARK_HOME="${SPARK_HOME:-/usr/local/spark}"
export HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-/usr/local/hadoop/etc/hadoop}"

"${SPARK_HOME}/bin/spark-submit" \
  --master yarn \
  --deploy-mode client \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,graphframes:graphframes:0.8.3-spark3.5-s_2.12 \
  --num-executors 2 \
  --executor-cores 2 \
  --executor-memory 2G \
  --driver-memory 2G \
  --py-files "${PROJECT_ROOT}/config.py" \
  "$SPARK_SCRIPT" \
  "${EXTRA_ARGS[@]}"
