# Sentinel360 – Comprobar que la ingesta en NiFi funciona

## Antes de arrancar

1. **InvokeHTTP** debe recibir flowfiles para hacer la petición. Si no tienes **GenerateFlowFile** delante:
   - Añade **GenerateFlowFile** (Schedule: p. ej. `30 sec` o `5 min`, Batch Size: 1).
   - Conecta **GenerateFlowFile (success)** → **InvokeHTTP**.
2. **Controller Service de Kafka**: en el grupo (Configure → Controller Services) el **Kafka3ConnectionService** debe estar **Enabled**.
3. **Parameter Context**: el grupo debe tener el parámetro **openweather_api_key** con tu API key (para InvokeHTTP).
4. **GetFile**: Input Directory = `/home/hadoop/data/gps_logs` (o donde estén los archivos). Si está vacío, ejecuta antes:  
   `./scripts/preparar_ingesta_nifi.sh`

---

## Arrancar

1. Sal del interior del grupo (ver el cuadro del process group en el canvas).
2. Selecciona el **process group** (un clic).
3. Clic derecho → **Start** (o botón ▶).
4. Espera unos segundos. Los procesadores deberían pasar a **Running** (verde).

---

## Comprobar HTTP (tema raw-data)

En una terminal:

```bash
~/software/kafka_2.13-4.1.1/bin/kafka-console-consumer.sh \
  --bootstrap-server 192.168.99.10:9092 \
  --topic raw-data \
  --from-beginning \
  --max-messages 3
```

Deberías ver mensajes JSON de OpenWeather (si InvokeHTTP está conectado a un PublishKafka con topic `raw-data` y GenerateFlowFile está generando flowfiles).

---

## Comprobar GPS (tema filtered-data)

```bash
~/software/kafka_2.13-4.1.1/bin/kafka-console-consumer.sh \
  --bootstrap-server 192.168.99.10:9092 \
  --topic filtered-data \
  --from-beginning \
  --max-messages 5
```

Deberías ver líneas de los archivos GPS (JSON o CSV) que leyó GetFile.

---

## En la UI de NiFi

- **Conexiones**: en las líneas entre procesadores deberían aparecer números (flowfiles en cola o procesados).
- **Procesadores**: sin icono de error; si hay aviso, clic en el procesador y revisar la pestaña **Bulletin** o el mensaje de validación.
- **Provenance**: clic derecho en un procesador → **View data provenance** para ver flowfiles que pasaron por él.

---

## Si no llega nada

- **InvokeHTTP**: ¿hay **GenerateFlowFile** conectado a él y en ejecución? ¿El Parameter Context tiene `openweather_api_key`?
- **GetFile**: ¿existen archivos en el directorio configurado? (`ls /home/hadoop/data/gps_logs`)
- **PublishKafka**: ¿el Controller Service de Kafka está habilitado? ¿El tema existe? (`kafka-topics.sh --list --bootstrap-server 192.168.99.10:9092`)
