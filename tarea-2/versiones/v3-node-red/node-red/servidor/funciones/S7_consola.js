// =====================================================================
// BLOQUE S7 · Registro en consola — Raspberry Pi 1
// diagramas/flujo_servidor.md, bloque S7 · consigna Parte 3.5
// ---------------------------------------------------------------------
// Descripcion: una vez por segundo imprime la rampa que genera esta placa,
//   la que recibe del cliente (Cliente.Rampa) y el SourceTimestamp de ese
//   dato. Va a node.log(): en la RPi sale por "journalctl -u nodered" y por
//   la consola de node-red-log, sin pasar por el editor.
// Entrada: msg del inject "S7 · Cada 1 s".
// Salida: msg.payload con la linea (para un nodo debug opcional).
// Excepciones: ninguna.
//
// Por que 1 s y no cada tick: imprimir 20 lineas por segundo suma carga
// al mismo event loop que genera las senales (el "efecto sonda" de la
// Tarea 1).
// =====================================================================
const generada = flow.get('rampaGenerada');
const recibido = flow.get('clienteRampa');
const ts = recibido && recibido.sourceTimestamp ? new Date(recibido.sourceTimestamp).toISOString() : 'sin dato';
const linea = 'SERVIDOR generada=' + (generada === undefined ? '-' : generada) +
    ' recibida(Cliente.Rampa)=' + (recibido ? recibido.valor : '-') +
    ' SourceTimestamp=' + ts;
node.log(linea);
return { payload: linea };
