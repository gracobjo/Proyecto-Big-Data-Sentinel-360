"""
Dashboards – Exportar datos a Superset/Grafana: MongoDB (KPIs + anomalías) + Hive.

Tareas (en paralelo):
  1) MongoDB → MariaDB: aggregated_delays → kpi_delays_by_vehicle/warehouse; anomalies → kpi_anomalies.
  2) Hive → MariaDB: aggregated_delays y reporte_diario_retrasos → kpi_hive_aggregated_delays, kpi_hive_reporte_diario.
Requisito: MariaDB en marcha y tablas KPI creadas (02_create_kpi_tables.sql).
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
    dag_id="sentinel360_dashboards_exportar",
    default_args={"owner": "sentinel360", "retries": 1, "retry_delay": timedelta(minutes=3)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "dashboards", "export"],
    description="Exportar MongoDB y Hive a MariaDB para Superset y Grafana.",
) as dag:
    export_mongo = BashOperator(
        task_id="export_mongo_to_mariadb",
        bash_command=f"cd {PROJECT_DIR} && python3 scripts/mongo_to_mariadb_kpi.py --source mongo --export-anomalies",
    )
    export_hive = BashOperator(
        task_id="export_hive_to_mariadb",
        bash_command=f"cd {PROJECT_DIR} && python3 scripts/export_hive_to_mariadb.py --dias 7",
    )
