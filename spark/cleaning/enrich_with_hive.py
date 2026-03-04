#!/usr/bin/env python3
"""
Fase II - Enriquecimiento: cruzar datos limpios con datos maestros en Hive.
Refactorizado para clúster: YARN, HDFS, rutas desde config.
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
    HDFS_CLEANED_PATH,
    HDFS_ENRICHED_PATH,
    HIVE_WAREHOUSES_TABLE,
)

from pyspark.sql import SparkSession


def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-Enrich")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .enableHiveSupport()
        .getOrCreate()
    )


def main(cleaned_path: str = None, output_path: str = None) -> None:
    cleaned_path = cleaned_path or HDFS_CLEANED_PATH
    output_path = output_path or HDFS_ENRICHED_PATH
    spark = get_spark_session()
    events = spark.read.parquet(cleaned_path)
    warehouses = spark.table(HIVE_WAREHOUSES_TABLE)
    enriched = (
        events.join(warehouses, events.warehouse_id == warehouses.warehouse_id, "left")
        .select(
            events["*"],
            warehouses["name"].alias("warehouse_name"),
            warehouses["city"].alias("warehouse_city"),
        )
    )
    enriched.write.mode("overwrite").parquet(output_path)
    print(f"Enriquecimiento completado. Escrito en {output_path}")
    spark.stop()


if __name__ == "__main__":
    cleaned = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else None
    main(cleaned, out)
