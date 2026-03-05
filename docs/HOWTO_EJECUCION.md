# Sentinel360 – HOWTO de ejecución por supuestos

Guía paso a paso para ejecutar los distintos supuestos del proyecto. Ejecutar desde la raíz del repositorio: `cd ~/Documentos/ProyectoBigData` (o la ruta donde tengas el proyecto).

---

## Requisitos previos

- Hadoop (HDFS + YARN), Kafka, Hive (metastore + HiveServer2), opcionalmente NiFi y MongoDB, instalados y accesibles.
- Variables de entorno: `HADOOP_HOME`, `SPARK_HOME`, `HIVE_HOME`, `KAFKA_HOME` según tu instalación (el script de arranque las detecta si están en rutas habituales).

---

## Supuesto 0: Arrancar servicios

Objetivo: tener el clúster listo (HDFS, YARN, Kafka, MariaDB/MySQL, Hive, NiFi, etc.).

```bash
cd ~/Documentos/ProyectoBigData
./scripts/start_servicios.sh
```

Opcional: comprobar con `./scripts/verificar_cluster.sh`.

---

## Supuesto 1: Fase I – Ingesta (NiFi → Kafka + HDFS raw)

Objetivo: datos GPS y API (OpenWeather) a Kafka y copia raw en HDFS.

1. Crear rutas HDFS y temas Kafka (si no existen):
   ```bash
   ./scripts/setup_hdfs.sh
   ./scripts/preparar_ingesta_nifi.sh
   ```
2. En NiFi: importar flujos (GPS y HTTP), configurar PutHDFS (Directory: `/user/hadoop/proyecto/raw`), Controller Service HDFS con `core-site.xml` (ruta absoluta sin `file://`), conectar GetFile e InvokeHTTP a PutHDFS y a PublishKafka. Arrancar los procesadores.
3. Comprobar:
   ```bash
   hdfs dfs -ls /user/hadoop/proyecto/raw/
   ```

Documentación: `ingest/nifi/FASE_I_INGESTA.md`, `ingest/nifi/FLUJO_HTTP_OPENWEATHER.md`.

---

## Supuesto 2: Hive – Base `transport` y tablas

Objetivo: base de datos `transport` con tablas warehouses, routes, events_raw, aggregated_delays.

1. Asegurar que HiveServer2 y el metastore están en marcha (por ejemplo con `start_servicios.sh`; MariaDB debe estar levantada antes que Hive).
2. Crear base y tablas con Beeline (un solo comando o uno por script):
   ```bash
   ./scripts/crear_tablas_hive.sh
   ```
   O a mano (01 a 05):
   ```bash
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/02_routes.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/03_events_raw.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/05_reporte_diario.sql
   ```
3. Poblar datos maestros en HDFS (las tablas EXTERNAL leen de ahí):
   ```bash
   ./scripts/ingest_from_local.sh
   ```
4. Comprobar:
   ```bash
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SHOW TABLES;"
   ./scripts/verificar_tablas_hive.sh
   ```

Documentación: `docs/HIVE_SENTINEL360.md`, `hive/README.md`, `docs/POBLAR_TABLAS_HIVE.md`.

---

## Supuesto 3: Fase II – Limpieza y enriquecimiento (Spark)

Objetivo: datos limpios y enriquecidos en HDFS (cleaned, enriched).

1. Asegurar datos en HDFS (raw y/o maestros): `./scripts/ingest_from_local.sh` si no lo has hecho.
2. Ejecutar en orden:
   ```bash
   ./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
   ./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
   ```
3. Comprobar:
   ```bash
   hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned
   hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched
   ```

Documentación: `docs/KDD_FASES.md` (Fase II).

---

## Supuesto 4: Fase II – Grafos (GraphFrames)

Objetivo: shortest_paths y connected_components en HDFS y, opcionalmente, visualización.

1. Requisitos: YARN y HDFS en marcha; en la máquina donde lanzas `spark-submit`, instalar el módulo Python del driver:
   ```bash
   pip install graphframes
   ```
2. Ejecutar (no cerrar la terminal hasta que termine):
   ```bash
   ./scripts/run_spark_submit.sh spark/graph/transport_graph.py
   ```
3. Comprobar:
   ```bash
   hdfs dfs -ls /user/hadoop/proyecto/procesado/graph/
   # Debe haber shortest_paths y connected_components
   ```
