-- Datos maestros: Almacenes (nodos del grafo). Rutas en HDFS del clúster.
CREATE DATABASE IF NOT EXISTS transport;
USE transport;

DROP TABLE IF EXISTS warehouses;
CREATE EXTERNAL TABLE IF NOT EXISTS warehouses (
    warehouse_id   STRING,
    name          STRING,
    city          STRING,
    country       STRING,
    lat           DOUBLE,
    lon           DOUBLE,
    capacity      INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/user/hadoop/proyecto/warehouses'
TBLPROPERTIES ('skip.header.line.count'='1');
