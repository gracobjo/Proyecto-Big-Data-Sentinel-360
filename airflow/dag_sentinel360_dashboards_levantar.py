"""
Dashboards – Levantar MariaDB, Superset y Grafana con Docker.

Requiere Docker en el nodo donde corre el worker. Puertos: MariaDB 3307, Superset 8089, Grafana 3000.
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"

DOCKER_DIR = f"{PROJECT_DIR}/docker"

with DAG(
    dag_id="sentinel360_dashboards_levantar",
    default_args={"owner": "sentinel360", "retries": 0},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "dashboards", "docker"],
    description="Levantar MariaDB, Superset y Grafana (Docker).",
) as dag:
    up_mariadb = BashOperator(
        task_id="docker_mariadb",
        bash_command=f"cd {DOCKER_DIR} && docker compose up -d mariadb",
    )
    up_superset = BashOperator(
        task_id="docker_superset",
        bash_command=f"cd {DOCKER_DIR} && docker compose up -d superset",
    )
    up_grafana = BashOperator(
        task_id="docker_grafana",
        bash_command=f"cd {DOCKER_DIR} && docker compose up -d grafana",
    )
    up_mariadb >> up_superset
    up_mariadb >> up_grafana
