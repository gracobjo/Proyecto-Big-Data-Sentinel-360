# Documento de Requisitos – Sentinel360

## Introducción

Sentinel360 es un sistema de monitorización de redes de transporte y logística que implementa el ciclo KDD (Knowledge Discovery in Databases) sobre un stack Apache distribuido. El sistema transforma telemetría GPS masiva y datos meteorológicos en inteligencia accionable: detección de retrasos, identificación de anomalías, análisis de grafos de rutas y KPIs operativos accesibles desde dashboards en tiempo casi real.

El sistema opera sobre un clúster multi-nodo (Hadoop/YARN) e integra NiFi, Kafka, Spark, Hive, MongoDB, MariaDB, Airflow, Grafana, Superset y una interfaz web Streamlit.

---

## Glosario

- **Sistema**: Sentinel360 en su conjunto.
- **Pipeline**: Flujo de datos extremo a extremo desde la ingesta hasta la visualización.
- **Ingesta**: Proceso de captura y publicación de datos desde fuentes externas.
- **NiFi**: Apache NiFi, componente de orquestación de flujos de datos (ingesta).
- **Kafka**: Apache Kafka, bus de eventos distribuido.
- **Spark**: Apache Spark, motor de procesamiento distribuido (batch y streaming).
- **HDFS**: Hadoop Distributed File System, almacenamiento distribuido.
- **Hive**: Apache Hive, data warehouse analítico sobre HDFS.
- **MongoDB**: Base de datos documental para estado operativo y anomalías.
- **MariaDB**: Base de datos relacional para KPIs y dashboards.
- **Airflow**: Apache Airflow, orquestador de workflows (DAGs).
- **Grafana**: Herramienta de visualización de KPIs en tiempo real.
- **Superset**: Apache Superset, herramienta de análisis y dashboards analíticos.
- **Streamlit**: Interfaz web de presentación del ciclo KDD.
- **Evento_GPS**: Registro de telemetría de un vehículo con campos: event_id, vehicle_id, ts, lat, lon, speed, warehouse_id.
- **Ventana_Temporal**: Intervalo de 15 minutos usado para agregar métricas de retrasos.
- **Almacen**: Nodo logístico de la red (warehouse), con identificador, nombre, ciudad, coordenadas y capacidad.
- **Ruta**: Arista del grafo logístico entre dos almacenes, con distancia y duración media.
- **Anomalia**: Ventana temporal cuyo retraso medio supera el umbral definido por el modelo K-Means.
- **KPI**: Indicador clave de rendimiento calculado a partir de los agregados de retrasos.
- **DAG**: Directed Acyclic Graph, unidad de orquestación en Airflow.
- **Operador**: Usuario del sistema con rol de monitorización de tráfico en tiempo real.
- **Planificador**: Usuario con rol de análisis histórico y planificación de la red.
- **Administrador**: Usuario con rol de operación y mantenimiento del pipeline.
- **GraphFrames**: Librería de Spark para análisis de grafos distribuidos.
- **KDD**: Knowledge Discovery in Databases, metodología de descubrimiento de conocimiento.
- **Checkpoint**: Punto de recuperación del estado del streaming en HDFS.
- **SSOT**: Single Source of Truth; en Sentinel360, el fichero config.py.


---

## Requisitos

### Requisito 1: Ingesta de datos GPS desde NiFi hacia Kafka y HDFS

**User Story:** Como Operador, quiero que los eventos GPS de la flota se capturen automáticamente y se publiquen en el bus de eventos, para que el pipeline de procesamiento disponga de datos en tiempo real.

#### Criterios de Aceptación

