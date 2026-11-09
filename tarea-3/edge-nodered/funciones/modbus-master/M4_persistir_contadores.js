// =====================================================================
// M4 · persistir contadores — I-05
// ---------------------------------------------------------------------
// Descripcion: cada 10 s copia los contadores MODBus al contexto "archivo"
//   (localfilesystem, settings.js), para que OK / CRC_ERROR / TIMEOUT /
//   EXCEPTION sobrevivan a un reinicio de Node-RED. M1 los restaura al arrancar.
// =====================================================================
const s = global.get('pdci_modbus');
if (s) global.set('pdci_contadores', s.contadores, 'archivo');
return null;
