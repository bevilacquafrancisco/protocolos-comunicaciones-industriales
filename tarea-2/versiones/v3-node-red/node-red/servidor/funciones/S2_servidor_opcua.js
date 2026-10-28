// =====================================================================
// BLOQUES S3 y S4 -> S2 · Publicacion de los datos del servidor
// diagramas/flujo_servidor.md
// ---------------------------------------------------------------------
// Descripcion: recibe la rampa (S3) y el pulsador (S4) y los publica en
//   Servidor.Rampa y Servidor.EstadoPulsador con setValueFromSource(), que
//   fija el SourceTimestamp en el instante de generacion.
// Entrada: msg.topic 'rampa' (payload 0-65535) o 'pulsador' (boolean);
//   msg.instante (Date) opcional.
// Salidas: ninguna (las escrituras del cliente salen desde On Start).
// Excepciones: si el servidor no termino de arrancar, el dato se descarta
//   y se cuenta: el siguiente tick lo reemplaza.
// =====================================================================
const controlador = context.get('controlador');
if (!controlador) {
    context.set('descartados', (context.get('descartados') || 0) + 1);
    return null;
}
const instante = msg.instante instanceof Date ? msg.instante : new Date();
if (msg.topic === 'rampa') {
    controlador.publicarRampa(msg.payload, instante);
} else if (msg.topic === 'pulsador') {
    controlador.publicarPulsador(msg.payload === true, instante);
    node.status({ fill: 'green', shape: msg.payload ? 'dot' : 'ring', text: 'pulsador ' + (msg.payload ? 'ON' : 'OFF') });
}
return null;
