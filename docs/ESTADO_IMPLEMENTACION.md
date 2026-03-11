# Estado de implementación – Sentinel360

Revisión del proyecto según el ciclo KDD y el stack documentado. Fecha de revisión: según último commit.

---

## Resumen ejecutivo

| Fase KDD | Estado | Notas |
|----------|--------|--------|
| **Fase I** – Ingesta y selección | ✅ Implementado | NiFi (GPS + PutHDFS + Kafka), flujo importable, docs y verificaciones |
| **Fase II** – Preprocesamiento | ✅ Implementado | Limpieza, enriquecimiento, grafo (Spark + Hive) |
| **Fase III** – Streaming y multicapa | ✅ Implementado | delays_windowed (Kafka→Hive+MongoDB), write_to_hive_and_mongo (batch) |
| **Fase IV** – Orquestación | ✅ Implementado | DAGs Airflow (batch y streaming); requieren ajuste de rutas en despliegue |
| **Extras** | ✅ Implementado | Web presentación (Streamlit), ML anomalías, KPIs→MariaDB, Grafana dashboards |

---

## 1. Configuración y infraestructura

| Elemento | Estado | Ubicación |
|---------|--------|-----------|
| Config centralizada | ✅ | `config.py`: IPs, HDFS, Kafka, Hive, MongoDB, MariaDB |
| Rutas HDFS | ✅ | Definidas en `config.py` y `hdfs/paths.txt` |
| Scripts arranque/parada | ✅ | `scripts/start_servicios.sh`, `stop_servicios.sh` |
| Verificación clúster | ✅ | `scripts/verificar_cluster.sh` |
| Verificación topics Kafka | ✅ | `scripts/verificar_topics_kafka.sh` |
| Verificación ingesta GPS | ✅ | `scripts/verificar_ingesta_gps.sh` (HDFS raw, topics Kafka) |
| Verificación tablas Hive | ✅ | `scripts/verificar_tablas_hive.sh` |
| Instalación Grafana | ✅ | `scripts/install_grafana.sh` (Ubuntu nativo) |
| Setup HDFS | ✅ | `scripts/setup_hdfs.sh` |
| Crear tablas Hive | ✅ | `scripts/crear_tablas_hive.sh` |

---

## 2. Fase I – Ingesta (NiFi, Kafka, HDFS)

| Componente | Estado | Detalle |
|------------|--------|---------|
| Flujo NiFi GPS | ✅ | `ingest/gps_transport_flow_importable.json`: GetFile → UpdateAttribute → PutHDFS, SplitText → EvaluateJsonPath → RouteOnAttribute → PublishKafka raw-data / filtered-data |
| GetFile GPS Logs | ✅ | Directorio `/home/hadoop/data/gps_logs`, filtro JSON/JSONL/CSV |
| PutHDFS | ✅ | Copia raw en `/user/hadoop/proyecto/raw` (Conflict Resolution Strategy corregido en JSON) |
| EvaluateJsonPath | ✅ | Return Type `auto-detect`; extrae vehicle_id, speed, warehouse_id |
| RouteOnAttribute | ✅ | Filtro speed < 120 → filtered-data; resto → raw-data |
| Kafka topics | ✅ | `raw-data`, `filtered-data` (192.168.99.10:9092) |
| Controller Service Kafka | ✅ | Kafka3ConnectionService en el flujo; hay que habilitarlo en la UI |
| Documentación Fase I | ✅ | `ingest/FLUJO_GPS_README.md`, `ingest/nifi/FASE_I_INGESTA.md`, `RESOLVER_ERRORES_FLUJO_GPS.md` |
| Flujo HTTP/OpenWeather | 📄 Doc | `ingest/nifi/FLUJO_HTTP_OPENWEATHER.md`; flujo importable aparte si existe |
| Datos de prueba | ✅ | `data/sample/gps_events.json`, `generate_gps_logs.py`; copia a `gps_logs` para NiFi |

