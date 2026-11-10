// =====================================================================
// M1 · maestro MODBus — "On Start" del function node
// docs/diagramas/flujo-maestro.mmd, bloque [DF-2.1] (inicio)
// ---------------------------------------------------------------------
// Descripcion: carga la configuracion persistida (o la de fabrica), crea el
//   maestro (lib/maestro.js) con un transporte compuesto -puerto serie de
//   node-red-node-serialport o TCP de desarrollo- y lo arranca.
//   El protocolo NO lo hace ningun nodo de la paleta: lo hace lib/modbus.js (I-01).
// Salidas: [1] serial out      Buffer con la trama a transmitir
//          [2] serial control  {serialport, serialbaud, databits, parity, stopbits, enabled}
//          [3] estado          instantanea del maestro (max. 2 por segundo) y eventos
//          [4] valores         una variable que cambio: topic = nombre, payload = valor
//          [5] respuestas      resultado de cada comando del panel (topic = tipo)
// Firma de la biblioteca (consigna: "parametros con tipo"):
//   new MaestroModbus({config: object, transporte: {enviar(Buffer): void,
//       reconfigurar(puerto: object): Promise<void>}}) : MaestroModbus
// =====================================================================
const pdci = global.get('pdci');
const { configuracion, MaestroModbus, transportes } = pdci;

const carga = configuracion.cargar(pdci.rutas.config);
carga.avisos.forEach((aviso) => node.warn(aviso));
const config = carga.config;

// --- Adaptador del puerto serie de Node-RED ------------------------------
// serial control responde ANTES de que el puerto termine de reabrir (changePort
// cierra y la reapertura es asincrona): la espera de asentamiento la hace el
// maestro con config.puerto.esperaReconfiguracionMs.
let confirmarPuerto = null;
const serie = {
    enviar: (trama) => node.send([{ payload: trama }, null, null, null, null]),
    reconfigurar: (puerto) => new Promise((resolver) => {
        confirmarPuerto = resolver;
        node.send([null, { payload: Object.assign(configuracion.paraSerialControl(puerto), { enabled: true }) },
            null, null, null]);
        // Si serial control no confirma (puerto inexistente), se sigue: el maestro contara TIMEOUT.
        setTimeout(() => { if (confirmarPuerto === resolver) { confirmarPuerto = null; resolver(); } }, 2000);
    }),
    deshabilitar: () => node.send([null, { payload: { enabled: false } }, null, null, null]),
};
context.set('confirmarPuerto', (estadoPuerto) => {
    if (confirmarPuerto) { const r = confirmarPuerto; confirmarPuerto = null; r(estadoPuerto); }
});

const transporte = new transportes.TransporteCompuesto(serie);
const maestro = new MaestroModbus({ config, transporte });
transporte.on('datos', (bloque) => maestro.recibir(bloque));
transporte.on('evento', (e) => pdci.historial.agregar(Object.assign({ capa: 'MODBUS' }, e)));

// Contadores persistidos (contexto "archivo"): sobreviven a un reinicio.
maestro.restaurarContadores(global.get('pdci_contadores', 'archivo'));

// --- Eventos del maestro ---------------------------------------------------
let ultimoEstado = null;
maestro.on('estado', (s) => {
    ultimoEstado = s;
    global.set('pdci_modbus', s);
    pdci.capas.actualizar('MODBUS', { estado: s.estado, contadores: {
        OK: s.contadores.OK, CRC_ERROR: s.contadores.CRC_ERROR, TIMEOUT: s.contadores.TIMEOUT,
        EXCEPTION: s.contadores.EXCEPTION }, detalle: { ultimaTx: s.ultimaTx, ultimaRx: s.ultimaRx,
        latenciaMs: s.latenciaMs, esclavo: s.esclavo, puerto: s.puerto, ...s.contadores.detalle } });
});
maestro.on('valor', (v) => node.send([null, null, null,
    { topic: v.nombre, payload: v.valor, calidad: v.calidad, ts: v.ts }, null]));
maestro.on('evento', (e) => {
    pdci.historial.agregar(e);
    node.status({ fill: e.nivel === 'info' ? 'green' : 'yellow', shape: 'dot', text: e.texto.slice(0, 60) });
});

// Estado hacia el panel y OPC UA a 2 por segundo como maximo: el maestro emite uno por
// peticion (16/s con 4 variables cada 250 ms) y no hace falta redibujar tanto.
const intervalo = setInterval(() => {
    if (ultimoEstado) node.send([null, null, { topic: 'estado', payload: ultimoEstado }, null, null]);
    ultimoEstado = null;
}, 500);

context.set('maestro', maestro);
// O1 (servidor OPC UA) encola sus escrituras FC 05/06 en este mismo maestro [DF-5.4].
global.set('pdci_maestro', maestro);
context.set('transporte', transporte);
context.set('intervalo', intervalo);

// Arranque diferido: los nodos serie tienen que estar levantados antes de reconfigurarlos.
setTimeout(() => {
    transporte.reconfigurar(config.puerto).then(() => {
        maestro.iniciar();
        node.send([null, null, null, null, { topic: 'config', payload: config, origen: carga.origen }]);
        node.status({ fill: 'green', shape: 'dot', text: `sondeando: ${maestro.instantanea().puerto}` });
    });
}, 1000);
node.status({ fill: 'yellow', shape: 'ring', text: `iniciando (${carga.origen})` });
