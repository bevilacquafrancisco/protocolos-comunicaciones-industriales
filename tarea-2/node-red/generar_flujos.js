/**
 * generar_flujos.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Genera servidor/flows.json y cliente/flows.json, los archivos que se
 * importan en Node-RED, a partir de:
 *   - comun/config.js: pines, periodos, frecuencia de PWM (unica fuente de
 *     verdad: el flows.json no contiene ningun numero escrito a mano).
 *   - {comun,servidor,cliente}/funciones/X.js: el codigo de cada function node, versionado como
 *     JavaScript legible en lugar de quedar escondido como una cadena
 *     dentro del JSON.
 *
 * Por que un generador: si los pines y los intervalos se tipearan en el
 * editor de Node-RED, quedarian duplicados respecto de config.js y podrian
 * divergir sin que nada lo detecte. Ademas, el codigo de las function nodes
 * en archivos .js se puede revisar, comparar en git y verificar
 * (herramientas/prueba_flujos.js).
 *
 * Los IDs de nodo se derivan del nombre (SHA-1): regenerar produce el mismo
 * archivo, y los diffs de git muestran solo lo que cambio de verdad.
 *
 * Uso
 * ---
 *     node tarea-2/node-red/generar_flujos.js
 *
 * Despues de modificar config.js o una funcion: regenerar, importar el
 * flows.json en Node-RED (Menu > Importar > reemplazar) y desplegar.
 *
 * Dependencias externas: ninguna (Node.js >= 18).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const config = require('./comun/config.js');

const RAIZ = __dirname;

/** ID estable de 16 hex a partir de una clave. */
const id = (clave) => crypto.createHash('sha1').update(clave).digest('hex').slice(0, 16);

/** Lee el codigo de una function node. */
const leer = (relativo) => fs.readFileSync(path.join(RAIZ, relativo), 'utf8');

/** Segundos con el formato que espera el campo "repeat" del inject. */
const segundos = (ms) => String(ms / 1000);

/**
 * Descripcion: fabrica de nodos para una pestana (tab) de Node-RED.
 * Parametros: prefijo (string) para los IDs; tab (string) id de la pestana.
 * Retorna: (object) funciones que crean cada tipo de nodo.
 */
function fabrica(prefijo, tab) {
    const nid = (nombre) => id(prefijo + '/' + nombre);
    const base = (tipo, nombre, x, y, extra) => Object.assign({ id: nid(nombre), type: tipo, z: tab, name: nombre, x, y }, extra);
    const cables = (destinos) => destinos.map((salida) => salida.map(nid));
    return {
        nid,
        comentario: (nombre, info, x, y) => base('comment', nombre, x, y, { info, wires: [] }),
        // unaVez = false: boton manual (no se dispara al desplegar).
        inject: (nombre, x, y, { repetirMs = null, payload = '', payloadType = 'date', topic = '', unaVez = true, destinos = [] } = {}) =>
            base('inject', nombre, x, y, {
                props: [{ p: 'payload' }, { p: 'topic', vt: 'str' }],
                repeat: repetirMs === null ? '' : segundos(repetirMs), crontab: '',
                once: unaVez, onceDelay: '0.5', topic, payload, payloadType, wires: cables([destinos]),
            }),
        funcion: (nombre, x, y, { archivo, inicio = '', fin = '', salidas = 1, destinos = [[]] }) =>
            base('function', nombre, x, y, {
                func: leer(archivo), outputs: salidas, timeout: 0, noerr: 0,
                initialize: inicio ? leer(inicio) : '', finalize: fin ? leer(fin) : '', libs: [],
                wires: cables(destinos),
            }),
        debug: (nombre, x, y, activo = true) => base('debug', nombre, x, y, {
            active: activo, tosidebar: true, console: false, tostatus: false, complete: 'payload',
            targetType: 'msg', statusVal: '', statusType: 'auto', wires: [],
        }),
        rbe: (nombre, x, y, destinos) => base('rbe', nombre, x, y, {
            func: 'rbe', gap: '', start: '', inout: 'out', septopics: true, property: 'payload',
            topi: 'topic', wires: cables([destinos]),
        }),
        // host 127.0.0.1 y no "localhost": en Raspberry Pi OS "localhost" puede
        // resolver a ::1 y pigpiod escucha solo en IPv4.
        gpioIn: (nombre, x, y, pin, destinos) => base('pi-gpiod in', nombre, x, y, {
            host: config.gpio.pigpiodHost, port: config.gpio.pigpiodPuerto, pin: String(pin),
            intype: 'PUD_UP', debounce: String(config.gpio.antirreboteUs), read: true, wires: cables([destinos]),
        }),
        gpioOut: (nombre, x, y, pin, modo) => base('pi-gpiod out', nombre, x, y, {
            host: config.gpio.pigpiodHost, port: config.gpio.pigpiodPuerto, pin: String(pin),
            set: true, level: '0', out: modo, sermin: '1000', sermax: '2000',
            freq: String(config.gpio.frecuenciaPwmHz), wires: [],
        }),
    };
}

