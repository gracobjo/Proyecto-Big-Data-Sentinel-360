# Cómo probar el pipeline Sentinel360

Pasos para ejecutar y verificar el flujo completo (Fase I ya verificada → Fase II → opcional III).

---

## Si hay errores en los nodos: ejecutar en local

Cuando YARN falla en los nodos (p. ej. **No space left on device**, **AM Container exited with exitCode -1000**, **Download and unpack failed**), el job no llega a ejecutarse. Para que **no falle** y poder seguir probando el pipeline, usa el modo **local** (todo corre en la máquina donde lanzas el comando, sin contenedores YARN):

```bash
./scripts/run_spark_submit.sh --local spark/cleaning/clean_and_normalize.py
./scripts/run_spark_submit.sh --local spark/cleaning/enrich_with_hive.py
./scripts/run_spark_submit.sh --local spark/graph/transport_graph.py
```

Equivalente con la forma corta: `-l` en lugar de `--local`. Cuando liberes espacio en los nodos o arregles YARN, puedes volver a ejecutar sin `--local` para usar el clúster.

---

## Errores frecuentes al ejecutar Spark en YARN

- **PYTHON_VERSION_MISMATCH** (driver 3.13, worker 3.12): PySpark exige la misma versión menor en driver y workers. El script `run_spark_submit.sh` intenta fijar `PYSPARK_PYTHON` y `PYSPARK_DRIVER_PYTHON` a la misma (p. ej. `python3.12`). Si sigue fallando, ejecuta antes: `export PYSPARK_DRIVER_PYTHON=python3.12` y `export PYSPARK_PYTHON=python3.12` (o la versión que tengan los nodos workers).
- **No space left on device** en nodo1/nodo2 (o AM container exitCode -1000): YARN no puede descomprimir los JARs en el nodo donde arranca el contenedor. **Para que no falle**, ejecuta en **modo local** (sin YARN, todo en la máquina actual):  
  `./scripts/run_spark_submit.sh --local spark/cleaning/enrich_with_hive.py`  
  Alternativas: liberar espacio en los nodos (logs, `/tmp`, cache de YARN) o `NUM_EXECUTORS=1` (el AM puede seguir cayendo en un worker con disco lleno).
- **"Job 0 cancelled because SparkContext was shut down"** al leer Parquet: suele ser un *efecto secundario*. El fallo real está en YARN (un ejecutor murió: disco lleno, container killed, etc.). Revisa la aplicación en http://hadoop:8088/cluster/app/application_XXX. **Solución:** ejecutar en local: `./scripts/run_spark_submit.sh --local <script.py>`.

### Hive Metastore / HiveServer2 no arrancan

Si al ejecutar `./scripts/start_servicios.sh` ves:

- `[?] Hive Metastore no arrancó. Comprobar: tail -20 logs/hive-metastore.log`
- `[?] HiveServer2 no arrancó (opcional). Ver: tail logs/hive-hiveserver2.log`

**Causa:** El Metastore de Hive guarda los metadatos en **MySQL/MariaDB** (puerto 3306). Si la base no está en marcha o no acepta conexiones, Hive falla con `MetaException: Connection refused`.

**Qué hacer:**

1. Arrancar MySQL/MariaDB **antes** que Hive:
   - **XAMPP:** `sudo /opt/lampp/lampp startmysql`
   - **systemd:** `sudo systemctl start mariadb`
2. Comprobar que escucha en 3306: `nc -z localhost 3306` (o `ss -tlnp | grep 3306`).
3. Volver a arrancar solo Hive:
   ```bash
   nohup hive --service metastore >> logs/hive-metastore.log 2>&1 &
   sleep 3
   nohup hive --service hiveserver2 >> logs/hive-hiveserver2.log 2>&1 &
   ```
4. Ver errores: `tail -30 logs/hive-metastore.log` (busca `Connection refused` o `jdbc:mysql`).

El script `start_servicios.sh` intenta arrancar MariaDB antes que Hive; si MariaDB no arranca (p. ej. hace falta `sudo`), Hive se omite y se muestra el aviso. Arranca MySQL manualmente y luego Hive como arriba.

### "com.mysql.cj.jdbc.Driver was not found in the CLASSPATH" (Spark + Hive)

Al ejecutar `enrich_with_hive.py` (o cualquier job con `enableHiveSupport()`), Spark necesita el **driver JDBC de MySQL/MariaDB** en su classpath. Si falta, verás:

`DatastoreDriverNotFoundException: The specified datastore driver ("com.mysql.cj.jdbc.Driver") was not found in the CLASSPATH`

**Solución:** El script `run_spark_submit.sh` intenta añadir automáticamente el JAR desde `$HIVE_HOME/lib/` (p. ej. `mysql-connector-j-8.0.33.jar` o `mariadb-java-client-*.jar`). Asegúrate de que en `/usr/local/hive/lib/` exista uno de esos JARs. Si Hive está en otra ruta, exporta `HIVE_HOME` antes de ejecutar:

