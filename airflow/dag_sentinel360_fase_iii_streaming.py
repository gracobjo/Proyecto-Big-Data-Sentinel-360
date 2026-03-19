"""
Fase III KDD – Streaming: job de retrasos por ventana (delays_windowed.py).

Modo file o kafka según variable sentinel360_streaming_mode.
Variable sentinel360_spark_use_local=true (por defecto): Spark en modo local (sin YARN).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
    SPARK_USE_LOCAL = Variable.get("sentinel360_spark_use_local", default_var="true").lower() in ("true", "1", "yes")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"
    SPARK_USE_LOCAL = True

# --local evita conexión a YARN (ResourceManager 8032); usar cuando YARN no esté en marcha
# Importante: los scripts fuerzan .master(SPARK_MASTER), así que pasamos SPARK_MASTER=local[*] cuando usamos local.
SPARK_MASTER_VALUE = "local[*]" if SPARK_USE_LOCAL else "yarn"
SPARK_CMD_PREFIX = (
    f"cd {PROJECT_DIR} && "
    f'SPARK_MASTER="{SPARK_MASTER_VALUE}" && '
    f"./scripts/run_spark_submit.sh {'--local ' if SPARK_USE_LOCAL else ''}"
)

from sentinel360_reporting import Sentinel360ReportConfig, write_dag_run_report  # type: ignore

with DAG(
    dag_id="sentinel360_fase_iii_streaming",
    default_args={"owner": "sentinel360", "retries": 0, "retry_delay": timedelta(minutes=2), "execution_timeout": timedelta(minutes=30)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-iii", "kdd-mineria", "streaming"],
    description="Fase III KDD: streaming de retrasos (delays_windowed). Modo file o kafka.",
) as dag:
    run_streaming = BashOperator(
        task_id="run_streaming",
        bash_command=f"{SPARK_CMD_PREFIX}spark/streaming/delays_windowed.py {{{{ var.value.sentinel360_streaming_mode | default('file') }}}} ",
    )

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        trigger_rule="all_done",
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    run_streaming >> report