// ==========================================================================
// Servidor — Raspberry Pi 1 (diagramas/flujo_servidor.md)
// ==========================================================================
function flujoServidor() {
    const tab = id('tab/servidor');
    const f = fabrica('servidor', tab);
    const g = config.gpio;
    const s = config.senales;
    return [
        { id: tab, type: 'tab', label: 'T2 · Servidor OPC UA (RPi 1)', disabled: false,
            info: 'Generado por generar_flujos.js desde config.js v' + config.VERSION + '. No editar a mano: regenerar.' },
        f.comentario('Tarea 2 · Servidor OPC UA · bloques S1-S7 de diagramas/flujo_servidor.md', 'Ver node-red/README.md', 330, 40),
        // S1
        f.inject('S1 · Arranque', 130, 100, { payload: 'servidorOpcua', payloadType: 'str', destinos: ['S1 · Verificar configuracion'] }),
        f.funcion('S1 · Verificar configuracion', 370, 100, {
            archivo: 'comun/funciones/X1_verificar_config.js', salidas: 2,
            destinos: [['S6 · GPIO LED digital'], ['S6 · GPIO LED PWM']],
        }),
        // S3
        f.inject('S3 · Tick ' + s.tickMs + ' ms', 130, 180, { repetirMs: s.tickMs, destinos: ['S3 · Generar rampa diente de sierra'] }),
        // Botones para la captura de KeepAlive (Parte 3.4): rampa detenida.
        f.inject('S3 · Detener rampa', 130, 140, { payload: 'true', payloadType: 'bool', topic: 'pausa', unaVez: false, destinos: ['S3 · Generar rampa diente de sierra'] }),
        f.inject('S3 · Reanudar rampa', 680, 140, { payload: 'false', payloadType: 'bool', topic: 'pausa', unaVez: false, destinos: ['S3 · Generar rampa diente de sierra'] }),
        f.funcion('S3 · Generar rampa diente de sierra', 400, 180, {
            archivo: 'servidor/funciones/S3_generar_rampa.js', destinos: [['S2 · Servidor OPC UA']],
        }),
        // S4
        f.gpioIn('S4 · GPIO pulsador', 130, 240, g.pulsador, ['S4 · Leer pulsador']),
        f.funcion('S4 · Leer pulsador', 370, 240, {
            archivo: 'comun/funciones/X4_leer_pulsador.js', destinos: [['S2 · Servidor OPC UA']],
        }),
        // S2 + S5
        f.funcion('S2 · Servidor OPC UA', 680, 210, {
            archivo: 'servidor/funciones/S2_servidor_opcua.js',
            inicio: 'servidor/funciones/S2_servidor_opcua.inicio.js',
            fin: 'servidor/funciones/S2_servidor_opcua.fin.js',
            salidas: 3,
            destinos: [['S6 · LED digital'], ['S6 · LED PWM'], ['S2 · Eventos de sesion']],
        }),
        f.debug('S2 · Eventos de sesion', 950, 300),
        // S6
        f.funcion('S6 · LED digital', 930, 160, { archivo: 'comun/funciones/X6_led_digital.js', destinos: [['S6 · GPIO LED digital']] }),
        f.funcion('S6 · LED PWM', 930, 220, { archivo: 'comun/funciones/X6_led_pwm.js', destinos: [['S6 · GPIO LED PWM']] }),
        f.gpioOut('S6 · GPIO LED digital', 1180, 160, g.ledDigital, 'out'),
        f.gpioOut('S6 · GPIO LED PWM', 1180, 220, g.ledPwm, 'pwm'),
        // S7
        f.inject('S7 · Cada ' + config.consola.periodoMs + ' ms', 130, 360, { repetirMs: config.consola.periodoMs, destinos: ['S7 · Registro en consola'] }),
        f.funcion('S7 · Registro en consola', 370, 360, { archivo: 'servidor/funciones/S7_consola.js', destinos: [['S7 · Consola']] }),
        f.debug('S7 · Consola', 600, 360, false),
    ];
}

