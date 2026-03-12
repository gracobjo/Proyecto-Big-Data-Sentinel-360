# Superset – Sentinel360

Apache Superset para dashboards analíticos de Sentinel360 (KPIs por vehículo y almacén).

## Uso con Docker (este proyecto)

Superset está en el `docker-compose` del proyecto. **URL:** http://localhost:8089

### 1. Arrancar

```bash
cd ~/Documentos/ProyectoBigData/docker
docker compose up -d mariadb superset
```

### 2. Primera vez: inicializar BD y usuario administrador

La base de datos interna de Superset debe crearse/actualizarse **antes** de usar la app. Si ves **500** o *"no such table: themes"*, ejecuta desde la raíz del proyecto:

```bash
./scripts/init_superset.sh
```

O manualmente:

```bash
docker exec sentinel360-superset superset db upgrade
docker exec sentinel360-superset superset init
docker exec sentinel360-superset superset fab create-admin \
  --username admin --firstname Admin --lastname User \
  --email admin@localhost --password admin
```

Luego recarga http://localhost:8089 e inicia sesión con **admin / admin**.

### 3. Conectar MariaDB (datos de KPIs)

Desde Superset, los contenedores están en la misma red Docker; MariaDB se alcanza por el nombre del servicio.

**Si la conexión falla**, ejecuta primero el script de verificación (asegura usuario y prueba desde el contenedor Superset):

```bash
./scripts/verificar_conexion_superset_mariadb.sh
```

Luego en Superset:

1. **Settings** (o **Data**) → **Database connections** → **+ Database**.
2. **Supported databases** → **MySQL**.
3. **Connection** (formulario):
   - **Host:** `mariadb`
   - **Port:** `3306`
   - **Username:** `sentinel`
   - **Password:** `sentinel_password`
   - **Database name:** `sentinel360_analytics`
4. Pulsa **Test connection**; si es correcto, se habilitará **Connect**.

En **SQL Alchemy URI** usa siempre **`mysql+pymysql://`** (no solo `mysql://`):

```text
mysql+pymysql://sentinel:sentinel_password@mariadb:3306/sentinel360_analytics
```

**Si sale "Could not load database driver: MySQLEngineSpec"**:

1. **Reconstruir la imagen sin caché** (el Dockerfile instala PyMySQL en el venv de Superset):

   ```bash
   cd ~/Documentos/ProyectoBigData/docker
   docker compose build superset --no-cache
   docker compose up -d superset
   ```

2. **Comprueba la URI**: debe ser exactamente `mysql+pymysql://...` y el nombre de la base **`sentinel360_analytics`** (no `sentinel360`).

3. **Alternativa**: usar la imagen oficial con drivers, `apache/superset:latest-dev` (incluye MySQL). En `docker-compose.yml` cambia la línea `build:` por `image: apache/superset:latest-dev` y quita `context`/`dockerfile`. La URI puede ser `mysql://...` (usa mysqlclient).

### 4. Datasets y dashboards

- Crear **Datasets** desde **Data → Datasets**: tablas `kpi_delays_by_warehouse` y `kpi_delays_by_vehicle`.
- Crear gráficos y dashboards según **docs/SUPERSET_DASHBOARDS.md** (Big Number, barras, time-series, etc.).

Los datos en MariaDB son los mismos que usa Grafana (seed o pipeline con `./scripts/pipeline_to_grafana.sh`).
