# Resolver errores del flujo GPS en NiFi

Tras importar `gps_transport_flow_importable.json`, corrige estos puntos en la UI.

---

## 1. UpdateAttribute: "not a valid Processor type"

**Causa:** El bundle estaba mal (nifi-standard-nar). **Corregido** en el JSON → bundle `nifi-update-attribute-nar`.

**Acción:** Borra el grupo actual e importa de nuevo el JSON actualizado desde `ingest/gps_transport_flow_importable.json`.

---

## 2. Kafka Connection Service deshabilitado

**Síntoma:** PublishKafka con aviso (icono naranja).

**Acción:**
1. Clic derecho en el **Process Group** → **Configure** (o icono de engranaje).
2. Pestaña **Controller Services**.
3. Localiza **Kafka3ConnectionService** → clic en el icono de **rayo** (Enable).
4. Confirma **Enable**.

---

## 3. GetFile: directorio no existe

**Síntoma:** GetFile GPS Logs con aviso.

**Acción:** Crea el directorio y copia datos de prueba:
```bash
mkdir -p /home/hadoop/data/gps_logs
cp ~/Documentos/ProyectoBigData/data/sample/gps_events.json /home/hadoop/data/gps_logs/
```

O cambia en NiFi el **Input Directory** del GetFile a una ruta que exista (p. ej. `~/Documentos/ProyectoBigData/data/sample`).

---

## 4. PutHDFS

### 4a. "'Conflict Resolution' is not a supported property"

**Síntoma:** Error: `'Conflict Resolution' validated against 'replace' is invalid...`

**Causa:** En NiFi 2.7 la propiedad se llama **Conflict Resolution Strategy**, no "Conflict Resolution".

**Acción:** Si el JSON importado da ese error, reimporta desde `gps_transport_flow_importable.json` (ya corregido). En la UI, usa la propiedad **Conflict Resolution Strategy** = `replace` (o `ignore`/`fail`).

### 4b. Ruta de Hadoop

**Síntoma:** PutHDFS con aviso de conexión o ruta.

**Acción:** En la configuración de PutHDFS:
- **Hadoop Configuration Resources:** ruta a `core-site.xml` (p. ej. `/usr/local/hadoop/etc/hadoop/core-site.xml`).
- Si Hadoop está en otra ubicación, usa la ruta correcta.

---

## 5. EvaluateJsonPath: "'Return Type' validated against 'auto' is invalid"

**Síntoma:** Error: `Given value not found in allowed set 'auto-detect, json, scalar'`.

**Causa:** En NiFi 2.7 el valor correcto es **auto-detect**, no "auto".

**Acción:** Reimporta desde `gps_transport_flow_importable.json` (ya corregido). En la UI: **Return Type** = `auto-detect` (o `json`/`scalar` según necesites).

---

## 6. RouteOnAttribute: ruta "filtered"

Si aparece aviso, revisa:
- **Routing Strategy:** `Route to Property name`
- Propiedad definida por usuario: nombre `filtered`, valor `${speed:lt(120)}`

---

## Orden recomendado

1. Borrar el Process Group con errores.
2. Importar de nuevo `ingest/gps_transport_flow_importable.json`.
3. Habilitar **Kafka3ConnectionService**.
4. Crear `/home/hadoop/data/gps_logs` y copiar `gps_events.json`.
5. Comprobar la ruta de Hadoop en PutHDFS.
6. Iniciar los procesadores (icono Play en el grupo).
