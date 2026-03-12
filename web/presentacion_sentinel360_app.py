import subprocess
import sys
import base64
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
PAGE_LABELS = [
    "0 · Arranque de servicios",
    "1 · Fase I – Ingesta",
    "2 · Fase II – Limpieza y enriquecimiento",
    "3 · Fase II – Grafos",
    "4 · Fase III – Streaming + anomalías",
    "5 · Entorno visual (Superset / Grafana)",
]


def run_command(cmd: str) -> str:
    """
    Ejecuta un comando de shell desde la raíz del proyecto y devuelve stdout+stderr.
    No lanza excepción si falla: devolvemos el error en texto para mostrarlo en Streamlit.
    """
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return completed.stdout
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        return f"Error ejecutando comando:\n{exc}"


def load_sample_data():
    gps_path = DATA_SAMPLE_DIR / "gps_events.csv"
    wh_path = DATA_SAMPLE_DIR / "warehouses.csv"
    routes_path = DATA_SAMPLE_DIR / "routes.csv"

    gps_df = pd.read_csv(gps_path) if gps_path.exists() else None
    wh_df = pd.read_csv(wh_path) if wh_path.exists() else None
    routes_df = pd.read_csv(routes_path) if routes_path.exists() else None
    return gps_df, wh_df, routes_df


def navigate_to(page_label: str) -> None:
    """
    Cambia de pestaña dentro de la propia app sin perder la URL.
    """
    st.session_state["sidebar_page"] = page_label


def render_top_nav(current_label: str) -> None:
    """
    Muestra controles de navegación anterior/siguiente al inicio de cada página.
    """
    if current_label not in PAGE_LABELS:
        return
    idx = PAGE_LABELS.index(current_label)
    cols = st.columns(3)
    with cols[0]:
        if idx > 0:
            st.button(
                f"← {PAGE_LABELS[idx - 1]}",
                key=f"topnav_prev_{idx}",
                on_click=navigate_to,
                args=(PAGE_LABELS[idx - 1],),
            )
    with cols[2]:
        if idx < len(PAGE_LABELS) - 1:
            st.button(
                f"{PAGE_LABELS[idx + 1]} →",
                key=f"topnav_next_{idx}",
                on_click=navigate_to,
                args=(PAGE_LABELS[idx + 1],),
            )


def show_text_file_preview(path: Path, label: str, max_lines: int = 5) -> None:
    """
    Muestra un resumen de un fichero de texto (primeras y últimas N líneas).
    Si el fichero tiene <= 2 * max_lines, se muestra completo.
    """
    if not path.exists():
        st.info(f"No se ha encontrado `{path.relative_to(PROJECT_ROOT)}`.")
        return

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - interfaz interactiva
        st.warning(f"No se ha podido leer `{path}`: {exc}")
        return

    lines = content.splitlines()
    if len(lines) <= max_lines * 2:
        preview = "\n".join(lines)
    else:
        head = "\n".join(lines[:max_lines])
        tail = "\n".join(lines[-max_lines:])
        preview = f"{head}\n...\n{tail}"

    suffix = path.suffix.lower()
    if suffix == ".json":
        language = "json"
    elif suffix in {".md", ".markdown"}:
        language = "markdown"
    else:
        language = "text"

    with st.expander(label):
        st.code(preview, language=language)


