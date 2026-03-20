#!/usr/bin/env python3
"""
Ver y visualizar los resultados del job de grafos (shortest_paths, connected_components).
Uso:
  python scripts/ver_grafos_resultados.py                    # ver tablas desde resultados/
  python scripts/ver_grafos_resultados.py --viz             # generar grafo.png (requiere networkx, matplotlib)
  python scripts/ver_grafos_resultados.py --hdfs            # leer desde HDFS (requiere pyarrow + HDFS)
"""
import os
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

def main():
    parser = argparse.ArgumentParser(description="Ver resultados Parquet del grafo de transporte")
    parser.add_argument("--hdfs", action="store_true", help="Leer desde HDFS en lugar de resultados/")
    parser.add_argument("--viz", action="store_true", help="Generar imagen del grafo (grafo.png)")
    parser.add_argument("--dir", default="resultados", help="Carpeta local con Parquet (default: resultados)")
    args = parser.parse_args()

    if args.hdfs:
        try:
            import subprocess
            # Copiar desde HDFS a temporal y leer
            base = "/user/hadoop/proyecto/procesado/graph"
            for name in ["shortest_paths", "connected_components"]:
                path = f"{base}/{name}"
                print(f"\n=== {name} (desde HDFS) ===")
                subprocess.run(["hdfs", "dfs", "-cat", f"{path}/*.parquet"], check=False, capture_output=True)
            print("Para ver datos desde HDFS usa: spark-submit con .read.parquet() o beeline.")
            return
        except Exception as e:
            print("HDFS:", e)
            return

    # Leer Parquet locales (resultados/)
    try:
        import pandas as pd
    except ImportError:
        print("Instala pandas y pyarrow: pip install pandas pyarrow")
        return

    dir_path = os.path.join(PROJECT_ROOT, args.dir)
    if os.path.isdir(dir_path):
        parquets = [f for f in os.listdir(dir_path) if f.endswith(".parquet")]
        if parquets:
            print("=== Datos en Parquet (tablas) ===\n")
            for f in sorted(parquets)[:5]:  # máximo 5 archivos
                path = os.path.join(dir_path, f)
                try:
                    df = pd.read_parquet(path)
                    print(f"--- {f} ---")
                    print(df.to_string())
                    print()
                except Exception as e:
                    print(f"{f}: {e}\n")
        elif not args.viz:
            print(f"No hay ficheros .parquet en {dir_path}")
            return
    elif not args.viz:
        print(f"No existe la carpeta {dir_path}. Copia los Parquet desde HDFS:")
        print("  hdfs dfs -get /user/hadoop/proyecto/procesado/graph/shortest_paths/* resultados/")
        print("  hdfs dfs -get /user/hadoop/proyecto/procesado/graph/connected_components/* resultados/")
        return

    if args.viz:
        try:
            import networkx as nx
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("Para --viz instala: pip install networkx matplotlib")
            return

        # Cargar warehouses y routes para dibujar el grafo (desde data/sample si existen)
        wh_path = os.path.join(PROJECT_ROOT, "data", "sample", "warehouses.csv")
        routes_path = os.path.join(PROJECT_ROOT, "data", "sample", "routes.csv")
        if not os.path.isfile(routes_path) or not os.path.isfile(wh_path):
            print("Faltan data/sample/warehouses.csv o routes.csv para --viz")
            return

        wh = pd.read_csv(wh_path)
        routes = pd.read_csv(routes_path)
        G = nx.from_pandas_edgelist(routes, "from_warehouse_id", "to_warehouse_id", edge_attr="distance_km")

        pos = nx.spring_layout(G, seed=42)
        plt.figure(figsize=(10, 8))
        nx.draw_networkx_nodes(G, pos, node_color="lightblue", node_size=800)
        nx.draw_networkx_labels(G, pos, font_size=9)
        nx.draw_networkx_edges(G, pos, edge_color="gray")
        nx.draw_networkx_edge_labels(G, pos, nx.get_edge_attributes(G, "distance_km"))
        plt.title("Grafo de almacenes y rutas (Sentinel360)")
        plt.axis("off")
        out = os.path.join(PROJECT_ROOT, "grafo.png")
        plt.savefig(out, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"\nGrafo guardado en: {out}")


if __name__ == "__main__":
    main()
