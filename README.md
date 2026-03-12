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

## Arquitectura de referencia – Sentinel360

### 1. Marco estratégico y propósito del sistema

Sentinel360 se plantea como una solución de **misión crítica** para la visibilidad integral de redes de transporte. El objetivo es pasar de un monitoreo **reactivo** (ver qué ha pasado cuando ya es tarde) a un **descubrimiento de conocimiento proactivo** apoyado en el ciclo **KDD (Knowledge Discovery in Databases)**.

El sistema transforma:

- Telemetría **GPS** masiva (eventos de posición de vehículos).
- Datos de contexto de la API de **OpenWeather**.

en **inteligencia accionable**: detección de cuellos de botella, rutas ineficientes, comportamientos anómalos y KPIs de retrasos.

El uso del **stack Apache** (NiFi, Kafka, Spark, Hive, Airflow) evita la fragmentación de datos, integrando flujos heterogéneos en una plataforma unificada. El dato crudo se convierte en un activo que permite **modelar la red de transporte como una entidad dinámica y observable**.

---

### 2. Infraestructura del clúster y topología de red

La arquitectura se despliega sobre un **clúster multi‑nodo** que separa claramente responsabilidades:

| Nodo              | IP             | Servicios clave                                                |
|-------------------|----------------|----------------------------------------------------------------|
| `hadoop` (master) | `192.168.99.10`| NameNode, ResourceManager, Kafka (KRaft), NiFi, Hive, MariaDB |
| `nodo1`           | `192.168.99.12`| DataNode, NodeManager                                          |
| `nodo2`           | `192.168.99.14`| DataNode, NodeManager                                          |

Toda la configuración se centraliza en **`config.py`**, que actúa como **Single Source of Truth (SSOT)**:

- IPs y puertos de servicios (HDFS, YARN, Kafka, Hive, MongoDB, MariaDB).
- Rutas HDFS base del proyecto.
- Nombres de topics Kafka (`raw-data`, `filtered-data`, `alerts`).
- Rutas de checkpoints de streaming y de salida de cada fase.

Cambios de infraestructura (p. ej. migrar de una IP a otra o cambiar rutas HDFS) se gestionan desde este punto, propagándose automáticamente a jobs Spark, scripts de ingesta y DAGs de Airflow.

---

### 3. El ciclo KDD en Sentinel360

Sentinel360 implementa el ciclo **KDD** extremo a extremo, desde la ingesta `raw` hasta modelos de grafos y anomalías:

1. **Fase I – Ingesta y selección**  
   - **Herramientas**: Apache NiFi 2.x, Apache Kafka 3.x (KRaft), HDFS.  
   - NiFi ingesta logs GPS desde `/home/hadoop/data/gps_logs` y publica en Kafka (`raw-data`, `filtered-data`), además de escribir una copia **raw** en HDFS (`/user/hadoop/proyecto/raw`).  
   - Flujos NiFi importables y documentados en `ingest/` y `ingest/nifi/`.

2. **Fase II – Preprocesamiento, limpieza y enriquecimiento**  
   - **Herramientas**: Apache Spark 3.5, Apache Hive.  
   - Jobs Spark principales:
     - `spark/cleaning/clean_and_normalize.py`: limpia y normaliza eventos `raw` → `procesado/cleaned`.
     - `spark/cleaning/enrich_with_hive.py`: enriquece con maestros de Hive (`warehouses`, `routes`) → `procesado/enriched`.
     - `spark/graph/transport_graph.py`: genera el grafo almacenes–rutas con GraphFrames → `procesado/graph`.
   - Las tablas Hive (`01_warehouses.sql`, `02_routes.sql`, `03_events_raw.sql`, `04_aggregated_reporting.sql`) apuntan con `LOCATION` a estas rutas Parquet.

3. **Fase III – Streaming de retrasos y anomalías**  
   - **Herramientas**: Spark Structured Streaming, Kafka, Hive, MongoDB.  
   - `spark/streaming/delays_windowed.py`:
     - Lee de `raw-data` o de ficheros HDFS (`file` mode).
     - Calcula métricas de retrasos en ventanas de 15 minutos.
     - Escribe en Hive (`aggregated_delays`) y en MongoDB (`transport.aggregated_delays`).
     - Publica alertas en el topic Kafka `alerts`.  
   - `spark/ml/anomaly_detection.py`:
     - Aplica K‑Means sobre los agregados de retrasos.
     - Marca anomalías en MongoDB (`transport.anomalies`) y puede publicar nuevas alertas en Kafka.

