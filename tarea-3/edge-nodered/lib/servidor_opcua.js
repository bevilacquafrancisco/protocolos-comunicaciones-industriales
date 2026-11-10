/**
 * servidor_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-10
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Servidor OPC UA del dispositivo 2 (Fase F4). Publica el espacio de direcciones de
 * docs/diccionario-de-datos.md §3 con node-opcua usado desde un function node (ADR-011: el
 * nodo servidor de node-red-contrib-opcua no crea EURange y guarda claves en texto plano).
 * Adaptado de tarea-2/versiones/v3-node-red/node-red/servidor/servidor_opcua.js.
 *
 *   Objects/Dispositivo1/Inputs   Pulsador, Potenciometro, Potenciometro_pct  (solo lectura)
 *   Objects/Dispositivo1/Outputs  LedDigital, LedPWM                         (lectura y escritura)
 *   Objects/Dispositivo1/Status/MODBUS  Estado, OK, CRC_ERROR, TIMEOUT, EXCEPTION,
 *                                       UltimaTramaTx, UltimaTramaRx, LatenciaMs
 *   Objects/Dispositivo1/Status/OPCUA   Estado
 *   Objects/Dispositivo1/Mapa     variables que el maestro lee y no estan en el diccionario
 *                                 (las del esclavo desconocido, I-04), creadas al vuelo
 *
 * Reglas de veracidad ("no mentir sobre el estado"):
 *   - Una escritura sobre Outputs NO cambia el valor: llama al maestro (FC 05/06) y la
 *     respuesta OPC UA espera el ECO del esclavo (ADR-015). Si falla, el WriteResponse lleva
 *     el StatusCode del fallo y el Value queda como estaba.
 *   - Variable sin dato todavia: BadWaitingForInitialData. Esclavo no alcanzado:
 *     UncertainLastUsableValue (es el ultimo valor leido, no uno actual).
 *   - Status.OPCUA.Estado = DONE si el servidor corre y recibio datos del maestro hace menos
 *     de 5 s; ERROR si los datos estan vencidos (el servidor seguiria publicando valores viejos).
 *
 * Seguridad (ADR-009): endpoints None, Basic256Sha256 Sign y Basic256Sha256 SignAndEncrypt;
 * lista de confianza sin aceptacion automatica; usuario con hash scrypt; el anonimo lee y
 * navega pero no escribe (rolePermissions). Ver docs/seguridad-opcua.md.
 *
 * Diagrama: docs/diagramas/flujo-servidor-opcua.mmd, bloques [DF-5.x].
 *
 * Dependencias externas: node-opcua 2.160.0.
 */
'use strict';

const os = require('node:os');
const { verificarClave } = require('./credenciales');

/** Antiguedad maxima de los datos del maestro para declarar la capa sana. */
const DATOS_VENCIDOS_MS = 5000;

/**
 * Variables del dispositivo 1: el diccionario de datos §1 y §3 (I-06). "nombre" es el de la
 * metrica Sparkplug B y el del mapa del maestro; el NodeId es Dispositivo1.<carpeta>.<browse>.
 */
const VARIABLES = Object.freeze([
    { nombre: 'Inputs/Pulsador', carpeta: 'Inputs', browse: 'Pulsador', tipo: 'Boolean',
        descripcion: 'Pulsador del ESP32 (Discrete Input 10001, FC 02); true = presionado' },
    { nombre: 'Inputs/Potenciometro', carpeta: 'Inputs', browse: 'Potenciometro', tipo: 'UInt16',
        eu: { low: 0, high: 4095 }, descripcion: 'ADC crudo de 12 bits (Input Register 30001, FC 04)' },
    { nombre: 'Inputs/Potenciometro_pct', carpeta: 'Inputs', browse: 'Potenciometro_pct', tipo: 'Float',
        eu: { low: 0, high: 100 }, descripcion: 'Potenciometro en porcentaje, escalado en el borde (ADR-003)' },
    { nombre: 'Outputs/LedDigital', carpeta: 'Outputs', browse: 'LedDigital', tipo: 'Boolean', escritura: true,
        descripcion: 'LED digital (Coil 00001): lectura FC 01, escritura FC 05' },
    { nombre: 'Outputs/LedPWM', carpeta: 'Outputs', browse: 'LedPWM', tipo: 'UInt16', escritura: true,
        eu: { low: 0, high: 255 }, descripcion: 'LED PWM (Holding Register 40001): lectura FC 03, escritura FC 06' },
]);