1. WHEN un fichero GPS (JSON o CSV) es depositado en el directorio de entrada configurado, THE NiFi SHALL leer el fichero y publicar cada evento en el topic Kafka `raw-data`.
2. WHEN un evento GPS tiene velocidad inferior a 120 km/h, THE NiFi SHALL publicar el evento también en el topic Kafka `filtered-data`.
3. WHEN NiFi procesa un fichero GPS, THE NiFi SHALL escribir una copia inmutable del fichero en la ruta HDFS `/user/hadoop/proyecto/raw/`.
4. IF el directorio de entrada de NiFi no contiene ficheros, THEN THE NiFi SHALL permanecer en espera activa y reintentar la lectura cada 5 segundos.
5. THE Sistema SHALL soportar ficheros GPS en formato JSON (JSON Lines) y CSV con los campos: `event_id`, `vehicle_id`, `ts`, `lat`, `lon`, `speed`, `warehouse_id`.

---

### Requisito 2: Ingesta de datos meteorológicos desde OpenWeather

**User Story:** Como Planificador, quiero que el sistema capture datos meteorológicos de la API OpenWeather, para que puedan correlacionarse con los retrasos de la flota.

#### Criterios de Aceptación

1. WHEN el flujo NiFi de OpenWeather está activo, THE NiFi SHALL invocar la API OpenWeather mediante HTTP y publicar la respuesta en el topic Kafka `raw-data`.
2. IF la API OpenWeather no está disponible, THEN THE Sistema SHALL registrar el error y continuar la operación sin interrumpir la ingesta GPS.
3. WHERE el script alternativo `ingest_openweather.py` esté configurado, THE Sistema SHALL permitir la ingesta meteorológica sin depender del flujo NiFi.

---

### Requisito 3: Almacenamiento inmutable de datos crudos en HDFS

**User Story:** Como Administrador, quiero que todos los datos crudos se almacenen de forma inmutable en HDFS, para poder reprocesarlos ante cambios en las reglas de negocio sin pérdida de información.

#### Criterios de Aceptación

1. THE Sistema SHALL mantener los datos crudos en la ruta HDFS `/user/hadoop/proyecto/raw/` sin modificación ni eliminación automática.
2. WHEN un job Spark de limpieza se ejecuta, THE Spark SHALL leer los datos desde `/user/hadoop/proyecto/raw/` y escribir los resultados en `/user/hadoop/proyecto/procesado/cleaned/` sin alterar los datos originales.
3. THE Sistema SHALL organizar los datos procesados en las subrutas: `cleaned/`, `enriched/`, `graph/`, `aggregated_delays/` y `temp/` bajo `/user/hadoop/proyecto/procesado/`.


---

### Requisito 4: Limpieza y normalización de eventos GPS (Fase II)

**User Story:** Como Administrador, quiero que los datos GPS crudos sean limpiados y normalizados automáticamente, para garantizar la calidad de los datos en las fases posteriores del pipeline.

#### Criterios de Aceptación

1. WHEN el job `clean_and_normalize.py` se ejecuta, THE Spark SHALL leer los eventos desde HDFS raw, eliminar registros con campos obligatorios nulos (`vehicle_id`, `ts`, `lat`, `lon`) y escribir el resultado en formato Parquet en `/user/hadoop/proyecto/procesado/cleaned/`.
2. THE Spark SHALL normalizar el campo `ts` al tipo timestamp ISO 8601 durante la limpieza.
3. IF un evento GPS contiene un valor de velocidad negativo o superior a 300 km/h, THEN THE Spark SHALL descartar el registro y registrar el evento en el log de ejecución.
4. THE Spark SHALL ejecutar los jobs de limpieza en modo distribuido sobre YARN con al menos 2 ejecutores.

---

### Requisito 5: Enriquecimiento de eventos con datos maestros (Fase II)

**User Story:** Como Planificador, quiero que los eventos GPS se enriquezcan con información de almacenes y rutas, para poder analizar los retrasos en el contexto de la red logística.

#### Criterios de Aceptación

