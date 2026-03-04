# Arranque de servicios (Kafka, MongoDB, Spark, Hadoop, Hive, NiFi)

## Resolver problemas frecuentes

- **KAFKA_HOME no encontrado**: El script busca en `~/software/kafka_2.13-4.1.1`, `~/software/confluent-7.5.0` y otras rutas. Si Kafka está en `~/software/kafka_2.13-4.1.1`, ya está en `config/rutas_servicios.env` (export activo). Para el clúster, el broker debe escuchar en **192.168.99.10:9092**: en `$KAFKA_HOME/config/server.properties` pon `listeners=PLAINTEXT://192.168.99.10:9092` y `advertised.listeners=PLAINTEXT://192.168.99.10:9092`.
- **Spark History Server: FileNotFoundException file:/tmp/spark-events**: El script crea ya ese directorio. Si falla, créalo a mano: `mkdir -p /tmp/spark-events && chmod 1777 /tmp/spark-events`. En `config/spark-defaults.conf` está configurado `spark.history.fs.logDirectory`.
- **MongoDB "Data directory /data/db not found"**: Al ejecutar `mongod` a mano usa por defecto `/data/db`. Opciones: (1) Usar el servicio: `sudo systemctl start mongod`. (2) El script arranca mongod con `--dbpath` en `data/mongodb_db` del proyecto; o en tu casa: `mkdir -p ~/data/db && mongod --dbpath ~/data/db`.

## Script único (recomendado)

Desde la **raíz del proyecto**:

```bash
chmod +x scripts/start_servicios.sh scripts/stop_servicios.sh
./scripts/start_servicios.sh
```

Para detener:

```bash
./scripts/stop_servicios.sh
```

Para apagar también HDFS y YARN:

```bash
STOP_HADOOP=1 ./scripts/stop_servicios.sh
```

---

## Rutas por defecto

El script usa estas rutas si no defines las variables de entorno:

| Servicio | Variable      | Por defecto           |
|----------|---------------|------------------------|
| Hadoop   | HADOOP_HOME   | /usr/local/hadoop      |
| Kafka    | KAFKA_HOME    | /usr/local/kafka       |
| Spark    | SPARK_HOME    | /usr/local/spark       |
| NiFi     | NIFI_HOME     | /usr/local/nifi        |
| Hive     | HIVE_HOME     | /usr/local/hive        |

Ejemplo con rutas distintas:

```bash
export KAFKA_HOME=/opt/kafka
export SPARK_HOME=$HOME/spark-3.5.0
./scripts/start_servicios.sh
```

---

## Kafka (KRaft) – Primera vez

Si Kafka usa **KRaft** (sin Zookeeper), la primera vez hay que formatear el almacenamiento:

1. Generar un ID de clúster:
   ```bash
   $KAFKA_HOME/bin/kafka-storage.sh random-uuid
   ```
   (ejemplo de salida: `abcd1234-...`)

2. Formatear (sustituir `TU_UUID` por el valor anterior):
   ```bash
   $KAFKA_HOME/bin/kafka-storage.sh format -t TU_UUID -c $KAFKA_HOME/config/kraft/server.properties
   ```

3. Arrancar Kafka con el script:
   ```bash
   ./scripts/start_servicios.sh
   ```

4. Crear el tema del proyecto (broker en 192.168.99.10:9092):
   ```bash
   $KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server 192.168.99.10:9092 --create --topic raw-data --partitions 3 --replication-factor 1
   ```

Si usas **Zookeeper** (modo clásico), en lugar de `config/kraft/server.properties` usa `config/server.properties` y arranca antes Zookeeper.

---

## Qué arranca cada servicio

| Servicio | Qué hace |
|----------|----------|
| **Hadoop** | Si HDFS/YARN no responden, ejecuta `start-dfs.sh` y `start-yarn.sh`. |
| **Kafka** | Inicia el broker (KRaft o clásico) en segundo plano. Logs en `logs/kafka.log`. |
| **MongoDB** | Intenta `systemctl start mongod` o, si no, `mongod` en segundo plano. Logs en `logs/mongodb.log`. |
| **Spark** | Solo el **History Server** (opcional). Los jobs se lanzan con `./scripts/run_spark_submit.sh`. |
| **Hive** | No se arranca automáticamente. Si lo usas: `nohup hive --service metastore &` y opcionalmente `hive --service hiveserver2 &`. |
| **NiFi** | Si existe `NIFI_HOME`, ejecuta `nifi.sh start`. |

---

## Comprobar que todo está bien

```bash
./scripts/verificar_cluster.sh
```

Deberías ver [OK] en HDFS, YARN, Kafka (puerto 9092) y `config.py`.
