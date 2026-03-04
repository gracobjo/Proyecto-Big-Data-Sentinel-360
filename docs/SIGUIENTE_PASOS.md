# Próximos pasos: PutHDFS (Fase I) + Fases II y III

## Opción A: Completar Fase I – Copia raw en HDFS (PutHDFS)

Para guardar una copia de auditoría en HDFS (`/user/hadoop/proyecto/raw`):

### 1. Controller Service HDFS en NiFi

1. En tu process group → **Configure** (engranaje) → **Controller Services**.
2. Clic en **+** (Add controller service).
3. Busca **HDFSCredentialService** o **StandardHDFSConnectionPoolService** o similar (según tu NiFi 2.7).
4. Si no hay uno HDFS específico, busca **Hadoop Configuration Resources**: añade un controller service que permita configurar HDFS y pon la ruta a `core-site.xml` (p. ej. `/usr/local/hadoop/etc/hadoop/core-site.xml`) donde esté `fs.defaultFS=hdfs://192.168.99.10:9000`.
5. **Enable** el servicio.

### 2. PutHDFS para InvokeHTTP (datos HTTP)

1. Añade el procesador **PutHDFS**.
2. **Properties**:
   - **Directory**: `/user/hadoop/proyecto/raw/weather`
   - **Hadoop Configuration Resources** o **HDFS Connection**: selecciona el controller service HDFS creado.
   - **Conflict Resolution**: `replace` o `ignore`.
3. Conecta **InvokeHTTP (Response)** → **PutHDFS**.
4. **Start** PutHDFS.

### 3. PutHDFS para GetFile (datos GPS)

1. Otro procesador **PutHDFS** (o el mismo si quieres todo en la misma carpeta).
2. **Directory**: `/user/hadoop/proyecto/raw/gps` (o `/user/hadoop/proyecto/raw`).
3. Conecta **GetFile (success)** → **PutHDFS**.
4. **Start**.

**Nota:** Si NiFi 2.7 no tiene PutHDFS o el controller HDFS es complejo, puedes usar **PutFile** apuntando a una carpeta local y luego copiar a HDFS con `hdfs dfs -put`, o usar **ExecuteStreamCommand** con `hdfs dfs -put`. La opción más limpia es PutHDFS si está disponible.

---

## Opción B: Fases II y III (Spark, Hive, Grafos, Streaming)

### Orden de ejecución

```bash
cd ~/Documentos/ProyectoBigData
```

**1. Rutas HDFS y datos (si no está hecho)**

```bash
./scripts/setup_hdfs.sh
./scripts/ingest_from_local.sh
```

**2. Hive – metastore y tablas**

```bash
nohup hive --service metastore > logs/hive-metastore.log 2>&1 &
sleep 5
hive -f hive/schema/01_warehouses.sql
hive -f hive/schema/02_routes.sql
hive -f hive/schema/03_events_raw.sql
hive -f hive/schema/04_aggregated_reporting.sql
```

**3. Datos en HDFS raw**

Los datos deben estar en `/user/hadoop/proyecto/raw` (CSV/JSON). Si usaste solo NiFi hacia Kafka, copia los datos de ejemplo a HDFS:

```bash
hdfs dfs -put -f data/sample/gps_events.csv data/sample/gps_events.json /user/hadoop/proyecto/raw/
hdfs dfs -put -f data/sample/warehouses.csv /user/hadoop/proyecto/warehouses/
hdfs dfs -put -f data/sample/routes.csv /user/hadoop/proyecto/routes/
```

**4. Jobs Spark**

```bash
# Limpieza (Fase II)
./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py

# Enriquecimiento con Hive (Fase II) – requiere tablas warehouses cargadas
./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py

# Grafos (Fase II)
./scripts/run_spark_submit.sh spark/graph/transport_graph.py

# Streaming ventanas 15 min (Fase III) – opcional, se queda escuchando
# ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file
```

**5. Comprobar**

```bash
hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned
hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched
hdfs dfs -ls /user/hadoop/proyecto/procesado/graph
```

---

## Resumen rápido

| Paso | Acción |
|------|--------|
| **PutHDFS (NiFi)** | Añadir PutHDFS, configurar HDFS controller, conectar InvokeHTTP (Response) y GetFile (success) → PutHDFS |
| **Datos HDFS** | `ingest_from_local.sh` o copiar manualmente a `/user/hadoop/proyecto/raw` |
| **Hive** | metastore + DDL (01–04) |
| **Spark** | clean → enrich → graph (y streaming si quieres) |