1. WHEN el job `enrich_with_hive.py` se ejecuta, THE Spark SHALL realizar un join entre los eventos limpios y la tabla Hive `transport.warehouses` por el campo `warehouse_id`, escribiendo el resultado en `/user/hadoop/proyecto/procesado/enriched/`.
2. THE Sistema SHALL mantener las tablas maestras `transport.warehouses` y `transport.routes` en Hive con los campos definidos en los esquemas DDL (`hive/schema/01_warehouses.sql` y `hive/schema/02_routes.sql`).
3. IF un evento GPS referencia un `warehouse_id` que no existe en `transport.warehouses`, THEN THE Spark SHALL conservar el evento con los campos de enriquecimiento como nulos y registrar la incidencia en el log.

---

### Requisito 6: Modelado de la red logística como grafo (Fase II)

**User Story:** Como Planificador, quiero que la red de almacenes y rutas se modele como un grafo dirigido, para poder calcular caminos mínimos y detectar componentes desconectados.

#### Criterios de Aceptación

1. WHEN el job `transport_graph.py` se ejecuta, THE Spark SHALL construir un grafo dirigido usando GraphFrames con los almacenes como vértices y las rutas como aristas ponderadas por `distance_km`.
2. THE Spark SHALL calcular los caminos más cortos (shortest paths) desde los almacenes de referencia configurados y escribir los resultados en `/user/hadoop/proyecto/procesado/graph/` en formato Parquet.
3. THE Spark SHALL calcular los componentes conectados del grafo e incluirlos en la salida de grafos.
4. IF la tabla `transport.routes` está vacía, THEN THE Spark SHALL registrar un error descriptivo y finalizar el job sin escritura parcial.


---

### Requisito 7: Streaming de retrasos en ventanas temporales (Fase III)

**User Story:** Como Operador, quiero que el sistema calcule el retraso medio de la flota en ventanas de 15 minutos por almacén, para detectar problemas operativos en tiempo casi real.

#### Criterios de Aceptación

1. WHEN el job `delays_windowed.py` está activo y recibe eventos del topic Kafka `raw-data`, THE Spark SHALL agrupar los eventos por ventanas de 15 minutos y por `warehouse_id`, calculando `avg_delay_min` y `vehicle_count` por ventana.
2. WHEN se completa una Ventana_Temporal, THE Spark SHALL escribir los agregados en la tabla Hive `transport.aggregated_delays` en modo append.
3. WHEN se completa una Ventana_Temporal y MongoDB está disponible, THE Spark SHALL insertar los agregados en la colección MongoDB `transport.aggregated_delays`.
4. WHEN el `avg_delay_min` de una ventana supera 20 minutos, THE Spark SHALL publicar una alerta en el topic Kafka `alerts` con los campos: `type`, `warehouse_id`, `window_start`, `window_end`, `avg_delay_min`, `vehicle_count`, `threshold`.
5. THE Spark SHALL aplicar un watermark de 10 minutos sobre el campo `ts` para gestionar eventos tardíos.
6. THE Sistema SHALL persistir el Checkpoint del streaming en la ruta HDFS configurada en `config.py` para permitir la reanudación sin duplicados.
7. IF MongoDB no está disponible, THEN THE Spark SHALL continuar el streaming escribiendo únicamente en Hive sin interrumpir el procesamiento.
8. THE Sistema SHALL soportar dos modos de entrada para el streaming: `kafka` (desde el topic `raw-data`) y `file` (desde ficheros CSV en HDFS raw).

---

### Requisito 8: Detección de anomalías mediante K-Means (Fase III)

**User Story:** Como Operador, quiero que el sistema identifique automáticamente ventanas temporales con comportamiento anómalo, para priorizar la atención sobre los almacenes más problemáticos.

#### Criterios de Aceptación

