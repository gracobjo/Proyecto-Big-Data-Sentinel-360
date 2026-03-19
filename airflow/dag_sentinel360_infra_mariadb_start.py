"""
Infra – Arrancar solo MariaDB/MySQL y esperar al puerto 3306.

Soluciona el fallo "Puerto 3306 no respondió" del DAG sentinel360_infra_start.
Ejecutar este DAG primero; cuando termine en verde, lanzar sentinel360_infra_start
para que Hive Metastore pueda arrancar.

Prueba XAMPP (/opt/lampp/lampp startmysql) y systemd (mariadb/mysql).
Requisito: sudo sin contraseña para lampp o systemctl si Airflow corre como otro usuario.
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
    dag_id="sentinel360_infra_mariadb_start",
    default_args={
        "owner": "sentinel360",
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(minutes=2),
    },
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "infra", "mariadb", "kdd-0"],
    description="Arrancar MariaDB/MySQL (XAMPP o systemd) y esperar puerto 3306 para Hive Metastore.",
) as dag:
    BashOperator(
        task_id="start_mariadb_and_wait",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/start_mariadb.sh ",
    )
