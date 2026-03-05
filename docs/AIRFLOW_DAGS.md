## Integración de los DAGs de Sentinel360 en Apache Airflow

Este documento explica **dónde guardar** y **cómo ejecutar** los DAGs de Airflow incluidos en Sentinel360.

---

### 1. DAGs disponibles en el proyecto

En la carpeta `airflow/` del repositorio se incluyen los siguientes DAGs:

- `airflow/dag_sentinel360_batch.py`  
  - Pipeline batch diario: limpieza, enriquecimiento, grafos, carga de agregados, detección de anomalías y carga de KPIs en MariaDB.
- `airflow/dag_sentinel360_streaming_monitoring.py`  
  - Monitorización streaming: job de retrasos en Kafka (`delays_windowed.py`) y consumer de alertas (`alerts_consumer.py`).

---

### 2. Dónde deben guardarse los DAGs en Airflow

Airflow detecta automáticamente los DAGs que se encuentran en el directorio configurado como `dags_folder` (por defecto, `\$AIRFLOW_HOME/dags`).

Tienes dos opciones:

1. **Copiar los DAGs al directorio `dags` de Airflow**
   - En el servidor donde tengas instalado Airflow:
     - Localiza `\$AIRFLOW_HOME` (por ejemplo `~/airflow` o `/opt/airflow`).
     - Copia los ficheros:
       - `dag_sentinel360_batch.py`
       - `dag_sentinel360_streaming_monitoring.py`
     - A la ruta:
       - `\$AIRFLOW_HOME/dags/`

2. **Apuntar `dags_folder` al proyecto**
   - Editar `airflow.cfg` (en `\$AIRFLOW_HOME`) y cambiar:
     - `dags_folder = /ruta/a/tu/proyecto/airflow`
   - De esta forma, Airflow leerá directamente los DAGs desde la carpeta `airflow/` del repositorio (sin necesidad de copiarlos).

> En ambos casos, asegúrate de que las rutas internas (`PROJECT_DIR`) de los DAGs apuntan a la ubicación real del proyecto en el servidor.

---

### 3. Ajustar la ruta del proyecto (`PROJECT_DIR`)

En ambos DAGs (`dag_sentinel360_batch.py` y `dag_sentinel360_streaming_monitoring.py`) existe una constante:

```python
PROJECT_DIR = "/opt/sentinel360"  # AJUSTAR a la ruta real del repositorio
```

Debes cambiarla para que apunte al directorio del proyecto en el nodo donde se ejecuta Airflow. Por ejemplo:

- Si el proyecto está en:
  - `/home/hadoop/Proyecto-Big-Data-Sentinel-360`

  entonces:

  ```python
  PROJECT_DIR = "/home/hadoop/Proyecto-Big-Data-Sentinel-360"
  ```

---

### 4. Carga y ejecución de los DAGs

1. **Arrancar Airflow**
   - Inicializar la base de datos (solo la primera vez):
     - `airflow db init`
   - Lanzar scheduler y webserver:
     - `airflow scheduler`
     - `airflow webserver -p 8080`

2. **Carga automática de los DAGs**
   - Una vez que los ficheros `.py` estén en el `dags_folder` configurado:
     - Airflow los importará automáticamente.
   - En la interfaz web de Airflow (`http://<host>:8080`) deberían aparecer:
     - `sentinel360_batch_pipeline`
     - `sentinel360_streaming_monitoring`

3. **Ejecución**
   - Desde la UI:
     - Activar el DAG (toggle **On**).
     - Pulsar **Trigger DAG** para lanzar una ejecución.
   - Desde CLI:
     - `airflow dags trigger sentinel360_batch_pipeline`
     - `airflow dags trigger sentinel360_streaming_monitoring`

---

### 5. Resumen

- Los DAGs viven en el repositorio en `airflow/`.
- Para que Airflow los vea, deben estar bajo su `dags_folder` (o debes apuntar `dags_folder` a esa carpeta).
- Ajusta siempre `PROJECT_DIR` para que coincida con la ruta real del proyecto en el servidor donde se ejecuta Airflow.

