#!/usr/bin/env bash
# Configura Airflow para usar todos los DAGs de Sentinel360.
# Opción 1 (recomendada): apuntar dags_folder al proyecto (Airflow lee siempre desde el repo).
# Opción 2: copiar los DAGs a \$AIRFLOW_HOME/dags.
#
# Uso: bash ./scripts/setup_airflow_dags.sh [--copy]
#   Sin argumentos: actualiza airflow.cfg para dags_folder = <proyecto>/airflow
#   --copy: copia los .py del proyecto a \$AIRFLOW_HOME/dags (no modifica airflow.cfg)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AIRFLOW_DAGS_SOURCE="$PROJECT_ROOT/airflow"
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"
AIRFLOW_CFG="$AIRFLOW_HOME/airflow.cfg"
TARGET_DAGS="$AIRFLOW_HOME/dags"

USE_COPY=false
if [[ "${1:-}" == "--copy" ]]; then
  USE_COPY=true
fi

echo "=== DAGs Sentinel360 ==="
echo "Proyecto: $PROJECT_ROOT"
echo "AIRFLOW_HOME: $AIRFLOW_HOME"
echo "Origen DAGs: $AIRFLOW_DAGS_SOURCE"
echo ""

if [[ "$USE_COPY" == true ]]; then
  mkdir -p "$TARGET_DAGS"
  echo "Copiando DAGs a $TARGET_DAGS ..."
  for f in "$AIRFLOW_DAGS_SOURCE"/dag_sentinel360_*.py; do
    [[ -f "$f" ]] || continue
    cp "$f" "$TARGET_DAGS/"
    echo "  - $(basename "$f")"
  done
  echo ""
  echo "Listo. Reinicia el scheduler si estaba en marcha: pkill -f 'airflow scheduler'; airflow scheduler &"
  exit 0
fi

# Apuntar dags_folder al proyecto
if [[ ! -f "$AIRFLOW_CFG" ]]; then
  echo "No se encontró $AIRFLOW_CFG. Ejecuta antes: airflow db init"
  exit 1
fi

# Actualizar dags_folder en airflow.cfg (evitar duplicados y comentarios)
if grep -q "^dags_folder" "$AIRFLOW_CFG"; then
  sed -i "s|^dags_folder = .*|dags_folder = $AIRFLOW_DAGS_SOURCE|" "$AIRFLOW_CFG"
else
  echo "dags_folder = $AIRFLOW_DAGS_SOURCE" >> "$AIRFLOW_CFG"
fi

echo "Configurado: dags_folder = $AIRFLOW_DAGS_SOURCE"
echo ""
echo "DAGs que cargará Airflow:"
for f in "$AIRFLOW_DAGS_SOURCE"/dag_sentinel360_*.py; do
  [[ -f "$f" ]] && echo "  - $(basename "$f")"
done
echo ""
echo "Reinicia scheduler (y api-server) para que cargue los DAGs:"
echo "  pkill -f 'airflow scheduler'; pkill -f 'airflow api'"
echo "  cd $PROJECT_ROOT && bash ./scripts/start_airflow.sh"
echo ""
echo "Orden sugerido al ejecutar: start_services → kafka_topics → hive_setup → ingest_gps_synthetic / ingest_openweather → spark_batch (y opcional spark_streaming, docker_dashboards, dashboards_data)."
