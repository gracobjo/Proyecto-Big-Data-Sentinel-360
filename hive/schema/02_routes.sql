-- Rutas entre almacenes (aristas del grafo). Clúster HDFS.
USE transport;
DROP TABLE IF EXISTS routes;
CREATE EXTERNAL TABLE IF NOT EXISTS routes (
    route_id      STRING,
    from_warehouse_id STRING,
    to_warehouse_id   STRING,
    distance_km   DOUBLE,
    avg_duration_min INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/user/hadoop/proyecto/routes'
TBLPROPERTIES ('skip.header.line.count'='1');
