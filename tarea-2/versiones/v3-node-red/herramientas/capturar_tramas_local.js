/**
 * capturar_tramas_local.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Genera vectores de prueba REALES para opcua_tramas.py sin hardware ni
 * Wireshark: levanta el servidor (servidor_opcua.js) y el cliente
 * (cliente_opcua.js) en la PC, intercala un proxy TCP entre ambos y guarda
 * cada mensaje UA TCP completo que pasa en cada sentido.
 *
 * El proxy reensambla el flujo TCP usando el campo MessageSize de la
 * cabecera, que es exactamente como un receptor OPC UA delimita los mensajes
 * dentro del flujo de bytes (TCP no conserva limites de mensaje).
 *
 * Salida: herramientas/vectores/sesion_<modo>.json con la constante de
 * version de node-opcua, los identificadores numericos y StatusCodes que usa
 * la pila (para contrastar las tablas de opcua_tramas.py) y la lista de
 * mensajes { t_ms, sentido, hex }.
 *
 * NO reemplaza la captura con tcpdump de la Parte 4: aca no hay Ethernet,
 * IP ni TCP reales, ni la temporizacion del enlace. Sirve para desarrollar y
 * verificar el decodificador antes de llegar al banco.
 *
 * Uso
 * ---
 *     NODE_PATH=<node_modules con node-opcua> node tarea-2/herramientas/capturar_tramas_local.js [None|Sign|SignAndEncrypt]
 *
 * Dependencias externas: node-opcua 2.x (probado con 2.160.0).
 */
'use strict';

const net = require('node:net');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const opcua = require('node-opcua');

const RAIZ = path.join(__dirname, '..', 'node-red');
const configBase = require(path.join(RAIZ, 'comun', 'config.js'));
const { iniciarServidor } = require(path.join(RAIZ, 'servidor', 'servidor_opcua.js'));
const { iniciarCliente } = require(path.join(RAIZ, 'cliente', 'cliente_opcua.js'));

const PUERTO_SERVIDOR = 48410;
const PUERTO_PROXY = 48411;
const modo = process.argv[2] || 'None';
// Opciones adicionales (en cualquier orden despues del modo):
//   usuario  -> sesion con UserNameIdentityToken (Parte 4.9). La clave es
//               efimera y aleatoria: no queda en ningun archivo.
//   lecturaA -> Modo A (Read periodico) en lugar del Modo B (suscripcion).
//   regimen  -> 10 s con la rampa en movimiento y sin escrituras: sirve para
//               comparar tramas y bytes por segundo entre Modo A y Modo B
//               (Parte 3.4) antes de medir en el banco.
//   quieto   -> con 'regimen': la rampa NO cambia durante los 10 s (escenario
//               de la consigna para observar los KeepAlive).
const opciones = new Set(process.argv.slice(3));
const conUsuario = opciones.has('usuario');
const lecturaA = opciones.has('lecturaA');
const regimen = opciones.has('regimen');
const quieto = opciones.has('quieto');

/**
 * Descripcion: separa un flujo de bytes en mensajes UA TCP completos.
 * Parametros:
 *   acumulado (Buffer): bytes pendientes de este sentido.
 * Retorna: ({ mensajes: Buffer[], resto: Buffer })
 * Excepciones: ninguna; un MessageSize absurdo descarta el flujo.
 */
function separarMensajes(acumulado) {
    const mensajes = [];
    let resto = acumulado;
    while (resto.length >= 8) {
        const tamano = resto.readUInt32LE(4);
        if (tamano < 8 || tamano > 16 * 1024 * 1024) return { mensajes, resto: Buffer.alloc(0) };
        if (resto.length < tamano) break;
        mensajes.push(resto.subarray(0, tamano));
        resto = resto.subarray(tamano);
    }
    return { mensajes, resto };
}

