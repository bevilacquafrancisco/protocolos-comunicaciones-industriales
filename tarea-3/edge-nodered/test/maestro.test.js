/**
 * maestro.test.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Pruebas unitarias del maestro y de la configuracion, con un esclavo falso en memoria
 * (respuestas armadas con lib/modbus) y sin red ni Python:
 *   - validacion de la configuracion (todo lo que llega del Dashboard es entrada no confiable);
 *   - persistencia atomica en archivo y recuperacion ante un archivo corrupto;
 *   - el mutex del bus: nunca hay dos tramas en vuelo a la vez (RS-485 es semiduplex);
 *   - una sola escritura pendiente por variable (la nueva reemplaza a la vieja);
 *   - tipos de 32 bits y orden de palabras.
 */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const m = require('../lib/modbus');
const tipos = require('../lib/tipos');
const configuracion = require('../lib/configuracion');
const { MaestroModbus, ESTADO } = require('../lib/maestro');

const BASE = configuracion.cargar(null).config;
const clon = () => configuracion.clonar(BASE);

/**
 * Esclavo falso: responde por setImmediate con el mapa del dispositivo 1 y registra si
 * alguna vez hubo dos peticiones sin responder al mismo tiempo.
 */
function esclavoFalso() {
    const estado = { coil: 0, hreg: 0, enVuelo: 0, maximoEnVuelo: 0, peticiones: [] };
    let maestro = null;
    const transporte = {
        enviar(trama) {
            estado.enVuelo += 1;
            estado.maximoEnVuelo = Math.max(estado.maximoEnVuelo, estado.enVuelo);
            estado.peticiones.push(m.toHex(trama));
            const [id, fc] = trama;
            const dir = (trama[2] << 8) | trama[3];
            const arg = (trama[4] << 8) | trama[5];
            let resp;
            if (id !== 1) resp = null;                                  // otro Unit ID: silencio
            else if (dir !== 0) resp = m.appendCrc(Buffer.from([1, fc | 0x80, 2]));
            else if (fc === 1) resp = m.appendCrc(Buffer.from([1, 1, 1, estado.coil]));
            else if (fc === 2) resp = m.appendCrc(Buffer.from([1, 2, 1, 1]));
            else if (fc === 3) resp = m.appendCrc(Buffer.from([1, 3, 2, 0, estado.hreg]));
            else if (fc === 4) resp = m.appendCrc(Buffer.from([1, 4, 2, 0x07, 0xFF]));
            else if (fc === 5) { estado.coil = arg ? 1 : 0; resp = Buffer.from(trama); }
            else if (fc === 6) { estado.hreg = arg; resp = Buffer.from(trama); }
            setTimeout(() => { estado.enVuelo -= 1; if (resp) maestro.recibir(resp); }, 2);
            if (!resp) setTimeout(() => {}, 0);
        },
        reconfigurar: () => Promise.resolve(),
    };
    return { estado, transporte, conectar: (mm) => { maestro = mm; } };
}

