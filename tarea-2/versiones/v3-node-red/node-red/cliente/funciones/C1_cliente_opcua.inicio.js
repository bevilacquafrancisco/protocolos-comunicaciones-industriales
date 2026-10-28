// =====================================================================
// BLOQUES C1, C3 y C7 · Cliente OPC UA — "On Start" de la function node
// diagramas/flujo_cliente.md, bloques C1 (conexion), C3a/C3b (lectura)
// y C7 (perdida y recuperacion del canal)
// ---------------------------------------------------------------------
// Descripcion: arranca el cliente con cliente_opcua.iniciarCliente() EN
//   SEGUNDO PLANO, sin await. Si On Start esperara la conexion y la RPi 1
//   estuviera apagada, Node-RED encolaria los 20 mensajes por segundo de
//   los temporizadores hasta que el servidor aparezca. Asi, el nodo queda
//   listo enseguida y descarta (y cuenta) lo que llega sin conexion.
// Salidas: [1] dato recibido { topic: 'servidorPulsador'|'servidorRampa',
//               payload, sourceTimestamp, serverTimestamp, statusCode }
//          [2] evento de conexion/sesion/suscripcion { topic, payload }
// Excepciones: si el primer intento falla (servidor caido, certificado no
//   confiado), reintenta cada 5 s y lo informa en el estado del nodo.
//
// Firma de la biblioteca:
//   iniciarCliente({ opcua: object, config: object, directorioPki: string,
//     alRecibir: (dato: object) => void, alEvento: (evento: object) => void,
//     entorno?: object }) : Promise<Controlador>
// =====================================================================
const config = global.get('config');
const opcua = global.get('opcua');
const modulo = global.get('clienteOpcua');
const rutas = global.get('pdciRutas');

context.set('activo', true);

const alRecibir = (dato) => {
    node.send([{
        topic: dato.variable, payload: dato.valor, statusCode: dato.statusCode,
        sourceTimestamp: dato.sourceTimestamp, serverTimestamp: dato.serverTimestamp, modo: dato.modo,
    }, null]);
};
const alEvento = (e) => {
    const texto = e.evento + (e.statusCode ? ' StatusCode=' + e.statusCode : '') + (e.detalle ? ' ' + e.detalle : '');
    node.send([null, { topic: e.evento, payload: texto, statusCode: e.statusCode }]);
};

const conectar = () => {
    if (!context.get('activo')) return;
    node.status({ fill: 'yellow', shape: 'ring', text: 'conectando a ' + config.opcua.endpointCliente });
    modulo.iniciarCliente({ opcua, config, directorioPki: rutas.pkiCliente, alRecibir, alEvento })
        .then((controlador) => {
            if (!context.get('activo')) { controlador.detener(); return; }
            context.set('controlador', controlador);
            node.status({ fill: 'green', shape: 'dot', text: 'Modo ' + config.lectura.modo + ' ' +
                config.seguridad.modoCliente + '/' + config.seguridad.politicaCliente });
        })
        .catch((error) => {
            node.status({ fill: 'red', shape: 'dot', text: error.message });
            node.warn('conexion fallida, reintento en 5 s: ' + error.message);
            context.set('reintento', setTimeout(conectar, 5000));
        });
};
conectar();