4. Ver datos o generar imagen del grafo:
   ```bash
   hdfs dfs -get /user/hadoop/proyecto/procesado/graph/shortest_paths resultados/shortest_paths
   hdfs dfs -get /user/hadoop/proyecto/procesado/graph/connected_components resultados/connected_components
   pip install pandas pyarrow networkx matplotlib
   python scripts/ver_grafos_resultados.py
   python scripts/ver_grafos_resultados.py --viz
   ```
   Se genera `grafo.png` (red de almacenes y rutas).

Documentación: `docs/VISUALIZAR_GRAFOS.md`, `docs/FUNCIONALIDADES_RECIENTES.md`.

---

## Supuesto 5: Fase III – Streaming + escritura en Hive y MongoDB

Objetivo: ventanas de retrasos (15 min) y carga multicapa: cada micro-batch se escribe en **Hive** (`transport.aggregated_delays`) y opcionalmente en **MongoDB** (colección `transport.aggregated_delays`).

**Requisitos previos**

- Tabla Hive creada: `beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql`
- MongoDB en marcha y colección creada (opcional): `mongosh < mongodb/scripts/init_collection.js` (crea `transport.aggregated_delays` e índices).
- En la máquina donde lanzas `spark-submit`: `pip install pymongo` (solo si quieres escritura en MongoDB; si no, el job sigue escribiendo en Hive).

**Ejecución**

```bash
# Modo fichero: lee CSVs desde HDFS raw (debe haber datos en /user/hadoop/proyecto/raw)
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file

# Modo Kafka: consume el tema raw-data
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka
```

El job es de larga duración (queda escuchando). Cada ventana completada se escribe en Hive y, si MongoDB está disponible y `pymongo` instalado, también en la colección `aggregated_delays`. Para detener: Ctrl+C.

**Comprobar**

```bash
# Hive
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM aggregated_delays LIMIT 10;"

# MongoDB (si usaste MongoDB)
mongosh --eval "db.getSiblingDB('transport').aggregated_delays.find().limit(5)"
```

**Carga batch desde Parquet (alternativa)**  
Si los agregados se generan por otro proceso y quedan en HDFS en `procesado/aggregated_delays`, puedes volcarlos a Hive con:

```bash
./scripts/run_spark_submit.sh spark/streaming/write_to_hive_and_mongo.py
```

Documentación: `docs/FASE_III_STREAMING.md`, `docs/KDD_FASES.md`, `docs/SIGUIENTE_PASOS.md`.

---

## Supuesto 6: Verificación global

- **Hive**: `./scripts/verificar_tablas_hive.sh`
- **HDFS**: `hdfs dfs -ls /user/hadoop/proyecto/`
- **YARN**: http://192.168.99.10:8088
- **NiFi**: https://localhost:8443/nifi

---

## Supuesto 7: Prueba extremo a extremo (Kafka → Spark → HDFS + MongoDB)

Objetivo: verificar el pipeline completo de streaming usando Kafka y Spark, y comprobar que los datos llegan a HDFS (y opcionalmente a MongoDB).

> Esta prueba es complementaria a los supuestos anteriores. Aquí se fuerza el flujo Producer → Kafka → Spark Streaming → HDFS/Hive (+ MongoDB).

### 1️⃣ Arrancar clúster Hadoop / YARN

En `nodo1`:

```bash
jps
```

Deberías ver al menos:

- NameNode  
- DataNode  
- SecondaryNameNode  
- ResourceManager  
- NodeManager  

En `nodo2`:

```bash
jps
```

Deberías ver:

- DataNode  
- NodeManager  

Si falta algo:

```bash
start-dfs.sh
start-yarn.sh
```

### 2️⃣ Arrancar Kafka

En `nodo1`:

```bash
cd /usr/local/kafka
bin/kafka-server-start.sh config/kraft/server.properties
```

Comprobar:

```bash
jps
```

Debe aparecer `Kafka`. Y el puerto:

```bash
netstat -tulnp | grep 9092
```

### 3️⃣ Crear topic de streaming

```bash
/usr/local/kafka/bin/kafka-topics.sh \
  --create \
  --topic gps-events \
  --bootstrap-server nodo1:9092 \
  --partitions 1 \
  --replication-factor 1
```

Comprobar:

```bash
/usr/local/kafka/bin/kafka-topics.sh \
  --list \
  --bootstrap-server nodo1:9092
```

Debe aparecer `gps-events`.

