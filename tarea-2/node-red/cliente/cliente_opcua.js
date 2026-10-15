/**
 * cliente_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Cliente OPC UA de la Raspberry Pi 2 (consigna Parte 3). Se conecta al
 * servidor por eth0, lee Servidor.EstadoPulsador y Servidor.Rampa por Read
 * periodico (Modo A) o por suscripcion (Modo B), escribe Cliente.* y maneja la
 * perdida y la recuperacion del canal.
 *
 * Node-RED orquesta (GPIO, temporizadores, consola) y este modulo implementa la
 * pila OPC UA con node-opcua. Por que no el nodo OpcUa-Client de la paleta: no
 * expone SamplingInterval, QueueSize ni los eventos de reconexion con su
 * StatusCode, que la consigna pide documentar (Partes 3.4 y 3.6). Ver
 * docs/arquitectura-red.md §8 (ADR-01).
 *
 * Bloques de diagramas/flujo_cliente.md implementados aca: C1, C3a, C3b, C5
 * (envio) y C7.
 *
 * Dependencias externas: node-opcua 2.x (probado con 2.160.0).
 */
'use strict';

// ==========================================================================
// BLOQUE C1 — Conexion
// ==========================================================================

/**
 * Descripcion: opciones de OPCUAClient.create() a partir de config.
 * Parametros:
 *   opcua (object): modulo node-opcua.
 *   config (object): config.js.
 *   gestorCertificados (OPCUACertificateManager): PKI del cliente.
 * Retorna: (object) OPCUAClientOptions.
 * Excepciones: Error si el modo o la politica no existen.
 */
function opcionesCliente(opcua, config, gestorCertificados) {
    const s = config.seguridad;
    const modo = opcua.MessageSecurityMode[s.modoCliente];
    const politica = opcua.SecurityPolicy[s.politicaCliente];
    if (modo === undefined || !politica) {
        throw new Error('modo/politica de cliente invalidos: ' + s.modoCliente + '/' + s.politicaCliente);
    }
    return {
        applicationName: 'UNRaf PdCI T2 - Cliente (RPi 2)',
        applicationUri: 'urn:unraf:pdci:t2:cliente',
        securityMode: modo,
        securityPolicy: politica,
        clientCertificateManager: gestorCertificados,
        // false: el cliente abre el canal contra la URL configurada (la IP de
        // eth0) aunque el servidor anuncie otras en GetEndpoints. Con true,
        // node-opcua exige que esa URL figure textualmente en la lista.
        endpointMustExist: false,
        keepSessionAlive: true,
        requestedSessionTimeout: config.suscripcion.timeoutSesionMs,
        connectionStrategy: {
            initialDelay: config.suscripcion.reconexionDemoraInicialMs,
            maxDelay: config.suscripcion.reconexionDemoraMaximaMs,
            maxRetry: -1, // sin limite: el cliente de planta no se rinde
        },
    };
}

/**
 * Descripcion: identidad de usuario para CreateSession/ActivateSession.
 * Parametros:
 *   opcua (object), config (object).
 *   entorno (object): process.env (inyectable para pruebas).
 * Retorna: (object) UserIdentityInfo.
 * Excepciones: Error si se pide 'usuario' y faltan las variables de entorno.
 */
function identidadUsuario(opcua, config, entorno = process.env) {
    if (config.seguridad.autenticacionCliente !== 'usuario') {
        return { type: opcua.UserTokenType.Anonymous };
    }
    const usuario = entorno.OPCUA_CLIENTE_USUARIO;
    const clave = entorno.OPCUA_CLIENTE_CLAVE;
    if (!usuario || !clave) {
        // [SEC] Nunca un valor por defecto embebido en el codigo.
        throw new Error('faltan OPCUA_CLIENTE_USUARIO / OPCUA_CLIENTE_CLAVE en el entorno');
    }
    return { type: opcua.UserTokenType.UserName, userName: usuario, password: clave };
}

/**
 * Descripcion: crea el cliente, conecta, abre sesion, resuelve el indice del
 *   namespace por URI y arranca la lectura en el modo configurado.
 *
 * Parametros (objeto):
 *   opcua (object): modulo node-opcua.
 *   config (object): config.js.
 *   directorioPki (string): PKI del cliente (fuera del repositorio).
 *   alRecibir (function): ({ variable, valor, statusCode, sourceTimestamp,
 *     serverTimestamp, modo }) => void. variable = 'servidorPulsador' |
 *     'servidorRampa'. BLOQUE C4 (vive en Node-RED).
 *   alEvento (function): ({ evento, detalle, statusCode }) => void. Eventos de
 *     conexion, sesion y suscripcion para la consola (BLOQUE C7).
 *   entorno (object): process.env.
 *
 * Retorna: (Promise<object>) controlador con:
 *   escribirPulsador(valor: boolean): Promise<string|null>  StatusCode o null si se omitio
 *   escribirRampa(valor: number): Promise<string|null>
 *   estadisticas(): object  contadores de lecturas, notificaciones, omitidas
 *   detener(): Promise<void>
 *
 * Excepciones: rechaza si la primera conexion falla de forma no recuperable
 *   (por ejemplo, certificado no confiado: BadSecurityChecksFailed).
 */
