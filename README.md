# Proyecto Big Data - Monitorización de Red de Transporte Global

Proyecto integral siguiendo el ciclo **KDD** (Knowledge Discovery in Databases) con stack Apache.

## Stack utilizado

| Componente     | Tecnología                    | Uso en el proyecto                          |
|---------------|-------------------------------|---------------------------------------------|
| Ingesta       | NiFi 2.6, Kafka 3.9 (KRaft)   | APIs + logs GPS → temas Kafka → HDFS raw   |
| Procesamiento | Spark 3.5 (SQL, Streaming, GraphFrames) | Limpieza, enriquecimiento, grafos, ventanas |
| Almacenamiento| HDFS, Hive, MongoDB | Raw, agregados (Hive), estado vehículos (MongoDB) |
| Orquestación  | Airflow 2.10                  | DAG re-entrenamiento grafos y limpieza     |
| Recursos      | YARN                          | Ejecución de jobs Spark                     |

## Estructura del proyecto

```
ProyectoBigData/
├── config/              # Configuraciones (Kafka, NiFi, Spark, Hive)
├── ingest/              # Fase I: Ingesta (NiFi, Kafka, HDFS)
├── spark/               # Fase II–III: Jobs Spark (SQL, GraphFrames, Streaming)
├── hive/                # Esquemas y consultas Hive
├── mongodb/             # Scripts y esquemas MongoDB (estado vehículos)
├── airflow/             # Fase IV: DAGs Airflow
├── hdfs/                # Rutas y scripts HDFS
├── data/                # Datos de ejemplo y logs simulados
├── docs/                # Documentación y diagramas
└── scripts/             # Utilidades y lanzamiento
```

## Clúster (refactorizado)

| Nodo   | IP           | Servicios                          |
|--------|--------------|-------------------------------------|
| hadoop (master) | 192.168.99.10 | NameNode, ResourceManager, Kafka, NiFi |
| nodo1  | 192.168.99.12 | DataNode, NodeManager              |
| nodo2  | 192.168.99.14 | DataNode, NodeManager              |

- **HDFS**: `hdfs://192.168.99.10:9000`
- **Kafka**: `192.168.99.10:9092`
- **YARN Web UI**: http://192.168.99.10:8088

Toda la configuración (IPs, rutas, temas) está centralizada en **`config.py`**. Los scripts Python importan estas variables.

## Rutas HDFS del proyecto

- **Raw**: `/user/hadoop/proyecto/raw/`
- **Procesado**: `/user/hadoop/proyecto/procesado/` (cleaned, enriched, graph, aggregated_delays, temp)

## Ejecución en el clúster

1. **Crear rutas HDFS**: `./scripts/setup_hdfs.sh`
2. **Subir datos maestros** (warehouses, routes) y raw: `./scripts/ingest_from_local.sh` (tras generar datos en `data/sample/`).
3. **Lanzar jobs Spark (YARN, 2 ejecutores)**:
   ```bash
   ./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
   ./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
   ./scripts/run_spark_submit.sh spark/graph/transport_graph.py
   ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file   # o "kafka" si Kafka tiene datos
   ```
   El script usa `--master yarn`, `--num-executors 2`, y los packages **spark-sql-kafka** y **graphframes**.
4. **Hive**: ejecutar DDL en `hive/schema/` (las LOCATION apuntan a `/user/hadoop/proyecto/...`). Con Beeline: `beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql` (y 02, 03, 04).

Consultar **`docs/KDD_FASES.md`** para el detalle de cada fase del ciclo KDD.

---

## Documentación para desarrolladores

| Documento | Contenido |
|-----------|-----------|
| [docs/KDD_FASES.md](docs/KDD_FASES.md) | Fases del ciclo KDD (ingesta, limpieza, enriquecimiento, streaming, orquestación) |
| [docs/ARRANQUE_SERVICIOS.md](docs/ARRANQUE_SERVICIOS.md) | Cómo arrancar y parar Kafka, MongoDB, Hive, NiFi, Spark History |
| [docs/SIGUIENTE_PASOS.md](docs/SIGUIENTE_PASOS.md) | PutHDFS en NiFi, orden de jobs Spark, Hive DDL |
| [docs/ANALISIS_HIVE.md](docs/ANALISIS_HIVE.md) | Uso de Hive en el proyecto (maestros, agregados, reporting) |
| [hive/README.md](hive/README.md) | Esquema Hive, scripts 01–05, orden de ejecución |
| [ingest/nifi/FASE_I_INGESTA.md](ingest/nifi/FASE_I_INGESTA.md) | Flujos NiFi (GPS, HTTP), PutHDFS, temas Kafka |
| [ingest/nifi/FLUJO_HTTP_OPENWEATHER.md](ingest/nifi/FLUJO_HTTP_OPENWEATHER.md) | Configuración InvokeHTTP para OpenWeather |
| [mongodb/README.md](mongodb/README.md) | Colección `transport.vehicle_state`, scripts de inicialización |

**Configuración central**: IPs, rutas HDFS, Kafka y Hive están en **`config.py`**; los jobs Spark e ingest lo importan.