/** Estado de la capa MODBus (diccionario §2) y de la capa OPC UA. */
const ESTADOS = Object.freeze([
    { clave: 'estado', carpeta: 'MODBUS', browse: 'Estado', tipo: 'String', inicial: 'DEVICE NOT REACHED' },
    { clave: 'OK', carpeta: 'MODBUS', browse: 'OK', tipo: 'UInt32', inicial: 0 },
    { clave: 'CRC_ERROR', carpeta: 'MODBUS', browse: 'CRC_ERROR', tipo: 'UInt32', inicial: 0 },
    { clave: 'TIMEOUT', carpeta: 'MODBUS', browse: 'TIMEOUT', tipo: 'UInt32', inicial: 0 },
    { clave: 'EXCEPTION', carpeta: 'MODBUS', browse: 'EXCEPTION', tipo: 'UInt32', inicial: 0 },
    { clave: 'ultimaTx', carpeta: 'MODBUS', browse: 'UltimaTramaTx', tipo: 'String', inicial: '' },
    { clave: 'ultimaRx', carpeta: 'MODBUS', browse: 'UltimaTramaRx', tipo: 'String', inicial: '' },
    { clave: 'latenciaMs', carpeta: 'MODBUS', browse: 'LatenciaMs', tipo: 'UInt16', inicial: 0 },
    { clave: 'opcua', carpeta: 'OPCUA', browse: 'Estado', tipo: 'String', inicial: 'ERROR' },
]);

/** Resultado de maestro.escribir() -> StatusCode del WriteResponse. */
const STATUS_POR_ERROR = Object.freeze({
    VALOR_INVALIDO: 'BadOutOfRange',          // fuera del min/max del mapa: no llego al bus
    NO_ESCRIBIBLE: 'BadNotWritable',
    DESCONOCIDA: 'BadNodeIdUnknown',          // la variable no esta en el mapa vigente (I-04)
    EXCEPTION: 'BadDeviceFailure',            // el esclavo respondio una excepcion MODBus
    TIMEOUT: 'BadCommunicationError',
    CRC_ERROR: 'BadCommunicationError',
    MALFORMED: 'BadCommunicationError',
    WRONG_SLAVE: 'BadCommunicationError',
    SUPERSEDED: 'BadRequestCancelledByClient', // otra orden mas nueva reemplazo a esta
    RECONFIGURADO: 'BadInvalidState',
    DETENIDO: 'BadServerHalted',
});

// =============================================================================
// [DF-5.1] Configuracion del servidor
// =============================================================================

/** IPv4 de las interfaces activas: se anuncian en GetEndpoints (no el nombre de host). */
function direccionesIPv4(interfaces = os.networkInterfaces()) {
    return Object.values(interfaces).flat().filter((i) => i && i.family === 'IPv4' && !i.internal).map((i) => i.address);
}

/**
 * Gestor de usuarios: valida contra el hash scrypt y asigna roles.
 * @param {object} opcua node-opcua
 * @param {{usuario: string, hashClave: string}|null} credenciales
 * @param {function(string): void} registrar
 * @returns {object} IUserManager de node-opcua
 */
function crearGestorUsuarios(opcua, credenciales, registrar, contadores) {
    return {
        isValidUserAsync(usuario, clave, callback) {
            if (!credenciales || usuario !== credenciales.usuario) {
                contadores.usuariosRechazados += 1;
                registrar(`ActivateSession rechazado: usuario desconocido "${usuario}"`);   // [SEC] sin la clave
                return callback(null, false);
            }
            verificarClave(clave, credenciales.hashClave).then((valida) => {
                if (!valida) contadores.usuariosRechazados += 1;
                registrar(`ActivateSession usuario "${usuario}": ${valida ? 'aceptado' : 'clave incorrecta'}`);
                callback(null, valida);
            });
        },
        getUserRoles(usuario) {
            if (credenciales && usuario === credenciales.usuario) {
                return opcua.makeRoles([opcua.WellKnownRoles.AuthenticatedUser, opcua.WellKnownRoles.Operator]);
            }
            return opcua.makeRoles([opcua.WellKnownRoles.Anonymous]);
        },
    };
}