async function iniciarCliente({ opcua, config, directorioPki, alRecibir, alEvento, entorno = process.env }) {
    const evento = alEvento || (() => {});
    const recibir = alRecibir || (() => {});
    const nombreStatus = (sc) => (sc && sc.name) || String(sc);

    const gestorCertificados = new opcua.OPCUACertificateManager({
        rootFolder: directorioPki,
        automaticallyAcceptUnknownCertificate: config.seguridad.aceptarCertificadosDesconocidos,
    });
    await gestorCertificados.initialize();

    const cliente = opcua.OPCUAClient.create(opcionesCliente(opcua, config, gestorCertificados));

    // ---- BLOQUE C7: perdida y recuperacion del canal ---------------------
    // Estos eventos son la evidencia de la Parte 3.6: que paso, cuando y con
    // que StatusCode.
    cliente.on('connection_lost', () => evento({ evento: 'connection_lost', detalle: 'se perdio la conexion TCP' }));
    cliente.on('backoff', (intento, demora) => evento({ evento: 'backoff', detalle: 'reintento ' + intento + ' en ' + demora + ' ms' }));
    cliente.on('start_reconnection', () => evento({ evento: 'start_reconnection', detalle: 'reabriendo canal seguro' }));
    cliente.on('connection_reestablished', () => evento({ evento: 'connection_reestablished', detalle: 'canal seguro reabierto' }));
    cliente.on('after_reconnection', (error) => evento({ evento: 'after_reconnection', detalle: error ? error.message : 'sesion y suscripcion recuperadas' }));

    // La identidad se valida ANTES de conectar: si faltan credenciales no se
    // abre ninguna conexion.
    const identidad = identidadUsuario(opcua, config, entorno);

    await cliente.connect(config.opcua.endpointCliente);
    evento({ evento: 'connected', detalle: config.opcua.endpointCliente + ' ' + config.seguridad.modoCliente + '/' + config.seguridad.politicaCliente });

    try {
        return await prepararSesion({ opcua, config, cliente, identidad, evento, recibir, nombreStatus });
    } catch (error) {
        // Sin esto, un fallo despues de conectar (clave rechazada, namespace
        // ausente) deja al cliente reintentando para siempre en segundo plano:
        // un proceso zombi que ademas ensucia las capturas.
        await cliente.disconnect().catch(() => {});
        throw error;
    }
}

/**
 * Descripcion: crea la sesion, resuelve el namespace y arranca la lectura y
 *   las escrituras. Separada de iniciarCliente() para poder desconectar si
 *   algo falla a mitad de camino.
 * Parametros: ver iniciarCliente(); cliente (OPCUAClient) ya conectado;
 *   identidad (UserIdentityInfo).
 * Retorna: (Promise<object>) el controlador descripto en iniciarCliente().
 * Excepciones: rechaza si la sesion o la suscripcion no se pueden crear.
 */
