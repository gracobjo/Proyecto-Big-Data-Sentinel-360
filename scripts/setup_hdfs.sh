#!/bin/bash
# Crear rutas HDFS para el proyecto (clúster: NameNode en 192.168.99.10)
# Uso: ./scripts/setup_hdfs.sh [usuario_hdfs]
# Requiere: HADOOP_HOME en PATH o hdfs disponible (ej. /usr/local/hadoop/bin/hdfs)

USER="${1:-hadoop}"
BASE="/user/${USER}/proyecto"

# Asegurar que usamos el NameNode del clúster (configurar fs.defaultFS en core-site.xml)
export HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-/usr/local/hadoop/etc/hadoop}"

for dir in raw procesado/cleaned procesado/enriched procesado/graph procesado/aggregated_delays procesado/temp checkpoints/delays; do
  hdfs dfs -mkdir -p "${BASE}/${dir}"
  echo "Creado: ${BASE}/${dir}"
done
# Datos maestros
hdfs dfs -mkdir -p "${BASE}/warehouses" "${BASE}/routes"
echo "Creado: ${BASE}/warehouses, ${BASE}/routes"
hdfs dfs -ls -R "${BASE}"