**Pendiente / verificación:** Comprobar que tras ejecutar el flujo hay datos en HDFS (`/user/hadoop/proyecto/raw`) y en Kafka (consumir `raw-data` y `filtered-data`).

---

## 3. Fase II – Preprocesamiento (Spark, Hive)

| Componente | Estado | Detalle |
|------------|--------|---------|
| Esquemas Hive | ✅ | `hive/schema/`: 01_warehouses, 02_routes, 03_events_raw, 04_aggregated_reporting, 05_reporte_diario |
| clean_and_normalize.py | ✅ | Lee raw/procesado, limpia y normaliza → `procesado/cleaned` |
| enrich_with_hive.py | ✅ | Cruce con `transport.warehouses` → `procesado/enriched` |
| transport_graph.py | ✅ | GraphFrames: grafo almacenes + rutas → `procesado/graph` |
| run_spark_submit.sh | ✅ | Lanza jobs con YARN, spark-sql-kafka, graphframes |
| Consultas Hive ejemplo | ✅ | `hive/queries/` (example_report, reporte_diario) |

**Requisitos:** Tablas Hive creadas (01–04), datos en raw (o procesado) y datos maestros en warehouses/routes.

---

## 4. Fase III – Streaming y carga multicapa

| Componente | Estado | Detalle |
|------------|--------|---------|
| delays_windowed.py | ✅ | Consume Kafka `raw-data` (o HDFS file); ventanas 15 min; escribe Hive `aggregated_delays` + MongoDB `aggregated_delays` |
| write_to_hive_and_mongo.py | ✅ | Batch: lee Parquet de `procesado/aggregated_delays` → inserta en tabla Hive |
| Tabla Hive aggregated_delays | ✅ | Definida en 04_aggregated_reporting.sql |
| MongoDB init | ✅ | `mongodb/scripts/init_collection.js`: vehicle_state, aggregated_delays, anomalies |
| Checkpoint streaming | ✅ | `config.py`: STREAMING_CHECKPOINT_PATH en HDFS |

**Nota:** MongoDB se alimenta desde **Spark** (delays_windowed.py), no desde NiFi. Para ver datos en MongoDB hay que tener el job de streaming en marcha (o un batch que escriba agregados).

---

## 5. Fase IV – Orquestación (Airflow)

| Componente | Estado | Detalle |
|------------|--------|---------|
| DAG batch | ✅ | `airflow/dag_sentinel360_batch.py`: clean → enrich → graph → load_aggregated_delays → detect_anomalies → load_kpis_to_mariadb |
| DAG streaming monitoring | ✅ | `airflow/dag_sentinel360_streaming_monitoring.py` |
| start_airflow.sh | ✅ | `scripts/start_airflow.sh` |
| Ajuste en despliegue | ⚠️ | En los DAGs, `PROJECT_DIR` está en `/opt/sentinel360`; cambiar a la ruta real del repo (p. ej. `/home/hadoop/Documentos/ProyectoBigData`) |

---

## 6. ML y analítica

| Componente | Estado | Detalle |
|------------|--------|---------|
| anomaly_detection.py | ✅ | K-Means sobre aggregated_delays; escribe anomalías en MongoDB y Kafka `alerts` |
| mongo_to_mariadb_kpi.py | ✅ | Lee aggregated_delays (Mongo o Parquet), calcula KPIs, inserta en MariaDB |
| MariaDB/Superset | ✅ | Documentado en `docs/PRESENTACION_ENTORNO_VISUAL.md`; docker-compose incluye MariaDB, Superset, Grafana |

---

## 7. Interfaz y presentación

| Componente | Estado | Detalle |
|------------|--------|---------|
| Web presentación (Streamlit) | ✅ | `web/presentacion_sentinel360_app.py`: 6 pestañas KDD (arranque, ingesta, limpieza, grafos, streaming, entorno visual). Lanza scripts y muestra salida. |
| Grafana dashboards | ✅ | `grafana/`: provisioning MariaDB, dashboard KPIs (retrasos por almacén, series temporales, tabla). Docker + script nativo. |
| Documentación | ✅ | `docs/PRESENTACION_INTERFAZ_WEB.md`, `docs/GRAFANA_DASHBOARDS.md`, `grafana/README.md` |

