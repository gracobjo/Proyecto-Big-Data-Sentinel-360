-- Tabla para reporte diario (equivalente al ejemplo NYC: "Airflow genera reporte diario y lo guarda en Hive")
-- Opcional: un DAG de Airflow puede insertar aquí el resumen del día.
CREATE DATABASE IF NOT EXISTS transport;
USE transport;

DROP TABLE IF EXISTS reporte_diario_retrasos;
CREATE TABLE IF NOT EXISTS reporte_diario_retrasos (
    fecha_reportado    DATE,
    warehouse_id       STRING,
    total_vehiculos    BIGINT,
    avg_retraso_min    DOUBLE,
    ventanas_15min     INT
)
STORED AS PARQUET
LOCATION '/user/hadoop/proyecto/procesado/reporte_diario_retrasos';
