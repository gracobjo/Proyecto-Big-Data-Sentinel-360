# HDFS - Rutas del proyecto (clúster)

NameNode: **hdfs://192.168.99.10:9000**

| Ruta | Descripción |
|------|-------------|
| `/user/hadoop/proyecto/raw` | Datos crudos (auditoría) desde NiFi/Kafka o ingest_from_local.sh |
| `/user/hadoop/proyecto/procesado/cleaned` | Salida limpieza Spark |
| `/user/hadoop/proyecto/procesado/enriched` | Salida enriquecimiento Spark |
| `/user/hadoop/proyecto/procesado/graph` | Shortest paths y connected components (GraphFrames) |
| `/user/hadoop/proyecto/procesado/aggregated_delays` | Agregados por ventana para Hive |
| `/user/hadoop/proyecto/warehouses` | Datos maestros almacenes |
| `/user/hadoop/proyecto/routes` | Datos maestros rutas |
| `/user/hadoop/proyecto/checkpoints/delays` | Checkpoint Structured Streaming |

Crear todas: `./scripts/setup_hdfs.sh`
