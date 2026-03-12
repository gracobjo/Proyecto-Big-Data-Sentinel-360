## Sentinel360 – Documento de presentación unificado

Autor: **Jose Antonio Gracia Cobacho**  
Repositorio: [Proyecto-Big-Data-Sentinel-360](https://github.com/gracobjo/Proyecto-Big-Data-Sentinel-360)

Este documento reúne, en un único fichero imprimible, la descripción de la arquitectura, las fases del ciclo KDD y los principales scripts y flujos implementados en Sentinel360.

---

## Índice

1. [Arquitectura de referencia](#arquitectura-de-referencia)
2. [Fase I – Ingesta (NiFi → Kafka + HDFS raw)](#fase-i--ingesta-nifi--kafka--hdfs-raw)
   - [Scripts de preparación](#scripts-de-preparación-fase-i)
   - [Flujo NiFi (JSON importable)](#flujo-nifi-json-importable)
   - [Eventos GPS de ejemplo](#eventos-gps-de-ejemplo)
3. [Fase II – Limpieza, enriquecimiento y grafos](#fase-ii--limpieza-enriquecimiento-y-grafos)
   - [Lanzador genérico de jobs Spark](#lanzador-genérico-de-jobs-spark)
   - [Job de grafos con GraphFrames](#job-de-grafos-con-graphframes)
4. [Fase III – Streaming de retrasos](#fase-iii--streaming-de-retrasos)
5. [Fase III – Detección de anomalías (K-Means)](#fase-iii--detección-de-anomalías-k-means)
6. [Interfaz web de presentación (Streamlit)](#interfaz-web-de-presentación-streamlit)
7. [Entorno visual y material de apoyo](#entorno-visual-y-material-de-apoyo)

---

## Arquitectura de referencia

Sentinel360 monitoriza una red de transporte utilizando el ciclo **KDD** completo, apoyándose en el stack **Apache**:

- **NiFi + Kafka + HDFS** para la ingesta de logs GPS y datos de OpenWeather.
- **Spark (batch y streaming) + Hive** para limpieza, enriquecimiento, grafos y agregados de retrasos.
- **MongoDB** para el estado operativo y las anomalías.
- **Airflow** para orquestar procesos.
- **Streamlit + Superset + Grafana** como capa de presentación.

Topología de clúster (resumen):

- Nodo `hadoop` (master): NameNode, ResourceManager, Kafka (KRaft), NiFi, Hive, MariaDB.
- Nodos `nodo1` y `nodo2`: DataNode + NodeManager.

Toda la configuración (IPs, rutas HDFS, topics Kafka, colecciones Mongo, BBDD MariaDB) reside en `config.py`, utilizada por scripts y jobs Spark.

---

## Fase I – Ingesta (NiFi → Kafka + HDFS raw)

En esta fase se prepara el entorno para que NiFi lea los logs GPS desde un directorio local, publique eventos en Kafka (`raw-data`, `filtered-data`) y mantenga una copia cruda en HDFS (`/user/hadoop/proyecto/raw`).

### Scripts de preparación (Fase I)

**`scripts/setup_hdfs.sh`** – creación de rutas en HDFS:

```bash
#!/bin/bash
# Crear rutas HDFS para Sentinel360 (clúster: NameNode en 192.168.99.10)
# Uso: ./scripts/setup_hdfs.sh [usuario_hdfs]
# Requiere: HADOOP_HOME en PATH o hdfs disponible (ej. /usr/local/hadoop/bin/hdfs)

USER="${1:-hadoop}"
BASE="/user/${USER}/proyecto"

# Asegurar que usamos el NameNode del clúster (configurar fs.defaultFS en core-site.xml)
export HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-/usr/local/hadoop/etc/hadoop}"

for dir in raw procesado/cleaned procesado/enriched procesado/graph procesado/aggregated_delays procesado/temp checkpoints/delays; do
  hdfs dfs -mkdir -p "${BASE}/${dir}"
  echo "Creado: ${BASE}/${dir}"
done
# Datos maestros
hdfs dfs -mkdir -p "${BASE}/warehouses" "${BASE}/routes"
echo "Creado: ${BASE}/warehouses, ${BASE}/routes"
hdfs dfs -ls -R "${BASE}"
```

**`scripts/preparar_ingesta_nifi.sh`** – preparación del flujo NiFi y topics Kafka:

```bash
#!/bin/bash
# Prepara el entorno para la ingesta en NiFi: directorio GPS, datos de prueba y temas Kafka.
# Ejecutar desde la raíz de Sentinel360: ./scripts/preparar_ingesta_nifi.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

KAFKA_HOME="${KAFKA_HOME:-/home/hadoop/software/kafka_2.13-4.1.1}"
BOOTSTRAP="192.168.99.10:9092"
GPS_DIR="/home/hadoop/data/gps_logs"

echo "=== Preparando ingesta NiFi ==="

mkdir -p "$GPS_DIR"
echo "[OK] Directorio: $GPS_DIR"

if [ -f "data/sample/generate_gps_logs.py" ]; then
  python3 data/sample/generate_gps_logs.py
  cp -f data/sample/gps_events.csv data/sample/gps_events.json "$GPS_DIR/" 2>/dev/null || true
  echo "[OK] Datos GPS copiados a $GPS_DIR"
else
  echo "[?] No existe data/sample/generate_gps_logs.py; crea archivos .json/.csv en $GPS_DIR a mano"
fi

for topic in raw-data filtered-data; do
  "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
    --topic "$topic" --partitions 3 --replication-factor 1 2>/dev/null \
    && echo "[OK] Tema Kafka: $topic" \
    || echo "[?] Tema $topic (puede existir ya)"
done
```

### Flujo NiFi (JSON importable)

El flujo de NiFi se distribuye como `ingest/gps_transport_flow_importable.json`. A continuación se muestran las **primeras líneas** del JSON (esquema del flujo):

```json
{"flowContents":{"identifier":"75036830-1c96-3109-b159-7f69658b8015","instanceIdentifier":"6dcabec5-019c-1000-2a24-f153b13bdb00","name":"gps_transport_flow_importable","comments":"Flujo GPS Sentinel360 Fase I (esquema completo): GetFile → UpdateAttribute → PutHDFS + SplitText → EvaluateJsonPath → RouteOnAttribute → PublishKafka raw/filtered.","position":{"x":-80.0,"y":-696.0},"processGroups":[],"remoteProcessGroups":[],"processors":[{"identifier":"gps-0002-4000-8000-000000000002","instanceIdentifier":"efa344f0-e506-3061-94fb-d1d141019365","name":"GetFile GPS Logs","comments":"Lee ficheros JSON/CSV desde directorio local.","position":{"x":80.0,"y":128.0},"type":"org.apache.nifi.processors.standard.GetFile","bundle":{"group":"org.apache.nifi","artifact":"nifi-standard-nar","version":"2.7.2"},"properties":{"Keep Source File":"false","Minimum File Age":"0 sec","Polling Interval":"5 sec","Input Directory":"/home/hadoop/data/gps_logs","Maximum File Age":null,"Batch Size":"10","Maximum File Size":null,"Minimum File Size":"0 B","Ignore Hidden Files":"true","Recurse Subdirectories":"true","File Filter":".*\\.(jsonl?|csv)","Path Filter":null},"propertyDescriptors":{},"style":{},"schedulingPeriod":"5 sec","schedulingStrategy":"TIMER_DRIVEN","executionNode":"ALL","penaltyDuration":"30 sec","yieldDuration":"1 sec","bulletinLevel":"WARN","runDurationMillis":0,"concurrentlySchedulableTaskCount":1,"autoTerminatedRelationships":["failure"],"scheduledState":"ENABLED","retryCount":10,"retriedRelationships":[],"backoffMechanism":"PENALIZE_FLOWFILE","maxBackoffPeriod":"10 mins","componentType":"PROCESSOR","groupIdentifier":"75036830-1c96-3109-b159-7f69658b8015"}, ...}
```

Y un extracto de la parte media (PublishKafka / PutHDFS) para documentar visualmente la ruta:

```json
{"identifier":"gps-put-hdfs-4000-8000-000002","name":"PutHDFS","comments":"Copia raw en HDFS.","type":"org.apache.nifi.processors.hadoop.PutHDFS","properties":{"Directory":"/user/hadoop/proyecto/raw", ...}}
{"identifier":"c8b54c9f-b31f-309d-a0f9-81cc1d69c71c","name":"PublishKafka filtered-data","comments":"Solo eventos filtrados (ej. speed < 120).","properties":{"Topic Name":"filtered-data", ...}}
{"identifier":"gps-kafka-raw-4000-8000-000001","name":"PublishKafka raw-data","comments":"Todos los eventos (matched + unmatched).","properties":{"Topic Name":"raw-data", ...}}
```

*(El fichero completo puede importarse directamente en la UI de NiFi.)*

### Eventos GPS de ejemplo

Muestra de los **primeros 5** eventos del fichero `data/sample/gps_events.json`:

```json
{"event_id": "ev-000000", "vehicle_id": "V-028", "ts": "2026-03-03T19:06:28.351399+00:00Z", "lat": 38.774562, "lon": -3.307077, "speed": 6.8, "warehouse_id": "WH-BCN"}
{"event_id": "ev-000001", "vehicle_id": "V-041", "ts": "2026-03-03T19:07:37.351399+00:00Z", "lat": 38.425968, "lon": -3.173307, "speed": 80.23, "warehouse_id": "WH-MAD"}
{"event_id": "ev-000002", "vehicle_id": "V-020", "ts": "2026-03-03T19:10:27.351399+00:00Z", "lat": 39.835104, "lon": -3.47018, "speed": 48.37, "warehouse_id": "WH-BIL"}
{"event_id": "ev-000003", "vehicle_id": "V-001", "ts": "2026-03-03T19:10:57.351399+00:00Z", "lat": 41.491927, "lon": -3.147339, "speed": 70.3, "warehouse_id": "WH-SEV"}
{"event_id": "ev-000004", "vehicle_id": "V-012", "ts": "2026-03-03T19:14:01.351399+00:00Z", "lat": 40.436619, "lon": -3.247214, "speed": 36.74, "warehouse_id": "WH-SEV"}
```

Y los **últimos 5**:

```json
{"event_id": "ev-000495", "vehicle_id": "V-006", "ts": "2026-03-04T11:36:40.351399+00:00Z", "lat": 41.965626, "lon": -2.618045, "speed": 69.57, "warehouse_id": "WH-MAD"}
{"event_id": "ev-000496", "vehicle_id": "V-007", "ts": "2026-03-04T11:36:42.351399+00:00Z", "lat": 39.499719, "lon": -3.486565, "speed": 3.93, "warehouse_id": "WH-SEV"}
{"event_id": "ev-000497", "vehicle_id": "V-015", "ts": "2026-03-04T11:39:12.351399+00:00Z", "lat": 40.295237, "lon": -2.71854, "speed": 42.75, "warehouse_id": "WH-MAD"}
{"event_id": "ev-000498", "vehicle_id": "V-043", "ts": "2026-03-04T11:41:12.351399+00:00Z", "lat": 38.243404, "lon": -4.490769, "speed": 35.47, "warehouse_id": "WH-BIL"}
{"event_id": "ev-000499", "vehicle_id": "V-046", "ts": "2026-03-04T11:43:50.351399+00:00Z", "lat": 41.458636, "lon": -3.25963, "speed": 83.04, "warehouse_id": "WH-BCN"}
```

---

## Fase II – Limpieza, enriquecimiento y grafos

En la Fase II se normalizan los datos crudos y se enriquecen con información de almacenes y rutas. Después se modela la red como grafo.

### Lanzador genérico de jobs Spark

`scripts/run_spark_submit.sh` encapsula la ejecución de `spark-submit` tanto en YARN como en modo local:

```bash
#!/bin/bash
# Lanzar jobs Spark en modo distribuido (YARN) o local.
# Uso: ./scripts/run_spark_submit.sh [--local] <script.py> [arg1 [arg2 ...]]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

USE_LOCAL=""
while [ -n "$1" ]; do
  case "$1" in
    --local|-l) USE_LOCAL=1; shift ;;
    *) break ;;
  esac
done

SPARK_SCRIPT="$1"
...

"${SPARK_HOME}/bin/spark-submit" \
  --master yarn \
  --deploy-mode client \
  $SPARK_JARS \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,graphframes:graphframes:0.8.3-spark3.5-s_2.12 \
  --num-executors "$NUM_EXECUTORS" \
  --executor-cores 2 \
  --executor-memory 2G \
  --driver-memory 2G \
  --py-files "${PROJECT_ROOT}/config.py" \
  "$SPARK_SCRIPT" \
  "${EXTRA_ARGS[@]}"
```

### Job de grafos con GraphFrames

`spark/graph/transport_graph.py` construye el grafo de almacenes y rutas:

```python
#!/usr/bin/env python3
"""
Fase II - Análisis de grafos con GraphFrames (distribuido en YARN).
Nodos: Almacenes. Aristas: Rutas. Camino más corto y componentes conectados.
"""
from config import (
    HDFS_NAMENODE,
    SPARK_MASTER,
    HDFS_ROUTES_PATH,
    HDFS_WAREHOUSES_PATH,
    HDFS_GRAPH_PATH,
)
from pyspark.sql import SparkSession, functions as F

def get_spark_session():
    return (
        SparkSession.builder
        .appName("Transport-GraphFrames")
        .master(SPARK_MASTER)
        .config("spark.hadoop.fs.defaultFS", HDFS_NAMENODE)
        .config("spark.yarn.resourcemanager.hostname", "192.168.99.10")
        .getOrCreate()
    )

def main(routes_path: str = None, warehouses_path: str = None, output_path: str = None) -> None:
    ...
    from graphframes import GraphFrame
    vertices = (
        spark.read.option("header", "true")
        .csv(warehouses_path)
        .select(F.col("warehouse_id").alias("id"), F.lit("warehouse").alias("type"))
    )
    edges = (
        spark.read.option("header", "true")
        .csv(routes_path)
        .select(
            F.col("from_warehouse_id").alias("src"),
            F.col("to_warehouse_id").alias("dst"),
            F.col("distance_km").alias("weight"),
        )
    )
    g = GraphFrame(vertices, edges)
    paths = g.shortestPaths(landmarks=["WH-MAD", "WH-BCN"])
    paths.write.mode("overwrite").parquet(output_path + "/shortest_paths")
    ...
```

---

## Fase III – Streaming de retrasos

El componente principal es `spark/streaming/delays_windowed.py`, que calcula retrasos en ventanas de 15 minutos y escribe agregados en Hive + MongoDB.

```python
#!/usr/bin/env python3
"""
Fase III - Structured Streaming: media de retrasos en ventanas de 15 minutos.
Entrada: Kafka (raw-data) o directorio HDFS. Salida: consola + Hive (aggregated_delays) + MongoDB (opcional).
"""
from config import (
    HDFS_NAMENODE,
    SPARK_MASTER,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RAW,
    KAFKA_TOPIC_ALERTS,
    HDFS_RAW_PATH,
    STREAMING_CHECKPOINT_PATH,
    HIVE_AGGREGATED_DELAYS_TABLE,
    MONGO_URI,
    MONGO_DB,
    MONGO_AGGREGATED_COLLECTION,
)
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DoubleType

STREAMING_ANOMALY_THRESHOLD_MIN = 20.0

def write_batch_to_hive_and_mongo(batch_df, batch_id):
    """Escribe cada micro-batch en Hive y MongoDB, y genera alertas si avg_delay_min supera el umbral."""
    ...

def main(source: str = "file", input_path: str = None, checkpoint: str = None) -> None:
    ...
    windowed = (
        events.withWatermark("ts", "10 minutes")
        .groupBy(F.window("ts", "15 minutes", "15 minutes"), "warehouse_id")
        .agg(
            F.avg("delay_min").alias("avg_delay_min"),
            F.count("*").alias("vehicle_count"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "warehouse_id",
            "avg_delay_min",
            "vehicle_count",
        )
    )
    q = (
        windowed.writeStream
        .outputMode("append")
        .option("checkpointLocation", checkpoint)
        .foreachBatch(write_batch_to_hive_and_mongo)
        .start()
    )
    q.awaitTermination()
```

---

## Fase III – Detección de anomalías (K-Means)

El modelo de clustering se implementa en `spark/ml/anomaly_detection.py`. Utiliza K-Means de Spark ML sobre los agregados `avg_delay_min` y `vehicle_count`.

```python
from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import VectorAssembler

def train_kmeans(df: DataFrame, k: int = 3) -> DataFrame:
    """
    Entrena un K-Means sobre (avg_delay_min, vehicle_count) y devuelve
    el DataFrame con `prediction` (cluster) y `anomaly_flag`.
    """
    features_cols: List[str] = ["avg_delay_min", "vehicle_count"]
    assembler = VectorAssembler(inputCols=features_cols, outputCol="features")
    assembled = assembler.transform(df)

    kmeans = KMeans(k=k, seed=42, featuresCol="features", predictionCol="prediction")
    model = kmeans.fit(assembled)

    # Determinar cluster más problemático: mayor avg_delay_min en el centroide
    centers = model.clusterCenters()
    max_delay = -1.0
    anomaly_cluster = 0
    for idx, center in enumerate(centers):
        if center[0] > max_delay:
            max_delay = center[0]
            anomaly_cluster = idx

    scored = model.transform(assembled)
    scored = scored.withColumn(
        "anomaly_flag", F.col("prediction") == F.lit(anomaly_cluster)
    )
    return scored
```

La función `write_anomalies_to_mongo_and_kafka` envía las filas con `anomaly_flag=True` a:

- MongoDB (`transport.anomalies`).
- Kafka (`alerts`), como eventos de tipo `"ANOMALY"`.

---

## Interfaz web de presentación (Streamlit)

La interfaz `web/presentacion_sentinel360_app.py` actúa como **panel de control** para recorrer las fases del ciclo KDD:

- Arranque de servicios.
- Ingesta (Fase I).
- Limpieza/enriquecimiento (Fase II).
- Grafos (Fase II, GraphFrames).
- Streaming y anomalías (Fase III).
- Entorno visual (Superset / Grafana) y material de presentación.

Ejemplo de la pestaña de streaming + anomalías:

```python
def page_fase_iii_streaming_anomalias():
    st.header("4 · Fase III – Streaming de retrasos y anomalías")
    st.markdown(
        """
        Desde aquí puedes lanzar:

        - `delays_windowed.py` (Spark Streaming): lee de Kafka (`raw-data` o ficheros), calcula retrasos
          por ventana y escribe en Hive + MongoDB, generando alertas al topic `alerts`.
        - `anomaly_detection.py` (batch): detecta anomalías sobre los agregados y escribe en MongoDB + Kafka.
        """
    )

    modo_stream = st.selectbox("Modo de entrada para `delays_windowed.py`", ["kafka", "file"])

    st.subheader("Comandos de esta fase")
    st.code(
        f"./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {modo_stream}\n"
        "./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py\n",
        language="bash",
    )
    ...
```

---

## Entorno visual y material de apoyo

En la pestaña **5 · Entorno visual (Superset / Grafana)** se integran:

- Enlaces a la documentación de dashboards (`PRESENTACION_ENTORNO_VISUAL.md`, `SUPERSET_DASHBOARDS.md`, `GRAFANA_DASHBOARDS.md`).
- Imagen de arquitectura (`sentinel360v2.png` / `Sentinel360.png`) como portada visual.
- Botones para descargar:
  - `Sentinel360_Proactive_Logistics_Intelligence.pptx`.
  - `Sentinel360_Proactive_Logistics_Intelligence.pdf`.

Esto permite, desde la propia UI:

- Explicar la arquitectura con la imagen.
- Navegar a las fases del KDD.
- Abrir/descargar el material de presentación usado en la defensa.

---

Este documento `.md` está pensado para convertirse directamente en **PDF imprimible**, reuniendo:

- Descripción textual de la arquitectura.
- Código de los principales scripts.
- Fragmentos representativos de los ficheros JSON de ingesta.