1. WHEN el job `anomaly_detection.py` se ejecuta, THE Spark SHALL cargar los agregados de la tabla Hive `transport.aggregated_delays`, entrenar un modelo K-Means con k=3 sobre las características `avg_delay_min` y `vehicle_count`, e identificar el cluster con mayor retraso medio como cluster anómalo.
2. WHEN el modelo K-Means identifica registros anómalos, THE Spark SHALL escribir dichos registros en la colección MongoDB `transport.anomalies` con los campos: `window_start`, `window_end`, `warehouse_id`, `avg_delay_min`, `vehicle_count`, `cluster`, `anomaly_flag`.
3. WHEN se detectan anomalías, THE Spark SHALL publicar una alerta por cada anomalía en el topic Kafka `alerts` con `type: "ANOMALY"`.
4. IF la tabla `transport.aggregated_delays` está vacía, THEN THE Spark SHALL registrar un mensaje informativo y finalizar el job sin error.


---

### Requisito 9: Exportación de KPIs a MariaDB para dashboards

**User Story:** Como Operador, quiero que los KPIs de retrasos estén disponibles en MariaDB, para que Grafana y Superset puedan consultarlos con baja latencia.

#### Criterios de Aceptación

1. WHEN el script `mongo_to_mariadb_kpi.py` se ejecuta, THE Sistema SHALL leer los agregados de retrasos desde MongoDB o desde ficheros Parquet en HDFS y calcular los KPIs: retraso medio por ruta, retraso medio por vehículo y número de anomalías por almacén.
2. THE Sistema SHALL insertar los KPIs calculados en las tablas correspondientes de la base de datos MariaDB `sentinel360_analytics`.
3. IF la conexión a MongoDB falla, THEN THE Sistema SHALL intentar leer los agregados desde los ficheros Parquet en HDFS como fuente alternativa.

---

### Requisito 10: Visualización de KPIs en Grafana

**User Story:** Como Operador, quiero visualizar los KPIs de retrasos en dashboards de Grafana, para monitorizar el estado de la flota de forma continua.

#### Criterios de Aceptación

1. THE Grafana SHALL mostrar un dashboard con al menos los siguientes paneles: retraso medio por almacén (serie temporal), top almacenes con mayor retraso (tabla) y número de vehículos activos por ventana.
2. THE Grafana SHALL conectarse a la base de datos MariaDB `sentinel360_analytics` como fuente de datos principal.
3. WHEN los datos en MariaDB se actualizan, THE Grafana SHALL reflejar los nuevos valores en el dashboard en el siguiente ciclo de refresco configurado.

---

### Requisito 11: Análisis histórico en Superset

**User Story:** Como Planificador, quiero explorar el histórico de retrasos mediante dashboards analíticos en Superset, para identificar patrones temporales y tomar decisiones de planificación.

#### Criterios de Aceptación

1. THE Superset SHALL conectarse a la base de datos MariaDB `sentinel360_analytics` y exponer los datos de KPIs para la creación de gráficos y dashboards.
2. THE Superset SHALL permitir filtrar los datos de retrasos por almacén, rango de fechas y franja horaria.
3. THE Sistema SHALL proveer datos históricos en Hive (`transport.aggregated_delays`) consultables mediante SQL para análisis de patrones por hora del día y día de la semana.


---

### Requisito 12: Orquestación del pipeline mediante Airflow

**User Story:** Como Administrador, quiero que el pipeline completo sea orquestado por Airflow, para garantizar la reproducibilidad, el orden de ejecución y la recuperación ante fallos.

#### Criterios de Aceptación

1. THE Airflow SHALL disponer de un DAG para la Fase I (ingesta) que ejecute en orden: creación de topics Kafka, ingesta GPS sintética e ingesta OpenWeather.
2. THE Airflow SHALL disponer de un DAG para la Fase II (preprocesamiento) que ejecute en orden: limpieza, enriquecimiento y construcción del grafo.
3. THE Airflow SHALL disponer de un DAG para la Fase III (batch) que ejecute en orden: carga de agregados, detección de anomalías y exportación de KPIs a MariaDB.
4. THE Airflow SHALL disponer de un DAG para el streaming que permita iniciar el job `delays_windowed.py` de forma controlada.
5. WHEN una tarea de un DAG falla, THE Airflow SHALL reintentar la tarea al menos 1 vez con un intervalo de espera de 2 a 5 minutos antes de marcarla como fallida.
6. THE Airflow SHALL generar un informe de ejecución al finalizar cada DAG, registrando el estado de cada tarea.
7. THE Sistema SHALL centralizar toda la configuración de rutas, IPs y nombres de servicios en el fichero `config.py`, que actuará como SSOT para todos los DAGs y scripts.

