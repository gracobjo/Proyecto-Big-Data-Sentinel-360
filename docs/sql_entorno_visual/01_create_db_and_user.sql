-- Crear base de datos y usuario para la capa analítica de Sentinel360

CREATE DATABASE IF NOT EXISTS sentinel360_analytics
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Usuario de aplicación (ajustar host y contraseña según tu entorno)
CREATE USER IF NOT EXISTS 'sentinel'@'%' IDENTIFIED BY 'sentinel_password';

GRANT ALL PRIVILEGES ON sentinel360_analytics.* TO 'sentinel'@'%';
FLUSH PRIVILEGES;

