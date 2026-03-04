# Ingesta con NiFi (Fase I): GPS ficticios + HTTP

NiFi debe estar instalado y en marcha. Comprobar:

```bash
./scripts/verificar_nifi.sh
```

Si no está instalado, descarga desde [nifi.apache.org](https://nifi.apache.org/) (p. ej. 2.6.x) y descomprime en `~/nifi` o `~/software/nifi-2.6.0`. Arrancar: `$NIFI_HOME/bin/nifi.sh start`. UI: **http://localhost:8080/nifi** (o https://localhost:8443/nifi si usas SSL).

---

## Configuración del clúster (antes de crear flujos)

En NiFi, usa estas variables o configúralas en los procesadores:

| Variable | Valor |
|----------|--------|
| Kafka bootstrap | `192.168.99.10:9092` |
| Tema crudo | `raw-data` |
| Tema filtrado | `filtered-data` |
| HDFS NameNode | `hdfs://192.168.99.10:9000` |
| Ruta HDFS raw | `/user/hadoop/proyecto/raw` |

---

## 1. Flujo: GPS ficticios (logs simulados)

**Objetivo**: Leer archivos CSV/JSON de logs GPS (p. ej. generados por `data/sample/generate_gps_logs.py`) y enviarlos a Kafka y a HDFS.

### Procesadores (arrastrar y configurar)

| Orden | Procesador | Propósito |
|-------|------------|-----------|
| 1 | **GetFile** | Lee archivos de una carpeta. Directorio: ruta a `data/sample` o a una carpeta que contenga `gps_events.csv` / `*.json`. Mantener archivos después de leer (opcional) o mover a `./processed`. |
| 2 | **SplitText** (opcional) | Si quieres un evento por línea (JSON línea a línea), usar SplitText por línea; para CSV puede ir directo o con SplitText por líneas. |
| 3 | **PublishKafkaRecord** o **PublishKafka** (2.6) | Envía cada flowfile al tema Kafka. Kafka Brokers: `192.168.99.10:9092`, Topic: `raw-data`. Para JSON/CSV como valor: Key (vacío o atributo), Value = contenido del flowfile. |
| 4 | **PutHDFS** | Escribe en HDFS. Directory: `/user/hadoop/proyecto/raw`. Conflict Resolution: replace o ignore. Configurar HDFS con NameNode `hdfs://192.168.99.10:9000` (o usar Controller Service HDFS con esa URL). |

**Conexiones**: GetFile → PublishKafka; GetFile → PutHDFS (o GetFile → SplitText → PublishKafka y PutHDFS según quieras un evento por mensaje Kafka).

**Generar datos de prueba** (en la máquina donde está la carpeta que vigila NiFi):

```bash
cd ~/Documentos/ProyectoBigData
python data/sample/generate_gps_logs.py
# Copiar a la carpeta que vigila NiFi, o configurar GetFile con Directory = .../ProyectoBigData/data/sample
```

---

## 2. Flujo: HTTP (API externa, p. ej. OpenWeather)

**Objetivo**: Llamar a una API HTTP periódicamente y enviar la respuesta a Kafka y HDFS (datos crudos para auditoría).

### Procesadores

| Orden | Procesador | Propósito |
|-------|------------|-----------|
| 1 | **GenerateFlowFile** (o **Schedule** en cron) | Genera un flowfile cada X segundos (p. ej. 300) para disparar la petición. |
| 2 | **InvokeHTTP** | Método GET. URL ejemplo OpenWeather: `https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${OPENWEATHER_API_KEY}&units=metric`. Añadir atributo con timestamp si quieres. |
| 3 | **PublishKafkaRecord** / **PublishKafka** | Kafka Brokers: `192.168.99.10:9092`, Topic: `raw-data` (o un tema distinto, p. ej. `http-weather`). Value = cuerpo de la respuesta. |
| 4 | **PutHDFS** | Directory: `/user/hadoop/proyecto/raw` (o subcarpeta `weather`). Nombre de archivo: puede usar `${filename}` o `${now():format('yyyy-MM-dd-HH-mm')}.json`. |

**API Key**: Crear variable en NiFi (Variable Registry o Parameter Context) `OPENWEATHER_API_KEY` con tu clave de [OpenWeather](https://openweathermap.org/api), y usarla en la URL de InvokeHTTP.

**Conexiones**: GenerateFlowFile → InvokeHTTP → success → PublishKafka; InvokeHTTP success → PutHDFS.

---

## 3. Resumen de destinos (según el PDF)

- **Kafka tema "Datos Crudos"**: `raw-data` (GPS + HTTP pueden ir al mismo tema o a temas distintos).
- **HDFS auditoría**: `/user/hadoop/proyecto/raw/` (mismo directorio o subcarpetas `gps/`, `weather/` si quieres separar).
- Opcional: un segundo flujo o rama que filtre/transforme y publique en tema **"Datos Filtrados"**: `filtered-data`.

---

## 4. Comprobar que la ingesta funciona

1. **Kafka**: Listar mensajes del tema `raw-data`:
   ```bash
   $KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic raw-data --from-beginning --max-messages 5
   ```

2. **HDFS**: Ver archivos en raw:
   ```bash
   hdfs dfs -ls /user/hadoop/proyecto/raw
   hdfs dfs -cat /user/hadoop/proyecto/raw/$(hdfs dfs -ls /user/hadoop/proyecto/raw | tail -1 | awk '{print $NF}') | head -5
   ```

3. **NiFi**: En la UI, revisar que los procesadores no marquen error y que las colas no se acumulen (back-pressure correcto).