---

### Requisito 13: Interfaz web de presentación del ciclo KDD (Streamlit)

**User Story:** Como Administrador, quiero una interfaz web que permita recorrer y ejecutar las fases del ciclo KDD de forma interactiva, para facilitar la demostración y validación del sistema.

#### Criterios de Aceptación

1. THE Streamlit SHALL presentar al menos 7 secciones navegables correspondientes a: arranque de servicios, Fase I (ingesta), Fase II (limpieza/enriquecimiento), Fase II (grafos), Fase III (streaming y anomalías), entorno visual y dashboard de retrasos/anomalías.
2. WHEN el usuario pulsa el botón de ejecución de un script, THE Streamlit SHALL lanzar el script correspondiente y mostrar la salida en tiempo real en la interfaz.
3. THE Streamlit SHALL permitir cargar ficheros GPS (CSV o JSON), rutas (CSV) y almacenes (CSV) para su previsualización sin modificar el repositorio.
4. THE Streamlit SHALL mostrar un mapa interactivo con la posición de los almacenes usando sus coordenadas lat/lon.
5. WHEN hay datos disponibles en MongoDB, THE Streamlit SHALL mostrar los agregados de retrasos y las anomalías detectadas en el dashboard de la sección 6.
6. THE Streamlit SHALL incluir un buscador de conceptos KDD en la barra lateral que permita navegar a la sección relevante para un término dado.


---

### Requisito 14: Simulación de datos GPS para pruebas

**User Story:** Como Administrador, quiero un simulador de datos GPS que genere eventos realistas y los publique en Kafka, para poder probar el pipeline sin depender de fuentes externas.

#### Criterios de Aceptación

1. THE Sistema SHALL proveer el script `gps_simulator.py` que genere eventos GPS con los campos: `vehicle_id`, `route_id`, `lat`, `lon`, `speed`, `delay_minutes`, `timestamp`.
2. WHEN el simulador está activo, THE Sistema SHALL publicar un evento GPS en el topic Kafka `gps-events` cada segundo.
3. THE Sistema SHALL generar coordenadas lat/lon dentro de un área geográfica representativa de la red logística configurada.
4. THE Sistema SHALL proveer el script `generate_synthetic_gps.py` que genere ficheros CSV y JSON Lines de eventos GPS a partir de los maestros `warehouses.csv` y `routes.csv`.

---

### Requisito 15: Consumo y visualización de alertas

**User Story:** Como Operador, quiero recibir y visualizar las alertas de anomalías generadas por el pipeline, para poder reaccionar ante situaciones críticas en tiempo real.

#### Criterios de Aceptación

1. THE Sistema SHALL proveer el script `alerts_consumer.py` que consuma el topic Kafka `alerts` y muestre cada alerta por consola con su tipo, almacén, ventana temporal y retraso medio.
2. WHEN se recibe una alerta en el topic `alerts`, THE Sistema SHALL mostrarla en consola en menos de 5 segundos desde su publicación.
3. THE Sistema SHALL soportar alertas de dos tipos: `ANOMALY` (generadas por el modelo K-Means batch) y `ANOMALY_STREAMING` (generadas por el job de streaming cuando `avg_delay_min > 20`).

---

### Requisito 16: Configuración centralizada y despliegue

**User Story:** Como Administrador, quiero que toda la configuración del sistema esté centralizada en un único fichero, para simplificar el mantenimiento y los cambios de infraestructura.

