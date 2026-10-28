// =====================================================================
// BLOQUES S4 / C5 · Lectura del pulsador local (comun a ambas placas)
// diagramas/flujo_servidor.md S4 · diagramas/flujo_cliente.md C5
// ---------------------------------------------------------------------
// Descripcion: convierte el nivel del GPIO en el Boolean del modelo. El
//   pulsador va a GND con pull-up interno: nivel 0 = presionado. El
//   antirrebote lo hace pigpio (set_glitch_filter, 25 000 us) antes de que
//   llegue el mensaje.
// Entrada: msg.payload 0 | 1 desde "pi gpiod in" (un mensaje por flanco).
// Salida: { topic: 'pulsador', payload: boolean, instante: Date }
//   -> S2 (servidor: publica Servidor.EstadoPulsador)
//   -> C1 (cliente: escribe Cliente.EstadoPulsador)
// Registro: una linea 'LATENCIA pulsador_local=...' por flanco.
// Excepciones: un payload que no sea 0/1 se descarta con advertencia.
// =====================================================================
const nivel = Number(msg.payload);
if (nivel !== 0 && nivel !== 1) {
    node.warn('nivel GPIO invalido: ' + msg.payload);
    return null;
}
const presionado = nivel === 0; // activo en bajo
const instante = new Date();
flow.set('pulsadorLocal', presionado);
// Marca para medir la latencia pulsador -> LED de la otra placa (Parte 3.4):
// se compara con la linea "LED digital" del otro equipo, con los relojes
// sincronizados por chrony (node-red/README.md §14).
node.log('LATENCIA pulsador_local=' + (presionado ? 'ON' : 'OFF') + ' t=' + instante.toISOString());
return { topic: 'pulsador', payload: presionado, instante };
