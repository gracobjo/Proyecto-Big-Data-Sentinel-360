#!/bin/bash
# Instalación de Grafana en Ubuntu según docs/GRAFANA_DASHBOARDS.md
# Ejecutar en el nodo donde quieras ejecutar Grafana (p. ej. hadoop o nodo con acceso a MariaDB).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Instalación de Grafana para Sentinel360 ==="

# Requiere sudo
if [ "$(id -u)" -ne 0 ]; then
  echo "Este script debe ejecutarse con sudo para instalar paquetes."
  echo "Uso: sudo $0"
  exit 1
fi

# Añadir repositorio oficial de Grafana
apt-get install -y apt-transport-https software-properties-common wget
wget -q -O - https://packages.grafana.com/gpg.key | apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | tee /etc/apt/sources.list.d/grafana.list

# Instalar Grafana
apt-get update
apt-get install -y grafana

# Copiar provisioning (datasources y dashboards)
GRAFANA_PROVISIONING="/etc/grafana/provisioning"
mkdir -p "$GRAFANA_PROVISIONING/datasources"
mkdir -p "$GRAFANA_PROVISIONING/dashboards"
mkdir -p /var/lib/grafana/dashboards/sentinel360

cp -r "$PROJECT_ROOT/grafana/provisioning/datasources/"* "$GRAFANA_PROVISIONING/datasources/" 2>/dev/null || true
cp "$PROJECT_ROOT/grafana/provisioning/dashboards/dashboards.yml" "$GRAFANA_PROVISIONING/dashboards/" 2>/dev/null || true
cp "$PROJECT_ROOT/grafana/dashboards/"*.json /var/lib/grafana/dashboards/sentinel360/ 2>/dev/null || true

chown -R grafana:grafana /var/lib/grafana/dashboards

# Configurar variables de entorno para el datasource MariaDB (provisioning)
# Ajustar según tu entorno: si MariaDB está en localhost o en 192.168.99.10
MARIA_HOST="${MARIA_DB_HOST:-192.168.99.10}"
GRAFANA_ENV="/etc/default/grafana-server"
if [ -f "$GRAFANA_ENV" ]; then
  if ! grep -q "MARIA_DB_HOST" "$GRAFANA_ENV"; then
    {
      echo ""
      echo "# Sentinel360 - conexión a MariaDB para provisioning"
      echo "export MARIA_DB_HOST=$MARIA_HOST"
      echo "export MARIA_DB_PORT=3306"
      echo "export MARIA_DB_USER=sentinel"
      echo "export MARIA_DB_PASSWORD=sentinel_password"
      echo "export MARIA_DB_NAME=sentinel360_analytics"
    } >> "$GRAFANA_ENV"
  fi
else
  echo "Creando $GRAFANA_ENV con variables para Sentinel360..."
  mkdir -p "$(dirname "$GRAFANA_ENV")"
  {
    echo "# Sentinel360 - conexión a MariaDB"
    echo "export MARIA_DB_HOST=$MARIA_HOST"
    echo "export MARIA_DB_PORT=3306"
    echo "export MARIA_DB_USER=sentinel"
    echo "export MARIA_DB_PASSWORD=sentinel_password"
    echo "export MARIA_DB_NAME=sentinel360_analytics"
  } > "$GRAFANA_ENV"
fi

# Arrancar y habilitar
systemctl start grafana-server
systemctl enable grafana-server

echo ""
echo "=== Grafana instalado correctamente ==="
echo "  - URL: http://$(hostname -I | awk '{print $1}'):3000"
echo "  - Usuario/contraseña inicial: admin / admin (cambiar en primer acceso)"
echo "  - Dashboards Sentinel360: en carpeta 'Sentinel360'"
echo ""
echo "Si MariaDB no está en $MARIA_HOST, edita /etc/default/grafana-server"
echo "y reinicia: sudo systemctl restart grafana-server"
echo ""
