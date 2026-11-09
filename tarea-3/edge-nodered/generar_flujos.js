/**
 * generar_flujos.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Genera los flows de Node-RED del dispositivo 2, UNO POR FLOW, en edge-nodered/flows/:
 *
 *   dashboard-base.json    configuracion global del Dashboard 2.0 (ui-base, ui-theme)
 *   modbus-master.json     maestro MODBus RTU: puerto serie, M1-M4
 *   dashboard-config.json  pagina de configuracion en vivo (I-04): D1, D2 y 4 paneles
 *   estadisticas.json      pagina de estadistica de las cuatro capas (I-05): E1, E2 y 4 paneles
 *
 * y el archivo combinado que carga Node-RED (<userDir>/flows.json, no versionado).
 *
 * Fuentes: funciones/<flow>/*.js (codigo de cada function node), plantillas/*.vue (cada
 * ui-template) y config/config.default.json (valores iniciales del puerto serie). Nada se
 * edita a mano en el editor: un cambio hecho alli se pierde al regenerar (mismo criterio
 * que la T2, ADR-03). Los IDs se derivan del nombre (SHA-1), asi regenerar produce el mismo
 * archivo y git muestra solo lo que cambio de verdad. prueba: test/flujos.test.js.
 *
 * Uso
 *   node generar_flujos.js          (en tarea-3/edge-nodered; o: npm run flows)
 *
 * Dependencias externas: ninguna (Node.js >= 18).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const RAIZ = __dirname;
const DESTINO = path.join(RAIZ, 'flows');
const USER_DIR = process.env.PDCI_T3_USERDIR || path.join(RAIZ, '.node-red');
const CONFIG = JSON.parse(fs.readFileSync(path.join(RAIZ, 'config', 'config.default.json'), 'utf8'));

/** ID estable de 16 hex a partir de una clave. */
const id = (clave) => crypto.createHash('sha1').update(clave).digest('hex').slice(0, 16);
/** Contenido de un archivo fuente. */
const leer = (relativo) => fs.readFileSync(path.join(RAIZ, relativo), 'utf8');

// =============================================================================
// Nodos globales (configuracion), compartidos por varios flows
// =============================================================================

const ID = {
    base: id('ui/base'),
    tema: id('ui/tema'),
    paginaConfig: id('ui/pagina/configuracion'),
    paginaEstadisticas: id('ui/pagina/estadisticas'),
    puertoSerie: id('serie/bus-rs485'),
    // Links entre flows
    aMaestro: id('link/a-maestro'),
    deMaestroEstado: id('link/de-maestro-estado'),
    deMaestroValores: id('link/de-maestro-valores'),
    deMaestroRespuestas: id('link/de-maestro-respuestas'),
    configDesdeMaestro: id('link/config-desde-maestro'),
    configAMaestro: id('link/config-a-maestro'),
    estadValores: id('link/estad-valores'),
    estadRespuestas: id('link/estad-respuestas'),
    estadAMaestro: id('link/estad-a-maestro'),
};

/** Fabrica de nodos de una pestana. */
function fabrica(prefijo, tab) {
    const nid = (nombre) => id(`${prefijo}/${nombre}`);
    const base = (tipo, nombre, x, y, extra) => Object.assign({ id: nid(nombre), type: tipo, z: tab, name: nombre, x, y }, extra);
    const cables = (destinos) => destinos.map((salida) => salida.map((d) => (d.length === 16 && /^[0-9a-f]+$/.test(d) ? d : nid(d))));
    return {
        nid,
        tab: (etiqueta, info) => ({ id: tab, type: 'tab', label: etiqueta, disabled: false, info }),
        comentario: (nombre, info, x, y) => base('comment', nombre, x, y, { info, wires: [] }),
        inject: (nombre, x, y, { repetirS, destinos }) => base('inject', nombre, x, y, {
            props: [{ p: 'payload' }], repeat: String(repetirS), crontab: '', once: true, onceDelay: '2',
            topic: '', payload: '', payloadType: 'date', wires: cables([destinos]) }),
        funcion: (nombre, x, y, { archivo, inicio = '', fin = '', salidas = 1, etiquetas = [], destinos = [[]] }) =>
            base('function', nombre, x, y, {
                func: leer(archivo), outputs: salidas, timeout: 0, noerr: 0,
                initialize: inicio ? leer(inicio) : '', finalize: fin ? leer(fin) : '', libs: [],
                outputLabels: etiquetas, wires: cables(destinos) }),
        plantilla: (nombre, x, y, { archivo, grupo, orden, destinos = [] }) => base('ui-template', nombre, x, y, {
            group: grupo, page: '', ui: '', order: orden, width: 0, height: 0, head: '', format: leer(archivo),
            storeOutMessages: true, passthru: false, resendOnRefresh: true, templateScope: 'local', className: '',
            wires: cables([destinos]) }),
        linkIn: (nombre, idFijo, x, y, { desde, destinos }) => Object.assign(base('link in', nombre, x, y,
            { links: desde, wires: cables([destinos]) }), { id: idFijo }),
        linkOut: (nombre, idFijo, x, y, { hacia }) => Object.assign(base('link out', nombre, x, y,
            { mode: 'link', links: hacia, wires: [] }), { id: idFijo }),
        grupo: (nombre, pagina, ancho, orden) => ({ id: nid(`grupo/${nombre}`), type: 'ui-group', name: nombre,
            page: pagina, width: ancho, height: 1, order: orden, showTitle: true, className: '', visible: 'true',
            disabled: 'false', groupType: 'default' }),
    };
}

