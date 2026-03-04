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
2. Crear base y tablas con Beeline (mismo Hive que usarás para consultas):
   ```bash
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/02_routes.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/03_events_raw.sql
   beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql
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

Documentación: `hive/README.md`, `docs/POBLAR_TABLAS_HIVE.md`.

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

## Supuesto 5: Fase III – Streaming (opcional)

Objetivo: ventanas de retrasos y/o carga multicapa (Hive + MongoDB).

```bash
# Modo fichero (datos de ejemplo)
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file

# Modo Kafka (si hay datos en el tema)
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka
```

El job que escribe en `transport.aggregated_delays` y en MongoDB es `spark/streaming/write_to_hive_and_mongo.py` (integrar según tu flujo).

Documentación: `docs/KDD_FASES.md` (Fase III), `docs/SIGUIENTE_PASOS.md`.

---

## Supuesto 6: Verificación global

- **Hive**: `./scripts/verificar_tablas_hive.sh`
- **HDFS**: `hdfs dfs -ls /user/hadoop/proyecto/`
- **YARN**: http://192.168.99.10:8088
- **NiFi**: https://localhost:8443/nifi

---

## Orden recomendado (flujo completo)

1. Supuesto 0 (arranque servicios)  
2. Supuesto 1 (ingesta NiFi → Kafka + HDFS raw)  
3. Supuesto 2 (Hive DDL + ingest_from_local para maestros y raw)  
4. Supuesto 3 (cleaning + enrich)  
5. Supuesto 4 (grafos + visualización)  
6. Opcional: Supuesto 5 (streaming)  
7. Supuesto 6 (verificación)

Documentación relacionada: `README.md`, `docs/KDD_FASES.md`, `docs/ARRANQUE_SERVICIOS.md`.