// =============================================================================
// [DF-5.2] Espacio de direcciones
// =============================================================================

/**
 * Crea Dispositivo1/{Inputs,Outputs,Status/{MODBUS,OPCUA},Mapa} con NodeIds fijos.
 * @returns {{namespace: object, nodos: Map<string, object>, estados: Map<string, object>, carpetas: object}}
 */
function construirEspacio(opcua, addressSpace, namespaceUri) {
    const namespace = addressSpace.registerNamespace(namespaceUri);
    if (namespace.index !== 1) throw new Error(`se esperaba ns=1 para ${namespaceUri} y quedo ns=${namespace.index}`);
    const id = (s) => `ns=1;s=${s}`;
    const objeto = (padre, browse, nodeId, descripcion, organizado = false) => namespace.addObject(Object.assign(
        { browseName: browse, nodeId: id(nodeId), description: descripcion },
        organizado ? { organizedBy: padre } : { componentOf: padre }));

    const d1 = objeto(addressSpace.rootFolder.objects, 'Dispositivo1', 'Dispositivo1',
        'Esclavo MODBus RTU de la Tarea 1 (ESP32), leido por el maestro de este dispositivo', true);
    const carpetas = {
        Inputs: objeto(d1, 'Inputs', 'Dispositivo1.Inputs', 'Entradas del dispositivo 1 (solo lectura)'),
        Outputs: objeto(d1, 'Outputs', 'Dispositivo1.Outputs', 'Salidas: la escritura se confirma con el eco MODBus'),
    };
    const status = objeto(d1, 'Status', 'Dispositivo1.Status', 'Estado de las capas MODBus y OPC UA');
    carpetas.MODBUS = objeto(status, 'MODBUS', 'Status.MODBUS', 'Contadores y estado del maestro MODBus');
    carpetas.OPCUA = objeto(status, 'OPCUA', 'Status.OPCUA', 'Salud del servidor OPC UA');
    carpetas.Mapa = objeto(d1, 'Mapa', 'Dispositivo1.Mapa', 'Variables del mapa vigente que no estan en el diccionario (I-04)');

    const lectura = opcua.makeAccessLevelFlag('CurrentRead');
    const lecturaEscritura = opcua.makeAccessLevelFlag('CurrentRead | CurrentWrite');
    // El anonimo navega y lee; solo un usuario autenticado escribe (ADR-009).
    const P = opcua.PermissionType;
    const soloAutenticadosEscriben = [
        { roleId: opcua.WellKnownRoles.Anonymous, permissions: P.Browse | P.Read | P.ReadRolePermissions },
        { roleId: opcua.WellKnownRoles.AuthenticatedUser, permissions: P.Browse | P.Read | P.ReadRolePermissions | P.Write },
    ];

    const nodos = new Map();
    for (const v of VARIABLES) {
        const opciones = {
            componentOf: carpetas[v.carpeta], browseName: v.browse, nodeId: id(`Dispositivo1.${v.carpeta}.${v.browse}`),
            dataType: v.tipo, description: v.descripcion, minimumSamplingInterval: 100,
            accessLevel: v.escritura ? lecturaEscritura : lectura,
            userAccessLevel: v.escritura ? lecturaEscritura : lectura,
            rolePermissions: v.escritura ? soloAutenticadosEscriben : undefined,
        };
        // EURange: las analogicas son AnalogItemType (IEC 62541-8), que lleva la propiedad.
        const nodo = v.eu ? namespace.addAnalogDataItem(Object.assign(opciones, { engineeringUnitsRange: v.eu }))
            : namespace.addVariable(opciones);
        nodos.set(v.nombre, { def: v, nodo });
    }
    const estados = new Map();
    for (const e of ESTADOS) {
        const nodeId = e.carpeta === 'OPCUA' ? 'Status.OPCUA.Estado' : `Status.MODBUS.${e.browse}`;
        const nodo = namespace.addVariable({ componentOf: carpetas[e.carpeta], browseName: e.browse,
            nodeId: id(nodeId), dataType: e.tipo, accessLevel: lectura, userAccessLevel: lectura,
            minimumSamplingInterval: 100 });
        nodo.setValueFromSource({ dataType: opcua.DataType[e.tipo], value: e.inicial }, opcua.StatusCodes.Good);
        estados.set(e.clave, { def: e, nodo });
    }
    return { namespace, nodos, estados, carpetas };
}