// =============================================================================
// dashboard-base.json — Dashboard 2.0: base, tema y paginas
// =============================================================================
function flujoDashboardBase() {
    const pagina = (idPagina, nombre, rutaUrl, icono, orden) => ({
        id: idPagina, type: 'ui-page', name: nombre, ui: ID.base, path: rutaUrl, icon: icono, layout: 'grid',
        theme: ID.tema, breakpoints: [{ name: 'Default', px: '0', cols: '3' }, { name: 'Tablet', px: '576', cols: '6' },
            { name: 'Small Desktop', px: '768', cols: '9' }, { name: 'Desktop', px: '1024', cols: '12' }],
        order: orden, className: '', visible: 'true', disabled: 'false' });
    return [
        { id: ID.base, type: 'ui-base', name: 'PdCI T3 · dispositivo 2', path: '/dashboard', appIcon: '',
            includeClientData: true, acceptsClientConfig: ['ui-notification', 'ui-control'], showPathInSidebar: false,
            headerContent: 'page', navigationStyle: 'default', titleBarStyle: 'default',
            showReconnectNotification: true, notificationDisplayTime: 1, showDisconnectNotification: true,
            allowInstall: false },
        { id: ID.tema, type: 'ui-theme', name: 'PdCI azul marino',
            colors: { surface: '#1f3864', primary: '#1f3864', bgPage: '#f2f4f8', groupBg: '#ffffff', groupOutline: '#d0d5de' },
            sizes: { density: 'compact', pagePadding: '12px', groupGap: '12px', groupBorderRadius: '4px', widgetGap: '12px' } },
        pagina(ID.paginaEstadisticas, 'Estadísticas', '/estadisticas', 'chart-box-outline', 1),
        pagina(ID.paginaConfig, 'Configuración MODBus', '/configuracion', 'cog-outline', 2),
    ];
}

// =============================================================================
// modbus-master.json — maestro MODBus RTU (F3)
// =============================================================================
function flujoMaestro() {
    const f = fabrica('maestro', id('tab/maestro'));
    const p = CONFIG.puerto;
    return [
        f.tab('MODBus · maestro', 'Maestro MODBus RTU con stack y CRC propios (I-01). Protocolo en lib/modbus.js, '
            + 'maquina de estados en lib/maestro.js, diagrama docs/diagramas/flujo-maestro.mmd. '
            + 'NO usar node-red-contrib-modbus. Generado por generar_flujos.js: no editar a mano.'),
        // Puerto serie: binario, separacion "interbyte" de 2 ms (solo agrupa: el maestro
        // delimita por longitud, ADR-012), sin caracter agregado al transmitir.
        { id: ID.puertoSerie, type: 'serial-port', name: 'bus RS-485', serialport: p.ruta, serialbaud: String(p.baud),
            databits: p.bitsDatos, parity: p.paridad, stopbits: p.bitsParada, waitfor: '', dtr: 'none', rts: 'none',
            cts: 'none', dsr: 'none', newline: '2', bin: 'bin', out: 'interbyte', addchar: '', responsetimeout: 10000 },
        f.comentario('Maestro MODBus RTU · F3', 'M1 crea el maestro (On Start) y atiende comandos. '
            + 'M2: bytes de serial in. M3: confirmacion de serial control. M4: contadores a disco.', 210, 40),
        Object.assign(f.funcion('M1 · maestro MODBus [DF-2.1 a DF-2.17]', 560, 180, {
            archivo: 'funciones/modbus-master/M1_maestro.js', inicio: 'funciones/modbus-master/M1_maestro.inicio.js',
            fin: 'funciones/modbus-master/M1_maestro.fin.js', salidas: 5,
            etiquetas: ['serial out', 'serial control', 'estado', 'valores', 'respuestas'],
            destinos: [['serial out'], ['serial control'], [ID.deMaestroEstado], [ID.deMaestroValores], [ID.deMaestroRespuestas]] })),
        { id: f.nid('serial in'), type: 'serial in', z: id('tab/maestro'), name: 'bus RS-485 (entrada)',
            serial: ID.puertoSerie, x: 150, y: 120, wires: [[f.nid('M2 · bytes recibidos [DF-2.8]')]] },
        f.funcion('M2 · bytes recibidos [DF-2.8]', 360, 120, { archivo: 'funciones/modbus-master/M2_bytes_recibidos.js',
            destinos: [['M1 · maestro MODBus [DF-2.1 a DF-2.17]']] }),
        { id: f.nid('serial out'), type: 'serial out', z: id('tab/maestro'), name: 'bus RS-485 (salida)',
            serial: ID.puertoSerie, x: 880, y: 120, wires: [] },
        { id: f.nid('serial control'), type: 'serial control', z: id('tab/maestro'), name: 'reconfigurar puerto',
            serial: ID.puertoSerie, x: 880, y: 160, wires: [[f.nid('M3 · puerto reconfigurado [DF-2.17]')]] },
        f.funcion('M3 · puerto reconfigurado [DF-2.17]', 360, 240, { archivo: 'funciones/modbus-master/M3_puerto_reconfigurado.js',
            destinos: [['M1 · maestro MODBus [DF-2.1 a DF-2.17]']] }),
        f.linkIn('→ maestro (comandos)', ID.aMaestro, 150, 180, { desde: [ID.configAMaestro, ID.estadAMaestro],
            destinos: ['M1 · maestro MODBus [DF-2.1 a DF-2.17]'] }),
        f.linkOut('maestro → estado', ID.deMaestroEstado, 880, 200, { hacia: [] }),
        f.linkOut('maestro → valores', ID.deMaestroValores, 880, 240, { hacia: [ID.estadValores] }),
        f.linkOut('maestro → respuestas', ID.deMaestroRespuestas, 880, 280,
            { hacia: [ID.configDesdeMaestro, ID.estadRespuestas] }),
        f.inject('cada 10 s', 150, 320, { repetirS: 10, destinos: ['M4 · persistir contadores'] }),
        f.funcion('M4 · persistir contadores', 360, 320, { archivo: 'funciones/modbus-master/M4_persistir_contadores.js' }),
    ];
}

