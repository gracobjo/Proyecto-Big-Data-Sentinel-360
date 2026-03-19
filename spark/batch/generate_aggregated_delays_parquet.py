#!/usr/bin/env python3
"""
Genera los agregados de retrasos (ventanas de 15 min por warehouse) en batch.

Motivo:
- La Fase III batch (load_aggregated) espera Parquet en:
  HDFS_AGGREGATED_DELAYS_PATH = /user/hadoop/proyecto/procesado/aggregated_delays
- En algunos reinicios/ejecuciones, esa carpeta puede quedar vacía.

Este job:
1) Lee raw gps events (HDFS_RAW_PATH/gps_events.csv).
2) Calcula una delay_min (prototipo: aleatoria, consistente con delays_windowed.py).
3) Agrupa en ventanas de 15 min por warehouse_id.
4) Escribe Parquet con columnas:
   window_start, window_end, warehouse_id, avg_delay_min, vehicle_count

Luego, los pasos de Airflow pueden:
- cargar Hive/Mongo desde Parquet (write_to_hive_and_mongo.py), y/o
- leer la tabla Hive para anomalías y KPIs.
"""

from __future__ import annotations

import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import (  # type: ignore
    HDFS_RAW_PATH,
    HDFS_AGGREGATED_DELAYS_PATH,
)


def get_spark_session() -> SparkSession:
    # Importante: NO usamos enableHiveSupport aquí para no depender del metastore
    # (la Fase III carga el Hive desde este Parquet más adelante).
    spark = SparkSession.builder.appName("GenerateAggregatedDelaysParquet").getOrCreate()
    return spark


def main() -> None:
    spark = get_spark_session()
    try:
        gps_csv = f"{HDFS_RAW_PATH}/gps_events.csv"
        events = (
            spark.read.option("header", "true")
            .csv(gps_csv)
            .select(
                F.col("event_id"),
                F.col("vehicle_id"),
                F.col("ts"),
                F.col("lat").cast("double").alias("lat"),
                F.col("lon").cast("double").alias("lon"),
                F.col("speed").cast("double").alias("speed"),
                F.col("warehouse_id"),
            )
        )

        # Los timestamps del CSV pueden venir con sufijo 'Z' tras el offset (+00:00Z).
        # Spark suele parsear ISO8601, pero limpiamos el 'Z' final por robustez.
        events = events.withColumn(
            "ts_clean",
            F.to_timestamp(F.regexp_replace(F.col("ts"), "Z$", "")),
        )

        events = events.drop("ts").withColumnRenamed("ts_clean", "ts")

        # Prototipo: generamos delay_min aleatoria (determinista por seed) como en streaming.
        events = events.withColumn("delay_min", (F.rand(42) * F.lit(30.0)).cast("double"))

        # Ventanas de 15 min (alineadas) por warehouse.
        windowed = (
            events.groupBy(F.window(F.col("ts"), "15 minutes", "15 minutes"), "warehouse_id")
            .agg(
                F.avg("delay_min").alias("avg_delay_min"),
                F.count("*").alias("vehicle_count"),
            )
        )

        aggregated = windowed.select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            F.col("warehouse_id"),
            F.col("avg_delay_min").alias("avg_delay_min"),
            F.col("vehicle_count").alias("vehicle_count"),
        )

        # Escribimos Parquet sobre la misma ubicación de la tabla Hive.
        aggregated.write.mode("overwrite").parquet(HDFS_AGGREGATED_DELAYS_PATH)
        print(f"Parquet agregados escritos en: {HDFS_AGGREGATED_DELAYS_PATH}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

