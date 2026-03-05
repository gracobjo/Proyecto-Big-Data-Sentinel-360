#!/usr/bin/env python3
"""
Simulador realista de datos GPS para Sentinel360.

Genera posiciones de una flota de autobuses y las envía continuamente
al topic de Kafka `gps-events`, actuando como fuente de ingesta en tiempo real.
"""

import json
import time
import random
from datetime import datetime

from kafka import KafkaProducer


KAFKA_BOOTSTRAP_SERVERS = "nodo1:9092"
TOPIC = "gps-events"


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def main() -> None:
    producer = create_producer()

    vehicles = [f"BUS_{i:02d}" for i in range(1, 21)]
    routes = ["R1", "R2", "R3", "R4", "R5"]

    print(f"Enviando eventos GPS simulados a Kafka ({TOPIC})...")

    while True:
        vehicle = random.choice(vehicles)
        route = random.choice(routes)

        data = {
            "vehicle_id": vehicle,
            "route_id": route,
            "speed": random.randint(20, 60),
            "delay_minutes": round(random.uniform(0, 5), 2),
            "timestamp": datetime.utcnow().isoformat(),
        }

        producer.send(TOPIC, data)
        print(data)

        time.sleep(1)


if __name__ == "__main__":
    main()