def page_arranque_servicios():
    st.header("0 · Arranque de servicios del clúster")
    render_top_nav("0 · Arranque de servicios")
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD**

        Antes de empezar con la Fase I (ingesta) necesitamos tener levantado todo el
        **stack de servicios** del proyecto:

        - HDFS y YARN (almacenamiento distribuido y ejecución de Spark).
        - Kafka (cola de eventos para GPS y alertas).
        - Hive (metastore y consultas SQL sobre HDFS).
        - MongoDB y MariaDB (capas de almacenamiento analítico).
        - NiFi y servicios auxiliares documentados en el documento `docs/ARRANQUE_SERVICIOS.md`
          (consultable más abajo desde esta misma pestaña).

        Esta pestaña debe ejecutarse **en el nodo donde están instalados los servicios**
        (por ejemplo, la máquina `hadoop` del clúster).

        - **Entrada**: configuración ya preparada en los scripts del proyecto.
        - **Salida**: servicios arriba y verificados para poder seguir con las fases KDD.
        """
    )

    docs_path = PROJECT_ROOT / "docs" / "ARRANQUE_SERVICIOS.md"
    if docs_path.exists():
        with st.expander("Ver detalle de arranque de servicios (`docs/ARRANQUE_SERVICIOS.md`)"):
            st.markdown(docs_path.read_text(encoding="utf-8"))
    else:
        st.info("No se ha encontrado `docs/ARRANQUE_SERVICIOS.md` en el proyecto.")

    st.subheader("Comando que se va a ejecutar")
    st.code("./scripts/start_servicios.sh", language="bash")

    st.markdown(
        """
        **¿Qué hace `start_servicios.sh`?**

        - **Objetivo**: levantar de forma ordenada los servicios base del clúster
          (HDFS, YARN, Kafka, Hive, MongoDB, MariaDB, NiFi, etc.).
        - **Entrada**: configuración del entorno (variables como `HADOOP_HOME`, `HIVE_HOME`,
          rutas de logs, etc.) ya definida en el propio script y en el sistema.
        - **Salida**:
          - Servicios arrancados si todo va bien.
          - Ficheros de log actualizados (por ejemplo en `logs/`) para diagnosticar errores.
        """
    )

    if st.button("Arrancar servicios (start_servicios.sh)"):
        with st.spinner("Arrancando servicios..."):
            output = run_command("./scripts/start_servicios.sh")
        st.subheader("Salida del script")
        st.text(output)

    show_text_file_preview(
        SCRIPTS_DIR / "start_servicios.sh",
        "Ver contenido de `scripts/start_servicios.sh`",
    )

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    st.button(
        "Ir a 1 · Fase I – Ingesta",
        key="nav_0_to_1",
        on_click=navigate_to,
        args=("1 · Fase I – Ingesta",),
    )


def page_fase_i_ingesta():
    st.header("1 · Fase I – Ingesta (NiFi → Kafka + HDFS raw)")
    render_top_nav("1 · Fase I – Ingesta")
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase I – Selección e ingesta de datos)**

        En esta etapa preparamos las **rutas en HDFS** y los **datos de ejemplo** para que NiFi
        pueda leer los logs GPS y publicar en Kafka (`raw-data` / `filtered-data`), dejando además
        una copia *raw* en HDFS.

        - **Entrada**:
          - Ficheros de ejemplo en `data/sample/gps_events.*`.
          - Configuración del flujo NiFi (`ingest/gps_transport_flow_importable.json`).
        - **Transformación**:
          - Copia de datos maestros y logs al HDFS del proyecto.
          - Preparación de directorios esperados por NiFi.
        - **Salida esperada**:
          - Directorios `raw` poblados en HDFS.
          - Flujo NiFi listo para leer esos datos y mandarlos a Kafka.

        Más detalle de esta fase en `docs/INGEST/` y en `docs/KDD_FASES.md`.
        """
    )

    # Documentación relacionada accesible desde la propia pestaña
    ingest_docs = [
        ("docs/KDD_FASES.md", "Ver resumen de fases KDD (`docs/KDD_FASES.md`)"),
        ("ingest/FLUJO_GPS_README.md", "Ver flujo de ingesta GPS (`ingest/FLUJO_GPS_README.md`)"),
        ("ingest/nifi/FASE_I_INGESTA.md", "Detalle NiFi Fase I (`ingest/nifi/FASE_I_INGESTA.md`)"),
        ("ingest/nifi/RESOLVER_ERRORES_FLUJO_GPS.md", "Resolver errores flujo GPS (`ingest/nifi/RESOLVER_ERRORES_FLUJO_GPS.md`)"),
    ]
    for rel_path, label in ingest_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    st.subheader("Vista previa de ficheros de entrada")
    gps_json_path = PROJECT_ROOT / "data" / "sample" / "gps_events.json"
    show_text_file_preview(
        gps_json_path,
        "Muestra de `data/sample/gps_events.json` (5 primeras y 5 últimas líneas si es largo)",
    )
    nifi_flow_path = PROJECT_ROOT / "ingest" / "gps_transport_flow_importable.json"
    show_text_file_preview(
        nifi_flow_path,
        "Muestra de `ingest/gps_transport_flow_importable.json` (definición flujo NiFi)",
    )

    nifi_png = PROJECT_ROOT / "ingest" / "capturas" / "grupoProcesadores.png"
    if nifi_png.exists():
        st.subheader("Vista del grupo de procesadores NiFi")
        st.image(
            str(nifi_png),
            caption=(
                "Grupo de procesadores NiFi para la Fase I: "
                "GetFile → UpdateAttribute → PutHDFS + SplitText → "
                "EvaluateJsonPath → RouteOnAttribute → PublishKafka raw/filtered"
            ),
        )

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/setup_hdfs.sh\n"
        "./scripts/preparar_ingesta_nifi.sh\n",
        language="bash",
    )

    st.markdown(
        """
        **¿Qué hacen estos scripts?**

        - `setup_hdfs.sh`:
          - **Objetivo**: crear en HDFS las rutas necesarias para el proyecto
            (raw, processed, maestros, etc.).
          - **Entrada**: estructura de rutas definida en el propio script y en `config.py`.
          - **Salida**: directorios creados en HDFS, listos para recibir datos desde NiFi y Spark.
        - `preparar_ingesta_nifi.sh`:
          - **Objetivo**: copiar datos de ejemplo y dejar preparada la carpeta de entrada
            que NiFi vigila (por ejemplo `gps_logs` en el nodo hadoop).
          - **Entrada**: ficheros de `data/sample` (como `gps_events.json`).
          - **Salida**: ficheros ubicados en el directorio de entrada que usa el flujo NiFi.
        """
    )

    show_text_file_preview(
        SCRIPTS_DIR / "setup_hdfs.sh",
        "Ver contenido de `scripts/setup_hdfs.sh`",
    )
    show_text_file_preview(
        SCRIPTS_DIR / "preparar_ingesta_nifi.sh",
        "Ver contenido de `scripts/preparar_ingesta_nifi.sh`",
    )

    if st.button("Ejecutar comandos de Fase I"):
        with st.spinner("Ejecutando scripts de Fase I..."):
            output = run_command("./scripts/setup_hdfs.sh && ./scripts/preparar_ingesta_nifi.sh")
        st.subheader("Salida de los scripts")
        st.text(output)

    st.subheader("Datos de ejemplo (data/sample)")
    gps_df, wh_df, routes_df = load_sample_data()
    if gps_df is not None:
        st.markdown("**Muestra de eventos GPS (`gps_events.csv`)**")
        st.dataframe(gps_df.head())
    else:
        st.info("No se ha encontrado `data/sample/gps_events.csv`.")

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 0 · Arranque de servicios",
            key="nav_1_to_0",
            on_click=navigate_to,
            args=("0 · Arranque de servicios",),
        )
    with cols[1]:
        st.button(
            "Ir a 2 · Fase II – Limpieza y enriquecimiento",
            key="nav_1_to_2",
            on_click=navigate_to,
            args=("2 · Fase II – Limpieza y enriquecimiento",),
        )


