## Ejecutar Sentinel360 en GitHub Actions (demo finita)

Este proyecto incluye un workflow para ejecutar una corrida **finita** del pipeline en un runner de GitHub Actions, sin depender de Grafana/Superset.

### Qué ejecuta

Workflow: `.github/workflows/sentinel360_pipeline_demo.yml`

- Levanta **MongoDB** como servicio (contenedor).
- Genera un `config.py` **temporal** (solo dentro del runner) para ejecutar en **modo local**:
  - `SPARK_MASTER = local[*]`
  - rutas de entrada desde `data/sample`
  - Hive metastore local (Spark + Derby)
- Crea la tabla Hive local `default.aggregated_delays`.
- Ejecuta:
  - Limpieza (Fase II): `spark/cleaning/clean_and_normalize.py`
  - Streaming (Fase III) en modo `file` con **timeout** (para que sea finito): `spark/streaming/delays_windowed.py`
  - Anomalías K‑Means (Fase III batch): `spark/ml/anomaly_detection.py`
- Verifica que existen agregados en MongoDB (`transport.aggregated_delays`).

### Cómo lanzarlo

1. Ve a la pestaña **Actions** del repositorio.
2. Selecciona **“Sentinel360 - Pipeline demo (finite)”**.
3. Pulsa **Run workflow**.

Al terminar:

- Revisa los logs del job para ver el orden de ejecución y los contadores insertados en MongoDB.

### Nota importante

Este workflow **no modifica tu repositorio**: el `config.py` se reemplaza **solo dentro del runner** y se restaura al final del job.

