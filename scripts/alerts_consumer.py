#!/usr/bin/env python3
"""
Consumidor sencillo del topic Kafka `alerts` para la demo.

Muestra por consola las alertas generadas por:
- El job de anomalías batch (spark/ml/anomaly_detection.py).
- El streaming de retrasos (spark/streaming/delays_windowed.py) cuando se
  superan ciertos umbrales de retraso medio.
"""

import json
from kafka import KafkaConsumer

from config import KAFKA_BOOTSTRAP_SERVERS  # type: ignore


def main() -> None:
    consumer = KafkaConsumer(
        "alerts",
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="sentinel360-alerts-demo",
    )

    print("Escuchando alertas en topic 'alerts'...\n")
    try:
        for msg in consumer:
            alert = msg.value
            print(f"[ALERTA] {alert}")
    except KeyboardInterrupt:
        print("\nParando consumer de alertas.")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()

