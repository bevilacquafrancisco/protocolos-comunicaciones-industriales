/**
 * modbus.test.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Pruebas de lib/modbus.js. El CRC se verifica contra tests/fixtures/crc_vectors.json:
 * los MISMOS vectores que prueba el firmware del esclavo (plan de pruebas N1.1). Si las
 * dos implementaciones pasan los mismos vectores generados por oraculos independientes
 * (pymodbus y la rutina de la T1), maestro y esclavo coinciden byte a byte.
 *
 * Uso: npm test (en tarea-3/edge-nodered)
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const m = require('../lib/modbus');

const VECTORES = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', '..', 'tests', 'fixtures', 'crc_vectors.json'), 'utf8')).vectores;
const vec = Object.fromEntries(VECTORES.map((v) => [v.nombre, v]));
const hx = m.fromHex;

describe('N1.1 · CRC-16/MODBUS contra los vectores golden compartidos con el ESP32', () => {
    test('hay al menos 20 vectores', () => expect(VECTORES.length).toBeGreaterThanOrEqual(20));

    test.each(VECTORES.map((v) => [v.nombre, v]))('%s', (_nombre, v) => {
        const mensaje = hx(v.mensaje_hex);
        expect(m.crc16(mensaje)).toBe(v.crc);
        expect(m.crc16Bitwise(mensaje)).toBe(v.crc);
        expect(m.toHex(m.appendCrc(mensaje))).toBe(v.trama_hex);   // byte bajo primero
        expect(m.checkCrc(hx(v.trama_hex))).toBe(true);
        expect(m.crc16(hx(v.trama_hex))).toBe(0);                  // propiedad del residuo
    });

    test('vector estandar 123456789 = 0x4B37, en el cable 37 4B', () => {
        expect(m.crc16(Buffer.from('123456789'))).toBe(0x4B37);
        expect(vec.vector_estandar.crc_en_cable_hex).toBe('37 4B');
    });

    test('cualquier error de 1 bit invalida la trama', () => {
        for (const nombre of ['fc04_peticion', 'fc06_peticion', 'longitud_maxima']) {
            const trama = hx(vec[nombre].trama_hex);
            for (let i = 0; i < trama.length * 8; i++) {
                const t = Buffer.from(trama);
                t[i >> 3] ^= 1 << (i & 7);
                expect(m.checkCrc(t)).toBe(false);
            }
        }
    });

    test('checkCrc rechaza tramas de menos de 4 bytes', () => {
        expect(m.checkCrc(Buffer.alloc(0))).toBe(false);
        expect(m.checkCrc(hx('01 04 31'))).toBe(false);
        expect(m.checkCrc(hx(vec.longitud_minima.trama_hex))).toBe(true);
    });
});

describe('[DF-2.5] buildRequest', () => {
    test.each([
        ['fc01_peticion', { slaveId: 1, fc: 1, address: 0, quantity: 1 }],
        ['fc02_peticion', { slaveId: 1, fc: 2, address: 0, quantity: 1 }],
        ['fc03_peticion', { slaveId: 1, fc: 3, address: 0, quantity: 1 }],
        ['fc04_peticion', { slaveId: 1, fc: 4, address: 0, quantity: 1 }],
        ['fc05_peticion_on', { slaveId: 1, fc: 5, address: 0, value: true }],
        ['fc05_peticion_off', { slaveId: 1, fc: 5, address: 0, value: false }],
        ['fc06_peticion', { slaveId: 1, fc: 6, address: 0, value: 128 }],
        ['desconocido_fc03', { slaveId: 17, fc: 3, address: 0x0200, quantity: 2 }],
        ['difusion_fc06', { slaveId: 0, fc: 6, address: 0, value: 0x40 }],
    ])('%s = vector golden', (nombre, req) => {
        expect(m.toHex(m.buildRequest(req))).toBe(vec[nombre].trama_hex);
    });

    test.each([
        [{ slaveId: 248, fc: 3, address: 0 }, 'slaveId 248'],
        [{ slaveId: 1, fc: 3, address: 0x10000 }, 'direccion 0x10000'],
        [{ slaveId: 1, fc: 3, address: 0, quantity: 126 }, 'FC 03 cantidad 126'],
        [{ slaveId: 1, fc: 1, address: 0, quantity: 2001 }, 'FC 01 cantidad 2001'],
        [{ slaveId: 1, fc: 3, address: 0, quantity: 0 }, 'cantidad 0'],
        [{ slaveId: 1, fc: 6, address: 0, value: 70000 }, 'FC 06 valor 70000'],
        [{ slaveId: 1, fc: 7, address: 0 }, 'FC 07'],
        [{ slaveId: 0, fc: 3, address: 0 }, 'lectura en difusion'],
        [{ slaveId: 1, fc: 3, address: 0xFFFF, quantity: 2 }, 'rango mas alla de 0xFFFF'],
        [{ slaveId: 1.5, fc: 3, address: 0 }, 'slaveId no entero'],
    ])('rechaza %#: %s', (req) => {
        expect(() => m.buildRequest(req)).toThrow(RangeError);
    });
});

describe('[DF-2.8] longitud esperada', () => {
    test('normales y excepcion', () => {
        expect(m.expectedLength({ fc: 1, quantity: 1 })).toBe(6);
        expect(m.expectedLength({ fc: 2, quantity: 9 })).toBe(7);
        expect(m.expectedLength({ fc: 3, quantity: 2 })).toBe(9);
        expect(m.expectedLength({ fc: 4, quantity: 125 })).toBe(255);
        expect(m.expectedLength({ fc: 5 })).toBe(8);
        expect(m.expectedLength({ fc: 6 })).toBe(8);
        expect(m.responseLengthSoFar(hx('01'), { fc: 4 })).toBeNull();
        expect(m.responseLengthSoFar(hx('01 84'), { fc: 4 })).toBe(5);
        expect(m.responseLengthSoFar(hx('01 04'), { fc: 4, quantity: 1 })).toBe(7);
    });
});

describe('[DF-2.10] a [DF-2.12] parseResponse', () => {
    const req04 = { slaveId: 1, fc: 4, address: 0, quantity: 1 };

    test('respuesta normal FC 04 (golden)', () => {
        const r = m.parseResponse(hx(vec.fc04_respuesta.trama_hex), req04);
        expect(r).toEqual({ ok: true, data: [2047], error: null, errorType: 'NONE', exceptionCode: null });
    });
    test('FC 01, 02 y 03 (golden)', () => {
        expect(m.parseResponse(hx(vec.fc01_respuesta.trama_hex), { slaveId: 1, fc: 1, address: 0, quantity: 1 }).data).toEqual([1]);
        expect(m.parseResponse(hx(vec.fc02_respuesta.trama_hex), { slaveId: 1, fc: 2, address: 0, quantity: 1 }).data).toEqual([1]);
        expect(m.parseResponse(hx(vec.fc03_respuesta.trama_hex), { slaveId: 1, fc: 3, address: 0, quantity: 1 }).data).toEqual([128]);
    });
    test('bits multiples: el primero en el LSB', () => {
        const resp = m.appendCrc(hx('11 01 02 05 01'));          // 10 bits: 1,0,1,0,0,0,0,0 , 1,0
        const r = m.parseResponse(resp, { slaveId: 17, fc: 1, address: 0x20, quantity: 10 });
        expect(r.data).toEqual([1, 0, 1, 0, 0, 0, 0, 0, 1, 0]);
    });
    test('eco de FC 05 y FC 06 (golden)', () => {
        expect(m.parseResponse(hx(vec.fc05_peticion_on.trama_hex), { slaveId: 1, fc: 5, address: 0, value: true }).ok).toBe(true);
        expect(m.parseResponse(hx(vec.fc06_peticion.trama_hex), { slaveId: 1, fc: 6, address: 0, value: 128 }).data)
            .toEqual({ address: 0, value: 128 });
    });
    test('TIMEOUT si no hay respuesta', () => {
        expect(m.parseResponse(null, req04).errorType).toBe('TIMEOUT');
        expect(m.parseResponse(Buffer.alloc(0), req04).errorType).toBe('TIMEOUT');
    });
    test('CRC_ERROR con un bit alterado', () => {
        const t = hx(vec.fc04_respuesta.trama_hex);
        t[4] ^= 0x10;
        expect(m.parseResponse(t, req04).errorType).toBe('CRC_ERROR');
    });
    test('EXCEPTION 01-04 con su codigo (golden)', () => {
        for (const [n, fc, code] of [['excepcion_01', 7, 1], ['excepcion_02', 4, 2], ['excepcion_03', 6, 3], ['excepcion_04', 3, 4]]) {
            const r = m.parseResponse(hx(vec[n].trama_hex), { slaveId: 1, fc, address: 0, value: 0 });
            expect(r.errorType).toBe('EXCEPTION');
            expect(r.exceptionCode).toBe(code);
        }
    });
    test('WRONG_SLAVE si responde otro Unit ID', () => {
        expect(m.parseResponse(m.appendCrc(hx('02 04 02 07 FF')), req04).errorType).toBe('WRONG_SLAVE');
    });
    test('MALFORMED: largo, FC, conteo y eco incoherentes', () => {
        expect(m.parseResponse(hx('01 04 02'), req04).errorType).toBe('MALFORMED');
        expect(m.parseResponse(m.appendCrc(hx('01 03 02 07 FF')), req04).errorType).toBe('MALFORMED');
        expect(m.parseResponse(m.appendCrc(hx('01 04 02 07 FF 00')), req04).errorType).toBe('MALFORMED');
        expect(m.parseResponse(m.appendCrc(hx('01 04 04 07 FF')), req04).errorType).toBe('MALFORMED');
        expect(m.parseResponse(m.appendCrc(hx('01 06 00 00 00 81')), { slaveId: 1, fc: 6, address: 0, value: 128 }).errorType)
            .toBe('MALFORMED');
    });
});

describe('[DF-2.6] tiempos', () => {
    test('t3,5 calculado y fijo por encima de 19200', () => {
        expect(m.t35ms(9600)).toBeCloseTo(4.0104, 3);
        expect(m.t35ms(19200)).toBeCloseTo(2.0052, 3);
        expect(m.t35ms(38400)).toBe(1.75);
        expect(m.t35ms(115200)).toBe(1.75);
        expect(m.t15ms(9600)).toBeCloseTo(1.7188, 3);
        expect(m.t15ms(115200)).toBe(0.75);
        expect(() => m.t35ms(0)).toThrow(RangeError);
    });
    test('coincide con el esclavo (firmware: 4011 us y 2006 us redondeado hacia arriba)', () => {
        expect(Math.ceil(m.t35ms(9600) * 1000)).toBe(4011);
        expect(Math.ceil(m.t35ms(19200) * 1000)).toBe(2006);
    });
});

describe('utilidades', () => {
    test('toHex y fromHex', () => {
        expect(m.toHex(hx('01:04-00 00'))).toBe('01 04 00 00');
        expect(() => hx('0G')).toThrow(RangeError);
        expect(() => hx('012')).toThrow(RangeError);
        expect(m.toHex(null)).toBe('');
    });
});
