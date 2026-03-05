# Hive en Sentinel360 – Dónde buscar y qué hacer

Guía de referencia para trabajar con la base Hive `transport` en Sentinel360.

---

## Dónde buscar esta información

| Necesitas… | Dónde está |
|------------|------------|
| **Crear la base y todas las tablas** | `./scripts/crear_tablas_hive.sh` (ejecuta 01 a 05 con Beeline). O a mano: `hive/README.md` → sección *Orden de ejecución*. |
| **Comandos Beeline** (crear tabla por tabla) | `docs/HOWTO_EJECUCION.md` → **Supuesto 2** (Hive – Base transport y tablas). |
| **Cómo se pueblan las tablas** (EXTERNAL vs Spark) | `docs/POBLAR_TABLAS_HIVE.md`. |
| **Comprobar que hay datos** | `./scripts/verificar_tablas_hive.sh`. |
| **Relación con el enunciado / PDF** | `docs/ANALISIS_HIVE.md`. |
| **Esquemas SQL** | `hive/schema/` (01_warehouses.sql … 05_reporte_diario.sql). |
| **Consultas de ejemplo** | `hive/queries/` (example_report.sql, reporte_diario.sql). |

Búsqueda en el repo: `beeline`, `transport`, `warehouses`, `aggregated_delays`, `verificar_tablas_hive`.

---

## Requisitos previos

1. **MariaDB/MySQL** (metastore de Hive) en marcha (p. ej. XAMPP: `sudo /opt/lampp/lampp startmysql`).
2. **Hive Metastore** y **HiveServer2** en marcha (p. ej. con `./scripts/start_servicios.sh`).
3. Rutas HDFS existentes (opcional para DDL; necesario para que las tablas EXTERNAL vean datos):  
   `./scripts/setup_hdfs.sh`.

---

## Orden típico (resumen)

```bash
# 1. Arrancar servicios (incluye Hive si está en start_servicios.sh)
./scripts/start_servicios.sh

# 2. Crear base y tablas (una sola vez)
./scripts/crear_tablas_hive.sh

# 3. Poblar datos maestros y raw (warehouses, routes, events en HDFS)
./scripts/ingest_from_local.sh

# 4. Comprobar
./scripts/verificar_tablas_hive.sh
```

---

## Tablas de la base `transport`

| Tabla | Tipo | Cómo se puebla |
|-------|------|----------------|
| **warehouses** | EXTERNAL | CSV en HDFS `/user/hadoop/proyecto/warehouses/` (p. ej. `ingest_from_local.sh`) |
| **routes** | EXTERNAL | CSV en HDFS `/user/hadoop/proyecto/routes/` |
| **events_raw** | EXTERNAL | Ficheros en `/user/hadoop/proyecto/raw/` (CSV acorde al esquema) |
| **aggregated_delays** | MANAGED/Parquet | Spark (streaming o batch): `delays_windowed.py` o `write_to_hive_and_mongo.py` |
| **reporte_diario_retrasos** | MANAGED/Parquet | Opcional: DAG Airflow o job que escriba el resumen diario |

---

## Comandos útiles

```bash
# Listar tablas
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SHOW TABLES;"

# Contar registros por tabla
./scripts/verificar_tablas_hive.sh

# Consultas de ejemplo
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/queries/example_report.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/queries/reporte_diario.sql
```

Más detalle: `hive/README.md`, `docs/POBLAR_TABLAS_HIVE.md`, `docs/ANALISIS_HIVE.md`.
