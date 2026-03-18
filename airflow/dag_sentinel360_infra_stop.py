"""
Infra – Parar servicios del clúster Sentinel360.

Equivalente a ./scripts/stop_servicios.sh. Solo ejecución manual (Trigger DAG).
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"

from sentinel360_reporting import Sentinel360ReportConfig, write_dag_run_report  # type: ignore

with DAG(
    dag_id="sentinel360_infra_stop",
    default_args={"owner": "sentinel360", "retries": 0},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "infra", "kdd-0"],
    description="Parar todos los servicios del clúster.",
) as dag:
    stop_all_services = BashOperator(
        task_id="stop_all_services",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/stop_servicios.sh",
    )

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        trigger_rule="all_done",
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    stop_all_services >> report
