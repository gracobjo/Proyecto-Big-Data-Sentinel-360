#!/usr/bin/env python3
"""
Fase III - Structured Streaming: media de retrasos en ventanas de 15 minutos.
Entrada: Kafka (raw-data) o directorio HDFS. Salida: consola + Hive (aggregated_delays) + MongoDB (opcional).
Refactorizado para clúster: Kafka bootstrap, rutas y tablas desde config.
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
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RAW,
    HDFS_RAW_PATH,
    STREAMING_CHECKPOINT_PATH,
    HIVE_AGGREGATED_DELAYS_TABLE,
    MONGO_URI,
    MONGO_DB,
    MONGO_AGGREGATED_COLLECTION,
)

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType


def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-Delays-Streaming")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .enableHiveSupport()
        .getOrCreate()
    )


def write_batch_to_hive_and_mongo(batch_df, batch_id):
    """Escribe el micro-batch en Hive (transport.aggregated_delays) y opcionalmente en MongoDB."""
    if batch_df.isEmpty():
        return
    print(f"[batch {batch_id}] Escribiendo agregados en Hive y MongoDB...")
    # Hive: append a la tabla (esquema: window_start, window_end, warehouse_id, avg_delay_min, vehicle_count)
    batch_df.write.mode("append").insertInto(HIVE_AGGREGATED_DELAYS_TABLE)
    # MongoDB (opcional): insertar documentos en transport.aggregated_delays
    try:
        import pymongo
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        coll = db[MONGO_AGGREGATED_COLLECTION]
        rows = batch_df.collect()
        docs = []
        for row in rows:
            docs.append({
                "window_start": row.window_start.isoformat() if hasattr(row.window_start, "isoformat") else str(row.window_start),
                "window_end": row.window_end.isoformat() if hasattr(row.window_end, "isoformat") else str(row.window_end),
                "warehouse_id": row.warehouse_id,
                "avg_delay_min": float(row.avg_delay_min),
                "vehicle_count": int(row.vehicle_count),
            })
        if docs:
            coll.insert_many(docs)
        client.close()
    except Exception as e:
        # MongoDB no disponible o pymongo no instalado: no fallar el streaming
        pass


def main(source: str = "file", input_path: str = None, checkpoint: str = None) -> None:
    input_path = input_path or HDFS_RAW_PATH
    checkpoint = checkpoint or STREAMING_CHECKPOINT_PATH
    spark = get_spark_session()
    if source == "kafka":
        df = (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
            .option("subscribe", KAFKA_TOPIC_RAW)
            .load()
        )
        events = (
            df.select(
                F.from_json(
                    F.col("value").cast("string"),
                    "event_id string, vehicle_id string, ts string, lat double, lon double, speed double, warehouse_id string",
                ).alias("data")
            )
            .select("data.*")
        )
        events = events.withColumn("ts", F.to_timestamp("ts"))
    else:
        events = (
            spark.readStream.schema(
                "event_id string, vehicle_id string, ts timestamp, lat double, lon double, speed double, warehouse_id string"
            )
            .option("header", "true")
            .csv(input_path)
        )
    events = events.withColumn("delay_min", (F.rand() * 30).cast(DoubleType()))
    windowed = (
        events.withWatermark("ts", "10 minutes")
        .groupBy(F.window("ts", "15 minutes", "15 minutes"), "warehouse_id")
        .agg(
            F.avg("delay_min").alias("avg_delay_min"),
            F.count("*").alias("vehicle_count"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "warehouse_id",
            "avg_delay_min",
            "vehicle_count",
        )
    )
    q = (
        windowed.writeStream
        .outputMode("append")
        .option("checkpointLocation", checkpoint)
        .foreachBatch(write_batch_to_hive_and_mongo)
        .start()
    )
    q.awaitTermination()


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "file"
    inp = sys.argv[2] if len(sys.argv) > 2 else None
    cp = sys.argv[3] if len(sys.argv) > 3 else None
    main(src, inp, cp)
