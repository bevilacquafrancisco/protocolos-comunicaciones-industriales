/**
 * credenciales.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Almacenamiento y verificacion de la contrasena del usuario OPC UA del
 * servidor (consigna Parte 4.9).
 *
 * [SEC] El servidor NUNCA guarda la contrasena en claro: guarda un hash scrypt
 * con sal aleatoria, en una variable de entorno fuera del repositorio. Se
 * usan los parametros minimos de OWASP Password Storage Cheat Sheet para
 * scrypt (N = 2^17, r = 8, p = 1), que exigen 128 MiB por verificacion: un
 * atacante que robe el hash no puede probar millones de claves por segundo
 * en una GPU. En la RPi una verificacion tarda del orden de 1 s, aceptable
 * porque ocurre solo en ActivateSession.
 *
 * Por que no se uso el archivo users.json de node-red-contrib-opcua: guarda
 * las contrasenas en texto plano (ver docs/seguridad.md §6).
 *
 * Formato del hash: "scrypt$N$r$p$sal_hex$hash_hex".
 *
 * Dependencias externas: ninguna (modulo crypto de Node.js).
 */
'use strict';

const crypto = require('node:crypto');

const PARAMETROS = Object.freeze({ N: 2 ** 17, r: 8, p: 1, largo: 32, sal: 16 });
// 128 * N * r = 128 MiB; Node rechaza por defecto mas de 32 MiB.
const MEMORIA_MAXIMA = 256 * 1024 * 1024;

/**
 * Descripcion: genera el hash almacenable de una contrasena.
 * Parametros: clave (string): contrasena en claro, minimo 12 caracteres.
 * Retorna: (Promise<string>) "scrypt$N$r$p$sal$hash".
 * Excepciones: RangeError si la clave es demasiado corta.
 */
function hashearClave(clave) {
    if (typeof clave !== 'string' || clave.length < 12) {
        return Promise.reject(new RangeError('la clave debe tener al menos 12 caracteres'));
    }
    const sal = crypto.randomBytes(PARAMETROS.sal);
    const { N, r, p, largo } = PARAMETROS;
    return new Promise((resolver, rechazar) => {
        crypto.scrypt(clave, sal, largo, { N, r, p, maxmem: MEMORIA_MAXIMA }, (error, derivada) => {
            if (error) return rechazar(error);
            resolver(['scrypt', N, r, p, sal.toString('hex'), derivada.toString('hex')].join('$'));
        });
    });
}

/**
 * Descripcion: verifica una contrasena contra un hash generado por
 *   hashearClave(). La comparacion es de tiempo constante.
 * Parametros:
 *   clave (string): contrasena recibida en el UserNameIdentityToken.
 *   almacenado (string): hash "scrypt$...".
 * Retorna: (Promise<boolean>) true si coincide. Un hash mal formado devuelve
 *   false (nunca autoriza por error).
 * Excepciones: ninguna; los errores se traducen a false.
 */
function verificarClave(clave, almacenado) {
    const partes = typeof almacenado === 'string' ? almacenado.split('$') : [];
    if (partes.length !== 6 || partes[0] !== 'scrypt' || typeof clave !== 'string') {
        return Promise.resolve(false);
    }
    const [, N, r, p, salHex, hashHex] = partes;
    const esperado = Buffer.from(hashHex, 'hex');
    if (esperado.length === 0) return Promise.resolve(false);
    return new Promise((resolver) => {
        crypto.scrypt(clave, Buffer.from(salHex, 'hex'), esperado.length,
            { N: Number(N), r: Number(r), p: Number(p), maxmem: MEMORIA_MAXIMA },
            (error, derivada) => {
                // [SEC] timingSafeEqual: el tiempo de respuesta no revela cuantos
                // bytes del hash coincidieron.
                resolver(!error && crypto.timingSafeEqual(derivada, esperado));
            });
    });
}

module.exports = Object.freeze({ PARAMETROS, hashearClave, verificarClave });

// ---------------------------------------------------------------------------
// Uso desde la linea de comandos, para generar el hash en la RPi 1:
//     node credenciales.js
// La clave se pide por la entrada estandar para que no quede en el historial
// de la shell.
// ---------------------------------------------------------------------------
if (require.main === module) {
    const lector = require('node:readline').createInterface({ input: process.stdin, output: process.stderr });
    lector.question('Clave del usuario OPC UA (minimo 12 caracteres): ', (clave) => {
        lector.close();
        hashearClave(clave.trim())
            .then((hash) => { console.log(hash); })
            .catch((error) => { console.error('Error: ' + error.message); process.exitCode = 1; });
    });
}
