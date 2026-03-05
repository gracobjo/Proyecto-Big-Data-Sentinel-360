#!/usr/bin/env python3
"""
Script de ejemplo para poblar las tablas de KPIs en MariaDB a partir de:
- La colección MongoDB `transport.aggregated_delays`, o
- Ficheros Parquet generados por Spark (carpeta resultados/).

Pensado como referencia para la demo del máster: puedes ejecutarlo de forma
standalone o integrarlo en un DAG de Airflow.
"""

import os
from datetime import datetime
from typing import Iterable, Dict, Any

from pymongo import MongoClient
import pandas as pd
import sqlalchemy
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# Configuración (ajusta estos valores a tu entorno)
# ---------------------------------------------------------------------------

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "transport")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "aggregated_delays")

MARIA_DB_URI = os.getenv(
    "MARIA_DB_URI",
    "mysql+pymysql://sentinel:sentinel_password@localhost:3306/sentinel360_analytics",
)

# Si prefieres leer de Parquet en lugar de Mongo, ajusta esta ruta:
PARQUET_DIR = os.getenv("PARQUET_DIR", "resultados")


def get_mongo_client() -> MongoClient:
    return MongoClient(MONGO_URI)


def get_sql_engine() -> Engine:
    return sqlalchemy.create_engine(MARIA_DB_URI)


def fetch_from_mongo() -> pd.DataFrame:
    """
    Ejemplo de lectura desde MongoDB. Se asume una estructura aproximada
    en `aggregated_delays` con campos:
      - vehicle_id
      - warehouse_id (opcional)
      - window_start, window_end
      - trips_count, delayed_trips, avg_delay_minutes, max_delay_minutes
    """
    client = get_mongo_client()
    coll = client[MONGO_DB][MONGO_COLLECTION]

    cursor: Iterable[Dict[str, Any]] = coll.find({})
    docs = list(cursor)
    if not docs:
        print("No se encontraron documentos en MongoDB; devuelve DataFrame vacío.")
        return pd.DataFrame()

    df = pd.DataFrame(docs)

    # Normalizar campos de fecha (por si vienen como cadenas)
    for col in ("window_start", "window_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    return df


def fetch_from_parquet() -> pd.DataFrame:
    """
    Ejemplo de lectura desde ficheros Parquet locales en PARQUET_DIR.
    Se espera que los ficheros tengan la misma estructura de columnas
    que la descrita en `fetch_from_mongo`.
    """
    if not os.path.isdir(PARQUET_DIR):
        print(f"No existe la carpeta {PARQUET_DIR}, devuelve DataFrame vacío.")
        return pd.DataFrame()

    parquets = [os.path.join(PARQUET_DIR, f) for f in os.listdir(PARQUET_DIR) if f.endswith(".parquet")]
    if not parquets:
        print(f"No hay ficheros .parquet en {PARQUET_DIR}, devuelve DataFrame vacío.")
        return pd.DataFrame()

    dfs = []
    for path in parquets:
        try:
            df_part = pd.read_parquet(path)
            dfs.append(df_part)
        except Exception as exc:
            print(f"Error leyendo {path}: {exc}")

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    for col in ("window_start", "window_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def build_kpi_by_vehicle(df: pd.DataFrame) -> pd.DataFrame:
    """
    A partir del DataFrame "crudo" (Mongo/Parquet), construye las métricas
    agregadas a nivel (vehicle_id, window_start, window_end).
    """
    required_cols = ["vehicle_id", "window_start", "window_end", "delay_minutes"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para KPIs por vehículo: {missing}")

    # Ejemplo de agregaciones: cuenta de viajes, viajes con retraso,
    # promedio y máximo de retraso en minutos.
    grouped = (
        df.groupby(["vehicle_id", "window_start", "window_end"])
        .agg(
            trips_count=("vehicle_id", "count"),
            delayed_trips=("delay_minutes", lambda s: (s > 0).sum()),
            avg_delay_minutes=("delay_minutes", "mean"),
            max_delay_minutes=("delay_minutes", "max"),
        )
        .reset_index()
    )

    # Opcional: redondear métricas
    grouped["avg_delay_minutes"] = grouped["avg_delay_minutes"].round(2)
    grouped["max_delay_minutes"] = grouped["max_delay_minutes"].round(2)

    return grouped


def build_kpi_by_warehouse(df: pd.DataFrame) -> pd.DataFrame:
    """
    KPIs a nivel (warehouse_id, window_start, window_end).
    """
    required_cols = ["warehouse_id", "window_start", "window_end", "delay_minutes"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para KPIs por almacén: {missing}")

    grouped = (
        df.groupby(["warehouse_id", "window_start", "window_end"])
        .agg(
            trips_count=("warehouse_id", "count"),
            delayed_trips=("delay_minutes", lambda s: (s > 0).sum()),
            avg_delay_minutes=("delay_minutes", "mean"),
            max_delay_minutes=("delay_minutes", "max"),
        )
        .reset_index()
    )

    grouped["avg_delay_minutes"] = grouped["avg_delay_minutes"].round(2)
    grouped["max_delay_minutes"] = grouped["max_delay_minutes"].round(2)

    return grouped


def load_to_mariadb(df_vehicle: pd.DataFrame, df_warehouse: pd.DataFrame) -> None:
    """
    Carga (modo "append") los DataFrames de KPIs en las tablas de MariaDB.
    Se asume que las tablas ya existen (ver docs/sql_entorno_visual/02_create_kpi_tables.sql).
    """
    engine = get_sql_engine()

    now = datetime.utcnow()
    for df, table in [
        (df_vehicle, "kpi_delays_by_vehicle"),
        (df_warehouse, "kpi_delays_by_warehouse"),
    ]:
        if df.empty:
            print(f"DataFrame vacío, no se inserta nada en {table}.")
            continue

        # Añadir timestamps si quieres registrar cuándo se cargaron los datos
        if "created_at" not in df.columns:
            df["created_at"] = now
        if "updated_at" not in df.columns:
            df["updated_at"] = now

        df.to_sql(table, con=engine, if_exists="append", index=False)
        print(f"Insertadas {len(df)} filas en {table}.")


def main(source: str = "mongo") -> None:
    """
    Ejecuta el pipeline de ejemplo:
      1) Leer datos crudos de MongoDB o Parquet.
      2) Construir KPIs por vehículo y almacén.
      3) Insertar en MariaDB.
    """
    if source == "mongo":
        df_raw = fetch_from_mongo()
    elif source == "parquet":
        df_raw = fetch_from_parquet()
    else:
        raise ValueError("source debe ser 'mongo' o 'parquet'")

    if df_raw.empty:
        print("No hay datos de entrada; termina sin cargar en MariaDB.")
        return

    df_vehicle = build_kpi_by_vehicle(df_raw)
    df_warehouse = build_kpi_by_warehouse(df_raw)

    load_to_mariadb(df_vehicle, df_warehouse)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Poblar tablas de KPIs en MariaDB desde MongoDB o Parquet."
    )
    parser.add_argument(
        "--source",
        choices=["mongo", "parquet"],
        default="mongo",
        help="Fuente de datos para la carga (por defecto: mongo).",
    )
    args = parser.parse_args()

    main(source=args.source)