#### Criterios de Aceptación

1. THE Sistema SHALL centralizar en `config.py` todas las IPs de nodos, rutas HDFS, nombres de topics Kafka, nombres de tablas Hive, URIs de MongoDB y MariaDB, y rutas de checkpoints.
2. THE Sistema SHALL permitir sobrescribir los parámetros de conexión a MongoDB y MariaDB mediante variables de entorno (`MONGO_URI`, `MARIA_DB_URI`, `MARIA_DB_HOST`, `MARIA_DB_PORT`, `MARIA_DB_USER`, `MARIA_DB_PASSWORD`, `MARIA_DB_NAME`).
3. THE Sistema SHALL proveer scripts de arranque (`start_servicios.sh`) y parada (`stop_servicios.sh`) que gestionen el ciclo de vida de todos los servicios del clúster.
4. THE Sistema SHALL proveer scripts de verificación para cada componente: clúster HDFS/YARN, topics Kafka, ingesta GPS, tablas Hive y conexión Superset-MariaDB.
5. WHERE el entorno de demo esté basado en Docker, THE Sistema SHALL proveer un `docker-compose.yml` que levante MariaDB, Superset y Grafana con la configuración de Sentinel360.


---

## Requisitos No Funcionales

### RNF-1: Rendimiento del streaming

1. THE Sistema SHALL procesar ventanas de retrasos de 15 minutos con una latencia máxima de 30 segundos desde el cierre de la ventana hasta la escritura en Hive.
2. THE Kafka SHALL soportar al menos 3 particiones por topic para permitir el consumo paralelo por parte de Spark Streaming.
3. THE Spark SHALL ejecutarse con al menos 2 ejecutores YARN con 2 núcleos y 2 GB de memoria cada uno para los jobs de streaming y batch.

### RNF-2: Disponibilidad y tolerancia a fallos

1. THE Sistema SHALL permitir la reanudación del streaming desde el último Checkpoint sin pérdida ni duplicación de datos ante un reinicio del job.
2. IF un DataNode del clúster HDFS falla, THEN THE Sistema SHALL continuar operando gracias al factor de replicación de HDFS (mínimo 2 réplicas por bloque).
3. THE Airflow SHALL reintentar automáticamente las tareas fallidas según la política de reintentos definida en cada DAG.

### RNF-3: Escalabilidad

1. THE Sistema SHALL soportar la adición de nuevos DataNodes al clúster HDFS/YARN sin modificar la configuración de los jobs Spark.
2. THE Sistema SHALL soportar el incremento del número de vehículos simulados hasta al menos 50 vehículos simultáneos sin degradación observable del pipeline.

### RNF-4: Mantenibilidad y configurabilidad

1. THE Sistema SHALL centralizar toda la configuración en `config.py` de forma que un cambio de IP o ruta se propague a todos los componentes sin modificar código de negocio.
2. THE Sistema SHALL documentar cada componente del pipeline con un fichero README o documento Markdown en su directorio correspondiente.
3. THE Sistema SHALL proveer scripts de verificación ejecutables de forma independiente para cada capa del pipeline.

### RNF-5: Seguridad básica

1. THE Sistema SHALL gestionar las credenciales de MariaDB y MongoDB mediante variables de entorno, sin incluirlas en texto plano en el código fuente del repositorio.
2. THE Sistema SHALL restringir el acceso a la interfaz Grafana mediante autenticación con usuario y contraseña.

### RNF-6: Observabilidad

1. THE Sistema SHALL registrar en logs el inicio, progreso y finalización de cada job Spark, incluyendo el número de registros procesados por batch.
2. THE Airflow SHALL mantener un historial de ejecuciones de cada DAG accesible desde su interfaz web.
3. THE Sistema SHALL exponer la interfaz web de YARN en el puerto 8088 del nodo master para la monitorización de jobs Spark en ejecución.


---

## Casos de Uso

