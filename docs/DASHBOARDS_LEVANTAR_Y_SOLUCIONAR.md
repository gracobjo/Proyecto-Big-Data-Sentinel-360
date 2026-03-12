# Dashboards Sentinel360: cómo levantar y solucionar fallos

Guía para arrancar **Superset** y **Grafana** en este proyecto y resolver los problemas más habituales.

---

## 1. Qué hay que tener levantado

Los dashboards usan **MariaDB** como base de datos analítica (`sentinel360_analytics`). Superset y Grafana se ejecutan en Docker y se conectan a MariaDB por la red interna del compose.

| Servicio   | URL (desde el host) | Contenedor          |
|-----------|----------------------|---------------------|
| MariaDB   | `localhost:3307`     | `sentinel360-mariadb` |
| Superset  | http://localhost:8089 | `sentinel360-superset` |
| Grafana   | http://localhost:3000 | `sentinel360-grafana`  |

---

## 2. Levantar todo con Docker

Desde la raíz del proyecto:

```bash
cd docker
docker compose up -d mariadb superset grafana
```

O solo lo que necesites:

```bash
docker compose up -d mariadb superset   # Solo Superset
docker compose up -d mariadb grafana    # Solo Grafana
```

**Primera vez con Superset:** la base de datos interna de Superset (SQLite) debe inicializarse. Si al abrir http://localhost:8089 ves **error 500** o *"no such table: themes"*, sigue la sección [3. Solución: error 500 en Superset](#3-solución-error-500-en-superset).

---

## 3. Solución: error 500 en Superset

**Síntoma:** al abrir http://localhost:8089 aparece *"Internal server error"* (500) o en los logs: `no such table: themes`.

**Causa:** la base de datos interna de Superset no está creada o actualizada (sobre todo tras crear el contenedor por primera vez o tras un rebuild).

**Qué hacer** (desde la raíz del proyecto):

```bash
./scripts/init_superset.sh
```

Ese script ejecuta:

1. `superset db upgrade` – crea/actualiza tablas internas
2. `superset init` – roles y permisos
3. `superset fab create-admin` – usuario **admin** con contraseña **admin**

Luego recarga http://localhost:8089 e inicia sesión con **admin / admin**.

Si no usas el script, puedes ejecutar los comandos a mano:

```bash
docker exec sentinel360-superset superset db upgrade
docker exec sentinel360-superset superset init
docker exec sentinel360-superset superset fab create-admin \
  --username admin --firstname Admin --lastname User \
  --email admin@localhost --password admin
```

---

## 4. Solución: Superset no conecta a MariaDB (driver o conexión)

### 4.1 Error "Could not load database driver: MySQLEngineSpec"

**Síntoma:** al añadir la base de datos en Superset aparece *"Could not load database driver: MySQLEngineSpec"*.

**Causa:** en la imagen *lean* de Superset no viene el driver MySQL; el proyecto lo instala en el venv mediante un Dockerfile y un entrypoint.

**Qué hacer:**

1. Reconstruir la imagen sin caché y levantar de nuevo:

   ```bash
   cd docker
   docker compose build superset --no-cache
   docker compose up -d superset
   ```

2. En Superset, usar siempre la URI con **`mysql+pymysql://`** (no solo `mysql://`):

   ```text
   mysql+pymysql://sentinel:sentinel_password@mariadb:3306/sentinel360_analytics
   ```

3. Si sigue fallando, ver `superset/README.md` (alternativa con imagen `apache/superset:latest-dev`).

### 4.2 La conexión a MariaDB falla (Test connection / Connect)

**Síntoma:** el botón "Test connection" o "Connect" falla al configurar la base de datos en Superset.

**Qué hacer:**

1. Comprobar que MariaDB y el usuario existan y que Superset pueda conectar:

   ```bash
   ./scripts/verificar_conexion_superset_mariadb.sh
   ```

   Ese script: comprueba MariaDB, aplica `01_create_db_and_user.sql` si hace falta y prueba la conexión desde dentro del contenedor de Superset.

