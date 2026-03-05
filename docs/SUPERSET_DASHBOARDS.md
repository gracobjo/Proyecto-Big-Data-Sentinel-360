## Superset – Dashboards analíticos para Sentinel360

Este documento explica cómo instalar **Apache Superset**, conectarlo a los datos de Sentinel360 y definir los dashboards recomendados para la demo del proyecto.

---

### 1. Instalación de Superset (vía Docker)

La forma más sencilla de probar Superset en el contexto del máster es usar el **docker-compose oficial**.

1. Clonar el repositorio de Superset en el servidor donde quieras ejecutarlo:

   ```bash
   git clone https://github.com/apache/superset.git
   cd superset
   ```

2. Levantar Superset con Docker Compose:

   ```bash
   docker compose up
   ```

   - Esto levantará:
     - Superset (frontend + backend).
     - La base de datos interna de Superset (por defecto, Postgres en contenedor).

3. Inicializar usuario administrador (si la imagen lo requiere):

   En otra terminal, dentro del directorio `superset/`:

   ```bash
   docker exec -it superset-app superset fab create-admin
   # Rellenar usuario, correo y contraseña

   docker exec -it superset-app superset init
   ```

4. Acceder a la interfaz web:

   - URL: `http://<IP_DEL_SERVIDOR>:8088`
   - Usuario / contraseña: los que creaste en el paso anterior.

> Alternativa: instalación nativa en entorno Python (virtualenv), siguiendo la guía oficial de Superset. Para el alcance del máster, Docker Compose suele ser suficiente.

---

### 2. Conexión a MariaDB (capa analítica de Sentinel360)

Superset se conectará a la base de datos **`sentinel360_analytics`** en MariaDB, donde residen las tablas de KPIs que llenas con `scripts/mongo_to_mariadb_kpi.py`.

1. En Superset, ir a:
   - **Settings → Database Connections** (o **Data → Databases** según versión).
   - Pulsar **+ Database**.

2. Seleccionar tipo **MySQL** (compatible con MariaDB).

3. Rellenar la URI de conexión, por ejemplo:

   ```text
   mysql+pymysql://sentinel:sentinel_password@192.168.99.10:3306/sentinel360_analytics
   ```

   - Ajustar:
     - Host/IP (`192.168.99.10` o la que tenga tu LAMP/MariaDB).
     - Usuario/contraseña según `docs/sql_entorno_visual/01_create_db_and_user.sql`.

4. Probar conexión (**Test Connection**) y guardar.

---

### 3. Crear datasets para las tablas de KPIs

1. En Superset:
   - Ir a **Data → Datasets → + Dataset**.
2. Seleccionar:
   - Base de datos: `sentinel360_analytics`.
   - Esquema (si aplica): dejar vacío o `public` según configuración.
   - Tabla:
     - `kpi_delays_by_vehicle`
     - `kpi_delays_by_warehouse`
3. Guardar cada dataset con un nombre descriptivo:
   - `KPIs por vehículo (Sentinel360)`.
   - `KPIs por almacén (Sentinel360)`.

Estos datasets serán la base para los gráficos y dashboards.

---

### 4. Dashboard 1 – “Overview retrasos Sentinel360”

**Objetivo**: ofrecer una vista ejecutiva de la situación de la red de transporte.

**Gráficos sugeridos** (usando `kpi_delays_by_warehouse` y/o `kpi_delays_by_vehicle`):

1. **Métrica principal – Retraso medio global**
   - Tipo: **Big Number**.
   - Métrica: `AVG(avg_delay_minutes)` sobre todas las filas recientes.
   - Filtro temporal: última semana / último mes.

2. **Retraso medio por almacén**
   - Tipo: **Bar chart**.
   - Dataset: `kpi_delays_by_warehouse`.
   - Eje X: `warehouse_id`.
   - Métrica: `AVG(avg_delay_minutes)`.
   - Orden: descendente, para ver fácilmente los almacenes más problemáticos.

3. **Top N vehículos con más retraso**
   - Tipo: **Bar chart** (horizontal).
   - Dataset: `kpi_delays_by_vehicle`.
   - Eje Y: `vehicle_id`.
   - Métrica: `AVG(avg_delay_minutes)`.
   - Filtro: limitar a los últimos X días.

4. **Serie temporal del retraso medio**
   - Tipo: **Time-series Line Chart**.
   - Dataset: cualquiera de los dos (por ejemplo `kpi_delays_by_vehicle`).
   - Time column: `window_start`.
   - Métrica: `AVG(avg_delay_minutes)`.
   - Granularidad: día u hora, según la resolución de tus datos.

Este dashboard puede llamarse, por ejemplo: **“Sentinel360 – Overview retrasos”**.

---

### 5. Dashboard 2 – “Detalle por vehículo / ruta”

**Objetivo**: permitir explorar en detalle el comportamiento de un vehículo o almacén concreto.

Basado principalmente en `kpi_delays_by_vehicle`.

1. **Filtros principales**:
   - `vehicle_id` (dropdown).
   - Rango de fechas por `window_start`.

2. **Gráficos sugeridos**:

   - **Time-series – Retraso de un vehículo concreto**
     - Time column: `window_start`.
     - Métrica: `avg_delay_minutes`.
     - Filtro: `vehicle_id = <seleccionado>`.

   - **Distribución de retrasos del vehículo**:
     - Tipo: **Histogram** o **Box plot**.
     - Campo: `avg_delay_minutes` filtrado por vehículo.

   - **Comparativa entre varios vehículos**:
     - Tipo: **Bar chart**.
     - Eje X: `vehicle_id`.
     - Métrica: `AVG(avg_delay_minutes)`.
     - Filtro temporal fijo (última semana / mes).

3. **Uso en la demo**:
   - Mostrar cómo seleccionando un `vehicle_id` concreto se puede:
     - Ver su historial de retrasos.
     - Compararlo con otros vehículos de la misma ruta.

---

### 6. Dashboard 3 – “Detalle por almacén / zona logística”

Basado en `kpi_delays_by_warehouse`.

1. **Filtros**:
   - `warehouse_id`.
   - Intervalo de fechas.

2. **Gráficos sugeridos**:

   - **Time-series – Retraso medio por almacén**.
   - **Heatmap – Retraso vs. día de la semana y franja horaria** (si en el futuro incluyes esas dimensiones en los KPIs).

3. **Narrativa**:
   - Sirve para que el responsable de planificación vea qué zonas logísticas generan más retrasos y en qué momentos.

---

### 7. Relación entre Superset y el resto de Sentinel360

En la arquitectura de Sentinel360, Superset se sitúa en la **capa de analítica y visualización**:

- Recibe datos agregados desde:
  - **MongoDB** → `scripts/mongo_to_mariadb_kpi.py` → **MariaDB (`sentinel360_analytics`)**.
  - Opcionalmente, en el futuro, desde tablas adicionales con predicciones o congestión.
- Ofrece:
  - Dashboards de KPIs globales (overview).
  - Vistas detalladas por vehículo, ruta o almacén.

Mientras Grafana se orienta a:

- Monitorización **operacional** (tiempo casi real):
  - Estado actual de la flota.
  - Anomalías activas (colecciones Mongo, topic `alerts`).

Superset, por tanto, refuerza el componente de **“toma de decisiones basada en datos históricos y KPIs”**, mientras que Grafana cubre la **parte de observabilidad diaria**.

