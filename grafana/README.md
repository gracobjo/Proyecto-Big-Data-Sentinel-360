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
- **MariaDB** en el host: puerto **3307** (no 3306), para que los scripts del pipeline (`pipeline_to_grafana.sh`, etc.) conecten al contenedor sin chocar con un MySQL del host.
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

Requiere que las tablas `kpi_delays_by_vehicle` y `kpi_delays_by_warehouse` existan en `sentinel360_analytics` y tengan datos.

**Por qué los paneles muestran "No data"**  
Grafana lee de MariaDB (la misma del contenedor, por red interna). Comprueba en este orden:  
1. **Datos en MariaDB**: demo con `./scripts/seed_kpi_demo_via_docker.sh` o pipeline con `./scripts/pipeline_to_grafana.sh`.  
2. **Datasource en Grafana**: Configuration → Data sources → "Sentinel360 MariaDB" → **Save & test** (debe salir en verde).  
3. **Reiniciar Grafana** para que recargue el provisioning: `docker compose -f docker/docker-compose.yml restart grafana`.  
4. **Reset completo** si sigue fallando: `docker compose -f docker/docker-compose.yml down grafana && docker volume rm docker_grafana_data 2>/dev/null; docker compose -f docker/docker-compose.yml up -d grafana` (borra dashboards/config que hayas cambiado a mano).

**Cómo generar datos para los KPIs**

1. **Datos de demo (rápido)**  
   Crear las tablas en MariaDB y rellenarlas con datos de ejemplo.

   **Si usas Docker** (recomendado; evita problemas de conexión desde el host). **Ejecuta desde la raíz del proyecto** (`~/Documentos/ProyectoBigData`), no desde `docker/`:
   ```bash
   cd ~/Documentos/ProyectoBigData

   # Crear tablas (una vez)
   docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql

   # Insertar datos de ejemplo
   ./scripts/seed_kpi_demo_via_docker.sh
   ```

   **Si MariaDB está en el host** (localhost):
   ```bash
   pip install pymysql sqlalchemy pandas
   python scripts/seed_kpi_demo_data.py
   ```
   Después, en Grafana elige un intervalo de tiempo (p. ej. "Last 7 days") y recarga los paneles.

2. **Datos reales (pipeline → Grafana)**  
   La información que ve Grafana debe venir del pipeline: NiFi/Kafka → Spark → MongoDB → MariaDB.

   **Flujo** (comandos desde la **raíz del proyecto**, `cd ~/Documentos/ProyectoBigData`):
   1. **Pipeline** genera datos en MongoDB: ejecutar los jobs Spark (p. ej. `delays_windowed.py` o batch que escriba en `transport.aggregated_delays`).
   2. **Crear tablas** en MariaDB (una vez):  
      `docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql`
   3. **Llevar datos a MariaDB** (MariaDB Docker en puerto **3307**):
      ```bash
      ./scripts/pipeline_to_grafana.sh
      ```
      Ese script usa `mongo_to_mariadb_kpi.py` con `MARIA_DB_PORT=3307` para conectar al MariaDB del contenedor.
   4. **Grafana** lee de esa misma MariaDB (por red interna Docker, `mariadb:3306`). Recarga el dashboard.

   Si `mongo_to_mariadb_kpi.py` espera columnas distintas a las que escribe tu job Spark, hay que adaptar el script o el esquema en MongoDB.

## ¿Se actualiza el panel con datos reales?

Sí. El dashboard tiene **Refresh 30s**: cada 30 segundos Grafana vuelve a consultar MariaDB. Si en MariaDB hay datos nuevos (porque has ejecutado `pipeline_to_grafana.sh` o porque un proceso los escribe ahí), los paneles se actualizan solos en el siguiente ciclo.

**Cómo arrancar el flujo y comprobarlo:**

1. **Levantar servicios** (Docker + lo que use tu pipeline):
   ```bash
   cd ~/Documentos/ProyectoBigData/docker
   docker compose up -d mariadb grafana
   ```
   Si tu pipeline usa clúster (HDFS, YARN, Kafka, MongoDB en 192.168.99.10), arranca también esos servicios.

2. **Generar datos en MongoDB** (uno de estos):
   - **Streaming**: `./scripts/run_spark_submit.sh spark/streaming/delays_windowed.py kafka` (con NiFi/Kafka enviando datos).
   - **Batch**: job que escriba agregados en `transport.aggregated_delays` (Hive o MongoDB), o usar datos de prueba que rellenen esa colección.

3. **Llevar MongoDB → MariaDB** (desde la raíz del proyecto):
   ```bash
   cd ~/Documentos/ProyectoBigData
   ./scripts/pipeline_to_grafana.sh
   ```

4. **Comprobar en Grafana**: abre http://localhost:3000, entra en el dashboard "Sentinel360 – KPIs…". En unos 30 s deberías ver los nuevos datos. Puedes forzar una actualización con el botón de refresco (o cambiando el rango de tiempo).

**Para actualización continua:** ejecuta `pipeline_to_grafana.sh` de forma periódica (p. ej. cada 5 min con cron), o integra ese paso en tu DAG de Airflow para que los KPIs se vuelquen a MariaDB tras cada ejecución del pipeline.

## Paneles adicionales (MongoDB)

Los paneles de "Estado actual de la flota" y "Anomalías detectadas" descritos en `docs/GRAFANA_DASHBOARDS.md` requieren un datasource MongoDB. Grafana no incluye MongoDB nativamente; puede usarse un plugin o backend intermedio. Para la demo principal, el dashboard de KPIs (MariaDB) es suficiente.
