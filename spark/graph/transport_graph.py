#!/usr/bin/env python3
"""
Fase II - Análisis de grafos con GraphFrames (distribuido en YARN).
Nodos: Almacenes. Aristas: Rutas. Camino más corto y componentes conectados.
Ejecutar con scripts/run_spark_submit.sh para incluir packages GraphFrames + Kafka.
"""
import sys
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import (
    HDFS_NAMENODE,
    SPARK_MASTER,
    HDFS_ROUTES_PATH,
    HDFS_WAREHOUSES_PATH,
    HDFS_GRAPH_PATH,
)

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-GraphFrames")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .getOrCreate()
    )


def main(routes_path: str = None, warehouses_path: str = None, output_path: str = None) -> None:
    routes_path = routes_path or HDFS_ROUTES_PATH
    warehouses_path = warehouses_path or HDFS_WAREHOUSES_PATH
    output_path = output_path or HDFS_GRAPH_PATH
    spark = get_spark_session()
    try:
        from graphframes import GraphFrame
    except ImportError:
        print("Ejecuta con: --packages graphframes:graphframes:0.8.3-spark3.5-s_2.12")
        spark.stop()
        sys.exit(1)
    vertices = (
        spark.read.option("header", "true")
        .csv(warehouses_path)
        .select(F.col("warehouse_id").alias("id"), F.lit("warehouse").alias("type"))
    )
    edges = (
        spark.read.option("header", "true")
        .csv(routes_path)
        .select(
            F.col("from_warehouse_id").alias("src"),
            F.col("to_warehouse_id").alias("dst"),
            F.col("distance_km").alias("weight"),
        )
    )
    g = GraphFrame(vertices, edges)
    paths = g.shortestPaths(landmarks=["WH-MAD", "WH-BCN"])
    paths.write.mode("overwrite").parquet(output_path + "/shortest_paths")
    cc = g.connectedComponents()
    cc.write.mode("overwrite").parquet(output_path + "/connected_components")
    print(f"Grafos escritos en {output_path}")
    spark.stop()


if __name__ == "__main__":
    routes = sys.argv[1] if len(sys.argv) > 1 else None
    wh = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else None
    main(routes, wh, out)
