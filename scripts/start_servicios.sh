#!/bin/bash
# Arranca los servicios necesarios para el proyecto (Kafka, MongoDB, opcional: Spark History, Hive, NiFi).
# Ejecutar en el nodo master (hadoop, 192.168.99.10) o donde tengas instalados los servicios.
# Rutas por defecto: /usr/local/hadoop, /usr/local/kafka, /usr/local/spark. Ajusta con variables de entorno.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Rutas de instalación (exportar si están en otro sitio)
export HADOOP_HOME="${HADOOP_HOME:-/usr/local/hadoop}"
# Kafka: auto-detectar (incluye ~/software/kafka_2.13-* y Confluent)
if [ -z "$KAFKA_HOME" ] || [ ! -d "$KAFKA_HOME" ]; then
  for d in /usr/local/kafka "$HOME/kafka" /opt/kafka "$HOME/Documentos/ProyectoBigData/kafka" \
           "$HOME/software/kafka_2.13-4.1.1" "$HOME/software/confluent-7.5.0"; do
    [ -d "$d" ] && [ -x "$d/bin/kafka-server-start.sh" ] && export KAFKA_HOME="$d" && break
  done
  # Cualquier kafka_2.* en ~/software
  [ -z "$KAFKA_HOME" ] && for d in "$HOME/software"/kafka_2.*; do
    [ -d "$d" ] && [ -x "$d/bin/kafka-server-start.sh" ] && export KAFKA_HOME="$d" && break
  done
  [ -z "$KAFKA_HOME" ] && command -v kafka-server-start.sh >/dev/null 2>&1 && \
    export KAFKA_HOME="$(cd "$(dirname "$(dirname "$(command -v kafka-server-start.sh)")")" && pwd)"
fi
export KAFKA_HOME="${KAFKA_HOME:-/usr/local/kafka}"
# Spark: usar $HOME/spark si existe y el default no
if [ -z "$SPARK_HOME" ] || [ ! -d "$SPARK_HOME" ]; then
  [ -d "$HOME/spark" ] && [ -x "$HOME/spark/bin/spark-submit" ] && export SPARK_HOME="$HOME/spark"
fi
export SPARK_HOME="${SPARK_HOME:-/usr/local/spark}"
# NiFi: auto-detectar en rutas habituales
if [ -z "$NIFI_HOME" ] || [ ! -d "$NIFI_HOME" ]; then
  for d in /opt/nifi/nifi-2.7.2 /opt/nifi/nifi* /usr/local/nifi "$HOME/nifi" "$HOME/software/nifi"* /opt/nifi; do
    [ -d "$d" ] && [ -x "$d/bin/nifi.sh" ] && export NIFI_HOME="$d" && break
  done
fi
export NIFI_HOME="${NIFI_HOME:-/usr/local/nifi}"
export HIVE_HOME="${HIVE_HOME:-/usr/local/hive}"

RED='\033[0;31m'
VERDE='\033[0;32m'
AMARILLO='\033[1;33m'
NC='\033[0m'
log_ok()   { echo -e "${VERDE}[OK]${NC} $1"; }
log_warn() { echo -e "${AMARILLO}[?]${NC} $1"; }
log_fail() { echo -e "${RED}[FALLO]${NC} $1"; }

# Cargar rutas opcionales (KAFKA_HOME, SPARK_HOME, etc.)
[ -f "$PROJECT_ROOT/config/rutas_servicios.env" ] && . "$PROJECT_ROOT/config/rutas_servicios.env" 2>/dev/null || true

mkdir -p "$PROJECT_ROOT/logs"
echo "=== Arrancando servicios (proyecto: $PROJECT_ROOT) ==="
echo ""

# --- 1. Hadoop (HDFS + YARN) ---
if [ -d "$HADOOP_HOME" ]; then
  if command -v hdfs >/dev/null 2>&1; then
    if hdfs dfs -ls / >/dev/null 2>&1; then
      log_ok "HDFS ya está en marcha"
    else
      log_warn "HDFS no responde. Arrancar con: $HADOOP_HOME/sbin/start-dfs.sh && $HADOOP_HOME/sbin/start-yarn.sh"
    fi
  else
    export PATH="$HADOOP_HOME/bin:$PATH"
    if hdfs dfs -ls / >/dev/null 2>&1; then
      log_ok "HDFS ya está en marcha"
    else
      [ -x "$HADOOP_HOME/sbin/start-dfs.sh" ] && "$HADOOP_HOME/sbin/start-dfs.sh" && log_ok "HDFS arrancado" || log_warn "No se pudo arrancar HDFS"
      [ -x "$HADOOP_HOME/sbin/start-yarn.sh" ] && "$HADOOP_HOME/sbin/start-yarn.sh" && log_ok "YARN arrancado" || log_warn "No se pudo arrancar YARN"
    fi
  fi
