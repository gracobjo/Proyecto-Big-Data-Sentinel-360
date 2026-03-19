# Diagramas UML – Sentinel360

> Todos los diagramas están en formato **Mermaid**.  
> Puedes visualizarlos en:
> - **VS Code**: instala la extensión [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
> - **Online**: copia cualquier bloque en [https://mermaid.live](https://mermaid.live)
> - **GitHub**: se renderizan automáticamente en cualquier `.md`

---

## 1. Diagrama de Componentes (C4 – Nivel 2)

Muestra los principales bloques del sistema y sus dependencias.

```mermaid
graph TD
    subgraph Fuentes["🌐 Fuentes Externas"]
        GPS_FILE[Ficheros GPS\nCSV / JSON Lines]
        OW_API[OpenWeather API\nHTTP REST]
    end

    subgraph Ingesta["📥 Fase I – Ingesta"]
        NIFI["Apache NiFi\n(flujos GPS + OpenWeather)"]
        SIM["gps_simulator.py\n(generador sintético)"]
        KAFKA["Apache Kafka\ntopics: raw-data · filtered-data\ngps-events · alerts"]
        HDFS_RAW["HDFS /raw/\n(datos crudos inmutables)"]
    end

    subgraph Preprocesamiento["⚙️ Fase II – Preprocesamiento (Spark/YARN)"]
        CLEAN["clean_and_normalize.py\n(limpieza + dedup + cast)"]
        ENRICH["enrich_with_hive.py\n(join con warehouses)"]
        GRAPH["transport_graph.py\n(GraphFrames: shortest paths\n+ connected components)"]
        HDFS_PROC["HDFS /procesado/\ncleaned · enriched · graph"]
    end

    subgraph Mineria["🔬 Fase III – Minería"]
        STREAM["delays_windowed.py\n(Spark Structured Streaming\nventanas 15 min)"]
        ANOMALY["anomaly_detection.py\n(Spark ML – K-Means k=3)"]
    end

    subgraph Almacenamiento["🗄️ Almacenamiento Políglota"]
        HIVE["Apache Hive\ntransport.*\n(data warehouse analítico)"]
        MONGO["MongoDB\ntransport.*\n(estado operativo + anomalías)"]
        MARIADB["MariaDB\nsentinel360_analytics\n(KPIs para dashboards)"]
    end

    subgraph Exportacion["🔄 Exportación de KPIs"]
        KPI_SCRIPT["mongo_to_mariadb_kpi.py\nexport_hive_to_mariadb.py"]
    end

    subgraph Visualizacion["📊 Visualización"]
        GRAFANA["Grafana\n:3000\n(KPIs tiempo real)"]
        SUPERSET["Apache Superset\n:8089\n(análisis histórico)"]
        STREAMLIT["Streamlit\n:8501\n(demo KDD interactiva)"]
        ALERTS_CON["alerts_consumer.py\n(consola alertas)"]
    end

    subgraph Orquestacion["🎛️ Orquestación"]
        AIRFLOW["Apache Airflow\n8 DAGs\n(infra · fase I · II · III · dashboards)"]
    end

    subgraph Config["⚙️ Configuración"]
        CONFIG["config.py\n(SSOT: IPs · rutas · topics · URIs)"]
    end

    GPS_FILE --> NIFI
    OW_API --> NIFI
    SIM --> KAFKA
    NIFI --> KAFKA
    NIFI --> HDFS_RAW

    HDFS_RAW --> CLEAN
    CLEAN --> HDFS_PROC
    HDFS_PROC --> ENRICH
    ENRICH --> HDFS_PROC
    HDFS_PROC --> GRAPH
    GRAPH --> HDFS_PROC

    KAFKA --> STREAM
    STREAM --> HIVE
    STREAM --> MONGO
    STREAM --> KAFKA

    HIVE --> ANOMALY
    ANOMALY --> MONGO
    ANOMALY --> KAFKA

    MONGO --> KPI_SCRIPT
    HIVE --> KPI_SCRIPT
    KPI_SCRIPT --> MARIADB

    MARIADB --> GRAFANA
    MARIADB --> SUPERSET
    HIVE --> SUPERSET
    MONGO --> STREAMLIT
    KAFKA --> ALERTS_CON

    AIRFLOW -.->|orquesta| NIFI
    AIRFLOW -.->|orquesta| CLEAN
    AIRFLOW -.->|orquesta| ENRICH
    AIRFLOW -.->|orquesta| GRAPH
    AIRFLOW -.->|orquesta| STREAM
    AIRFLOW -.->|orquesta| ANOMALY
    AIRFLOW -.->|orquesta| KPI_SCRIPT

    CONFIG -.->|importado por| CLEAN
    CONFIG -.->|importado por| ENRICH
    CONFIG -.->|importado por| GRAPH
    CONFIG -.->|importado por| STREAM
    CONFIG -.->|importado por| ANOMALY
    CONFIG -.->|importado por| KPI_SCRIPT
    CONFIG -.->|importado por| AIRFLOW
```

---

## 2. Diagrama de Despliegue (Infraestructura)

Muestra la distribución física de servicios en los tres nodos del clúster.

```mermaid
graph TB
    subgraph Internet["🌐 Internet"]
        OW_EXT[OpenWeather API]
    end

    subgraph Master["🖥️ Nodo Master – hadoop (192.168.99.10)"]
        direction TB
        NN[NameNode\nHDFS]
        RM[ResourceManager\nYARN]
        KAFKA_SVC[Kafka Broker\nKRaft – :9092]
        NIFI_SVC[Apache NiFi\n:8080]
        HIVE_SVC[HiveServer2\n:10000]
        AIRFLOW_SVC[Apache Airflow\n:8080]
        MONGO_SVC[MongoDB\n:27017]
    end

    subgraph Worker1["🖥️ Nodo Worker 1 – nodo1 (192.168.99.12)"]
        DN1[DataNode\nHDFS]
        NM1[NodeManager\nYARN]
    end

    subgraph Worker2["🖥️ Nodo Worker 2 – nodo2 (192.168.99.14)"]
        DN2[DataNode\nHDFS]
        NM2[NodeManager\nYARN]
    end

    subgraph Docker["🐳 Contenedores Docker (demo)"]
        MARIA_C[MariaDB\n:3306]
        GRAFANA_C[Grafana\n:3000]
        SUPERSET_C[Apache Superset\n:8089]
        TOOLS_C[tools container\nPython scripts]
        STREAMLIT_C[Streamlit\n:8501]
    end

    subgraph Cliente["💻 Cliente / Operador"]
        BROWSER[Navegador Web]
        TERMINAL[Terminal / CLI]
    end

    OW_EXT -->|HTTP REST| NIFI_SVC

    NN <-->|replicación bloques| DN1
    NN <-->|replicación bloques| DN2
    RM <-->|tareas YARN| NM1
    RM <-->|tareas YARN| NM2

    NIFI_SVC -->|publica eventos| KAFKA_SVC
    NIFI_SVC -->|escribe ficheros| NN
    KAFKA_SVC -->|consume streaming| RM
    RM -->|ejecuta jobs Spark| NM1
    RM -->|ejecuta jobs Spark| NM2
    HIVE_SVC -->|metastore + datos| NN
    MONGO_SVC -->|escribe agregados| MONGO_SVC

    TOOLS_C -->|lee MongoDB| MONGO_SVC
    TOOLS_C -->|escribe KPIs| MARIA_C
    GRAFANA_C -->|consulta SQL| MARIA_C
    SUPERSET_C -->|consulta SQL| MARIA_C
    STREAMLIT_C -->|lee anomalías| MONGO_SVC

    BROWSER -->|:3000| GRAFANA_C
    BROWSER -->|:8089| SUPERSET_C
    BROWSER -->|:8501| STREAMLIT_C
    BROWSER -->|:8080 Airflow| AIRFLOW_SVC
    BROWSER -->|:8088 YARN UI| RM
    TERMINAL -->|spark-submit / scripts| Master
```

---

## 3. Diagrama de Secuencia – Pipeline KDD Completo

Flujo de datos extremo a extremo desde la ingesta hasta la visualización.

```mermaid
sequenceDiagram
    actor Admin as Administrador
    participant NiFi
    participant Kafka
    participant HDFS
    participant SparkC as Spark Clean
    participant SparkE as Spark Enrich
    participant SparkG as Spark Graph
    participant SparkS as Spark Streaming
    participant SparkML as Spark ML
    participant Hive
    participant MongoDB
    participant MariaDB
    participant Grafana

    Admin->>NiFi: Deposita fichero GPS en directorio entrada
    NiFi->>Kafka: Publica eventos → raw-data
    NiFi->>Kafka: Publica eventos filtrados → filtered-data (speed < 120)
    NiFi->>HDFS: Escribe copia inmutable → /raw/

    Admin->>SparkC: Ejecuta clean_and_normalize.py (vía Airflow)
    SparkC->>HDFS: Lee /raw/
    SparkC->>HDFS: Escribe Parquet → /procesado/cleaned/

    Admin->>SparkE: Ejecuta enrich_with_hive.py
    SparkE->>HDFS: Lee /procesado/cleaned/
    SparkE->>Hive: JOIN con transport.warehouses
    SparkE->>HDFS: Escribe Parquet → /procesado/enriched/

    Admin->>SparkG: Ejecuta transport_graph.py
    SparkG->>Hive: Lee transport.routes
    SparkG->>HDFS: Escribe shortest_paths + connected_components

    Note over Kafka,SparkS: Streaming continuo (Fase III)
    Kafka->>SparkS: Consume raw-data (micro-batches)
    loop Cada ventana de 15 min
        SparkS->>Hive: Append → transport.aggregated_delays
        SparkS->>MongoDB: Insert → aggregated_delays
        alt avg_delay_min > 20
            SparkS->>Kafka: Publica alerta ANOMALY_STREAMING → alerts
        end
    end

    Admin->>SparkML: Ejecuta anomaly_detection.py (batch)
    SparkML->>Hive: Lee transport.aggregated_delays
    SparkML->>SparkML: Entrena K-Means k=3
    SparkML->>MongoDB: Insert → transport.anomalies
    SparkML->>Kafka: Publica alerta ANOMALY → alerts

    Admin->>MariaDB: Ejecuta mongo_to_mariadb_kpi.py
    MongoDB->>MariaDB: KPIs → kpi_delays_by_warehouse / kpi_anomalies

    Grafana->>MariaDB: Consulta SQL (refresco periódico)
    Grafana-->>Admin: Dashboard KPIs actualizado
```

---

## 4. Diagrama de Casos de Uso

Actores y sus interacciones con el sistema.

```mermaid
graph LR
    subgraph Actores
        OP([👤 Operador])
        PL([👤 Planificador])
        AD([👤 Administrador])
    end

    subgraph Sistema Sentinel360
        CU01["CU-01\nMonitorizar retrasos\nen tiempo real"]
        CU02["CU-02\nAnálisis histórico\ny planificación"]
        CU03["CU-03\nDetectar y revisar\nanomalías"]
        CU04["CU-04\nSimular y probar\npipeline E2E"]
        CU05["CU-05\nOrquestar pipeline\ncon Airflow"]
        CU06["CU-06\nArrancar y verificar\nel clúster"]
        CU07["CU-07\nConsultar alertas\nen tiempo real"]
        CU08["CU-08\nExplorar ciclo KDD\nvía Streamlit"]
    end

    OP --> CU01
    OP --> CU03
    OP --> CU07

    PL --> CU02
    PL --> CU03

    AD --> CU04
    AD --> CU05
    AD --> CU06
    AD --> CU08
    AD --> CU01
```

---

## 5. Diagrama de Clases – Modelos de Datos

Esquema lógico de las entidades principales y sus relaciones.

```mermaid
classDiagram
    class EventoGPS {
        +String event_id
        +String vehicle_id
        +Timestamp ts
        +Double lat
        +Double lon
        +Double speed
        +String warehouse_id
    }

    class Almacen {
        +String warehouse_id
        +String name
        +String city
        +String country
        +Double lat
        +Double lon
        +Int capacity
    }

    class Ruta {
        +String route_id
        +String from_warehouse_id
        +String to_warehouse_id
        +Double distance_km
        +Int avg_duration_min
    }

    class VentanaAgregada {
        +Timestamp window_start
        +Timestamp window_end
        +String warehouse_id
        +Double avg_delay_min
        +Long vehicle_count
    }

    class Anomalia {
        +Timestamp window_start
        +Timestamp window_end
        +String warehouse_id
        +Double avg_delay_min
        +Long vehicle_count
        +Int cluster
        +Boolean anomaly_flag
    }

    class Alerta {
        +String type
        +String warehouse_id
        +Timestamp window_start
        +Timestamp window_end
        +Double avg_delay_min
        +Long vehicle_count
        +Double threshold
    }

    class KPI_Almacen {
        +String warehouse_id
        +Datetime window_start
        +Datetime window_end
        +Int trips_count
        +Int delayed_trips
        +Decimal avg_delay_minutes
        +Decimal max_delay_minutes
    }

    class KPI_Vehiculo {
        +String vehicle_id
        +Datetime window_start
        +Datetime window_end
        +Int trips_count
        +Int delayed_trips
        +Decimal avg_delay_minutes
        +Decimal max_delay_minutes
    }

    EventoGPS "N" --> "1" Almacen : warehouse_id
    Ruta "N" --> "1" Almacen : from_warehouse_id
    Ruta "N" --> "1" Almacen : to_warehouse_id
    EventoGPS "N" --> "1" VentanaAgregada : agrupado en
    VentanaAgregada "1" --> "0..1" Anomalia : detectada por K-Means
    VentanaAgregada "1" --> "0..1" Alerta : genera si avg > 20
    Anomalia "1" --> "1" Alerta : genera ANOMALY
    VentanaAgregada "N" --> "1" KPI_Almacen : exportado a MariaDB
    EventoGPS "N" --> "1" KPI_Vehiculo : exportado a MariaDB
```

---

## 6. Diagrama de Estados – Ciclo de Vida de un Evento GPS

```mermaid
stateDiagram-v2
    [*] --> Capturado : NiFi lee fichero GPS

    Capturado --> PublicadoRaw : NiFi → Kafka raw-data
    Capturado --> PublicadoFiltrado : speed < 120 km/h\nNiFi → Kafka filtered-data
    Capturado --> AlmacenadoHDFS : NiFi → HDFS /raw/

    AlmacenadoHDFS --> Limpio : clean_and_normalize.py\n(elimina nulos, dedup, cast ts)
    Limpio --> Descartado : speed < 0 o > 300\no campos obligatorios nulos

    Limpio --> Enriquecido : enrich_with_hive.py\n(join con warehouses)

    Enriquecido --> Agregado : delays_windowed.py\n(ventana 15 min por warehouse)

    Agregado --> EnHive : Spark → Hive aggregated_delays
    Agregado --> EnMongoDB : Spark → MongoDB aggregated_delays
    Agregado --> Anomalo : anomaly_detection.py\n(K-Means cluster anómalo)

    Anomalo --> EnMongoAnomalias : MongoDB transport.anomalies
    Anomalo --> AlertaKafka : Kafka alerts\ntype=ANOMALY

    Agregado --> AlertaStreaming : avg_delay_min > 20\ntype=ANOMALY_STREAMING

    EnHive --> KPI_MariaDB : export_hive_to_mariadb.py
    EnMongoDB --> KPI_MariaDB : mongo_to_mariadb_kpi.py

    KPI_MariaDB --> Visualizado : Grafana / Superset

    Descartado --> [*]
    Visualizado --> [*]
    AlertaKafka --> [*]
    AlertaStreaming --> [*]
```

---

## 7. Diagrama de Actividad – Orquestación Airflow (Pipeline Completo)

```mermaid
flowchart TD
    START([▶ Inicio]) --> INFRA[DAG: infra_start\nArrancar HDFS · YARN · Kafka · NiFi · Hive]
    INFRA --> FASE1[DAG: fase_i_ingesta]

    subgraph FASE1["DAG Fase I – Ingesta"]
        F1A[Crear topics Kafka] --> F1B[Ingestar GPS sintético]
        F1B --> F1C[Ingestar OpenWeather]
        F1C --> F1R[reporte_ejecucion]
    end

    FASE1 --> FASE2[DAG: fase_ii_preprocesamiento]

    subgraph FASE2["DAG Fase II – Preprocesamiento"]
        F2A[Setup tablas Hive] --> F2B[clean_and_normalize]
        F2B --> F2C[enrich_with_hive]
        F2C --> F2D[transport_graph]
        F2D --> F2R[reporte_ejecucion]
    end

    FASE2 --> FASE3B[DAG: fase_iii_batch]
    FASE2 --> FASE3S[DAG: fase_iii_streaming]

    subgraph FASE3B["DAG Fase III – Batch"]
        F3A[write_to_hive_and_mongo] --> F3B[anomaly_detection K-Means]
        F3B --> F3C[mongo_to_mariadb_kpi]
        F3C --> F3R[reporte_ejecucion]
    end

    subgraph FASE3S["DAG Fase III – Streaming"]
        FS1[Iniciar delays_windowed.py\nStreaming continuo]
        FS1 --> FSR[reporte_ejecucion]
    end

    FASE3B --> DASH[DAG: dashboards_exportar\nexport_hive_to_mariadb]
    DASH --> VIZ[Grafana · Superset · Streamlit\nDatos disponibles para visualización]
    VIZ --> END([⏹ Fin])

    FASE3S -.->|alertas continuas| KAFKA_ALERTS[Kafka: alerts\nalerts_consumer.py]
```

---

## Cómo visualizar estos diagramas

### Opción 1 – VS Code (recomendado)
1. Instala la extensión **Markdown Preview Mermaid Support** (`bierner.markdown-mermaid`)
2. Abre este fichero y pulsa `Ctrl+Shift+V` para la vista previa

### Opción 2 – Online (sin instalación)
1. Ve a [https://mermaid.live](https://mermaid.live)
2. Copia el contenido de cualquier bloque ` ```mermaid ` y pégalo en el editor

### Opción 3 – GitHub
Los bloques Mermaid se renderizan automáticamente en cualquier fichero `.md` del repositorio.

### Opción 4 – Exportar a PNG/SVG
En [https://mermaid.live](https://mermaid.live) puedes exportar cada diagrama como PNG o SVG desde el botón "Export".
