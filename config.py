# Configuración centralizada del clúster (3 nodos: hadoop + nodo1 + nodo2)
# Migración de red: sin localhost/127.0.0.1; uso de IPs estáticas.

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
# Datos maestros (warehouses, routes) en HDFS
HDFS_WAREHOUSES_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/warehouses"
HDFS_ROUTES_PATH = f"{HDFS_NAMENODE}{HDFS_BASE}/routes"

# Kafka (broker en master)
KAFKA_BOOTSTRAP_SERVERS = f"{MASTER_IP}:9092"
KAFKA_TOPIC_RAW = "raw-data"
KAFKA_TOPIC_FILTERED = "filtered-data"

# Spark / YARN (modo distribuido)
SPARK_MASTER = "yarn"
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