```bash
export HIVE_HOME=/usr/local/hive
./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
```

Si no tienes el connector en Hive, descárgalo y pásalo explícitamente:  
`spark-submit --jars /ruta/a/mysql-connector-j-8.x.x.jar ...`

---

## Estado actual (tras verificación)

- **HDFS raw:** hay datos (p. ej. `gps_events.json`, CSV, etc. en `/user/hadoop/proyecto/raw`).
- **Kafka:** topics `raw-data` y `filtered-data` existen.
- **Clúster:** HDFS, YARN, Kafka, Spark OK. NiFi no está corriendo (opcional para volver a ingestar).

---

## Opción A: Script automático (Fase II)

Ejecuta los jobs Spark en orden: limpieza → enriquecimiento → grafo.

```bash
cd ~/Documentos/ProyectoBigData

# Si ya creaste las tablas Hive (01 a 04), usa --skip-hive y --yes para no preguntar
./scripts/probar_pipeline.sh --skip-hive --yes

# Si quieres que pregunte por las tablas Hive
./scripts/probar_pipeline.sh
```

Requisito: **tablas Hive creadas** (ver abajo).

---

## Opción B: Pasos manuales

### 1. Tablas Hive (solo la primera vez)

```bash
./scripts/crear_tablas_hive.sh
```

O con beeline:

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/01_warehouses.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/02_routes.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/03_events_raw.sql
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -f hive/schema/04_aggregated_reporting.sql
```

### 2. Subir datos maestros a HDFS (si no están)

```bash
hdfs dfs -put data/sample/warehouses.csv /user/hadoop/proyecto/warehouses/
hdfs dfs -put data/sample/routes.csv /user/hadoop/proyecto/routes/
```

### 3. Fase II – Spark (orden obligatorio)

```bash
./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
./scripts/run_spark_submit.sh spark/graph/transport_graph.py
```

Si hay errores en los nodos (disco lleno, AM failed), usa `--local` antes del script para ejecutar en la máquina actual sin YARN (ver sección «Si hay errores en los nodos: ejecutar en local»).

### 4. Comprobar salidas en HDFS

```bash
hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned
hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched
hdfs dfs -ls /user/hadoop/proyecto/procesado/graph
```

**Salidas esperadas:**

| Ruta | Contenido esperado |
|------|--------------------|
| `procesado/cleaned` | `_SUCCESS` + uno o más `part-*-*.snappy.parquet` (datos limpios). |
| `procesado/enriched` | `_SUCCESS` + uno o más `part-*-*.snappy.parquet` (eventos enriquecidos con warehouses). |
| `procesado/graph` | Directorios: `connected_components/` y `shortest_paths/` (cada uno con `_SUCCESS` y Parquet). |

Si `enriched` no existe o está vacío, ejecuta antes el enriquecimiento con Hive en marcha:  
`./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py`

### 5. Fase III (opcional) – Streaming

Modo **file** (lee de HDFS raw y termina; útil para prueba):

```bash
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file
```

Modo **kafka** (queda escuchando; para datos en tiempo real):

```bash
./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka
```

Luego comprobar Hive y MongoDB:

```bash
beeline -u "jdbc:hive2://localhost:10000" -n hadoop -e "USE transport; SELECT * FROM aggregated_delays LIMIT 5;"
mongosh --eval "db.getSiblingDB('transport').aggregated_delays.find().limit(5)"
```

---

## Volver a probar Fase I (NiFi)

1. Arrancar NiFi:  
   `/opt/nifi/nifi-2.7.2/bin/nifi.sh start`
2. Abrir UI: `http://192.168.99.10:8080/nifi` (o localhost si es local).
3. Importar flujo: `ingest/gps_transport_flow_importable.json`.
4. Habilitar **Kafka3ConnectionService** en el Process Group.
5. Poner datos en entrada:  
   `cp data/sample/gps_events.json /home/hadoop/data/gps_logs/`
6. Iniciar el Process Group.
7. Verificar:  
   `./scripts/verificar_ingesta_gps.sh`

---

## Resumen de scripts útiles

| Script | Uso |
|--------|-----|
| `./scripts/verificar_cluster.sh` | Comprueba HDFS, YARN, Kafka, NiFi, datos sample |
| `./scripts/verificar_ingesta_gps.sh` | Comprueba HDFS raw y topics Kafka |
| `./scripts/verificar_tablas_hive.sh` | Comprueba tablas de la BD `transport` |
| `./scripts/probar_pipeline.sh` | Ejecuta Fase II (y opcional III) en orden |
| `./scripts/run_spark_submit.sh <script.py>` | Lanza un job Spark en YARN |