else
  log_warn "HADOOP_HOME no encontrado: $HADOOP_HOME"
fi
echo ""

# --- 2. Kafka (clásico con Zookeeper o KRaft) ---
if [ -d "$KAFKA_HOME" ]; then
  if pgrep -f "kafka.Kafka" >/dev/null 2>&1; then
    log_ok "Kafka ya está en marcha"
  else
    KAFKA_CONFIG=""
    [ -f "$KAFKA_HOME/config/kraft/server.properties" ] && KAFKA_CONFIG="$KAFKA_HOME/config/kraft/server.properties"
    [ -z "$KAFKA_CONFIG" ] && [ -f "$KAFKA_HOME/config/server.properties" ] && KAFKA_CONFIG="$KAFKA_HOME/config/server.properties"
    if [ -n "$KAFKA_CONFIG" ]; then
      # Modo clásico (Zookeeper): arrancar Zookeeper antes del broker
      ZK_PROPS="$KAFKA_HOME/config/zookeeper.properties"
      if [ -f "$ZK_PROPS" ] && [ ! -f "$KAFKA_HOME/config/kraft/server.properties" ]; then
        if ! pgrep -f "QuorumPeerMain" >/dev/null 2>&1; then
          nohup "$KAFKA_HOME/bin/zookeeper-server-start.sh" "$ZK_PROPS" >> "$PROJECT_ROOT/logs/zookeeper.log" 2>&1 &
          sleep 4
          log_ok "Zookeeper arrancado"
        fi
      fi
      nohup "$KAFKA_HOME/bin/kafka-server-start.sh" "$KAFKA_CONFIG" >> "$PROJECT_ROOT/logs/kafka.log" 2>&1 &
      sleep 4
      if pgrep -f "kafka.Kafka" >/dev/null 2>&1; then
        log_ok "Kafka arrancado (broker 192.168.99.10:9092)"
      else
        log_warn "Kafka no arrancó. KRaft: formatear con kafka-storage.sh format -t \$(random-uuid) -c $KAFKA_CONFIG. Ver logs/kafka.log"
      fi
    else
      log_warn "No se encontró server.properties en $KAFKA_HOME/config/"
    fi
  fi
else
  log_warn "KAFKA_HOME no encontrado: $KAFKA_HOME (ej: export KAFKA_HOME=$HOME/software/kafka_2.13-4.1.1)"
fi
echo ""

# --- 3. MongoDB (servicio systemd o mongod con --dbpath en el proyecto) ---
if pgrep -x mongod >/dev/null 2>&1; then
  log_ok "MongoDB ya está en marcha"
elif command -v mongod >/dev/null 2>&1; then
  # Directorio de datos si no existe /data/db (evita "Data directory /data/db not found")
  MONGO_DBPATH="${MONGO_DBPATH:-$PROJECT_ROOT/data/mongodb_db}"
  mkdir -p "$MONGO_DBPATH"
  nohup mongod --bind_ip 0.0.0.0 --dbpath "$MONGO_DBPATH" >> "$PROJECT_ROOT/logs/mongodb.log" 2>&1 &
  sleep 2
  pgrep -x mongod >/dev/null 2>&1 && log_ok "MongoDB arrancado (dbpath: $MONGO_DBPATH)" || {
    log_warn "MongoDB no arrancó. Usar servicio: sudo systemctl start mongod  o  mongod --dbpath $MONGO_DBPATH. Ver: tail -20 logs/mongodb.log"
    tail -5 "$PROJECT_ROOT/logs/mongodb.log" 2>/dev/null | sed 's/^/    /'
  }
else
  log_warn "MongoDB no encontrado. Usar: sudo systemctl start mongod"
fi
echo ""

# --- 4. Spark (History Server: requiere directorio de eventos) ---
if [ -d "$SPARK_HOME" ] && [ -x "$SPARK_HOME/sbin/start-history-server.sh" ]; then
  if pgrep -f "HistoryServer" >/dev/null 2>&1; then
    log_ok "Spark History Server ya está en marcha"
  else
    # Crear directorio de eventos (evita FileNotFoundException: file:/tmp/spark-events)
    SPARK_EVENTS_DIR="${SPARK_EVENTS_DIR:-/tmp/spark-events}"
    mkdir -p "$SPARK_EVENTS_DIR" && chmod 1777 "$SPARK_EVENTS_DIR" 2>/dev/null || true
    export SPARK_HOME
    "$SPARK_HOME/sbin/start-history-server.sh" 2>/dev/null && sleep 2
    pgrep -f "HistoryServer" >/dev/null 2>&1 && log_ok "Spark History Server arrancado" || \
    log_warn "History Server falló (¿$SPARK_EVENTS_DIR creado?). Jobs con spark-submit siguen funcionando."
  fi
