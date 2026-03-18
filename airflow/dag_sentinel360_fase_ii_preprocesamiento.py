"""
Fase II KDD – Preprocesamiento: Hive + limpieza + enriquecimiento + grafo.

Orden: setup HDFS y tablas Hive → limpieza → enriquecimiento con Hive → grafo de transporte.
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
    dag_id="sentinel360_fase_ii_preprocesamiento",
    default_args={"owner": "sentinel360", "retries": 1, "retry_delay": timedelta(minutes=5)},
    schedule=None,
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sentinel360", "fase-ii", "kdd-preprocesamiento"],
    description="Fase II KDD: Hive setup, limpieza, enriquecimiento y grafo de transporte.",
) as dag:
    hive_setup = BashOperator(
        task_id="hive_setup",
        bash_command=f"cd {PROJECT_DIR} && bash ./scripts/setup_hdfs.sh && bash ./scripts/crear_tablas_hive.sh",
    )
    clean = BashOperator(task_id="clean", bash_command=spark("spark/cleaning/clean_and_normalize.py"))
    enrich = BashOperator(task_id="enrich", bash_command=spark("spark/cleaning/enrich_with_hive.py"))
    graph = BashOperator(task_id="graph", bash_command=spark("spark/graph/transport_graph.py"))
    hive_setup >> clean >> enrich >> graph

    report = PythonOperator(
        task_id="reporte_ejecucion",
        python_callable=write_dag_run_report,
        trigger_rule="all_done",
        op_kwargs={"config": Sentinel360ReportConfig(project_dir=PROJECT_DIR)},
    )

    graph >> report
