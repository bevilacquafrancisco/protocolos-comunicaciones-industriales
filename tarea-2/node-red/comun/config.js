/**
 * config.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * UNICA FUENTE DE VERDAD de todo parametro que debe coincidir entre el servidor
 * (Raspberry Pi 1) y el cliente (Raspberry Pi 2): direcciones IP, puerto,
 * espacio de nombres, NodeIds, pines, periodos e intervalos de OPC UA.
 * Es el mismo invariante que firmware/comun/config.py en la Tarea 1: ningun
 * flujo de Node-RED repite un valor de este archivo.
 *
 * No contiene logica. Se carga desde settings.js en functionGlobalContext y las
 * function nodes lo leen con global.get('config').
 *
 * Se eligio .js y no .json porque JSON no admite comentarios, y la convencion
 * del repositorio exige que cada numero lleve su justificacion al lado.
 *
 * Dependencias externas: ninguna.
 */
'use strict';

module.exports = Object.freeze({
    // Version de este archivo. Las function nodes comparan contra la que
    // necesitan y avisan si una placa quedo con una copia vieja (el despliegue
    // es manual sobre dos placas, igual que en la Tarea 1).
    VERSION: 1,

    // ------------------------------------------------------------------
    // RED — consigna, Parte 1.2. Ver docs/arquitectura-red.md §3
    // ------------------------------------------------------------------
    red: Object.freeze({
        ipServidor: '192.168.10.1',
        ipCliente: '192.168.10.2',
        // /24: 254 hosts utiles. Alcanza con 2, y es la mascara que fija la
        // consigna. Al estar ambos en el mismo prefijo, la ruta es "directly
        // connected" y no hace falta puerta de enlace.
        prefijo: 24,
        // 4840: puerto registrado por IANA para OPC UA TCP (IEC 62541-6 §7.2).
        puertoOpcUa: 4840,
    }),

    // ------------------------------------------------------------------
    // MODELO DE INFORMACION — consigna, Parte 2.2. Ver docs/modelo-informacion.md
    // ------------------------------------------------------------------
    opcua: Object.freeze({
        namespaceUri: 'urn:unraf:pdci:t2',
        // Endpoint que usa el cliente: SIEMPRE la IP de eth0, nunca el nombre
        // de host. Si se usara "raspberrypi.local", mDNS podria resolverlo por
        // wlan0 y el trafico dejaria de pasar por el enlace directo (P1.4).
        endpointCliente: 'opc.tcp://192.168.10.1:4840',
        // Identificadores string (s=) de los cuatro nodos. El indice de
        // namespace no se fija aca: el cliente lo resuelve por URI leyendo
        // Server.NamespaceArray (ns=0;i=2255). Ver modelo-informacion.md §4.
        identificadores: Object.freeze({
            servidorPulsador: 'Servidor.EstadoPulsador',
            servidorRampa: 'Servidor.Rampa',
            clientePulsador: 'Cliente.EstadoPulsador',
            clienteRampa: 'Cliente.Rampa',
        }),
        // EURange de las dos variables Rampa (consigna, Parte 2.2).
        euRange: Object.freeze({ low: 0, high: 65535 }),
    }),

    // ------------------------------------------------------------------
    // SENALES — consigna, Partes 2.3 y 3.2
    // ------------------------------------------------------------------
    senales: Object.freeze({
        // UInt16: 0 a 2^16 - 1.
        maximo: 65535,
        // Tick de generacion de 50 ms (consigna). 4000 / 50 = 80 muestras por
        // periodo de la sierra; 8000 / 50 = 160 de la triangular.
        tickMs: 50,
        periodoSierraMs: 4000,
        periodoTriangularMs: 8000,
        // Escritura de Cliente.Rampa cada 100 ms (consigna, Parte 3.3).
        periodoEscrituraRampaMs: 100,
        // Correccion gamma (Parte 3.7, opcional). 2,2 es el exponente de la
        // curva sRGB (IEC 61966-2-1) y aproxima la respuesta perceptiva del ojo
        // (ley de Stevens para el brillo). false = escala lineal.
        usarGamma: false,
        gamma: 2.2,
    }),

    // ------------------------------------------------------------------
    // LECTURA DEL CLIENTE — consigna, Parte 3.4
    // ------------------------------------------------------------------
    lectura: Object.freeze({
        // 'A' = Read periodico (polling) | 'B' = Subscription + MonitoredItems.
        // Se cambia SOLO aca para repetir las capturas de 60 s: una variable
        // por vez.
        modo: 'B',
        periodoReadMs: 100,
        publishingIntervalMs: 100,
        // SamplingInterval = PublishingInterval: muestrear mas rapido que lo
        // que se publica solo llena la cola con valores que se descartan.
        samplingIntervalMs: 100,
        // QueueSize 1: para replicar en un LED interesa el ultimo valor, no la
        // historia. Con 1 y discardOldest=true el servidor entrega siempre el
        // mas reciente (IEC 62541-4 §5.12.1.5).
        queueSize: 1,
    }),

    // ------------------------------------------------------------------
    // SEGURIDAD — consigna, Partes 4.7 a 4.9. Ver docs/seguridad.md
    // ------------------------------------------------------------------
    seguridad: Object.freeze({
        // Servidor: politicas x modos. node-opcua combina None solo con el
        // modo None, y Basic256Sha256 con Sign y SignAndEncrypt: quedan
        // exactamente los tres endpoints que pide la consigna (por cada
        // direccion IP anunciada).
        politicasServidor: Object.freeze(['None', 'Basic256Sha256']),
        modosServidor: Object.freeze(['None', 'Sign', 'SignAndEncrypt']),
        // Acceso anonimo habilitado "ademas de" usuario/contrasena (P4.9).
        permitirAnonimo: true,
        // true = solo un usuario autenticado puede escribir Cliente.*; el
        // anonimo queda de solo lectura (BadUserAccessDenied). Se deja en
        // false para las Partes 2 y 3 (UaExpert anonimo escribe) y se pasa a
        // true en la demostracion de la Parte 4.9.
        soloAutenticadosEscriben: false,
        // [SEC] false: un certificado desconocido va a la carpeta rejected/ y
        // la conexion segura falla hasta que alguien lo mueva a trusted/.
        // Aceptarlo automaticamente anularia la autenticacion de aplicacion.
        aceptarCertificadosDesconocidos: false,
        // Cliente: endpoint con el que se conecta. Se cambia para repetir la
        // conexion con cada modo (P4.7): None/None, Sign/Basic256Sha256,
        // SignAndEncrypt/Basic256Sha256.
        modoCliente: 'None',
        politicaCliente: 'None',
        // 'anonimo' | 'usuario'. Con 'usuario', las credenciales salen de las
        // variables de entorno OPCUA_CLIENTE_USUARIO / OPCUA_CLIENTE_CLAVE.
        autenticacionCliente: 'anonimo',
    }),

    // ------------------------------------------------------------------
    // SUSCRIPCION Y SESION — consigna, Parte 3.4 y 3.6
    // ------------------------------------------------------------------
    suscripcion: Object.freeze({
        // MaxKeepAliveCount 10 x 100 ms = 1 s: sin cambios, el servidor manda
        // un PublishResponse vacio (KeepAlive) por segundo.
        maxKeepAliveCount: 10,
        // LifetimeCount 300 x 100 ms = 30 s (debe ser >= 3 x KeepAlive, IEC
        // 62541-4 §5.13.2). Si el cable se desconecta MENOS de 30 s, la
        // suscripcion sobrevive y se recupera; si se desconecta mas, el
        // servidor la borra y el cliente tiene que recrearla. Las dos ramas
        // se prueban en la Parte 3.6.
        lifetimeCount: 300,
        // Timeout de sesion: 60 s, mayor que la vida de la suscripcion, para
        // poder observar los dos fenomenos por separado.
        timeoutSesionMs: 60000,
        // Reintentos de conexion: primer intento a 1 s, tope de 5 s entre
        // intentos, sin limite de cantidad (el cliente nunca se rinde).
        reconexionDemoraInicialMs: 1000,
        reconexionDemoraMaximaMs: 5000,
    }),

    // ------------------------------------------------------------------
    // GPIO (numeracion BCM) — igual en ambas placas. Ver arquitectura-red.md §6
    // ------------------------------------------------------------------
    gpio: Object.freeze({
        // Pulsador a GND con pull-up interno (~50 kohm): activo en bajo. Sin
        // resistencia externa, y un pin flotante no queda en estado indefinido.
        pulsador: 17,     // pin fisico 11
        ledDigital: 27,   // pin fisico 13, LED + 330 ohm a GND
        // GPIO18 = PWM0 por hardware. pigpio genera PWM por DMA en cualquier
        // pin, pero usar el canal de hardware deja la puerta abierta a una
        // RPi sin pigpiod.
        ledPwm: 18,       // pin fisico 12, LED + 330 ohm a GND
        // 800 Hz: muy por encima de la frecuencia de fusion del parpadeo
        // (~90 Hz), y con la muestra de 5 us de pigpiod deja una resolucion
        // real de 1e6 / (5 * 800) = 250 pasos, casi los 256 de la escala.
        // A 8000 Hz quedarian solo 25 pasos (documentacion de pigpio,
        // set_PWM_frequency).
        frecuenciaPwmHz: 800,
        // Antirrebote: los rebotes de un pulsador tactil duran 1-10 ms;
        // 25 ms los cubre y sigue muy por debajo de los ~100 ms en que una
        // persona percibe demora. OJO: el campo "debounce" del nodo pi-gpiod
        // se pasa a set_glitch_filter() de pigpio, que trabaja en
        // MICROSEGUNDOS (0-300000). Su valor por defecto "25" son 25 us, no
        // 25 ms. Ver evidencia/INCONVENIENTES.md, I-01.
        antirreboteUs: 25000,
        // pigpiod escucha en el puerto 8888 de localhost (valor por defecto).
        pigpiodHost: '127.0.0.1',
        pigpiodPuerto: 8888,
    }),

    // ------------------------------------------------------------------
    // CONSOLA — consigna, Parte 3.5
    // ------------------------------------------------------------------
    consola: Object.freeze({
        // 1 s: 20 muestras de rampa por linea. Imprimir cada 50 ms inundaria la
        // consola y le sumaria carga al event loop que genera las senales
        // (el "efecto sonda" de la Tarea 1).
        periodoMs: 1000,
    }),
});
