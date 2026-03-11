# Flujo NiFi: GPS Transport (`gps_transport_flow_importable.json`)

## Procesadores: qué hace cada uno

| Procesador | Función | Entrada | Salida | Notas |
|------------|---------|---------|--------|-------|
| **GetFile GPS Logs** | Lee archivos JSON/JSONL/CSV del directorio local. Polling cada 5 s. | Directorio `/home/hadoop/data/gps_logs` | FlowFile por archivo (success) | Filtro: `.*\.(jsonl?|csv)`. Elimina archivo tras leerlo (Keep Source File=false). |
| **UpdateAttribute** | Añade atributo `source.type=gps` al FlowFile. | success de GetFile | success | Marca el origen para trazabilidad en fases posteriores. |
| **PutHDFS** | Copia el contenido raw del FlowFile en HDFS. | success de GetFile (rama directa) | success/failure | Ruta: `/user/hadoop/proyecto/raw`. Auditoría de datos crudos. |
| **SplitText** | Parte el contenido en líneas (1 línea = 1 FlowFile). | success de UpdateAttribute | splits | Cada línea JSONL se convierte en un FlowFile independiente. |
| **EvaluateJsonPath** | Extrae campos JSON a atributos: `vehicle_id`, `speed`, `warehouse_id`. | splits de SplitText | matched / unmatched | Return Type: `auto-detect`. Los que no coinciden → unmatched. |
| **RouteOnAttribute** | Enruta según condición: `speed < 120`. | matched de EvaluateJsonPath | filtered / unmatched | filtered = eventos “normales”; unmatched = resto (velocidad alta). |
| **PublishKafka raw-data** | Publica en Kafka topic `raw-data`. | unmatched de EvaluateJsonPath + unmatched de RouteOnAttribute | success/failure | Todos los eventos procesables van a raw-data. |
| **PublishKafka filtered-data** | Publica en Kafka topic `filtered-data`. | filtered de RouteOnAttribute | success/failure | Solo eventos con `speed < 120`. |

## Qué hemos conseguido con este flujo

1. **Copia raw en HDFS** (PutHDFS): respaldo de los datos crudos para auditoría y reprocesado.
2. **Streaming en Kafka** en dos temas:
   - `raw-data`: todos los eventos (base para Spark streaming, Hive, etc.).
   - `filtered-data`: solo eventos con velocidad &lt; 120 km/h (calidad/seguridad).
3. **Detección de valores altos**: velocidades ≥ 120 van a raw-data pero no a filtered-data.
4. **Fase I KDD**: ingesta, selección y clasificación básica (Selección en KDD).

---

## Comprobación del JSON

El archivo **`gps_transport_flow_importable.json`** es un flujo NiFi 2.7 válido que cumple Fase I según ESQUEMA_PROCESADORES_REVISION. Procesadores (resumen):

- **GetFile GPS Logs**: lee archivos del directorio local. Filtro: `.*\.(jsonl?|csv)`.
- **UpdateAttribute**: marca `source.type=gps`.
- **PutHDFS**: copia raw en HDFS (`/user/hadoop/proyecto/raw`). Rama directa desde GetFile.
- **SplitText**: divide JSONL en líneas (1 por flow file).
- **EvaluateJsonPath**: extrae `vehicle_id`, `speed`, `warehouse_id` a atributos.
- **RouteOnAttribute**: filtro `speed < 120` → **filtered** (filtered-data) | **unmatched** (raw-data).
- **PublishKafka raw-data**: todos los eventos (filtered + unmatched).
- **PublishKafka filtered-data**: solo eventos con speed < 120.

Ajustes aplicados al JSON de Sentinel360:

- `bootstrap.servers` y parámetro `kafka_brokers`: **192.168.99.10:9092** (en lugar de 127.0.0.1).
- Filtro de GetFile ampliado para incluir **CSV** (Sentinel360 genera `gps_events.csv` y `gps_events.json`).

