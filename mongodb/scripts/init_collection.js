// Crear colecciones e índices para Sentinel360 (Fase III)
db = db.getSiblingDB('transport');
// Estado por vehículo
db.createCollection('vehicle_state');
db.vehicle_state.createIndex({ vehicle_id: 1 }, { unique: true });
db.vehicle_state.createIndex({ updated_at: -1 });
// Agregados por ventana (streaming desde Spark)
db.createCollection('aggregated_delays');
db.aggregated_delays.createIndex({ window_start: -1 });
db.aggregated_delays.createIndex({ warehouse_id: 1, window_start: -1 });
print('Colecciones transport.vehicle_state y transport.aggregated_delays listas.');
