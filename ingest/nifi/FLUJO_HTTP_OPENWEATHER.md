# Flujo NiFi: HTTP / OpenWeather (API pública) – Fase I

Consumir datos de una API pública (OpenWeather) y publicar en Kafka (tema **raw-data**) y opcionalmente en HDFS (copia raw).

---

## Requisitos

- **API Key OpenWeather**: regístrate en [openweathermap.org](https://openweathermap.org/api) y obtén una API key (gratis).
- Temas Kafka **raw-data** y **filtered-data** creados (`./scripts/preparar_ingesta_nifi.sh` ya los crea).
- NiFi con acceso a Kafka (192.168.99.10:9092) y, si usas PutHDFS, a HDFS (192.168.99.10:9000).

---

## Opción A: Importar el flujo JSON (recomendado)

1. En NiFi: **Upload flow** / **Import from file**.
2. Selecciona: **`ingest/http_weather_flow_importable.json`**.
3. Abre el process group importado → **Configure** → **Controller Services** → habilita **Kafka3ConnectionService**.
4. **Parameter context**: asigna el contexto "HTTP Weather Params" al grupo (o crea uno) con:
   - `openweather_api_key` = tu API key (marcar como sensitive si quieres).
   - Opcional: `openweather_url` = `https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${openweather_api_key}&units=metric`
5. En el procesador **InvokeHTTP**, en **URL** usa:  
   `https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${openweather_api_key}&units=metric`
6. **Añadir PutHDFS** (copia raw en HDFS):
   - Añadir procesador **PutHDFS**.
   - Directory: `/user/hadoop/proyecto/raw` (o `/user/hadoop/proyecto/raw/weather`).
   - Crear **HDFS Connection** (Controller Service) con NameNode `hdfs://192.168.99.10:9000` si no existe.
   - Conectar **InvokeHTTP (success)** → **PutHDFS**.
7. **Start** del process group.

---

## Opción B: Crear el flujo a mano en la UI

### 1. Process Group

- Clic derecho en el canvas → **Add** → **Process group** → nombre: "HTTP OpenWeather".

### 2. Procesadores

| Procesador        | Tipo            | Configuración |
|-------------------|-----------------|------------------------------------------------------------------|
| **GenerateFlowFile** | GenerateFlowFile | **Schedule**: 5 min (300 sec). **Batch Size**: 1. **File Size**: 0. **Custom Text**: (vacío). |
| **InvokeHTTP**    | InvokeHTTP      | **HTTP Method**: GET. **URL**: `https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${openweather_api_key}&units=metric`. **Content-type**: (vacío). Añadir **Parameter Context** al grupo con parámetro `openweather_api_key` (sensitive). |
| **PublishKafka**  | PublishKafka    | **Kafka Connection Service**: crear/enlazar Kafka3 con bootstrap `192.168.99.10:9092`. **Topic Name**: `raw-data`. **Publish Strategy**: USE_VALUE (cuerpo del flowfile = valor del mensaje). |
| **PutHDFS**       | PutHDFS         | **Directory**: `/user/hadoop/proyecto/raw`. **Hadoop Configuration** o **HDFS Connection** con NameNode `hdfs://192.168.99.10:9000`. **Conflict Resolution**: replace. |

### 3. Conexiones

- **GenerateFlowFile (success)** → **InvokeHTTP**.
- **InvokeHTTP (success)** → **PublishKafka**.
- **InvokeHTTP (success)** → **PutHDFS**.

### 4. Parameter Context (API key)

- En el process group: **Configure** → **Parameters** (o Parameter Context).
- Crear parámetro **openweather_api_key** (sensitive) con tu API key.
- En InvokeHTTP, URL debe usar `${openweather_api_key}`.

### 5. Arrancar

- **Start** del process group.

---

## Comprobar

- **Kafka (raw-data)**:
  ```bash
  $KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic raw-data --from-beginning --max-messages 2
  ```
- **HDFS** (si añadiste PutHDFS):
  ```bash
  hdfs dfs -ls /user/hadoop/proyecto/raw
  hdfs dfs -cat /user/hadoop/proyecto/raw/weather/*.json | head -1
  ```

---

## Resumen Fase I

| Requisito              | GPS flow              | HTTP flow     |
|------------------------|------------------------|---------------|
| Fuente externa         | ✅ Logs simulados GPS  | ✅ API OpenWeather |
| Kafka Datos Crudos     | ✅ raw-data            | ✅ raw-data   |
| Kafka Datos Filtrados  | ✅ filtered-data      | —             |
| Copia raw HDFS         | ✅ PutHDFS             | ✅ PutHDFS    |

Ver **FASE_I_INGESTA.md** para el checklist completo.
