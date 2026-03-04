// Crear colección e índices para estado de vehículos
db = db.getSiblingDB('transport');
db.createCollection('vehicle_state');
db.vehicle_state.createIndex({ vehicle_id: 1 }, { unique: true });
db.vehicle_state.createIndex({ updated_at: -1 });
print('Colección transport.vehicle_state lista.');