### CU-01: Monitorización de retrasos en tiempo casi real

**Actor principal:** Operador de tráfico  
**Actores secundarios:** Sistema (Spark Streaming, Kafka, Hive, MongoDB, MariaDB, Grafana)  
**Precondición:** Los servicios del clúster están activos. El job `delays_windowed.py` está en ejecución. Hay eventos GPS llegando al topic Kafka `raw-data`.  
**Postcondición:** El Operador visualiza el retraso medio por almacén en el dashboard de Grafana actualizado.

**Flujo principal:**
1. El Operador accede al dashboard de Grafana en `http://localhost:3000`.
2. Grafana consulta la tabla `kpi_delays_by_route` en MariaDB `sentinel360_analytics`.
3. El Sistema muestra el retraso medio por almacén en una serie temporal y una tabla de top almacenes.
4. El Operador identifica los almacenes con mayor retraso y toma decisiones operativas.

**Flujo alternativo A – Sin datos en MariaDB:**
- En el paso 2, si MariaDB no tiene datos recientes, el Operador ejecuta `mongo_to_mariadb_kpi.py` para volcar los KPIs desde MongoDB.

**Flujo alternativo B – Alerta en tiempo real:**
- Cuando `avg_delay_min > 20` en una ventana, el Sistema publica una alerta en Kafka `alerts`.
- El Operador puede ejecutar `alerts_consumer.py` para recibir las alertas por consola.

---

### CU-02: Análisis histórico y planificación de la red

**Actor principal:** Responsable de planificación  
**Actores secundarios:** Sistema (Hive, MariaDB, Superset)  
**Precondición:** Existen datos históricos en la tabla Hive `transport.aggregated_delays` de al menos varios días.  
**Postcondición:** El Planificador obtiene un análisis de patrones de retraso por ruta, hora y día de la semana.

**Flujo principal:**
1. El Planificador accede a Superset en `http://localhost:8089`.
2. Superset consulta la base de datos MariaDB `sentinel360_analytics`.
3. El Planificador aplica filtros por almacén, rango de fechas y franja horaria.
4. El Sistema muestra gráficos de evolución del retraso medio y mapas de calor por hora/día.
5. El Planificador exporta los datos o genera un informe para justificar decisiones de rediseño de rutas.

**Flujo alternativo – Consulta directa en Hive:**
- El Planificador ejecuta consultas SQL en Hive mediante Beeline para obtener agregados personalizados (`AVG(delay_minutes) BY route_id, hour_of_day`).

---

### CU-03: Detección y revisión de anomalías en la flota

**Actor principal:** Centro de control / equipo de analítica  
**Actores secundarios:** Sistema (Spark ML, MongoDB, Kafka, Grafana/Superset)  
**Precondición:** La tabla Hive `transport.aggregated_delays` contiene datos suficientes para entrenar el modelo K-Means (al menos 3 registros distintos).  
**Postcondición:** Las anomalías detectadas están disponibles en MongoDB `transport.anomalies` y en el topic Kafka `alerts`.

**Flujo principal:**
1. El Administrador ejecuta el job `anomaly_detection.py` (manualmente o vía DAG de Airflow).
2. Spark carga los agregados de Hive y entrena el modelo K-Means con k=3.
3. El Sistema identifica el cluster con mayor `avg_delay_min` como cluster anómalo.
4. El Sistema escribe los registros anómalos en MongoDB `transport.anomalies`.
5. El Sistema publica una alerta por cada anomalía en el topic Kafka `alerts`.
6. El Centro de control revisa las anomalías en el dashboard de Grafana o Superset.

**Flujo alternativo – Anomalía detectada en streaming:**
- Durante la ejecución de `delays_windowed.py`, si `avg_delay_min > 20` en una ventana, el Sistema publica automáticamente una alerta `ANOMALY_STREAMING` en Kafka `alerts` sin esperar al batch de K-Means.

---

