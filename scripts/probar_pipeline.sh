#!/bin/bash
# Prueba del pipeline Sentinel360 (Fases I verificadas → II → III opcional)
# Uso: ./scripts/probar_pipeline.sh [--skip-hive] [--hasta FASE] [--yes]
#   --skip-hive: no pedir confirmación de tablas Hive
#   --hasta 2|3: solo ejecutar hasta Fase II (2) o III (3). Por defecto hasta 2.
#   --yes: no pedir confirmaciones (modo no interactivo)
#
# Requisitos previos:
#   - HDFS con datos en raw (NiFi o ingest_from_local.sh)
#   - Tablas Hive creadas (./scripts/crear_tablas_hive.sh o beeline -f hive/schema/01_warehouses.sql ...)
#   - YARN y Spark operativos

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_HIVE=false
HASTA=2
YES=false
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-hive) SKIP_HIVE=true; shift ;;
    --hasta) HASTA="$2"; shift 2 ;;
    --yes) YES=true; shift ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
done

echo "=============================================="
echo "  Sentinel360 – Prueba del pipeline"
echo "  Hasta fase: $HASTA  |  Skip Hive: $SKIP_HIVE"
echo "=============================================="
echo ""

# --- Comprobaciones iniciales ---
echo "=== 0. Comprobaciones iniciales ==="
if ! hdfs dfs -test -d /user/hadoop/proyecto/raw 2>/dev/null; then
  echo "[ERROR] No existe /user/hadoop/proyecto/raw. Ejecuta: ./scripts/setup_hdfs.sh y sube datos (ingest_from_local.sh o NiFi)."
  exit 1
fi
RAW_COUNT=$(hdfs dfs -ls /user/hadoop/proyecto/raw 2>/dev/null | grep -c "^-" || true)
echo "[OK] HDFS raw: $RAW_COUNT archivo(s)"
echo ""

if [ "$SKIP_HIVE" = false ] && [ "$YES" = false ]; then
  echo "=== Tablas Hive (opcional) ==="
  echo "Si no las has creado: ./scripts/crear_tablas_hive.sh"
  echo "O: beeline -u 'jdbc:hive2://localhost:10000' -n hadoop -f hive/schema/01_warehouses.sql"
  echo "   (y 02_routes.sql, 03_events_raw.sql, 04_aggregated_reporting.sql)"
  read -p "¿Tablas Hive ya creadas? (s/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[sS]$ ]]; then
    echo "Crea las tablas y vuelve a ejecutar este script."
    exit 0
  fi
fi
echo ""

# --- Fase II: Limpieza ---
echo "=== Fase II.1 – clean_and_normalize.py ==="
./scripts/run_spark_submit.sh spark/cleaning/clean_and_normalize.py
echo ""

# --- Fase II: Enriquecimiento ---
echo "=== Fase II.2 – enrich_with_hive.py ==="
./scripts/run_spark_submit.sh spark/cleaning/enrich_with_hive.py
echo ""

# --- Fase II: Grafo ---
echo "=== Fase II.3 – transport_graph.py ==="
./scripts/run_spark_submit.sh spark/graph/transport_graph.py
echo ""

echo "[OK] Fase II completada. Salidas en HDFS: procesado/cleaned, procesado/enriched, procesado/graph"
echo ""

if [ "$HASTA" -ge 3 ]; then
  echo "=== Fase III – delays_windowed.py (streaming) ==="
  echo "Atención: es un job de streaming (no termina). Para probar en modo batch usa source 'file'."
  echo "Ejemplo: ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file"
  if [ "$YES" = false ]; then
    read -p "¿Ejecutar delays_windowed.py ahora? (s/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[sS]$ ]]; then
      ./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py file
    fi
  else
    echo "Omitido (usa --hasta 3 sin --yes para preguntar)."
  fi
fi

echo ""
echo "=============================================="
echo "  Prueba finalizada"
echo "=============================================="
echo "Comprobar salidas:"
echo "  hdfs dfs -ls /user/hadoop/proyecto/procesado/cleaned"
echo "  hdfs dfs -ls /user/hadoop/proyecto/procesado/enriched"
echo "  hdfs dfs -ls /user/hadoop/proyecto/procesado/graph"
