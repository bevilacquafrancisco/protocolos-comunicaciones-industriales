/**
 * integracion_simulador.test.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Criterio de salida de la Fase F3, automatizado y sin hardware: el maestro REAL
 * (lib/maestro.js + lib/transportes.js) contra el simulador REAL
 * (simuladores/esclavo_modbus_sim.py), que ejecuta el stack del firmware del ESP32.
 * Es por lo tanto una prueba cruzada maestro JS <-> esclavo MicroPython.
 *
 *   1. Lee las cuatro variables del dispositivo 1.
 *   2. Escribe el coil y el holding register (y se confirma con la lectura).
 *   3. Cada falla inyectada mueve SU contador y el estado textual (I-05).
 *   4. El asistente de descubrimiento encuentra al esclavo desconocido en < 60 s.
 *   5. Reconfiguracion en vivo al mapa del esclavo desconocido, sin reiniciar (I-04).
 *
 * Requiere Python 3.10+ en el PATH (o la variable PYTHON). Si no esta, se omite.
 *
 * Uso: npm test -- integracion
 */
'use strict';

const { spawn, spawnSync } = require('node:child_process');
const path = require('node:path');
const { MaestroModbus, ESTADO } = require('../lib/maestro');
const { TransporteTcp } = require('../lib/transportes');
const configuracion = require('../lib/configuracion');

const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const SIMULADORES = path.join(__dirname, '..', '..', 'simuladores');
const hayPython = spawnSync(PYTHON, ['--version']).status === 0;
const describirSi = hayPython ? describe : describe.skip;

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

/** Espera hasta que condicion() sea verdadera o vence. */
async function hasta(condicion, ms = 5000, paso = 20) {
    const fin = Date.now() + ms;
    while (Date.now() < fin) {
        if (condicion()) return true;
        await esperar(paso);
    }
    return condicion();
}

/** Arranca un simulador y espera su linea LISTO. */
function arrancarSimulador(script, args) {
    return new Promise((resolver, rechazar) => {
        const proceso = spawn(PYTHON, ['-u', path.join(SIMULADORES, script), ...args], { stdio: ['pipe', 'pipe', 'pipe'] });
        let salida = '';
        proceso.stdout.on('data', (d) => {
            salida += d.toString();
            if (salida.includes('LISTO')) resolver(proceso);
        });
        proceso.stderr.on('data', (d) => { salida += d.toString(); });
        proceso.on('exit', (codigo) => rechazar(new Error(`simulador termino (${codigo}): ${salida}`)));
        setTimeout(() => rechazar(new Error(`simulador sin LISTO: ${salida}`)), 10000).unref();
    });
}

/** Maestro con transporte TCP hacia el simulador. */
async function crearMaestro(direccion, cambios = {}) {
    const base = configuracion.cargar(null).config;
    const config = configuracion.clonar(base);
    Object.assign(config.puerto, { tipo: 'tcp', tcp: direccion, esperaReconfiguracionMs: 50 });
    Object.assign(config.sondeo, { periodoMs: 100, timeoutMs: 150, reintentos: 1, ausenciaMs: 700 }, cambios.sondeo || {});
    const tcp = new TransporteTcp(direccion);
    const maestro = new MaestroModbus({ config, transporte: tcp });
    tcp.on('datos', (d) => maestro.recibir(d));
    await tcp.reconfigurar(config.puerto);
    return { maestro, tcp };
}

