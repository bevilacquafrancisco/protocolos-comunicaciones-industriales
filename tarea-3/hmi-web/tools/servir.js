/**
 * servir.js
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
 *
 * Servidor estatico minimo para la Host Application. Hace falta un servidor (no file://) porque
 * la pagina descarga proto/sparkplug_b.proto con fetch().
 *
 * Por que no "python -m http.server": este sirve SOLO la lista blanca de abajo. El otro expone la
 * carpeta entera (node_modules, package.json, tools/) y lista directorios. Agrega ademas
 * cabeceras de seguridad (nosniff, sin referrer, sin cache, sin framing).
 *
 * Uso (en tarea-3/hmi-web):
 *   node tools/servir.js                  http://127.0.0.1:8080  (solo esta PC)
 *   node tools/servir.js --lan            http://<IP de la PC>:8080  (para abrirla en el celular)
 *   node tools/servir.js --puerto 9000
 *
 * Dependencias externas: ninguna (Node >= 18).
 */
'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const RAIZ = path.join(__dirname, '..');
const PERMITIDOS = new Map([
    ['/', 'index.html'], ['/index.html', 'index.html'], ['/styles.css', 'styles.css'], ['/app.js', 'app.js'],
    ['/sparkplug.js', 'sparkplug.js'], ['/config.js', 'config.js'], ['/vendor/mqtt.min.js', 'vendor/mqtt.min.js'],
    ['/vendor/protobuf.min.js', 'vendor/protobuf.min.js'], ['/proto/sparkplug_b.proto', 'proto/sparkplug_b.proto'],
]);
const TIPOS = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.proto': 'text/plain; charset=utf-8' };

/**
 * Crea el servidor (exportado para las pruebas).
 * @param {string} [raiz] carpeta de la pagina
 * @param {{config?: string}} [opciones] config: contenido de config.js en memoria (pruebas: asi
 *        no se escribe un config.js con claves en la carpeta del repositorio)
 * @returns {http.Server}
 */
function crearServidor(raiz = RAIZ, opciones = {}) {
    return http.createServer((req, res) => {
        const ruta = new URL(req.url, 'http://x').pathname;
        const archivo = PERMITIDOS.get(ruta);
        const cabeceras = { 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY' };
        if (req.method !== 'GET' || !archivo) {
            res.writeHead(404, cabeceras).end('no encontrado');
            return;
        }
        if (archivo === 'config.js' && opciones.config !== undefined) {
            res.writeHead(200, Object.assign({ 'Content-Type': TIPOS['.js'] }, cabeceras)).end(opciones.config);
            return;
        }
        fs.readFile(path.join(raiz, archivo), (err, datos) => {
            if (err) {
                res.writeHead(404, cabeceras).end(archivo === 'config.js' ? 'falta config.js (ver README)' : 'no encontrado');
                return;
            }
            res.writeHead(200, Object.assign({ 'Content-Type': TIPOS[path.extname(archivo)] }, cabeceras)).end(datos);
        });
    });
}

if (require.main === module) {
    const args = process.argv.slice(2);
    const puerto = Number(args[args.indexOf('--puerto') + 1]) || 8080;
    const interfaz = args.includes('--lan') ? '0.0.0.0' : '127.0.0.1';
    crearServidor().listen(puerto, interfaz, () => {
        console.log(`Host Application en http://${interfaz === '0.0.0.0' ? '<IP de esta PC>' : '127.0.0.1'}:${puerto}/`);
    });
}

module.exports = { crearServidor, PERMITIDOS };