function crear(cambios) {
    const cfg = clon();
    Object.assign(cfg.sondeo, { periodoMs: 50, timeoutMs: 40, reintentos: 0, ausenciaMs: 300 }, cambios || {});
    cfg.puerto.esperaReconfiguracionMs = 0;
    const falso = esclavoFalso();
    const maestro = new MaestroModbus({ config: cfg, transporte: falso.transporte });
    falso.conectar(maestro);
    return { maestro, falso };
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
async function hasta(cond, ms = 3000) {
    const fin = Date.now() + ms;
    while (Date.now() < fin) { if (cond()) return true; await esperar(5); }
    return cond();
}

describe('configuracion.validar: entrada del Dashboard no confiable', () => {
    test('la configuracion de fabrica es valida', () => {
        expect(configuracion.validar(clon()).ok).toBe(true);
    });
    test('normaliza numeros que llegan como texto', () => {
        const c = clon();
        c.puerto.baud = '19200'; c.esclavo.id = '17'; c.sondeo.timeoutMs = '500';
        const r = configuracion.validar(c);
        expect(r.ok).toBe(true);
        expect([r.config.puerto.baud, r.config.esclavo.id, r.config.sondeo.timeoutMs]).toEqual([19200, 17, 500]);
    });
    test.each([
        ['Unit ID 0', (c) => { c.esclavo.id = 0; }],
        ['Unit ID 248', (c) => { c.esclavo.id = 248; }],
        ['baud 300', (c) => { c.puerto.baud = 300; }],
        ['paridad "mark"', (c) => { c.puerto.paridad = 'mark'; }],
        ['parada 3', (c) => { c.puerto.bitsParada = 3; }],
        ['ruta con inyeccion', (c) => { c.puerto.ruta = '/dev/ttyUSB0; rm -rf /'; }],
        ['timeout 5 ms', (c) => { c.sondeo.timeoutMs = 5; }],
        ['mapa vacio', (c) => { c.mapa = []; }],
        ['nombre repetido', (c) => { c.mapa[1].nombre = c.mapa[0].nombre; }],
        ['nombre con espacios', (c) => { c.mapa[0].nombre = 'Inputs/Pulsador uno'; }],
        ['FC 5 en el mapa', (c) => { c.mapa[0].fc = 5; }],
        ['bool sobre FC 03', (c) => { c.mapa[3].tipo = 'bool'; }],
        ['uint16 sobre FC 02', (c) => { c.mapa[0].tipo = 'uint16'; }],
        ['escritura sobre FC 04', (c) => { c.mapa[1].escritura = true; }],
        ['direccion 70000', (c) => { c.mapa[0].direccion = 70000; }],
        ['float32 en 0xFFFF', (c) => { c.mapa[3] = { nombre: 'X', fc: 3, direccion: 0xFFFF, tipo: 'float32' }; }],
        ['min > max', (c) => { c.mapa[3].min = 300; }],
        ['65 variables', (c) => { c.mapa = Array.from({ length: 65 }, (_, i) => ({ nombre: `V${i}`, fc: 3, direccion: i, tipo: 'uint16' })); }],
    ])('rechaza: %s', (_t, cambiar) => {
        const c = clon();
        cambiar(c);
        expect(configuracion.validar(c).ok).toBe(false);
    });
    test('7 bits de datos: se admite con aviso (RTU usa 8)', () => {
        const c = clon(); c.puerto.bitsDatos = 7;
        const r = configuracion.validar(c);
        expect(r.ok).toBe(true);
        expect(r.errores.some((e) => e.startsWith('AVISO'))).toBe(true);
    });
    test('una derivada cuya fuente ya no esta en el mapa se descarta sin error', () => {
        const c = clon(); c.mapa = c.mapa.filter((v) => v.nombre !== 'Inputs/Potenciometro');
        const r = configuracion.validar(c);
        expect(r.ok).toBe(true);
        expect(r.config.derivadas).toEqual([]);
    });
    test('paraSerialControl usa los nombres del nodo serial control', () => {
        expect(configuracion.paraSerialControl(BASE.puerto)).toEqual({ serialport: '/dev/ttyUSB0', serialbaud: 9600,
            databits: 8, parity: 'none', stopbits: 1 });
    });
});

describe('configuracion: persistencia en archivo', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-t3-'));
    const ruta = path.join(dir, 'config.json');
    afterAll(() => fs.rmSync(dir, { recursive: true, force: true }));

    test('sin archivo: configuracion de fabrica', () => {
        expect(configuracion.cargar(ruta).origen).toBe('defecto');
    });
    test('guardar y volver a cargar (sobrevive a un reinicio)', () => {
        const c = clon(); c.esclavo.id = 17; c.puerto.baud = 19200;
        configuracion.guardar(ruta, c);
        const r = configuracion.cargar(ruta);
        expect(r.origen).toBe('usuario');
        expect([r.config.esclavo.id, r.config.puerto.baud]).toEqual([17, 19200]);
        expect(fs.readdirSync(dir).filter((f) => f.endsWith('.tmp'))).toEqual([]);   // escritura atomica
    });
    test('archivo corrupto: arranca con la de fabrica y avisa (no aborta)', () => {
        fs.writeFileSync(ruta, '{ esto no es JSON');
        const r = configuracion.cargar(ruta);
        expect(r.origen).toBe('defecto');
        expect(r.avisos.join(' ')).toMatch(/no se pudo leer/);
    });
    test('no guarda una configuracion invalida', () => {
        const c = clon(); c.esclavo.id = 999;
        expect(() => configuracion.guardar(ruta, c)).toThrow(/invalida/);
    });
});

