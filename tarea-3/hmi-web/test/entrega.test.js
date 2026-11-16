/**
 * entrega.test.js — lo que se sirve es lo revisado: vendor/ al dia y servidor con lista blanca.
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { ARCHIVOS, sha256 } = require('../tools/copiar_vendor');
const { crearServidor } = require('../tools/servir');

const RAIZ = path.join(__dirname, '..');

test('vendor/ y proto/ identicos a las versiones fijadas (npm run vendor)', () => {
    for (const a of ARCHIVOS) {
        assert.equal(sha256(path.join(RAIZ, a.destino)), sha256(path.join(RAIZ, a.origen)), `${a.destino} desactualizado`);
    }
    const pkg = require('../package.json').devDependencies;
    for (const [nombre, version] of Object.entries(pkg)) assert.match(version, /^\d+\.\d+\.\d+$/, `${nombre} sin version exacta`);
});

test('sitio para GitHub Pages: solo la lista blanca, config.js sin claves, y exige wss:// (ADR-029)', () => {
    const { armarSitio } = require('../tools/armar_sitio');
    const os = require('node:os');
    const salida = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-sitio-'));
    try {
        const archivos = armarSitio(salida, { HMI_BROKER_URL: 'wss://broker.ejemplo:8084/mqtt' });
        const { PERMITIDOS } = require('../tools/servir');
        assert.deepEqual(archivos, [...new Set(PERMITIDOS.values())].sort());
        assert.ok(!fs.existsSync(path.join(salida, 'package.json')) && !fs.existsSync(path.join(salida, 'tools')));
        const config = fs.readFileSync(path.join(salida, 'config.js'), 'utf8');
        assert.match(config, /wss:\/\/broker\.ejemplo:8084\/mqtt/);
        assert.doesNotMatch(config, /"(clave|password|pass)"\s*:/i, 'el sitio no lleva ningún campo de clave');
        assert.throws(() => armarSitio(salida, { HMI_BROKER_URL: 'ws://broker.ejemplo:8083/mqtt' }), /wss/);
        assert.throws(() => armarSitio(salida, {}), /HMI_BROKER_URL/);
        assert.throws(() => armarSitio(salida, { HMI_BROKER_URL: 'wss://b:8084/mqtt', HMI_CLAVE: 'x' }), /no lleva claves/);
    } finally {
        fs.rmSync(salida, { recursive: true, force: true });
    }
});

test('el servidor entrega solo la lista blanca, con cabeceras de seguridad', async () => {
    const s = crearServidor(RAIZ, { config: 'window.PDCI_CONFIG = null;' });
    await new Promise((r) => s.listen(0, '127.0.0.1', r));
    const base = `http://127.0.0.1:${s.address().port}`;
    try {
        const ok = await fetch(`${base}/`);
        assert.equal(ok.status, 200);
        assert.equal(ok.headers.get('x-content-type-options'), 'nosniff');
        assert.equal(ok.headers.get('x-frame-options'), 'DENY');
        for (const ruta of ['/package.json', '/node_modules/mqtt/package.json', '/tools/servir.js', '/test/',
            '/..%2f..%2fCLAUDE.md', '/vendor/']) {
            assert.equal((await fetch(base + ruta)).status, 404, `${ruta} no deberia servirse`);
        }
        assert.equal((await fetch(`${base}/index.html`, { method: 'POST' })).status, 404);
    } finally {
        s.close();
    }
});
