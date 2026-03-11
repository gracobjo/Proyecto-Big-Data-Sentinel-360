# Interfaz web de presentación – Sentinel360

Este documento describe la **interfaz web ligera** creada con **Streamlit** para acompañar la defensa del proyecto Sentinel360. No sustituye a Superset/Grafana, sino que sirve como **“panel de control”** para ir recorriendo el ciclo KDD paso a paso y lanzar los scripts clave desde una UI.

---

## 1. Ubicación y requisitos

- Script principal: `web/presentacion_sentinel360_app.py`
- Requisitos mínimos en la máquina donde se ejecute (idealmente el nodo `hadoop` o una máquina que tenga acceso a los mismos binarios/scripts):

```bash
cd /ruta/a/Proyecto-Big-Data-Sentinel-360
pip install streamlit pandas
```

> Nota: la app asume que los scripts (`./scripts/*.sh`, jobs Spark, etc.) ya funcionan si se lanzan desde terminal en esa misma máquina.

Para arrancar la interfaz:

```bash
streamlit run web/presentacion_sentinel360_app.py
```

Se abrirá (o te indicará) una URL local, normalmente `http://localhost:8501`.

---

## 2. Estructura de la interfaz (pestañas KDD)

La app utiliza la barra lateral de Streamlit (`sidebar`) para ofrecer **pestañas por etapa del ciclo KDD**. Internamente, cada pestaña llama a funciones Python que a su vez ejecutan los scripts del proyecto mediante `subprocess.run`, y muestran por pantalla la salida de consola.

### 0 · Arranque de servicios del clúster

- **Función**: `page_arranque_servicios`.
- **Qué hace**:
  - Muestra el comando que se va a ejecutar: `./scripts/start_servicios.sh`.
  - Botón **“Arrancar servicios (start_servicios.sh)”**: lanza el script y muestra stdout/stderr en un panel de texto.
- **Objetivo en la demo**: enseñar que antes de cualquier fase KDD se levanta el stack base (HDFS, YARN, Kafka, MongoDB, Hive, NiFi, etc.).

### 1 · Fase I – Ingesta (NiFi → Kafka + HDFS raw)

- **Función**: `page_fase_i_ingesta`.
- **Scripts que lanza** (botón **“Ejecutar comandos de Fase I”**):
  - `./scripts/setup_hdfs.sh`
  - `./scripts/preparar_ingesta_nifi.sh`
- **Qué muestra**:
  - Explicación de que se crean rutas HDFS y datos de ejemplo para NiFi.
  - Una muestra del CSV `data/sample/gps_events.csv` en forma de tabla (si existe).
- **Objetivo en la demo**: visualizar el **punto de partida de los datos crudos** (GPS) y que NiFi tiene materia prima para enviar a Kafka/HDFS.

### 2 · Fase II – Limpieza y enriquecimiento

- **Función**: `page_fase_ii_limpieza_enriquecimiento`.
- **Scripts que lanza** (botón **“Lanzar limpieza + enriquecimiento (Spark)”**):
  - `./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py`
  - `./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py`
- **Qué muestra**:
  - Descripción de ambos jobs (limpieza de `raw` → `cleaned`, enriquecimiento con Hive → `enriched`).
  - Tablas con `warehouses.csv` y `routes.csv` (datos maestros).
  - Un mapa con los almacenes (`lat`, `lon`) si esas columnas existen (usa `st.map`).
- **Objetivo en la demo**: enseñar **cómo se transforma y enriquece el dato** antes del análisis (Fase II del KDD).

### 3 · Fase II – Grafos (GraphFrames)

- **Función**: `page_fase_ii_grafos`.
- **Scripts que lanza** (botón **“Lanzar análisis de grafos”**):
  - `./scripts/run_spark_submit.sh spark/graph/transport_graph.py`
  - `python scripts/ver_grafos_resultados.py --viz` (usando el intérprete Python actual).
- **Qué muestra**:
  - Explicación de que se construye el grafo almacenes–rutas y se calculan shortest paths y componentes conectados.
  - La salida de ambos comandos.
  - Si existe `grafo.png` en la raíz del proyecto, la imagen se muestra en la propia pestaña.
- **Objetivo en la demo**: visualizar la **topología de la red de transporte** como grafo y enlazarlo con los casos de uso de planificación.

### 4 · Fase III – Streaming de retrasos y anomalías

- **Función**: `page_fase_iii_streaming_anomalias`.
- **Controles**:
  - Selector `modo_stream` con opciones `kafka` o `file` para el job de streaming.
- **Scripts que lanza**:
  - Botón **“Lanzar streaming de retrasos”**:
    - `./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py <modo>`
  - Botón **“Lanzar detección de anomalías (batch)”**:
    - `./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py`
- **Qué muestra**:
  - Descripción de lo que hace cada script:
    - `delays_windowed.py`: ventanas de retrasos, escritura en Hive + MongoDB, alertas en Kafka (`alerts`).
    - `anomaly_detection.py`: K-Means sobre agregados, marcaje de anomalías en MongoDB + alerts.
  - La salida completa de cada ejecución.
- **Objetivo en la demo**: enseñar la parte de **monitorización en tiempo casi real** y la **detección de anomalías** sobre los agregados.

### 5 · Entorno visual (Superset / Grafana)

- **Función**: `page_entorno_visual`.
- **Qué hace**:
  - Explica que los dashboards finales viven en Superset y Grafana, alimentados desde MariaDB (`sentinel360_analytics`) y otras fuentes.
  - Lista los documentos relevantes:
    - `docs/PRESENTACION_ENTORNO_VISUAL.md`
    - `docs/SUPERSET_DASHBOARDS.md`
    - `docs/GRAFANA_DASHBOARDS.md`
  - Muestra un recordatorio de que hay que arrancar Superset/Grafana como se tenga configurado y navegar a los dashboards definidos.
- **Objetivo en la demo**: conectar el **pipeline técnico** que se ha ido viendo en pestañas anteriores con la **presentación visual final**.

---

## 3. Flujo típico de la demo usando la interfaz

1. Abrir la app Streamlit con `streamlit run web/presentacion_sentinel360_app.py`.
2. En la barra lateral, ir pasando por las pestañas en este orden:
   - `0 · Arranque de servicios`
   - `1 · Fase I – Ingesta`
   - `2 · Fase II – Limpieza y enriquecimiento`
   - `3 · Fase II – Grafos`
   - `4 · Fase III – Streaming + anomalías`
   - `5 · Entorno visual (Superset / Grafana)`
3. En cada pestaña, pulsar el botón correspondiente para **lanzar los scripts** y mostrar la salida en vivo, explicando brevemente:
   - Qué datos entran.
   - Qué transformación/algoritmo se aplica.
   - Qué salidas se generan (HDFS, Hive, MongoDB, Kafka, MariaDB).
4. Terminar abriendo los dashboards en Superset/Grafana para enseñar el “front” que vería un usuario de negocio.

---

## 4. Gradio (opcional – idea futura)

En lugar de (o además de) Streamlit, se podría utilizar **Gradio** para construir una interfaz muy ligera sobre **funciones concretas** del proyecto, por ejemplo:

- Un formulario para probar el detector de anomalías (CU3), donde el usuario selecciona una ruta y rango de fechas y se muestran solo las ventanas marcadas como anómalas.

Sin embargo, para la presentación principal del ciclo KDD y la orquestación de scripts, Streamlit encaja mejor por su estructura de pestañas y facilidad para mostrar logs y gráficos simples.

