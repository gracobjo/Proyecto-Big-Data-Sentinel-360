## Arquitectura de Referencia: Sistema Sentinel360 para el Monitoreo Logístico Global

### 1. Marco Estratégico y Propósito del Sistema

El sistema **Sentinel360** se posiciona como una solución de misión crítica para la visibilidad integral de redes de transporte globales. En el panorama logístico actual, la ventaja competitiva reside en la capacidad de transitar desde un monitoreo **reactivo** —basado en la resolución de incidencias post-mortem— hacia un **descubrimiento de conocimiento proactivo**.

Mediante la implementación del ciclo **KDD (Knowledge Discovery in Databases)**, Sentinel360 transforma telemetría GPS masiva y datos ambientales provenientes de la OpenWeather API en **inteligencia accionable**, permitiendo la detección temprana de cuellos de botella y la optimización de rutas.

Desde una perspectiva arquitectónica, la adopción del **stack Apache** resuelve la fragmentación histórica de datos en el sector logístico. Al integrar flujos de datos heterogéneos en una plataforma unificada, se habilita una toma de decisiones basada en hechos técnicos, mitigando la incertidumbre operativa. Esta integración no es meramente tecnológica, sino estratégica: convierte el flujo de datos brutos en un activo que permite modelar la red de transporte como una entidad dinámica y predecible.

La consecución de estos objetivos estratégicos requiere una **infraestructura física y lógica robusta**, diseñada para soportar cargas de trabajo distribuidas de alto rendimiento.

---

### 2. Infraestructura del Clúster y Topología de Red

La arquitectura de Sentinel360 se fundamenta en un **clúster multi-nodo** que garantiza la alta disponibilidad y la distribución eficiente de cargas. En ecosistemas de Big Data, la **separación de roles** es vital: mientras el nodo maestro coordina, los nodos de trabajo proporcionan la escalabilidad horizontal necesaria para el almacenamiento y procesamiento paralelo.

La topología del clúster se define bajo el siguiente esquema técnico:

| Nodo             | IP            | Servicios Clave                                      | Puertos de Control                      |
|------------------|---------------|------------------------------------------------------|-----------------------------------------|
| hadoop (master)  | 192.168.99.10 | NameNode, ResourceManager, Kafka (KRaft), NiFi, Hive Server2 | 9000 (HDFS), 8088 (YARN), 9092 (Kafka) |
| nodo1            | 192.168.99.12 | DataNode, NodeManager                                | -                                       |
| nodo2            | 192.168.99.14 | DataNode, NodeManager                                | -                                       |

Un pilar fundamental de esta arquitectura es la **centralización mediante `config.py`**. Este archivo actúa como la *Fuente Única de Verdad* (SSOT), donde se definen IPs, rutas HDFS y nombres de temas Kafka. Este enfoque facilita el mantenimiento y la gobernanza, permitiendo que cualquier cambio en la infraestructura se propague automáticamente a todos los jobs de Spark y procesos de ingesta.

Asimismo, la distribución de DataNodes en `nodo1` y `nodo2` asegura que el almacenamiento en HDFS crezca de forma casi lineal con la demanda operativa del sistema.

Esta disposición física de servicios constituye el sustrato sobre el cual reside el flujo lógico de datos definido por la metodología KDD.

---

### 3. El Ciclo KDD (Knowledge Discovery in Databases) en Sentinel360

Sentinel360 utiliza el ciclo **KDD** como motor metodológico para refinar datos brutos hasta convertirlos en modelos de grafos y predicciones de retrasos. Esta metodología asegura que la transformación de logs GPS y respuestas de APIs siga un proceso riguroso de auditoría y limpieza.

Fases implementadas en el ecosistema:

1. **Ingesta (Fase I)**  
   Integración de **Apache NiFi** para la captura de flujos HTTP (OpenWeather) y logs GPS, orquestando su publicación en temas de **Apache Kafka** y su persistencia inicial en HDFS.

