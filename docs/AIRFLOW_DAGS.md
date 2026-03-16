## Integración de los DAGs de Sentinel360 en Apache Airflow

Este documento explica **cómo arrancar Airflow**, **dónde guardar** los DAGs y **cómo ejecutarlos**.

---

### 0. Cómo arrancar Airflow

**Requisito:** tener Apache Airflow instalado (por ejemplo `pip install apache-airflow` en un venv, o el venv en `/home/hadoop/mi_proyecto_airflow/venv_airflow` que usa el script). En **Airflow 3.x** la UI se sirve con `airflow api-server` (el script ya lo usa).

**Primera vez (solo una vez):**

```bash
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"
airflow db init
airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@localhost --password admin
```

**Incorporar todos los DAGs del proyecto:** desde la raíz del repo ejecuta:

```bash
bash ./scripts/setup_airflow_dags.sh
```

Eso deja en `airflow.cfg` la opción `dags_folder` apuntando a `airflow/` del proyecto, así Airflow carga los 8 DAGs agrupados por etapa KDD (infra, fase I/II/III, dashboards). Si prefieres no tocar la configuración y solo copiar los `.py` a `$AIRFLOW_HOME/dags`, usa: `bash ./scripts/setup_airflow_dags.sh --copy`.

**Arrancar scheduler y API server (UI):**

```bash
cd ~/Documentos/ProyectoBigData
bash ./scripts/start_airflow.sh
```

- **UI:** http://localhost:8080 (o http://192.168.99.10:8080). Si el puerto está ocupado: `AIRFLOW_PORT=8081 bash ./scripts/start_airflow.sh`
- **Usuario por defecto:** admin / admin (si lo creaste así arriba).

---

### 1. DAGs disponibles (agrupados por etapa KDD)

Los DAGs están organizados por **fase del ciclo KDD** y por **infraestructura/dashboards**. En la carpeta `airflow/`:

| DAG | Etapa | Descripción |
|-----|-------|-------------|
| **sentinel360_infra_start** | Infra | Arrancar servicios: HDFS, YARN, Kafka, MongoDB, MariaDB, Hive, NiFi. |
| **sentinel360_infra_stop** | Infra | Parar todos los servicios. |
| **sentinel360_fase_i_ingesta** | Fase I – Ingesta | Crear temas Kafka → ingesta GPS sintética + OpenWeather (paralelo). Requiere variable `openweather_api_key`. |
| **sentinel360_fase_ii_preprocesamiento** | Fase II – Preprocesamiento | Hive setup → limpieza → enriquecimiento → grafo de transporte. |
| **sentinel360_fase_iii_batch** | Fase III – Minería (batch) | Cargar agregados Hive/MongoDB → detección de anomalías → KPIs + anomalías a MariaDB. |
| **sentinel360_fase_iii_streaming** | Fase III – Streaming | Job de retrasos por ventana (`delays_windowed.py`). Variable opcional `sentinel360_streaming_mode` = `file` \| `kafka`. |
| **sentinel360_dashboards_levantar** | Dashboards | Levantar MariaDB, Superset y Grafana con Docker (puertos 3307, 8089, 3000). |
| **sentinel360_dashboards_exportar** | Dashboards | Exportar a Superset/Grafana: **MongoDB** (aggregated_delays + anomalies → MariaDB) y **Hive** (aggregated_delays, reporte_diario_retrasos → MariaDB). |

**Exportación a dashboards:** el DAG `sentinel360_dashboards_exportar` ejecuta:
- `scripts/mongo_to_mariadb_kpi.py --source mongo --export-anomalies` (KPIs por vehículo/almacén y tabla `kpi_anomalies`).
- `scripts/export_hive_to_mariadb.py --dias 7` (consultas Hive relevantes → tablas `kpi_hive_aggregated_delays`, `kpi_hive_reporte_diario`).

Las tablas de MariaDB deben existir (crear con `docs/sql_entorno_visual/02_create_kpi_tables.sql`).

---

### 2. Dónde deben guardarse los DAGs en Airflow

**Recomendado:** usar el script `./scripts/setup_airflow_dags.sh` (sin argumentos) para que `dags_folder` apunte a la carpeta `airflow/` del proyecto. Así siempre se usan los DAGs del repo.

