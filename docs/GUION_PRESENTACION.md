# Guion corto para presentar Sentinel360

Guía en un solo documento: **orden de ejecución** para la demo y **qué hace cada script** (entrada/salida). Ejecutar siempre desde la **raíz del proyecto** salvo donde se indique otra carpeta.

```bash
cd ~/Documentos/Proyecto-Big-Data-Sentinel-360
# (o la ruta donde tengas clonado el repo)
```

---

## 1. Guion corto (orden del día de la defensa)

### Paso 1 – Arrancar servicios del clúster

**Objetivo**: Dejar listos HDFS, YARN, Kafka, Hive, MongoDB (y opcionalmente NiFi).

**Dónde**: Nodo master (hadoop, 192.168.99.10). Desde la raíz del proyecto:

```bash
./scripts/start_servicios.sh
./scripts/verificar_cluster.sh    # opcional
```

**Qué comprobar**: `jps` debe mostrar NameNode, DataNode, ResourceManager, NodeManager, Kafka; si usas MongoDB, `mongod` en marcha.

---

### Paso 2 – KDD Fase I – Ingesta (NiFi → Kafka + HDFS raw)

**Objetivo**: Crear rutas HDFS, temas Kafka y datos de prueba para que NiFi pueda ingestar.

**Comandos** (raíz del proyecto):

```bash
./scripts/setup_hdfs.sh
./scripts/preparar_ingesta_nifi.sh
```