4. **Fase IV – Orquestación y recarga**  
   - **Herramientas**: Apache Airflow 2.10.  
   - DAGs en `airflow/` coordinan:
     - Limpieza → enriquecimiento → grafo → carga de agregados → anomalías.
     - Cargas de KPIs hacia MariaDB (`sentinel360_analytics`) para dashboards en Superset/Grafana.

El repositorio `raw` en HDFS (`/user/hadoop/proyecto/raw`) actúa como **copia inmutable**, permitiendo re‑procesar datos si cambian reglas de negocio o algoritmos sin perder el histórico original.

---

### 4. Arquitectura de almacenamiento y modelado

Sentinel360 aplica una estrategia de **almacenamiento políglota**:

- **HDFS – capa física de datos**
  - `/user/hadoop/proyecto/raw/`: datos crudos.
  - `/user/hadoop/proyecto/procesado/cleaned/`: datos limpios.
  - `/user/hadoop/proyecto/procesado/enriched/`: datos enriquecidos con maestros.
  - `/user/hadoop/proyecto/procesado/graph/`: resultados de grafos.
  - Rutas de checkpoints de streaming definidas en `config.py`.

- **Hive – capa analítica**
  - Tablas declaradas en `hive/schema/` (`warehouses`, `routes`, `events_raw`, `aggregated_delays`, etc.) que apuntan a rutas Parquet en `/procesado/`.
  - Permite consultar en SQL lo que Spark genera en batch/streaming.

- **MongoDB – capa operativa / near‑real time**
  - Base de datos `transport` con colecciones:
    - `vehicle_state`: estado más reciente de cada vehículo.
    - `aggregated_delays`: agregados de retrasos por ventana.
    - `anomalies`: anomalías detectadas por el modelo.  
  - Se utiliza para dashboards y servicios que requieren lecturas/escrituras de baja latencia.

---

### 5. Orquestación y operación del pipeline

La operación del sistema se apoya en scripts y en Airflow:

1. **Inicialización y HDFS**  
   - `./scripts/setup_hdfs.sh`: crea la estructura de directorios en HDFS según `config.py`.  
   - `./scripts/crear_tablas_hive.sh`: ejecuta los DDL de `hive/schema/`.

2. **Ingesta de datos maestros y ejemplo**  
   - Scripts en `scripts/` y `ingest/` copian `warehouses.csv`, `routes.csv` y datos GPS de ejemplo a las rutas esperadas.

3. **Jobs Spark (batch + streaming)**  
   - `./scripts/run_spark_submit.sh <script.py>` encapsula la llamada a `spark-submit` (YARN, jars de Hive, `--local` cuando hace falta).  
   - Se usa para los módulos de limpieza, enriquecimiento, grafos, streaming de retrasos y anomalías.

4. **Orquestación con Airflow**  
   - DAGs en `airflow/` ejecutan el orden correcto de tareas y soportan re‑ejecuciones programadas.

5. **Presentación y validación**  
   - La app Streamlit (`web/presentacion_sentinel360_app.py`) actúa como panel KDD:
     - Lanza scripts clave con un clic.
     - Muestra logs y datos de ejemplo.
     - Integra documentación (`docs/*.md`) y navegación entre fases para la defensa.

En conjunto, la arquitectura convierte los datos de transporte aparentemente caóticos en una **red logística inteligente**, monitorizable y auditable de extremo a extremo.

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
├── docker/              # MariaDB, Superset, Grafana (docker compose)
├── grafana/             # Provisioning Grafana (datasources, dashboards KPIs)
├── web/                 # Interfaz presentación Streamlit (panel KDD)
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

**Topics Kafka del proyecto** (solo dos): **raw-data** (entrada principal: NiFi GPS + OpenWeather) y **filtered-data** (datos filtrados, consumo downstream). Ver y comprobar: `docs/KAFKA_TOPICS_SENTINEL360.md`, `./scripts/verificar_topics_kafka.sh`.

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

## Interfaz web y dashboards