Airflow detecta automáticamente los DAGs que se encuentran en el directorio configurado como `dags_folder` (por defecto, `\$AIRFLOW_HOME/dags`). Tienes dos opciones:

1. **Copiar los DAGs al directorio `dags` de Airflow** (alternativa: `bash ./scripts/setup_airflow_dags.sh --copy`)
   - Copia los `dag_sentinel360_*.py` (infra_start, infra_stop, fase_i_ingesta, fase_ii_preprocesamiento, fase_iii_batch, fase_iii_streaming, dashboards_levantar, dashboards_exportar) a `\$AIRFLOW_HOME/dags/`.

2. **Apuntar `dags_folder` al proyecto**
   - Editar `airflow.cfg` (en `\$AIRFLOW_HOME`) y cambiar:
     - `dags_folder = /ruta/a/tu/proyecto/airflow`
   - De esta forma, Airflow leerá directamente los DAGs desde la carpeta `airflow/` del repositorio (sin necesidad de copiarlos).

> En ambos casos, asegúrate de que las rutas internas (`PROJECT_DIR`) de los DAGs apuntan a la ubicación real del proyecto en el servidor.

---

### 3. Ajustar la ruta del proyecto (`PROJECT_DIR`)

Los DAGs usan la ruta del repositorio para ejecutar `scripts/start_servicios.sh` y `scripts/stop_servicios.sh`. Por defecto:

- `PROJECT_DIR = "/home/hadoop/Documentos/ProyectoBigData"`

Puedes cambiarla de dos formas:

1. **Variable de Airflow** (recomendado): en la UI, Admin → Variables → crear `sentinel360_project_dir` con el valor `/ruta/real/al/proyecto`.
2. **Editar el DAG**: en cada archivo `.py`, modificar la línea `PROJECT_DIR = ...` o el `default_var` dentro de `Variable.get(...)`.

**Variable para OpenWeather:** el DAG **sentinel360_fase_i_ingesta** usa la tarea de OpenWeather; crea la variable **`openweather_api_key`** (sensitive) en Admin → Variables. **Opcional:** `sentinel360_streaming_mode` = `file` o `kafka` para el DAG de streaming.

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
   - En la interfaz web deberían aparecer los 8 DAGs (filtrar por tag `sentinel360` o por nombre).

3. **Ejecución**
   - Desde la UI: activar el DAG (toggle **On**) y pulsar **Trigger DAG**.
   - Desde CLI (ejemplos):
     - `airflow dags trigger sentinel360_infra_start`
     - `airflow dags trigger sentinel360_infra_stop`
     - `airflow dags trigger sentinel360_fase_i_ingesta`   # requiere variable openweather_api_key
     - `airflow dags trigger sentinel360_fase_ii_preprocesamiento`
     - `airflow dags trigger sentinel360_fase_iii_batch`
     - `airflow dags trigger sentinel360_fase_iii_streaming`
     - `airflow dags trigger sentinel360_dashboards_levantar`   # requiere Docker
     - `airflow dags trigger sentinel360_dashboards_exportar`   # MongoDB + Hive → MariaDB

---

### 5. Orden sugerido de ejecución

1. **sentinel360_infra_start** — Levantar servicios del clúster.
2. **sentinel360_fase_i_ingesta** — Crear temas Kafka y cargar datos (GPS sintético + OpenWeather).
3. **sentinel360_fase_ii_preprocesamiento** — Hive, limpieza, enriquecimiento y grafo.
4. **sentinel360_fase_iii_batch** — Agregados, anomalías y KPIs a MariaDB; opcionalmente **sentinel360_fase_iii_streaming**.
5. **sentinel360_dashboards_levantar** (opcional) — MariaDB + Superset + Grafana con Docker.
6. **sentinel360_dashboards_exportar** — Exportar datos de MongoDB y Hive a MariaDB para Superset y Grafana (ejecutar con MariaDB y dashboards en marcha).

---

### 6. Resumen

- Los DAGs viven en el repositorio en `airflow/`.
- Para que Airflow los vea, deben estar bajo su `dags_folder` (o apuntar `dags_folder` a la carpeta `airflow/` del proyecto).
- Ajusta la ruta del proyecto con la variable `sentinel360_project_dir` en Airflow o editando el `PROJECT_DIR` en los DAGs.

