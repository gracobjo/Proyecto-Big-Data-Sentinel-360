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

**Dónde buscar**: `docs/HIVE_SENTINEL360.md` (resumen, comandos y enlaces a todo lo relacionado con Hive).

**Crear base y tablas** (recomendado: un solo comando desde la raíz del proyecto):

```bash
./scripts/crear_tablas_hive.sh
```

O a mano con Beeline (más fiable que `hive -f` si usas HiveServer2):

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/02_routes.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/03_events_raw.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/05_reporte_diario.sql
```

Antes: metastore y HiveServer2 en marcha (p. ej. `./scripts/start_servicios.sh`). Después, poblar datos maestros: `./scripts/ingest_from_local.sh`. Comprobar: `./scripts/verificar_tablas_hive.sh`.

**Consultas de ejemplo**:

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/queries/example_report.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/queries/reporte_diario.sql
```

## Integración con Spark

- **enrich_with_hive.py**: lee `transport.warehouses` y hace join con eventos limpios.
- **write_to_hive_and_mongo.py**: escribe agregados en `transport.aggregated_delays`.

Ambos usan `SparkSession.builder.enableHiveSupport()` y el metastore debe estar en marcha.
