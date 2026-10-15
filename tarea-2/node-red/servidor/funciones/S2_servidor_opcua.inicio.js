// =====================================================================
// BLOQUES S2 y S5 · Servidor OPC UA — "On Start" de la function node
// diagramas/flujo_servidor.md, bloques S2 (espacio de direcciones) y
// S5 (atencion de escrituras)
// ---------------------------------------------------------------------
// Descripcion: crea y arranca el servidor con
//   servidor_opcua.iniciarServidor() y deja el controlador en el contexto
//   del nodo. Cada escritura del cliente sale por las salidas 1/2.
// Salidas: [1] Cliente.EstadoPulsador (payload boolean)
//          [2] Cliente.Rampa (payload 0-65535)
//          [3] eventos de sesion y canal (payload texto)
// Excepciones: si el puerto 4840 sigue ocupado por el despliegue
//   anterior (EADDRINUSE) reintenta hasta 10 veces cada 500 ms; cualquier
//   otro error se informa en el estado del nodo.
//
// Firma de la biblioteca (consigna: "especificar parametros con tipo"):
//   iniciarServidor({ opcua: object, config: object, directorioPki: string,
//     credenciales: {usuario: string, hashClave: string} | null,
//     alEscribirCliente: (nombre: string, valor: boolean|number,
//                         dataValue: DataValue) => void,
//     registrar: (texto: string) => void }) : Promise<Controlador>
// =====================================================================
const config = global.get('config');
const opcua = global.get('opcua');
const modulo = global.get('servidorOpcua');
const rutas = global.get('pdciRutas');
const leerCredenciales = global.get('pdciCredencialesServidor');

// [SEC] Las credenciales se leen del entorno en el momento, a traves de una
// funcion: el hash nunca queda guardado en el contexto global, que el
// editor de Node-RED muestra en la barra lateral.
const cred = typeof leerCredenciales === 'function' ? leerCredenciales() : null;
const credenciales = cred && cred.usuario && cred.hashClave ? cred : null;
if (!credenciales) node.warn('sin OPCUA_USUARIO/OPCUA_CLAVE_HASH: solo acceso anonimo');

node.status({ fill: 'yellow', shape: 'ring', text: 'iniciando' });

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
let controlador = null;
for (let intento = 1; intento <= 10 && !controlador; intento++) {
    try {
        controlador = await modulo.iniciarServidor({
            opcua,
            config,
            directorioPki: rutas.pkiServidor,
            credenciales,
            // ---- BLOQUE S5: atencion de escrituras ----------------------
            alEscribirCliente: (nombre, valor, dataValue) => {
                flow.set(nombre, {
                    valor,
                    sourceTimestamp: dataValue.sourceTimestamp,
                    serverTimestamp: dataValue.serverTimestamp,
                });
                const m = { topic: nombre, payload: valor };
                node.send(nombre === 'clientePulsador' ? [m, null, null] : [null, m, null]);
            },
            registrar: (texto) => {
                node.log(texto);
                node.send([null, null, { topic: 'evento', payload: texto }]);
            },
        });
    } catch (error) {
        if (error.code === 'EADDRINUSE' && intento < 10) {
            await esperar(500);
        } else {
            node.status({ fill: 'red', shape: 'dot', text: error.message });
            node.error('no se pudo iniciar el servidor OPC UA: ' + error.message);
            break;
        }
    }
}

if (controlador) {
    context.set('controlador', controlador);
    for (const e of controlador.endpoints()) node.log('Endpoint: ' + e);
    node.status({ fill: 'green', shape: 'dot', text: 'escuchando :' + config.red.puertoOpcUa });
}
