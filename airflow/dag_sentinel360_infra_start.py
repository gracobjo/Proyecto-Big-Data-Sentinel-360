"""
Infra – Arrancar servicios del clúster Sentinel360.

Agrupa: HDFS, YARN, Kafka, MongoDB, MariaDB, Hive (metastore + hiveserver2), NiFi.
Equivalente a ./scripts/start_servicios.sh. Solo ejecución manual (Trigger DAG).
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
    dag_id="sentinel360_infra_start",
    default_args={"owner": "sentinel360", "retries": 0},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "infra", "kdd-0"],
    description="Arrancar todos los servicios del clúster (HDFS, YARN, Kafka, Hive, NiFi, etc.).",
) as dag:
    BashOperator(
        task_id="start_all_services",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/start_servicios.sh",
    )
