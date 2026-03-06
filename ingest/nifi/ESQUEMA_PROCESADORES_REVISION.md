sube # Revisión del esquema de procesadores NiFi – Sentinel360

Este documento valida el **esquema de grupos de procesadores** que propones y lo completa para cumplir Fase I (datos crudos, filtrados, copia raw en HDFS) y para dejar claro cuándo usar cada patrón.

---

## 1. Esquema que propones

### Flujo A – GPS / eventos generados

```
GenerateFlowFile → UpdateAttribute → ReplaceText → EvaluateJsonPath → PublishKafka
```

### Flujo B – HTTP (eventos entrantes)

```
HandleHttpRequest → EvaluateJsonPath → RouteOnAttribute → PublishKafka → HandleHttpResponse
```

---

## 2. Valoración general

- **Flujo B (HTTP)** está bien encaminado y es **apropiado** para **recibir** eventos por HTTP (dispositivos o gateways que envían POST a NiFi). Sustituye el patrón “NiFi llama a OpenWeather” (InvokeHTTP + GenerateFlowFile) por “algo llama a NiFi”; ambos son válidos según el caso de uso.
- **Flujo A (GPS)** se queda corto en un punto crítico: **falta el origen de los datos**. `GenerateFlowFile` solo crea flow files vacíos (o con texto fijo) en un intervalo; **no lee archivos del disco**. Para ingesta de logs GPS desde carpeta necesitas **GetFile** (o ListFile + FetchFile) al inicio. Además faltan: copia raw en HDFS y, si aplica, bifurcación a `raw-data` y `filtered-data`.

A continuación se detalla cada flujo y se proponen esquemas completos.

---

## 3. Flujo GPS / archivos – Qué falta y cómo completarlo

### Problema con el esquema actual

| Procesador        | Función típica | Observación |
|-------------------|----------------|-------------|
| **GenerateFlowFile** | Crea flow files en un intervalo (cuerpo vacío o Custom Text). | No lee archivos; no sustituye a GetFile para “leer logs GPS de una carpeta”. |
| **UpdateAttribute** | Añade/sobrescribe atributos (ej. `source.type=gps`). | Útil para marcar origen o tema. |
| **ReplaceText** | Sustituye texto en el contenido del flow file. | Útil para normalizar (encoding, separadores). Si los logs son **CSV**, para extraer campos después necesitarías **ConvertRecord** (CSV → JSON) o **SplitRecord**; ReplaceText solo no convierte formato. |
| **EvaluateJsonPath** | Extrae rutas JSON a atributos. | Válido si el **contenido es JSON**. Si es CSV, usar **ConvertRecord** antes o en lugar de EvaluateJsonPath. |
| **PublishKafka** | Publica en un tema. | Falta un segundo PublishKafka (o RouteOnAttribute) para diferenciar **raw-data** y **filtered-data**, y falta **PutHDFS** para la copia raw. |

### Esquema recomendado para GPS (archivos en disco)

Origen real = **GetFile**; después opcionalmente normalización, extracción y enrutado:

```
GetFile (logs GPS)
    |
    v
UpdateAttribute (opcional: source.type=gps, etc.)
    |
    +---> PutHDFS (copia raw: /user/hadoop/proyecto/raw)
    |
    v
[Si CSV] ConvertRecord (CSV → JSON)  OU  [Si ya JSON] nada
    |
    v
EvaluateJsonPath (extraer ej. vehicle_id, lat, lon a atributos)
    |
    v
RouteOnAttribute (opcional: filtrar por atributos, ej. speed < 120)
    |
    +---> matched (filtered)  ---> PublishKafka (filtered-data)
    |
    +---> unmatched (o "all" si no filtras) ---> PublishKafka (raw-data)
```

- **GetFile**: Input Directory = directorio de logs (ej. el que rellena `preparar_ingesta_nifi.sh`). Filtro `.*\.(csv|json|jsonl)`.
- **PutHDFS**: misma salida de GetFile (success) para cumplir “copia raw en HDFS”.
- **PublishKafka**: dos instancias (o una con RouteOnAttribute) para `raw-data` y `filtered-data`.

Si quieres **mantener** GenerateFlowFile en el flujo GPS, tiene sentido solo como **disparador periódico** de algo que no sea “leer archivos” (ej. invocar un script que genere un archivo y luego GetFile lo recoja, o un flujo distinto que genere eventos sintéticos). En ese caso la fuente del contenido seguiría siendo GetFile u otro procesador que aporte contenido.

---

## 4. Flujo HTTP (eventos entrantes) – Valoración y mejoras

### Por qué el esquema es apropiado

- **HandleHttpRequest** + **HandleHttpResponse**: patrón correcto para **ingesta por HTTP** (NiFi expone un endpoint; dispositivos o aplicaciones envían POST con el cuerpo del evento). Es el patrón “event-driven” frente a “NiFi hace polling” (InvokeHTTP + GenerateFlowFile).
- **EvaluateJsonPath**: adecuado para extraer campos del JSON del cuerpo y ponerlos en atributos para enrutar o validar.
- **RouteOnAttribute**: permite enviar a temas distintos (ej. por tipo de evento o por resultado de validación) o a manejo de error.
- **PublishKafka** antes de **HandleHttpResponse**: correcto si quieres responder 200 solo tras publicar en Kafka (conectar success de PublishKafka a HandleHttpResponse).

### Qué añadir para no quedarse corto