### CU-04: Simulación y prueba extremo a extremo del pipeline

**Actor principal:** Equipo técnico / evaluador  
**Actores secundarios:** Sistema (simulador GPS, Kafka, Spark, HDFS, Hive, MongoDB)  
**Precondición:** Los servicios del clúster están activos. Los topics Kafka están creados.  
**Postcondición:** El pipeline completo ha procesado datos sintéticos y los resultados son verificables en Hive, MongoDB y los dashboards.

**Flujo principal:**
1. El Administrador ejecuta `gps_simulator.py` para generar eventos GPS sintéticos hacia el topic Kafka `gps-events`.
2. El Sistema procesa los eventos a través del pipeline: Kafka → Spark Streaming → Hive + MongoDB.
3. El Administrador ejecuta los scripts de verificación: `verificar_ingesta_gps.sh`, `verificar_tablas_hive.sh`, `verificar_topics_kafka.sh`.
4. El Administrador consulta los datos en Hive (`SELECT * FROM transport.aggregated_delays LIMIT 10`) y en MongoDB para confirmar la escritura.
5. El Administrador ejecuta `anomaly_detection.py` y verifica la colección `transport.anomalies` en MongoDB.

**Flujo alternativo – Demo con interfaz Streamlit:**
- El Administrador accede a la interfaz Streamlit (`http://localhost:8501`) y recorre las fases del ciclo KDD pulsando los botones de ejecución de cada script.

---

### CU-05: Orquestación y operación automatizada del pipeline

**Actor principal:** Administrador del sistema  
**Actores secundarios:** Sistema (Airflow, Spark, scripts de shell)  
**Precondición:** Airflow está instalado y configurado con la variable `sentinel360_project_dir` apuntando al directorio del proyecto.  
**Postcondición:** El pipeline batch completo se ha ejecutado en el orden correcto y los KPIs están actualizados en MariaDB.

**Flujo principal:**
1. El Administrador accede a la interfaz web de Airflow.
2. El Administrador activa y dispara el DAG `sentinel360_fase_I_ingesta` para ejecutar la ingesta.
3. Una vez completada la Fase I, el Administrador dispara el DAG `sentinel360_fase_II_preprocesamiento`.
4. Una vez completada la Fase II, el Administrador dispara el DAG `sentinel360_fase_III_batch`.
5. Airflow ejecuta en orden: carga de agregados → detección de anomalías → exportación de KPIs a MariaDB.
6. El Administrador verifica el estado de cada tarea en la interfaz de Airflow y revisa los logs ante cualquier fallo.

**Flujo alternativo – Ejecución programada:**
- El DAG batch puede configurarse con un `schedule` diario para ejecutarse de forma desasistida a las 02:00.

---

### CU-06: Arranque y verificación del clúster

**Actor principal:** Administrador del sistema  
**Actores secundarios:** Sistema (HDFS, YARN, Kafka, NiFi, Hive, MongoDB, MariaDB)  
**Precondición:** Los nodos del clúster están encendidos y accesibles en la red.  
**Postcondición:** Todos los servicios del clúster están activos y verificados.

**Flujo principal:**
1. El Administrador ejecuta `./scripts/start_servicios.sh` en el nodo master.
2. El Sistema arranca en orden: HDFS, YARN, Kafka, Hive, MongoDB, MariaDB y NiFi.
3. El Administrador ejecuta `./scripts/verificar_cluster.sh` para comprobar el estado de cada servicio.
4. El Administrador ejecuta `./scripts/verificar_topics_kafka.sh` para confirmar que los topics `raw-data`, `filtered-data` y `alerts` existen.
5. El Administrador ejecuta `./scripts/setup_hdfs.sh` para crear las rutas HDFS necesarias si es la primera ejecución.

**Flujo alternativo – Parada del clúster:**
- El Administrador ejecuta `./scripts/stop_servicios.sh` para detener todos los servicios de forma ordenada.

