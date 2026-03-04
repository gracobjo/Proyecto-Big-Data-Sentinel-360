#!/usr/bin/env python3
"""Genera logs GPS simulados para pruebas (Fase I - ingesta)."""
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
WAREHOUSES = ["WH-MAD", "WH-BCN", "WH-VLC", "WH-BIL", "WH-SEV"]
N_ROWS = 500


def main():
    rows = []
    base_ts = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(N_ROWS):
        ts = base_ts + timedelta(minutes=i * 2, seconds=random.randint(0, 120))
        rows.append({
            "event_id": f"ev-{i:06d}",
            "vehicle_id": f"V-{random.randint(1, 50):03d}",
            "ts": ts.isoformat() + "Z",
            "lat": round(40.0 + random.uniform(-2, 2), 6),
            "lon": round(-3.5 + random.uniform(-1, 1), 6),
            "speed": round(random.uniform(0, 90), 2),
            "warehouse_id": random.choice(WAREHOUSES),
        })
    with open(OUT / "gps_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    with open(OUT / "gps_events.json", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Generados {N_ROWS} eventos en {OUT} (gps_events.csv, gps_events.json)")


if __name__ == "__main__":
    main()
