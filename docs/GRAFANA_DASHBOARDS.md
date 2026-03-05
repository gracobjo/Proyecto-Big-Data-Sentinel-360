## Grafana – Paneles de monitorización para Sentinel360

Este documento describe cómo:

- Instalar y arrancar **Grafana** en el nodo Ubuntu.
- Configurar **datasources** (MongoDB y MariaDB).
- Definir los paneles recomendados para la demo del proyecto.

---

### 1. Instalación básica de Grafana (Ubuntu)

En el nodo donde quieras ejecutar Grafana:

```bash
sudo apt-get install -y apt-transport-https software-properties-common wget
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee /etc/apt/sources.list.d/grafana.list

sudo apt-get update
sudo apt-get install -y grafana

sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

- Interfaz web: `http://<IP_DEL_SERVIDOR>:3000`
- Usuario/contraseña inicial: `admin / admin` (Grafana pedirá cambiarlos al primer inicio).

---

### 2. Datasource MariaDB (KPIs agregados)

1. En la UI de Grafana:
   - Ir a **Configuration → Data sources → Add data source**.
   - Seleccionar tipo **MySQL**.
2. Configurar:
   - `Host`: `IP_MARIADB:3306` (por ejemplo `192.168.99.10:3306` si usas LAMP local).
   - `Database`: `sentinel360_analytics`.
   - `User`: `sentinel` (o el que hayas definido en `01_create_db_and_user.sql`).
   - `Password`: la contraseña que configuraste.
3. Probar conexión (**Save & Test**).

Tablas relevantes:

- `kpi_delays_by_vehicle`
- `kpi_delays_by_warehouse`

---

### 3. Datasource MongoDB (estado actual y anomalías)

Grafana no trae MongoDB como datasource nativo. Opciones:

1. **Datasource específico para MongoDB** (si tu versión lo permite, ej. `mongodb` plugin).
2. **Datasource basado en un backend JSON / SimpleJSON**:
   - Requiere un pequeño servicio backend que exponga consultas sobre MongoDB vía HTTP.

Para el contexto del máster, basta con mencionar que:

- MongoDB se usa como backend para:
  - `transport.vehicle_state` (estado actual).
  - `transport.anomalies` (ventanas anómalas detectadas).
- Grafana se puede conectar a MongoDB (vía plugin o backend intermedio) para mostrar estos datos en tiempo casi real.

> Si no configuras MongoDB directamente en Grafana, puedes seguir usando MariaDB para la demo principal de dashboards y dejar MongoDB como backend para futuras integraciones.

---

### 4. Panel recomendado 1 – “Estado actual de la flota”

**Objetivo**: visualizar, casi en tiempo real, la posición y el retraso de cada vehículo.

Datasource sugerido:

- Si tienes MongoDB datasource: `transport.vehicle_state`.
- Alternativa: construir una tabla en MariaDB que refleje el estado actual (no implementado).

Paneles:

- **Geomap / Worldmap**:
  - Campos:
    - Latitud: `lat`
    - Longitud: `lon`
    - Label: `vehicle_id`
  - Color/size: basado en `delay_minutes`.
  - Filtro: por `route_id` o por `timestamp` (últimos X minutos).

- **Tabla de vehículos**:
  - Columnas: `vehicle_id`, `route_id`, `speed`, `delay_minutes`, `timestamp`, `anomaly_flag` (si existe).
  - Orden: `delay_minutes` descendente.

Mensajes clave en la demo:

- “Aquí vemos la flota en el mapa, con el color indicando el retraso.”
- “La tabla permite localizar rápidamente los vehículos más retrasados.”

---

### 5. Panel recomendado 2 – “Anomalías detectadas”

**Objetivo**: visualizar las ventanas de tiempo y almacenes donde se ha detectado comportamiento anómalo.

Datasource sugerido:

- MongoDB: colección `transport.anomalies`.

Campos esperados (según `anomaly_detection.py`):

- `window_start`, `window_end`
- `warehouse_id`
- `avg_delay_min`
- `vehicle_count`
- `cluster`
- `anomaly_flag`

Paneles:

- **Tabla de anomalías**:
  - Columnas: `warehouse_id`, `window_start`, `window_end`, `avg_delay_min`, `vehicle_count`, `cluster`.
  - Filtro por rango de fechas.

- **Time series – Número de anomalías**:
  - Eje X: tiempo (por ejemplo `window_start`).
  - Métrica: `count(*)` de anomalías por intervalo (hora/día).

Mensajes para la defensa:

- “Este panel nos muestra, por almacén y ventana de tiempo, dónde el sistema ha detectado retrasos anómalos.”
- “Podemos ver cómo evolucionan las anomalías a lo largo de los días.”

---

### 6. Panel recomendado 3 – “KPIs por ruta / almacén”

**Objetivo**: ofrecer una visión de negocio de los retrasos usando las tablas de KPIs en MariaDB.

Datasource:

- MariaDB: `sentinel360_analytics`.

Tablas:

- `kpi_delays_by_vehicle`
- `kpi_delays_by_warehouse`

Paneles sugeridos:

- **Barras – Retraso medio por almacén**:
  - Query ejemplo:
    ```sql
    SELECT warehouse_id, AVG(avg_delay_minutes) AS delay_avg
    FROM kpi_delays_by_warehouse
    GROUP BY warehouse_id
    ORDER BY delay_avg DESC;
    ```
  - Eje X: `warehouse_id`.
  - Eje Y: `delay_avg`.

- **Time series – Retraso medio en el tiempo**:
  - Query ejemplo (simplificado):
    ```sql
    SELECT DATE(window_start) AS day,
           AVG(avg_delay_minutes) AS delay_avg
    FROM kpi_delays_by_route -- o by_vehicle / by_warehouse
    GROUP BY DATE(window_start)
    ORDER BY day;
    ```
  - Eje X: `day`.
  - Eje Y: `delay_avg`.

- **Tabla de KPIs**:
  - Columnas: `vehicle_id` / `warehouse_id`, `window_start`, `trips_count`, `delayed_trips`, `avg_delay_minutes`, `max_delay_minutes`.

---

### 7. Cómo encaja Grafana en la narrativa del proyecto

En la presentación puedes posicionar Grafana como:

- **Capa de monitorización operacional**:
  - Mapa de flota.
  - Panel de anomalías activas.
  - Vista rápida de KPIs operativos.

Mientras que Superset se mantiene como:

- **Capa de analítica de negocio / reporting**:
  - KPIs agregados históricos.
  - Exploración ad hoc de datos.

Esta dualidad (Grafana + Superset) refuerza la idea de que Sentinel360 cubre tanto la **operación en tiempo real** como la **analítica histórica y estratégica**.

