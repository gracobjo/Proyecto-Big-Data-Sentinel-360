"""
Fase I KDD – Ingesta: temas Kafka + datos sintéticos GPS + OpenWeather.

Orden: crear temas Kafka → en paralelo ingesta GPS sintética y OpenWeather.
Variable opcional openweather_api_key (Admin → Variables); si no existe, la tarea OpenWeather usa cadena vacía.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

try:
    from airflow.models import Variable
    PROJECT_DIR = Variable.get("sentinel360_project_dir", default_var="/home/hadoop/Documentos/ProyectoBigData")
    OPENWEATHER_API_KEY = Variable.get("openweather_api_key", default_var="")
except Exception:
    PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"
    OPENWEATHER_API_KEY = ""

from sentinel360_reporting import Sentinel360ReportConfig, write_dag_run_report  # type: ignore

with DAG(
    dag_id="sentinel360_fase_I_ingesta",
    default_args={"owner": "sentinel360", "retries": 1, "retry_delay": timedelta(minutes=2), "execution_timeout": timedelta(minutes=15)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-I", "kdd-ingesta"],
    description="Fase I KDD: Kafka topics + ingesta GPS sintética + OpenWeather.",
) as dag:
    kafka = BashOperator(
        task_id="ensure_kafka_topics",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/ensure_kafka_topics.sh ",
    )
    ingest_gps = BashOperator(
        task_id="ingest_gps_synthetic",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/setup_hdfs.sh && bash ./scripts/preparar_ingesta_nifi.sh ",
    )
    ingest_weather = BashOperator(
        task_id="ingest_openweather",
        # Si no hay API key, no tumbamos todo el DAG de Fase I:
        # dejamos evidencia y continuamos con la ingesta GPS.
        bash_command=(
            f"cd {PROJECT_DIR} && "
            "if [ -z \"$OPENWEATHER_API_KEY\" ]; then "
            "echo '[WARN] openweather_api_key no definida en Airflow Variables; se omite ingest_openweather.'; "
            "exit 0; "
            "fi; "
            "python3 scripts/ingest_openweather.py "
        ),
        env={"OPENWEATHER_API_KEY": OPENWEATHER_API_KEY},
    )
    kafka >> ingest_gps
    kafka >> ingest_weather

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        trigger_rule="all_done",
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    [ingest_gps, ingest_weather] >> report
