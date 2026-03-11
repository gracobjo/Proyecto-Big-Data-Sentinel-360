# Grafana – Sentinel360

Configuración de provisioning para dashboards de monitorización Sentinel360.

## Estructura

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── datasources.yml    # Datasource MariaDB (sentinel360_analytics)
│   └── dashboards/
│       └── dashboards.yml     # Proveedor de dashboards
├── dashboards/
│   └── sentinel360-kpis.json  # Dashboard de KPIs por almacén
└── README.md
```

## Uso con Docker

Con `docker compose` en la carpeta `docker/`:

```bash
cd docker
docker compose up -d grafana mariadb
```

- **URL**: http://localhost:3000
- **Usuario/contraseña**: admin / admin (configurable vía `GF_SECURITY_*`)
- Los dashboards se cargan automáticamente en la carpeta **Sentinel360**
- El datasource MariaDB se conecta al servicio `mariadb` del compose

## Instalación nativa (Ubuntu)

```bash
sudo MARIA_DB_HOST=192.168.99.10 ./scripts/install_grafana.sh
```

Ajusta `MARIA_DB_HOST` según la IP de tu servidor MariaDB.

## Dashboard incluido

**Sentinel360 – KPIs por ruta y almacén** (Panel 3 del documento):

- **Retraso medio por almacén**: gráfico de barras
- **Retraso medio en el tiempo**: series temporales
- **Tabla de KPIs por almacén**: ventanas, viajes, retrasos

Requiere que las tablas `kpi_delays_by_vehicle` y `kpi_delays_by_warehouse` existan en `sentinel360_analytics` y estén pobladas (p. ej. con `scripts/mongo_to_mariadb_kpi.py`).

## Paneles adicionales (MongoDB)

Los paneles de "Estado actual de la flota" y "Anomalías detectadas" descritos en `docs/GRAFANA_DASHBOARDS.md` requieren un datasource MongoDB. Grafana no incluye MongoDB nativamente; puede usarse un plugin o backend intermedio. Para la demo principal, el dashboard de KPIs (MariaDB) es suficiente.
