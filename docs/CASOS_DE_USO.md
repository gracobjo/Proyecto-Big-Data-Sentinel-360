## Casos de uso de Sentinel360

Este documento describe los principales **casos de uso** de Sentinel360, conectando:

- Los **actores** (quién usa el sistema).
- Los **objetivos de negocio**.
- Los **datos y componentes Big Data** implicados.
- Las **salidas** (consultas, dashboards, alertas).

Está pensado para poder copiarse casi tal cual a la memoria del proyecto.

---

## Origen de los datos

Los datos de entrada de Sentinel360 provienen de tres fuentes principales:

| Dato | Archivo / origen | Descripción breve |
|------|------------------|-------------------|
| **GPS + tiempo** | `data/sample/gps_events.csv`, simulador `scripts/gps_simulator.py`, NiFi | Eventos de telemetría: posición (lat/lon), velocidad, `vehicle_id`, **timestamp** (`ts`). Son la base del streaming y de los agregados por ventana. |
| **Rutas** | **`data/sample/routes.csv`** | Catálogo maestro de rutas entre almacenes: `route_id`, `from_warehouse_id`, `to_warehouse_id`, `distance_km`, `avg_duration_min`. Define la topología de la red (aristas del grafo). |
| **Almacenes** | `data/sample/warehouses.csv` | Catálogo maestro de centros logísticos: `warehouse_id`, nombre, ciudad, lat/lon, capacidad. Nodos del grafo y contexto para enriquecimiento. |

El script `scripts/ingest_from_local.sh` sube estos CSV a HDFS; las tablas Hive `transport.warehouses` y `transport.routes` apuntan a esas rutas. Detalle de cada archivo, campos y uso: **[data/sample/README.md](../data/sample/README.md)**.

---

## Factores que afectan los resultados: tiempo y otras variables

### Cómo afecta el tiempo (y qué sí tenemos en cuenta)

- **Ventanas temporales**: El streaming agrupa eventos por ventanas de tiempo (p. ej. 15 minutos). El **timestamp** de cada evento (`ts`) determina a qué ventana pertenece y, por tanto, los agregados de retraso por ventana (Hive, MongoDB, alertas).
- **Agregados históricos**: En Hive y MariaDB se pueden hacer consultas por **hora del día**, **día de la semana** o **mes**. El tiempo es la dimensión principal para ver “a qué horas/días hay más retrasos” y para planificación (CU2).
- **Alertas en tiempo casi real**: Las alertas se disparan cuando el retraso medio en una ventana supera un umbral; sin una **referencia temporal correcta** (ventana actual vs. histórico), las alertas no serían interpretables.
- **Limitación actual**: El modelo de anomalías (K-Means) usa `avg_delay_min` y `vehicle_count` por ventana, pero **no incluye de forma explícita** la hora del día o el día de la semana como características. Por tanto, un retraso “normal” en hora punta podría mezclarse con anomalías si no se segmenta por franja horaria.

### Variables que podrían afectar y no estamos teniendo en cuenta

Estas variables influyen en la realidad sobre retrasos y calidad del servicio, pero en el estado actual del proyecto **no se usan como entrada** (o solo de forma parcial):

| Variable | Efecto típico | Estado en Sentinel360 |
|----------|----------------|----------------------|
| **Meteorología** | Lluvia, nieve, viento → más retrasos y menor velocidad. | OpenWeather se menciona en la arquitectura (NiFi/API), pero **no se integra de forma sistemática** en el modelo de retrasos ni en las alertas. |
| **Franja horaria / día de la semana** | Hora punta vs. valle; lunes vs. domingo. | Se pueden hacer consultas en Hive por hora/día, pero el **modelo de anomalías** y las ventanas **no normalizan** por “retraso esperado en esta franja”. |
| **Tipo de vehículo o ruta** | Autobús urbano vs. largo recorrido; tipo de ruta (urbana, interurbana). | No hay dimensión **tipo_vehiculo** o **tipo_ruta** en los agregados; el análisis es por `warehouse_id` / ventana. |
| **Carga / ocupación** | Más pasajeros o carga → más tiempo en paradas y más variabilidad. | No hay dato de **carga u ocupación** en los eventos GPS ni en los maestros. |
| **Obras, eventos, incidencias** | Accidentes, cortes, conciertos, manifestaciones. | No hay fuente de **eventos externos** ni banderas de “incidencia conocida” para filtrar o explicar picos. |
| **Mantenimiento / estado del vehículo** | Vehículo en revisión o con avería. | No hay campo **estado_mantenimiento** ni integración con sistemas de taller. |
| **Calendario (festivos, vacaciones)** | Menor demanda o patrones distintos. | No se usa **calendario laboral/festivos** para ajustar umbrales o interpretar anomalías. |