describe('maestro: concurrencia y escrituras', () => {
    test('el sondeo lee las cuatro variables y llega a DONE', async () => {
        const { maestro } = crear();
        maestro.iniciar();
        expect(await hasta(() => maestro.valores.size >= 5 && maestro.estado === ESTADO.DONE)).toBe(true);
        maestro.detener();
    });

    test('mutex del bus: con sondeo, pruebas y escrituras simultaneas nunca hay dos tramas en vuelo', async () => {
        const { maestro, falso } = crear();
        maestro.iniciar();
        await Promise.all([
            maestro.probar({ fc: 4 }), maestro.probar({ fc: 3 }), maestro.escribir('Outputs/LedPWM', 10),
            maestro.tramaManual('01 03 00 00 00 01'), maestro.escribir('Outputs/LedDigital', true),
            maestro.explorar({ fc: 3, desde: 0, hasta: 3, timeoutMs: 20 }),
        ]);
        await esperar(100);
        maestro.detener();
        expect(falso.estado.maximoEnVuelo).toBe(1);
        expect(falso.estado.peticiones.length).toBeGreaterThan(8);
    });

    test('mutex del bus: dos operaciones exclusivas a la vez (exploracion + descubrimiento + reconfiguracion)', async () => {
        // Es el caso que el mutex protege de verdad: el sondeo ya se serializa por la bandera
        // _ocupado, pero dos operaciones exclusivas lanzadas a la vez solo las ordena _tomarBus.
        const { maestro, falso } = crear();
        maestro.iniciar();
        const c = configuracion.clonar(maestro.config); c.sondeo.periodoMs = 60;
        const [exploracion, descubrimiento, reconfiguracion] = await Promise.all([
            maestro.explorar({ fc: 3, desde: 0, hasta: 5, timeoutMs: 15 }),
            maestro.descubrir({ idDesde: 1, idHasta: 3, timeoutMs: 15, combinaciones: [{ baud: 9600, paridad: 'none' }] }),
            maestro.reconfigurar(c),
        ]);
        maestro.detener();
        expect(exploracion.existentes.map((e) => e.direccion)).toEqual([0]);
        expect(descubrimiento.encontrados[0]).toMatchObject({ id: 1 });
        expect(reconfiguracion.ok).toBe(true);
        expect(falso.estado.maximoEnVuelo).toBe(1);
    });

    test('una sola escritura pendiente por variable: la nueva reemplaza a la vieja', async () => {
        const { maestro, falso } = crear();
        // Sin iniciar el sondeo, las escrituras quedan pendientes.
        const vieja = maestro.escribir('Outputs/LedPWM', 10);
        const nueva = maestro.escribir('Outputs/LedPWM', 20);
        expect(await vieja).toMatchObject({ ok: false, errorType: 'SUPERSEDED' });
        maestro.iniciar();
        expect(await nueva).toMatchObject({ ok: true });
        maestro.detener();
        expect(falso.estado.hreg).toBe(20);
        expect(falso.estado.peticiones.filter((p) => p.startsWith('01 06')).length).toBe(1);
    });

    test('reconfigurar conserva los contadores y vuelve a buscar al esclavo', async () => {
        const { maestro } = crear();
        maestro.iniciar();
        await hasta(() => maestro.contadores.OK >= 4);
        const ok = maestro.contadores.OK;
        const c = configuracion.clonar(maestro.config); c.sondeo.periodoMs = 80;
        const r = await maestro.reconfigurar(c);
        expect(r.ok).toBe(true);
        expect(maestro.contadores.OK).toBeGreaterThanOrEqual(ok);
        expect(maestro.config.sondeo.periodoMs).toBe(80);
        maestro.detener();
    });

    test('reconfigurar con datos invalidos no toca nada', async () => {
        const { maestro } = crear();
        const c = configuracion.clonar(maestro.config); c.esclavo.id = 0;
        expect((await maestro.reconfigurar(c)).ok).toBe(false);
        expect(maestro.config.esclavo.id).toBe(1);
    });

    test('ausencia sostenida: DEVICE NOT REACHED con un Unit ID que nadie tiene', async () => {
        const { maestro } = crear();
        maestro.iniciar();
        await hasta(() => maestro.estado === ESTADO.DONE);
        const c = configuracion.clonar(maestro.config); c.esclavo.id = 9;
        await maestro.reconfigurar(c);
        expect(await hasta(() => maestro.contadores.TIMEOUT > 2 && maestro.estado === ESTADO.NO_ALCANZADO)).toBe(true);
        maestro.detener();
    });
});

describe('tipos de dato', () => {
    test('int16, uint32, int32 y float32 con orden de palabras', () => {
        expect(tipos.decodificar('int16', [0xFFFE])).toBe(-2);
        expect(tipos.decodificar('uint32', [0x0001, 0x0002])).toBe(0x00010002);
        expect(tipos.decodificar('uint32', [0x0002, 0x0001], 'CDAB')).toBe(0x00010002);
        expect(tipos.decodificar('int32', [0xFFFF, 0xFFFF])).toBe(-1);
        expect(tipos.decodificar('float32', [0x4049, 0x0FDB])).toBeCloseTo(Math.PI, 5);
        expect(tipos.decodificar('float32', [0x0FDB, 0x4049], 'CDAB')).toBeCloseTo(Math.PI, 5);
    });
    test('codificar valores a escribir', () => {
        expect(tipos.codificar('bool', 'true')).toBe(true);
        expect(tipos.codificar('int16', -1)).toBe(0xFFFF);
        expect(() => tipos.codificar('uint16', 70000)).toThrow(RangeError);
        expect(() => tipos.codificar('bool', 'tal vez')).toThrow(RangeError);
    });
});
