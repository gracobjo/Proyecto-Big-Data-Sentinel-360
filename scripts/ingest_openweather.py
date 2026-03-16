#!/usr/bin/env python3
"""
Ingesta única de OpenWeather API hacia Kafka (topic raw-data) y/o fichero local.

Uso:
  OPENWEATHER_API_KEY=tu_key python3 scripts/ingest_openweather.py
  OPENWEATHER_API_KEY=tu_key python3 scripts/ingest_openweather.py --no-kafka   # solo escribe a data/ingest/weather/

Equivalente funcional al flujo NiFi InvokeHTTP + PublishKafka (OpenWeather).
Pensado para ejecución desde Airflow o cron.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Ruta del proyecto (script en scripts/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_api_key():
    key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not key:
        print("OPENWEATHER_API_KEY no definida. Exporta la variable o configúrala en Airflow.", file=sys.stderr)
        sys.exit(1)
    return key


def fetch_weather(api_key: str, lat: float = 40.42, lon: float = -3.70) -> dict:
    url = (
        f"https://api.openweathermap.org/data/2.5/weather?"
        f"lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )
    req = Request(url, headers={"User-Agent": "Sentinel360-Ingest/1.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    data["_ingested_at"] = datetime.now(timezone.utc).isoformat()
    return data


def send_to_kafka(payload: dict, bootstrap: str, topic: str) -> bool:
    try:
        from kafka import KafkaProducer
    except ImportError:
        return False
    try:
        prod = KafkaProducer(bootstrap_servers=bootstrap, value_serializer=lambda v: json.dumps(v).encode("utf-8"))
        prod.send(topic, value=payload)
        prod.flush()
        prod.close()
        return True
    except Exception as e:
        print(f"Kafka: {e}", file=sys.stderr)
        return False


def write_to_file(payload: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"weather_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Ingesta OpenWeather API → Kafka y/o fichero")
    parser.add_argument("--no-kafka", action="store_true", help="Solo escribir a data/ingest/weather/, no enviar a Kafka")
    parser.add_argument("--lat", type=float, default=40.42, help="Latitud (default Madrid)")
    parser.add_argument("--lon", type=float, default=-3.70, help="Longitud (default Madrid)")
    args = parser.parse_args()

    api_key = get_api_key()
    payload = fetch_weather(api_key, args.lat, args.lon)

    # Siempre guardar copia local
    out_dir = PROJECT_ROOT / "data" / "ingest" / "weather"
    path = write_to_file(payload, out_dir)
    print(f"Guardado: {path}")

    if not args.no_kafka:
        try:
            import config
            bootstrap = getattr(config, "KAFKA_BOOTSTRAP_SERVERS", "192.168.99.10:9092")
            topic = getattr(config, "KAFKA_TOPIC_RAW", "raw-data")
        except ImportError:
            bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "192.168.99.10:9092")
            topic = os.environ.get("KAFKA_TOPIC_RAW", "raw-data")
        if send_to_kafka(payload, bootstrap, topic):
            print(f"Enviado a Kafka: {topic}")
        else:
            print("No se pudo enviar a Kafka (kafka-python no instalado o broker no disponible).", file=sys.stderr)


if __name__ == "__main__":
    main()
