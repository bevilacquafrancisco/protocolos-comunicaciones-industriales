// =====================================================================
// BLOQUE C7 · Perdida y recuperacion del canal — Raspberry Pi 2
// diagramas/flujo_cliente.md, bloque C7 · consigna Parte 3.6
// ---------------------------------------------------------------------
// Descripcion: registra con marca de tiempo cada evento de conexion,
//   sesion y suscripcion que informa cliente_opcua.js (connection_lost,
//   backoff, connection_reestablished, after_reconnection,
//   subscription_status, keepalive...). Es la evidencia de la prueba de
//   desconexion: que paso, cuando y con que StatusCode.
//   Los KeepAlive se cuentan pero no se imprimen uno por uno (uno por
//   segundo inundaria el registro).
// Entrada: msg.topic = nombre del evento, msg.payload = texto.
// Salida: msg.payload con la linea fechada.
// Excepciones: ninguna.
// =====================================================================
if (msg.topic === 'keepalive') {
    const n = (flow.get('keepalives') || 0) + 1;
    flow.set('keepalives', n);
    node.status({ fill: 'green', shape: 'ring', text: 'KeepAlive x' + n });
    return null;
}
const linea = new Date().toISOString() + ' EVENTO ' + msg.payload;
node.log(linea);
const color = /lost|error|closed|failure|terminated|backoff/.test(msg.topic) ? 'red'
    : /reestablished|after_reconnection|connected|activated|created/.test(msg.topic) ? 'green' : 'yellow';
node.status({ fill: color, shape: 'dot', text: msg.topic });
return { payload: linea };
