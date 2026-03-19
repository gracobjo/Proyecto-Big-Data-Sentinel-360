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
    raw_path = (raw_path or HDFS_RAW_PATH).rstrip("/")
    output_path = output_path or HDFS_CLEANED_PATH
    spark = get_spark_session()

    # Leer solo datos de eventos GPS: primero gps_events*.csv; si no hay, *.json (evita mezclar routes/warehouses y JSON como CSV)
    df = None
    try:
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(f"{raw_path}/gps_events*.csv")
        if df.rdd.isEmpty():
            df = None
    except Exception:
        df = None
    if df is None:
        try:
            df = spark.read.json(f"{raw_path}/gps_events*.json")
        except Exception:
            df = spark.read.json(f"{raw_path}/*.json")
    if df.rdd.isEmpty():
        raise ValueError(
            f"No se encontraron datos de eventos en {raw_path}. "
            "Añade gps_events.csv o gps_events.json en raw."
        )

    for c in df.columns:
        df = df.withColumnRenamed(c, c.lower().replace(" ", "_"))
    # Normalizar nombres típicos de fuentes GPS (timestamp→ts, latitude→lat, longitude→lon)
    if "timestamp" in df.columns and "ts" not in df.columns:
        df = df.withColumnRenamed("timestamp", "ts")
    if "latitude" in df.columns and "lat" not in df.columns:
        df = df.withColumnRenamed("latitude", "lat")
    if "longitude" in df.columns and "lon" not in df.columns:
        df = df.withColumnRenamed("longitude", "lon")
    # Campos obligatorios (R4): eliminar registros con nulos en vehicle_id, ts, lat, lon
    required_obligatory = ["vehicle_id", "ts", "lat", "lon"]
    for col_name in required_obligatory:
        if col_name not in df.columns:
            raise ValueError(
                f"El dataset no tiene la columna obligatoria '{col_name}'. "
                f"Columnas encontradas: {df.columns}."
            )
    before_dropna = df.count()
    df = df.dropna(subset=required_obligatory)
    dropped_nulls = before_dropna - df.count()
    if dropped_nulls > 0:
        print(f"[Limpieza] Descartados {dropped_nulls} registros con vehicle_id, ts, lat o lon nulos.")

    # Columnas opcionales para velocidad y warehouse
    if "speed" not in df.columns:
        df = df.withColumn("speed", F.lit(0.0))
    if "warehouse_id" not in df.columns:
        df = df.withColumn("warehouse_id", F.lit("UNKNOWN"))
    df = df.fillna(0.0, subset=["speed"]).fillna("UNKNOWN", subset=["warehouse_id"])

    # R4: descartar registros con velocidad < 0 o > 300 km/h y registrar en log
    invalid_speed = (F.col("speed") < 0) | (F.col("speed") > 300)
    discarded_speed = df.filter(invalid_speed)
    n_discarded_speed = discarded_speed.count()
    if n_discarded_speed > 0:
        print(f"[Limpieza] Descartados {n_discarded_speed} registros con velocidad < 0 o > 300 km/h.")
        try:
            sample = discarded_speed.limit(5)
            for row in sample.collect():
                print(f"  Ejemplo descartado: vehicle_id={row.vehicle_id}, ts={row.ts}, speed={row.speed}")
        except Exception:
            pass
    df = df.filter(~invalid_speed)

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
