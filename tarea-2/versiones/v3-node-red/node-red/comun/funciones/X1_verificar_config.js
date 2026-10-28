// =====================================================================
// BLOQUES S1 / C0 · Inicializacion (comun a ambas placas)
// diagramas/flujo_servidor.md S1 · diagramas/flujo_cliente.md C0
// ---------------------------------------------------------------------
// Descripcion: se ejecuta una vez al desplegar el flujo. Verifica que
//   settings.js haya cargado los modulos compartidos y que config.js sea
//   la version que este flujo espera, y lleva los dos LED a su estado
//   seguro (apagados) antes de que exista cualquier dato.
// Entrada: msg del inject de arranque; msg.payload = nombre del modulo
//   OPC UA que esta placa necesita ('servidorOpcua' | 'clienteOpcua').
// Salidas: [1] LED digital (payload 0) · [2] LED PWM (payload 0 %).
// Excepciones: si falta un modulo, informa con node.error() y no envia
//   nada: un nodo mal desplegado avisa, no se comporta a medias.
// =====================================================================
const VERSION_CONFIG_REQUERIDA = 1;

const config = global.get('config');
const senales = global.get('senales');
const faltantes = ['config', 'senales', 'opcua', 'pdciRutas', String(msg.payload)].filter((n) => !global.get(n));
if (faltantes.length > 0) {
    node.error('settings.js no cargo: ' + faltantes.join(', ') + ' (ver node-red/README.md §3)');
    node.status({ fill: 'red', shape: 'dot', text: 'falta ' + faltantes.join(', ') });
    return null;
}
if (config.VERSION !== VERSION_CONFIG_REQUERIDA) {
    // Igual que en la Tarea 1: un nodo con configuracion vieja arranca
    // avisando, no aborta.
    node.warn('config.js version ' + config.VERSION + ', este flujo espera ' + VERSION_CONFIG_REQUERIDA);
}
node.status({ fill: 'green', shape: 'dot', text: 'config v' + config.VERSION });
return [{ payload: 0 }, { payload: senales.dutyAPorcentajePiGpiod(0) }];