Incorporar estas variables requeriría: (1) nuevas fuentes de datos o campos en los eventos, (2) enriquecimiento en el pipeline (p. ej. unir con clima o calendario), y (3) modelos que usen esas características (p. ej. retraso esperado por ruta + hora + clima). La documentación de la API OpenWeather y de los flujos NiFi está en `ingest/nifi/` para una futura integración de clima.

---

## Resumen rápido de casos de uso

| Caso de uso | Actor principal | Objetivo | Componentes clave |
|-------------|----------------|----------|-------------------|
| CU1 – Monitorización de retrasos por ruta | Operador de tráfico | Ver qué rutas van peor y priorizar acciones | NiFi, Kafka, Spark, HDFS/Hive, Superset |
| CU2 – Análisis histórico y planificación | Responsable de planificación | Detectar patrones de retrasos y rediseñar horarios/rutas | HDFS, Hive, Spark, Superset/MariaDB |
| CU3 – Detección de anomalías en la flota | Centro de control / IA | Identificar vehículos con comportamiento anómalo | Kafka, Spark ML, MongoDB, Grafana/Superset |
| CU4 – Simulación y prueba del sistema | Equipo técnico / docente | Probar el pipeline extremo a extremo con datos realistas | Simulador GPS, Kafka, Spark, HDFS, MongoDB |
| CU5 – Orquestación y operación del pipeline | Equipo de operaciones | Ejecutar y mantener el pipeline de forma reproducible | Airflow, scripts de arranque, jobs Spark |

---

## CU1 – Monitorización de retrasos por ruta (tiempo casi real)

- **Actor principal**: Operador de tráfico / centro de control.
- **Objetivo**: disponer de una visión clara de:
  - Qué rutas presentan más retrasos.
  - Qué vehículos están teniendo más incidencias en una ventana reciente.

### Flujo de datos implicado

1. **Ingesta**
   - Datos GPS de la flota (simulador / logs reales) → NiFi → Kafka (`gps-events` / `filtered-events`).
   - Datos de tráfico desde API HTTP → NiFi → Kafka (`traffic-events`).
2. **Procesamiento**
   - Spark Streaming une GPS + tráfico, calcula retrasos y genera ventanas agregadas.
   - Se escribe en:
     - **HDFS/Hive** (`transport.aggregated_delays`).
     - **MongoDB** (`transport.aggregated_delays`, `vehicle_state`).
3. **Capa analítica / visual**
   - Proceso batch (script o Airflow) vuelca agregados en MariaDB (`kpi_delays_by_route`, `kpi_delays_by_vehicle`).
   - Superset muestra:
     - Retraso medio por ruta.
     - Top N rutas con más retraso.
     - Top N vehículos más problemáticos.

### Valor aportado

- Permite al operador:
  - Identificar en minutos las rutas con peor servicio.
  - Decidir dónde enviar refuerzos o ajustar frecuencias.
  - Explicar con datos objetivos el nivel de servicio prestado.

---

## CU2 – Análisis histórico y planificación de la red

- **Actor principal**: Responsable de planificación / analista de negocio.
- **Objetivo**: usar el histórico para:
  - Detectar patrones de retraso por ruta, franja horaria y día de la semana.
  - Tomar decisiones de rediseño de rutas y horarios.

### Flujo de datos implicado

1. **Almacenamiento histórico**
   - Todo el flujo de streaming se persiste en HDFS en diferentes capas:
     - `/data/raw/`
     - `/data/curated/`
     - `/data/analytics/`
2. **Modelo de datos analítico**
   - Hive expone tablas como:
     - `gps_curated`
     - `aggregated_delays`
   - MariaDB recibe KPIs de alto nivel (retraso medio por ruta, puntualidad, etc.).
3. **Consultas típicas**
   - En Hive:
     - `AVG(delay_minutes) BY route_id, hour_of_day, day_of_week`
   - En Superset:
     - Mapa de calor de retrasos por ruta y hora.
     - Evolución mensual del retraso medio.

### Valor aportado

- Responde preguntas como:
  - ¿Qué rutas presentan sistemáticamente más retrasos?
  - ¿En qué franjas horarias se concentran los problemas?
  - ¿Cómo ha evolucionado el nivel de servicio tras un cambio de horario?
- Facilita justificar decisiones de rediseño de la red con datos objetivos.

---

## CU3 – Detección de anomalías en la flota

- **Actor principal**: Centro de control, equipo de IA / analítica avanzada.
- **Objetivo**: detectar automáticamente vehículos con comportamiento anómalo, por ejemplo:
  - Velocidades excesivamente bajas o altas.
  - Retrasos mucho mayores que los habituales para esa ruta/hora.
  - Trayectorias o posiciones incoherentes.

### Implementación actual

