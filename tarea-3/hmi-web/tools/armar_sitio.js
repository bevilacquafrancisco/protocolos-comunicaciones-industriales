/**
 * armar_sitio.js
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-16 · v1.0 (ADR-029)
 *
 * Arma la Host Application como sitio estatico para publicarla en GitHub Pages: un enlace
 * fijo para profesores en PC o celular, que no depende de la IP de la notebook.
 *
 * Copia SOLO la lista blanca de tools/servir.js (lo mismo que se sirve en la LAN) y genera
 * config.js a partir de variables de entorno. En GitHub Actions esas variables salen de la
 * configuracion del repositorio (Settings > Secrets and variables > Actions > Variables):
 * la direccion del broker no queda escrita en ningun archivo versionado.
 *
 * [SEC] El sitio NUNCA lleva claves (ADR-028): la pagina las pide al entrar. El script
 * falla si la URL no es wss:// o si aparece una variable de clave.
 *
 * Uso:
 *   HMI_BROKER_URL=wss://<broker>:8084/mqtt node tools/armar_sitio.js <carpeta de salida>
 *   Opcionales: HMI_USUARIO_SUGERIDO (no es secreto), HMI_GRUPO, HMI_NODO, HMI_DISPOSITIVO, HMI_HOST_ID
 *
 * Dependencias externas: ninguna (Node >= 18).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { PERMITIDOS } = require('./servir');

const RAIZ = path.join(__dirname, '..');

/**
 * Arma el sitio.
 * @param {string} salida carpeta destino (se vacia)
 * @param {object} entorno variables (process.env en la linea de comandos)
 * @returns {string[]} archivos escritos, relativos a la salida
 * @throws {Error} URL ausente o sin TLS, o una variable de clave presente
 */
function armarSitio(salida, entorno) {
    const url = String(entorno.HMI_BROKER_URL || '').trim();
    let u;
    try { u = new URL(url); } catch (e) { throw new Error('HMI_BROKER_URL ausente o inválida (wss://<broker>:8084/mqtt)'); }
    if (u.protocol !== 'wss:') throw new Error('HMI_BROKER_URL debe ser wss:// (TLS): la página publicada va por internet');
    for (const k of Object.keys(entorno)) {
        if (/^HMI_.*(CLAVE|PASS|SECRET)/i.test(k)) throw new Error(`${k}: el sitio no lleva claves (ADR-028); la página las pide al entrar`);
    }
    const config = {
        url,
        usuario: entorno.HMI_USUARIO_SUGERIDO || '',
        grupo: entorno.HMI_GRUPO || 'UNRaf_PdCI_2026',
        nodo: entorno.HMI_NODO || 'EN01_Gateway',
        dispositivo: entorno.HMI_DISPOSITIVO || 'DEV01_ESP32_Slave',
        hostId: entorno.HMI_HOST_ID || 'HA01_WebDashboard',
    };
    fs.rmSync(salida, { recursive: true, force: true });
    fs.mkdirSync(salida, { recursive: true });
    const escritos = [];
    for (const archivo of new Set(PERMITIDOS.values())) {
        const destino = path.join(salida, archivo);
        fs.mkdirSync(path.dirname(destino), { recursive: true });
        if (archivo === 'config.js') {
            fs.writeFileSync(destino, `// Generado por tools/armar_sitio.js (ADR-029). SIN claves: la página las pide al entrar.\n`
                + `window.PDCI_CONFIG = Object.freeze(${JSON.stringify(config, null, 4)});\n`);
        } else {
            fs.copyFileSync(path.join(RAIZ, archivo), destino);
        }
        escritos.push(archivo);
    }
    fs.writeFileSync(path.join(salida, '.nojekyll'), '');        // GitHub Pages: servir tal cual
    return escritos.sort();
}

if (require.main === module) {
    const salida = process.argv[2];
    if (!salida) {
        console.error('uso: node tools/armar_sitio.js <carpeta de salida>');
        process.exit(2);
    }
    try {
        const archivos = armarSitio(path.resolve(salida), process.env);
        console.log(`Sitio armado en ${salida}: ${archivos.join(', ')}`);
    } catch (e) {
        console.error(`✖ ${e.message}`);
        process.exit(1);
    }
}

module.exports = { armarSitio };
