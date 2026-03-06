# Sentinel360

Monitorización de red de transporte global siguiendo el ciclo **KDD** (Knowledge Discovery in Databases) con stack Apache.

## Por qué el nombre Sentinel360

- **Sentinel**: hace referencia a un **sistema de vigilancia** que monitoriza continuamente el estado de la red de transporte.
- **360**: alude a una **visión completa del sistema**, combinando:
  - **Datos en tiempo real** (streaming, estado de vehículos).
  - **Datos históricos** (almacenamiento y agregados para análisis).
  - **Análisis predictivo** (modelos y KPIs que ayudan a anticipar incidencias).

## Stack utilizado

| Componente     | Tecnología                    | Uso en Sentinel360                           |
|---------------|-------------------------------|---------------------------------------------|
| Ingesta       | NiFi 2.6, Kafka 3.9 (KRaft)   | APIs + logs GPS → temas Kafka → HDFS raw   |
| Procesamiento | Spark 3.5 (SQL, Streaming, GraphFrames) | Limpieza, enriquecimiento, grafos, ventanas |
| Almacenamiento| HDFS, Hive, MongoDB | Raw, agregados (Hive), estado vehículos (MongoDB) |
| Orquestación  | Airflow 2.10                  | DAG re-entrenamiento grafos y limpieza     |
| Recursos      | YARN                          | Ejecución de jobs Spark                     |

## Estructura del proyecto Sentinel360

```
Sentinel360/   (o ProyectoBigData/ según nombre de la carpeta local)
├── config/              # Configuraciones (Kafka, NiFi, Spark, Hive)
├── ingest/              # Fase I: Ingesta (NiFi, Kafka, HDFS)
├── spark/               # Fase II–III: Jobs Spark (SQL, GraphFrames, Streaming)
├── hive/                # Esquemas y consultas Hive
├── mongodb/             # Scripts y esquemas MongoDB (estado vehículos)
├── airflow/             # Fase IV: DAGs Airflow
├── hdfs/                # Rutas y scripts HDFS
├── data/                # Datos de ejemplo y logs simulados
├── docs/                # Documentación, diagramas e infografías
├── docker/              # Ficheros de apoyo para despliegues dockerizados
├── unnamed.png          # Infografía general de la arquitectura Sentinel360
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

Toda la configuración de Sentinel360 (IPs, rutas, temas) está centralizada en **`config.py`**. Los scripts Python importan estas variables.

## Rutas HDFS (Sentinel360)

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
| [docs/ANALISIS_HIVE.md](docs/ANALISIS_HIVE.md) | Uso de Hive en Sentinel360 (maestros, agregados, reporting) |
| [hive/README.md](hive/README.md) | Esquema Hive, scripts 01–05, orden de ejecución |
| [ingest/nifi/FASE_I_INGESTA.md](ingest/nifi/FASE_I_INGESTA.md) | Flujos NiFi (GPS, HTTP), PutHDFS, temas Kafka |
| [ingest/nifi/FLUJO_HTTP_OPENWEATHER.md](ingest/nifi/FLUJO_HTTP_OPENWEATHER.md) | Configuración InvokeHTTP para OpenWeather |
| [mongodb/README.md](mongodb/README.md) | Colección `transport.vehicle_state`, scripts de inicialización |
| [docs/HOWTO_EJECUCION.md](docs/HOWTO_EJECUCION.md) | **Guía de ejecución**: paso a paso por supuestos (ingesta, Hive, Spark, grafos, streaming) |
| [docs/GUION_PRESENTACION.md](docs/GUION_PRESENTACION.md) | **Guion corto** para la defensa: orden de pasos y tabla de scripts (qué hace cada uno, entrada/salida) |
| [docs/FASE_III_STREAMING.md](docs/FASE_III_STREAMING.md) | Fase III: streaming (ventanas 15 min), escritura en Hive y MongoDB |
| [docs/FUNCIONALIDADES_RECIENTES.md](docs/FUNCIONALIDADES_RECIENTES.md) | Grafos, visualización, verificación Hive y correcciones aplicadas |
| [docs/VISUALIZAR_GRAFOS.md](docs/VISUALIZAR_GRAFOS.md) | Cómo ver los Parquet y generar grafo.png (red de almacenes y rutas) |
| [docs/POBLAR_TABLAS_HIVE.md](docs/POBLAR_TABLAS_HIVE.md) | Cómo se pueblan las tablas de `transport` y script de verificación |
| [docs/PRESENTACION_ENTORNO_VISUAL.md](docs/PRESENTACION_ENTORNO_VISUAL.md) | Entorno visual para la demo: MariaDB + Superset, KPIs y dashboards |
| [docs/CASOS_DE_USO.md](docs/CASOS_DE_USO.md) | Casos de uso de Sentinel360 (operador, planificación, anomalías, simulación) |
| [docs/ARQUITECTURA_SENTINEL360.md](docs/ARQUITECTURA_SENTINEL360.md) | Visión arquitectónica de alto nivel (clúster, KDD, stack Apache, almacenamiento) |
| [docs/AIRFLOW_DAGS.md](docs/AIRFLOW_DAGS.md) | Cómo integrar y ejecutar los DAGs de Sentinel360 en Apache Airflow |

**Configuración central de Sentinel360**: IPs, rutas HDFS, Kafka (incl. temas `gps-events` y `alerts`), Hive, MongoDB (incl. colección `anomalies`) y MariaDB (`sentinel360_analytics`) están en **`config.py`**; los scripts Python y jobs Spark importan las variables que necesitan. Para sobrescribir en un entorno concreto puedes usar variables de entorno (p. ej. `MONGO_URI`, `MARIA_DB_URI`).
