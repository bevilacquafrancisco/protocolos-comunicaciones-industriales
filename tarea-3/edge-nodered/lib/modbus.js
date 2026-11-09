/**
 * modbus.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Protocolo MODBus RTU del MAESTRO, en JavaScript puro (sin Node-RED ni puerto serie):
 * CRC-16 propio, armado de peticiones, validacion de respuestas y tiempos del enlace.
 * Cumple el invariante I-01: ninguna biblioteca de protocolo genera ni verifica el CRC.
 *
 * Es el mismo algoritmo que el esclavo (firmware/esclavo-modbus/lib/modbus_slave/crc16.py)
 * y se prueba contra los MISMOS vectores golden (tests/fixtures/crc_vectors.json).
 *
 * Orden de bytes: todos los campos de 16 bits de MODBus viajan big-endian (MSB primero);
 * el CRC es la unica excepcion y viaja con el byte bajo primero.
 *
 * Bloques del diagrama de flujo (docs/diagramas/flujo-maestro.mmd):
 *   [DF-2.5]  buildRequest()        armado de la ADU con CRC propio
 *   [DF-2.8]  expectedLength(), responseLengthSoFar()  longitud esperada de la respuesta
 *   [DF-2.10] [DF-2.11] [DF-2.12] parseResponse()  validacion de Unit ID, FC, CRC y excepcion
 *   [DF-2.6]  t35ms()               cota inferior del silencio entre tramas
 *
 * Dependencias externas: ninguna (Node.js >= 18).
 */
'use strict';

// =============================================================================
// Constantes de la especificacion
// =============================================================================

/** Codigos de funcion soportados. */
const FC = Object.freeze({
    READ_COILS: 0x01,
    READ_DISCRETE_INPUTS: 0x02,
    READ_HOLDING_REGISTERS: 0x03,
    READ_INPUT_REGISTERS: 0x04,
    WRITE_SINGLE_COIL: 0x05,
    WRITE_SINGLE_REGISTER: 0x06,
});

/** Tipos de error de parseResponse() (consigna 1.c y plan de pruebas N4). */
const ERROR_TYPE = Object.freeze({
    NONE: 'NONE',
    CRC_ERROR: 'CRC_ERROR',       // CRC invalido
    TIMEOUT: 'TIMEOUT',           // no llego respuesta
    EXCEPTION: 'EXCEPTION',       // el esclavo respondio con FC | 0x80
    MALFORMED: 'MALFORMED',       // la trama no se pudo recomponer (longitud, FC, eco)
    WRONG_SLAVE: 'WRONG_SLAVE',   // respondio otro Unit ID
});

/** Nombres de las excepciones (MODBUS Application Protocol V1.1b3, §7). */
const EXCEPTION_NAMES = Object.freeze({
    1: 'ILLEGAL FUNCTION', 2: 'ILLEGAL DATA ADDRESS', 3: 'ILLEGAL DATA VALUE',
    4: 'SLAVE DEVICE FAILURE', 5: 'ACKNOWLEDGE', 6: 'SLAVE DEVICE BUSY',
    8: 'MEMORY PARITY ERROR', 10: 'GATEWAY PATH UNAVAILABLE', 11: 'GATEWAY TARGET FAILED',
});

/** Limites de cantidad por lectura (ADU de 256 bytes; V1.1b3 §6.1 a §6.4). */
const MAX_READ_BITS = 2000;
const MAX_READ_REGISTERS = 125;

/** Bits por caracter que la norma toma para los tiempos (MODBus over Serial Line §2.5.1). */
const BITS_PER_CHAR = 11;

// =============================================================================
// CRC-16/MODBUS — [DF-2.5] generacion · [DF-2.10b] verificacion
// =============================================================================

/** Polinomio 0x8005 en forma reflejada: los bits se procesan del LSB al MSB. */
const POLY_REFLECTED = 0xA001;
/** Valor inicial: con 0x0000 no se detectarian ceros agregados al comienzo. */
const CRC_INIT = 0xFFFF;

/** Tabla de 256 entradas: el efecto de los 8 desplazamientos para cada byte posible. */
const CRC_TABLE = (() => {
    const table = new Uint16Array(256);
    for (let byte = 0; byte < 256; byte++) {
        let reg = byte;
        for (let bit = 0; bit < 8; bit++) {
            reg = (reg & 1) ? ((reg >>> 1) ^ POLY_REFLECTED) : (reg >>> 1);
        }
        table[byte] = reg;
    }
    return table;
})();

/**
 * Calcula el CRC-16/MODBUS de un buffer.
 * @param {Buffer|Uint8Array} buffer  mensaje (direccion + PDU), sin CRC
 * @param {number} [start=0]          primer indice incluido
 * @param {number} [end]              indice final excluido (por defecto, el largo)
 * @returns {number} valor del registro CRC, 0x0000-0xFFFF
 * @example crc16(Buffer.from('123456789')) === 0x4B37
 */
