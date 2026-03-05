"""
DAG de monitorización streaming de Sentinel360.

Objetivo:
- Facilitar el arranque y parada controlada de los componentes clave de
  monitorización en tiempo casi real:
  1) Job de streaming de retrasos (delays_windowed.py) leyendo de Kafka.
  2) Consumidor de alertas desde el topic `alerts`.

Nota: En muchos despliegues, jobs de streaming se gestionan fuera de Airflow
(como servicios de sistema), pero este DAG puede servir como ejemplo para
integrar Sentinel360 en un entorno orquestado.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


DEFAULT_ARGS = {
    "owner": "sentinel360",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}

PROJECT_DIR = "/opt/sentinel360"  # AJUSTAR a la ruta real del repositorio


with DAG(
    dag_id="sentinel360_streaming_monitoring",
    default_args=DEFAULT_ARGS,
    schedule_interval=None,  # lanzamiento manual
    start_date=datetime(2026, 3, 1),
    catchup=False,
    description="Monitorización streaming: retrasos + alertas en tiempo casi real.",
) as dag:

    # Lanzar streaming de retrasos (Kafka)
    start_delays_streaming = BashOperator(
        task_id="start_delays_streaming",
        bash_command=f"cd {PROJECT_DIR} && ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka",
    )

    # Lanzar consumidor de alertas
    start_alerts_consumer = BashOperator(
        task_id="start_alerts_consumer",
        bash_command=f"cd {PROJECT_DIR} && python3 scripts/alerts_consumer.py",
    )

    # En este DAG, ambos procesos pueden lanzarse en paralelo
    start_delays_streaming >> start_alerts_consumer

