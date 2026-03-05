## Entorno visual para la presentación del proyecto

Este documento describe cómo preparar un **entorno visual** para la presentación del proyecto Sentinel 360 usando:

- **MongoDB** como almacén operacional.
- **Spark / HDFS / NiFi** como capa de procesamiento Big Data (ya existente en el proyecto).
- **MariaDB (MySQL)** como base de datos analítica para los dashboards.
- **Apache Superset** como herramienta de visualización.

El objetivo es que, en la demo del máster, puedas mostrar:

- El flujo de datos extremo a extremo (desde la ingesta hasta los KPIs).
- Dashboards interactivos que se actualizan a partir de los datos procesados.

### Recordatorio: significado de Sentinel 360

- **Sentinel**: sistema de vigilancia que monitoriza la red de transporte.
- **360**: visión completa del sistema, combinando:
  - **Datos en tiempo real** (streaming y estado de vehículos).
  - **Datos históricos** (almacenamiento y agregados).
  - **Análisis predictivo** (modelos y métricas avanzadas que anticipan problemas).

---

## Arquitectura propuesta para la demo

1. **Capa operacional (ya existente)**
   - Datos históricos y de streaming en **MongoDB**, base de datos `transport`:
     - Colección `vehicle_state`
     - Colección `aggregated_delays`
   - Procesos de limpieza, enriquecimiento y grafos en **Spark**, con soporte de **HDFS** y **Hive**.

2. **Capa analítica**
   - Nueva base de datos en **MariaDB** (MySQL) que almacenará tablas agregadas y listas para análisis:
     - `kpi_delays_by_vehicle`
     - `kpi_delays_by_warehouse`

3. **Capa de visualización**
   - **Apache Superset**, conectado a MariaDB, desde donde se construyen dashboards:
     - Dashboard de *Overview* del sistema de transporte.
     - Dashboard de *Detalle* por vehículo / almacén / ventana temporal.

4. **Orquestación (opcional)**
   - Un DAG de **Airflow** (o un script Python programable) que:
     - Lee los datos procesados (desde MongoDB o Parquet).
     - Calcula métricas de interés.
     - Las vuelca en las tablas `kpi_*` de MariaDB.

---

## Preparación de la base de datos en MariaDB

### 1. Crear base de datos y usuario

En el servidor Ubuntu con LAMP/MariaDB, conectarse como usuario con privilegios suficientes y ejecutar:

```sql
CREATE DATABASE IF NOT EXISTS sentinel360_analytics
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'sentinel'@'%' IDENTIFIED BY 'sentinel_password';
GRANT ALL PRIVILEGES ON sentinel360_analytics.* TO 'sentinel'@'%';
FLUSH PRIVILEGES;
```

> Ajusta usuario, host y contraseña según la política de tu entorno.

### 2. Crear las tablas analíticas

En la carpeta `docs/sql_entorno_visual/` se incluyen los ficheros:

- `01_create_db_and_user.sql`
- `02_create_kpi_tables.sql`

Puedes aplicarlos con:

```bash
mysql -u root -p < docs/sql_entorno_visual/01_create_db_and_user.sql
mysql -u root -p sentinel360_analytics < docs/sql_entorno_visual/02_create_kpi_tables.sql
```

---

## Poblado de tablas desde MongoDB / Parquet

La lógica de negocio del proyecto ya produce:

- Colecciones en MongoDB (`transport.aggregated_delays`).
- Ficheros Parquet con resultados agregados (por ejemplo, en la carpeta `resultados/` o en HDFS).

Para alimentar las tablas de KPIs en MariaDB puedes seguir dos estrategias:

1. **Script Python standalone**
   - Script que:
     - Lee de MongoDB (`aggregated_delays`) o de los Parquet locales.
     - Calcula las agregaciones necesarias para los KPIs.
     - Inserta/actualiza las filas en `kpi_delays_by_vehicle` y `kpi_delays_by_warehouse`.
   - En este repositorio se incluye un ejemplo en `scripts/mongo_to_mariadb_kpi.py`:

     ```bash
     # Leer de MongoDB y cargar en MariaDB
     python scripts/mongo_to_mariadb_kpi.py --source mongo

     # Leer de ficheros Parquet (carpeta resultados/) y cargar en MariaDB
     python scripts/mongo_to_mariadb_kpi.py --source parquet
     ```

2. **DAG de Airflow**
   - DAG que ejecuta tareas similares al script anterior, pero programadas y monitorizadas.
   - Ventaja: mostrar en la demo la orquestación de extremo a extremo.

> Independientemente de la estrategia, la única condición para Superset es que las tablas `kpi_*` estén actualizadas en MariaDB.

---

## Configuración de Superset

### 1. Instalación rápida (ejemplo con Docker)

Seguir la guía oficial de Superset (puede variar con el tiempo); de forma resumida:

```bash
git clone https://github.com/apache/superset.git
cd superset
docker compose up
```

Una vez desplegado:

- Accede a la interfaz web de Superset (por defecto en `http://localhost:8088` o el puerto que definas).
- Crea el usuario administrador inicial según la guía oficial.

### 2. Añadir la conexión a MariaDB

En Superset:

1. Ir a **Settings → Database Connections** (o equivalente en tu versión).
2. Añadir una nueva base de datos con una URI similar a:

   ```text
   mysql+pymysql://sentinel:sentinel_password@hostname:3306/sentinel360_analytics
   ```

3. Probar la conexión y guardarla.

### 3. Crear datasets y dashboards

1. **Datasets**
   - Crear un dataset para `kpi_delays_by_vehicle`.
   - Crear un dataset para `kpi_delays_by_warehouse`.

2. **Dashboard de Overview**
   - KPIs principales:
     - Número total de viajes / eventos.
     - Retraso medio global.
     - Porcentaje de viajes con retraso por encima de cierto umbral.
   - Gráficos recomendados:
     - Serie temporal de `avg_delay_minutes` por día/ventana.
     - Top N vehículos más problemáticos (barras horizontales).

3. **Dashboard de Detalle**
   - Filtros por:
     - Fecha / ventana temporal.
     - `vehicle_id` y/o `warehouse_id`.
   - Gráficos:
     - Distribución de retrasos por vehículo / almacén.
     - Comparativa de retrasos entre almacenes.

> Es recomendable tener guardado un “storytelling” para la demo: qué gráficos mostrar y en qué orden.

---

## Guion sugerido para la presentación de máster

1. **Arquitectura general (diagrama)**
   - Explicar brevemente el flujo:
     - Ingesta → HDFS → Spark/Hive → MongoDB → MariaDB → Superset.

2. **Parte técnica**
   - Mostrar los scripts / DAGs clave (por ejemplo, los de Spark y el proceso que alimenta MariaDB).
   - Explicar cómo se garantiza la actualización de los KPIs.

3. **Parte visual (Superset)**
   - Abrir el dashboard de Overview:
     - Destacar 2–3 métricas clave.
   - Pasar al dashboard de Detalle:
     - Aplicar filtros y enseñar cómo el sistema permite analizar problemas específicos (vehículos, almacenes, ventanas temporales).

4. **Conclusión**
   - Resaltar la separación clara de capas:
     - Operacional (MongoDB).
     - Procesamiento Big Data (Spark/HDFS/Hive).
     - Analítica y visualización (MariaDB + Superset).
   - Explicar posibles extensiones futuras (más KPIs, alertas, otros tipos de visualización).

