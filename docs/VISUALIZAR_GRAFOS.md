# Cómo visualizar los resultados del grafo (Sentinel360)

Los resultados del job **transport_graph.py** son dos tablas en formato Parquet:

- **shortest_paths**: distancia mínima desde cada nodo a WH-MAD y WH-BCN.
- **connected_components**: componente conexa (id) asignada a cada nodo.

---

## 1. Ver los datos (tablas)

### Opción A: Desde la carpeta local `resultados/`

Si copiaste los Parquet a `resultados/`:

```bash
cd ~/Documentos/ProyectoBigData
pip install pandas pyarrow   # si no los tienes
python scripts/ver_grafos_resultados.py
```

Muestra el contenido de los Parquet en consola.

### Opción B: Desde HDFS con Spark (Beeline no lee Parquet directo)

```bash
cd ~/Documentos/ProyectoBigData
pyspark --master "local[*]" --packages graphframes:graphframes:0.8.3-spark3.5-s_2.12
```

En la sesión de PySpark:

```python
from config import HDFS_GRAPH_PATH
spark.conf.set("spark.hadoop.fs.defaultFS", "hdfs://192.168.99.10:9000")

paths = spark.read.parquet(HDFS_GRAPH_PATH + "/shortest_paths")
paths.show()

cc = spark.read.parquet(HDFS_GRAPH_PATH + "/connected_components")
cc.show()
```

### Opción C: Copiar Parquet a local y abrirlos

```bash
hdfs dfs -get /user/hadoop/proyecto/procesado/graph/shortest_paths resultados/shortest_paths
hdfs dfs -get /user/hadoop/proyecto/procesado/graph/connected_components resultados/connected_components
```

Luego en Python (o en un notebook):

```python
import pandas as pd
df1 = pd.read_parquet("resultados/shortest_paths")
df2 = pd.read_parquet("resultados/connected_components")
print(df1)
print(df2)
```

---

## 2. Dibujar el grafo (nodos y aristas)

El script puede generar una imagen del grafo (almacenes = nodos, rutas = aristas) si tienes `data/sample/warehouses.csv` y `routes.csv`:

```bash
pip install networkx matplotlib
python scripts/ver_grafos_resultados.py --viz
```

Genera **grafo.png** en la raíz del proyecto.

---

## 3. Resumen de columnas

| Parquet             | Columnas típicas |
|---------------------|-------------------|
| **shortest_paths**  | `id` (nodo), `distance` a WH-MAD, `distance` a WH-BCN |
| **connected_components** | `id` (nodo), `component` (id de la componente conexa) |

Así puedes **visualizar** tanto los datos (tablas) como el grafo (imagen).
