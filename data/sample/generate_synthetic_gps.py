import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


def load_master_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    warehouses_path = DATA_SAMPLE_DIR / "warehouses.csv"
    routes_path = DATA_SAMPLE_DIR / "routes.csv"

    wh_df = pd.read_csv(warehouses_path)
    routes_df = pd.read_csv(routes_path)

    # Solo usamos rutas con ids de almacén válidos
    routes_df = routes_df.dropna(subset=["from_warehouse_id", "to_warehouse_id"]).copy()
    routes_df["from_warehouse_id"] = routes_df["from_warehouse_id"].astype(str)
    routes_df["to_warehouse_id"] = routes_df["to_warehouse_id"].astype(str)
    routes_df = routes_df[
        routes_df["from_warehouse_id"].str.startswith("WH-")
        & routes_df["to_warehouse_id"].str.startswith("WH-")
    ]
    return wh_df, routes_df


def interpolate_points(
    lat_from: float,
    lon_from: float,
    lat_to: float,
    lon_to: float,
    steps: int,
) -> list[tuple[float, float]]:
    """Interpolación lineal muy sencilla entre dos puntos."""
    lats = np.linspace(lat_from, lat_to, steps)
    lons = np.linspace(lon_from, lon_to, steps)
    return list(zip(lats, lons))


def generate_trip_events(
    route_row: pd.Series,
    wh_df: pd.DataFrame,
    base_start: datetime,
    direction: str = "forward",
    vehicle_id: str | None = None,
    points_per_trip: int = 12,
) -> list[dict]:
    """
    Genera eventos GPS sintéticos para una ruta concreta.

    - Un evento cada ~15 min (points_per_trip * 15 min = duración aproximada).
    - Añadimos algo de ruido a la posición y a los tiempos para simular retrasos.
    """
    if vehicle_id is None:
        vehicle_id = f"V-{route_row['route_id']}-{direction}"

    if direction == "forward":
        from_id = route_row["from_warehouse_id"]
        to_id = route_row["to_warehouse_id"]
    else:
        from_id = route_row["to_warehouse_id"]
        to_id = route_row["from_warehouse_id"]

    wh_from = wh_df[wh_df["warehouse_id"] == from_id].iloc[0]
    wh_to = wh_df[wh_df["warehouse_id"] == to_id].iloc[0]

    lat_from, lon_from = float(wh_from["lat"]), float(wh_from["lon"])
    lat_to, lon_to = float(wh_to["lat"]), float(wh_to["lon"])

    # Duración teórica en minutos y distancia km
    base_duration_min = float(route_row.get("avg_duration_min", 180) or 180)
    distance_km = float(route_row.get("distance_km", 300) or 300)

    # Ajustamos el número de puntos a algo coherente con la duración
    approx_points = max(6, min(24, int(base_duration_min // 15)))
    steps = approx_points if approx_points > 0 else points_per_trip

    path_points = interpolate_points(lat_from, lon_from, lat_to, lon_to, steps)

    # Pequeño retraso aleatorio (puede ser negativo o positivo)
    delay_total_min = random.gauss(mu=10.0, sigma=15.0)

    # Velocidad media aproximada
    avg_speed_kmh = distance_km / (base_duration_min / 60.0) if base_duration_min > 0 else 70.0

    events: list[dict] = []
    for i, (lat, lon) in enumerate(path_points):
        # Tiempo base
        ts = base_start + timedelta(minutes=15 * i)

        # Distribuimos el retraso a lo largo del trayecto
        delay_fraction = (i / max(1, steps - 1))
        delay_here = delay_total_min * delay_fraction
        ts_effective = ts + timedelta(minutes=delay_here)

        # Ruido pequeño en posición
        lat_noise = lat + random.uniform(-0.03, 0.03)
        lon_noise = lon + random.uniform(-0.03, 0.03)

        events.append(
            {
                "event_id": f"{route_row['route_id']}-{direction}-{i}",
                "vehicle_id": vehicle_id,
                "ts": ts_effective.isoformat(timespec="seconds"),
                "lat": round(lat_noise, 6),
                "lon": round(lon_noise, 6),
                "speed_kmh": round(random.gauss(avg_speed_kmh, 10.0), 1),
                "warehouse_id": from_id if i == 0 else (to_id if i == steps - 1 else ""),
                "route_id": route_row["route_id"],
                "delay_minutes": round(delay_here, 1),
            }
        )

    return events


def main() -> None:
    wh_df, routes_df = load_master_data()

    # Nos centramos en rutas entre capitales y capital-secundarios principales
    selected_routes = routes_df.copy()

    base_start = datetime(2025, 5, 1, 8, 0, 0)
    all_events: list[dict] = []

    for idx, row in selected_routes.iterrows():
        # Limitamos el número total de rutas para no generar millones de eventos
        if idx >= 80:
            break

        # Ida
        all_events.extend(
            generate_trip_events(
                row,
                wh_df,
                base_start=base_start + timedelta(minutes=idx * 5),
                direction="forward",
            )
        )
        # Vuelta
        all_events.extend(
            generate_trip_events(
                row,
                wh_df,
                base_start=base_start + timedelta(minutes=idx * 5 + 60),
                direction="backward",
            )
        )

    gps_df = pd.DataFrame(all_events)

    csv_path = DATA_SAMPLE_DIR / "gps_events.csv"
    json_path = DATA_SAMPLE_DIR / "gps_events.json"

    gps_df.to_csv(csv_path, index=False)
    gps_df.to_json(json_path, orient="records", lines=True)

    print(f"Generados {len(gps_df)} eventos GPS.")
    print(f"- CSV:  {csv_path}")
    print(f"- JSON: {json_path}")


if __name__ == "__main__":
    main()

