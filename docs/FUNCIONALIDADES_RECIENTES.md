# Sentinel360 – Funcionalidades recientes documentadas

Documentación de las funcionalidades implementadas en las últimas fases: job de grafos, visualización, verificación de tablas Hive y correcciones aplicadas.

---

## 1. Job de grafos (GraphFrames)

- **Script**: `spark/graph/transport_graph.py`
- **Qué hace**: Construye un grafo con nodos = almacenes (`warehouses`) y aristas = rutas (`routes`). Calcula:
  - **shortest_paths**: distancias mínimas desde cada nodo a los landmarks WH-MAD y WH-BCN.
  - **connected_components**: componente conexa asignada a cada nodo (requiere checkpoint en HDFS).
- **Salida**: Parquet en HDFS:
  - `/user/hadoop/proyecto/procesado/graph/shortest_paths`
  - `/user/hadoop/proyecto/procesado/graph/connected_components`
- **Requisitos**: 
  - Driver: `pip install graphframes` (módulo Python en la máquina donde se lanza `spark-submit`).
  - YARN y HDFS en marcha; `--packages graphframes:graphframes:0.8.3-spark3.5-s_2.12` ya está en `run_spark_submit.sh`.
- **Checkpoint**: El script configura `spark.sparkContext.setCheckpointDir` en `/user/hadoop/proyecto/checkpoints/graph` para el algoritmo de componentes conexas.
- **Referencia**: `docs/VISUALIZAR_GRAFOS.md`, `docs/KDD_FASES.md` (Fase II).

---

## 2. Visualización del grafo

- **Grafo**: Red de almacenes (nodos) y rutas entre ellos (aristias con distancia en km). Representa la topología logística de Sentinel360.
- **Script**: `scripts/ver_grafos_resultados.py`
  - Sin opciones: lee los Parquet de la carpeta `resultados/` y muestra las tablas en consola (requiere `pandas`, `pyarrow`).
  - `--viz`: genera `grafo.png` con NetworkX + Matplotlib a partir de `data/sample/warehouses.csv` y `data/sample/routes.csv`.
- **Uso**:
  ```bash
  pip install pandas pyarrow
  python scripts/ver_grafos_resultados.py

  pip install networkx matplotlib
  python scripts/ver_grafos_resultados.py --viz
  ```
- **Documentación**: `docs/VISUALIZAR_GRAFOS.md`.

---

## 3. Verificación de tablas Hive

- **Cómo se pueblan**: Las tablas `transport.warehouses`, `transport.routes` y `transport.events_raw` son EXTERNAL: se “pueblan” con los ficheros que existan en sus rutas HDFS. La tabla `aggregated_delays` la rellenan los jobs Spark (Fase III).
- **Script**: `scripts/verificar_tablas_hive.sh`  
  Ejecuta `COUNT(*)` sobre las cuatro tablas y muestra el número de ficheros en las rutas HDFS asociadas.
- **Documentación**: `docs/POBLAR_TABLAS_HIVE.md`.

---

## 4. Correcciones aplicadas

- **slf4j-api 2.0.7**: El JAR faltaba en `~/.m2/repository/org/slf4j/slf4j-api/2.0.7/`. Se descargó desde Maven Central y se dejó en esa ruta para que la resolución de dependencias de Spark (Ivy) no falle al lanzar el job de grafos.
- **Driver desconectado**: Si el driver (terminal donde se ejecuta `spark-submit`) se cierra o se interrumpe, el Application Master en YARN detecta “Driver terminated or disconnected” y finaliza la aplicación. Solución: mantener la terminal abierta hasta que el job termine o usar `nohup` / `--deploy-mode cluster`.
- **ImportError graphframes**: En el driver debe poder importarse `graphframes` (por ejemplo `pip install graphframes`) además de pasar el JAR con `--packages`.

---

## 5. Resumen de scripts útiles

| Script | Uso |
|--------|-----|
| `scripts/run_spark_submit.sh spark/graph/transport_graph.py` | Ejecutar job de grafos (YARN) |
| `scripts/ver_grafos_resultados.py` | Ver Parquet de resultados en consola |
| `scripts/ver_grafos_resultados.py --viz` | Generar grafo.png |
| `scripts/verificar_tablas_hive.sh` | Comprobar conteos en tablas Hive `transport` |
| `./scripts/ingest_from_local.sh` | Subir warehouses, routes y raw a HDFS (poblar datos para Hive/Spark) |

Consultar **`docs/HOWTO_EJECUCION.md`** para el flujo completo de ejecución por supuestos.
