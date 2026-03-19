"""
Infra – Arrancar servicios del clúster Sentinel360.

Agrupa: HDFS, YARN, Kafka, MongoDB, MariaDB, Hive (metastore + hiveserver2), NiFi.
Equivalente a ./scripts/start_servicios.sh. Solo ejecución manual (Trigger DAG).

El script puede tardar 1–2 minutos. Se da entorno mínimo (HADOOP_HOME, etc.) por si
el worker de Airflow no hereda el shell de login.
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

# Entorno mínimo para que start_servicios.sh encuentre Hadoop, Kafka, etc. en el worker
COMMON_ENV = {
    "HADOOP_HOME": "/usr/local/hadoop",
    "HIVE_HOME": "/usr/local/hive",
    "SPARK_HOME": "/usr/local/spark",
}

with DAG(
    dag_id="sentinel360_infra_start",
    default_args={
        "owner": "sentinel360",
        "retries": 0,
        "execution_timeout": timedelta(minutes=15),
    },
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "infra", "kdd-0"],
    description="Arrancar todos los servicios del clúster (HDFS, YARN, Kafka, Hive, NiFi, etc.).",
) as dag:
    start_all_services = BashOperator(
        task_id="start_all_services",
        # Trailing space evita que Airflow 3 interprete el comando como ruta de plantilla Jinja
        # y SENTINEL360_SKIP_SUDO_STARTS evita sudo interactivo cuando Airflow ejecuta el worker.
        bash_command=(
            f"cd {PROJECT_DIR} && "
            "SENTINEL360_SKIP_SUDO_STARTS=1 "
            "bash ./scripts/start_servicios.sh "
        ),
        env=COMMON_ENV,
    )

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    start_all_services >> report
