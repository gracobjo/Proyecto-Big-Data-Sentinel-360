# Pasos: ingesta en NiFi (Fase I – GPS + HTTP)

**Fase I** exige: (1) API pública + logs GPS, (2) temas Kafka **raw-data** y **filtered-data**, (3) copia raw en HDFS.  
Flujo GPS: `ingest/gps_transport_flow_importable.json`. Flujo HTTP: `ingest/http_weather_flow_importable.json`.  
Ver **FASE_I_INGESTA.md** y **FLUJO_HTTP_OPENWEATHER.md** para el flujo HTTP y PutHDFS.

Sigue estos pasos en orden. Antes, ejecuta el script de preparación desde la raíz de Sentinel360:

```bash
cd ~/Documentos/ProyectoBigData   # ruta local del proyecto Sentinel360
chmod +x scripts/preparar_ingesta_nifi.sh
./scripts/preparar_ingesta_nifi.sh
```

---

## 1. Abrir la UI de NiFi

- URL: **https://localhost:8443/nifi**
- Acepta el aviso del certificado si el navegador lo muestra.

---

## 2. Importar el flujo GPS

1. En el canvas, haz clic en el **icono “+”** (añadir proceso) o en el menú superior **Operate** / **Flow**.
2. Busca la opción **“Import flow”** o **“Upload flow”** (según versión: puede estar en el menú de la esquina o en el desplegable del grupo raíz).
3. En NiFi 2.x: **Components** (panel izquierdo) → **Upload** / **Import** → **Import from file**.
4. Selecciona el archivo:  
   **`<ruta-Sentinel360>/ingest/gps_transport_flow_importable.json`** (p. ej. `~/Documentos/ProyectoBigData/ingest/...`)
5. Confirma la importación. Debería aparecer un **process group** (p. ej. “gps_transport_flow_importable”) con dos procesadores: **GetFile GPS Logs** y **PublishKafka**.

---

## 3. Habilitar el Controller Service de Kafka

1. Entra en el **process group** importado (doble clic o selección).
2. Clic en el **icono de engranaje** (Configure) del grupo, o clic derecho sobre el grupo → **Configure**.
3. Pestaña **Controller Services**.
4. Localiza **Kafka3ConnectionService** (estado *Disabled*).
5. Clic en el **icono de rayo** (Enable) para habilitarlo. Si pide validar, valida y confirma.
6. Cierra la ventana de configuración.

---

## 4. Comprobar / ajustar el directorio de entrada (GetFile)

1. Doble clic en el procesador **GetFile GPS Logs**.
2. En **Properties**, revisa **Input Directory**:
   - Por defecto: **`/home/hadoop/data/gps_logs`** (el script `preparar_ingesta_nifi.sh` ya ha copiado ahí los datos de prueba).
   - Si quieres usar la carpeta de datos de Sentinel360: **`<ruta-Sentinel360>/data/sample`** (p. ej. `/home/hadoop/Documentos/ProyectoBigData/data/sample`).
3. **File Filter** debe ser `.*\.(jsonl?|csv)` (ya viene en el flujo).
4. Acepta (Apply / OK).

---

## 5. Arrancar el flujo

1. En el process group, selecciona el **grupo** (no un procesador suelto).
2. Clic derecho → **Start**, o botón **Start** en la barra de acciones.
3. Los procesadores deberían pasar a estado **Running** (verde). Si alguno queda en **Invalid** o **Stopped**, abre su configuración y revisa errores (p. ej. Controller Service no habilitado, directorio inexistente o Kafka inaccesible).

---

## 6. Comprobar que llegan datos

**En Kafka (tema filtered-data):**

```bash
$KAFKA_HOME/bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic filtered-data --from-beginning --max-messages 5
```

Deberías ver líneas JSON o CSV según el archivo que haya leído GetFile.

**En NiFi:** en cada procesador, **View data provenance** o **List queue** en las conexiones para ver flowfiles procesados.

---

## Resumen rápido

| Paso | Acción |
|------|--------|
| 1 | Ejecutar `./scripts/preparar_ingesta_nifi.sh` |
| 2 | Abrir https://localhost:8443/nifi |
| 3 | Import flow → `ingest/gps_transport_flow_importable.json` |
| 4 | Controller Services → habilitar Kafka3ConnectionService |
| 5 | GetFile: comprobar Input Directory (`/home/hadoop/data/gps_logs` o `.../data/sample`) |
| 6 | Start del process group |

Si quieres además **copia en HDFS** (auditoría raw), añade un procesador **PutHDFS** y conecta la relación *success* de GetFile a PutHDFS; Directory = `/user/hadoop/proyecto/raw`. Ver `ingest/nifi/README.md` para detalles de PutHDFS.
