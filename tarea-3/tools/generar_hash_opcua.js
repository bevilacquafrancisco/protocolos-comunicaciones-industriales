/**
 * generar_hash_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-10
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Pide la contrasena del usuario OPC UA (sin eco) e imprime su hash scrypt para la variable
 * de entorno PDCI_T3_OPCUA_HASH. La contrasena nunca se pasa como argumento: no queda en el
 * historial de la shell ni en la lista de procesos.
 *
 * Uso
 *   node tools/generar_hash_opcua.js          (en tarea-3/)
 *
 * Dependencias externas: ninguna (usa edge-nodered/lib/credenciales.js).
 */
'use strict';

const path = require('node:path');
const readline = require('node:readline');
const { hashearClave, verificarClave } = require(path.join(__dirname, '..', 'edge-nodered', 'lib', 'credenciales'));

/**
 * Lee una linea de la terminal sin mostrarla.
 * @param {string} pregunta
 * @returns {Promise<string>}
 */
function leerOculto(pregunta) {
    return new Promise((resolver) => {
        const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
        rl._writeToOutput = (s) => { if (s.includes(pregunta)) process.stdout.write(s); };
        rl.question(pregunta, (r) => { rl.close(); process.stdout.write('\n'); resolver(r); });
    });
}

(async () => {
    const clave = await leerOculto('Contrasena OPC UA: ');
    // NIST SP 800-63B §5.1.1.2 exige al menos 8; se piden 12 por ser un acceso de escritura a campo.
    if (clave.length < 12) { console.error('minimo 12 caracteres'); process.exit(1); }
    if (clave !== await leerOculto('Repetir: ')) { console.error('no coinciden'); process.exit(1); }
    const hash = await hashearClave(clave);
    if (!(await verificarClave(clave, hash))) { console.error('autoverificacion fallida'); process.exit(1); }
    console.log(`PDCI_T3_OPCUA_HASH=${hash}`);
})();