def page_fase_ii_limpieza_enriquecimiento():
    st.header("2 · Fase II – Limpieza y enriquecimiento")
    render_top_nav("2 · Fase II – Limpieza y enriquecimiento")
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase II – Preprocesamiento y transformación)**

        Desde aquí se lanzan los jobs Spark de **limpieza** y **enriquecimiento** de los datos
        que vienen de la Fase I:

        - `clean_and_normalize.py`: normaliza y limpia los datos brutos en HDFS (`raw` → `cleaned`).
        - `enrich_with_hive.py`: cruza datos limpios con maestros de Hive (`warehouses`) y genera `enriched`.

        - **Entrada**:
          - Datos *raw* en HDFS (`/user/hadoop/proyecto/raw` y rutas definidas en `config.py`).
          - Tablas Hive de maestros (`warehouses`, `routes`).
        - **Transformación**:
          - Limpieza de columnas problemáticas, normalización de tipos y valores.
          - Join con almacenes/rutas para enriquecer los eventos.
        - **Salida esperada**:
          - Directorios `procesado/cleaned` y `procesado/enriched` en HDFS (ficheros Parquet).

        Para más detalle técnico, ver `docs/FASE_II_PREPROCESAMIENTO.md` y `docs/PROBAR_PIPELINE.md`.
        """
    )

    # Documentación técnica de apoyo para esta fase
    fase2_docs = [
        ("docs/FASE_II_PREPROCESAMIENTO.md", "Fase II – Preprocesamiento (`docs/FASE_II_PREPROCESAMIENTO.md`)"),
        ("docs/PROBAR_PIPELINE.md", "Cómo probar el pipeline (`docs/PROBAR_PIPELINE.md`)"),
    ]
    for rel_path, label in fase2_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py\n"
        "./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py\n",
        language="bash",
    )

    st.markdown(
        """
        **¿Qué hace `run_spark_submit.sh` en esta fase?**

        - **Objetivo general**: encapsular la llamada a `spark-submit` con la configuración del clúster
          (YARN, jars adicionales, versión de Python, etc.) para no repetir opciones en cada comando.
        - **Entradas**:
          - El script Python a ejecutar (`spark/cleaning/clean_and_normalize.py`, `spark/cleaning/enrich_with_hive.py`, etc.).
          - Parámetros opcionales como `--local` para ejecutar sin YARN (ver `docs/PROBAR_PIPELINE.md`).
        - **Salidas**:
          - Jobs Spark ejecutados en el clúster (o en modo local).
          - Logs de Spark accesibles desde la consola y desde la UI de YARN.
        """
    )

    show_text_file_preview(
        SCRIPTS_DIR / "run_spark_submit.sh",
        "Ver contenido de `scripts/run_spark_submit.sh`",
    )

    if st.button("Lanzar limpieza + enriquecimiento (Spark)"):
        with st.spinner("Lanzando jobs Spark de limpieza y enriquecimiento..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py && "
                "./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py"
            )
        st.subheader("Salida de Spark submit")
        st.text(output)

    _, wh_df, routes_df = load_sample_data()
    if wh_df is not None:
        st.subheader("Almacenes (`warehouses.csv`)")
        st.dataframe(wh_df)
        if {"lat", "lon"}.issubset(wh_df.columns):
            st.map(wh_df.rename(columns={"lat": "latitude", "lon": "longitude"}))

    if routes_df is not None:
        st.subheader("Rutas (`routes.csv`)")
        st.dataframe(routes_df)

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 1 · Fase I – Ingesta",
            key="nav_2_to_1",
            on_click=navigate_to,
            args=("1 · Fase I – Ingesta",),
        )
    with cols[1]:
        st.button(
            "Ir a 3 · Fase II – Grafos",
            key="nav_2_to_3",
            on_click=navigate_to,
            args=("3 · Fase II – Grafos",),
        )


def page_fase_ii_grafos():
    st.header("3 · Fase II – Grafos (GraphFrames)")
    render_top_nav("3 · Fase II – Grafos")
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase II – Modelado como grafo)**

        Esta pestaña acompaña el **análisis de grafos** sobre la red de transporte:

        - `transport_graph.py` construye el grafo almacenes–rutas y calcula shortest paths y componentes.
        - `ver_grafos_resultados.py` permite inspeccionar resultados y generar `grafo.png`.

        - **Entrada**:
          - Datos enriquecidos en HDFS (`procesado/enriched`).
          - Definiciones de almacenes y rutas en Hive.
        - **Transformación**:
          - Construcción de un grafo dirigido con GraphFrames.
          - Cálculo de componentes conectados y caminos mínimos.
        - **Salida esperada**:
          - Resultados en `procesado/graph` (Parquet).
          - Imagen `grafo.png` como apoyo visual para la demo.

        Puedes usar esta pestaña para explicar la **topología logística** y cómo el grafo
        ayuda a entender rutas alternativas, cuellos de botella, etc.
        """
    )

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/graph/transport_graph.py\n"
        "python scripts/ver_grafos_resultados.py --viz\n",
        language="bash",
    )

    if st.button("Lanzar análisis de grafos"):
        with st.spinner("Lanzando Spark (GraphFrames) y generación de grafo..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/graph/transport_graph.py && "
                f"{sys.executable} scripts/ver_grafos_resultados.py --viz"
            )
        st.subheader("Salida de comandos de grafos")
        st.text(output)

    grafo_png = PROJECT_ROOT / "grafo.png"
    if grafo_png.exists():
        st.subheader("Imagen del grafo (`grafo.png`)")
        st.image(str(grafo_png))
    else:
        st.info("Aún no se ha generado `grafo.png`. Ejecuta `ver_grafos_resultados.py --viz` primero.")

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 2 · Fase II – Limpieza y enriquecimiento",
            key="nav_3_to_2",
            on_click=navigate_to,
            args=("2 · Fase II – Limpieza y enriquecimiento",),
        )
    with cols[1]:
        st.button(
            "Ir a 4 · Fase III – Streaming + anomalías",
            key="nav_3_to_4",
            on_click=navigate_to,
            args=("4 · Fase III – Streaming + anomalías",),
        )