describirSi('F3 · maestro JS contra el simulador con el stack del firmware', () => {
    let sim; let maestro; let tcp;
    const PUERTO = '127.0.0.1:5031';

    beforeAll(async () => {
        sim = await arrancarSimulador('esclavo_modbus_sim.py', ['--tcp', PUERTO, '--manual']);
        ({ maestro, tcp } = await crearMaestro(PUERTO));
        maestro.iniciar();
    });
    afterAll(() => {
        if (maestro) maestro.detener();
        if (tcp) tcp.destruir();
        if (sim) sim.kill();
    });

    const comando = (texto) => sim.stdin.write(texto + '\n');

    test('1 · lee las cuatro variables del dispositivo 1', async () => {
        comando('pote 2047');
        comando('pulsador 1');
        const ok = await hasta(() => maestro.valores.get('Inputs/Potenciometro')?.valor === 2047
            && maestro.valores.get('Inputs/Pulsador')?.valor === true
            && maestro.valores.has('Outputs/LedDigital') && maestro.valores.has('Outputs/LedPWM'));
        expect(ok).toBe(true);
        expect(maestro.valores.get('Inputs/Potenciometro_pct').valor).toBe(50);   // derivada (ADR-003)
        expect(maestro.estado).toBe(ESTADO.DONE);
        expect(maestro.contadores.OK).toBeGreaterThanOrEqual(4);
        expect(maestro.ultimaTx).toMatch(/^01 0[1-4] 00 00 00 01/);
    });

    test('2 · escribe coil y holding register; la lectura lo confirma', async () => {
        const [coil, hreg] = await Promise.all([
            maestro.escribir('Outputs/LedDigital', true), maestro.escribir('Outputs/LedPWM', 200)]);
        expect(coil).toMatchObject({ ok: true, errorType: 'NONE' });
        expect(hreg).toMatchObject({ ok: true, errorType: 'NONE' });
        expect(await hasta(() => maestro.valores.get('Outputs/LedDigital')?.valor === true
            && maestro.valores.get('Outputs/LedPWM')?.valor === 200)).toBe(true);
    });

    test('2b · un valor fuera de rango no llega al bus', async () => {
        const antes = maestro.contadores.OK;
        expect(await maestro.escribir('Outputs/LedPWM', 300)).toMatchObject({ ok: false, errorType: 'VALOR_INVALIDO' });
        expect(await maestro.escribir('Inputs/Pulsador', true)).toMatchObject({ ok: false, errorType: 'NO_ESCRIBIBLE' });
        expect(maestro.contadores.OK).toBeGreaterThanOrEqual(antes);
    });

    test('3a · falla "crc": sube CRC_ERROR y el estado pasa a CRC ERROR', async () => {
        const antes = maestro.contadores.CRC_ERROR;
        comando('falla crc 0.5');
        expect(await hasta(() => maestro.contadores.CRC_ERROR >= antes + 3 && maestro.estado === ESTADO.CRC_ERROR)).toBe(true);
        expect(maestro.contadores.detalle.CRC_ERROR).toBeGreaterThan(0);
    });

    test('3b · falla "truncada": trama no recomponible, cuenta como CRC_ERROR', async () => {
        const antes = maestro.contadores.CRC_ERROR;
        comando('falla truncada 0.5');
        expect(await hasta(() => maestro.contadores.CRC_ERROR >= antes + 3)).toBe(true);
    });

    test('3c · falla "excepcion": sube EXCEPTION y el esclavo sigue alcanzado', async () => {
        const antes = maestro.contadores.EXCEPTION;
        comando('falla excepcion 1');
        expect(await hasta(() => maestro.contadores.EXCEPTION >= antes + 4)).toBe(true);
        expect(maestro.ultimaExcepcion).toBe(4);
        expect(maestro.estado).toBe(ESTADO.DONE);
    });

    test('3d · falla "silencio": sube TIMEOUT y, sostenida, DEVICE NOT REACHED', async () => {
        const antes = maestro.contadores.TIMEOUT;
        comando('falla silencio 1');
        expect(await hasta(() => maestro.estado === ESTADO.NO_ALCANZADO, 5000)).toBe(true);
        expect(maestro.contadores.TIMEOUT).toBeGreaterThan(antes);
        expect(maestro.valores.get('Inputs/Potenciometro').calidad).toBe('bad');
    });

    test('3e · falla "retardo" mayor que el timeout: TIMEOUT', async () => {
        comando('falla ninguna');
        await hasta(() => maestro.estado === ESTADO.DONE);
        const antes = maestro.contadores.TIMEOUT;
        comando('falla retardo 1 400');
        expect(await hasta(() => maestro.contadores.TIMEOUT >= antes + 2, 8000)).toBe(true);
    });

    test('3f · sin fallas se recupera solo: DONE y calidad good', async () => {
        comando('falla ninguna');
        expect(await hasta(() => maestro.estado === ESTADO.DONE
            && maestro.valores.get('Inputs/Potenciometro')?.calidad === 'good', 8000)).toBe(true);
    });

    test('probar conexion devuelve la trama cruda de ida y vuelta con el CRC validado', async () => {
        const r = await maestro.probar({ fc: 4, direccion: 0, cantidad: 1 });
        expect(r.ok).toBe(true);
        expect(r.tx).toBe('01 04 00 00 00 01 31 CA');
        expect(r.rx).toBe('01 04 02 07 FF FB 40');   // pote fijado en 2047 = vector golden
        expect(r.crcValido).toBe(true);
    });

    test('trama manual: el maestro agrega el CRC propio', async () => {
        const r = await maestro.tramaManual('01 03 00 00 00 01');
        expect(r.tx).toBe('01 03 00 00 00 01 84 0A');
        expect(r.crcValido).toBe(true);
    });
});

