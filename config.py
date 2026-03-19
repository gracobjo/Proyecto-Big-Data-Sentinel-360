# Sentinel360 – Configuración centralizada del clúster (3 nodos: hadoop + nodo1 + nodo2)
# Migración de red: sin localhost/127.0.0.1; uso de IPs estáticas.
#
# Centraliza: IPs, rutas HDFS, temas Kafka, tablas Hive, MongoDB, MariaDB (analytics),
# topic de alertas y checkpoint. Los scripts Python importan las variables desde aquí.
import os

# Nodos
MASTER_IP = "192.168.99.10"   # hadoop: NameNode, ResourceManager, Kafka, NiFi
NODE1_IP = "192.168.99.12"    # nodo1: DataNode, NodeManager
NODE2_IP = "192.168.99.14"    # nodo2: DataNode, NodeManager

# HDFS (NameNode en master)
HDFS_NAMENODE = f"hdfs://{MASTER_IP}:9000"
HDFS_USER = "hadoop"
HDFS_BASE = f"/user/{HDFS_USER}/proyecto"
# Rutas de datos (prefijo completo para Spark)
HDFS_RAW_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/raw"
HDFS_PROCESSED_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/procesado"
# Subrutas bajo procesado
HDFS_CLEANED_PATH = f"{HDFS_PROCESSED_PATH}/cleaned"
HDFS_ENRICHED_PATH = f"{HDFS_PROCESSED_PATH}/enriched"
HDFS_GRAPH_PATH = f"{HDFS_PROCESSED_PATH}/graph"
HDFS_AGGREGATED_DELAYS_PATH = f"{HDFS_PROCESSED_PATH}/aggregated_delays"
HDFS_TEMP_PATH = f"{HDFS_PROCESSED_PATH}/temp"
# Ruta opcional para modelos ML (p. ej. K-Means de anomalías)
HDFS_MODELS_PATH = f"{HDFS_PROCESSED_PATH}/models"
# Datos maestros (warehouses, routes) en HDFS
HDFS_WAREHOUSES_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/warehouses"
HDFS_ROUTES_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/routes"

# Kafka (broker en master). Topics del proyecto Sentinel360:
#   raw-data     = entrada principal (NiFi: GPS + OpenWeather)
#   filtered-data = datos filtrados (consumo downstream)
KAFKA_BOOTSTRAP_SERVERS = f"{MASTER_IP}:9092"
KAFKA_TOPIC_RAW = "raw-data"
KAFKA_TOPIC_FILTERED = "filtered-data"
KAFKA_TOPIC_GPS_EVENTS = "gps-events"   # opcional: simulador y consumidores de demo
KAFKA_TOPIC_ALERTS = "alerts"           # opcional: alertas de anomalías (batch y streaming)

# Spark: por defecto YARN; si SPARK_MASTER está en el entorno (p. ej. run_spark_submit.sh --local), se usa ese valor
SPARK_MASTER = os.environ.get("SPARK_MASTER", "yarn")
SPARK_DEPLOY_MODE = "client"
# ResourceManager para configuración Hadoop (Web UI: http://192.168.99.10:8088)
YARN_RESOURCE_MANAGER_HOST = MASTER_IP

# Hive (tablas del proyecto)
HIVE_DATABASE = "transport"
HIVE_WAREHOUSES_TABLE = "transport.warehouses"
HIVE_ROUTES_TABLE = "transport.routes"
HIVE_AGGREGATED_DELAYS_TABLE = "transport.aggregated_delays"

# Checkpoint para Structured Streaming (en HDFS o local según despliegue)
STREAMING_CHECKPOINT_PATH = f"{HDFS_NAMENODE}/user/{HDFS_USER}/proyecto/checkpoints/delays"

# MongoDB (Fase III - carga multicapa: estado vehículos, agregados, anomalías)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = "transport"
MONGO_AGGREGATED_COLLECTION = "aggregated_delays"   # ventanas de retrasos
MONGO_VEHICLE_STATE_COLLECTION = "vehicle_state"   # último estado por vehículo
MONGO_ANOMALIES_COLLECTION = "anomalies"           # anomalías detectadas (CU3)

# MariaDB / MySQL – capa analítica para Superset y Grafana (sentinel360_analytics)
MARIA_DB_HOST = os.environ.get("MARIA_DB_HOST", "localhost")
MARIA_DB_PORT = int(os.environ.get("MARIA_DB_PORT", "3306"))
MARIA_DB_USER = os.environ.get("MARIA_DB_USER", "sentinel")
MARIA_DB_PASSWORD = os.environ.get("MARIA_DB_PASSWORD", "sentinel_password")
MARIA_DB_NAME = os.environ.get("MARIA_DB_NAME", "sentinel360_analytics")
MARIA_DB_URI = os.environ.get(
    "MARIA_DB_URI",
    f"mysql+pymysql://{MARIA_DB_USER}:{MARIA_DB_PASSWORD}@{MARIA_DB_HOST}:{MARIA_DB_PORT}/{MARIA_DB_NAME}",
)
