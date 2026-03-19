# Comprobación de cumplimiento – Requisitos Sentinel360

Este documento contrasta el contenido de `.kiro/specs/sentinel360-requirements/requirements.md` con el estado actual del repositorio (código, scripts y documentación).

---

## Resumen ejecutivo

| Requisito | Estado | Notas |
|-----------|--------|--------|
| R1 – Ingesta GPS NiFi → Kafka/HDFS | ✅ Cumple | Documentado y configurado en NiFi; scripts y docs referencian raw-data, filtered-data, PutHDFS |
| R2 – Ingesta OpenWeather | ✅ Cumple | NiFi (doc) + script `ingest_openweather.py` alternativo; topic raw-data |
| R3 – Almacenamiento inmutable HDFS | ✅ Cumple | config.py con rutas raw/procesado; jobs escriben en cleaned, enriched, graph, etc. |
| R4 – Limpieza y normalización | ✅ Cumple | Parquet, ts normalizado, dropna(vehicle_id, ts, lat, lon), descarte speed &lt;0 o &gt;300 con registro en log, YARN |
| R5 – Enriquecimiento con maestros | ✅ Cumple | enrich_with_hive.py: join con transport.warehouses, escritura en enriched; DDL en hive/schema |
| R6 – Modelado grafo (GraphFrames) | ✅ Cumple | transport_graph.py: GraphFrames, shortest paths, connected components; entrada desde HDFS CSV |
| R7 – Streaming ventanas 15 min | ✅ Cumple | delays_windowed.py: Kafka raw-data/file, Hive+Mongo, alertas &gt;20 min, watermark 10 min, checkpoint |
| R8 – Detección anomalías K-Means | ✅ Cumple | anomaly_detection.py: k=3, Hive→Mongo anomalies, Kafka alerts type ANOMALY |
| R9 – Exportación KPIs a MariaDB | ✅ Cumple | mongo_to_mariadb_kpi.py: Mongo/Parquet→KPIs→MariaDB sentinel360_analytics |
| R10 – Visualización Grafana | ✅ Cumple | docker-compose Grafana, MariaDB; docs y provisioning |
| R11 – Análisis histórico Superset | ✅ Cumple | Superset en docker-compose, MariaDB; filtros y Hive documentados |
| R12 – Orquestación Airflow | ✅ Cumple | DAGs Fase I/II/III batch/streaming, retries, reporte_ejecucion por DAG, config.py como SSOT |
| R13 – Interfaz Streamlit | ✅ Cumple | ≥7 secciones, botones ejecución, upload GPS/rutas/almacenes, mapa, dashboard Mongo, buscador KDD |
| R14 – Simulación GPS | ✅ Cumple | gps_simulator.py (gps-events, campos requeridos); generate_synthetic_gps.py desde warehouses/routes |
| R15 – Consumo/visualización alertas | ✅ Cumple | alerts_consumer.py consume topic alerts y muestra por consola; tipos ANOMALY y ANOMALY_STREAMING |
| R16 – Configuración y despliegue | ✅ Cumple | config.py centralizado; variables de entorno; start/stop_servicios.sh; scripts verificar_*; docker-compose |
| RNF-1 a RNF-6 | ✅ / ⚠️ | Ver sección RNF más abajo |

---

## Requisitos funcionales – detalle

### R1: Ingesta de datos GPS desde NiFi hacia Kafka y HDFS

- **Cumple.** Documentación en `ingest/FLUJO_GPS_README.md`, `ingest/nifi/FASE_I_INGESTA.md` y diseño en `.kiro/specs/.../design.md` describen: GetFile → PublishKafka `raw-data`, filtro speed &lt; 120 → `filtered-data`, PutHDFS `/user/hadoop/proyecto/raw`. Scripts `preparar_ingesta_nifi.sh` crean temas `raw-data` y `filtered-data`. Campos GPS documentados: event_id, vehicle_id, ts, lat, lon, speed, warehouse_id.

### R2: Ingesta de datos meteorológicos desde OpenWeather

