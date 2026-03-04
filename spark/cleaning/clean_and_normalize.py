#!/usr/bin/env python3
"""
Fase II - Preprocesamiento: limpieza con Spark SQL.
Normaliza formatos, gestiona nulos y elimina duplicados.
Refactorizado para clúster: YARN, HDFS en 192.168.99.10, rutas desde config.
"""
import sys
import os
# Incluir proyecto en path para importar config (o usar --py-files config.py)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import (
    HDFS_NAMENODE,
    SPARK_MASTER,
    HDFS_RAW_PATH,
    HDFS_CLEANED_PATH,
)

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-Cleaning")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .enableHiveSupport()
        .getOrCreate()
    )


def main(raw_path: str = None, output_path: str = None) -> None:
    raw_path = raw_path or HDFS_RAW_PATH
    output_path = output_path or HDFS_CLEANED_PATH
    spark = get_spark_session()
    df = spark.read.option("header", "true").option("inferSchema", "true").csv(raw_path)
    for c in df.columns:
        df = df.withColumnRenamed(c, c.lower().replace(" ", "_"))
    df = df.fillna(0.0, subset=["speed"]).fillna("UNKNOWN", subset=["warehouse_id"])
    df = (
        df.dropDuplicates(["event_id"])
        if "event_id" in df.columns
        else df.dropDuplicates(["vehicle_id", "ts"])
    )
    if "ts" in df.columns and "timestamp" not in str(df.schema["ts"].dataType):
        df = df.withColumn("ts", F.to_timestamp(F.col("ts")))
    df.write.mode("overwrite").parquet(output_path)
    print(f"Limpieza completada. Escrito en {output_path}")
    spark.stop()


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else None
    main(raw, out)
