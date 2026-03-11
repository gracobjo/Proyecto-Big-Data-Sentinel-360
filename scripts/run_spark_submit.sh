#!/bin/bash
# Lanzar jobs Spark en modo distribuido (YARN) o local.
# Uso: ./scripts/run_spark_submit.sh [--local] <script.py> [arg1 [arg2 ...]]
#
# Opciones:
#   --local, -l   Ejecutar en modo local (sin YARN). Usar cuando los nodos fallan
#                 (p. ej. "No space left on device", AM container exitCode -1000).
#                 Todo corre en la máquina actual; no requiere contenedores en workers.
#
# Sin --local: YARN (2 ejecutores por defecto). Para 1 ejecutor: NUM_EXECUTORS=1 $0 ...
# Requiere: SPARK_HOME y ejecutar desde la raíz de Sentinel360 (para --py-files config.py)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

USE_LOCAL=""
while [ -n "$1" ]; do
  case "$1" in
    --local|-l) USE_LOCAL=1; shift ;;
    *) break ;;
  esac
done

SPARK_SCRIPT="$1"
if [ -z "$SPARK_SCRIPT" ]; then
  echo "Uso: $0 [--local] <script.py> [arg1 [arg2 ...]]"
  echo "Ejemplos:"
  echo "  $0 spark/cleaning/clean_and_normalize.py"
  echo "  $0 --local spark/cleaning/enrich_with_hive.py   # si YARN falla en nodos (disco lleno)"
  echo "  $0 spark/streaming/delays_windowed.py kafka"
  exit 1
fi
shift
EXTRA_ARGS=("$@")

# Ruta a Spark (ajustar si tu instalación está en otro sitio)
SPARK_HOME="${SPARK_HOME:-/usr/local/spark}"
export HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-/usr/local/hadoop/etc/hadoop}"

# PySpark exige la misma versión menor de Python en driver y workers (evitar PYTHON_VERSION_MISMATCH).
# En YARN los workers usan el Python del sistema (p. ej. 3.12); si el driver usa 3.13, falla.
# Fijar ambos a la misma: por defecto python3.12 (habitual en workers). Sobrescribir con env si hace falta.
if [ -z "$PYSPARK_PYTHON" ] || [ -z "$PYSPARK_DRIVER_PYTHON" ]; then
  for py in python3.12 python3.11 python3; do
    if command -v "$py" >/dev/null 2>&1; then
      export PYSPARK_PYTHON="${PYSPARK_PYTHON:-$py}"
      export PYSPARK_DRIVER_PYTHON="${PYSPARK_DRIVER_PYTHON:-$py}"
      break
    fi
  done
fi

# Jobs con enableHiveSupport() (p. ej. enrich_with_hive.py) necesitan el driver JDBC de MySQL/MariaDB
# en el classpath; si no, fallan con "com.mysql.cj.jdbc.Driver was not found in the CLASSPATH".
HIVE_HOME="${HIVE_HOME:-/usr/local/hive}"
EXTRA_JARS=""
for jar in "$HIVE_HOME/lib/mysql-connector-j-"*.jar "$HIVE_HOME/lib/mysql-connector-java-"*.jar "$HIVE_HOME/lib/mariadb-java-client-"*.jar; do
  [ -f "$jar" ] && EXTRA_JARS="$jar" && break
done
[ -n "$EXTRA_JARS" ] && SPARK_JARS="--jars $EXTRA_JARS" || SPARK_JARS=""

# Modo local: sin YARN, todo en la máquina actual (evita fallos por disco lleno en nodos).
if [ -n "$USE_LOCAL" ]; then
  echo "[run_spark_submit] Modo local (--local): sin YARN, ejecución en esta máquina."
  "${SPARK_HOME}/bin/spark-submit" \
    --master "local[*]" \
    $SPARK_JARS \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,graphframes:graphframes:0.8.3-spark3.5-s_2.12 \
    --driver-memory 2G \
    --py-files "${PROJECT_ROOT}/config.py" \
    "$SPARK_SCRIPT" \
    "${EXTRA_ARGS[@]}"
  exit $?
fi

# Modo YARN. Si los workers fallan (p. ej. "No space left"), usar NUM_EXECUTORS=1 o --local.
NUM_EXECUTORS="${NUM_EXECUTORS:-2}"

"${SPARK_HOME}/bin/spark-submit" \
  --master yarn \
  --deploy-mode client \
  $SPARK_JARS \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,graphframes:graphframes:0.8.3-spark3.5-s_2.12 \
  --num-executors "$NUM_EXECUTORS" \
  --executor-cores 2 \
  --executor-memory 2G \
  --driver-memory 2G \
  --py-files "${PROJECT_ROOT}/config.py" \
  "$SPARK_SCRIPT" \
  "${EXTRA_ARGS[@]}"