2. **Procesamiento y Limpieza (Fase II)**  
   Utilización de **Apache Spark** para la normalización de esquemas y eliminación de ruido en los datos de telemetría.

3. **Enriquecimiento y Modelado (Fase III)**  
   Cruce de datos de posición en tiempo real con datos maestros (warehouses y rutas) almacenados en **Apache Hive**. En esta fase se emplean **GraphFrames** para modelar la topología de la red y análisis de ventanas para identificar desviaciones.

4. **Orquestación y Re-entrenamiento (Fase IV)**  
   Automatización mediante **Apache Airflow**, que gestiona la re-ejecución de los modelos de grafos y jobs de limpieza para reflejar cambios en la infraestructura física de transporte.

La separación entre la fase de ingesta *raw* y el procesamiento posterior es una decisión de diseño crítica. Al mantener un repositorio inmutable en HDFS `/raw/`, el sistema garantiza la integridad de los datos logísticos, permitiendo re-procesar la información ante cambios en las reglas de negocio o fallos en los algoritmos de limpieza sin pérdida de datos originales.

Este ciclo se materializa a través de un stack tecnológico de última generación que garantiza interoperabilidad y rendimiento.

---

### 4. Stack Tecnológico Apache: Integración y Flujo de Datos

La sinergia de los componentes Apache en Sentinel360 permite el procesamiento **polimodal (Batch y Streaming)**, asegurando que el análisis histórico y la respuesta en tiempo real coexistan en un flujo de datos unificado.

**Matriz de componentes del stack Sentinel360**

| Tecnología   | Versión        | Función Específica                     | Uso en el Proyecto                                           |
|-------------|----------------|----------------------------------------|--------------------------------------------------------------|
| Apache NiFi | 2.6            | Orquestación de DataFlows              | Ingesta desde OpenWeather y logs GPS hacia Kafka y HDFS.    |
| Apache Kafka| 3.9 (KRaft)    | Bus de eventos distribuido             | Desacoplamiento de productores y consumidores de telemetría.|
| Apache Spark| 3.5            | Motor de computación distribuida       | Limpieza, GraphFrames y Streaming con spark-sql-kafka.      |
| Apache Hive | Metastore/SQL  | Data Warehouse analítico               | Datos maestros y reporting de agregados.                    |
| Apache Airflow | 2.10        | Orquestador de workflows               | Gestión de dependencias y tareas de mantenimiento del pipeline. |

Arquitectónicamente, la transición a **Kafka 3.9 con KRaft** es un avance significativo, ya que elimina la complejidad operativa de ZooKeeper, simplificando la administración del clúster y mejorando la resiliencia del bus de eventos. El flujo de datos fluye desde los temas Kafka hacia el almacenamiento analítico, permitiendo que Spark SQL consuma eventos en ventanas de tiempo para una visibilidad inmediata de la flota.

Esta integración tecnológica dirige el flujo de información hacia una arquitectura de persistencia diseñada para la diversidad de consultas.

---

### 5. Arquitectura de Almacenamiento y Modelado de Datos

Sentinel360 implementa una estrategia de **almacenamiento políglota**, optimizando la persistencia según los requisitos de latencia y volumen de cada tipo de dato.

- **Jerarquía HDFS**: los datos se organizan para garantizar la trazabilidad:
  - `/user/hadoop/proyecto/raw/`: datos inmutables sin procesar.
  - `/user/hadoop/proyecto/procesado/`: resultados de limpieza, enriquecimiento y agregados.
  - `/user/hadoop/proyecto/temp/`: espacio para persistencia intermedia y *staging*.

- **Modelo en Apache Hive**: las tablas de Hive se definen utilizando la cláusula `LOCATION` apuntando directamente a las rutas de HDFS bajo `/procesado/`. Esto permite una integración nativa donde los datos limpios generados por Spark son consultables mediante SQL para reporting de almacenes y rutas.

