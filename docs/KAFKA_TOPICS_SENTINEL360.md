# Topics Kafka de Sentinel360

## Dónde buscar esta información

Si necesitas recordar cómo listar temas, ver mensajes o crear los topics de Sentinel360:

- **Este documento**: `docs/KAFKA_TOPICS_SENTINEL360.md` — temas del proyecto, comandos de listado, consumer y creación.
- **README**: sección *Topics Kafka del proyecto* con enlace a este doc y al script `./scripts/verificar_topics_kafka.sh`.
- **En el repo**: buscar `raw-data`, `filtered-data`, `kafka-console-consumer` o `kafka-topics` (p. ej. en `docs/`, `scripts/`, `config.py`).

Resumen rápido de comandos: más abajo en este mismo archivo (secciones *Comprobar que existen* y *Ver mensajes*).

---

En este proyecto se usan **solo dos temas Kafka**:

| Topic | Uso |
|-------|-----|
| **raw-data** | Entrada principal. NiFi publica aquí: logs GPS (GetFile) y respuestas de la API OpenWeather (InvokeHTTP). Es la fuente para el streaming (delays_windowed.py) y para la copia raw en HDFS. |
| **filtered-data** | Datos filtrados. Opcionalmente, NiFi (o un flujo posterior) publica en este tema los eventos ya filtrados para consumo downstream (dashboards, alertas, etc.). |

El resto de temas que pueda haber en el broker (p. ej. `__consumer_offsets`, `connect-*`, etc.) son internos de Kafka o de otros proyectos; **Sentinel360 se centra en raw-data y filtered-data**.

## Configuración

En `config.py`:

- `KAFKA_TOPIC_RAW = "raw-data"`
- `KAFKA_TOPIC_FILTERED = "filtered-data"`

Broker: `192.168.99.10:9092` (o `KAFKA_BOOTSTRAP_SERVERS` en config).

## Crear los temas (si no existen)

```bash
./scripts/preparar_ingesta_nifi.sh
```

O a mano (con Kafka en `$KAFKA_HOME`, p. ej. `/home/hadoop/software/kafka_2.13-4.1.1`):

```bash
export KAFKA_HOME=/home/hadoop/software/kafka_2.13-4.1.1
BOOTSTRAP=192.168.99.10:9092
$KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server $BOOTSTRAP --create --if-not-exists --topic raw-data --partitions 3 --replication-factor 1
$KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server $BOOTSTRAP --create --if-not-exists --topic filtered-data --partitions 3 --replication-factor 1
```

## Comprobar que existen

```bash
./scripts/verificar_topics_kafka.sh
```

O manualmente:

```bash
export KAFKA_HOME=/home/hadoop/software/kafka_2.13-4.1.1
$KAFKA_HOME/bin/kafka-topics.sh --bootstrap-server 192.168.99.10:9092 --list | grep -E 'raw-data|filtered-data'
```

## Ver mensajes (prueba rápida)

```bash
export KAFKA_HOME=/home/hadoop/software/kafka_2.13-4.1.1   # ajustar si tu Kafka está en otra ruta
BOOTSTRAP=192.168.99.10:9092

# Últimos mensajes de raw-data (entrada principal: GPS + OpenWeather)
$KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server $BOOTSTRAP --topic raw-data --from-beginning --max-messages 10

# Últimos mensajes de filtered-data (datos filtrados)
$KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server $BOOTSTRAP --topic filtered-data --from-beginning --max-messages 10
```

Sin `--max-messages` el consumer se queda escuchando hasta que lo detengas con **Ctrl+C**.
