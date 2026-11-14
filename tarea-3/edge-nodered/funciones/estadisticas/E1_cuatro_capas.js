// =====================================================================
// E1 · cuatro capas — I-05 (estadistica de las cuatro capas en todo momento)
// ---------------------------------------------------------------------
// Descripcion: cada 1 s arma la instantanea de las cuatro capas (MODBUS en
//   F3; OPC UA, MQTT y Sparkplug B se registran en F4/F5 con
//   pdci.capas.actualizar) y el historial de eventos. Va por tiempo y no por
//   eventos para que el panel se actualice aunque una capa este caida y no
//   produzca mensajes: justo cuando mas importa verla.
// Salidas: [1] tarjetas de las capas  [2] tramas y tiempos  [3] historial
// =====================================================================
const pdci = global.get('pdci');
const capas = pdci.capas.instantanea();
const modbus = global.get('pdci_modbus') || null;
return [
    { topic: 'capas', payload: capas },
    { topic: 'tramas', payload: modbus },
    { topic: 'historial', payload: pdci.historial.ultimos(40) },
];
