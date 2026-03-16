"""
Fase I KDD – Ingesta: temas Kafka + datos sintéticos GPS + OpenWeather.

Orden: crear temas Kafka → en paralelo ingesta GPS sintética y OpenWeather.
Requiere variable openweather_api_key para la tarea de OpenWeather.
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
    dag_id="sentinel360_fase_i_ingesta",
    default_args={"owner": "sentinel360", "retries": 1, "retry_delay": timedelta(minutes=2)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-i", "kdd-ingesta"],
    description="Fase I KDD: Kafka topics + ingesta GPS sintética + OpenWeather.",
) as dag:
    kafka = BashOperator(
        task_id="ensure_kafka_topics",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/ensure_kafka_topics.sh",
    )
    ingest_gps = BashOperator(
        task_id="ingest_gps_synthetic",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/setup_hdfs.sh && bash ./scripts/preparar_ingesta_nifi.sh",
    )
    ingest_weather = BashOperator(
        task_id="ingest_openweather",
        bash_command=f'cd {PROJECT_DIR} && export OPENWEATHER_API_KEY="{{{{ var.value.openweather_api_key }}}}" && python3 scripts/ingest_openweather.py',
    )
    kafka >> ingest_gps
    kafka >> ingest_weather
