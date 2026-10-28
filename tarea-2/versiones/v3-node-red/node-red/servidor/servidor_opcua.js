/**
 * servidor_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Servidor OPC UA de la Raspberry Pi 1 (consigna Parte 2). Construye el
 * servidor con node-opcua, publica el modelo de informacion con NodeIds fijos
 * y avisa a Node-RED cada vez que el cliente escribe una variable.
 *
 * Node-RED orquesta (temporizadores, GPIO, consola) y este modulo implementa la
 * pila OPC UA. La function node "S2 · Servidor OPC UA" lo carga por
 * functionGlobalContext. Por que node-opcua directo y no los nodos servidor de
 * la paleta, ver docs/arquitectura-red.md §8 (ADR-01): el Compact-Server acepta
 * cualquier contrasena y depende de vm2 (vulnerabilidades criticas); el nodo
 * OpcUa-Server guarda las claves en texto plano.
 *
 * Es la misma API que usa el material de clase (diapositiva 32:
 * namespace.addVariable, Variant, DataType).
 *
 * Bloques del diagrama diagramas/flujo_servidor.md implementados aca:
 *   S1 (parte OPC UA), S2, S5.
 *
 * Dependencias externas
 * ---------------------
 * node-opcua 2.x (probado con 2.160.0). Se instala en ~/.node-red con
 *   npm install node-opcua@2.160.0
 */
'use strict';

const os = require('node:os');
const path = require('node:path');
const { verificarClave } = require('../comun/credenciales.js');

// ==========================================================================
// BLOQUE S1 — Configuracion del servidor
// ==========================================================================

/**
 * Descripcion: direcciones IPv4 de todas las interfaces activas, excepto
 *   loopback. Se anuncian como alternateHostname para que GetEndpoints
 *   devuelva un endpoint por cada IP (eth0 para la RPi 2, wlan0 para UaExpert
 *   desde la PC) y nunca solo el nombre de host, que mDNS podria resolver por
 *   la interfaz equivocada.
 * Parametros: interfaces (object): salida de os.networkInterfaces().
 * Retorna: (string[]) direcciones IPv4.
 * Excepciones: ninguna.
 */
function direccionesIPv4(interfaces = os.networkInterfaces()) {
    return Object.values(interfaces).flat()
        .filter((i) => i && i.family === 'IPv4' && !i.internal)
        .map((i) => i.address);
}

/**
 * Descripcion: arma el objeto de opciones de OPCUAServer a partir de config.
 * Parametros:
 *   opcua (object): modulo node-opcua.
 *   config (object): node-red/comun/config.js.
 *   gestorCertificados (OPCUACertificateManager): PKI del servidor.
 *   gestorUsuarios (object): ver crearGestorUsuarios().
 * Retorna: (object) OPCUAServerOptions.
 * Excepciones: Error si una politica o modo de config no existe.
 */
function opcionesServidor(opcua, config, gestorCertificados, gestorUsuarios) {
    const politica = (nombre) => {
        const valor = opcua.SecurityPolicy[nombre];
        if (!valor) throw new Error('politica de seguridad desconocida: ' + nombre);
        return valor;
    };
    const modo = (nombre) => {
        const valor = opcua.MessageSecurityMode[nombre];
        if (valor === undefined) throw new Error('modo de seguridad desconocido: ' + nombre);
        return valor;
    };
    return {
        port: config.red.puertoOpcUa,
        // Sin ruta de recurso: el endpoint queda opc.tcp://IP:4840, exactamente
        // el que pide la consigna (Parte 2.1).
        resourcePath: '',
        // Escucha en todas las interfaces (0.0.0.0), como pide la consigna.
        // Las direcciones anunciadas en GetEndpoints son otra cosa: las fija
        // alternateHostname.
        alternateHostname: direccionesIPv4(),
        // El namespace 1 NO es el applicationUri (comportamiento por defecto
        // de node-opcua) sino urn:unraf:pdci:t2, que se registra a mano en
        // construirEspacioDirecciones(). Ver modelo-informacion.md §4.
        skipOwnNamespace: true,
        serverInfo: {
            applicationUri: 'urn:' + os.hostname() + ':unraf:pdci:t2:servidor',
            productUri: 'urn:unraf:pdci:t2',
            applicationName: { text: 'UNRaf PdCI T2 - Servidor (RPi 1)', locale: 'es' },
        },
        buildInfo: {
            productName: 'UNRaf PdCI T2 Servidor',
            manufacturerName: 'Bevilacqua - Peralta',
            softwareVersion: String(config.VERSION),
        },
        securityPolicies: config.seguridad.politicasServidor.map(politica),
        securityModes: config.seguridad.modosServidor.map(modo),
        allowAnonymous: config.seguridad.permitirAnonimo,
        serverCertificateManager: gestorCertificados,
        userManager: gestorUsuarios,
        // Una sola sesion de la RPi 2 + UaExpert + margen. Limitar sesiones
        // acota el consumo de memoria ante un cliente que abra sesiones sin
        // cerrarlas (STRIDE: denegacion de servicio).
        serverCapabilities: { maxSessions: 5 },
    };
}

