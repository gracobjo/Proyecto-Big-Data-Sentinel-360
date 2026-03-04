# Cómo se pueblan las tablas Hive (base `transport`)

En Sentinel360 las tablas de la base **`transport`** se rellenan de dos maneras: **externas** (leyendo archivos en HDFS) y **gestionadas** (escritas por Spark).

---

## 1. Tablas EXTERNAL (se “pueblan” poniendo datos en HDFS)

Hive **no hace INSERT**: lee los ficheros que ya están en la ruta de la tabla.

| Tabla           | Cómo se puebla | Origen de los datos |
|-----------------|----------------|----------------------|
| **warehouses**  | Copiar CSV en la ruta HDFS de la tabla | `./scripts/ingest_from_local.sh` sube `data/sample/warehouses.csv` a `/user/hadoop/proyecto/warehouses/` |
| **routes**      | Igual: CSV en la ruta HDFS             | `ingest_from_local.sh` sube `data/sample/routes.csv` a `/user/hadoop/proyecto/routes/` |
| **events_raw**  | CSV/JSON en la ruta raw                 | NiFi (PutHDFS) escribe en `/user/hadoop/proyecto/raw/`; o `ingest_from_local.sh` copia `gps_events.csv` y `gps_events.json` ahí |

- **warehouses** y **routes**: formato CSV con cabecera; la tabla tiene `skip.header.line.count='1'`.
- **events_raw**: definida con `OpenCSVSerde` (espera CSV). Los ficheros JSON de OpenWeather en `raw/` no encajan en el esquema; solo los CSV tipo `gps_events.csv` (columnas: event_id, vehicle_id, ts, lat, lon, speed, warehouse_id) se leen bien.

---

## 2. Tabla gestionada (la puebla Spark)

| Tabla                | Cómo se puebla | Origen |
|----------------------|----------------|--------|
| **aggregated_delays** | Spark escribe en la tabla / en Parquet en HDFS | Job `spark/streaming/write_to_hive_and_mongo.py` (Fase III): agrega por ventana y hace `df.write.insertInto("transport.aggregated_delays")` o escribe en `LOCATION` |

Hasta que no ejecutes ese job (o uno equivalente), **aggregated_delays** estará vacía.

---

## Comprobar si las tablas están pobladas

Desde la raíz del proyecto:

```bash
# Contar registros (Beeline)
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "
USE transport;
SELECT 'warehouses' AS tabla, COUNT(*) AS n FROM warehouses
UNION ALL SELECT 'routes', COUNT(*) FROM routes
UNION ALL SELECT 'events_raw', COUNT(*) FROM events_raw
UNION ALL SELECT 'aggregated_delays', COUNT(*) FROM aggregated_delays;
"

# Ver algunas filas
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM warehouses LIMIT 5;"
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM routes LIMIT 5;"
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM events_raw LIMIT 5;"
```

O usar el script de comprobación:

```bash
./scripts/verificar_tablas_hive.sh
```

---

## Resumen rápido

1. **warehouses** y **routes**: se pueblan al subir los CSV a HDFS con `./scripts/ingest_from_local.sh`.
2. **events_raw**: se puebla con lo que haya en `/user/hadoop/proyecto/raw/` en formato CSV acorde al esquema (p. ej. `gps_events.csv` subido por `ingest_from_local.sh` o por NiFi).
3. **aggregated_delays**: se puebla cuando se ejecuta el job de Spark que escribe agregados en Hive (Fase III).
