# Fase I: Ingesta y Selección (NiFi + Kafka) – Checklist práctica

Según el enunciado:

1. **Fuentes externas**: NiFi debe consumir (a) una **API pública** (OpenWeather o similar) y (b) **archivos logs simulados de GPS**.
2. **Streaming**: Publicar en Kafka diferenciando temas **"Datos Crudos"** (`raw-data`) y **"Datos Filtrados"** (`filtered-data`).
3. **Registro**: Almacenar una **copia "raw" en HDFS** para auditoría (`/user/hadoop/proyecto/raw`).

---

## Resumen de flujos

| Flujo        | Fuente              | Kafka (crudo) | Kafka (filtrado) | HDFS raw |
|-------------|---------------------|---------------|-------------------|----------|
| **GPS**     | GetFile (logs)      | ✅ raw-data   | ✅ filtered-data  | ✅ PutHDFS |
| **HTTP**    | InvokeHTTP (API)    | ✅ raw-data   | —                 | ✅ PutHDFS |

- **Datos crudos**: todo lo que entra (GPS + API) → tema `raw-data` y copia en HDFS.
- **Datos filtrados**: solo el flujo GPS (o un filtro posterior) → tema `filtered-data` (opcional también a HDFS si quieres).

---

## 1. Flujo GPS (ya importable)

- Archivo: **`ingest/gps_transport_flow_importable.json`**.
- Hoy: GetFile → PublishKafka (`filtered-data`).

**Para cumplir Fase I en el flujo GPS:**

1. Añadir **PublishKafka** al tema **`raw-data`**: duplicar el PublishKafka (o añadir otro) y configurar Topic = `raw-data`; conectar **GetFile (success)** a este segundo PublishKafka.
2. Añadir **PutHDFS**: arrastrar **PutHDFS**, Directory = `/user/hadoop/proyecto/raw`. Configurar **HDFS Connection** (Controller Service tipo HDFS con NameNode `hdfs://192.168.99.10:9000`). Conectar **GetFile (success)** → **PutHDFS**.

Queda: GetFile → PublishKafka (raw-data), GetFile → PublishKafka (filtered-data), GetFile → PutHDFS.

---

## 2. Flujo HTTP (API pública, p. ej. OpenWeather)

- Guía detallada: **`ingest/nifi/FLUJO_HTTP_OPENWEATHER.md`**.
- Flujo importable (solo Kafka): **`ingest/http_weather_flow_importable.json`** (luego añades PutHDFS en la UI).

Pasos resumidos:

1. **GenerateFlowFile**: cada X minutos (p. ej. 300 s).
2. **InvokeHTTP**: GET a OpenWeather, URL con parámetro `${openweather_api_key}`.
3. **PublishKafka**: tema **`raw-data`**.
4. **PutHDFS** (añadir en NiFi): misma ruta `/user/hadoop/proyecto/raw`, p. ej. subcarpeta `weather/` o nombre `${now():format('yyyy-MM-dd-HH-mm')}.json`.

---

## 3. HDFS (copia raw)

- Ruta única del proyecto: **`/user/hadoop/proyecto/raw`**.
- En NiFi: procesador **PutHDFS**; hace falta un **Controller Service HDFS** (o equivalente) con:
  - **Hadoop configuration** que apunte a `fs.defaultFS` = `hdfs://192.168.99.10:9000`,  
  - o **Hadoop Configuration Resources** con `core-site.xml` (y si aplica `hdfs-site.xml`) del clúster.

---

## 4. Comprobar

- **Kafka crudo**:  
  `kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic raw-data --from-beginning --max-messages 5`
- **Kafka filtrado**:  
  `kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic filtered-data --from-beginning --max-messages 5`
- **HDFS**:  
  `hdfs dfs -ls /user/hadoop/proyecto/raw`
