// =====================================================================
// BLOQUE C4 · Manejo de notificaciones y respuestas — Raspberry Pi 2
// diagramas/flujo_cliente.md, bloque C4 · consigna Parte 3.3
// ---------------------------------------------------------------------
// Descripcion: recibe cada dato leido del servidor (por Read en Modo A o
//   por notificacion en Modo B; el resto del flujo no distingue) y lo
//   dirige al LED correspondiente. Guarda el ultimo valor y su
//   SourceTimestamp para la consola (C6).
// Entrada: msg.topic 'servidorPulsador' | 'servidorRampa', msg.payload,
//   msg.statusCode, msg.sourceTimestamp.
// Salidas: [1] -> LED digital · [2] -> LED PWM.
// Excepciones: un dato con StatusCode distinto de Good NO se aplica a los
//   LED: se conserva el ultimo valor bueno (el LED se congela, igual que
//   con el cable desconectado).
// =====================================================================
if (msg.statusCode && msg.statusCode !== 'Good') {
    node.status({ fill: 'yellow', shape: 'ring', text: msg.topic + ' ' + msg.statusCode });
    return null;
}
flow.set(msg.topic, { valor: msg.payload, sourceTimestamp: msg.sourceTimestamp, modo: msg.modo });
if (msg.topic === 'servidorPulsador') return [{ payload: msg.payload }, null];
if (msg.topic === 'servidorRampa') return [null, { payload: msg.payload }];
return null;
