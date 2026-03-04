# Análisis del uso de Hive en Sentinel360 (según PDF)

Documento que relaciona los requisitos del enunciado con la implementación actual de **Apache Hive** en Sentinel360.

---

## 1. Qué dice el PDF sobre Hive

### Requisitos técnicos (Stack Apache 2026)

- **Almacenamiento**: *"HDFS 3.4.2 & ... (NoSQL) / **Apache Hive (SQL)**"* — en Sentinel360 la capa NoSQL es **MongoDB**.
- Hive es la capa **SQL** (reporting histórico); MongoDB es la capa **NoSQL** para consultas de baja latencia (estado por vehículo).

### Fase II – Preprocesamiento y transformación

- *"**Enriquecimiento**: Cruzar el streaming de Kafka con **datos maestros almacenados en Hive**."*
- Los datos maestros (almacenes, rutas) deben estar en Hive para que Spark los use en el enriquecimiento (join con el flujo de eventos).

### Fase III – Minería y acción

- *"**Carga multicapa**:*
  - ***Relacional (Hive)**: Datos agregados para reporting histórico.*
  - *NoSQL (MongoDB): Último estado conocido de cada vehículo."*
- Hive almacena los **agregados históricos** (por ejemplo ventanas de retrasos) para reporting y análisis SQL.

### Rúbrica de evaluación

- **Persistencia (Excelente)**: *"Uso correcto de NoSQL y **Hive (SQL)** según el caso de uso."*
- En Sentinel360: Hive para SQL/reporting histórico; **MongoDB** para estado reciente por vehículo.

### Ejemplo de referencia (NYC Taxi)

- *"**Airflow** genera un **reporte diario** de ingresos y **lo guarda en Hive**."*
- Equivalente en Sentinel360: un proceso (p. ej. DAG de Airflow o job programado) que genere un reporte periódico y persista resultados en tablas Hive.

---

## 2. Mapeo PDF → implementación en Sentinel360

| Requisito PDF | Implementación en Sentinel360 |
|---------------|-------------------------------|
| **Hive (SQL)** como capa de almacenamiento | Base de datos Hive `transport` y tablas en `hive/schema/`. |
| **Datos maestros en Hive** para enriquecimiento | Tablas `warehouses` y `routes` (HDFS: `/user/hadoop/proyecto/warehouses`, `.../routes`). Lectura en `spark/cleaning/enrich_with_hive.py` con `spark.table("transport.warehouses")`. |
| **Agregados en Hive** para reporting histórico | Tabla `aggregated_delays` (Parquet en `/user/hadoop/proyecto/procesado/aggregated_delays`). Escritura desde Spark en `spark/streaming/write_to_hive_and_mongo.py`. |
| **Reporte diario guardado en Hive** (ej. NYC) | Consultas de ejemplo en `hive/queries/`. Opcional: DAG Airflow que ejecute una query y guarde resultado en una tabla de reportes (ver más abajo). |

---

## 3. Esquema Hive actual

```
transport (database)
├── warehouses      → datos maestros (almacenes); EXTERNAL, texto en HDFS
├── routes          → datos maestros (rutas); EXTERNAL, texto en HDFS
├── events_raw      → eventos crudos; EXTERNAL, apunta a /user/hadoop/proyecto/raw
└── aggregated_delays → agregados por ventana (15 min); MANAGED, Parquet
```

- **Datos maestros**: `warehouses`, `routes` → usados en **Fase II** (enriquecimiento).
- **Agregados**: `aggregated_delays` → usados en **Fase III** (reporting histórico).
- **Crudos**: `events_raw` → opcional para consultas SQL sobre raw en HDFS.

---

## 4. Flujo de datos con Hive

1. **Carga inicial de maestros**  
   Los CSV de `warehouses` y `routes` se suben a HDFS (`ingest_from_local.sh`). Las tablas EXTERNAL de Hive apuntan a esas rutas; no hace falta cargar datos “dentro” de Hive, solo crear las tablas con `hive -f hive/schema/01_warehouses.sql` y `02_routes.sql`.

2. **Fase II – Enriquecimiento**  
   `enrich_with_hive.py` lee eventos limpios (Parquet) y hace join con `transport.warehouses` vía Spark con `enableHiveSupport()`. El resultado se escribe en Parquet en HDFS (no obligatoriamente en otra tabla Hive).

3. **Fase III – Carga multicapa**  
   Los agregados (ventanas de retrasos) se escriben en la tabla Hive `aggregated_delays` con `write_to_hive_and_mongo.py` (`df.write.insertInto("transport.aggregated_delays")`). Así quedan disponibles para **reporting histórico** vía SQL (Hive CLI, Beeline, Spark SQL).

4. **Reporte diario (equivalente NYC)**  
   Consultas en `hive/queries/` (p. ej. `example_report.sql`). Opcional: DAG Airflow que ejecute una query de resumen y guarde el resultado en una tabla tipo `transport.reporte_diario_retrasos`.

---

## 5. Cómo cumplir bien la rúbrica (Hive + NoSQL)

- **Hive (SQL)**  
  - Datos maestros en tablas Hive y usados en el enriquecimiento.  
  - Agregados históricos en `aggregated_delays` (y opcionalmente tablas de reportes).  
  - Uso de Hive/Spark SQL para consultas de reporting.

- **NoSQL (MongoDB)**  
  - Último estado por vehículo en MongoDB (colección `vehicle_state`) para consultas de baja latencia.  
  - No mezclar ese caso de uso con Hive; cada capa para su propósito.

---

## 6. Orden recomendado de uso de Hive

1. Arrancar **Metastore** (y opcionalmente HiveServer2):  
   `nohup hive --service metastore &`  
   (y opcionalmente `nohup hive --service hiveserver2 &`).

2. Crear esquema y tablas:  
   `hive -f hive/schema/01_warehouses.sql`  
   `hive -f hive/schema/02_routes.sql`  
   `hive -f hive/schema/03_events_raw.sql`  
   `hive -f hive/schema/04_aggregated_reporting.sql`

3. Subir datos maestros a HDFS (si no está hecho):  
   `./scripts/ingest_from_local.sh`

4. Ejecutar pipeline Spark que use Hive:  
   limpieza → `enrich_with_hive.py` (usa `transport.warehouses`) → después jobs que generen agregados y los escriban en `aggregated_delays` con `write_to_hive_and_mongo.py`.

5. Consultas de reporting:  
   `hive -f hive/queries/example_report.sql` o Beeline/Spark SQL sobre `transport.aggregated_delays`.

---

## 7. Resumen

| Uso de Hive en el PDF | Cubierto en Sentinel360 |
|------------------------|-------------------------|
| Capa SQL del almacenamiento | Sí: DB `transport`, tablas en HDFS/Parquet |
| Datos maestros para enriquecimiento | Sí: `warehouses`, `routes`; usados en `enrich_with_hive.py` |
| Agregados para reporting histórico | Sí: `aggregated_delays`; escritura desde Spark |
| Reporte diario guardado en Hive (ej. NYC) | Parcial: consultas en `hive/queries/`; opcional DAG que persista reporte en tabla Hive |
