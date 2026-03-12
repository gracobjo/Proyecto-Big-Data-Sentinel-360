#!/bin/bash
# Inicializa la BD interna de Superset y crea el usuario admin.
# Ejecutar después de levantar el contenedor por primera vez o si ves error 500 / "no such table: themes".
# Uso: ./scripts/init_superset.sh

set -e
CONTAINER="${SUPERSET_CONTAINER:-sentinel360-superset}"

echo "Inicializando Superset en $CONTAINER..."
echo "1. Migraciones (db upgrade)..."
docker exec "$CONTAINER" superset db upgrade
echo "2. Init (roles y permisos)..."
docker exec "$CONTAINER" superset init
echo "3. Crear usuario admin..."
docker exec "$CONTAINER" superset fab create-admin \
  --username admin --firstname Admin --lastname User \
  --email admin@localhost --password admin
echo ""
echo "Listo. Abre http://localhost:8089 e inicia sesión con: admin / admin"