### 4️⃣ Generar datos de prueba (GPS)

Productor Kafka:

```bash
/usr/local/kafka/bin/kafka-console-producer.sh \
  --topic gps-events \
  --bootstrap-server nodo1:9092
```

Enviar algunos JSON:

```text
{"vehicle_id":"BUS_01","route_id":"R1","speed":45,"timestamp":"2026-03-02T10:01:00"}
{"vehicle_id":"BUS_02","route_id":"R1","speed":38,"timestamp":"2026-03-02T10:02:00"}
{"vehicle_id":"BUS_03","route_id":"R2","speed":50,"timestamp":"2026-03-02T10:03:00"}
```

### 5️⃣ Comprobar que Kafka recibe datos

Consumidor:

```bash
/usr/local/kafka/bin/kafka-console-consumer.sh \
  --topic gps-events \
  --bootstrap-server nodo1:9092 \
  --from-beginning
```

Deberías ver los JSON enviados.

### 6️⃣ Lanzar Spark Streaming

Ejemplo conceptual de script (`kafka_streaming.py`):

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("KafkaToHDFSStreaming") \
    .getOrCreate()

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "nodo1:9092") \
    .option("subscribe", "gps-events") \
    .load()

df.writeStream \
    .format("parquet") \
    .option("path", "hdfs://192.168.99.10:9000/data/gps") \
    .option("checkpointLocation", "hdfs://192.168.99.10:9000/checkpoints/gps") \
    .start() \
    .awaitTermination()
```

Lanzar en el nodo donde tengas Spark:

```bash
spark-submit --master yarn kafka_streaming.py
```

### 7️⃣ Comprobar que Spark está corriendo

```bash
yarn application -list
```

Debe aparecer algo como:

```text
KafkaToHDFSStreaming RUNNING
```

### 8️⃣ Verificar que HDFS recibe datos

```bash
hdfs dfs -ls /data/gps
```

Deberían aparecer archivos tipo:

- `part-00000.parquet`  
- `part-00001.parquet`

### 9️⃣ Leer datos desde Hive

Crear tabla externa (si no existe):

```sql
CREATE EXTERNAL TABLE gps_curated (
  vehicle_id STRING,
  route_id   STRING,
  speed      INT,
  timestamp  STRING
)
STORED AS PARQUET
LOCATION '/data/gps';
```

Probar:

```sql
SELECT * FROM gps_curated LIMIT 10;
```

### 🔟 Guardar estado en MongoDB (opcional)

Spark puede escribir también en MongoDB. Ejemplo conceptual:

```python
df.writeStream \
    .format("mongo") \
    .option("database", "sentinel") \
    .option("collection", "vehicle_state") \
    .start()
```

En Mongo verás documentos como:

```json
{
  "vehicle_id": "BUS_01",
  "route": "R1",
  "speed": 38,
  "delay": 3.5,
  "last_update": "2026-03-02T10:05:00"
}
```

### 🧪 Resultado esperado del pipeline

Si todo está correcto:

- Producer → **Kafka** → **Spark Streaming** → **HDFS**  
                             ↳ (opcional) **MongoDB**

Verás:

- Mensajes en Kafka.  
- Aplicación Spark en YARN.  
- Ficheros Parquet en HDFS.  
- Datos consultables en Hive.

### ⚠️ Prueba rápida de diagnóstico

Si algo falla, revisar:

- **Kafka**
  - `jps` → debe aparecer `Kafka`.
- **Spark / YARN**
  - `yarn application -list`
- **HDFS**
  - `hdfs dfsadmin -report`

---

## Orden recomendado (flujo completo)

1. Supuesto 0 (arranque servicios)  
2. Supuesto 1 (ingesta NiFi → Kafka + HDFS raw)  
3. Supuesto 2 (Hive DDL + ingest_from_local para maestros y raw)  
4. Supuesto 3 (cleaning + enrich)  
5. Supuesto 4 (grafos + visualización)  
6. Opcional: Supuesto 5 (streaming)  
7. Supuesto 6 (verificación)  
8. Opcional: Supuesto 7 (prueba extremo a extremo Kafka → Spark → HDFS + MongoDB)

---

## Supuesto 8: Simulador GPS en tiempo real → Kafka

Objetivo: utilizar un simulador realista de datos GPS que envía eventos continuamente a Kafka (`gps-events`), alimentando el pipeline NiFi / Kafka / Spark / HDFS / MongoDB.

### 1️⃣ Arquitectura del flujo

```text
Simulador GPS (scripts/gps_simulator.py)
          │
          ▼
   Kafka (gps-events)
          │
          ▼
   Spark Streaming
      ┌────┴─────┐
      ▼          ▼
     HDFS      MongoDB
 (histórico) (estado actual)
