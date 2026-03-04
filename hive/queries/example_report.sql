-- Ejemplo: reporting histórico de retrasos por almacén (ventanas 15 min)
USE transport;

SELECT
    warehouse_id,
    window_start,
    avg_delay_min,
    vehicle_count
FROM aggregated_delays
WHERE window_start >= date_sub(current_timestamp(), 1)
ORDER BY window_start DESC, avg_delay_min DESC
LIMIT 100;
