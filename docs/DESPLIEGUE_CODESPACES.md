# Despliegue de Sentinel360 en GitHub Codespaces

## ¿Se puede desplegar Sentinel360 en Codespaces?

**Sí, de forma limitada:** la **aplicación de presentación (Streamlit)** puede ejecutarse en GitHub Codespaces en **modo demo**. El **stack completo** (clúster de 3 nodos con HDFS, YARN, Kafka, NiFi, Hive, Airflow, etc.) **no** puede desplegarse dentro de Codespaces.

### Resumen

| Componente | ¿En Codespaces? | Notas |
|------------|------------------|--------|
| **App Streamlit** (`web/presentacion_sentinel360_app.py`) | ✅ Sí | Modo demo: datos de muestra, incidencias/decisiones en memoria (sin MongoDB) o con MongoDB opcional en contenedor |
| **HDFS / YARN / Kafka / NiFi / Hive** | ❌ No | Requieren un clúster multi-nodo (IPs 192.168.99.x); Codespaces es un único entorno de desarrollo |
| **Spark (jobs batch/streaming)** | ❌ No | Diseñados para ejecutarse en YARN en el master |
| **Airflow** | ❌ No | Pensado para el master del clúster; en Codespaces podrías correr solo Airflow local, sin los servicios que orquesta |
| **MongoDB / MariaDB** | ⚠️ Opcional | Puedes añadir MongoDB (y/o MariaDB) como **servicio** en el devcontainer para persistencia; si no, la app usa `session_state` (demo) |

---

## Modo demo en Codespaces

La app Streamlit ya está preparada para funcionar **sin** clúster:

- **Datos:** usa ficheros de ejemplo en `data/sample/` (`gps_events.csv`, `warehouses.csv`, `routes.csv`).
- **MongoDB:** si no hay conexión a MongoDB, la app usa un store en memoria (`st.session_state`) para incidencias y decisiones; no hace falta tener Mongo corriendo.
- **MariaDB/Superset/Grafana:** no son necesarios para la interfaz de presentación; solo se usan en el entorno “completo” para dashboards externos.

Por tanto, en Codespaces puedes:

1. Abrir el repositorio en un Codespace (con el `.devcontainer` incluido en el repo).
2. Instalar dependencias (Python, Streamlit, pandas, pymongo, folium, streamlit-folium) y ejecutar la app.
3. Abrir el puerto **8501** (Streamlit) desde la pestaña “Ports” y usar la aplicación en modo demo.

---

## Cómo usar el devcontainer en Codespaces

1. En GitHub: **Code → Codespaces → Create codespace on main** (o en la rama que uses).
2. El devcontainer (`.devcontainer/devcontainer.json`) instalará las dependencias al crear el entorno (Streamlit, pandas, pymongo, folium, streamlit-folium).
3. En la terminal del Codespace, desde la raíz del repo:

   ```bash
   cd web && streamlit run presentacion_sentinel360_app.py --server.address=0.0.0.0
   ```

4. En la pestaña **Ports**, marca el puerto **8501** como “Public” si quieres abrirlo por URL, y abre el enlace que te muestre Codespaces (por ejemplo `https://...-8501.app.github.dev`).

Si añadiste el **servicio MongoDB** en el devcontainer y configuraste `MONGO_URI=mongodb://mongo:27017`, la app usará MongoDB para incidencias y decisiones; si no, seguirá en modo demo con datos en memoria.

---

## Limitaciones en Codespaces

- **Recursos:** Codespaces tiene límites de CPU/memoria según el tipo de máquina; suficiente para Streamlit y datos de muestra, no para un clúster real.
- **Red:** La configuración de `config.py` (IPs 192.168.99.x) está pensada para una red local/VMs; en Codespaces esas IPs no existen. La app de presentación no depende de ellas para el modo demo.
- **Jobs Spark / Airflow / NiFi:** Para desarrollarlos o probarlos, sigue usando tu entorno local o un clúster aparte; Codespaces sirve sobre todo para la **interfaz de presentación** y para explorar el código.

---

## Referencias

- [Forwarding ports in your codespace](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace)
- Configuración del proyecto: `config.py`, `README.md`, `docs/GUIA_ARRANQUE_AIRFLOW.md`
