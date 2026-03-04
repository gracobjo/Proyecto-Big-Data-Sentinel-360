-- Genera el resumen del día anterior desde aggregated_delays y lo guarda en reporte_diario_retrasos.
-- Ejecutar vía Hive CLI o desde un DAG de Airflow (equivalente al ejemplo NYC: reporte diario guardado en Hive).
USE transport;

INSERT INTO TABLE reporte_diario_retrasos
SELECT
    to_date(window_start) AS fecha_reportado,
    warehouse_id,
    sum(vehicle_count)    AS total_vehiculos,
    avg(avg_delay_min)    AS avg_retraso_min,
    count(*)              AS ventanas_15min
FROM aggregated_delays
WHERE to_date(window_start) = date_sub(current_date, 1)
GROUP BY to_date(window_start), warehouse_id;