async function prepararSesion({ opcua, config, cliente, identidad, evento, recibir, nombreStatus }) {
    const sesion = await cliente.createSession(identidad);
    evento({ evento: 'session_activated', detalle: 'autenticacion ' + config.seguridad.autenticacionCliente });
    sesion.on('session_closed', (sc) => evento({ evento: 'session_closed', statusCode: nombreStatus(sc) }));
    sesion.on('keepalive_failure', () => evento({ evento: 'keepalive_failure', detalle: 'el servidor no respondio el keep-alive de sesion' }));

    // El indice del namespace se resuelve por URI leyendo
    // Server.NamespaceArray (ns=0;i=2255), no se asume: es la practica que
    // recomienda IEC 62541-3 §8.2.2, porque el indice depende del servidor.
    const espacios = await sesion.readNamespaceArray();
    const ns = espacios.indexOf(config.opcua.namespaceUri);
    if (ns < 0) throw new Error('el servidor no publica ' + config.opcua.namespaceUri);
    const ids = config.opcua.identificadores;
    const nodo = (id) => opcua.resolveNodeId('ns=' + ns + ';s=' + id);
    const NODOS_LECTURA = [
        ['servidorPulsador', nodo(ids.servidorPulsador)],
        ['servidorRampa', nodo(ids.servidorRampa)],
    ];
    evento({ evento: 'namespace', detalle: config.opcua.namespaceUri + ' -> ns=' + ns });

    const contadores = { lecturas: 0, lecturasOmitidas: 0, notificaciones: 0, escrituras: 0, escriturasOmitidas: 0 };
    const entregar = (variable, dv, modo) => recibir({
        variable, modo, valor: dv.value.value, statusCode: nombreStatus(dv.statusCode),
        sourceTimestamp: dv.sourceTimestamp, serverTimestamp: dv.serverTimestamp,
    });

    let temporizador = null;
    let suscripcion = null;

    // ---- BLOQUE C3a: Modo A, Read periodico ------------------------------
    if (config.lectura.modo === 'A') {
        let pendiente = false;
        temporizador = setInterval(async () => {
            // Si el Read anterior no volvio (enlace caido), no se apila otro:
            // de lo contrario, al reconectar llegaria una rafaga de respuestas
            // viejas.
            if (pendiente || cliente.isReconnecting) {
                contadores.lecturasOmitidas++;
                return;
            }
            pendiente = true;
            try {
                const resultados = await sesion.read(
                    NODOS_LECTURA.map(([, nodeId]) => ({ nodeId, attributeId: opcua.AttributeIds.Value })),
                    0); // maxAge 0: el valor actual, no uno en cache
                contadores.lecturas++;
                resultados.forEach((dv, i) => entregar(NODOS_LECTURA[i][0], dv, 'A'));
            } catch (error) {
                evento({ evento: 'read_error', detalle: error.message });
            } finally {
                pendiente = false;
            }
        }, config.lectura.periodoReadMs);
    }

    // ---- BLOQUE C3b: Modo B, suscripcion + MonitoredItems ----------------
    if (config.lectura.modo === 'B') {
        suscripcion = await sesion.createSubscription2({
            requestedPublishingInterval: config.lectura.publishingIntervalMs,
            requestedMaxKeepAliveCount: config.suscripcion.maxKeepAliveCount,
            requestedLifetimeCount: config.suscripcion.lifetimeCount,
            maxNotificationsPerPublish: 0, // sin limite
            publishingEnabled: true,
            priority: 1,
        });
        // Valores REVISADOS por el servidor: son los que rigen, no los pedidos.
        evento({
            evento: 'subscription_created',
            detalle: 'id=' + suscripcion.subscriptionId + ' publishingInterval=' + suscripcion.publishingInterval +
                ' ms keepAliveCount=' + suscripcion.maxKeepAliveCount + ' lifetimeCount=' + suscripcion.lifetimeCount,
        });
        suscripcion.on('keepalive', () => evento({ evento: 'keepalive', detalle: 'PublishResponse sin notificaciones' }));
        suscripcion.on('status_changed', (sc) => evento({ evento: 'subscription_status', statusCode: nombreStatus(sc) }));
        suscripcion.on('terminated', () => evento({ evento: 'subscription_terminated' }));

        // Un unico CreateMonitoredItemsRequest con los dos nodos (grupo), en
        // lugar de dos peticiones: una sola trama para analizar.
        const grupo = opcua.ClientMonitoredItemGroup.create(
            suscripcion,
            NODOS_LECTURA.map(([, nodeId]) => ({ nodeId, attributeId: opcua.AttributeIds.Value })),
            { samplingInterval: config.lectura.samplingIntervalMs, queueSize: config.lectura.queueSize, discardOldest: true },
            opcua.TimestampsToReturn.Both);
        grupo.on('initialized', () => {
            const revisados = grupo.monitoredItems.map((m) =>
                'samplingInterval=' + m.result.revisedSamplingInterval + ' ms queueSize=' + m.result.revisedQueueSize);
            evento({ evento: 'monitored_items_created', detalle: revisados.join(' | ') });
        });
        grupo.on('changed', (item, dataValue, indice) => {
            contadores.notificaciones++;
            entregar(NODOS_LECTURA[indice][0], dataValue, 'B');
        });
    }

    // ---- BLOQUE C5: escrituras ------------------------------------------
    // Un Write por variable a la vez. Si el anterior sigue pendiente (canal
    // caido), el nuevo se omite y se cuenta: al reconectar se escribe el valor
    // VIGENTE, no una cola de valores viejos.
    const escritor = (nombreVariable, tipo) => {
        const nodeId = nodo(ids[nombreVariable]);
        let pendiente = false;
        return async (valor) => {
            if (pendiente || cliente.isReconnecting) {
                contadores.escriturasOmitidas++;
                return null;
            }
            pendiente = true;
            try {
                const sc = await sesion.write({
                    nodeId, attributeId: opcua.AttributeIds.Value,
                    value: { value: { dataType: tipo, value: valor } },
                });
                contadores.escrituras++;
                return nombreStatus(sc);
            } catch (error) {
                evento({ evento: 'write_error', detalle: nombreVariable + ': ' + error.message });
                return null;
            } finally {
                pendiente = false;
            }
        };
    };

    return {
        escribirPulsador: escritor('clientePulsador', opcua.DataType.Boolean),
        escribirRampa: escritor('clienteRampa', opcua.DataType.UInt16),
        estadisticas: () => Object.assign({}, contadores),
        detener: async () => {
            if (temporizador) clearInterval(temporizador);
            if (suscripcion) await suscripcion.terminate().catch(() => {});
            await sesion.close().catch(() => {});      // CloseSession
            await cliente.disconnect();                  // CLO + FIN de TCP
        },
        cliente,
        sesion,
    };
}

module.exports = Object.freeze({ opcionesCliente, identidadUsuario, iniciarCliente });
