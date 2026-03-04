# Flujo NiFi: GPS Transport (`gps_transport_flow_importable.json`)

## Comprobación del JSON

El archivo **`gps_transport_flow_importable.json`** es un flujo NiFi 2.x válido con:

- **GetFile GPS Logs**: lee archivos del directorio local (por defecto `/home/hadoop/data/gps_logs`). Filtro: `.*\.(jsonl?|csv)` (archivos `.json`, `.jsonl` y `.csv`).
- **PublishKafka**: publica el contenido en el tema Kafka **`filtered-data`**. Broker: **192.168.99.10:9092** (clúster).
- **Conexión**: GetFile (success) → PublishKafka.

Ajustes aplicados al JSON de Sentinel360:

- `bootstrap.servers` y parámetro `kafka_brokers`: **192.168.99.10:9092** (en lugar de 127.0.0.1).
- Filtro de GetFile ampliado para incluir **CSV** (Sentinel360 genera `gps_events.csv` y `gps_events.json`).

---

## Fase I: cumplir enunciado (crudo + filtrado + HDFS)

1. **Datos Crudos**: añadir otro **PublishKafka** con Topic = **`raw-data`**; conectar **GetFile (success)** a él.
2. **Copia raw en HDFS**: añadir **PutHDFS**, Directory = **`/user/hadoop/proyecto/raw`**, y Controller Service HDFS (NameNode `hdfs://192.168.99.10:9000`); conectar **GetFile (success)** → **PutHDFS**.

Resultado: GetFile → PublishKafka (raw-data), GetFile → PublishKafka (filtered-data), GetFile → PutHDFS.

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

3. **Tema Kafka**  
   El flujo publica en **`filtered-data`**. Si quieres “datos crudos” en el mismo flujo, puedes duplicar PublishKafka hacia el tema **`raw-data`** o usar un flujo aparte para raw. Según el PDF: tema crudo = `raw-data`, tema filtrado = `filtered-data`.

4. **Copia en HDFS (auditoría)**  
   El enunciado pide “almacenar una copia raw en HDFS”. Este flujo solo envía a Kafka. Para HDFS: añadir un procesador **PutHDFS** (mismo grupo), Directory = `/user/hadoop/proyecto/raw`, y conectar GetFile (success) también a PutHDFS.

---

## Resumen

| Aspecto              | Estado |
|----------------------|--------|
| JSON válido          | Sí     |
| Kafka broker clúster | 192.168.99.10:9092 |
| Soporte CSV + JSON   | Sí (filtro actualizado) |
| Directorio GetFile   | `/home/hadoop/data/gps_logs` (cambiable en NiFi) |
| Tema Kafka           | `filtered-data` |
| HDFS raw             | Añadir PutHDFS en la UI (Directory: /user/hadoop/proyecto/raw) para Fase I |
