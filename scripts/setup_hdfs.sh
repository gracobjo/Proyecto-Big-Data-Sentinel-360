#!/bin/bash
# Crear rutas HDFS para Sentinel360 (clúster: NameNode en 192.168.99.10)
# Uso: ./scripts/setup_hdfs.sh [usuario_hdfs]
# Requiere: HDFS levantado (NameNode) y hdfs en PATH (o HADOOP_HOME/bin)

USER="${1:-hadoop}"
BASE="/user/${USER}/proyecto"

# Asegurar que usamos el NameNode del clúster (configurar fs.defaultFS en core-site.xml)
export HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-/usr/local/hadoop/etc/hadoop}"

# Comprobar que HDFS responde antes de crear directorios
if ! hdfs dfs -ls / >/dev/null 2>&1; then
  echo "ERROR: No se puede conectar a HDFS (NameNode). ¿Está el clúster levantado?"
  echo "Ejecuta antes: ./scripts/start_servicios.sh  (pestaña '0 · Arranque de servicios' en la app)."
  exit 1
fi

for dir in raw procesado/cleaned procesado/enriched procesado/graph procesado/aggregated_delays procesado/temp checkpoints/delays; do
  if hdfs dfs -mkdir -p "${BASE}/${dir}" 2>/dev/null; then
    echo "Creado: ${BASE}/${dir}"
  else
    echo "Fallo al crear: ${BASE}/${dir}"
    exit 1
  fi
done
# Datos maestros
if hdfs dfs -mkdir -p "${BASE}/warehouses" "${BASE}/routes" 2>/dev/null; then
  echo "Creado: ${BASE}/warehouses, ${BASE}/routes"
else
  echo "Fallo al crear warehouses/routes"
  exit 1
fi
hdfs dfs -ls -R "${BASE}"
