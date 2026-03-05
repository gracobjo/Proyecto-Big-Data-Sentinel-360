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

