// =====================================================================
// M3 · puerto reconfigurado — [DF-2.17]
// ---------------------------------------------------------------------
// Descripcion: serial control responde con la configuracion vigente del
//   puerto despues de cada cambio. Se reenvia a M1 como "puerto-confirmado"
//   para que el maestro continue la reconfiguracion o el descubrimiento.
// =====================================================================
msg.topic = 'puerto-confirmado';
node.status({ fill: msg.payload.enabled === false ? 'grey' : 'green', shape: 'dot',
    text: msg.payload.enabled === false ? 'puerto serie deshabilitado (TCP)'
        : `${msg.payload.serialport} ${msg.payload.serialbaud} ${msg.payload.databits}${String(msg.payload.parity)[0].toUpperCase()}${msg.payload.stopbits}` });
return msg;
