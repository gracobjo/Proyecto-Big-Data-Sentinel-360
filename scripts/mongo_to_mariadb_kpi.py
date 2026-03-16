#!/usr/bin/env python3
"""
Script de ejemplo para poblar las tablas de KPIs en MariaDB a partir de:
- La colección MongoDB `transport.aggregated_delays`, o
- Ficheros Parquet generados por Spark (carpeta resultados/).

Pensado como referencia para la demo del máster: puedes ejecutarlo de forma
standalone o integrarlo en un DAG de Airflow.

La configuración de MongoDB y MariaDB se lee desde config.py (variables
MONGO_URI, MONGO_DB, MONGO_AGGREGATED_COLLECTION, MARIA_DB_URI).
Las variables de entorno del mismo nombre sobrescriben las de config si se desea.
"""

import os
import sys
from datetime import datetime
from typing import Iterable, Dict, Any

# Asegurar que el proyecto está en el path para importar config
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from config import (
        MONGO_URI,
        MONGO_DB,
        MONGO_AGGREGATED_COLLECTION,
        MONGO_ANOMALIES_COLLECTION,
        MARIA_DB_URI,
    )
except ImportError:
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.environ.get("MONGO_DB", "transport")
    MONGO_AGGREGATED_COLLECTION = os.environ.get("MONGO_COLLECTION", "aggregated_delays")
    MONGO_ANOMALIES_COLLECTION = os.environ.get("MONGO_ANOMALIES_COLLECTION", "anomalies")
    MARIA_DB_URI = os.environ.get(
        "MARIA_DB_URI",
        "mysql+pymysql://sentinel:sentinel_password@localhost:3306/sentinel360_analytics",
    )

# Si prefieres leer de Parquet en lugar de Mongo, ajusta esta ruta:
PARQUET_DIR = os.environ.get("PARQUET_DIR", os.path.join(_project_root, "resultados"))

from pymongo import MongoClient
import pandas as pd
import sqlalchemy
from sqlalchemy.engine import Engine


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
    coll = client[MONGO_DB][MONGO_AGGREGATED_COLLECTION]

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


def fetch_anomalies_from_mongo() -> pd.DataFrame:
    """Lee la colección MongoDB transport.anomalies (salida de anomaly_detection.py)."""
    client = get_mongo_client()
    coll = client[MONGO_DB][MONGO_ANOMALIES_COLLECTION]
    docs = list(coll.find({}))
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)
    for col in ("window_start", "window_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_anomalies_to_mariadb(df: pd.DataFrame) -> None:
    """Carga anomalías en la tabla kpi_anomalies de MariaDB (reemplaza contenido en cada ejecución)."""
    engine = get_sql_engine()
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM kpi_anomalies"))
        conn.commit()
    if df.empty:
        print("No hay anomalías para exportar.")
        return
    cols = ["warehouse_id", "window_start", "window_end", "avg_delay_min", "vehicle_count", "anomaly_flag"]
    for c in cols:
        if c not in df.columns and c != "anomaly_flag":
            df[c] = None
    if "anomaly_flag" not in df.columns:
        df["anomaly_flag"] = 1
    sub = df[["warehouse_id", "window_start", "window_end", "avg_delay_min", "vehicle_count", "anomaly_flag"]].copy()
    sub["anomaly_flag"] = sub["anomaly_flag"].astype(int)
    sub.to_sql("kpi_anomalies", con=engine, if_exists="append", index=False)
    print(f"Exportadas {len(sub)} anomalías a kpi_anomalies.")


def main(source: str = "mongo", export_anomalies: bool = False) -> None:
    """
    Ejecuta el pipeline:
      1) Leer datos crudos de MongoDB o Parquet.
      2) Construir KPIs por vehículo y almacén.
      3) Insertar en MariaDB.
      4) Si export_anomalies: exportar también transport.anomalies → kpi_anomalies.
    """
    if source == "mongo":
        df_raw = fetch_from_mongo()
    elif source == "parquet":
        df_raw = fetch_from_parquet()
    else:
        raise ValueError("source debe ser 'mongo' o 'parquet'")

    if not df_raw.empty:
        df_vehicle = build_kpi_by_vehicle(df_raw)
        df_warehouse = build_kpi_by_warehouse(df_raw)
        load_to_mariadb(df_vehicle, df_warehouse)
    else:
        print("No hay datos de entrada para KPIs por vehículo/almacén.")

    if export_anomalies:
        df_anom = fetch_anomalies_from_mongo()
        load_anomalies_to_mariadb(df_anom)


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
    parser.add_argument(
        "--export-anomalies",
        action="store_true",
        help="Exportar además la colección MongoDB anomalies a kpi_anomalies.",
    )
    args = parser.parse_args()

    main(source=args.source, export_anomalies=args.export_anomalies)

