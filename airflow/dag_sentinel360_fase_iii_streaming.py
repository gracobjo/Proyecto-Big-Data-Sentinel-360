"""
Fase III KDD – Streaming: job de retrasos por ventana (delays_windowed.py).

Modo file o kafka según variable sentinel360_streaming_mode.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"

with DAG(
    dag_id="sentinel360_fase_iii_streaming",
    default_args={"owner": "sentinel360", "retries": 0, "retry_delay": timedelta(minutes=2)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-iii", "kdd-mineria", "streaming"],
    description="Fase III KDD: streaming de retrasos (delays_windowed). Modo file o kafka.",
) as dag:
    BashOperator(
        task_id="run_streaming",
        bash_command=f"cd {PROJECT_DIR} && ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {{{{ var.value.sentinel360_streaming_mode | default('file') }}}}",
    )