async function main() {
    const t0 = Date.now();
    const registro = [];

    // ---- proxy TCP --------------------------------------------------------
    const proxy = net.createServer((desdeCliente) => {
        const haciaServidor = net.connect(PUERTO_SERVIDOR, '127.0.0.1');
        const pendiente = { 'C->S': Buffer.alloc(0), 'S->C': Buffer.alloc(0) };
        const anotar = (sentido) => (datos) => {
            const r = separarMensajes(Buffer.concat([pendiente[sentido], datos]));
            pendiente[sentido] = r.resto;
            for (const m of r.mensajes) registro.push({ t_ms: Date.now() - t0, sentido, hex: m.toString('hex') });
        };
        desdeCliente.on('data', anotar('C->S'));
        haciaServidor.on('data', anotar('S->C'));
        desdeCliente.pipe(haciaServidor).pipe(desdeCliente);
        desdeCliente.on('error', () => haciaServidor.destroy());
        haciaServidor.on('error', () => desdeCliente.destroy());
    });
    await new Promise((r) => proxy.listen(PUERTO_PROXY, '127.0.0.1', r));

    // ---- servidor y cliente ----------------------------------------------
    const pki = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-t2-captura-'));
    const config = JSON.parse(JSON.stringify(configBase));
    config.red.puertoOpcUa = PUERTO_SERVIDOR;
    config.opcua.endpointCliente = 'opc.tcp://127.0.0.1:' + PUERTO_PROXY;
    config.seguridad.aceptarCertificadosDesconocidos = true; // solo en la PC
    config.seguridad.modoCliente = modo;
    config.seguridad.politicaCliente = modo === 'None' ? 'None' : 'Basic256Sha256';
    config.lectura.modo = lecturaA ? 'A' : 'B';

    let credenciales = null;
    let entorno = {};
    if (conUsuario) {
        const clave = require('node:crypto').randomBytes(12).toString('base64');
        const { hashearClave } = require(path.join(RAIZ, 'comun', 'credenciales.js'));
        credenciales = { usuario: 'operador', hashClave: await hashearClave(clave) };
        entorno = { OPCUA_CLIENTE_USUARIO: 'operador', OPCUA_CLIENTE_CLAVE: clave };
        config.seguridad.autenticacionCliente = 'usuario';
    }

    const servidor = await iniciarServidor({ opcua, config, directorioPki: path.join(pki, 's'), credenciales });
    const cliente = await iniciarCliente({ opcua, config, directorioPki: path.join(pki, 'c'), entorno });

    if (regimen) {
        // 10 s de rampa en movimiento (un valor nuevo cada 50 ms, como S3),
        // sin escrituras: solo el trafico de lectura que se compara.
        for (let i = 0; i < 200; i++) {
            if (!quieto) servidor.publicarRampa((i * 819) % 65536);
            await new Promise((r) => setTimeout(r, 50));
        }
    } else {
        // 1,5 s con rampa en movimiento, dos escrituras de cada tipo, y 2,5 s
        // con todo quieto para que aparezcan los KeepAlive (MaxKeepAliveCount = 10).
        for (let i = 0; i < 30; i++) {
            servidor.publicarRampa((i * 2185) % 65536);
            await new Promise((r) => setTimeout(r, 50));
        }
        await cliente.escribirRampa(0x1234);
        await cliente.escribirPulsador(true);
        await cliente.escribirRampa(0xABCD);
        await cliente.escribirPulsador(false);
        await new Promise((r) => setTimeout(r, 2500));
    }

    await cliente.detener();
    await servidor.detener();
    proxy.close();
    fs.rmSync(pki, { recursive: true, force: true });

    // ---- constantes de la pila, para contrastar las tablas de Python -------
    const nombres = ['ReadRequest', 'ReadResponse', 'WriteRequest', 'WriteResponse', 'PublishRequest',
        'PublishResponse', 'CreateSubscriptionRequest', 'CreateMonitoredItemsRequest',
        'OpenSecureChannelRequest', 'CloseSecureChannelRequest', 'CreateSessionRequest',
        'ActivateSessionRequest', 'CloseSessionRequest', 'GetEndpointsRequest', 'DataChangeNotification',
        'ServiceFault', 'UserNameIdentityToken', 'AnonymousIdentityToken'];
    const constantes = {};
    for (const n of nombres) constantes[n] = opcua.ObjectIds[n + '_Encoding_DefaultBinary'];
    const status = {};
    for (const n of ['BadNotWritable', 'BadTypeMismatch', 'BadUserAccessDenied', 'BadSecureChannelClosed',
        'BadConnectionClosed', 'BadSessionIdInvalid', 'BadTimeout', 'BadNoSubscription',
        'BadIdentityTokenRejected', 'BadSecurityChecksFailed', 'BadCertificateUntrusted', 'BadOutOfRange']) {
        status[n] = opcua.StatusCodes[n].value;
    }

    const destino = path.join(__dirname, 'vectores');
    fs.mkdirSync(destino, { recursive: true });
    const sufijo = (conUsuario ? '_usuario' : '') + (lecturaA ? '_lecturaA' : '') + (regimen ? '_regimen' : '') + (quieto ? '_quieto' : '');
    const archivo = path.join(destino, 'sesion_' + modo + sufijo + '.json');
    fs.writeFileSync(archivo, JSON.stringify({
        generado_por: 'capturar_tramas_local.js (proxy TCP en 127.0.0.1, NO es una captura de banco)',
        node_opcua: require('node-opcua/package.json').version,
        modo_seguridad: modo,
        autenticacion: conUsuario ? 'usuario' : 'anonimo',
        lectura: config.lectura.modo,
        regimen,
        quieto,
        constantes, status,
        mensajes: registro,
    }, null, 1));
    console.log('Mensajes capturados: ' + registro.length + ' -> ' + archivo);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
