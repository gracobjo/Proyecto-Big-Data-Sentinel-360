#!/usr/bin/env python3
"""
CU3 – Detección de anomalías en la flota (prototipo).

Lee los agregados de retrasos desde Hive (tabla HIVE_AGGREGATED_DELAYS_TABLE),
entrena un modelo sencillo de clustering (K-Means) con Spark ML y marca como
"anómalos" los registros que pertenecen al cluster con mayor retraso medio.

Los resultados se escriben en una colección MongoDB `transport.anomalies`.
"""

import os
import sys
from typing import List

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import (  # type: ignore
    HDFS_NAMENODE,
    SPARK_MASTER,
    HIVE_AGGREGATED_DELAYS_TABLE,
    MONGO_URI,
    MONGO_DB,
    KAFKA_BOOTSTRAP_SERVERS,
)

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.clustering import KMeans


def get_spark_session() -> SparkSession:
    return (
        SparkSession.builder.appName("Sentinel360-AnomalyDetection")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .enableHiveSupport()
        .getOrCreate()
    )


def load_aggregated_delays(spark: SparkSession) -> DataFrame:
    """
    Carga la tabla de agregados de retrasos desde Hive.
    Se espera un esquema similar a:
      window_start, window_end, warehouse_id, avg_delay_min, vehicle_count
    """
    df = spark.table(HIVE_AGGREGATED_DELAYS_TABLE)
    # Filtrar nulos básicos para evitar problemas en el modelo
    df = df.dropna(subset=["avg_delay_min", "vehicle_count"])
    return df


def train_kmeans(df: DataFrame, k: int = 3) -> DataFrame:
    """
    Entrena un K-Means sobre (avg_delay_min, vehicle_count) y devuelve
    el DataFrame con una columna extra `prediction` (cluster asignado)
    y `anomaly_flag` (True para el cluster con mayor retraso medio).
    """
    features_cols: List[str] = ["avg_delay_min", "vehicle_count"]
    assembler = VectorAssembler(inputCols=features_cols, outputCol="features")
    assembled = assembler.transform(df)

    kmeans = KMeans(k=k, seed=42, featuresCol="features", predictionCol="prediction")
    model = kmeans.fit(assembled)

    # Determinar qué cluster es el "más problemático":
    # el que tiene mayor avg_delay_min en su centroide.
    centers = model.clusterCenters()
    # Cada centroide es [avg_delay_min, vehicle_count]
    max_delay = -1.0
    anomaly_cluster = 0
    for idx, center in enumerate(centers):
        if center[0] > max_delay:
            max_delay = center[0]
            anomaly_cluster = idx

    print(f"Cluster considerado anómalo: {anomaly_cluster} (avg_delay_min centroide={max_delay:.2f})")

    scored = model.transform(assembled)
    scored = scored.withColumn(
        "anomaly_flag", F.col("prediction") == F.lit(anomaly_cluster)
    )
    return scored


def write_anomalies_to_mongo_and_kafka(df: DataFrame) -> None:
    """
    Escribe únicamente los registros marcados como anómalos en:
    - MongoDB, colección `transport.anomalies`.
    - Kafka, topic `alerts` (avisos para otros sistemas o demos).
    """
    anomalous = df.filter(F.col("anomaly_flag") == F.lit(True))
    if anomalous.rdd.isEmpty():
        print("No se han detectado anomalías según el criterio actual.")
        return

    rows = anomalous.select(
        "window_start",
        "window_end",
        "warehouse_id",
        "avg_delay_min",
        "vehicle_count",
        "prediction",
    ).collect()

    # Persistencia en MongoDB
    import pymongo  # import local para no forzar dependencia cuando no se usa

    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    coll = db["anomalies"]

    docs = []
    for row in rows:
        doc = {
            "window_start": row.window_start.isoformat()
            if hasattr(row.window_start, "isoformat")
            else str(row.window_start),
            "window_end": row.window_end.isoformat()
            if hasattr(row.window_end, "isoformat")
            else str(row.window_end),
            "warehouse_id": row.warehouse_id,
            "avg_delay_min": float(row.avg_delay_min),
            "vehicle_count": int(row.vehicle_count),
            "cluster": int(row.prediction),
            "anomaly_flag": True,
        }
        docs.append(doc)

    if docs:
        coll.insert_many(docs)
        print(f"Insertadas {len(docs)} anomalías en MongoDB (colección transport.anomalies).")

        # Enviar también alertas a Kafka (topic alerts)
        try:
            from kafka import KafkaProducer
            import json

            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )

            for doc in docs:
                alert = {
                    "type": "ANOMALY",
                    "warehouse_id": doc["warehouse_id"],
                    "window_start": doc["window_start"],
                    "window_end": doc["window_end"],
                    "avg_delay_min": doc["avg_delay_min"],
                    "vehicle_count": doc["vehicle_count"],
                    "cluster": doc["cluster"],
                    "timestamp": doc["window_end"],
                }
                producer.send("alerts", alert)

            producer.flush()
            producer.close()
            print(f"Enviadas {len(docs)} alertas a Kafka (topic alerts).")
        except Exception as exc:  # pragma: no cover - no queremos fallar por alerta
            print(f"No se pudieron enviar alertas a Kafka: {exc}")

    client.close()


def main() -> None:
    spark = get_spark_session()
    try:
        df = load_aggregated_delays(spark)
        if df.rdd.isEmpty():
            print("La tabla de agregados está vacía; no se puede entrenar el modelo de anomalías.")
            return

        scored = train_kmeans(df, k=3)
        write_anomalies_to_mongo_and_kafka(scored)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

