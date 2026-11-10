/**
 * settings.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Configuracion de Node-RED para el dispositivo 2 (Tarea 3). Lo esencial:
 *
 *   - functionGlobalContext.pdci: los modulos propios (lib/) que usan los function nodes. El
 *     protocolo MODBus vive en lib/modbus.js, NO en un nodo de la paleta (I-01).
 *   - contextStorage: "memory" por defecto y "archivo" (localfilesystem) para lo que debe
 *     sobrevivir a un reinicio: los contadores MODBus.
 *   - Editor y Dashboard escuchan por defecto SOLO en 127.0.0.1: se accede por tunel SSH,
 *     como en la Tarea 2. Para abrirlos en la LAN: PDCI_T3_UI_HOST=0.0.0.0 y, entonces,
 *     credenciales obligatorias (ver abajo).
 *
 * Variables de entorno (ninguna es obligatoria en desarrollo):
 *   PDCI_T3_USERDIR          carpeta de datos de Node-RED (por defecto ./.node-red)
 *   PDCI_T3_CONFIG           archivo de configuracion del maestro (por defecto <userDir>/pdci-t3-config.json)
 *   PDCI_T3_UI_HOST          interfaz de escucha (por defecto 127.0.0.1)
 *   PDCI_T3_ADMIN_USUARIO / PDCI_T3_ADMIN_HASH  usuario del editor y su hash bcrypt
 *                            (node-red admin hash-pw). [SEC] Nunca la contrasena en claro.
 *   PDCI_T3_UI_USUARIO / PDCI_T3_UI_HASH        idem para el Dashboard (httpNodeAuth)
 *   PDCI_T3_OPCUA_PUERTO     puerto del servidor OPC UA (por defecto 4840)
 *   PDCI_T3_OPCUA_PKI        PKI del servidor OPC UA (por defecto <userDir>/opcua-pki). FUERA del repo.
 *   PDCI_T3_OPCUA_USUARIO / PDCI_T3_OPCUA_HASH  usuario OPC UA con permiso de escritura y su hash
 *                            scrypt (node tools/generar_hash_opcua.js). Sin ellos solo hay anonimo
 *                            (lectura): nadie puede escribir Outputs.
 *
 * Uso
 *   desarrollo:  npm start                     (en tarea-3/edge-nodered)
 *   Raspberry:   node-red --settings /ruta/a/tarea-3/edge-nodered/settings.js
 *
 * Dependencias externas: node-red 4.1, @flowfuse/node-red-dashboard 1.33, node-red-node-serialport 2.0, node-opcua 2.160.
 */
'use strict';

const path = require('node:path');
const { MaestroModbus, ESTADO } = require('./lib/maestro');
const { RegistroCapas, Historial } = require('./lib/estadisticas');

const RAIZ = __dirname;
const USER_DIR = process.env.PDCI_T3_USERDIR || path.join(RAIZ, '.node-red');
const UI_HOST = process.env.PDCI_T3_UI_HOST || '127.0.0.1';
const expuesto = UI_HOST !== '127.0.0.1' && UI_HOST !== 'localhost';

/** Usuario + hash bcrypt desde el entorno, o null. */
function credencial(prefijo) {
    const usuario = process.env[`${prefijo}_USUARIO`];
    const hash = process.env[`${prefijo}_HASH`];
    return usuario && hash ? { usuario, hash } : null;
}
const admin = credencial('PDCI_T3_ADMIN');
const ui = credencial('PDCI_T3_UI');
const opcuaUsuario = credencial('PDCI_T3_OPCUA');

// [SEC] Fuera de 127.0.0.1, sin credenciales no se arranca: un maestro MODBus accesible en la
// red sin autenticacion permitiria escribir salidas de campo a cualquiera (IEC 62443, SR 1.1).
if (expuesto && (!admin || !ui)) {
    throw new Error('PDCI_T3_UI_HOST expone Node-RED en la red: definir PDCI_T3_ADMIN_USUARIO/HASH '
        + 'y PDCI_T3_UI_USUARIO/HASH (hash bcrypt: npx node-red admin hash-pw)');
}

module.exports = {
    userDir: USER_DIR,
    flowFile: 'flows.json',
    flowFilePretty: true,
    uiPort: Number(process.env.PORT) || 1880,
    uiHost: UI_HOST,

    adminAuth: admin ? {
        type: 'credentials',
        users: [{ username: admin.usuario, password: admin.hash, permissions: '*' }],
    } : undefined,
    httpNodeAuth: ui ? { user: ui.usuario, pass: ui.hash } : undefined,

    functionGlobalContext: {
        pdci: {
            modbus: require('./lib/modbus'),
            tipos: require('./lib/tipos'),
            configuracion: require('./lib/configuracion'),
            transportes: require('./lib/transportes'),
            MaestroModbus,
            ESTADO,
            capas: new RegistroCapas(),
            historial: new Historial(200),
            // Servidor OPC UA (F4, ADR-011/ADR-019): node-opcua usado desde el function node O1.
            servidorOpcua: require('./lib/servidor_opcua'),
            nodeOpcua: require('node-opcua'),
            opcua: Object.freeze({
                puerto: Number(process.env.PDCI_T3_OPCUA_PUERTO) || 4840,
                namespaceUri: 'urn:unraf:pdci:t3',
                directorioPki: process.env.PDCI_T3_OPCUA_PKI || path.join(USER_DIR, 'opcua-pki'),
                credenciales: opcuaUsuario ? { usuario: opcuaUsuario.usuario, hashClave: opcuaUsuario.hash } : null,
            }),
            rutas: {
                config: process.env.PDCI_T3_CONFIG || path.join(USER_DIR, 'pdci-t3-config.json'),
            },
        },
    },
    // Los function nodes solo usan lo de functionGlobalContext, revisado en este archivo.
    functionExternalModules: false,

    contextStorage: {
        default: { module: 'memory' },
        archivo: { module: 'localfilesystem', config: { flushInterval: 10 } },
    },

    // Los flows no guardan credenciales (los secretos van por variables de entorno, ver arriba):
    // sin cifrado de credenciales se evita depender de una clave autogenerada que, si se
    // pierde al regrabar la microSD, vuelve ilegible el archivo.
    credentialSecret: false,

    logging: { console: { level: 'info', metrics: false, audit: false } },
    editorTheme: { projects: { enabled: false }, tours: false },
    diagnostics: { enabled: false },
    telemetry: { enabled: false },
    exportGlobalContextKeys: false,
};