Luego en la **UI de NiFi** (https://localhost:8443/nifi): importar flujos, habilitar Controller Service de Kafka, arrancar los procesadores.

**Comprobar**:

```bash
hdfs dfs -ls /user/hadoop/proyecto/raw/
```

---

### Paso 3 – Hive: base `transport` y tablas

**Objetivo**: Crear la base Hive `transport` y las tablas (warehouses, routes, events_raw, aggregated_delays) que apuntan a HDFS.

**Comandos** (raíz del proyecto):

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/02_routes.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/03_events_raw.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql
./scripts/ingest_from_local.sh
```

**Comprobar**:

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SHOW TABLES;"
./scripts/verificar_tablas_hive.sh
```

---

### Paso 4 – KDD Fase II – Limpieza y enriquecimiento (Spark batch)

**Objetivo**: Normalizar datos raw y cruzarlos con maestros de Hive; escribir cleaned y enriched en HDFS.

**Comandos** (raíz del proyecto):

```bash
./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
```

**Comprobar**:

```bash
hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned
hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched
```

---

### Paso 5 – KDD Fase II – Grafos (GraphFrames)

**Objetivo**: Construir el grafo de almacenes y rutas; calcular shortest_paths y connected_components en HDFS.

**Comandos** (raíz del proyecto):

```bash
./scripts/run_spark_submit.sh spark/graph/transport_graph.py
hdfs dfs -ls /user/hadoop/proyecto/procesado/graph
```

**Opcional – Ver resultados o imagen**:

```bash
python scripts/ver_grafos_resultados.py
python scripts/ver_grafos_resultados.py --viz   # genera grafo.png en la raíz
```

---

### Paso 6 – KDD Fase III – Streaming de retrasos (Hive + MongoDB)

**Objetivo**: Job de Spark Streaming que lee de Kafka (o CSV en HDFS), calcula ventanas de retraso y escribe en Hive y MongoDB; además envía alertas al topic `alerts` cuando el retraso supera un umbral.

**Requisitos previos**: Tabla Hive `transport.aggregated_delays` creada (Paso 3). MongoDB en marcha y colecciones creadas:

```bash
mongosh < mongodb/scripts/init_collection.js
```

**Comando** (raíz del proyecto; job de larga duración, dejarlo corriendo):

```bash
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka
```

Para **modo fichero** (lee CSV desde HDFS raw):

```bash
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file
```

**Comprobar**:

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM aggregated_delays LIMIT 5;"
mongosh --eval "db.getSiblingDB('transport').aggregated_delays.find().limit(5)"
```

---

### Paso 7 – Simulador GPS y consumer de alertas (demo en vivo)

**Objetivo**: Generar eventos GPS hacia Kafka y ver en consola las alertas que genera el streaming.

**Terminal 1 – Simulador** (desde raíz o desde `scripts/`):

```bash
cd ~/Documentos/Proyecto-Big-Data-Sentinel-360
python3 scripts/gps_simulator.py
```

**Terminal 2 – Consumer de alertas**:

```bash
cd ~/Documentos/Proyecto-Big-Data-Sentinel-360
python3 scripts/alerts_consumer.py
```

Mientras `delays_windowed.py` esté corriendo y haya ventanas con retraso por encima del umbral, las alertas aparecerán en la consola del consumer. *Nota*: el streaming lee del topic `raw-data`; para ver alertas en vivo asegúrate de que ese topic tenga datos (p. ej. NiFi publicando en `raw-data`, o haber corrido antes el job en modo `file` para generar agregados y luego en modo `kafka` con datos en `raw-data`). El simulador envía a `gps-events`; si tu flujo NiFi copia `gps-events` → `raw-data`, las alertas se dispararán al procesar esos eventos.

---

### Paso 8 – Anomalías batch y KPIs para dashboards (Superset / Grafana)

**Objetivo**: Detectar anomalías sobre los agregados en Hive, escribirlas en MongoDB y en Kafka (`alerts`); volcar KPIs a MariaDB para Superset.

**Comandos** (raíz del proyecto):

```bash
./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py
python3 scripts/mongo_to_mariadb_kpi.py --source mongo
```

Después configurar Superset/Grafana contra MariaDB (`sentinel360_analytics`) según `docs/PRESENTACION_ENTORNO_VISUAL.md`, `docs/SUPERSET_DASHBOARDS.md` y `docs/GRAFANA_DASHBOARDS.md`.

---

## 2. Scripts: qué hace cada uno, entrada y salida

### Scripts de arranque y preparación (bash)

| Script | Qué hace | Entrada | Salida |
|--------|----------|---------|--------|
| `scripts/start_servicios.sh` | Arranca HDFS (start-dfs, start-yarn), Kafka, MongoDB, Spark History, MariaDB (LAMPP), Hive (metastore + HiveServer2), NiFi. Usa rutas por defecto o variables de entorno. | Ninguna (lee `config/rutas_servicios.env` si existe). | Servicios en ejecución; logs en `logs/*.log`. |
| `scripts/verificar_cluster.sh` | Comprueba que HDFS, YARN, Kafka, etc. responden. | Ninguna. | Mensajes por consola (OK / advertencias). |
| `scripts/setup_hdfs.sh` | Crea en HDFS la estructura de directorios del proyecto: `/user/<usuario>/proyecto/raw`, `procesado/cleaned`, `enriched`, `graph`, `aggregated_delays`, `temp`, `checkpoints/delays`, `warehouses`, `routes`. | Opcional: usuario HDFS (por defecto `hadoop`). | Directorios creados en HDFS; listado final. |
| `scripts/preparar_ingesta_nifi.sh` | Crea directorio local para logs GPS, genera/copia datos de prueba desde `data/sample` a ese directorio, crea temas Kafka `raw-data` y `filtered-data`. | Espera `data/sample/generate_gps_logs.py` y ficheros en `data/sample/`. | Directorio de ingesta con CSV/JSON; temas Kafka creados; instrucciones para NiFi. |
| `scripts/ingest_from_local.sh` | Sube a HDFS los ficheros de `data/sample/` (CSV, JSON) en `raw` y los maestros `warehouses.csv` y `routes.csv` en `warehouses` y `routes`. | Contenido de `data/sample/` (p. ej. generado por `generate_gps_logs.py`). | HDFS: `/user/hadoop/proyecto/raw/*`, `warehouses/`, `routes/`. |
| `scripts/run_spark_submit.sh` | Wrapper que lanza un script Python con `spark-submit` en YARN (client), incluyendo `config.py` vía `--py-files` y los packages Kafka y GraphFrames. | Argumento 1: ruta al `.py` (ej. `spark/cleaning/clean_and_normalize.py`). Resto: argumentos para el script. | El job Spark se ejecuta en el clúster; salida en consola y en YARN. |

---

### Jobs Spark (Python) – Fase II y III

| Script | Qué hace | Entrada | Salida |
|--------|----------|---------|--------|
| `spark/cleaning/clean_and_normalize.py` | Lee CSV desde HDFS raw, normaliza nombres de columnas, rellena nulos, elimina duplicados, convierte `ts` a timestamp. | HDFS: `config.HDFS_RAW_PATH` (CSV). | HDFS: `config.HDFS_CLEANED_PATH` (Parquet, overwrite). |
| `spark/cleaning/enrich_with_hive.py` | Lee Parquet de cleaned y lo cruza con la tabla Hive de warehouses para enriquecer con datos maestros. | HDFS: `HDFS_CLEANED_PATH`; Hive: `HIVE_WAREHOUSES_TABLE`. | HDFS: `HDFS_ENRICHED_PATH` (Parquet, overwrite). |
| `spark/graph/transport_graph.py` | Construye un grafo con nodos = almacenes (warehouses) y aristas = rutas (routes). Calcula shortest paths y connected components con GraphFrames. | HDFS: `HDFS_WAREHOUSES_PATH`, `HDFS_ROUTES_PATH` (CSV). | HDFS: `HDFS_GRAPH_PATH/shortest_paths`, `HDFS_GRAPH_PATH/connected_components` (Parquet). |
| `spark/streaming/delays_windowed.py` | Job de **streaming**: lee eventos desde Kafka (`raw-data`) o desde CSV en HDFS (`file`). Añade un campo de retraso simulado, agrupa por ventana de 15 min y warehouse_id, escribe cada micro-batch en Hive (`transport.aggregated_delays`) y en MongoDB (`aggregated_delays`). Si el retraso medio supera un umbral, publica una alerta en Kafka (topic `alerts`). | Kafka topic `KAFKA_TOPIC_RAW` o HDFS path raw (CSV). Checkpoint en HDFS. | Hive: `transport.aggregated_delays`; MongoDB: `transport.aggregated_delays`; Kafka: topic `alerts` (solo ventanas anómalas). |
| `spark/streaming/write_to_hive_and_mongo.py` | **Batch**: lee Parquet de la ruta de aggregated_delays en HDFS y hace append en la tabla Hive `transport.aggregated_delays`. No escribe en MongoDB. | HDFS: `HDFS_AGGREGATED_DELAYS_PATH` (Parquet). | Hive: `HIVE_AGGREGATED_DELAYS_TABLE`. |
| `spark/ml/anomaly_detection.py` | Lee la tabla Hive `transport.aggregated_delays`, entrena un K-Means (k=3) sobre `avg_delay_min` y `vehicle_count`, marca como anómalo el cluster con mayor retraso medio. Escribe los registros anómalos en MongoDB (`transport.anomalies`) y publica cada uno en Kafka (topic `alerts`). | Hive: `HIVE_AGGREGATED_DELAYS_TABLE`. | MongoDB: `transport.anomalies`; Kafka: topic `alerts`. |

---

### Scripts Python de utilidad (no Spark)

| Script | Qué hace | Entrada | Salida |
|--------|----------|---------|--------|
| `scripts/ver_grafos_resultados.py` | Lee Parquet de shortest_paths y connected_components (desde carpeta local `resultados/` o indicada con `--dir`). Con `--viz` genera una imagen del grafo (warehouses + routes) en `grafo.png`. | Carpeta local con Parquet (p. ej. copiados desde HDFS) y, para `--viz`, `data/sample/warehouses.csv` y `routes.csv`. | Impresión por consola de tablas; opcional: `grafo.png`. |
| `scripts/gps_simulator.py` | Genera en bucle eventos GPS simulados (vehicle_id, route_id, lat, lon, speed, delay_minutes, timestamp) y los envía al topic Kafka `gps-events` (config en `config.py`). | Ninguna (usa `config.KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC_GPS_EVENTS`). | Kafka: topic `gps-events`; mensajes impresos en consola. |
| `scripts/alerts_consumer.py` | Consumidor Kafka del topic `alerts`. Imprime cada mensaje recibido (alertas de anomalías del batch o del streaming). | Kafka: topic `alerts` (config en `config.py`). | Consola: líneas `[ALERTA] {...}`. |
| `scripts/mongo_to_mariadb_kpi.py` | Lee agregados desde MongoDB (`transport.aggregated_delays`) o desde Parquet en carpeta local (`--source mongo` o `--source parquet`), calcula KPIs por vehículo y por almacén y los inserta en MariaDB en las tablas `kpi_delays_by_vehicle` y `kpi_delays_by_warehouse`. | MongoDB o carpeta `resultados/` (Parquet); `config.py` para URIs. | MariaDB: `sentinel360_analytics.kpi_delays_by_vehicle`, `kpi_delays_by_warehouse`. |

---

## 3. Dónde está el detalle

- **Comandos y supuestos completos**: `docs/HOWTO_EJECUCION.md`
- **Fases KDD y narrativa**: `docs/KDD_FASES.md`, `docs/ARQUITECTURA_SENTINEL360.md`
- **Casos de uso para la defensa**: `docs/CASOS_DE_USO.md`
- **Dashboards (Superset / Grafana)**: `docs/PRESENTACION_ENTORNO_VISUAL.md`, `docs/SUPERSET_DASHBOARDS.md`, `docs/GRAFANA_DASHBOARDS.md`