| Añadido | Motivo |
|--------|--------|
| **PutHDFS** | Cumplir Fase I: copia raw en HDFS (ej. `/user/hadoop/proyecto/raw` o subcarpeta `http_events/`). Conectar la salida success de HandleHttpRequest (o la rama que va a Kafka) también a PutHDFS. |
| **ValidateRecord** (opcional) | Validar el JSON antes de RouteOnAttribute; enviar a HandleHttpResponse con 400 si no es válido. |
| **Manejo de relaciones** | RouteOnAttribute: rama “matched”/success → PublishKafka → HandleHttpResponse (200); rama “unmatched”/failure → HandleHttpResponse (400 o 500) con mensaje de error. |

### Esquema recomendado para HTTP (eventos entrantes)

```
HandleHttpRequest
    |
    v
EvaluateJsonPath (extraer tipo, id, etc. a atributos)
    |
    +---> PutHDFS (copia raw; mismo flow file)
    |
    v
RouteOnAttribute (ej. por event.type o por validación)
    |
    +---> matched  --> PublishKafka (raw-data o topic específico)
    |                      |
    |                      v
    |                 HandleHttpResponse (200, cuerpo opcional)
    |
    +---> unmatched --> HandleHttpResponse (400/422, mensaje error)
```

- **HandleHttpResponse**: en NiFi 2.x suele configurarse con código de estado (200 / 400) y opcionalmente cuerpo; la relación que llega a HandleHttpResponse determina qué respuesta se envía (p. ej. una relación para éxito y otra para error).

---

## 5. Resumen: dos patrones HTTP

Para no mezclar conceptos en la documentación:

| Patrón | Procesadores | Uso en Sentinel360 |
|--------|--------------|--------------------|
| **NiFi llama a API externa** (polling) | GenerateFlowFile → **InvokeHTTP** → PublishKafka / PutHDFS | OpenWeather u otras APIs que se consultan cada X minutos. |
| **API/dispositivos llaman a NiFi** (event-driven) | **HandleHttpRequest** → EvaluateJsonPath → RouteOnAttribute → PublishKafka → **HandleHttpResponse** (+ PutHDFS) | Recepción de eventos por POST (gateways, apps, sensores). |

Tu esquema HTTP corresponde al segundo. El flujo OpenWeather actual (InvokeHTTP + GenerateFlowFile) sigue siendo válido para “consultar clima cada X minutos”; el flujo con HandleHttpRequest es para “recibir eventos que alguien nos envía por HTTP”.

---

## 6. Checklist Fase I con los esquemas propuestos

| Requisito | Flujo GPS (completado) | Flujo HTTP (propuesto) |
|-----------|------------------------|-------------------------|
| Fuente externa | GetFile (logs) | HandleHttpRequest (POST entrante) |
| Kafka raw-data | ✅ PublishKafka (raw-data) | ✅ PublishKafka (raw-data o topic dedicado) |
| Kafka filtered-data | ✅ PublishKafka (filtered-data) tras RouteOnAttribute | Opcional (RouteOnAttribute por tipo) |
| Copia raw HDFS | ✅ PutHDFS | ✅ PutHDFS (misma rama que Kafka) |
| Normalización / validación | UpdateAttribute, ConvertRecord si CSV, EvaluateJsonPath, RouteOnAttribute | EvaluateJsonPath, RouteOnAttribute, opcional ValidateRecord |
| Respuesta al cliente (solo HTTP) | — | HandleHttpResponse (200/400) |

---

## 7. Qué hacer con el grupo `gps_transport_flow_importable`

Si tu grupo GPS tiene solo **GetFile → PublishKafka (filtered-data)**, para cumplir Fase I hay que **añadir** en NiFi:

1. **PublishKafka** con Topic **`raw-data`**; conectar **GetFile (success)** a él.
2. **PutHDFS** con Directory **`/user/hadoop/proyecto/raw`** y Controller Service HDFS (NameNode `hdfs://192.168.99.10:9000`); conectar **GetFile (success)** a PutHDFS.

Resultado: GetFile (success) → [ PublishKafka (filtered-data) | PublishKafka (raw-data) | PutHDFS ].

Detalle paso a paso y comprobaciones: **[FASE_I_INGESTA.md](FASE_I_INGESTA.md)** → sección «Qué hacer con el grupo gps_transport_flow_importable».

---

## 8. Siguiente paso en la UI de NiFi

1. **Flujo GPS**: Añadir **GetFile** al inicio (o ListFile + FetchFile); **PutHDFS** desde la salida de GetFile; opcional **ConvertRecord** si los logs son CSV; **RouteOnAttribute** + dos **PublishKafka** (raw-data y filtered-data) según el esquema anterior.
2. **Flujo HTTP**: Mantener HandleHttpRequest → EvaluateJsonPath → RouteOnAttribute → PublishKafka → HandleHttpResponse; añadir **PutHDFS** en paralelo (misma fuente que PublishKafka) y, si quieres, **ValidateRecord** antes de RouteOnAttribute.
3. Controller Services: Kafka (PublishKafka) y HDFS (PutHDFS) habilitados; Parameter Context para API keys si usas también InvokeHTTP en otro grupo.

Si quieres, el siguiente paso puede ser bajar esto a un único diagrama ASCII por flujo (con nombres de procesadores y relaciones) y dejarlo en `ingest/nifi/` o en `FASE_I_INGESTA.md` como referencia del “esquema objetivo”.
