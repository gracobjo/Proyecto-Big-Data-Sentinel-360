# Datos de ejemplo – Sentinel360

Esta carpeta contiene los **datos de entrada** que usa el proyecto para ingesta, Hive, Spark y grafos. Aquí se explica **de dónde sale cada dataset** y cómo se utiliza.

---

## Resumen: archivos y origen

| Archivo | Descripción | Origen | Uso en el proyecto |
|---------|-------------|--------|--------------------|
| **gps_events.csv** | Eventos de telemetría GPS: posición, velocidad, vehículo, timestamp. | Generado por `data/sample/generate_gps_logs.py` (o similar) o por el simulador en tiempo real. | Raw en HDFS; NiFi/Kafka; Spark Streaming (ventanas de retraso); enriquecimiento con warehouses. |
| **warehouses.csv** | Catálogo de almacenes (nodos del grafo): id, nombre, ciudad, país, lat/lon, capacidad. | Datos maestros estáticos del negocio (catálogo de centros logísticos). | HDFS `warehouses/`; Hive `transport.warehouses`; GraphFrames (vértices); enriquecimiento. |
| **routes.csv** | Rutas entre almacenes (aristas del grafo): origen, destino, distancia, duración media. | Datos maestros estáticos del negocio (topología de la red). | HDFS `routes/`; Hive `transport.routes`; GraphFrames (aristas); análisis de caminos y componentes. |

El script **`scripts/ingest_from_local.sh`** sube todo el contenido de `data/sample/` a HDFS en las rutas `/user/hadoop/proyecto/raw/`, `.../warehouses/` y `.../routes/`.

---

## Detalle por archivo

### gps_events.csv (GPS + tiempo)

- **Campos típicos**: `event_id`, `vehicle_id`, `ts` (timestamp ISO), `lat`, `lon`, `speed`, `warehouse_id` (asignado por lógica de negocio o simulador).
- **Origen**:
  - **Generación batch**: script en `data/sample/` que genera logs con coordenadas y timestamps (p. ej. `generate_gps_logs.py` si existe).
  - **Tiempo real**: `scripts/gps_simulator.py` envía eventos similares al topic Kafka `gps-events` (con `route_id`, `delay_minutes`, etc.).
  - **Producción**: dispositivos GPS en vehículos → NiFi/API → Kafka/HDFS.
- **Cómo afecta el tiempo**: El campo `ts` es la base para ventanas temporales (p. ej. 15 min) en Spark Streaming, agregados por hora/día en Hive y análisis histórico. Sin timestamps correctos, las ventanas y los KPIs por franja horaria no serían válidos.

### warehouses.csv (almacenes)

- **Campos**: `warehouse_id`, `name`, `city`, `country`, `lat`, `lon`, `capacity`.
- **Origen**: Catálogo maestro de la empresa (centros logísticos). En el repo es un CSV estático de ejemplo.
- **Uso**: Nodos del grafo, join en el enriquecimiento de eventos GPS, mapas y reporting por almacén.

### routes.csv (rutas)

- **Campos**: `route_id`, `from_warehouse_id`, `to_warehouse_id`, `distance_km`, `avg_duration_min`.
- **Origen**: Catálogo maestro de rutas entre almacenes (topología de la red). En el repo es un CSV estático de ejemplo. Los identificadores deben coincidir con `warehouse_id` de `warehouses.csv`.
- **Uso**: Aristas del grafo (GraphFrames), análisis de shortest path y componentes conectados; contexto para interpretar retrasos por ruta.

---

## Dependencias entre archivos

- Los eventos GPS pueden llevar `warehouse_id` (almacén asociado) y/o `route_id`; el simulador genera ambos.
- Las **rutas** referencian almacenes por `from_warehouse_id` y `to_warehouse_id` → deben existir en **warehouses.csv**.
- Para que Hive y Spark vean los datos en el clúster, hay que ejecutar `./scripts/ingest_from_local.sh` después de tener estos CSV (o generarlos) en `data/sample/`.
