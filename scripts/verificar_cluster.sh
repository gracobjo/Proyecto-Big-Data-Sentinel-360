#!/bin/bash
# Comprueba que el clúster esté listo para ejecutar el proyecto.
# Puede ejecutarse desde la raíz del proyecto o desde scripts/.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MASTER_IP="${MASTER_IP:-192.168.99.10}"
RED='\033[0;31m'
VERDE='\033[0;32m'
AMARILLO='\033[1;33m'
NC='\033[0m'

ok()  { echo -e "${VERDE}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FALLO]${NC} $1"; return 1; }
warn() { echo -e "${AMARILLO}[?]${NC} $1"; }

echo "Proyecto: $PROJECT_ROOT"
echo ""

echo "=== 1. Conectividad (ping a nodos) ==="
ping -c 1 -W 2 "$MASTER_IP" >/dev/null 2>&1 && ok "Master $MASTER_IP" || fail "No se alcanza master $MASTER_IP"
ping -c 1 -W 2 192.168.99.12 >/dev/null 2>&1 && ok "nodo1 192.168.99.12" || warn "nodo1 no alcanzable"
ping -c 1 -W 2 192.168.99.14 >/dev/null 2>&1 && ok "nodo2 192.168.99.14" || warn "nodo2 no alcanzable"

echo ""
echo "=== 2. HDFS (NameNode y rutas del proyecto) ==="
if command -v hdfs >/dev/null 2>&1; then
  hdfs dfs -ls / >/dev/null 2>&1 && ok "HDFS accesible" || fail "HDFS no responde (revisar fs.defaultFS en core-site.xml)"
  hdfs dfs -ls /user/hadoop/proyecto >/dev/null 2>&1 && ok "Ruta /user/hadoop/proyecto existe" || warn "Ejecuta: ./scripts/setup_hdfs.sh"
else
  warn "Comando 'hdfs' no encontrado (¿HADOOP_HOME/bin en PATH?)"
fi

echo ""
echo "=== 3. YARN (ResourceManager) ==="
if command -v yarn >/dev/null 2>&1; then
  yarn node -list >/dev/null 2>&1 && ok "YARN accesible (nodemanagers listados)" || fail "YARN no responde"
else
  warn "Comando 'yarn' no encontrado"
fi

echo ""
echo "=== 4. Kafka (broker en master) ==="
if command -v nc >/dev/null 2>&1; then
  nc -z -w2 "$MASTER_IP" 9092 2>/dev/null && ok "Kafka 192.168.99.10:9092 escuchando" || warn "Puerto 9092 no abierto (Kafka no levantado o en otro puerto)"
else
  warn "nc no disponible; comprobar Kafka a mano: telnet $MASTER_IP 9092"
fi

echo ""
echo "=== 5. Spark (spark-submit y config) ==="
if command -v spark-submit >/dev/null 2>&1; then
  ok "spark-submit encontrado"
  [ -f "config.py" ] && ok "config.py en raíz del proyecto" || fail "Ejecuta este script desde la raíz del proyecto (donde está config.py)"
else
  warn "spark-submit no encontrado (¿SPARK_HOME/bin en PATH?)"
fi

echo ""
echo "=== 6. Hive (opcional) ==="
if command -v hive >/dev/null 2>&1; then
  ok "Hive CLI disponible"
else
  warn "Hive no en PATH (necesario para enrich y tablas agregadas)"
fi

echo ""
echo "=== 7. Datos de prueba ==="
[ -f "data/sample/warehouses.csv" ] && ok "data/sample/warehouses.csv" || warn "Falta warehouses.csv en data/sample/"
[ -f "data/sample/routes.csv" ]    && ok "data/sample/routes.csv"    || warn "Falta routes.csv en data/sample/"
[ -f "data/sample/gps_events.csv" ] && ok "data/sample/gps_events.csv"  || warn "Genera datos: python data/sample/generate_gps_logs.py"

echo ""
echo "=== 8. NiFi (ingesta GPS + HTTP) ==="
NIFI_HOME="${NIFI_HOME:-}"
for d in /opt/nifi/nifi-2.7.2 /opt/nifi/nifi* /usr/local/nifi "$HOME/nifi" "$HOME/software/nifi"* /opt/nifi; do
  [ -d "$d" ] && [ -x "$d/bin/nifi.sh" ] && NIFI_HOME="$d" && break
done
if [ -n "$NIFI_HOME" ] && [ -x "$NIFI_HOME/bin/nifi.sh" ]; then
  ok "NiFi encontrado: $NIFI_HOME"
  "$NIFI_HOME/bin/nifi.sh" status 2>/dev/null | grep -q "Running" && ok "NiFi en marcha (UI: http://localhost:8080/nifi)" || warn "NiFi no está corriendo: $NIFI_HOME/bin/nifi.sh start"
else
  warn "NiFi no encontrado. Ingesta alternativa: ./scripts/ingest_from_local.sh. Ver ingest/nifi/README.md"
fi

echo ""
echo "=== Resumen ==="
echo "Ingesta: ./scripts/ingest_from_local.sh  o  flujos NiFi (ingest/nifi/README.md)"
echo "  1. ./scripts/setup_hdfs.sh"
echo "  2. Generar GPS: python data/sample/generate_gps_logs.py"
echo "  3. Ingesta: NiFi (GPS+HTTP) o ./scripts/ingest_from_local.sh"
echo "  4. hive -f hive/schema/01_warehouses.sql   (y 02, 03, 04)"
echo "  5. ./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py"
echo "  6. ./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py"
echo "  7. ./scripts/run_spark_submit.sh spark/graph/transport_graph.py"
