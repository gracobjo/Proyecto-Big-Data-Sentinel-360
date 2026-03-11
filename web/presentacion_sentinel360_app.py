import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


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


def page_arranque_servicios():
    st.header("0 · Arranque de servicios del clúster")
    st.write(
        "Esta pestaña lanza el script de arranque para HDFS, YARN, Kafka, MongoDB, Hive, NiFi, etc. "
        "Debe ejecutarse en el nodo donde están instalados los servicios (p. ej. `hadoop`)."
    )

    st.subheader("Comando que se va a ejecutar")
    st.code("./scripts/start_servicios.sh", language="bash")

    if st.button("Arrancar servicios (start_servicios.sh)"):
        with st.spinner("Arrancando servicios..."):
            output = run_command("./scripts/start_servicios.sh")
        st.subheader("Salida del script")
        st.text(output)


def page_fase_i_ingesta():
    st.header("1 · Fase I – Ingesta (NiFi → Kafka + HDFS raw)")
    st.markdown(
        """
        Aquí se preparan las rutas en HDFS y los datos de ejemplo para que NiFi pueda leer
        los logs GPS y publicar en Kafka (`raw-data` / `filtered-data`), dejando copia `raw` en HDFS.
        """
    )

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/setup_hdfs.sh\n"
        "./scripts/preparar_ingesta_nifi.sh\n",
        language="bash",
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


def page_fase_ii_limpieza_enriquecimiento():
    st.header("2 · Fase II – Limpieza y enriquecimiento")
    st.markdown(
        """
        Desde aquí se lanzan los jobs Spark de limpieza y enriquecimiento:

        - `clean_and_normalize.py`: normaliza y limpia los datos brutos en HDFS (`raw` → `cleaned`).
        - `enrich_with_hive.py`: cruza datos limpios con maestros de Hive (`warehouses`) y genera `enriched`.
        """
    )

    st.subheader("Comandos de esta fase")
    st.code(
        "./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py\n"
        "./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py\n",
        language="bash",
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


def page_fase_ii_grafos():
    st.header("3 · Fase II – Grafos (GraphFrames)")
    st.markdown(
        """
        Esta pestaña está pensada para acompañar el análisis de grafos:

        - `transport_graph.py` construye el grafo almacenes–rutas y calcula shortest paths y componentes.
        - `ver_grafos_resultados.py` permite inspeccionar resultados y generar `grafo.png`.
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


def page_fase_iii_streaming_anomalias():
    st.header("4 · Fase III – Streaming de retrasos y anomalías")
    st.markdown(
        """
        Desde aquí puedes lanzar:

        - `delays_windowed.py` (Spark Streaming): lee de Kafka (`raw-data` o ficheros), calcula retrasos
          por ventana y escribe en Hive + MongoDB, generando alertas al topic `alerts`.
        - `anomaly_detection.py` (batch): detecta anomalías sobre los agregados y escribe en MongoDB + Kafka.
        """
    )

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


def page_entorno_visual():
    st.header("5 · Entorno visual (Superset / Grafana)")
    st.markdown(
        """
        Sentinel360 ya utiliza **Superset** y **Grafana** para los dashboards finales.

        Esta pestaña sirve como “hub” con enlaces y recordatorio de los KPIs que se alimentan
        desde Spark y MongoDB hacia MariaDB (`sentinel360_analytics`).
        """
    )

    st.subheader("Documentación de dashboards")
    st.markdown(
        """
        - `docs/PRESENTACION_ENTORNO_VISUAL.md`
        - `docs/SUPERSET_DASHBOARDS.md`
        - `docs/GRAFANA_DASHBOARDS.md`
        """
    )

    st.info(
        "Para la demo, arranca Superset/Grafana como tengas configurado en tu entorno y "
        "navega a los dashboards definidos en la documentación."
    )


def main():
    st.set_page_config(
        page_title="Sentinel360 – Presentación KDD",
        layout="wide",
    )
    st.sidebar.title("Sentinel360 – Demo KDD")
    st.sidebar.markdown("Selecciona la etapa del ciclo KDD:")

    pages = {
        "0 · Arranque de servicios": page_arranque_servicios,
        "1 · Fase I – Ingesta": page_fase_i_ingesta,
        "2 · Fase II – Limpieza y enriquecimiento": page_fase_ii_limpieza_enriquecimiento,
        "3 · Fase II – Grafos": page_fase_ii_grafos,
        "4 · Fase III – Streaming + anomalías": page_fase_iii_streaming_anomalias,
        "5 · Entorno visual (Superset / Grafana)": page_entorno_visual,
    }

    choice = st.sidebar.radio(
        "Etapa",
        list(pages.keys()),
        index=0,
    )
    pages[choice]()


if __name__ == "__main__":
    main()

