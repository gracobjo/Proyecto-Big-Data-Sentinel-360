#!/usr/bin/env python3
"""
Consumidor sencillo del topic Kafka `alerts` para la demo.

Muestra por consola las alertas generadas por:
- El job de anomalías batch (spark/ml/anomaly_detection.py).
- El streaming de retrasos (spark/streaming/delays_windowed.py) cuando se
  superan ciertos umbrales de retraso medio.

La configuración (broker y tema) se lee desde config.py.
"""

import json
import os
import sys

# Asegurar que el proyecto está en el path para importar config
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_ALERTS  # type: ignore
from kafka import KafkaConsumer


def main() -> None:
    consumer = KafkaConsumer(
        KAFKA_TOPIC_ALERTS,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="sentinel360-alerts-demo",
    )

    print(f"Escuchando alertas en topic '{KAFKA_TOPIC_ALERTS}'...\n")
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

