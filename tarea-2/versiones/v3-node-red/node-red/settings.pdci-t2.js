/**
 * settings.pdci-t2.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Agregado al settings.js de Node-RED de cada Raspberry Pi. Carga en
 * functionGlobalContext los modulos del trabajo (config, senales, node-opcua,
 * servidor/cliente OPC UA) y define la configuracion de seguridad del editor.
 *
 * Instalacion (detalle en node-red/README.md §8): en ~/.node-red/settings.js
 *
 *     const pdci = require('/home/pdci/pdci-t2/settings.pdci-t2.js');   // 1.a linea
 *     module.exports = {
 *         ...todo el contenido original...
 *         ...pdci.ajustes,          // ULTIMA linea antes de la llave de cierre
 *     };
 *
 * Va AL FINAL porque el settings.js que instala Node-RED ya trae
 * functionGlobalContext: {} y functionExternalModules: true sin comentar; en
 * un objeto literal gana la ultima clave, asi que al final estas reemplazan a
 * aquellas sin tener que editar el archivo original.
 *
 * [SEC] Ningun secreto vive en este archivo ni en el repositorio: todo sale
 * de variables de entorno que systemd carga desde /etc/nodered-pdci.env
 * (permisos 600). Ver .env.ejemplo.
 *
 * Dependencias externas: node-opcua@2.160.0 instalado en ~/.node-red.
 */
'use strict';

const os = require('node:os');
const path = require('node:path');

const RAIZ = __dirname; // copia de tarea-2/node-red en la placa
const DIR_USUARIO = process.env.NODE_RED_USERDIR || path.join(os.homedir(), '.node-red');

// node-opcua se instala en ~/.node-red (npm install en esa carpeta), no
// junto a este archivo: se resuelve explicitamente desde ahi.
const opcua = require(require.resolve('node-opcua', { paths: [DIR_USUARIO, RAIZ] }));

/**
 * Descripcion: devuelve config.js. Solo para pruebas en la PC se admite
 *   PDCI_T2_CONFIG_EXTRA (JSON) para cambiar, por ejemplo, el endpoint a
 *   127.0.0.1 o el modo de lectura sin editar config.js. En las placas esa
 *   variable no se define.
 * Retorna: (object) configuracion congelada.
 * Excepciones: SyntaxError si PDCI_T2_CONFIG_EXTRA no es JSON valido.
 */
function cargarConfig() {
    const base = require(path.join(RAIZ, 'comun', 'config.js'));
    const extra = process.env.PDCI_T2_CONFIG_EXTRA;
    if (!extra) return base;
    const copia = JSON.parse(JSON.stringify(base));
    for (const [seccion, valores] of Object.entries(JSON.parse(extra))) Object.assign(copia[seccion], valores);
    console.warn('[pdci-t2] ATENCION: config modificada por PDCI_T2_CONFIG_EXTRA (solo pruebas): ' + extra);
    return Object.freeze(copia);
}

const PKI = process.env.PDCI_T2_PKI || path.join(DIR_USUARIO, 'opcua-pki');

// [SEC] adminAuth: sin credenciales, cualquiera que alcance el puerto 1880
// puede cambiar los flujos, es decir, ejecutar codigo arbitrario en la placa.
// El hash bcrypt se genera con: node-red admin hash-pw
const adminAuth = process.env.NODE_RED_ADMIN_USER && process.env.NODE_RED_ADMIN_HASH ? {
    type: 'credentials',
    users: [{ username: process.env.NODE_RED_ADMIN_USER, password: process.env.NODE_RED_ADMIN_HASH, permissions: '*' }],
} : undefined;
if (!adminAuth) console.warn('[pdci-t2] ATENCION: editor sin adminAuth (definir NODE_RED_ADMIN_USER y NODE_RED_ADMIN_HASH)');

// Los dos hashes contienen '$'. Si el archivo de entorno se cargara con una
// shell en vez de systemd, '$2b' o '$131072' se expandirian a vacio y el hash
// llegaria mutilado: se detecta aca y no como "clave incorrecta" misteriosa.
if (process.env.NODE_RED_ADMIN_HASH && !/^\$2[aby]\$\d\d\$.{53}$/.test(process.env.NODE_RED_ADMIN_HASH)) {
    console.warn('[pdci-t2] ATENCION: NODE_RED_ADMIN_HASH no parece un hash bcrypt (se perdieron los "$"?)');
}
if (process.env.OPCUA_CLAVE_HASH && process.env.OPCUA_CLAVE_HASH.split('$').length !== 6) {
    console.warn('[pdci-t2] ATENCION: OPCUA_CLAVE_HASH mal formado (se perdieron los "$"?)');
}

module.exports = {
    ajustes: {
        // [SEC] El editor escucha solo en loopback: desde la PC se accede con
        // un tunel SSH (ssh -L 1880:localhost:1880 pi@<ip-wifi>). El puerto
        // 1880 no queda expuesto en la red Wi-Fi.
        uiHost: process.env.PDCI_T2_UI_HOST || '127.0.0.1',
        adminAuth,
        // Cifra flows_cred.json; sin esto Node-RED usa una clave generada
        // que se guarda en texto plano junto a los flujos.
        credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET || false,
        functionGlobalContext: {
            config: cargarConfig(),
            senales: require(path.join(RAIZ, 'comun', 'senales.js')),
            opcua,
            servidorOpcua: require(path.join(RAIZ, 'servidor', 'servidor_opcua.js')),
            clienteOpcua: require(path.join(RAIZ, 'cliente', 'cliente_opcua.js')),
            pdciRutas: Object.freeze({
                pkiServidor: path.join(PKI, 'servidor'),
                pkiCliente: path.join(PKI, 'cliente'),
            }),
            // [SEC] Funcion y no objeto: el editor muestra el contexto global
            // en la barra lateral; una funcion aparece como [Function] y el
            // hash no queda a la vista.
            pdciCredencialesServidor: () => ({
                usuario: process.env.OPCUA_USUARIO,
                hashClave: process.env.OPCUA_CLAVE_HASH,
            }),
        },
        // Las function nodes no pueden instalar modulos por su cuenta: todo
        // lo que usan pasa por functionGlobalContext, revisado en este archivo.
        functionExternalModules: false,
    },
};
