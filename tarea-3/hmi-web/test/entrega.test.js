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