/**
 * Descripcion: gestor de usuarios para node-opcua. Valida la contrasena
 *   contra el hash scrypt y asigna roles: el usuario autenticado recibe
 *   AuthenticatedUser y Operator; los anonimos reciben Anonymous (lo hace
 *   node-opcua).
 * Parametros:
 *   opcua (object): modulo node-opcua.
 *   credenciales (object|null): { usuario: string, hashClave: string } o null
 *     si no hay usuario configurado (solo anonimo).
 *   registrar (function): funcion de log (texto) => void.
 * Retorna: (object) IUserManagerEx.
 * Excepciones: ninguna.
 */
function crearGestorUsuarios(opcua, credenciales, registrar) {
    return {
        isValidUserAsync(usuario, clave, callback) {
            if (!credenciales || usuario !== credenciales.usuario) {
                // [SEC] Se registra el intento sin la contrasena.
                registrar('ActivateSession rechazado: usuario desconocido "' + usuario + '"');
                return callback(null, false);
            }
            verificarClave(clave, credenciales.hashClave).then((valida) => {
                registrar('ActivateSession usuario "' + usuario + '": ' + (valida ? 'aceptado' : 'clave incorrecta'));
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

// ==========================================================================
// BLOQUE S2 — Espacio de direcciones (consigna Parte 2.2)
// ==========================================================================

/**
 * Descripcion: registra urn:unraf:pdci:t2 y crea bajo Objects los objetos
 *   Servidor y Cliente con sus cuatro variables, con NodeIds fijos.
 *
 *   | NodeId                          | Tipo    | Acceso | Extra      |
 *   |---------------------------------|---------|--------|------------|
 *   | ns=1;s=Servidor.EstadoPulsador  | Boolean | L      |            |
 *   | ns=1;s=Servidor.Rampa           | UInt16  | L      | EURange    |
 *   | ns=1;s=Cliente.EstadoPulsador   | Boolean | L/E    |            |
 *   | ns=1;s=Cliente.Rampa            | UInt16  | L/E    | EURange    |
 *
 *   Las Rampa se crean como AnalogItemType (addAnalogDataItem), que es el
 *   tipo de Data Access (IEC 62541-8) que lleva la propiedad EURange.
 *
 * Parametros:
 *   opcua (object): modulo node-opcua.
 *   addressSpace (AddressSpace): server.engine.addressSpace.
 *   config (object): config.js.
 * Retorna: (object) { namespace, variables: { servidorPulsador, servidorRampa,
 *   clientePulsador, clienteRampa } }.
 * Excepciones: Error si el namespace no quedo en el indice 1.
 */
function construirEspacioDirecciones(opcua, addressSpace, config) {
    const namespace = addressSpace.registerNamespace(config.opcua.namespaceUri);
    if (namespace.index !== 1) {
        throw new Error('se esperaba ns=1 para ' + config.opcua.namespaceUri + ' y se obtuvo ' + namespace.index);
    }
    const ids = config.opcua.identificadores;
    const nodeId = (identificador) => 'ns=' + namespace.index + ';s=' + identificador;
    const objetos = addressSpace.rootFolder.objects;

    const lectura = opcua.makeAccessLevelFlag('CurrentRead');
    const lecturaEscritura = opcua.makeAccessLevelFlag('CurrentRead | CurrentWrite');

    // Permisos por rol (solo si se exige autenticacion para escribir).
    const P = opcua.PermissionType;
    const permisosEscritura = config.seguridad.soloAutenticadosEscriben ? [
        { roleId: opcua.WellKnownRoles.Anonymous, permissions: P.Browse | P.Read | P.ReadRolePermissions },
        { roleId: opcua.WellKnownRoles.AuthenticatedUser, permissions: P.Browse | P.Read | P.ReadRolePermissions | P.Write },
    ] : undefined;

    const servidor = namespace.addObject({
        organizedBy: objetos, browseName: 'Servidor', nodeId: nodeId('Servidor'),
        description: 'Datos generados en la Raspberry Pi 1',
    });
    const cliente = namespace.addObject({
        organizedBy: objetos, browseName: 'Cliente', nodeId: nodeId('Cliente'),
        description: 'Datos escritos por la Raspberry Pi 2',
    });

    // minimumSamplingInterval = tick de generacion (50 ms): no tiene sentido
    // muestrear mas rapido de lo que el dato cambia. El servidor revisa al
    // alza cualquier SamplingInterval menor que este valor.
    const muestreoMinimo = config.senales.tickMs;
    const rango = config.opcua.euRange;

    const variables = {
        servidorPulsador: namespace.addVariable({
            componentOf: servidor, browseName: 'EstadoPulsador', nodeId: nodeId(ids.servidorPulsador),
            dataType: 'Boolean', accessLevel: lectura, userAccessLevel: lectura,
            minimumSamplingInterval: muestreoMinimo,
            description: 'Pulsador de la Raspberry Pi 1 (true = presionado)',
        }),
        servidorRampa: namespace.addAnalogDataItem({
            componentOf: servidor, browseName: 'Rampa', nodeId: nodeId(ids.servidorRampa),
            dataType: 'UInt16', accessLevel: lectura, userAccessLevel: lectura,
            minimumSamplingInterval: muestreoMinimo,
            engineeringUnitsRange: { low: rango.low, high: rango.high },
            description: 'Diente de sierra 0-65535, periodo 4 s, generado en la Raspberry Pi 1',
        }),
        clientePulsador: namespace.addVariable({
            componentOf: cliente, browseName: 'EstadoPulsador', nodeId: nodeId(ids.clientePulsador),
            dataType: 'Boolean', accessLevel: lecturaEscritura, userAccessLevel: lecturaEscritura,
            minimumSamplingInterval: muestreoMinimo, rolePermissions: permisosEscritura,
            description: 'Pulsador de la Raspberry Pi 2, escrito por el cliente',
        }),
        clienteRampa: namespace.addAnalogDataItem({
            componentOf: cliente, browseName: 'Rampa', nodeId: nodeId(ids.clienteRampa),
            dataType: 'UInt16', accessLevel: lecturaEscritura, userAccessLevel: lecturaEscritura,
            minimumSamplingInterval: muestreoMinimo, rolePermissions: permisosEscritura,
            engineeringUnitsRange: { low: rango.low, high: rango.high },
            description: 'Rampa triangular de la Raspberry Pi 2, escrita por el cliente',
        }),
    };

    // Valores iniciales: estado seguro (pulsadores sueltos, rampas en 0).
    // Sin esto el primer Read devolveria un Variant nulo.
    const ahora = new Date();
    variables.servidorPulsador.setValueFromSource({ dataType: opcua.DataType.Boolean, value: false }, opcua.StatusCodes.Good, ahora);
    variables.clientePulsador.setValueFromSource({ dataType: opcua.DataType.Boolean, value: false }, opcua.StatusCodes.Good, ahora);
    variables.servidorRampa.setValueFromSource({ dataType: opcua.DataType.UInt16, value: 0 }, opcua.StatusCodes.Good, ahora);
    variables.clienteRampa.setValueFromSource({ dataType: opcua.DataType.UInt16, value: 0 }, opcua.StatusCodes.Good, ahora);

    return { namespace, variables };
}

// ==========================================================================
// Ciclo de vida
// ==========================================================================

/**
 * Descripcion: crea, inicializa y arranca el servidor.
 *
 * Parametros (objeto):
 *   opcua (object): modulo node-opcua.
 *   config (object): config.js.
 *   directorioPki (string): carpeta de la PKI del servidor (own/, trusted/,
 *     rejected/). Va fuera del repositorio: contiene la clave privada.
 *   credenciales (object|null): ver crearGestorUsuarios().
 *   alEscribirCliente (function): (nombre, valor, dataValue) => void. Se llama
 *     cuando cambia Cliente.EstadoPulsador o Cliente.Rampa (BLOQUE S5).
 *   registrar (function): (texto) => void, para la consola de Node-RED.
 *
 * Retorna: (Promise<object>) controlador con:
 *   publicarPulsador(valor: boolean, instante: Date): void   (BLOQUE S4)
 *   publicarRampa(valor: number, instante: Date): void       (BLOQUE S3)
 *   leer(nombre: string): DataValue
 *   endpoints(): string[]  descripcion legible de cada endpoint
 *   detener(demoraMs?: number): Promise<void>
 *
 * Excepciones: rechaza la promesa si el puerto esta ocupado o la PKI no se
 *   puede crear.
 */
async function iniciarServidor({ opcua, config, directorioPki, credenciales, alEscribirCliente, registrar }) {
    const log = registrar || (() => {});

    const gestorCertificados = new opcua.OPCUACertificateManager({
        rootFolder: directorioPki,
        automaticallyAcceptUnknownCertificate: config.seguridad.aceptarCertificadosDesconocidos,
    });
    await gestorCertificados.initialize();

    const servidor = new opcua.OPCUAServer(opcionesServidor(
        opcua, config, gestorCertificados, crearGestorUsuarios(opcua, credenciales, log)));
    await servidor.initialize();

    const { variables } = construirEspacioDirecciones(opcua, servidor.engine.addressSpace, config);

    // ---- BLOQUE S5: atencion de escrituras --------------------------------
    // node-opcua ya rechazo antes las escrituras invalidas: tipo distinto
    // (BadTypeMismatch), variable de solo lectura (BadNotWritable) o rol sin
    // permiso (BadUserAccessDenied). Lo que llega aca es un valor valido.
    for (const nombre of ['clientePulsador', 'clienteRampa']) {
        variables[nombre].on('value_changed', (dataValue) => {
            alEscribirCliente && alEscribirCliente(nombre, dataValue.value.value, dataValue);
        });
    }

    // ---- Eventos de sesion para la consola (Parte 3.6) -------------------
    // El modo y la politica del canal se leen al crear la sesion: en el evento
    // newChannel el OPN todavia no se proceso y valen "Invalid".
    servidor.on('create_session', (sesion) => {
        const canal = sesion.channel || {};
        log('CreateSession: ' + sesion.sessionName + ' desde ' + canal.remoteAddress +
            ' modo=' + opcua.MessageSecurityMode[canal.securityMode] +
            ' politica=' + String(canal.securityPolicy).split('#').pop());
    });
    servidor.on('session_closed', (sesion, motivo) => log('Sesion cerrada (' + sesion.sessionName + '): ' + motivo));
    servidor.on('newChannel', (canal) => log('Conexion TCP aceptada desde ' + canal.remoteAddress));
    servidor.on('closeChannel', (canal) => log('Canal seguro cerrado: ' + canal.remoteAddress));

    await servidor.start();

    const publicar = (variable, tipo) => (valor, instante = new Date()) => {
        // setValueFromSource fija Value, StatusCode Good y SourceTimestamp =
        // instante de generacion en la placa. El ServerTimestamp lo pone el
        // servidor al responder.
        variable.setValueFromSource({ dataType: tipo, value: valor }, opcua.StatusCodes.Good, instante);
    };

    return {
        publicarPulsador: publicar(variables.servidorPulsador, opcua.DataType.Boolean),
        publicarRampa: publicar(variables.servidorRampa, opcua.DataType.UInt16),
        leer: (nombre) => variables[nombre].readValue(),
        endpoints: () => servidor.endpoints.flatMap((e) => e.endpointDescriptions()).map((d) =>
            d.endpointUrl + '  ' + opcua.MessageSecurityMode[d.securityMode] + '  ' + String(d.securityPolicyUri).split('#').pop()),
        // demoraMs > 0 anuncia a los clientes el estado "Shutdown" antes de
        // cerrar; 0 libera el puerto de inmediato (redespliegue de Node-RED).
        detener: (demoraMs = 1000) => servidor.shutdown(demoraMs),
        servidor,
    };
}

module.exports = Object.freeze({
    direccionesIPv4,
    opcionesServidor,
    crearGestorUsuarios,
    construirEspacioDirecciones,
    iniciarServidor,
    directorioPkiPorDefecto: (userDir) => path.join(userDir, 'opcua-pki', 'servidor'),
});
