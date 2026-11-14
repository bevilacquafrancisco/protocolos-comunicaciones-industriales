// =====================================================================
// M2 · bytes recibidos — [DF-2.8]
// ---------------------------------------------------------------------
// Descripcion: marca cada bloque de serial in (modo binario, separacion
//   "interbyte" de 2 ms) como topic "bytes" y lo pasa a M1. La separacion
//   de 2 ms solo agrupa bytes: la delimitacion real de la respuesta la hace
//   el maestro por LONGITUD ESPERADA (ADR-012), porque Node-RED no puede
//   medir el silencio t3,5 con precision (docs/spike-nodered-opcua.md §3).
// =====================================================================
if (!Buffer.isBuffer(msg.payload)) return null;   // configurado en binario: llega un Buffer
msg.topic = 'bytes';
return msg;
