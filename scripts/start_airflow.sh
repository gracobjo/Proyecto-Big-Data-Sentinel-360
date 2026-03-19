#!/bin/bash
# Arranca Apache Airflow (scheduler + webserver) para Sentinel360.
# Requiere Airflow instalado (p. ej. venv en mi_proyecto_airflow o pip install apache-airflow).
# Uso: ./scripts/start_airflow.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT/logs"

# AIRFLOW_HOME: por defecto ~/airflow (donde suele estar airflow.cfg y airflow.db)
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"

# Ruta al ejecutable airflow (venv del otro proyecto o PATH)
if [ -x "/home/hadoop/mi_proyecto_airflow/venv_airflow/bin/airflow" ]; then
  export PATH="/home/hadoop/mi_proyecto_airflow/venv_airflow/bin:$PATH"
elif ! command -v airflow >/dev/null 2>&1; then
  echo "No se encontró 'airflow'. Instala con: pip install apache-airflow"
  echo "O activa el venv donde tengas Airflow y vuelve a ejecutar este script."
  exit 1
fi

echo "=== Airflow (AIRFLOW_HOME=$AIRFLOW_HOME) ==="

# Dag processor (Airflow 3: parsea los DAGs y los registra en la BD; sin esto la UI muestra "0 Dags")
if pgrep -f "airflow dag.processor\|airflow dag_processor" >/dev/null 2>&1; then
  echo "[OK] Dag processor ya en marcha"
else
  nohup airflow dag-processor -l "$PROJECT_ROOT/logs/airflow-dag-processor.log" >> "$PROJECT_ROOT/logs/airflow-dag-processor.log" 2>&1 &
  sleep 2
  pgrep -f "airflow dag" >/dev/null && echo "[OK] Dag processor arrancado" || echo "[?] Dag processor no arrancó"
fi

# Scheduler
if pgrep -f "airflow scheduler" >/dev/null 2>&1; then
  echo "[OK] Scheduler ya en marcha"
else
  nohup airflow scheduler >> "$PROJECT_ROOT/logs/airflow-scheduler.log" 2>&1 &
  sleep 2
  pgrep -f "airflow scheduler" >/dev/null && echo "[OK] Scheduler arrancado" || echo "[?] Scheduler no arrancó (ver logs/airflow-scheduler.log)"
fi

# API server / UI (Airflow 3.x usa api-server en lugar de webserver; puerto 8080; si está ocupado por YARN, usar 8081)
AIRFLOW_PORT="${AIRFLOW_PORT:-8080}"
if pgrep -f "airflow api" >/dev/null 2>&1; then
  echo "[OK] API server ya en marcha (http://localhost:$AIRFLOW_PORT)"
else
  nohup airflow api-server -p "$AIRFLOW_PORT" >> "$PROJECT_ROOT/logs/airflow-webserver.log" 2>&1 &
  sleep 4
  pgrep -f "airflow api" >/dev/null && echo "[OK] API server arrancado en http://localhost:$AIRFLOW_PORT" || \
    echo "[?] API server no arrancó. Puerto $AIRFLOW_PORT ocupado? Probar: AIRFLOW_PORT=8081 $0"
fi

echo ""
echo "UI: http://localhost:$AIRFLOW_PORT  (o http://192.168.99.10:$AIRFLOW_PORT)"
echo "DAGs: si no ves los 8 DAGs, ejecuta una vez: airflow dag-processor -n 2"
