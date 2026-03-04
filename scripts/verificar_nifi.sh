#!/bin/bash
# Comprueba si NiFi está instalado y opcionalmente si está en marcha.
# Ejecutar desde la raíz del proyecto o: bash scripts/verificar_nifi.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
VERDE='\033[0;32m'
AMARILLO='\033[1;33m'
NC='\033[0m'
ok()   { echo -e "${VERDE}[OK]${NC} $1"; }
warn() { echo -e "${AMARILLO}[?]${NC} $1"; }
fail() { echo -e "${RED}[FALLO]${NC} $1"; }

echo "=== Comprobación de NiFi ==="
echo ""

# Buscar NIFI_HOME en rutas habituales
NIFI_HOME="${NIFI_HOME:-}"
if [ -z "$NIFI_HOME" ] || [ ! -d "$NIFI_HOME" ]; then
  for d in /opt/nifi/nifi-2.7.2 /opt/nifi/nifi* /usr/local/nifi "$HOME/nifi" "$HOME/software/nifi"* /opt/nifi; do
    [ -d "$d" ] && [ -x "$d/bin/nifi.sh" ] && NIFI_HOME="$d" && break
  done
fi

if [ -z "$NIFI_HOME" ] || [ ! -d "$NIFI_HOME" ]; then
  fail "NiFi no encontrado. Rutas probadas: /usr/local/nifi, \$HOME/nifi, \$HOME/software/nifi*, /opt/nifi"
  echo "  Si está en otra ruta: export NIFI_HOME=/ruta/nifi y vuelve a ejecutar."
  exit 1
fi

ok "NiFi encontrado: $NIFI_HOME"

if [ -x "$NIFI_HOME/bin/nifi.sh" ]; then
  ok "nifi.sh disponible"
else
  fail "No se encuentra $NIFI_HOME/bin/nifi.sh"
  exit 1
fi

# Estado del servicio
if "$NIFI_HOME/bin/nifi.sh" status 2>/dev/null | grep -q "Running"; then
  ok "NiFi está en marcha"
  # Puerto por defecto 8443 (HTTPS) o 8080 (HTTP)
  if command -v nc >/dev/null 2>&1; then
    nc -z -w2 127.0.0.1 8443 2>/dev/null && echo "  UI HTTPS: https://127.0.0.1:8443/nifi (o https://192.168.99.10:8443/nifi)" || true
    nc -z -w2 127.0.0.1 8080 2>/dev/null && echo "  UI HTTP:  http://127.0.0.1:8080/nifi" || true
  fi
else
  warn "NiFi no está corriendo. Arrancar: $NIFI_HOME/bin/nifi.sh start"
  echo "  O usar: ./scripts/start_servicios.sh (con NIFI_HOME=$NIFI_HOME)"
fi

echo ""
echo "Para la ingesta (Fase I) necesitas dos flujos en NiFi:"
echo "  1. GPS ficticios: leer archivos de data/sample/ (o carpeta vigilada) → Kafka (raw-data) + HDFS (raw)"
echo "  2. HTTP: InvokeHTTP (ej. OpenWeather) → Kafka + HDFS"
echo "  Ver: ingest/nifi/README.md"
