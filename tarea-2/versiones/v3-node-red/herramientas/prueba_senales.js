/**
 * prueba_senales.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Banco de pruebas de node-red/comun/senales.js y de la coherencia de
 * node-red/comun/config.js. Corre en la PC, sin Raspberry Pi ni Node-RED:
 * si la forma de onda es incorrecta, se detecta aca y no frente a un LED.
 *
 * Uso
 * ---
 *     node --test tarea-2/herramientas/prueba_senales.js
 *
 * Devuelve codigo de salida 0 si todo pasa y distinto de 0 si algo falla.
 *
 * Dependencias externas: Node.js >= 18 (node:test y node:assert, incluidos).
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const COMUN = path.join(__dirname, '..', 'node-red', 'comun');
const s = require(path.join(COMUN, 'senales.js'));
const config = require(path.join(COMUN, 'config.js'));

const { tickMs, periodoSierraMs, periodoTriangularMs, maximo } = config.senales;

/** Muestras de un periodo completo, tomadas en cada tick. */
function periodo(fn, periodoMs, t0 = 0) {
    const valores = [];
    for (let t = t0; t < t0 + periodoMs; t += tickMs) valores.push(fn(t, periodoMs, tickMs));
    return valores;
}

// --------------------------------------------------------------------------
test('1. sierra: extremos, monotonia y retorno a 0', () => {
    const v = periodo(s.sierra, periodoSierraMs);
    assert.equal(v.length, 80, '4000 ms / 50 ms = 80 muestras');
    assert.equal(v[0], 0, 'arranca en 0');
    assert.equal(v[79], maximo, 'la ultima muestra alcanza 65535 exacto');
    for (let i = 1; i < v.length; i++) assert.ok(v[i] > v[i - 1], 'estrictamente creciente en ' + i);
    assert.equal(s.sierra(periodoSierraMs, periodoSierraMs, tickMs), 0, 'vuelve a 0 al cumplir el periodo');
});

test('2. sierra: el valor depende del reloj, no de cuantas veces se llamo', () => {
    // Un tick atrasado 30 ms (event loop ocupado) cae en la misma muestra:
    // el error queda acotado y no se acumula.
    assert.equal(s.sierra(1000, periodoSierraMs, tickMs), s.sierra(1030, periodoSierraMs, tickMs));
    // Periodicidad exacta despues de muchos periodos.
    assert.equal(s.sierra(1234, periodoSierraMs, tickMs), s.sierra(1234 + 1000 * periodoSierraMs, periodoSierraMs, tickMs));
    // Date.now() real (~1,7e12) no rompe la aritmetica.
    const ahora = 1760000000000;
    assert.ok(s.esUInt16(s.sierra(ahora, periodoSierraMs, tickMs)));
});

test('3. triangular: 4 s de subida y 4 s de bajada, simetrica', () => {
    const v = periodo(s.triangular, periodoTriangularMs);
    assert.equal(v.length, 160);
    assert.equal(v[0], 0);
    assert.equal(v[80], maximo, 'pico exacto a los 4000 ms');
    for (let i = 1; i <= 80; i++) assert.ok(v[i] > v[i - 1], 'sube en ' + i);
    for (let i = 81; i < 160; i++) assert.ok(v[i] < v[i - 1], 'baja en ' + i);
    for (let k = 1; k < 80; k++) assert.equal(v[80 - k], v[80 + k], 'simetria en k=' + k);
});

test('4. parametros invalidos se rechazan', () => {
    assert.throws(() => s.sierra(0, 4010, 50), RangeError, 'periodo no multiplo del tick');
    assert.throws(() => s.sierra(0, 4000, 0), RangeError);
    assert.throws(() => s.triangular(0, 150, 50), RangeError, 'cantidad impar de muestras');
});

test('5. escala255: lineal', () => {
    assert.equal(s.escala255(0), 0);
    assert.equal(s.escala255(maximo), 255);
    assert.equal(s.escala255(32768), 128);
    assert.throws(() => s.escala255(-1), RangeError);
    assert.throws(() => s.escala255(65536), RangeError);
    assert.throws(() => s.escala255(1.5), RangeError);
});

test('6. escala255: gamma 2,2', () => {
    const g = config.senales.gamma;
    assert.equal(s.escala255(0, maximo, g), 0);
    assert.equal(s.escala255(maximo, maximo, g), 255);
    // A mitad de escala el duty cae a ~22 %: es lo que el ojo percibe como
    // "la mitad" del brillo (consigna Parte 3.7).
    const medio = s.escala255(32768, maximo, g);
    assert.ok(medio >= 55 && medio <= 56, 'mitad de escala -> ' + medio);
    let previo = -1;
    for (let v = 0; v <= maximo; v += 257) {
        const d = s.escala255(v, maximo, g);
        assert.ok(d >= previo, 'monotona');
        previo = d;
    }
});

test('7. validadores de escritura', () => {
    assert.ok(s.esUInt16(0) && s.esUInt16(65535));
    assert.ok(!s.esUInt16(65536) && !s.esUInt16(-1) && !s.esUInt16('100') && !s.esUInt16(2.5));
    assert.ok(s.esBooleano(true) && s.esBooleano(false));
    assert.ok(!s.esBooleano(1) && !s.esBooleano('true') && !s.esBooleano(null));
});

test('9. conversion al porcentaje del nodo pi-gpiod: exacta en los 256 niveles', () => {
    for (let d = 0; d <= 255; d++) {
        const pct = s.dutyAPorcentajePiGpiod(d);
        assert.ok(pct >= 0 && pct <= 100, 'el nodo rechaza fuera de 0-100: ' + pct);
        // Replica exacta de lo que hace pi-gpiod.js en el modo "pwm".
        // Excepcion documentada: el nodo no puede generar 255, porque su
        // maximo admitido (100) da 100 * 2.55 = 254.99999... en coma flotante
        // y parseInt() lo trunca a 254 (INCONVENIENTES.md, I-02). Error de
        // 1/255 = 0,4 %, imperceptible.
        const esperado = d === 255 ? 254 : d;
        assert.equal(parseInt(pct * 2.55), esperado, 'duty ' + d);
    }
    assert.throws(() => s.dutyAPorcentajePiGpiod(256), RangeError);
});

test('8. config: coherencia con la consigna', () => {
    assert.equal(config.red.ipServidor, '192.168.10.1');
    assert.equal(config.red.ipCliente, '192.168.10.2');
    assert.equal(config.red.puertoOpcUa, 4840);
    assert.equal(config.opcua.namespaceUri, 'urn:unraf:pdci:t2');
    assert.equal(config.opcua.endpointCliente, `opc.tcp://${config.red.ipServidor}:${config.red.puertoOpcUa}`,
        'el endpoint del cliente usa la IP de eth0, no un nombre de host');
    assert.ok(['A', 'B'].includes(config.lectura.modo));
    assert.equal(periodoSierraMs % tickMs, 0);
    assert.equal(periodoTriangularMs % (2 * tickMs), 0);
    const pines = [config.gpio.pulsador, config.gpio.ledDigital, config.gpio.ledPwm];
    assert.equal(new Set(pines).size, 3, 'sin pines repetidos');
    assert.ok(Object.isFrozen(config) && Object.isFrozen(config.senales), 'config inmutable');
});
