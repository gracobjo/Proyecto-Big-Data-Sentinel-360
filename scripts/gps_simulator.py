#!/usr/bin/env python3
"""
Simulador realista de datos GPS para Sentinel360.

Genera posiciones de una flota de autobuses y las envía continuamente
al topic de Kafka configurado en config.py (por defecto gps-events).
"""

import json
import os
import sys
import time
import random
from datetime import datetime

# Asegurar que el proyecto está en el path para importar config
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_GPS_EVENTS  # type: ignore
from kafka import KafkaProducer


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def main() -> None:
    producer = create_producer()

    vehicles = [f"BUS_{i:02d}" for i in range(1, 20)]
    routes = ["R1", "R2", "R3"]

    # Zona Valladolid aproximada (lat/lon base)
    lat_base = 41.65
    lon_base = -4.72

    print(f"Enviando eventos GPS simulados a Kafka ({KAFKA_TOPIC_GPS_EVENTS}) con coordenadas reales aproximadas...")

    while True:
        data = {
            "vehicle_id": random.choice(vehicles),
            "route_id": random.choice(routes),
            "lat": lat_base + random.uniform(-0.01, 0.01),
            "lon": lon_base + random.uniform(-0.01, 0.01),
            "speed": random.randint(20, 60),
            "delay_minutes": round(random.uniform(0, 5), 2),
            "timestamp": datetime.utcnow().isoformat(),
        }

        producer.send(KAFKA_TOPIC_GPS_EVENTS, data)
        print(data)

        time.sleep(1)


if __name__ == "__main__":
    main()