2. En Superset, usar exactamente esta URI (incluyendo el nombre de base **`sentinel360_analytics`**):

   ```text
   mysql+pymysql://sentinel:sentinel_password@mariadb:3306/sentinel360_analytics
   ```

3. Si el script de verificación indica que falta el módulo `pymysql`, hay que reconstruir la imagen de Superset (ver apartado 4.1).

---

## 5. Resumen: pasos típicos con Superset

1. **Levantar:** `cd docker && docker compose up -d mariadb superset`
2. **Inicializar (primera vez o tras 500):** `./scripts/init_superset.sh`
3. **Comprobar conexión a MariaDB:** `./scripts/verificar_conexion_superset_mariadb.sh`
4. En Superset: **Settings → Database connections → + Database** → MySQL → URI `mysql+pymysql://sentinel:sentinel_password@mariadb:3306/sentinel360_analytics` → Test connection → Connect
5. Crear datasets (p. ej. `kpi_delays_by_warehouse`, `kpi_delays_by_vehicle`) y dashboards según `docs/SUPERSET_DASHBOARDS.md`

---

## 6. Grafana: levantar y datos

**Levantar:**

```bash
cd docker
docker compose up -d mariadb grafana
```

- **URL:** http://localhost:3000  
- **Login:** admin / admin (por defecto, configurable con `GF_SECURITY_*` en el compose)

El datasource MariaDB y los dashboards de la carpeta **Sentinel360** se cargan por provisioning (ver `grafana/README.md`).

**Para que los paneles tengan datos:**

1. **Datos de prueba:**  
   ```bash
   ./scripts/seed_kpi_demo_via_docker.sh
   ```  
   (Las tablas KPI deben existir; si no: `docker exec -i sentinel360-mariadb mysql -u sentinel -psentinel_password sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql`.)

2. **Datos del pipeline (MongoDB → MariaDB):**  
   ```bash
   ./scripts/pipeline_to_grafana.sh
   ```

---

## 7. Grafana: paneles en "No data"

**Síntoma:** los dashboards de Sentinel360 aparecen vacíos ("No data").

**Qué comprobar (en este orden):**

1. **Datos en MariaDB:** ejecutar `./scripts/seed_kpi_demo_via_docker.sh` o `./scripts/pipeline_to_grafana.sh` y comprobar que las tablas `kpi_delays_by_warehouse` y `kpi_delays_by_vehicle` tengan filas.
2. **Datasource en Grafana:** Configuration → Data sources → "Sentinel360 MariaDB" → **Save & test** (debe salir en verde).
3. **Reiniciar Grafana** para recargar provisioning:  
   `docker compose -f docker/docker-compose.yml restart grafana`
4. **Reset completo** (si sigues sin ver datos y has tocado configuración a mano):  
   `docker compose -f docker/docker-compose.yml down grafana && docker volume rm docker_grafana_data 2>/dev/null; docker compose -f docker/docker-compose.yml up -d grafana`  
   (esto borra cambios manuales en dashboards/datasources).

Más detalle en `grafana/README.md`.

---

## 8. Documentación de referencia

| Tema              | Ubicación |
|-------------------|-----------|
| Superset (uso, URI, driver, init) | `superset/README.md` |
| Grafana (provisioning, datos, "No data") | `grafana/README.md` |
| Diseño de dashboards Superset | `docs/SUPERSET_DASHBOARDS.md` |
| Diseño de dashboards Grafana | `docs/GRAFANA_DASHBOARDS.md` |
| Presentación del entorno visual | `docs/PRESENTACION_ENTORNO_VISUAL.md` |
| Scripts de inicialización/verificación | `scripts/init_superset.sh`, `scripts/verificar_conexion_superset_mariadb.sh`, `scripts/seed_kpi_demo_via_docker.sh`, `scripts/pipeline_to_grafana.sh` |
