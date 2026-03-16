-- Tablas de KPIs para dashboards en Superset
-- Base de datos: sentinel360_analytics

USE sentinel360_analytics;

-- 1) KPIs de retrasos por vehículo y ventana temporal

CREATE TABLE IF NOT EXISTS kpi_delays_by_vehicle (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vehicle_id VARCHAR(64) NOT NULL,
  window_start DATETIME NOT NULL,
  window_end   DATETIME NOT NULL,

  trips_count        INT UNSIGNED NOT NULL DEFAULT 0,
  delayed_trips      INT UNSIGNED NOT NULL DEFAULT 0,
  avg_delay_minutes  DECIMAL(10, 2) DEFAULT NULL,
  max_delay_minutes  DECIMAL(10, 2) DEFAULT NULL,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_vehicle_window (vehicle_id, window_start),
  KEY idx_window (window_start, window_end)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- 2) KPIs de retrasos por almacén y ventana temporal

CREATE TABLE IF NOT EXISTS kpi_delays_by_warehouse (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  warehouse_id VARCHAR(64) NOT NULL,
  window_start DATETIME NOT NULL,
  window_end   DATETIME NOT NULL,

  trips_count        INT UNSIGNED NOT NULL DEFAULT 0,
  delayed_trips      INT UNSIGNED NOT NULL DEFAULT 0,
  avg_delay_minutes  DECIMAL(10, 2) DEFAULT NULL,
  max_delay_minutes  DECIMAL(10, 2) DEFAULT NULL,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_warehouse_window (warehouse_id, window_start),
  KEY idx_window (window_start, window_end)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

-- 3) Exportación desde Hive: aggregated_delays (ventanas 15 min por almacén)
CREATE TABLE IF NOT EXISTS kpi_hive_aggregated_delays (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  window_start DATETIME NOT NULL,
  window_end DATETIME NOT NULL,
  warehouse_id VARCHAR(64) NOT NULL,
  avg_delay_min DECIMAL(10, 2) DEFAULT NULL,
  vehicle_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_wh_win (warehouse_id, window_start)
)
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) Exportación desde Hive: reporte diario de retrasos
CREATE TABLE IF NOT EXISTS kpi_hive_reporte_diario (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  fecha_reportado DATE NOT NULL,
  warehouse_id VARCHAR(64) NOT NULL,
  total_vehiculos BIGINT UNSIGNED NOT NULL DEFAULT 0,
  avg_retraso_min DECIMAL(10, 2) DEFAULT NULL,
  ventanas_15min INT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_fecha_wh (fecha_reportado, warehouse_id)
)
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) Exportación desde MongoDB: anomalías detectadas (transport.anomalies)
CREATE TABLE IF NOT EXISTS kpi_anomalies (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  warehouse_id VARCHAR(64) DEFAULT NULL,
  window_start DATETIME DEFAULT NULL,
  window_end DATETIME DEFAULT NULL,
  avg_delay_min DECIMAL(10, 2) DEFAULT NULL,
  vehicle_count INT UNSIGNED DEFAULT NULL,
  anomaly_flag TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_wh_win (warehouse_id, window_start)
)
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