// =============================================================================
// dashboard-config.json — configuracion en vivo (I-04)
// =============================================================================
function flujoDashboardConfig() {
    const tab = id('tab/dashboard-config');
    const f = fabrica('config', tab);
    const g = {
        enlace: f.grupo('Enlace serie, esclavo y sondeo', ID.paginaConfig, 6, 1),
        prueba: f.grupo('Probar conexión y trama manual', ID.paginaConfig, 6, 2),
        mapa: f.grupo('Mapa de registros', ID.paginaConfig, 12, 3),
        descubrimiento: f.grupo('Asistente de descubrimiento', ID.paginaConfig, 12, 4),
    };
    const D1 = 'D1 · comandos del panel [DF-2.17]';
    return [
        f.tab('Dashboard · configuración', 'Configuracion del maestro en vivo, sin recompilar ni reiniciar (I-04). '
            + 'D1 valida y combina; el maestro valida otra vez y guarda en disco.'),
        ...Object.values(g),
        f.comentario('Configuración en vivo · I-04', 'Cada panel es un ui-template (plantillas/*.vue).', 190, 40),
        f.linkIn('maestro → respuestas (config)', ID.configDesdeMaestro, 150, 140,
            { desde: [ID.deMaestroRespuestas], destinos: ['D2 · repartir respuestas'] }),
        f.funcion('D2 · repartir respuestas', 380, 140, { archivo: 'funciones/dashboard-config/D2_repartir_respuestas.js',
            salidas: 4, etiquetas: ['enlace', 'mapa', 'prueba', 'descubrimiento'],
            destinos: [['panel enlace'], ['panel mapa'], ['panel prueba'], ['panel descubrimiento']] }),
        f.plantilla('panel enlace', 640, 80, { archivo: 'plantillas/enlace.vue', grupo: g.enlace.id, orden: 1, destinos: [D1] }),
        f.plantilla('panel mapa', 640, 120, { archivo: 'plantillas/mapa.vue', grupo: g.mapa.id, orden: 1, destinos: [D1] }),
        f.plantilla('panel prueba', 640, 160, { archivo: 'plantillas/prueba.vue', grupo: g.prueba.id, orden: 1, destinos: [D1] }),
        f.plantilla('panel descubrimiento', 640, 200, { archivo: 'plantillas/descubrimiento.vue', grupo: g.descubrimiento.id,
            orden: 1, destinos: [D1] }),
        f.funcion(D1, 880, 140, { archivo: 'funciones/dashboard-config/D1_comandos_del_panel.js', destinos: [[ID.configAMaestro]] }),
        f.linkOut('→ maestro (desde config)', ID.configAMaestro, 1090, 140, { hacia: [ID.aMaestro] }),
    ];
}

