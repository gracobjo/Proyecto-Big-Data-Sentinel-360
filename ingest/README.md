# Sentinel360 – Fase I: Ingesta y Selección (KDD)

1. **Fuentes**: NiFi consume API pública (OpenWeather, etc.) y logs GPS simulados en `data/sample/` de Sentinel360.
2. **Streaming**: Publicar en Kafka en temas "Datos Crudos" y "Datos Filtrados".
3. **Registro**: Copia raw en HDFS para auditoría (ruta en `hdfs/paths.txt`).

Con solo Hadoop/Spark/Hive/MongoDB puedes simular la ingesta copiando CSVs/JSONs a HDFS y consumiéndolos con Spark. Ver `scripts/ingest_from_local.sh`.
