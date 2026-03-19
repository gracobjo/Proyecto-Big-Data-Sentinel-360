#!/bin/bash
# Arranca MariaDB/MySQL (XAMPP o systemd) y espera a que el puerto 3306 acepte conexiones.
# Uso: ./scripts/start_mariadb.sh
# Para Hive Metastore y DAGs que usan MariaDB. Ejecutar antes de sentinel360_infra_start si 3306 no está listo.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT/logs"

LAMPP_DIR="${LAMPP_DIR:-/opt/lampp}"

_mysql_listen() { command -v nc >/dev/null 2>&1 && nc -z -w2 localhost 3306 2>/dev/null; }
_wait_port() {
  local i=0 max=20
  while [ $i -lt $max ]; do
    _mysql_listen && return 0
    sleep 3
    i=$((i + 1))
  done
  return 1
}

if _mysql_listen; then
  echo "[OK] MariaDB/MySQL ya escucha en localhost:3306"
  exit 0
fi

# Intentar XAMPP
if [ -x "$LAMPP_DIR/lampp" ]; then
  echo "Arrancando MySQL (XAMPP $LAMPP_DIR)..."
  sudo "$LAMPP_DIR/lampp" startmysql >> "$PROJECT_ROOT/logs/lampp-mysql.log" 2>&1 || \
    "$LAMPP_DIR/lampp" startmysql >> "$PROJECT_ROOT/logs/lampp-mysql.log" 2>&1 || true
  if _wait_port; then
    echo "[OK] MariaDB/MySQL (XAMPP) listo en 3306"
    exit 0
  fi
fi

# Intentar systemd
if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-enabled mariadb >/dev/null 2>&1 || systemctl is-enabled mysql >/dev/null 2>&1; then
    echo "Arrancando MariaDB (systemd)..."
    sudo systemctl start mariadb 2>/dev/null || sudo systemctl start mysql 2>/dev/null || true
    if _wait_port; then
      echo "[OK] MariaDB (systemd) listo en 3306"
      exit 0
    fi
  fi
fi

echo "[?] MariaDB/MySQL no responde en 3306. Comprobar: sudo $LAMPP_DIR/lampp startmysql  o  sudo systemctl start mariadb"
exit 1
