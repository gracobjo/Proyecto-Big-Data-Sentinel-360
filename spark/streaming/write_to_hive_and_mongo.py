#!/usr/bin/env python3
"""
Fase III - Carga multicapa: agregados a Hive (Parquet). Estado por vehículo a MongoDB vía connector.
Refactorizado para clúster: YARN, HDFS y tabla Hive desde config.
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
    HDFS_AGGREGATED_DELAYS_PATH,
    HIVE_AGGREGATED_DELAYS_TABLE,
)

from pyspark.sql import SparkSession


def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-Load-Hive")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .enableHiveSupport()
        .getOrCreate()
    )


def main(aggregated_path: str = None, hive_table: str = None) -> None:
    aggregated_path = aggregated_path or HDFS_AGGREGATED_DELAYS_PATH
    hive_table = hive_table or HIVE_AGGREGATED_DELAYS_TABLE
    spark = get_spark_session()
    df = spark.read.parquet(aggregated_path)
    df.write.mode("append").insertInto(hive_table)
    print(f"Datos agregados cargados en {hive_table}")
    spark.stop()


if __name__ == "__main__":
    agg = sys.argv[1] if len(sys.argv) > 1 else None
    tbl = sys.argv[2] if len(sys.argv) > 2 else None
    main(agg, tbl)