function crc16(buffer, start = 0, end = buffer.length) {
    let reg = CRC_INIT;
    for (let i = start; i < end; i++) {
        reg = (reg >>> 8) ^ CRC_TABLE[(reg ^ buffer[i]) & 0xFF];
    }
    return reg;
}

/**
 * Version bit a bit (definicion del algoritmo). Misma salida que crc16(); existe para
 * explicar el mecanismo y para que las pruebas comparen ambas.
 * @param {Buffer|Uint8Array} buffer
 * @returns {number}
 */
function crc16Bitwise(buffer) {
    let reg = CRC_INIT;
    for (const byte of buffer) {
        reg ^= byte;
        for (let bit = 0; bit < 8; bit++) {
            reg = (reg & 1) ? ((reg >>> 1) ^ POLY_REFLECTED) : (reg >>> 1);
        }
    }
    return reg;
}

/**
 * [DF-2.5] Agrega el CRC al final del mensaje, byte bajo primero.
 * @param {Buffer|Uint8Array} message
 * @returns {Buffer} mensaje + 2 bytes de CRC
 */
function appendCrc(message) {
    const crc = crc16(message);
    return Buffer.concat([Buffer.from(message), Buffer.from([crc & 0xFF, crc >>> 8])]);
}

/**
 * [DF-2.10b] Verifica el CRC de una trama completa.
 * @param {Buffer|Uint8Array} frame
 * @returns {boolean} false si tiene menos de 4 bytes o si el CRC no coincide
 */
function checkCrc(frame) {
    if (!frame || frame.length < 4) return false;
    const n = frame.length;
    return crc16(frame, 0, n - 2) === (frame[n - 2] | (frame[n - 1] << 8));
}

// =============================================================================
// [DF-2.5] Armado de peticiones
// =============================================================================

/** Lanza RangeError si v no es un entero en [min, max]. */
function requireInt(v, min, max, name) {
    if (!Number.isInteger(v) || v < min || v > max) {
        throw new RangeError(`${name} fuera de rango [${min}, ${max}]: ${v}`);
    }
}

/**
 * [DF-2.5] Arma la peticion completa (ADU) con CRC propio.
 *
 * @param {object} req
 * @param {number} req.slaveId   Unit ID 0-247 (0 = difusion, solo escrituras)
 * @param {number} req.fc        codigo de funcion 1-6
 * @param {number} req.address   offset 0x0000-0xFFFF (NO la notacion Modicon)
 * @param {number} [req.quantity=1]  cantidad para FC 01-04
 * @param {number|boolean} [req.value]  valor para FC 05 (boolean) o FC 06 (0-65535)
 * @returns {Buffer} 8 bytes: ID, FC, direccion (2), cantidad o valor (2), CRC (2)
 * @throws {RangeError} parametros fuera de rango; difusion con lectura
 * @example buildRequest({slaveId: 1, fc: 4, address: 0, quantity: 1}) // 01 04 00 00 00 01 31 CA
 */
function buildRequest({ slaveId, fc, address, quantity = 1, value }) {
    requireInt(slaveId, 0, 247, 'slaveId');
    requireInt(address, 0, 0xFFFF, 'address');
    let arg;
    switch (fc) {
        case FC.READ_COILS:
        case FC.READ_DISCRETE_INPUTS:
            requireInt(quantity, 1, MAX_READ_BITS, 'quantity');
            arg = quantity;
            break;
        case FC.READ_HOLDING_REGISTERS:
        case FC.READ_INPUT_REGISTERS:
            requireInt(quantity, 1, MAX_READ_REGISTERS, 'quantity');
            arg = quantity;
            break;
        case FC.WRITE_SINGLE_COIL:
            // FC 05: 0xFF00 = encendido, 0x0000 = apagado; ningun otro valor es valido.
            arg = value ? 0xFF00 : 0x0000;
            break;
        case FC.WRITE_SINGLE_REGISTER:
            requireInt(value, 0, 0xFFFF, 'value');
            arg = value;
            break;
        default:
            throw new RangeError(`codigo de funcion no soportado: ${fc}`);
    }
    if (slaveId === 0 && fc <= FC.READ_INPUT_REGISTERS) {
        throw new RangeError('la difusion (Unit ID 0) solo admite escrituras');
    }
    if (fc <= FC.READ_INPUT_REGISTERS && address + quantity - 1 > 0xFFFF) {
        throw new RangeError('el rango pedido supera la direccion 0xFFFF');
    }
    // Campos de 16 bits en big-endian: MSB primero.
    return appendCrc(Buffer.from([slaveId, fc, address >>> 8, address & 0xFF, arg >>> 8, arg & 0xFF]));
}

