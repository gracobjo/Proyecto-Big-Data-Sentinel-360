# Cómo seguir con el grupo de procesadores en NiFi

Una vez has **importado** el flujo (GPS y/o HTTP), haz esto **dentro del process group** en la UI.

---

## 1. Entrar en el grupo

- **Doble clic** en el process group (cuadro que contiene GetFile, PublishKafka, etc.) para abrirlo y ver los procesadores por dentro.

---

## 2. Configurar el grupo (engranaje)

1. Arriba a la derecha del grupo, clic en el **icono de engranaje** (Configure the process group).
2. **Controller Services**  
   - Pestaña **Controller Services**.  
   - Busca **Kafka3ConnectionService** (o el servicio de Kafka que use el flujo).  
   - Clic en el **rayo** (Enable).  
   - Si pide validar, **Validate** y luego **Enable**.  
   - Cierra con **Apply** o **Close**.
3. **Parameters** (solo si es el flujo HTTP)  
   - En la misma ventana de configuración del grupo, pestaña **Parameters** (o **Parameter Context**).  
   - Asigna o crea el **Parameter Context** “HTTP Weather Params”.  
   - Añade el parámetro **`openweather_api_key`** (sensitive) con tu API key de OpenWeather.  
   - Guarda.

---

## 3. Revisar procesadores (opcional)

- **GetFile (flujo GPS)**  
  - Doble clic en **GetFile GPS Logs** → **Properties** → **Input Directory** = `/home/hadoop/data/gps_logs` (o la ruta donde tengas los JSON/CSV). Aceptar.
- **InvokeHTTP (flujo HTTP)**  
  - Doble clic en **InvokeHTTP** → **Properties** → **URL** debe llevar `${openweather_api_key}`. Si usas Parameter Context, ya tomará el valor. Aceptar.

---

## 4. Arrancar el grupo

1. **Sal** del interior del grupo** (clic en la flecha “atrás” o en el nombre del flujo arriba) para ver de nuevo el **cuadro del process group** en el canvas.
2. **Selecciona el grupo** (un solo clic en el cuadro del grupo).
3. Clic derecho → **Start**, o usa el botón **Start** (▶) de la barra de herramientas.
4. Los procesadores deberían pasar a **Running** (verde). Si alguno sigue en amarillo/rojo, abre ese procesador y revisa el error en la pestaña **Settings** o en el bulletin (icono de bocadillo).

---

## 5. Comprobar que fluyen datos

- **Conexiones**: en las líneas entre procesadores deberían aparecer números (flowfiles en cola).
- **Kafka** (en terminal):
  ```bash
  ~/software/kafka_2.13-4.1.1/bin/kafka-console-consumer.sh --bootstrap-server 192.168.99.10:9092 --topic filtered-data --from-beginning --max-messages 5
  ```
  Para el flujo HTTP, usa el tema **`raw-data`**.

---

## Si quieres completar Fase I (raw + HDFS)

- **Añadir envío a “Datos Crudos” (raw-data)**  
  En el flujo GPS: duplicar el **PublishKafka** (o añadir uno nuevo), Topic = **`raw-data`**, y conectar **GetFile (success)** a ese PublishKafka.
- **Añadir copia en HDFS**  
  Añadir procesador **PutHDFS** → Directory = **`/user/hadoop/proyecto/raw`** → configurar un Controller Service de tipo **HDFS** con NameNode **`hdfs://192.168.99.10:9000`** → conectar **GetFile (success)** (o InvokeHTTP success en el flujo HTTP) a **PutHDFS**.

Detalle completo: **FASE_I_INGESTA.md** y **FLUJO_HTTP_OPENWEATHER.md**.
