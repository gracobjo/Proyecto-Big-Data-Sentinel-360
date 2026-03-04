# Hive en Sentinel360 (ciclo KDD)

Según el enunciado del proyecto, Hive es la capa **SQL** del almacenamiento en Sentinel360:

- **Fase II**: datos maestros (almacenes, rutas) en Hive para enriquecimiento con Spark.
- **Fase III**: datos agregados para reporting histórico (tabla `aggregated_delays`).
- **Rúbrica**: uso correcto de Hive (SQL) y MongoDB (NoSQL) según el caso de uso.
- **Ejemplo NYC**: reporte diario generado (p. ej. por Airflow) y guardado en Hive.

Análisis detallado: **`docs/ANALISIS_HIVE.md`**.

## Esquema (`hive/schema/`)

| Script | Tabla | Uso |
|--------|--------|-----|
| 01_warehouses.sql | warehouses | Datos maestros (nodos del grafo); enriquecimiento |
| 02_routes.sql | routes | Rutas entre almacenes; GraphFrames |
| 03_events_raw.sql | events_raw | Eventos crudos (HDFS raw) |
| 04_aggregated_reporting.sql | aggregated_delays | Agregados por ventana; reporting histórico |
| 05_reporte_diario.sql | reporte_diario_retrasos | Resumen diario (ej. desde Airflow) |

## Orden de ejecución

```bash
# 1. Arrancar metastore (una vez)
nohup hive --service metastore > logs/hive-metastore.log 2>&1 &

# 2. Crear tablas (rutas HDFS deben existir; datos maestros vía ingest_from_local.sh)
hive -f hive/schema/01_warehouses.sql
hive -f hive/schema/02_routes.sql
hive -f hive/schema/03_events_raw.sql
hive -f hive/schema/04_aggregated_reporting.sql
hive -f hive/schema/05_reporte_diario.sql

# 3. Consultas de ejemplo
hive -f hive/queries/example_report.sql
hive -f hive/queries/reporte_diario.sql   # rellena reporte_diario_retrasos
```

## Integración con Spark

- **enrich_with_hive.py**: lee `transport.warehouses` y hace join con eventos limpios.
- **write_to_hive_and_mongo.py**: escribe agregados en `transport.aggregated_delays`.

Ambos usan `SparkSession.builder.enableHiveSupport()` y el metastore debe estar en marcha.
