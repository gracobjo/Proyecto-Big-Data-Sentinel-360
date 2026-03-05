"""
DAG principal de Sentinel360 (batch diario).

Objetivo:
- Ejecutar de forma orquestada el pipeline batch de Sentinel360:
  1) Limpieza de datos raw en HDFS.
  2) Enriquecimiento con maestros de Hive.
  3) Cálculo de grafo de transporte.
  4) Carga de agregados de retrasos en Hive.
  5) Detección batch de anomalías y registro en MongoDB + Kafka (topic alerts).
  6) Volcado de KPIs a MariaDB para dashboards (Superset).

Este DAG está pensado como referencia; los paths a los binarios de Spark, Python y
la ubicación del repositorio deben ajustarse al entorno real de despliegue.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


DEFAULT_ARGS = {
    "owner": "sentinel360",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Ruta al directorio del proyecto en el nodo donde corre Airflow
PROJECT_DIR = "/opt/sentinel360"  # AJUSTAR a la ruta real del repositorio

# Wrapper para ejecutar scripts usando el run_spark_submit.sh del proyecto
def spark_task(cmd: str) -> str:
    return f"cd {PROJECT_DIR} && ./scripts/run_spark_submit.sh {cmd}"


with DAG(
    dag_id="sentinel360_batch_pipeline",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",  # diario a las 02:00
    start_date=datetime(2026, 3, 1),
    catchup=False,
    description="Pipeline batch diario de Sentinel360 (limpieza, enriquecimiento, grafos, agregados, anomalías, KPIs).",
) as dag:

    # 1) Limpieza de datos raw
    clean_raw = BashOperator(
        task_id="clean_raw",
        bash_command=spark_task("spark/cleaning/clean_and_normalize.py"),
    )

    # 2) Enriquecimiento con maestros de Hive
    enrich_with_hive = BashOperator(
        task_id="enrich_with_hive",
        bash_command=spark_task("spark/cleaning/enrich_with_hive.py"),
    )

    # 3) Cálculo de grafo de transporte
    build_transport_graph = BashOperator(
        task_id="build_transport_graph",
        bash_command=spark_task("spark/graph/transport_graph.py"),
    )

    # 4) Carga batch de agregados de retrasos en Hive (si existen Parquet previos)
    load_aggregated_delays = BashOperator(
        task_id="load_aggregated_delays",
        bash_command=spark_task("spark/streaming/write_to_hive_and_mongo.py"),
    )

    # 5) Detección de anomalías (batch) y registro en MongoDB + Kafka alerts
    detect_anomalies_batch = BashOperator(
        task_id="detect_anomalies_batch",
        bash_command=f"cd {PROJECT_DIR} && ./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py",
    )

    # 6) Volcado de KPIs a MariaDB (para dashboards)
    load_kpis_to_mariadb = BashOperator(
        task_id="load_kpis_to_mariadb",
        bash_command=f"cd {PROJECT_DIR} && python3 scripts/mongo_to_mariadb_kpi.py --source mongo",
    )

    # Dependencias del DAG
    clean_raw >> enrich_with_hive >> build_transport_graph
    build_transport_graph >> load_aggregated_delays >> detect_anomalies_batch >> load_kpis_to_mariadb

