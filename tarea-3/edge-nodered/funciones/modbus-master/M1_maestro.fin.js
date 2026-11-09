// =====================================================================
// M1 · maestro MODBus — "On Stop" del function node
// ---------------------------------------------------------------------
// Descripcion: detiene el sondeo, libera temporizadores y el socket TCP de
//   desarrollo. Sin esto, cada Deploy dejaria un maestro viejo sondeando en
//   paralelo con el nuevo: dos maestros en un bus MODBus (leccion I-04 de la T2,
//   "cliente zombi").
// =====================================================================
const maestro = context.get('maestro');
if (maestro) maestro.detener();
const transporte = context.get('transporte');
if (transporte) transporte.destruir();
clearInterval(context.get('intervalo'));
// Contadores al archivo antes de salir.
const s = global.get('pdci_modbus');
if (s) global.set('pdci_contadores', s.contadores, 'archivo');
