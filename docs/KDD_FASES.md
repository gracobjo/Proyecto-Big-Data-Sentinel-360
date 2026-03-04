# Fases del ciclo KDD en el proyecto

Resumen de cómo se implementa cada fase según el enunciado (ciclo KDD + stack Apache).

---

## Fase I – Ingesta y selección

- **Objetivo**: Ingestar datos de fuentes externas (API + archivos) y publicar en Kafka y HDFS.
- **Herramientas**: NiFi, Kafka.
- **Qué hace**:
  - **GetFile**: lee logs GPS desde `/home/hadoop/data/gps_logs` → publica en temas `raw-data` y `filtered-data`, y copia raw en HDFS.
  - **InvokeHTTP**: llama a OpenWeather (u otra API) → publica en `raw-data` y copia raw en HDFS.
- **Rutas**: HDFS raw = `/user/hadoop/proyecto/raw`. Temas Kafka = `raw-data`, `filtered-data`.
- **Documentación**: `ingest/nifi/FASE_I_INGESTA.md`, `ingest/nifi/FLUJO_HTTP_OPENWEATHER.md`.

---

## Fase II – Preprocesamiento y transformación

- **Objetivo**: Limpiar datos, enriquecer con datos maestros (Hive) y construir grafos.
- **Herramientas**: Spark (SQL, GraphFrames), Hive.
- **Qué hace**:
  - **clean_and_normalize.py**: lee desde raw/procesado, limpia y normaliza → escribe en `procesado/cleaned`.
  - **enrich_with_hive.py**: cruza eventos limpios con `transport.warehouses` → escribe en `procesado/enriched`.
  - **transport_graph.py**: construye grafo (almacenes + rutas) con GraphFrames → escribe en `procesado/graph`.
- **Documentación**: `hive/README.md`, `docs/ANALISIS_HIVE.md`.

---

## Fase III – Minería y acción (streaming y carga multicapa)

- **Objetivo**: Agregaciones en ventanas (p. ej. retrasos 15 min) y carga en Hive + MongoDB.
- **Herramientas**: Spark Structured Streaming, Hive, MongoDB.
- **Qué hace**:
  - **delays_windowed.py**: consume desde Kafka (o ficheros), calcula ventanas → opcionalmente escribe agregados.
  - **write_to_hive_and_mongo.py**: escribe agregados en `transport.aggregated_delays` (Hive) y estado de vehículos en MongoDB.
- **Documentación**: `docs/SIGUIENTE_PASOS.md`, `mongodb/README.md`.

---

## Fase IV – Orquestación (opcional)

- **Objetivo**: Automatizar re-entrenamiento de grafos y limpieza de tablas temporales.
- **Herramientas**: Airflow.
- **Qué hace**: DAG que lanza jobs Spark (limpieza, grafos) y tareas de mantenimiento.
- **Documentación**: `airflow/` (si existe en el proyecto).

---

## Orden de ejecución recomendado

1. Arrancar servicios: `./scripts/start_servicios.sh`
2. Preparar HDFS y datos: `./scripts/setup_hdfs.sh`, `./scripts/ingest_from_local.sh`
3. Crear tablas Hive: `beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql` (y 02, 03, 04)
4. Jobs Spark: cleaning → enrich → graph → streaming (según necesidad)

Ver también: `docs/SIGUIENTE_PASOS.md`, `docs/ARRANQUE_SERVICIOS.md`.