```

### 2️⃣ Instalar cliente Kafka para Python

En el nodo donde ejecutes el simulador (por ejemplo `nodo1`):

```bash
pip install kafka-python
# o
pip3 install kafka-python
```

### 3️⃣ Ejecutar el simulador

Desde la raíz del proyecto:

```bash
cd scripts
python3 gps_simulator.py
```

Verás en consola eventos similares:

```text
{'vehicle_id': 'BUS_04', 'route_id': 'R1', 'speed': 41, 'delay_minutes': 1.2, 'timestamp': '2026-03-05T22:10:15'}
{'vehicle_id': 'BUS_02', 'route_id': 'R3', 'speed': 33, 'delay_minutes': 0.8, 'timestamp': '2026-03-05T22:10:16'}
```

### 4️⃣ Verificar que Kafka recibe datos

Consumidor de prueba:

```bash
/usr/local/kafka/bin/kafka-console-consumer.sh \
  --topic gps-events \
  --bootstrap-server nodo1:9092
```

Deberían verse los JSON generados por el simulador.

### 5️⃣ Qué hará Spark con estos datos

- **Spark Streaming** leerá del topic `gps-events`.
- Podrá:
  - Calcular **velocidad media** y **retraso medio** por vehículo/ruta.
  - Detectar **anomalías** (vehículos detenidos, retrasos excesivos, etc.).
  - Guardar:
    - En **HDFS** (histórico, Parquet).
    - En **MongoDB** (estado actual, colección `vehicle_state`).

Ejemplo de documento en MongoDB:

```json
{
  "vehicle_id": "BUS_04",
  "route_id": "R1",
  "speed": 41,
  "delay_minutes": 1.2,
  "timestamp": "2026-03-05T22:10:15"
}
```

---

## Supuesto 9: Alertas de anomalías en tiempo casi real

Objetivo: mostrar en directo alertas generadas por el sistema cuando se detectan ventanas con retrasos elevados.

### 1️⃣ Componentes implicados

- **Streaming de retrasos**: `spark/streaming/delays_windowed.py`
  - Calcula la media de retraso por ventana (15 min) y almacén.
  - Marca como “anómalas” las ventanas con `avg_delay_min` por encima de un umbral (`STREAMING_ANOMALY_THRESHOLD_MIN`).
  - Escribe los agregados en Hive y MongoDB.
  - Envía alertas al topic Kafka `alerts`.
- **Consumer de alertas**: `scripts/alerts_consumer.py`
  - Escucha el topic `alerts`.
  - Muestra por consola las alertas en formato JSON.

### 2️⃣ Ejecutar el streaming con alertas

En el nodo donde lances Spark (con Kafka y MongoDB ya en marcha):

```bash
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka
```

El job:

- Leerá del topic configurado en `config.py` (`raw-data` o el que uses).
- Calculará ventanas de retraso.
- Escribirá en Hive y MongoDB.
- Enviará alertas al topic `alerts` cuando `avg_delay_min` supere el umbral configurado.

### 3️⃣ Lanzar el consumidor de alertas

En otra terminal:

```bash
cd scripts
python3 alerts_consumer.py
```

Verás en consola líneas similares:

```text
[ALERTA] {'type': 'ANOMALY_STREAMING', 'warehouse_id': 'WH_01', 'window_start': '2026-03-05T21:30:00', 'window_end': '2026-03-05T21:45:00', 'avg_delay_min': 24.3, 'vehicle_count': 12, 'threshold': 20.0}
```

### 4️⃣ Alimentar el sistema con el simulador

Si quieres una demo completa:

1. Lanzar el simulador GPS (`Supuesto 8`).
2. Lanzar el streaming con alertas (`Supuesto 9`).
3. Lanzar el consumer de alertas (`alerts_consumer.py`).

A medida que el streaming detecte ventanas con mucho retraso, irán apareciendo alertas en la consola del consumer.


Documentación relacionada: `README.md`, `docs/KDD_FASES.md`, `docs/ARRANQUE_SERVICIOS.md`.
