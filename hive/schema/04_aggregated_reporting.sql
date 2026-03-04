-- Tabla agregada para reporting histórico (ventanas 15 min, por warehouse). Fase III.
CREATE DATABASE IF NOT EXISTS transport;
USE transport;

DROP TABLE IF EXISTS aggregated_delays;
CREATE TABLE IF NOT EXISTS aggregated_delays (
    window_start   TIMESTAMP,
    window_end     TIMESTAMP,
    warehouse_id   STRING,
    avg_delay_min  DOUBLE,
    vehicle_count  BIGINT
)
STORED AS PARQUET
LOCATION '/user/hadoop/proyecto/procesado/aggregated_delays';
