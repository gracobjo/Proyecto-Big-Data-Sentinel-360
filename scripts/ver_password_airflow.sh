#!/bin/bash
# Muestra la contraseña de Airflow (usuario admin).
# - Si existe simple_auth_manager_passwords.json.generated, muestra su contenido.
# - Si no, recuerda que el usuario por defecto es admin / admin (creado con airflow users create).

export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"
PASSFILE="$AIRFLOW_HOME/simple_auth_manager_passwords.json.generated"

echo "AIRFLOW_HOME: $AIRFLOW_HOME"
echo ""

if [ -f "$PASSFILE" ]; then
  echo "=== Contraseñas (Simple auth manager) ==="
  cat "$PASSFILE"
else
  echo "No existe $PASSFILE"
  echo ""
  echo "Usuario por defecto (si lo creaste con la doc):"
  echo "  Username: admin"
  echo "  Password: admin"
  echo ""
  echo "Para crear/resetear el usuario:"
  echo "  airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@localhost --password admin"
  echo "  (Si el usuario ya existe, usa 'airflow users reset-password -u admin' para cambiar la contraseña)"
fi