def page_fase_iii_streaming_anomalias():
    st.header("4 · Fase III – Streaming de retrasos y anomalías")
    render_top_nav("4 · Fase III – Streaming + anomalías")
    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Fase III – Minería de datos / explotación en tiempo casi real)**

        Desde aquí puedes lanzar:

        - `delays_windowed.py` (Spark Streaming): lee de Kafka (`raw-data` o ficheros), calcula retrasos
          por ventana y escribe en Hive + MongoDB, generando alertas al topic `alerts`.
        - `anomaly_detection.py` (batch): detecta anomalías sobre los agregados y escribe en MongoDB + Kafka.

        - **Entrada**:
          - Eventos de GPS ya normalizados (desde Kafka o desde ficheros en HDFS).
          - Agregados de retrasos generados por el propio streaming.
        - **Transformación**:
          - Cálculo de métricas de retrasos por ventana temporal.
          - Aplicación de modelos de ML (K-Means) para detectar comportamientos anómalos.
        - **Salida esperada**:
          - Tabla Hive `aggregated_delays`.
          - Colecciones MongoDB con agregados y anomalías.
          - Mensajes de alerta en el topic Kafka `alerts`.

        Esta etapa es la que conecta el *pipeline técnico* con los **casos de uso de monitorización
        y alertas** que luego se verán reflejados en los dashboards.
        """
    )

    # Documentación adicional para Fase III
    fase3_docs = [
        ("docs/FASE_III_STREAMING.md", "Fase III – Streaming y carga multicapa (`docs/FASE_III_STREAMING.md`)"),
    ]
    for rel_path, label in fase3_docs:
        doc_path = PROJECT_ROOT / rel_path
        if doc_path.exists():
            with st.expander(label):
                st.markdown(doc_path.read_text(encoding="utf-8"))

    modo_stream = st.selectbox("Modo de entrada para `delays_windowed.py`", ["kafka", "file"])

    st.subheader("Comandos de esta fase")
    st.code(
        f"./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {modo_stream}\n"
        "./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py\n",
        language="bash",
    )

    if st.button("Lanzar streaming de retrasos"):
        with st.spinner("Lanzando Spark Streaming (delays_windowed.py)..."):
            output = run_command(
                f"./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py {modo_stream}"
            )
        st.subheader("Salida de delays_windowed.py")
        st.text(output)

    if st.button("Lanzar detección de anomalías (batch)"):
        with st.spinner("Lanzando Spark ML (anomaly_detection.py)..."):
            output = run_command(
                "./scripts/run_spark_submit.sh spark/ml/anomaly_detection.py"
            )
        st.subheader("Salida de anomaly_detection.py")
        st.text(output)

    st.markdown("---")
    st.markdown("**Navegación rápida**")
    cols = st.columns(2)
    with cols[0]:
        st.button(
            "Ir a 3 · Fase II – Grafos",
            key="nav_4_to_3",
            on_click=navigate_to,
            args=("3 · Fase II – Grafos",),
        )
    with cols[1]:
        st.button(
            "Ir a 5 · Entorno visual",
            key="nav_4_to_5",
            on_click=navigate_to,
            args=("5 · Entorno visual (Superset / Grafana)",),
        )


def page_entorno_visual():
    st.header("5 · Entorno visual (Superset / Grafana)")
    render_top_nav("5 · Entorno visual (Superset / Grafana)")

    img_candidates = [
        PROJECT_ROOT / "sentinel360v2.png",
        PROJECT_ROOT / "Sentinel360.png",
        PROJECT_ROOT.parent / "sentinel360v2.png",
    ]
    img_path = next((p for p in img_candidates if p.exists()), None)
    if img_path is not None:
        st.subheader("Arquitectura Sentinel360")
        st.image(
            str(img_path),
            caption="Arquitectura Sentinel360 – vista general",
        )
        if st.button(
            "Comenzar recorrido KDD desde esta arquitectura",
            key="hero_nav_5_to_0",
        ):
            navigate_to("0 · Arranque de servicios")

    st.markdown(
        """
        **Objetivo dentro del ciclo KDD (Presentación de resultados)** – última etapa del ciclo.

        Sentinel360 ya utiliza **Superset** y **Grafana** para los dashboards finales que consumen
        los datos generados en las fases anteriores.

        Esta pestaña sirve como “hub” con enlaces y recordatorio de los KPIs que se alimentan
        desde Spark y MongoDB hacia MariaDB (`sentinel360_analytics`).

        - **Entrada**:
          - Tablas y vistas en MariaDB y otras fuentes configuradas para Superset/Grafana.
        - **Transformación**:
          - Construcción de dashboards, gráficos de retrasos, tablas de anomalías y KPIs de negocio.
        - **Salida esperada**:
          - Cuadros de mando navegables por usuarios de negocio para tomar decisiones.

        Usa esta pestaña como transición entre el **pipeline de datos** y la **capa de presentación**
        que verá el usuario final.
        """
    )

    st.subheader("Cómo levantar y solucionar fallos")
    st.markdown(
        "Guía rápida: **levantar** Superset y Grafana con Docker y **qué hacer cuando algo falla** "
        "(error 500 en Superset, driver MySQL, conexión a MariaDB, paneles sin datos en Grafana). "
        "Incluye los scripts `init_superset.sh`, `verificar_conexion_superset_mariadb.sh` y el flujo de datos para Grafana."
    )
    docs_dir = PROJECT_ROOT / "docs"
    levantar_doc = docs_dir / "DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md"
    if levantar_doc.exists():
        st.markdown("- **Levantar dashboards y solucionar fallos**: `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`")
        with st.expander("Ver `DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`"):
            st.markdown(levantar_doc.read_text(encoding="utf-8"))
    else:
        st.markdown("- **Levantar dashboards y solucionar fallos**: `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md` *(no encontrado)*")

    st.subheader("Documentación de dashboards")
    doc_files = [
        ("PRESENTACION_ENTORNO_VISUAL.md", "Presentación del entorno visual"),
        ("SUPERSET_DASHBOARDS.md", "Dashboards Superset"),
        ("GRAFANA_DASHBOARDS.md", "Dashboards Grafana"),
    ]
    for filename, desc in doc_files:
        doc_path = docs_dir / filename
        if doc_path.exists():
            st.markdown(f"- **{desc}**: `docs/{filename}`")
            with st.expander(f"Ver `{filename}`"):
                st.markdown(doc_path.read_text(encoding="utf-8"))
        else:
            st.markdown(f"- **{desc}**: `docs/{filename}` *(no encontrado)*")

    st.info(
        "Para la demo: `cd docker && docker compose up -d mariadb superset grafana`. "
        "Si Superset da 500, ejecuta `./scripts/init_superset.sh`. "
        "Detalle completo en `docs/DASHBOARDS_LEVANTAR_Y_SOLUCIONAR.md`."
    )

    st.subheader("Material de presentación")
    pptx_candidates = [
        PROJECT_ROOT / "Sentinel360_Proactive_Logistics_Intelligence.pptx",
        PROJECT_ROOT.parent / "Sentinel360_Proactive_Logistics_Intelligence.pptx",
    ]
    pptx_path = next((p for p in pptx_candidates if p.exists()), None)
    if pptx_path is not None:
        try:
            pptx_bytes = pptx_path.read_bytes()
            st.download_button(
                label="Descargar presentación Sentinel360 (PPTX)",
                data=pptx_bytes,
                file_name=pptx_path.name,
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"No se ha podido preparar la descarga de la presentación: {exc}")
    else:
        st.info(
            "No se ha encontrado `Sentinel360_Proactive_Logistics_Intelligence.pptx` "
            "en el proyecto ni en el directorio padre."
        )

    pdf_candidates = [
        PROJECT_ROOT / "Sentinel360_Proactive_Logistics_Intelligence.pdf",
        PROJECT_ROOT.parent / "Sentinel360_Proactive_Logistics_Intelligence.pdf",
    ]
    pdf_path = next((p for p in pdf_candidates if p.exists()), None)
    if pdf_path is not None:
        st.markdown("#### Descargar versión PDF de la presentación")
        try:
            pdf_bytes = pdf_path.read_bytes()
            st.download_button(
                label="Descargar presentación Sentinel360 (PDF)",
                data=pdf_bytes,
                file_name=pdf_path.name,
                mime="application/pdf",
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"No se ha podido preparar la descarga en PDF: {exc}")


def main():
    st.set_page_config(
        page_title="Sentinel360 – Presentación KDD",
        layout="wide",
    )
    st.sidebar.title("Sentinel360 – Demo KDD")
    st.sidebar.markdown("Selecciona la etapa del ciclo KDD:")
    st.sidebar.markdown(
        "[Repositorio en GitHub]("
        "https://github.com/gracobjo/Proyecto-Big-Data-Sentinel-360"
        ")"
    )

    pages = {
        "0 · Arranque de servicios": page_arranque_servicios,
        "1 · Fase I – Ingesta": page_fase_i_ingesta,
        "2 · Fase II – Limpieza y enriquecimiento": page_fase_ii_limpieza_enriquecimiento,
        "3 · Fase II – Grafos": page_fase_ii_grafos,
        "4 · Fase III – Streaming + anomalías": page_fase_iii_streaming_anomalias,
        "5 · Entorno visual (Superset / Grafana)": page_entorno_visual,
    }

    page_names = list(pages.keys())
    if "sidebar_page" not in st.session_state:
        st.session_state["sidebar_page"] = page_names[0]

    st.sidebar.radio(
        "Etapa",
        page_names,
        key="sidebar_page",
    )

    pages[st.session_state["sidebar_page"]]()


if __name__ == "__main__":
    main()