// =============================================================================
// estadisticas.json — estadistica de las cuatro capas (I-05)
// =============================================================================
function flujoEstadisticas() {
    const tab = id('tab/estadisticas');
    const f = fabrica('estadisticas', tab);
    const g = {
        capas: f.grupo('Estado de las cuatro capas', ID.paginaEstadisticas, 12, 1),
        variables: f.grupo('Variables del dispositivo 1', ID.paginaEstadisticas, 6, 2),
        tramas: f.grupo('Tramas MODBus en el bus', ID.paginaEstadisticas, 6, 3),
        historial: f.grupo('Historial de eventos', ID.paginaEstadisticas, 12, 4),
    };
    return [
        f.tab('Dashboard · estadísticas', 'Estadistica de MODBUS, OPC UA, MQTT y Sparkplug B en todo momento (I-05). '
            + 'OPC UA (F4) y MQTT/Sparkplug (F5) publican con pdci.capas.actualizar().'),
        ...Object.values(g),
        f.inject('cada 1 s', 150, 100, { repetirS: 1, destinos: ['E1 · cuatro capas'] }),
        f.funcion('E1 · cuatro capas', 360, 100, { archivo: 'funciones/estadisticas/E1_cuatro_capas.js', salidas: 3,
            etiquetas: ['capas', 'tramas', 'historial'], destinos: [['panel capas'], ['panel tramas'], ['panel historial']] }),
        f.plantilla('panel capas', 620, 60, { archivo: 'plantillas/capas.vue', grupo: g.capas.id, orden: 1, destinos: [ID.estadAMaestro] }),
        f.plantilla('panel tramas', 620, 100, { archivo: 'plantillas/tramas.vue', grupo: g.tramas.id, orden: 1 }),
        f.plantilla('panel historial', 620, 140, { archivo: 'plantillas/historial.vue', grupo: g.historial.id, orden: 1 }),
        f.linkIn('maestro → valores (estadísticas)', ID.estadValores, 150, 220,
            { desde: [ID.deMaestroValores], destinos: ['E2 · variables'] }),
        f.linkIn('maestro → respuestas (estadísticas)', ID.estadRespuestas, 150, 260,
            { desde: [ID.deMaestroRespuestas], destinos: ['E2 · variables'] }),
        f.funcion('E2 · variables', 380, 240, { archivo: 'funciones/estadisticas/E2_variables.js', destinos: [['panel variables']] }),
        f.plantilla('panel variables', 620, 240, { archivo: 'plantillas/variables.vue', grupo: g.variables.id, orden: 1,
            destinos: [ID.estadAMaestro] }),
        f.linkOut('→ maestro (desde estadísticas)', ID.estadAMaestro, 880, 240, { hacia: [ID.aMaestro] }),
        // Estilo comun de las tablas de TODAS las paginas (alcance "site:style"). Va dentro de
        // una pestana: ui-template es un nodo comun y Node-RED no instancia uno sin "z".
        // Las tablas son <table> nativo y no <v-table>: Dashboard 2.0 parsea la plantilla con
        // el HTML del navegador, que saca los <tr> de un elemento que no es <table>.
        Object.assign(f.plantilla('estilo de las tablas', 620, 320, { archivo: 'plantillas/estilo.css', grupo: '', orden: 0 }),
            { templateScope: 'site:style', ui: ID.base, passthru: true }),
    ];
}

// =============================================================================
// Escritura
// =============================================================================

/** Genera todos los flows. @returns {Object<string, object[]>} archivo -> nodos */
function generar() {
    return {
        'dashboard-base.json': flujoDashboardBase(),
        'modbus-master.json': flujoMaestro(),
        'dashboard-config.json': flujoDashboardConfig(),
        'estadisticas.json': flujoEstadisticas(),
    };
}

/** JSON con el formato de exportacion de Node-RED (4 espacios). */
const serializar = (nodos) => JSON.stringify(nodos, null, 4) + '\n';

function main() {
    const flujos = generar();
    fs.mkdirSync(DESTINO, { recursive: true });
    for (const [archivo, nodos] of Object.entries(flujos)) {
        fs.writeFileSync(path.join(DESTINO, archivo), serializar(nodos), 'utf8');
        console.log(`flows/${archivo}: ${nodos.length} nodos`);
    }
    fs.mkdirSync(USER_DIR, { recursive: true });
    const combinado = Object.values(flujos).flat();
    fs.writeFileSync(path.join(USER_DIR, 'flows.json'), serializar(combinado), 'utf8');
    console.log(`${path.relative(RAIZ, path.join(USER_DIR, 'flows.json'))}: ${combinado.length} nodos (lo carga Node-RED)`);
}

if (require.main === module) main();

module.exports = { generar, serializar, ID };