else
  log_warn "Spark History Server no encontrado en $SPARK_HOME (opcional). Jobs: spark-submit"
fi
echo ""

# --- 5. MariaDB/MySQL (XAMPP - requerido para Hive metastore) ---
LAMPP_DIR="${LAMPP_DIR:-/opt/lampp}"
_mysql_running() { pgrep -f "[m]ysqld" >/dev/null 2>&1 || pgrep -f "[m]ariadbd" >/dev/null 2>&1; }
if _mysql_running; then
  log_ok "MariaDB/MySQL ya está en marcha"
elif [ -x "$LAMPP_DIR/lampp" ]; then
  "$LAMPP_DIR/lampp" startmysql >> "$PROJECT_ROOT/logs/lampp-mysql.log" 2>&1 || true
  sleep 2
  if _mysql_running; then
    log_ok "MariaDB/MySQL (XAMPP) arrancado"
  else
    sudo "$LAMPP_DIR/lampp" startmysql >> "$PROJECT_ROOT/logs/lampp-mysql.log" 2>&1 || true
    sleep 2
    _mysql_running && log_ok "MariaDB/MySQL (XAMPP) arrancado" || \
      log_warn "MariaDB/MySQL no arrancó. Ejecutar: sudo $LAMPP_DIR/lampp startmysql"
  fi
elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled mariadb >/dev/null 2>&1; then
  sudo systemctl start mariadb 2>/dev/null && log_ok "MariaDB (systemd) arrancado" || log_warn "MariaDB: sudo systemctl start mariadb"
else
  log_warn "MariaDB/MySQL no encontrado (Hive metastore lo necesita). XAMPP: sudo $LAMPP_DIR/lampp startmysql"
fi
echo ""

# --- 6. Hive (metastore + opcional hiveserver2) ---
if [ -d "$HIVE_HOME" ] && [ -x "$HIVE_HOME/bin/hive" ]; then
  export PATH="$HIVE_HOME/bin:$PATH"
  if pgrep -f "HiveMetaStore" >/dev/null 2>&1; then
    log_ok "Hive Metastore ya está en marcha"
  else
    nohup hive --service metastore >> "$PROJECT_ROOT/logs/hive-metastore.log" 2>&1 &
    sleep 3
    if pgrep -f "HiveMetaStore" >/dev/null 2>&1; then
      log_ok "Hive Metastore arrancado (logs: logs/hive-metastore.log)"
    else
      log_warn "Hive Metastore no arrancó. Comprobar: tail -20 logs/hive-metastore.log"
    fi
  fi
  if pgrep -f "HiveServer2" >/dev/null 2>&1; then
    log_ok "HiveServer2 ya está en marcha"
  else
    nohup hive --service hiveserver2 >> "$PROJECT_ROOT/logs/hive-hiveserver2.log" 2>&1 &
    sleep 2
    pgrep -f "HiveServer2" >/dev/null 2>&1 && log_ok "HiveServer2 arrancado (logs: logs/hive-hiveserver2.log)" || \
      log_warn "HiveServer2 no arrancó (opcional). Ver: tail logs/hive-hiveserver2.log"
  fi
else
  log_warn "Hive no encontrado en $HIVE_HOME (opcional para enriquecimiento)"
fi

# --- 7. NiFi (opcional) ---
if [ -d "$NIFI_HOME" ] && [ -x "$NIFI_HOME/bin/nifi.sh" ]; then
  "$NIFI_HOME/bin/nifi.sh" status 2>/dev/null | grep -q "Running" && log_ok "NiFi ya está en marcha" || {
    "$NIFI_HOME/bin/nifi.sh" start 2>/dev/null && log_ok "NiFi arrancado" || log_warn "NiFi: $NIFI_HOME/bin/nifi.sh start"
  }
fi

mkdir -p "$PROJECT_ROOT/logs" 2>/dev/null || true
echo ""
echo "=== Resumen ==="
echo "  HDFS/YARN:    $HADOOP_HOME (Web UI ResourceManager: http://192.168.99.10:8088)"
echo "  Kafka:        $KAFKA_HOME (broker: 192.168.99.10:9092)"
echo "  MongoDB:      servicio local (puerto 27017)"
echo "  MariaDB:      XAMPP $LAMPP_DIR (metastore Hive)"
echo "  Spark:        jobs con: ./scripts/run_spark_submit.sh <script.py>"
echo "  Parar todo:   ./scripts/stop_servicios.sh"
