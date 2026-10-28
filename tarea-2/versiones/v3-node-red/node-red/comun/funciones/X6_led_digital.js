// =====================================================================
// BLOQUES S6 / C4 · LED digital (comun a ambas placas)
// diagramas/flujo_servidor.md S6 · diagramas/flujo_cliente.md C4
// ---------------------------------------------------------------------
// Descripcion: el LED digital refleja el EstadoPulsador del OTRO equipo
//   (servidor: Cliente.EstadoPulsador; cliente: Servidor.EstadoPulsador).
// Entrada: msg.payload boolean.
// Salida: msg.payload 1 | 0 -> "pi gpiod out" en modo digital.
// Registro: una linea 'LATENCIA led_digital=...' por cada cambio.
// Excepciones: un payload que no sea boolean se descarta: nunca se
//   enciende un actuador con un dato de tipo dudoso.
// =====================================================================
if (msg.payload !== true && msg.payload !== false) {
    node.warn('EstadoPulsador no booleano: ' + msg.payload);
    return null;
}
node.status({ fill: msg.payload ? 'green' : 'grey', shape: 'dot', text: msg.payload ? 'ON' : 'OFF' });
// Marca para medir la latencia (Parte 3.4): solo cuando el LED CAMBIA. En
// Modo A llega el mismo valor 10 veces por segundo; registrar cada uno
// inundaria el registro y no aporta nada.
if (context.get('ultimo') !== msg.payload) {
    context.set('ultimo', msg.payload);
    node.log('LATENCIA led_digital=' + (msg.payload ? 'ON' : 'OFF') + ' t=' + new Date().toISOString());
}
return { payload: msg.payload ? 1 : 0 };
