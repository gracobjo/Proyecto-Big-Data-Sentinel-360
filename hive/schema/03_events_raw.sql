-- Eventos crudos (desde HDFS raw / Kafka). Clúster: /user/hadoop/proyecto/raw
USE transport;
DROP TABLE IF EXISTS events_raw;
CREATE EXTERNAL TABLE IF NOT EXISTS events_raw (
    event_id      STRING,
    vehicle_id    STRING,
    ts            TIMESTAMP,
    lat           DOUBLE,
    lon           DOUBLE,
    speed         DOUBLE,
    warehouse_id  STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
   "separatorChar" = ",",
   "quoteChar"     = "\""
)
STORED AS TEXTFILE
LOCATION '/user/hadoop/proyecto/raw';