- **Cumple.** `scripts/ingest_openweather.py` publica en `raw-data`; documentación NiFi HTTP en `ingest/nifi/FLUJO_HTTP_OPENWEATHER.md`. Alternativa sin NiFi cubierta.

### R3: Almacenamiento inmutable en HDFS

- **Cumple.** `config.py` define `HDFS_RAW_PATH`, `HDFS_PROCESSED_PATH` y subrutas cleaned, enriched, graph, aggregated_delays, temp. Jobs de limpieza leen de raw y escriben en procesado sin borrar raw.

### R4: Limpieza y normalización de eventos GPS (Fase II)

- **Cumple.** Job `clean_and_normalize.py`: lectura desde raw, eliminación de registros con `vehicle_id`, `ts`, `lat` o `lon` nulos (`dropna(subset=...)`), descarte de registros con velocidad &lt; 0 o &gt; 300 km/h con mensaje en log de ejecución (y muestra de hasta 5 ejemplos), normalización de `ts` a timestamp, escritura en Parquet en `cleaned`, ejecución sobre YARN. Se aceptan nombres alternativos de columna (`timestamp`→`ts`, `latitude`→`lat`, `longitude`→`lon`).

### R5: Enriquecimiento con datos maestros (Fase II)

- **Cumple.** `enrich_with_hive.py` hace join con `transport.warehouses` por `warehouse_id` y escribe en `enriched`. Esquemas DDL en `hive/schema/01_warehouses.sql` y `02_routes.sql`.

### R6: Modelado de la red logística como grafo (Fase II)

- **Cumple.** `transport_graph.py` usa GraphFrames, vértices desde warehouses y aristas desde routes con peso `distance_km`, calcula shortest paths y connected components, escribe en `graph/`. La entrada es CSV en HDFS (warehouses/routes); si `transport.routes` está vacía en Hive no se comprueba en este job (el job lee desde HDFS).

### R7: Streaming de retrasos en ventanas temporales (Fase III)

- **Cumple.** `delays_windowed.py`: agrupa por ventana 15 min y `warehouse_id`, calcula `avg_delay_min` y `vehicle_count`; escribe en Hive `transport.aggregated_delays` (append) y en MongoDB `transport.aggregated_delays`; publica alerta en Kafka `alerts` cuando `avg_delay_min` &gt; 20 con campos type, warehouse_id, window_start, window_end, avg_delay_min, vehicle_count, threshold; watermark 10 minutos; checkpoint en HDFS vía `config.STREAMING_CHECKPOINT_PATH`; modo kafka y file; continúa sin Mongo si falla la escritura en Mongo.

### R8: Detección de anomalías mediante K-Means (Fase III)

- **Cumple.** `anomaly_detection.py`: carga desde Hive `transport.aggregated_delays`, K-Means k=3 sobre avg_delay_min y vehicle_count, cluster de mayor retraso como anómalo; escribe en MongoDB `transport.anomalies` con los campos indicados; publica en Kafka `alerts` con type "ANOMALY"; manejo de tabla vacía (mensaje informativo y salida sin error).

### R9: Exportación de KPIs a MariaDB para dashboards

- **Cumple.** `mongo_to_mariadb_kpi.py` lee desde MongoDB (o Parquet como alternativa), calcula KPIs y escribe en MariaDB `sentinel360_analytics`. Documentación y uso con `--source mongo` / Parquet.

### R10: Visualización de KPIs en Grafana

- **Cumple.** `docker-compose.yml` incluye Grafana con MariaDB como fuente; documentación y provisioning en `grafana/`. Paneles (retraso medio, top almacenes, vehículos activos) dependen de la definición concreta en dashboards.

### R11: Análisis histórico en Superset

- **Cumple.** Superset en docker-compose conectado a MariaDB; documentación de filtros y consultas; Hive `transport.aggregated_delays` documentado para histórico.

### R12: Orquestación del pipeline mediante Airflow

