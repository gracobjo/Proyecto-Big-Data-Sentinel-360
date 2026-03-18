"""
Fase III KDD – Batch: agregados Hive/MongoDB + anomalías + KPIs a MariaDB.

Orden: cargar agregados → detección de anomalías → exportar KPIs a MariaDB.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"

from sentinel360_reporting import Sentinel360ReportConfig, write_dag_run_report  # type: ignore

def spark(script: str) -> str:
    return f"cd {PROJECT_DIR} && ./scripts/run_spark_submit.sh {script}"

with DAG(
    dag_id="sentinel360_fase_iii_batch",
    default_args={"owner": "sentinel360", "retries": 1, "retry_delay": timedelta(minutes=5)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-iii", "kdd-mineria"],
    description="Fase III KDD (batch): agregados, anomalías y KPIs a MariaDB.",
) as dag:
    load_agg = BashOperator(
        task_id="load_aggregated",
        bash_command=spark("spark/streaming/write_to_hive_and_mongo.py"),
    )
    anomalies = BashOperator(
        task_id="anomalies",
        bash_command=spark("spark/ml/anomaly_detection.py"),
    )
    kpis = BashOperator(
        task_id="kpis_mariadb",
        bash_command=f"cd {PROJECT_DIR} && python3 scripts/mongo_to_mariadb_kpi.py --source mongo --export-anomalies",
    )
    load_agg >> anomalies >> kpis

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        trigger_rule="all_done",
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    kpis >> report