- **Persistencia en MongoDB**: se utiliza principalmente para:
  - Colección `transport.vehicle_state`: estado actual de cada vehículo.
  - Colecciones `transport.aggregated_delays` y `transport.anomalies`: ventanas de retrasos y anomalías detectadas.

La justificación técnica para el uso de **MongoDB** frente a Hive radica en la naturaleza de los datos operativos. Mientras Hive es excepcional para agregaciones analíticas y auditoría histórica, MongoDB proporciona la **baja latencia** necesaria para actualizaciones constantes del estado de los vehículos. Esta arquitectura híbrida permite que los tableros operativos consulten el estado actual en milisegundos sin sobrecargar el data warehouse analítico.

Finalmente, la coherencia de este almacenamiento se mantiene mediante procesos de ejecución y orquestación bien definidos.

---

### 6. Orquestación, Ejecución y Operaciones del Pipeline

La confiabilidad del sistema descansa en **Apache Airflow**, que garantiza la idempotencia de los procesos y la recuperación automática ante fallos. El pipeline se opera mediante una secuencia técnica rigurosa:

1. **Inicialización de entorno**  
   Ejecución de `./scripts/setup_hdfs.sh` para crear la estructura de directorios y asignar permisos necesarios para la gobernanza de datos.

2. **Ingesta de datos maestros**  
   Poblado de catálogos mediante `./scripts/ingest_from_local.sh`, cargando la definición de almacenes y rutas.

3. **Procesamiento Spark en YARN**  
   Lanzamiento de jobs distribuidos mediante `./scripts/run_spark_submit.sh` para los siguientes módulos:
   - `spark/cleaning/clean_and_normalize.py`: normalización de la telemetría.
   - `spark/cleaning/enrich_with_hive.py`: unión de logs con datos maestros de Hive.
   - `spark/graph/transport_graph.py`: generación del grafo de la red logística.
   - `spark/streaming/delays_windowed.py`: job de streaming que procesa ventanas de 15 minutos para identificar retrasos.

4. **Capa de servicio Hive**  
   Ejecución de esquemas DDL mediante Beeline (`beeline -u "jdbc:hive2://localhost:10000"`) para asegurar que las tablas reflejen los datos procesados en HDFS.

El procesamiento de ventanas de 15 minutos en Spark Streaming es el núcleo de la visibilidad logística de Sentinel360: permite detectar anomalías en tiempo casi real y persistir los retrasos detectados en Hive para su análisis de impacto.

En conclusión, Sentinel360 constituye un **ecosistema cohesivo** que, bajo la dirección de una arquitectura distribuida y el rigor del ciclo KDD, transforma el caos de los datos de transporte en una **red logística inteligente y monitorizada**.

---

### 7. Preparación para despliegues dockerizados (entorno de demo)

Aunque el clúster Big Data (Hadoop, Kafka, Spark, Hive, NiFi) se ejecuta sobre máquinas físicas/VMs, el proyecto incluye una carpeta `docker/` pensada para facilitar:

- El despliegue rápido de:
  - MariaDB (`sentinel360_analytics`).
  - Superset.
  - Grafana.
- Un contenedor de utilidades (`tools`) desde el que lanzar scripts del proyecto.

Ficheros relevantes:

- `docker/docker-compose.yml`: orquesta los contenedores de MariaDB, Superset, Grafana y `tools`.
- `docker/Dockerfile.tools`: imagen base Python para ejecutar scripts del repositorio.
- `docker/requirements-tools.txt`: dependencias necesarias para `gps_simulator.py`, consumer de alertas, etc.

Ejemplo de uso:

```bash
cd docker
docker compose up -d

# Ejecutar el simulador desde el contenedor tools
docker compose run --rm tools python scripts/gps_simulator.py
```

Con este enfoque, partes importantes de la capa de visualización y utilidades pueden ejecutarse en entornos como Render o servidores Docker dedicados, mientras el clúster Big Data permanece desplegado sobre los nodos on-premise.