describirSi('F3 · I-04: descubrimiento y reconfiguracion en vivo contra el esclavo desconocido', () => {
    let sim; let maestro; let tcp;
    const PUERTO = '127.0.0.1:5032';

    afterEach(() => {
        if (maestro) maestro.detener();
        if (tcp) tcp.destruir();
        if (sim) sim.kill();
        maestro = tcp = sim = null;
    });

    test('encuentra al esclavo desconocido (ID 17, 19200 8E1) en < 60 s y se reconfigura en vivo', async () => {
        sim = await arrancarSimulador('esclavo_desconocido_sim.py', ['--tcp', PUERTO, '--manual']);
        // El maestro arranca con la configuracion del dispositivo 1: 9600 8N1, Unit ID 1.
        ({ maestro, tcp } = await crearMaestro(PUERTO));
        maestro.iniciar();
        await hasta(() => maestro.contadores.TIMEOUT > 0, 3000);
        expect(maestro.estado).toBe(ESTADO.NO_ALCANZADO);       // nadie responde con 9600 8N1 / ID 1

        const r = await maestro.descubrir({ timeoutMs: 60 });
        expect(r.encontrados).toHaveLength(1);
        expect(r.encontrados[0]).toMatchObject({ id: 17, baud: 19200, paridad: 'even' });
        expect(r.encontrados[0].respuesta).toBe('excepcion 2');  // no tiene HR 0: igual responde
        console.info(`descubrimiento ID 17 19200 8E1: ${(r.duracionMs / 1000).toFixed(2)} s, ${r.probadas} pruebas`);
        expect(r.duracionMs).toBeLessThan(60000);

        // Exploracion de las direcciones de holding registers del desconocido.
        const nueva = configuracion.clonar(maestro.config);
        Object.assign(nueva.puerto, { baud: 19200, paridad: 'even' });
        nueva.esclavo.id = 17;
        await maestro.reconfigurar(nueva);
        const exploracion = await maestro.explorar({ fc: 3, desde: 0x01FE, hasta: 0x0203, timeoutMs: 100 });
        expect(exploracion.existentes.map((e) => e.direccion)).toEqual([0x0200, 0x0201]);

        // Mapa nuevo, en vivo: sin reiniciar el maestro.
        nueva.mapa = [
            { nombre: 'Inputs/Pulsador', fc: 2, direccion: 0x0010, tipo: 'bool' },
            { nombre: 'Inputs/Potenciometro', fc: 4, direccion: 0x0100, tipo: 'uint16' },
            { nombre: 'Outputs/LedDigital', fc: 1, direccion: 0x0020, tipo: 'bool', escritura: true },
            { nombre: 'Outputs/LedPWM', fc: 3, direccion: 0x0200, tipo: 'uint16', escritura: true, min: 0, max: 255 },
            { nombre: 'Outputs/Consigna', fc: 3, direccion: 0x0201, tipo: 'uint16', escritura: true },
        ];
        expect((await maestro.reconfigurar(nueva)).ok).toBe(true);
        sim.stdin.write('pote 1234\n');
        expect(await hasta(() => maestro.valores.get('Inputs/Potenciometro')?.valor === 1234
            && maestro.valores.get('Outputs/Consigna')?.valor === 500, 5000)).toBe(true);
        expect(maestro.estado).toBe(ESTADO.DONE);
        expect(await maestro.escribir('Outputs/LedPWM', 77)).toMatchObject({ ok: true });
        // Consigna admite 0..1000 en el esclavo: 2000 lo rechaza con excepcion 03.
        expect(await maestro.escribir('Outputs/Consigna', 2000)).toMatchObject({ ok: false, errorType: 'EXCEPTION', exceptionCode: 3 });
    });

    test('combinacion tardia (ID 5, 38400 8O1): la fase de IDs habituales lo encuentra en < 60 s', async () => {
        sim = await arrancarSimulador('esclavo_desconocido_sim.py',
            ['--tcp', PUERTO, '--manual', '--id', '5', '--baud', '38400', '--paridad', 'odd']);
        ({ maestro, tcp } = await crearMaestro(PUERTO));
        const r = await maestro.descubrir({ timeoutMs: 60 });
        expect(r.encontrados[0]).toMatchObject({ id: 5, baud: 38400, paridad: 'odd' });
        console.info(`descubrimiento ID 5 38400 8O1: ${(r.duracionMs / 1000).toFixed(2)} s, ${r.probadas} pruebas`);
        expect(r.duracionMs).toBeLessThan(60000);
    });
});
