/**
 * tipos.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Conversion entre los registros de 16 bits de MODBus y los tipos del mapa (bool, uint16,
 * int16, uint32, int32, float32). MODBus solo define bits y palabras de 16 bits; los tipos
 * de 32 bits ocupan dos registros, y el ORDEN de esas dos palabras no esta normalizado:
 * cada fabricante elige. Por eso el mapa admite "orden": ABCD (palabra alta primero, el
 * habitual) o CDAB (palabra baja primero, "word swap"). Es una de las cosas a averiguar del
 * esclavo desconocido de la catedra (I-04).
 *
 * Dentro de cada palabra el orden es siempre big-endian (MSB primero), por norma.
 *
 * Dependencias externas: ninguna.
 */
'use strict';

/**
 * Decodifica los datos leidos en el valor de la variable.
 * @param {string} tipo   bool | uint16 | int16 | uint32 | int32 | float32
 * @param {number[]} datos bits (0/1) o registros (0-65535), en el orden en que se leyeron
 * @param {string} [orden='ABCD'] orden de palabras para 32 bits
 * @returns {boolean|number}
 * @throws {RangeError} si faltan datos para el tipo
 */
function decodificar(tipo, datos, orden = 'ABCD') {
    if (tipo === 'bool') return datos[0] === 1;
    if (tipo === 'uint16') return datos[0];
    if (tipo === 'int16') return datos[0] >= 0x8000 ? datos[0] - 0x10000 : datos[0];
    if (datos.length < 2) throw new RangeError(`${tipo} necesita 2 registros`);
    const [alto, bajo] = orden === 'CDAB' ? [datos[1], datos[0]] : [datos[0], datos[1]];
    const b = Buffer.alloc(4);
    b.writeUInt16BE(alto, 0);
    b.writeUInt16BE(bajo, 2);
    if (tipo === 'uint32') return b.readUInt32BE(0);
    if (tipo === 'int32') return b.readInt32BE(0);
    if (tipo === 'float32') return b.readFloatBE(0);
    throw new RangeError(`tipo desconocido: ${tipo}`);
}

/**
 * Convierte un valor a escribir en el argumento de FC 05 (boolean) o FC 06 (0-65535).
 * @param {string} tipo bool | uint16 | int16
 * @param {*} valor
 * @returns {boolean|number}
 * @throws {RangeError} valor no representable en el tipo
 */
function codificar(tipo, valor) {
    if (tipo === 'bool') {
        if (valor === true || valor === 1 || valor === '1' || valor === 'true') return true;
        if (valor === false || valor === 0 || valor === '0' || valor === 'false') return false;
        throw new RangeError(`valor booleano invalido: ${valor}`);
    }
    const n = Number(valor);
    if (!Number.isInteger(n)) throw new RangeError(`valor entero invalido: ${valor}`);
    if (tipo === 'uint16' && n >= 0 && n <= 0xFFFF) return n;
    if (tipo === 'int16' && n >= -0x8000 && n <= 0x7FFF) return n < 0 ? n + 0x10000 : n;
    throw new RangeError(`${valor} no entra en ${tipo}`);
}

/** Cantidad de registros (o bits) que ocupa un tipo. */
const cantidad = (tipo) => (tipo === 'uint32' || tipo === 'int32' || tipo === 'float32' ? 2 : 1);

module.exports = { decodificar, codificar, cantidad };