// =============================================================================
// Ciclo de vida
// =============================================================================

/**
 * [DF-5.1] a [DF-5.6] Crea, configura y arranca el servidor.
 *
 * @param {object} p
 * @param {object} p.opcua                 modulo node-opcua
 * @param {number} p.puerto                4840 en produccion
 * @param {string} p.namespaceUri          urn:unraf:pdci:t3
 * @param {string} p.directorioPki         PKI del servidor (own/, trusted/, rejected/): FUERA del repositorio
 * @param {{usuario:string, hashClave:string}|null} p.credenciales
 * @param {boolean} [p.permitirAnonimo=true]
 * @param {function(string, *): Promise<{ok:boolean, errorType:string, error:string|null}>} p.escribir
 *        escritura MODBus del maestro (maestro.escribir)
 * @param {function(string): void} [p.registrar]
 * @param {function(): number} [p.ahora]
 * @returns {Promise<object>} controlador: publicarValor, publicarEstadoModbus, leerDataValue,
 *          estadisticas, endpoints, detener, servidor
 * @throws rechaza si el puerto esta ocupado o la PKI no se puede crear
 */
async function iniciarServidor({ opcua, puerto, namespaceUri, directorioPki, credenciales, permitirAnonimo = true,
    escribir, registrar = () => {}, ahora = () => Date.now() }) {
    const contadores = { escriturasOk: 0, escriturasRechazadas: 0, usuariosRechazados: 0 };
    let ultimoDatoMaestro = 0;

    // [DF-5.1] PKI: sin aceptacion automatica. Un certificado desconocido va a rejected/ y la
    // conexion segura falla hasta que alguien lo mueva a trusted/ (docs/seguridad-opcua.md).
    const gestorCertificados = new opcua.OPCUACertificateManager({
        rootFolder: directorioPki, automaticallyAcceptUnknownCertificate: false,
    });
    await gestorCertificados.initialize();

    const servidor = new opcua.OPCUAServer({
        port: puerto,
        resourcePath: '',
        alternateHostname: direccionesIPv4(),
        skipOwnNamespace: true,   // ns=1 = urn:unraf:pdci:t3, no la applicationUri
        serverInfo: {
            applicationUri: `urn:${os.hostname()}:unraf:pdci:t3:servidor`,
            productUri: 'urn:unraf:pdci:t3',
            applicationName: { text: 'UNRaf PdCI T3 - Dispositivo 2 (maestro MODBus + servidor OPC UA)', locale: 'es' },
        },
        buildInfo: { productName: 'UNRaf PdCI T3 Servidor', manufacturerName: 'Bevilacqua - Peralta', softwareVersion: '1.0' },
        // Tres endpoints (ADR-009): None/None y Basic256Sha256 con Sign y SignAndEncrypt.
        securityPolicies: [opcua.SecurityPolicy.None, opcua.SecurityPolicy.Basic256Sha256],
        securityModes: [opcua.MessageSecurityMode.None, opcua.MessageSecurityMode.Sign,
            opcua.MessageSecurityMode.SignAndEncrypt],
        allowAnonymous: permitirAnonimo,
        serverCertificateManager: gestorCertificados,
        userManager: crearGestorUsuarios(opcua, credenciales, registrar, contadores),
        // Dispositivo 3 + UaExpert + margen; acota memoria ante sesiones abandonadas (STRIDE: DoS).
        serverCapabilities: { maxSessions: 6 },
    });
    await servidor.initialize();
    const { namespace, nodos, estados, carpetas } = construirEspacio(opcua, servidor.engine.addressSpace, namespaceUri);

    // ---------------------------------------------------------------- valores
    // Cada variable guarda su DataValue; las Outputs lo exponen con timestamped_get.
    const valores = new Map();
    const tipoUa = (t) => opcua.DataType[t];
    const dataValue = (tipo, valor, codigo, ts) => new opcua.DataValue({
        value: { dataType: tipoUa(tipo), value: valor }, statusCode: codigo, sourceTimestamp: ts, serverTimestamp: new Date() });
    const valorInicial = (tipo) => (tipo === 'Boolean' ? false : 0);

    for (const [nombre, { def, nodo }] of nodos) {
        valores.set(nombre, dataValue(def.tipo, valorInicial(def.tipo), opcua.StatusCodes.BadWaitingForInitialData, new Date()));
        if (!def.escritura) {
            nodo.setValueFromSource(valores.get(nombre).value, opcua.StatusCodes.BadWaitingForInitialData);
            continue;
        }
        // [DF-5.4] Escritura sobre Outputs: node-opcua ya verifico tipo (BadTypeMismatch),
        // AccessLevel (BadNotWritable) y rol (BadUserAccessDenied). Aca se ordena la escritura
        // MODBus y se responde con su resultado. El valor NO cambia hasta el eco del esclavo.
        nodo.bindVariable({
            timestamped_get: () => valores.get(nombre),
            timestamped_set: async (dv) => {
                const pedido = dv.value.value;
                let r;
                try {
                    r = await escribir(nombre, pedido);
                } catch (e) {
                    r = { ok: false, errorType: 'ERROR', error: e.message };
                }
                if (r && r.ok) {
                    contadores.escriturasOk += 1;
                    // Confirmado por el eco (FC 05/06): se publica el valor escrito; la lectura
                    // siguiente lo vuelve a confirmar desde el registro del esclavo.
                    valores.set(nombre, dataValue(def.tipo, pedido, opcua.StatusCodes.Good, new Date()));
                    registrar(`Write ${nombre} = ${pedido}: Good (eco MODBus)`);
                    return opcua.StatusCodes.Good;
                }
                contadores.escriturasRechazadas += 1;
                const codigo = opcua.StatusCodes[STATUS_POR_ERROR[r && r.errorType]] || opcua.StatusCodes.BadCommunicationError;
                registrar(`Write ${nombre} = ${pedido}: ${codigo.name} (${r && r.error})`);
                return codigo;
            },
        }, true);
    }

    // [DF-5.5] Variables del mapa que no estan en el diccionario (esclavo desconocido, I-04).
    const extras = new Map();
    function variableExtra(nombre, valor) {
        if (extras.has(nombre)) return extras.get(nombre);
        const tipo = typeof valor === 'boolean' ? 'Boolean' : 'Double';
        const browse = nombre.replace(/[^A-Za-z0-9_]/g, '_');
        const nodo = namespace.addVariable({ componentOf: carpetas.Mapa, browseName: browse,
            nodeId: `ns=1;s=Dispositivo1.Mapa.${browse}`, dataType: tipo,
            accessLevel: opcua.makeAccessLevelFlag('CurrentRead'), userAccessLevel: opcua.makeAccessLevelFlag('CurrentRead'),
            minimumSamplingInterval: 100, description: `Variable "${nombre}" del mapa vigente del maestro` });
        const extra = { nodo, tipo };
        extras.set(nombre, extra);
        registrar(`variable del mapa publicada: ns=1;s=Dispositivo1.Mapa.${browse}`);
        return extra;
    }

    // ---------------------------------------------------------------- sesiones
    servidor.on('create_session', (s) => {
        const c = s.channel || {};
        registrar(`CreateSession desde ${c.remoteAddress} modo=${opcua.MessageSecurityMode[c.securityMode]} `
            + `politica=${String(c.securityPolicy).split('#').pop()}`);
    });
    servidor.on('session_closed', (s, motivo) => registrar(`Sesion cerrada: ${motivo}`));

    await servidor.start();
    registrar(`servidor OPC UA en opc.tcp://<ip>:${puerto} (${servidor.endpoints.length} endpoint(s) de red)`);

    // ---------------------------------------------------------------- API
    /**
     * [DF-5.3] Publica un valor leido por el maestro.
     * @param {string} nombre nombre del mapa (= metrica Sparkplug B)
     * @param {*} valor
     * @param {'good'|'bad'} calidad 'bad' = esclavo no alcanzado
     * @param {number} [ts] instante de la lectura (SourceTimestamp)
     */
    function publicarValor(nombre, valor, calidad, ts = ahora()) {
        ultimoDatoMaestro = ahora();
        const codigo = calidad === 'good' ? opcua.StatusCodes.Good : opcua.StatusCodes.UncertainLastUsableValue;
        const entrada = nodos.get(nombre);
        if (!entrada) {
            if (typeof valor !== 'boolean' && typeof valor !== 'number') return;
            const extra = variableExtra(nombre, valor);
            extra.nodo.setValueFromSource({ dataType: tipoUa(extra.tipo), value: valor }, codigo, new Date(ts));
            return;
        }
        const { def, nodo } = entrada;
        const dv = dataValue(def.tipo, def.tipo === 'Boolean' ? Boolean(valor) : Number(valor), codigo, new Date(ts));
        valores.set(nombre, dv);
        if (!def.escritura) nodo.setValueFromSource(dv.value, codigo, new Date(ts));
        else nodo.touchValue && nodo.touchValue();
    }

    /**
     * [DF-5.3] Publica la instantanea del maestro en Status.MODBUS.* y evalua Status.OPCUA.Estado.
     * @param {object} s maestro.instantanea()
     */
    function publicarEstadoModbus(s) {
        ultimoDatoMaestro = ahora();
        const fuente = { estado: s.estado, OK: s.contadores.OK, CRC_ERROR: s.contadores.CRC_ERROR,
            TIMEOUT: s.contadores.TIMEOUT, EXCEPTION: s.contadores.EXCEPTION, ultimaTx: s.ultimaTx || '',
            ultimaRx: s.ultimaRx || '', latenciaMs: Math.min(0xFFFF, Math.max(0, Math.round(s.latenciaMs || 0))) };
        for (const [clave, valor] of Object.entries(fuente)) {
            const { def, nodo } = estados.get(clave);
            nodo.setValueFromSource({ dataType: tipoUa(def.tipo), value: valor }, opcua.StatusCodes.Good);
        }
        evaluarSalud();
    }

    /** [DF-5.6] Status.OPCUA.Estado: DONE o ERROR segun la frescura de los datos. */
    function evaluarSalud() {
        const sano = ahora() - ultimoDatoMaestro < DATOS_VENCIDOS_MS;
        const { nodo } = estados.get('opcua');
        const valor = sano ? 'DONE' : 'ERROR';
        if (nodo.readValue().value.value !== valor) {
            nodo.setValueFromSource({ dataType: opcua.DataType.String, value: valor }, opcua.StatusCodes.Good);
            registrar(`Status.OPCUA.Estado = ${valor}`);
        }
        return valor;
    }

    /** Contadores de la capa OPC UA para el panel de las cuatro capas (I-05). */
    function estadisticas() {
        const r = servidor.engine.serverDiagnosticsSummary;
        return {
            estado: evaluarSalud(),
            contadores: {
                sesiones: r.currentSessionCount,
                suscripciones: r.currentSubscriptionCount,
                sesionesRechazadas: r.rejectedSessionCount,
                rechazosSeguridad: r.securityRejectedSessionCount,
                escriturasOk: contadores.escriturasOk,
                escriturasRechazadas: contadores.escriturasRechazadas,
            },
            detalle: { usuariosRechazados: contadores.usuariosRechazados, sesionesTotales: r.cumulatedSessionCount },
        };
    }

    // ---------------------------------------------------------------- lista de confianza
    // [DF-5.7] El gestor de certificados de node-opcua indexa las carpetas AL INICIAR y despues
    // mantiene el estado en memoria: mover un archivo de rejected/ a trusted/ con el servidor
    // corriendo NO alcanza (medido: sigue rechazando). Dos caminos validos: mover el archivo y
    // reiniciar Node-RED, o estas funciones, que usan la API del gestor y aplican en vivo.
    const crypto = require('node-opcua-crypto');
    const fs = require('node:fs');
    const path = require('node:path');
    const carpeta = (sub) => path.join(gestorCertificados.rootDir, sub);

    /** Certificados de clientes en rejected/ y trusted/certs/, con huella SHA-1 y sujeto. */
    function listarCertificados() {
        const leerCarpeta = (dir) => (fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /\.(pem|der)$/.test(f)) : [])
            .map((archivo) => {
                const der = crypto.readCertificate(path.join(dir, archivo));
                const info = crypto.exploreCertificate(der);
                return { archivo, huella: crypto.makeSHA1Thumbprint(der).toString('hex'),
                    sujeto: info.tbsCertificate.subject.commonName || archivo,
                    applicationUri: (info.tbsCertificate.extensions && info.tbsCertificate.extensions.subjectAltName
                        && (info.tbsCertificate.extensions.subjectAltName.uniformResourceIdentifier || [])[0]) || '',
                    venceEl: info.tbsCertificate.validity.notAfter };
            });
        return { rechazados: leerCarpeta(carpeta('rejected')), confiables: leerCarpeta(carpeta(path.join('trusted', 'certs'))) };
    }

    /**
     * Confia en un certificado rechazado, identificado por su huella (que el operador debe
     * comparar con la que muestra el cliente antes de confiar: es lo que impide confiar en
     * un impostor).
     * @param {string} huella SHA-1 en hexadecimal
     * @returns {Promise<{ok:boolean, error?:string}>}
     */
    async function confiarCertificado(huella) {
        const c = listarCertificados().rechazados.find((x) => x.huella === String(huella).toLowerCase());
        if (!c) return { ok: false, error: `no hay un certificado rechazado con huella ${huella}` };
        await gestorCertificados.trustCertificate(crypto.readCertificate(path.join(carpeta('rejected'), c.archivo)));
        registrar(`certificado confiado: ${c.sujeto} (${c.huella})`);
        return { ok: true };
    }

    /** Revoca la confianza (lo pasa a rejected/). @returns {Promise<{ok:boolean, error?:string}>} */
    async function revocarCertificado(huella) {
        const c = listarCertificados().confiables.find((x) => x.huella === String(huella).toLowerCase());
        if (!c) return { ok: false, error: `no hay un certificado confiado con huella ${huella}` };
        await gestorCertificados.rejectCertificate(crypto.readCertificate(path.join(carpeta(path.join('trusted', 'certs')), c.archivo)));
        registrar(`certificado revocado: ${c.sujeto} (${c.huella})`);
        return { ok: true };
    }

    return {
        publicarValor,
        publicarEstadoModbus,
        evaluarSalud,
        estadisticas,
        listarCertificados,
        confiarCertificado,
        revocarCertificado,
        huellaPropia: () => crypto.makeSHA1Thumbprint(servidor.getCertificate()).toString('hex'),
        leerDataValue: (nombre) => (nodos.has(nombre) ? valores.get(nombre) : null),
        endpoints: () => servidor.endpoints.flatMap((e) => e.endpointDescriptions()).map((d) =>
            `${d.endpointUrl}  ${opcua.MessageSecurityMode[d.securityMode]}  ${String(d.securityPolicyUri).split('#').pop()}`),
        detener: (demoraMs = 0) => servidor.shutdown(demoraMs),
        servidor,
    };
}

module.exports = Object.freeze({ VARIABLES, ESTADOS, STATUS_POR_ERROR, DATOS_VENCIDOS_MS, iniciarServidor, direccionesIPv4 });