- **Streamlit** (panel de presentación KDD): `pip install streamlit pandas && streamlit run web/presentacion_sentinel360_app.py` → http://localhost:8501
- **Grafana** (KPIs): con Docker: `cd docker && docker compose up -d mariadb grafana` → http://localhost:3000 (admin/admin). Dashboards en carpeta *Sentinel360*.
- **Estado de implementación**: ver `docs/ESTADO_IMPLEMENTACION.md`.

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
| [docs/KAFKA_TOPICS_SENTINEL360.md](docs/KAFKA_TOPICS_SENTINEL360.md) | **Topics del proyecto**: raw-data (entrada NiFi) y filtered-data (filtrados) |
| [docs/HIVE_SENTINEL360.md](docs/HIVE_SENTINEL360.md) | **Hive**: dónde buscar, crear tablas (crear_tablas_hive.sh), poblar y comprobar |
| [docs/HOWTO_EJECUCION.md](docs/HOWTO_EJECUCION.md) | **Guía de ejecución**: paso a paso por supuestos (ingesta, Hive, Spark, grafos, streaming) |
| [docs/GUION_PRESENTACION.md](docs/GUION_PRESENTACION.md) | **Guion corto** para la defensa: orden de pasos y tabla de scripts (qué hace cada uno, entrada/salida) |
| [data/sample/README.md](data/sample/README.md) | **Origen de los datos**: GPS, rutas (`routes.csv`), almacenes (`warehouses.csv`); de dónde salen y cómo se usan |
| [docs/FASE_III_STREAMING.md](docs/FASE_III_STREAMING.md) | Fase III: streaming (ventanas 15 min), escritura en Hive y MongoDB |
| [docs/PRESENTACION_INTERFAZ_WEB.md](docs/PRESENTACION_INTERFAZ_WEB.md) | Interfaz web de presentación (Streamlit) para recorrer el ciclo KDD y lanzar scripts |
| [docs/GRAFANA_DASHBOARDS.md](docs/GRAFANA_DASHBOARDS.md) | Grafana: dashboards de KPIs, provisioning MariaDB (Docker + nativo) |
| [docs/SUPERSET_DASHBOARDS.md](docs/SUPERSET_DASHBOARDS.md) | Dashboards analíticos en Superset |
| [docs/FUNCIONALIDADES_RECIENTES.md](docs/FUNCIONALIDADES_RECIENTES.md) | Grafos, visualización, verificación Hive y correcciones aplicadas |
| [docs/VISUALIZAR_GRAFOS.md](docs/VISUALIZAR_GRAFOS.md) | Cómo ver los Parquet y generar grafo.png (red de almacenes y rutas) |
| [docs/POBLAR_TABLAS_HIVE.md](docs/POBLAR_TABLAS_HIVE.md) | Cómo se pueblan las tablas de `transport` y script de verificación |
| [docs/PRESENTACION_ENTORNO_VISUAL.md](docs/PRESENTACION_ENTORNO_VISUAL.md) | Entorno visual para la demo: MariaDB + Superset, KPIs y dashboards |
| [docs/CASOS_DE_USO.md](docs/CASOS_DE_USO.md) | Casos de uso de Sentinel360 (operador, planificación, anomalías, simulación) |
| [docs/ARQUITECTURA_SENTINEL360.md](docs/ARQUITECTURA_SENTINEL360.md) | Visión arquitectónica de alto nivel (clúster, KDD, stack Apache, almacenamiento) |
| [docs/AIRFLOW_DAGS.md](docs/AIRFLOW_DAGS.md) | Cómo integrar y ejecutar los DAGs de Sentinel360 en Apache Airflow |
| [docs/ESTADO_IMPLEMENTACION.md](docs/ESTADO_IMPLEMENTACION.md) | Estado actual de implementación de todas las fases KDD |

**Configuración central de Sentinel360**: IPs, rutas HDFS, Kafka (incl. temas `gps-events` y `alerts`), Hive, MongoDB (incl. colección `anomalies`) y MariaDB (`sentinel360_analytics`) están en **`config.py`**; los scripts Python y jobs Spark importan las variables que necesitan. Para sobrescribir en un entorno concreto puedes usar variables de entorno (p. ej. `MONGO_URI`, `MARIA_DB_URI`).
