// =====================================================================
// O1 · servidor OPC UA — "On Start" del function node
// docs/diagramas/flujo-servidor-opcua.mmd, bloques [DF-5.1] y [DF-5.2]
// ---------------------------------------------------------------------
// Descripcion: arranca el servidor OPC UA (lib/servidor_opcua.js, node-opcua 2.160.0,
//   ADR-011 / ADR-019) con el espacio de direcciones de docs/diccionario-de-datos.md §3.
//   Las escrituras sobre Outputs se delegan en el maestro MODBus que publico M1
//   (global "pdci_maestro"): el WriteResponse espera el eco FC 05/06 (ADR-015).
// Salida 1: panel de certificados {topic: 'certificados', payload: {rechazados, confiables, huellaPropia}}
// Firma de la biblioteca (consigna: "parametros con tipo"):
//   iniciarServidor({opcua: object, puerto: number, namespaceUri: string,
//       directorioPki: string, credenciales: {usuario: string, hashClave: string}|null,
//       escribir: (nombre: string, valor: any) => Promise<{ok: boolean, errorType: string, error: string|null}>,
//       registrar: (texto: string) => void}) : Promise<Controlador>
// =====================================================================
const pdci = global.get('pdci');
const cfg = pdci.opcua;

// [DF-5.4] Sin maestro (todavia arrancando o detenido) la escritura se rechaza con un
// error de comunicacion: nunca se confirma un valor que el esclavo no recibio.
const escribir = (nombre, valor) => {
    const maestro = global.get('pdci_maestro');
    if (!maestro) return Promise.resolve({ ok: false, errorType: 'TIMEOUT', error: 'maestro MODBus no disponible' });
    return maestro.escribir(nombre, valor);
};
const registrar = (texto) => {
    node.log(texto);
    pdci.historial.agregar({ capa: 'OPCUA', nivel: /rechaz|Bad|ERROR/.test(texto) ? 'aviso' : 'info', texto });
};

if (!cfg.credenciales) node.warn('sin PDCI_T3_OPCUA_USUARIO/HASH: solo acceso anonimo (lectura); las Outputs no se pueden escribir');

node.status({ fill: 'yellow', shape: 'ring', text: 'iniciando servidor OPC UA' });
const listo = pdci.servidorOpcua.iniciarServidor({ opcua: pdci.nodeOpcua, puerto: cfg.puerto, namespaceUri: cfg.namespaceUri,
    directorioPki: cfg.directorioPki, credenciales: cfg.credenciales, escribir, registrar })
    .then((servidor) => {
        context.set('servidor', servidor);
        node.status({ fill: 'green', shape: 'dot', text: `opc.tcp://:${cfg.puerto} · ${servidor.endpoints().length} endpoints` });
        return servidor;
    })
    .catch((e) => {
        // Puerto ocupado o PKI ilegible: la capa queda en ERROR y se ve en el panel (I-05).
        node.error(`servidor OPC UA no arranco: ${e.message}`);
        node.status({ fill: 'red', shape: 'dot', text: e.message.slice(0, 60) });
        pdci.capas.actualizar('OPCUA', { estado: 'ERROR', contadores: {}, detalle: { error: e.message } });
        return null;
    });
context.set('listo', listo);