// ==========================================================================
// Cliente — Raspberry Pi 2 (diagramas/flujo_cliente.md)
// ==========================================================================
function flujoCliente() {
    const tab = id('tab/cliente');
    const f = fabrica('cliente', tab);
    const g = config.gpio;
    const s = config.senales;
    return [
        { id: tab, type: 'tab', label: 'T2 · Cliente OPC UA (RPi 2)', disabled: false,
            info: 'Generado por generar_flujos.js desde config.js v' + config.VERSION + '. No editar a mano: regenerar.' },
        f.comentario('Tarea 2 · Cliente OPC UA · bloques C0-C7 de diagramas/flujo_cliente.md', 'Ver node-red/README.md', 330, 40),
        // C0
        f.inject('C0 · Arranque', 130, 100, { payload: 'clienteOpcua', payloadType: 'str', destinos: ['C0 · Verificar configuracion'] }),
        f.funcion('C0 · Verificar configuracion', 370, 100, {
            archivo: 'comun/funciones/X1_verificar_config.js', salidas: 2,
            destinos: [['C4 · GPIO LED digital'], ['C4 · GPIO LED PWM']],
        }),
        // C2
        f.inject('C2 · Tick ' + s.tickMs + ' ms', 130, 160, { repetirMs: s.tickMs, destinos: ['C2 · Generar rampa triangular'] }),
        f.funcion('C2 · Generar rampa triangular', 380, 160, { archivo: 'cliente/funciones/C2_generar_rampa.js', destinos: [[]] }),
        // C5
        f.inject('C5 · Cada ' + s.periodoEscrituraRampaMs + ' ms', 130, 220, { repetirMs: s.periodoEscrituraRampaMs, destinos: ['C5 · Escribir rampa'] }),
        f.inject('C5 · Detener rampa', 130, 440, { payload: 'true', payloadType: 'bool', topic: 'pausa', unaVez: false, destinos: ['C5 · Escribir rampa'] }),
        f.inject('C5 · Reanudar rampa', 130, 480, { payload: 'false', payloadType: 'bool', topic: 'pausa', unaVez: false, destinos: ['C5 · Escribir rampa'] }),
        f.funcion('C5 · Escribir rampa', 370, 220, { archivo: 'cliente/funciones/C5_escribir_rampa.js', destinos: [['C1 · Cliente OPC UA']] }),
        f.gpioIn('C5 · GPIO pulsador', 130, 280, g.pulsador, ['C5 · Leer pulsador']),
        f.funcion('C5 · Leer pulsador', 350, 280, { archivo: 'comun/funciones/X4_leer_pulsador.js', destinos: [['C5 · Solo al cambiar']] }),
        // El pulsador se escribe SOLO AL CAMBIAR (consigna 3.3): pigpio ya
        // emite un mensaje por flanco, y el filtro rbe lo garantiza aunque
        // llegue un nivel repetido (lectura inicial, rebote residual).
        f.rbe('C5 · Solo al cambiar', 550, 280, ['C1 · Cliente OPC UA']),
        // C1 + C3 + C7
        f.funcion('C1 · Cliente OPC UA', 780, 250, {
            archivo: 'cliente/funciones/C1_cliente_opcua.js',
            inicio: 'cliente/funciones/C1_cliente_opcua.inicio.js',
            fin: 'cliente/funciones/C1_cliente_opcua.fin.js',
            salidas: 2,
            destinos: [['C4 · Replicar en LEDs'], ['C7 · Eventos de conexion']],
        }),
        // C4
        f.funcion('C4 · Replicar en LEDs', 1020, 200, {
            archivo: 'cliente/funciones/C4_replicar.js', salidas: 2,
            destinos: [['C4 · LED digital'], ['C4 · LED PWM']],
        }),
        f.funcion('C4 · LED digital', 1240, 160, { archivo: 'comun/funciones/X6_led_digital.js', destinos: [['C4 · GPIO LED digital']] }),
        f.funcion('C4 · LED PWM', 1240, 220, { archivo: 'comun/funciones/X6_led_pwm.js', destinos: [['C4 · GPIO LED PWM']] }),
        f.gpioOut('C4 · GPIO LED digital', 1480, 160, g.ledDigital, 'out'),
        f.gpioOut('C4 · GPIO LED PWM', 1480, 220, g.ledPwm, 'pwm'),
        // C7
        f.funcion('C7 · Eventos de conexion', 1030, 320, { archivo: 'cliente/funciones/C7_eventos.js', destinos: [['C7 · Registro de eventos']] }),
        f.debug('C7 · Registro de eventos', 1270, 320),
        // C6
        f.inject('C6 · Cada ' + config.consola.periodoMs + ' ms', 130, 380, { repetirMs: config.consola.periodoMs, destinos: ['C6 · Registro en consola'] }),
        f.funcion('C6 · Registro en consola', 370, 380, { archivo: 'cliente/funciones/C6_consola.js', destinos: [['C6 · Consola']] }),
        f.debug('C6 · Consola', 600, 380, false),
    ];
}

/**
 * Descripcion: genera y escribe ambos flows.json.
 * Retorna: (object) { servidor: array, cliente: array }.
 * Excepciones: Error si un archivo de funcion no existe.
 */
function generar() {
    const flujos = { servidor: flujoServidor(), cliente: flujoCliente() };
    for (const [nombre, nodos] of Object.entries(flujos)) {
        const destino = path.join(RAIZ, nombre, 'flows.json');
        fs.writeFileSync(destino, JSON.stringify(nodos, null, 2) + '\n');
        console.log(nombre + ': ' + nodos.length + ' nodos -> ' + path.relative(process.cwd(), destino));
    }
    return flujos;
}

module.exports = { flujoServidor, flujoCliente, generar };

if (require.main === module) generar();