- **Cumple.** DAGs en `airflow/`: Fase I (Kafka topics, ingesta GPS, OpenWeather), Fase II (limpieza, enriquecimiento, grafo), Fase III batch (agregados, anomalías, KPIs MariaDB), streaming (`delays_windowed.py`). Varios DAGs con `retries` ≥ 1 y `retry_delay` 2–5 min. Tarea final `reporte_ejecucion` (write_dag_run_report) genera informe por ejecución. `config.py` y variable `sentinel360_project_dir` como SSOT.

### R13: Interfaz web de presentación del ciclo KDD (Streamlit)

- **Cumple.** `web/presentacion_sentinel360_app.py`: al menos 7 secciones navegables (arranque, Fase I, Fase II limpieza/enriquecimiento, Fase II grafos, Fase III, entorno visual, dashboard), más 6.1 Incidencias y 6.2 Histórico/SLA; botones que lanzan scripts y muestran salida; `st.file_uploader` para GPS (CSV/JSON), rutas (CSV) y almacenes (CSV); mapa interactivo (Folium/st_folium y st.map); dashboard con agregados y anomalías desde MongoDB (y modo demo); buscador de conceptos KDD en la barra lateral.

### R14: Simulación de datos GPS para pruebas

- **Cumple.** `scripts/gps_simulator.py` genera eventos con vehicle_id, route_id, lat, lon, speed, delay_minutes, timestamp y publica en `gps-events` (configurable). `data/sample/generate_synthetic_gps.py` genera CSV y JSON Lines a partir de `warehouses.csv` y `routes.csv`.

### R15: Consumo y visualización de alertas

- **Cumple.** `scripts/alerts_consumer.py` consume el topic `alerts` y muestra cada alerta por consola (objeto completo con tipo, almacén, ventana, retraso). Tipos ANOMALY (batch) y ANOMALY_STREAMING (streaming) documentados y generados por el pipeline.

### R16: Configuración centralizada y despliegue

- **Cumple.** `config.py` centraliza IPs, rutas HDFS, topics Kafka, tablas Hive, URIs Mongo/MariaDB y checkpoint. Variables de entorno MONGO_URI, MARIA_DB_* documentadas y usadas. `start_servicios.sh` y `stop_servicios.sh` gestionan servicios. Scripts de verificación: `verificar_cluster.sh`, `verificar_topics_kafka.sh`, `verificar_tablas_hive.sh`, `verificar_ingesta_gps.sh`, `verificar_nifi.sh`, `verificar_conexion_superset_mariadb.sh`. `docker-compose.yml` levanta MariaDB, Superset y Grafana.

---

## Requisitos no funcionales (resumen)

- **RNF-1 (Rendimiento streaming):** Checkpoint y configuración YARN/Kafka documentados; latencia y particiones dependen del despliegue.
- **RNF-2 (Disponibilidad):** Checkpoint para reanudación; reintentos en Airflow.
- **RNF-3 (Escalabilidad):** Añadir nodos YARN/HDFS sin cambiar jobs; simulador y docs mencionan flota.
- **RNF-4 (Mantenibilidad):** config.py como SSOT; documentación en docs/ y README por componente; scripts de verificación.
- **RNF-5 (Seguridad):** Credenciales por variables de entorno; Grafana con usuario/contraseña.
- **RNF-6 (Observabilidad):** Logs en jobs Spark; Airflow con historial; YARN UI en 8088 documentado.

---

## Acciones recomendadas (opcionales)

1. **NiFi:** Revisar que el flujo importable incluya GetFile → PublishKafka (raw-data y filtered-data) y PutHDFS a `/user/hadoop/proyecto/raw` con filtro de velocidad 120 km/h.

2. **R15:** En `alerts_consumer.py`, formatear la salida por consola de forma explícita (tipo, almacén, ventana temporal, retraso medio) para alinearlo al 100 % con el criterio de aceptación.

---

*Generado a partir de `.kiro/specs/sentinel360-requirements/requirements.md` y del estado del repositorio.*