1. **Entrenamiento (batch)**
   - Se utilizan datos agregados de retrasos desde Hive (`HIVE_AGGREGATED_DELAYS_TABLE`, tabla `transport.aggregated_delays`).
   - Script `spark/ml/anomaly_detection.py`:
     - Carga los agregados de retraso (`avg_delay_min`, `vehicle_count`).
     - Construye un vector de características.
     - Entrena un modelo K-Means (k=3) en Spark ML.
     - Identifica como “cluster anómalo” aquel cuyo centroide tiene mayor retraso medio.
2. **Marcado de anomalías**
   - El script marca como anómalos todos los registros que pertenecen al cluster más problemático.
   - Escribe las anomalías en MongoDB:
     - Base de datos `transport`.
     - Colección `anomalies` (creada en `mongodb/scripts/init_collection.js`).
     - Campos: `window_start`, `window_end`, `warehouse_id`, `avg_delay_min`, `vehicle_count`, `cluster`, `anomaly_flag`.
3. **Visualización (prototipo)**
   - A partir de la colección `transport.anomalies`, se puede construir:
     - Un panel en Grafana o Superset con:
       - Lista de almacenes/ventanas marcadas como anómalas.
       - Evolución temporal del número de anomalías.

### Estado actual

- **Modelo básico de anomalías (batch) implementado** en `spark/ml/anomaly_detection.py`.
- **Colección MongoDB de anomalías** disponible (`transport.anomalies`).
- **Panel de visualización dedicado** (Grafana/Superset): *pendiente de implementación*.

---

## CU4 – Simulación y prueba extremo a extremo del sistema

- **Actor principal**: Equipo técnico, docentes, evaluadores del máster.
- **Objetivo**: demostrar que el pipeline Big Data funciona de extremo a extremo con datos realistas, sin depender de fuentes externas.

### Flujo de datos implicado

1. **Simulador GPS**
   - Script `scripts/gps_simulator.py` genera eventos de una flota de autobuses:
     - `vehicle_id`, `route_id`, `lat`, `lon`, `speed`, `delay_minutes`, `timestamp`.
   - Envía los eventos al topic Kafka `gps-events`.
2. **Pipeline Big Data**
   - NiFi (opcional) puede actuar como capa de ingesta/control.
   - Kafka bufferiza los eventos.
   - Spark Streaming lee `gps-events`, transforma y escribe en:
     - HDFS (histórico, Parquet).
     - MongoDB (estado actual de vehículos).
   - Hive expone las tablas para consultas SQL.
3. **Verificación**
   - Scripts de HOWTO (`docs/HOWTO_EJECUCION.md`) permiten:
     - Verificar mensajes en Kafka.
     - Ver aplicaciones en YARN.
     - Ver ficheros en HDFS.
     - Consultar datos en Hive y MongoDB.

### Valor aportado

- Permite:
  - Probar el sistema sin depender de APIs externas.
  - Repetir demostraciones en el contexto del máster.
  - Validar fácilmente la arquitectura y la robustness del pipeline.

---

## CU5 – Orquestación y operación del pipeline con Airflow

- **Actor principal**: Equipo de operaciones / administrador del sistema.
- **Objetivo**: disponer de una forma reproducible y automatizada de ejecutar el pipeline completo (batch) y los componentes de monitorización streaming.

### Implementación actual

1. **DAG batch principal**
   - Archivo: `airflow/dag_sentinel360_batch.py`.
   - Tareas:
     - `clean_raw` → `spark/cleaning/clean_and_normalize.py`.
     - `enrich_with_hive` → `spark/cleaning/enrich_with_hive.py`.
     - `build_transport_graph` → `spark/graph/transport_graph.py`.
     - `load_aggregated_delays` → `spark/streaming/write_to_hive_and_mongo.py`.
     - `detect_anomalies_batch` → `spark/ml/anomaly_detection.py`.
     - `load_kpis_to_mariadb` → `scripts/mongo_to_mariadb_kpi.py --source mongo`.
   - Este DAG se ejecuta típicamente de forma diaria y asegura que:
     - Los datos están limpios y enriquecidos.
     - El grafo de transporte está actualizado.
     - Los agregados de retrasos e identificaciones de anomalías se calculan periódicamente.
     - Las tablas de KPIs en MariaDB se mantienen al día para los dashboards.

2. **DAG de monitorización streaming**
   - Archivo: `airflow/dag_sentinel360_streaming_monitoring.py`.
   - Tareas:
     - `start_delays_streaming` → lanza el job de streaming `delays_windowed.py` (modo Kafka).
     - `start_alerts_consumer` → arranca `scripts/alerts_consumer.py` para ver alertas en el topic `alerts`.
   - Pensado como DAG manual (sin schedule) para:
     - Iniciar rápidamente una demo de monitorización en tiempo casi real.
     - Integrar los procesos de streaming dentro del ecosistema de orquestación.

### Valor aportado

- Permite que la operación del sistema:
  - Sea **repetible** y documentada.
  - Tenga un punto único de control (Airflow) para ejecuciones completas y parciales.
  - Facilite la integración del pipeline en entornos de producción o de laboratorio.