---

## 8. Documentación general

| Documento | Contenido |
|-----------|-----------|
| README.md | Visión general, stack, estructura, clúster, rutas, ejecución |
| docs/KDD_FASES.md | Fases I–IV y orden de ejecución |
| docs/HOWTO_EJECUCION.md | Pasos detallados por supuesto |
| docs/GUION_PRESENTACION.md | Guion defensa y tabla de scripts |
| docs/ARRANQUE_SERVICIOS.md | Arranque/parada de servicios |
| docs/SIGUIENTE_PASOS.md | PutHDFS, orden jobs Spark, Hive DDL |
| docs/KAFKA_TOPICS_SENTINEL360.md | Topics del proyecto |
| docs/HIVE_SENTINEL360.md | Hive en Sentinel360 |
| docs/FASE_III_STREAMING.md | Streaming y carga multicapa |
| docs/CASOS_DE_USO.md | Casos de uso |
| docs/ARQUITECTURA_SENTINEL360.md | Arquitectura de alto nivel |
| docs/AIRFLOW_DAGS.md | Integración DAGs en Airflow |
| docs/GRAFANA_DASHBOARDS.md | Grafana: instalación, datasources, paneles KPIs |
| docs/SUPERSET_DASHBOARDS.md | Dashboards Superset |
| docs/PROBAR_PIPELINE.md | Cómo probar el pipeline end-to-end |

---

## 9. Qué falta o conviene verificar

1. **Ejecución end-to-end en clúster:** Que todos los servicios (HDFS, YARN, Kafka, NiFi, Hive, MongoDB) estén arriba y que el flujo NiFi + jobs Spark se hayan ejecutado al menos una vez.
2. **HDFS:** Confirmar que PutHDFS escribe en `/user/hadoop/proyecto/raw` (ejecutar flujo y `./scripts/verificar_ingesta_gps.sh` o `hdfs dfs -ls ...`).
3. **MongoDB:** Confirmar que hay datos en `transport.aggregated_delays` tras ejecutar `delays_windowed.py` (Kafka con datos).
4. **Airflow:** Ajustar `PROJECT_DIR` en los DAGs a la ruta real del proyecto en el nodo donde corre Airflow.
5. **MariaDB/Superset:** Opcional; si se usan KPIs/dashboards, tener MariaDB creado y `mongo_to_mariadb_kpi.py` (o DAG) ejecutado.

---

## 10. Orden sugerido para comprobar que todo está implementado

1. `./scripts/setup_hdfs.sh` y `./scripts/crear_tablas_hive.sh` (o DDL manual).
2. Subir datos maestros y raw: `./scripts/ingest_from_local.sh` (o copiar a `gps_logs` y dejar que NiFi ingeste).
3. Arrancar NiFi, importar `gps_transport_flow_importable.json`, habilitar Kafka3ConnectionService, poner datos en `gps_logs`, ejecutar flujo.
4. `./scripts/verificar_ingesta_gps.sh` y consumir de Kafka para comprobar mensajes.
5. Ejecutar en orden: `clean_and_normalize.py` → `enrich_with_hive.py` → `transport_graph.py`.
6. Ejecutar `delays_windowed.py` (origen Kafka o file) y comprobar Hive y MongoDB.
7. (Opcional) Ejecutar `anomaly_detection.py` y `mongo_to_mariadb_kpi.py`.
8. (Opcional) Arrancar Airflow, cargar DAGs y ajustar `PROJECT_DIR`.

Con esto el proyecto está **implementado de punta a punta** según las fases KDD documentadas; lo que queda es **verificación en tu entorno** y ajuste de rutas/servicios (Airflow, MariaDB, etc.).