// =============================================================================
// [DF-2.8] Longitud esperada de la respuesta (delimitacion por longitud, ADR-012)
// =============================================================================

/**
 * [DF-2.8] Longitud de la respuesta NORMAL a una peticion.
 * @param {{fc:number, quantity?:number}} req
 * @returns {number} bytes: 5 + ceil(q/8) (FC 01/02) · 5 + 2q (FC 03/04) · 8 (FC 05/06)
 */
function expectedLength({ fc, quantity = 1 }) {
    if (fc === FC.READ_COILS || fc === FC.READ_DISCRETE_INPUTS) return 5 + Math.ceil(quantity / 8);
    if (fc === FC.READ_HOLDING_REGISTERS || fc === FC.READ_INPUT_REGISTERS) return 5 + 2 * quantity;
    return 8;
}

/** Longitud de una respuesta de excepcion: ID, FC | 0x80, codigo, CRC (2). */
const EXCEPTION_LENGTH = 5;

/**
 * [DF-2.8] Cuantos bytes tiene que tener la respuesta, mirando lo recibido hasta ahora.
 *
 * El maestro sabe que pregunto, asi que sabe cuanto esperar: no necesita detectar el
 * silencio t3,5, que Node-RED no puede medir con precision (docs/spike-nodered-opcua.md §3).
 *
 * @param {Buffer} received  bytes recibidos hasta el momento
 * @param {{fc:number, quantity?:number}} req  la peticion
 * @returns {number|null} longitud total esperada, o null si todavia no se puede saber
 */
function responseLengthSoFar(received, req) {
    if (!received || received.length < 2) return null;
    if (received[1] & 0x80) return EXCEPTION_LENGTH;
    return expectedLength(req);
}

// =============================================================================
// [DF-2.10] a [DF-2.12] Validacion de la respuesta
// =============================================================================

/** Lee un entero de 16 bits big-endian. */
const u16 = (buf, i) => (buf[i] << 8) | buf[i + 1];

/**
 * [DF-2.10] a [DF-2.12] Valida y decodifica una respuesta.
 *
 * Orden de las verificaciones: presencia (TIMEOUT) -> longitud minima (MALFORMED) ->
 * CRC (CRC_ERROR) -> Unit ID (WRONG_SLAVE) -> codigo de funcion y excepcion (EXCEPTION)
 * -> longitud, conteo de bytes y eco (MALFORMED). El CRC va antes que el Unit ID: si el
 * CRC falla, el Unit ID recibido tampoco es confiable.
 *
 * @param {Buffer|null} buffer  respuesta completa (o null/vacio si vencio el tiempo)
 * @param {{slaveId:number, fc:number, address:number, quantity?:number, value?:number|boolean}} expected
 *        la peticion que se hizo
 * @returns {{ok:boolean, data:(number[]|{address:number,value:number}|null), error:(string|null),
 *            errorType:string, exceptionCode:(number|null)}}
 *   data: FC 01/02 -> array de 0/1 (largo = quantity) · FC 03/04 -> array de UInt16 ·
 *         FC 05/06 -> {address, value} del eco
 */