---

## Fase I: ya incluido en el flujo

El flujo cumple Fase I: GetFile → PutHDFS (copia raw), PublishKafka (raw-data) y PublishKafka (filtered-data). Si PutHDFS falla al importar (p. ej. bundle Hadoop no instalado), añadirlo manualmente en la UI con Directory `/user/hadoop/proyecto/raw` y Hadoop Configuration Resources.

---

## Después de importar en NiFi

1. **Habilitar el Controller Service**  
   El *Kafka3ConnectionService* puede quedar en estado *Disabled*. En NiFi: Configuration → Controller Services → habilitar *Kafka3ConnectionService*.

2. **Directorio de entrada**  
   GetFile usa por defecto **`/home/hadoop/data/gps_logs`**. Opciones:
   - Copiar o enlazar los datos de Sentinel360 ahí:
     ```bash
     mkdir -p /home/hadoop/data/gps_logs
     python data/sample/generate_gps_logs.py
     cp /home/hadoop/Documentos/ProyectoBigData/data/sample/gps_events.* /home/hadoop/data/gps_logs/   # ruta Sentinel360
     ```
   - O en NiFi, editar GetFile y poner **Input Directory** = ruta a `data/sample` de Sentinel360 (p. ej. `/home/hadoop/Documentos/ProyectoBigData/data/sample`).

3. **Temas Kafka**  
   El flujo publica en **`raw-data`** y **`filtered-data`**.

4. **PutHDFS**  
   Si la ruta de Hadoop difiere, editar PutHDFS → **Hadoop Configuration Resources** = ruta a tu `core-site.xml` (p. ej. `/usr/local/hadoop/etc/hadoop/core-site.xml`).

---

## Resumen

| Aspecto              | Estado |
|----------------------|--------|
| JSON válido          | Sí     |
| Kafka broker clúster | 192.168.99.10:9092 |
| Soporte CSV + JSON   | Sí (filtro actualizado) |
| Directorio GetFile   | `/home/hadoop/data/gps_logs` (cambiable en NiFi) |
| Temas Kafka          | `raw-data`, `filtered-data` |
| HDFS raw (PutHDFS)   | `/user/hadoop/proyecto/raw` (incluido en el flujo) |

---

## Comprobación de datos (verificación end-to-end)

### 1. Kafka (datos directos del flujo NiFi)

```bash
# Desde el directorio de Kafka (p. ej. ~/software/kafka_2.13-4.1.1)
./bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic raw-data --from-beginning --max-messages 5 --timeout-ms 5000

./bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic filtered-data --from-beginning --max-messages 5 --timeout-ms 5000
```

### 2. HDFS (PutHDFS escribe aquí)

```bash
hdfs dfs -ls /user/hadoop/proyecto/raw

# Mostrar primeras líneas del último archivo subido
hdfs dfs -cat "$(hdfs dfs -ls /user/hadoop/proyecto/raw | tail -1 | awk '{print $NF}')" | head -20
```

### 3. MongoDB (no viene directamente de NiFi)

MongoDB recibe datos del **job Spark streaming** `delays_windowed.py`, que consume Kafka (`raw-data`) y escribe en Hive y MongoDB (`transport.aggregated_delays`). NiFi no escribe en MongoDB.

**Requisito previo**: ejecutar `delays_windowed.py` para que se escriban agregados en Hive y MongoDB.

```bash
# Comprobar si hay documentos (tras ejecutar delays_windowed.py)
mongosh --eval "db.getSiblingDB('transport').aggregated_delays.find().limit(5)"

# O si mongosh no está en PATH:
mongo --eval "db.getSiblingDB('transport').aggregated_delays.find().limit(5)"
```

**Orden de verificación recomendado**: Kafka → HDFS → (opcional) Spark streaming → Hive y MongoDB.

**Script de ayuda**:
```bash
./scripts/verificar_ingesta_gps.sh
```
