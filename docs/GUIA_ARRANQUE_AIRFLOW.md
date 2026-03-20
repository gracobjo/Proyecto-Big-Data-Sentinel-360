## Guía de arranque de Airflow en Sentinel360

Esta guía explica:

- cómo **arrancar Airflow** (con o sin entorno virtual),
- cómo **cargar y ejecutar** los DAGs de Sentinel360,
- qué hacer con el **arranque de MariaDB (LAMP/XAMPP)** cuando Airflow no puede pedir contraseña,
- y cómo generar un **reporte descargable** por ejecución (evidencias).

---

### 0) Contexto del proyecto

- Los DAGs viven en `airflow/dag_sentinel360_*.py`.
- El detalle funcional de cada DAG está en `docs/AIRFLOW_DAGS.md`.
- El arranque de Airflow y la carga de DAGs están automatizados con:
  - `scripts/setup_airflow_dags.sh`
  - `scripts/start_airflow.sh`

---

### 1) ¿Airflow se arranca desde un venv?

**Recomendado**: sí, en un **entorno virtual** (venv) dedicado, para aislar dependencias.

Ejemplo (Linux):

```bash
python3 -m venv .venv_airflow
source .venv_airflow/bin/activate
pip install --upgrade pip
pip install apache-airflow
```

> Nota: Airflow requiere dependencias extra según backend/ejecutor. Para una demo local, el modo por defecto (SQLite + LocalExecutor/SequentialExecutor) es suficiente.

Si ya tienes un Airflow instalado en otro venv (por ejemplo `/home/hadoop/mi_proyecto_airflow/venv_airflow/`), el script `scripts/start_airflow.sh` intenta reutilizarlo.

---

### 2) Primera inicialización (solo una vez)

```bash
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"
airflow db init

airflow users create \
  --username admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@localhost \
  --password admin
```

---

### 3) Cargar DAGs de Sentinel360 en Airflow

Opción A (recomendada): Airflow lee DAGs directamente desde el repo.

```bash
bash ./scripts/setup_airflow_dags.sh
```

Esto configura `dags_folder` en `airflow.cfg` apuntando a `./airflow/` del proyecto.

Opción B: copiar DAGs a `$AIRFLOW_HOME/dags` (sin tocar `airflow.cfg`):

```bash
bash ./scripts/setup_airflow_dags.sh --copy
```

---

### 4) Arrancar Airflow (scheduler + UI)

```bash
bash ./scripts/start_airflow.sh
```

- UI: `http://localhost:8080`
- Si el puerto está ocupado: `AIRFLOW_PORT=8081 bash ./scripts/start_airflow.sh`

---

### 5) Configuración mínima en Airflow (Variables)

En la UI de Airflow: **Admin → Variables**:

- **`sentinel360_project_dir`**: ruta absoluta al repo en la máquina donde corre Airflow (ej. `/home/hadoop/Documentos/ProyectoBigData`).
- **`openweather_api_key`**: API key para ingesta de OpenWeather (si se usa el DAG de Fase I con OpenWeather).
- (opcional) **`sentinel360_streaming_mode`**: `file` o `kafka` (para el DAG de streaming).

---

### 6) MariaDB (LAMP/XAMPP) y por qué “pide contraseña”

En este proyecto, **MariaDB/MySQL** es necesario para el **metastore de Hive** y en algunos entornos se gestiona con **LAMP/XAMPP** (típicamente `sudo /opt/lampp/lampp startmysql`).

Problema: en Airflow, una tarea `BashOperator` **no puede introducir la contraseña** si el comando hace `sudo` interactivo, así que el DAG se queda bloqueado/falla.

Solución aplicada:

- El DAG `sentinel360_infra_start` lanza `start_servicios.sh` en modo no interactivo:
  - `SENTINEL360_SKIP_SUDO_STARTS=1`
- En ese modo, el script **no intenta** `sudo ... startmysql`/`sudo systemctl start ...` y muestra un aviso indicando el comando manual.

**Arranque manual (cuando uses LAMP/XAMPP):**

```bash
sudo /opt/lampp/lampp startmysql
```

> Alternativa “pro”: configurar sudoers con `NOPASSWD` para el comando concreto (solo si tu entorno lo permite).

---

### 7) Cómo ejecutar DAGs (UI y CLI)

**Desde UI**:

- Activa el DAG (toggle **On**) y pulsa **Trigger DAG**.

**Desde CLI**:

```bash
airflow dags trigger sentinel360_infra_start
airflow dags trigger sentinel360_fase_I_ingesta
airflow dags trigger sentinel360_fase_II_preprocesamiento
airflow dags trigger sentinel360_fase_III_batch
airflow dags trigger sentinel360_dashboards_exportar
```

---

### 8) Orden recomendado de ejecución (demo)

1. `sentinel360_infra_start`
2. `sentinel360_fase_I_ingesta`
3. `sentinel360_fase_II_preprocesamiento`
4. `sentinel360_fase_III_batch` (y opcional `sentinel360_fase_III_streaming`)
5. (opcional) `sentinel360_dashboards_levantar` (Docker)
6. `sentinel360_dashboards_exportar`

---

### 9) Reporte descargable por ejecución (evidencias)

Cada DAG de Sentinel360 termina con una tarea final llamada **`reporte_ejecucion`** que genera un reporte en disco con:

- estado final del DAG,
- lista de tareas y estado (`success`, `failed`, `skipped`, etc.),
- timestamps básicos.

Se guarda en:

- `reports/airflow/<dag_id>/LATEST.md` (último reporte “estable”)
- `reports/airflow/<dag_id>/<run_id>_*.md` (histórico por ejecución)

Así puedes **descargar/adjuntar** el reporte en la memoria o como evidencia de ejecución paso a paso.

---

### 10) Validación operativa recomendada para Fase II

Cuando ejecutes `sentinel360_fase_II_preprocesamiento`, valida el éxito técnico en este orden:

1. **Airflow reportes**
   - `reports/airflow/sentinel360_fase_II_preprocesamiento/LATEST.md`
   - (compatibilidad) `reports/airflow/sentinel360_fase_ii_preprocesamiento/LATEST.md`
2. **HDFS procesado**
   - `/user/hadoop/proyecto/procesado/cleaned`
   - `/user/hadoop/proyecto/procesado/enriched`
3. **Logs locales**
   - `reports/logs/` (si guardaste ejecuciones Spark manuales)

Comandos útiles:

```bash
sed -n '1,80p' reports/airflow/sentinel360_fase_II_preprocesamiento/LATEST.md 2>/dev/null || \
sed -n '1,80p' reports/airflow/sentinel360_fase_ii_preprocesamiento/LATEST.md

hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned
hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched
hdfs dfs -du -h /user/hadoop/proyecto/procesado/cleaned
hdfs dfs -du -h /user/hadoop/proyecto/procesado/enriched

ls -lt reports/logs 2>/dev/null | head -8
```

Si en HDFS aparecen `_SUCCESS` y `part-*.parquet`, considera la fase validada aunque Airflow muestre algún run histórico en estado inconsistente.
