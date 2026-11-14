/**
 * credenciales.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-10
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Contrasenas del usuario OPC UA: el servidor NUNCA guarda la clave, solo un hash scrypt
 * con sal aleatoria (adaptado de tarea-2/versiones/v3-node-red/node-red/comun/credenciales.js).
 *
 * Parametros scrypt: N = 2^17, r = 8, p = 1 (128 MiB por verificacion). Hace caro un ataque
 * de diccionario contra un hash robado; el costo por intento de login (~0,2-0,5 s en una
 * Raspberry Pi 4) es aceptable para un servidor con pocas sesiones.
 *
 * Formatos aceptados (los dos de la Tarea 2, para no regenerar hashes ya creados):
 *   scrypt:131072:8:1:<sal_hex>:<hash_hex>   (T2 v2 en Python, el de .env.example)
 *   scrypt$131072$8$1$<sal_hex>$<hash_hex>   (T2 v3 en Node-RED)
 *
 * Dependencias externas: ninguna (node:crypto).
 */
'use strict';

const crypto = require('node:crypto');

/** Parametros de scrypt. */
const PARAMETROS = Object.freeze({ N: 2 ** 17, r: 8, p: 1, largo: 32, bytesSal: 16 });
const MEMORIA_MAXIMA = 256 * 1024 * 1024;

/**
 * Genera el hash de una clave (lo usa tools/generar_hash_opcua.js).
 * @param {string} clave
 * @returns {Promise<string>} "scrypt:N:r:p:sal:hash"
 */
function hashearClave(clave) {
    const sal = crypto.randomBytes(PARAMETROS.bytesSal);
    const { N, r, p, largo } = PARAMETROS;
    return new Promise((resolver, rechazar) => {
        crypto.scrypt(clave, sal, largo, { N, r, p, maxmem: MEMORIA_MAXIMA }, (error, derivada) => {
            if (error) return rechazar(error);
            resolver(['scrypt', N, r, p, sal.toString('hex'), derivada.toString('hex')].join(':'));
        });
    });
}

/**
 * Verifica una clave contra el hash almacenado, en tiempo constante.
 * @param {string} clave       la que mando el cliente en ActivateSession
 * @param {string} almacenado  hash en cualquiera de los dos formatos
 * @returns {Promise<boolean>} false ante cualquier error de formato (nunca lanza)
 */
function verificarClave(clave, almacenado) {
    const partes = String(almacenado || '').split(/[:$]/);
    if (partes.length !== 6 || partes[0] !== 'scrypt' || typeof clave !== 'string') return Promise.resolve(false);
    const [, N, r, p, salHex, hashHex] = partes;
    const esperado = Buffer.from(hashHex, 'hex');
    if (!esperado.length) return Promise.resolve(false);
    return new Promise((resolver) => {
        crypto.scrypt(clave, Buffer.from(salHex, 'hex'), esperado.length,
            { N: Number(N), r: Number(r), p: Number(p), maxmem: MEMORIA_MAXIMA }, (error, derivada) => {
                // timingSafeEqual: comparar byte a byte con === filtraria por tiempo cuantos
                // bytes coinciden.
                resolver(!error && crypto.timingSafeEqual(derivada, esperado));
            });
    });
}

module.exports = Object.freeze({ PARAMETROS, hashearClave, verificarClave });