function parseResponse(buffer, expected) {
    const fail = (errorType, error, exceptionCode = null) =>
        ({ ok: false, data: null, error, errorType, exceptionCode });

    if (!buffer || buffer.length === 0) return fail(ERROR_TYPE.TIMEOUT, 'sin respuesta');
    if (buffer.length < 4) return fail(ERROR_TYPE.MALFORMED, `trama de ${buffer.length} bytes`);
    if (!checkCrc(buffer)) return fail(ERROR_TYPE.CRC_ERROR, 'CRC invalido');
    if (buffer[0] !== expected.slaveId) {
        return fail(ERROR_TYPE.WRONG_SLAVE, `respondio el Unit ID ${buffer[0]}, se esperaba ${expected.slaveId}`);
    }
    const fc = buffer[1];
    if (fc === (expected.fc | 0x80)) {
        if (buffer.length !== EXCEPTION_LENGTH) return fail(ERROR_TYPE.MALFORMED, 'excepcion de largo invalido');
        const code = buffer[2];
        return fail(ERROR_TYPE.EXCEPTION, `excepcion ${code} ${EXCEPTION_NAMES[code] || ''}`.trim(), code);
    }
    if (fc !== expected.fc) return fail(ERROR_TYPE.MALFORMED, `FC ${fc} en respuesta a FC ${expected.fc}`);
    const quantity = expected.quantity || 1;
    if (buffer.length !== expectedLength({ fc, quantity })) {
        return fail(ERROR_TYPE.MALFORMED, `largo ${buffer.length}, se esperaban ${expectedLength({ fc, quantity })}`);
    }

    if (fc === FC.READ_COILS || fc === FC.READ_DISCRETE_INPUTS) {
        if (buffer[2] !== Math.ceil(quantity / 8)) return fail(ERROR_TYPE.MALFORMED, 'conteo de bytes incoherente');
        // El primer bit pedido esta en el LSB del primer byte (V1.1b3 §6.1).
        const bits = [];
        for (let i = 0; i < quantity; i++) bits.push((buffer[3 + (i >> 3)] >> (i & 7)) & 1);
        return { ok: true, data: bits, error: null, errorType: ERROR_TYPE.NONE, exceptionCode: null };
    }
    if (fc === FC.READ_HOLDING_REGISTERS || fc === FC.READ_INPUT_REGISTERS) {
        if (buffer[2] !== 2 * quantity) return fail(ERROR_TYPE.MALFORMED, 'conteo de bytes incoherente');
        const regs = [];
        for (let i = 0; i < quantity; i++) regs.push(u16(buffer, 3 + 2 * i));
        return { ok: true, data: regs, error: null, errorType: ERROR_TYPE.NONE, exceptionCode: null };
    }
    // FC 05 / 06: la respuesta normal es el eco exacto de la peticion.
    const echoAddress = u16(buffer, 2);
    const echoValue = u16(buffer, 4);
    const sentValue = fc === FC.WRITE_SINGLE_COIL ? (expected.value ? 0xFF00 : 0x0000) : expected.value;
    if (echoAddress !== expected.address || echoValue !== sentValue) {
        return fail(ERROR_TYPE.MALFORMED, 'el eco no coincide con la peticion');
    }
    return { ok: true, data: { address: echoAddress, value: echoValue }, error: null,
        errorType: ERROR_TYPE.NONE, exceptionCode: null };
}

// =============================================================================
// [DF-2.6] Tiempos del enlace
// =============================================================================

/**
 * Duracion de un caracter en ms (11 bits por caracter, como manda la norma).
 * @param {number} baud
 * @returns {number}
 */
function charMs(baud) {
    if (!(baud > 0)) throw new RangeError(`baud invalido: ${baud}`);
    return (BITS_PER_CHAR * 1000) / baud;
}

/**
 * t3,5 en ms: silencio minimo entre tramas.
 * Regla: t3,5 = 3,5 x 11 bits / baud; por encima de 19200 bps, 1,75 ms fijos
 * (MODBus over Serial Line V1.02 §2.5.1.1).
 * 9600 bps -> 4,0104 ms · 19200 -> 2,0052 ms · 38400 y 115200 -> 1,75 ms
 * @param {number} baud
 * @returns {number}
 */
function t35ms(baud) {
    return baud > 19200 ? 1.75 : 3.5 * charMs(baud);
}

/**
 * t1,5 en ms: hueco maximo dentro de una trama (0,75 ms fijos por encima de 19200 bps).
 * @param {number} baud
 * @returns {number}
 */
function t15ms(baud) {
    return baud > 19200 ? 0.75 : 1.5 * charMs(baud);
}

/**
 * Tiempo de transmision de n bytes en ms (sirve para estimar latencias).
 * @param {number} bytes
 * @param {number} baud
 * @returns {number}
 */
function txMs(bytes, baud) {
    return bytes * charMs(baud);
}

// =============================================================================
// Utilidades
// =============================================================================

/**
 * Formatea bytes en hexadecimal: '01 04 00 00 00 01 31 CA'.
 * @param {Buffer|Uint8Array|null} buffer
 * @returns {string}
 */
function toHex(buffer) {
    if (!buffer) return '';
    return Array.from(buffer, (b) => b.toString(16).toUpperCase().padStart(2, '0')).join(' ');
}

/**
 * Convierte '01 04 00 00' (con o sin espacios) en Buffer.
 * @param {string} text
 * @returns {Buffer}
 * @throws {RangeError} si no es hexadecimal de longitud par
 */
function fromHex(text) {
    const clean = String(text).replace(/[\s:,-]/g, '');
    if (!/^([0-9a-fA-F]{2})*$/.test(clean)) throw new RangeError('hexadecimal invalido');
    return Buffer.from(clean, 'hex');
}

module.exports = {
    FC, ERROR_TYPE, EXCEPTION_NAMES, MAX_READ_BITS, MAX_READ_REGISTERS, EXCEPTION_LENGTH,
    crc16, crc16Bitwise, appendCrc, checkCrc,
    buildRequest, expectedLength, responseLengthSoFar, parseResponse,
    charMs, t35ms, t15ms, txMs, toHex, fromHex,
};
