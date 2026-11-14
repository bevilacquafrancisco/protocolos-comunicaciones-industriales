/**
 * copiar_vendor.js
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
 *
 * Copia a vendor/ los builds de navegador de mqtt.js y protobuf.js (versiones exactas de
 * package.json) y a proto/ el sparkplug_b.proto del dispositivo 3, y anota la SHA-256 de cada uno
 * en vendor/VERSIONES.txt.
 *
 * Por que se sirven desde el repositorio y no desde un CDN: (1) la red del aula puede bloquear
 * CDNs (riesgo R-06) y la demo no puede depender de eso; (2) el codigo que corre en la pagina es
 * exactamente el revisado y fijado, sin un tercero que lo pueda cambiar (cadena de suministro).
 * test/vendor.test.js falla si vendor/ no coincide con node_modules/.
 *
 * Uso: npm run vendor   (despues de npm ci)
 * Dependencias externas: ninguna (Node >= 18).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const RAIZ = path.join(__dirname, '..');
const ARCHIVOS = [
    { origen: 'node_modules/mqtt/dist/mqtt.min.js', destino: 'vendor/mqtt.min.js', paquete: 'mqtt' },
    { origen: 'node_modules/protobufjs/dist/protobuf.min.js', destino: 'vendor/protobuf.min.js', paquete: 'protobufjs' },
    { origen: '../gateway-sparkplug/proto/sparkplug_b.proto', destino: 'proto/sparkplug_b.proto', paquete: null },
];

const sha256 = (ruta) => crypto.createHash('sha256').update(fs.readFileSync(ruta)).digest('hex');

function main() {
    const lineas = ['# Archivos de terceros servidos por la pagina (generado por tools/copiar_vendor.js)', ''];
    for (const a of ARCHIVOS) {
        const origen = path.join(RAIZ, a.origen);
        const destino = path.join(RAIZ, a.destino);
        fs.mkdirSync(path.dirname(destino), { recursive: true });
        fs.copyFileSync(origen, destino);
        const version = a.paquete ? require(path.join(RAIZ, 'node_modules', a.paquete, 'package.json')).version : '-';
        lineas.push(`${a.destino}  ${a.paquete || 'sparkplug_b.proto (Eclipse Tahu)'}@${version}  sha256=${sha256(destino)}`);
        console.log(`${a.destino} <- ${a.origen}`);
    }
    fs.writeFileSync(path.join(RAIZ, 'vendor', 'VERSIONES.txt'), lineas.join('\n') + '\n', 'utf8');
}

if (require.main === module) main();
module.exports = { ARCHIVOS, sha256 };
