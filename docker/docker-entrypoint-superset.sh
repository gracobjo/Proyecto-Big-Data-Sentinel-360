#!/bin/sh
# Ejecutar como root para poder escribir en /app/.venv; el servidor se lanza como superset.
# El venv no tiene pip; instalar en site-packages del venv con pip del sistema.
set -e
SITEPACKAGES="$(/app/.venv/bin/python3 -c 'import sys; print(f"/app/.venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")')"
/usr/local/bin/pip install --no-cache-dir --target "$SITEPACKAGES" pymysql mysqlclient 2>/dev/null || true
exec /usr/sbin/runuser -u superset -- "$@"
