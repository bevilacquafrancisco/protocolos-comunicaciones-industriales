/**
 * sparkplug.test.js — nucleo de la Host Application (sin navegador ni broker).
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
 * Uso: node --test test/   (en tarea-3/hmi-web)
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const protobuf = require('protobufjs');
const S = require('../sparkplug');

const RAIZ = path.join(__dirname, '..');
const PROTO = fs.readFileSync(path.join(RAIZ, 'proto', 'sparkplug_b.proto'), 'utf8');
const codec = S.crearCodec(protobuf, PROTO);
const IDS = { grupo: 'UNRaf_PdCI_2026', nodo: 'EN01_Gateway', dispositivo: 'DEV01_ESP32_Slave', hostId: 'HA01_WebDashboard' };
const T = (tipo) => (tipo.startsWith('D') ? `spBv1.0/${IDS.grupo}/${tipo}/${IDS.nodo}/${IDS.dispositivo}` : `spBv1.0/${IDS.grupo}/${tipo}/${IDS.nodo}`);

// Metricas como las publica el Edge Node real (alias del diccionario).
const NODO = [
    { nombre: 'bdSeq', tipo: 'Int64', valor: 3 }, { nombre: 'Node Control/Rebirth', tipo: 'Boolean', valor: false },
    { nombre: 'Status/MODBUS/Estado', alias: 10, tipo: 'String', valor: 'DONE' },
    { nombre: 'Status/MODBUS/OK', alias: 11, tipo: 'UInt32', valor: 10 },
    { nombre: 'Status/OPCUA/Estado', alias: 20, tipo: 'String', valor: 'DONE' },
];
const DISP = [
    { nombre: 'Inputs/Pulsador', alias: 101, tipo: 'Boolean', valor: false },
    { nombre: 'Inputs/Potenciometro', alias: 102, tipo: 'UInt16', valor: 2048 },
    { nombre: 'Outputs/LedDigital', alias: 103, tipo: 'Boolean', valor: false },
    { nombre: 'Outputs/LedPWM', alias: 104, tipo: 'UInt16', valor: 0 },
    { nombre: 'Inputs/Potenciometro_pct', alias: 105, tipo: 'Float', valor: 50 },
];

function nuevoHost(extra = {}) {
    let reloj = 1_000_000;
    const host = new S.HostSparkplug(Object.assign({ codec, ...IDS, ahora: () => reloj }, extra));
    host.avanzar = (ms) => { reloj += ms; };
    return host;
}
const msg = (host, tipo, seq, metricas) => host.procesar(T(tipo), codec.codificar({ timestamp: 1, seq, metricas }));
function enLinea(host) {
    msg(host, 'NBIRTH', 0, NODO);
    msg(host, 'DBIRTH', 1, DISP);
    return host;
}
const ncmdRebirth = (r) => r.publicar.filter((p) => p.topico === T('NCMD'));

test('codec: ida y vuelta por tipo (UInt32 en intValue, Int64, Float, String, nulo)', () => {
    const bytes = codec.codificar({ timestamp: 1794524426114, seq: 255, metricas: [
        { alias: 11, tipo: 'UInt32', valor: 4294967295 }, { nombre: 'bdSeq', tipo: 'Int64', valor: 255 },
        { alias: 105, tipo: 'Float', valor: 59.7 }, { alias: 10, tipo: 'String', valor: 'DEVICE NOT REACHED' },
        { alias: 101, tipo: 'Boolean', valor: true }] });
    const p = codec.decodificar(bytes);
    assert.equal(p.timestamp, 1794524426114);
    assert.equal(p.seq, 255);
    const v = p.metricas.map((m) => codec.valor(m.crudo, m.tipo));
    assert.equal(v[0], 4294967295);
    assert.ok(p.metricas[0].crudo.intValue !== undefined, 'UInt32 viaja en intValue');
    assert.equal(v[1], 255);
    assert.ok(Math.abs(v[2] - 59.7) < 1e-4);
    assert.deepEqual(v.slice(3), ['DEVICE NOT REACHED', true]);
    assert.throws(() => codec.codificar({ timestamp: 1, metricas: [{ alias: 104, tipo: 'UInt16', valor: 65536 }] }), RangeError);
    assert.throws(() => codec.codificar({ timestamp: 1, metricas: [{ alias: 103, tipo: 'Boolean', valor: 1 }] }), TypeError);
});

test('interoperabilidad: lo que codifica el Edge Node en Python lo decodifica la web, y al reves', (t) => {
    const python = path.join(RAIZ, '..', 'gateway-sparkplug', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    if (!fs.existsSync(python)) return t.skip('falta el venv de gateway-sparkplug');
    const src = path.join(RAIZ, '..', 'gateway-sparkplug', 'src').replace(/\\/g, '/');
    const hexPy = execFileSync(python, ['-c', `import sys; sys.path.insert(0, '${src}'); import sparkplug as s
print(s.armar_payload([s.ValorMetrica('bdSeq', None, 'Int64', 7), s.ValorMetrica(None, 104, 'UInt16', 200),
  s.ValorMetrica(None, 11, 'UInt32', 4294967295)], seq=42, timestamp=1794524426114).hex())`]).toString().trim();
    const p = codec.decodificar(Buffer.from(hexPy, 'hex'));
    assert.equal(p.seq, 42);
    assert.deepEqual(p.metricas.map((m) => codec.valor(m.crudo, m.tipo)), [7, 200, 4294967295]);
    // DCMD de la web -> lo decodifica y VALIDA el nucleo del Edge Node (alias 103 = Outputs/LedDigital)
    const hexJs = Buffer.from(codec.codificar({ timestamp: 5, metricas: [{ alias: 103, tipo: 'Boolean', valor: true }] })).toString('hex');
    const salida = execFileSync(python, ['-c', `import sys; sys.path.insert(0, '${src}'); import sparkplug as s
p = s.decodificar(bytes.fromhex('${hexJs}')); m = p.metrics[0]
print(p.HasField('seq'), m.alias, s.leer_valor(m), p.timestamp)`]).toString().trim();
    assert.equal(salida, 'False 103 True 5');
});

test('proto identico al del dispositivo 3 (y este al oficial de Eclipse Tahu)', () => {
    const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f, 'utf8').replace(/\r\n/g, '\n')).digest('hex');
    assert.equal(sha(path.join(RAIZ, 'proto', 'sparkplug_b.proto')), '4432c5c483b7fb9732d0594c98a2e97dca5e517e39c5374a8b918d837f0b4a19');
});

test('sin BIRTH, ninguna metrica es valida (DESCONOCIDO) y se pide Rebirth', () => {
    const host = nuevoHost();
    assert.equal(host.metrica('Inputs/Potenciometro').vigencia, S.VIGENCIA.DESCONOCIDO);
    const r = msg(host, 'DDATA', 5, [{ alias: 102, tipo: 'UInt16', valor: 999 }]);
    assert.equal(host.metrica('Inputs/Potenciometro').valor, null, 'un DATA sin BIRTH no se aplica');
    assert.equal(ncmdRebirth(r).length, 1);
    const ncmd = codec.decodificar(ncmdRebirth(r)[0].bytes);
    assert.equal(ncmd.seq, null, 'NCMD sin seq');
    assert.equal(ncmd.metricas[0].nombre, 'Node Control/Rebirth');
    assert.equal(codec.valor(ncmd.metricas[0].crudo, 'Boolean'), true);
    assert.equal(host.rebirthsSolicitados, 1);
});

test('NBIRTH + DBIRTH: todo EN LINEA; DDATA por alias actualiza valor y timestamp', () => {
    const host = enLinea(nuevoHost());
    assert.equal(host.nodo.bdSeq, 3);
    assert.equal(host.metrica('Inputs/Potenciometro').vigencia, S.VIGENCIA.EN_LINEA);
    const r = host.procesar(T('DDATA'), codec.codificar({ timestamp: 9, seq: 2, metricas: [{ alias: 102, tipo: 'UInt16', valor: 4095 }] }));
    assert.equal(r.publicar.length, 0);
    assert.deepEqual(host.metrica('Inputs/Potenciometro'), { valor: 4095, ts: 9, vigencia: S.VIGENCIA.EN_LINEA });
});

test('salto de seq: Rebirth una sola vez dentro de la espera, contador y aviso', () => {
    const host = enLinea(nuevoHost());
    const r1 = msg(host, 'DDATA', 5, [{ alias: 101, tipo: 'Boolean', valor: true }]);    // esperado 2
    assert.equal(ncmdRebirth(r1).length, 1);
    assert.match(r1.eventos.map((e) => e.texto).join(), /esperado 2, llegó 5/);
    const r2 = msg(host, 'DDATA', 9, [{ alias: 101, tipo: 'Boolean', valor: false }]);   // otro salto, 0 ms despues
    assert.equal(ncmdRebirth(r2).length, 0, 'no se repite el Rebirth antes de 5 s');
    host.avanzar(6000);
    assert.equal(ncmdRebirth(msg(host, 'NDATA', 20, [{ alias: 11, tipo: 'UInt32', valor: 50 }])).length, 1);
    assert.equal(host.rebirthsSolicitados, 2);
});

test('seq envuelve de 255 a 0 sin falso salto', () => {
    const host = enLinea(nuevoHost());
    for (let s = 2; s <= 255; s++) assert.equal(ncmdRebirth(msg(host, 'NDATA', s, [{ alias: 11, tipo: 'UInt32', valor: s }])).length, 0);
    assert.equal(ncmdRebirth(msg(host, 'NDATA', 0, [{ alias: 11, tipo: 'UInt32', valor: 1000 }])).length, 0);
    assert.equal(host.rebirthsSolicitados, 0);
});

test('DDEATH: metricas del dispositivo OBSOLETAS (las del nodo siguen EN LINEA); DBIRTH las revive', () => {
    const host = enLinea(nuevoHost());
    msg(host, 'DDEATH', 2, []);
    assert.equal(host.metrica('Outputs/LedPWM').vigencia, S.VIGENCIA.OBSOLETO);
    assert.equal(host.metrica('Outputs/LedPWM').valor, 0, 'conserva el ultimo valor, marcado obsoleto');
    assert.equal(host.metrica('Status/MODBUS/Estado').vigencia, S.VIGENCIA.EN_LINEA, 'el diagnostico sigue vivo (ADR-006)');
    assert.equal(ncmdRebirth(msg(host, 'DDATA', 3, [{ alias: 101, tipo: 'Boolean', valor: true }])).length, 1, 'DDATA sin DBIRTH');
    msg(host, 'DBIRTH', 4, DISP);
    assert.equal(host.metrica('Outputs/LedPWM').vigencia, S.VIGENCIA.EN_LINEA);
});

test('NDEATH solo cuenta si su bdSeq es el del NBIRTH vigente', () => {
    const host = enLinea(nuevoHost());
    const viejo = host.procesar(T('NDEATH'), codec.codificar({ timestamp: 1, metricas: [{ nombre: 'bdSeq', tipo: 'Int64', valor: 2 }] }));
    assert.match(viejo.eventos[0].texto, /otra sesión/);
    assert.equal(host.nodo.estado, S.VIGENCIA.EN_LINEA);
    host.procesar(T('NDEATH'), codec.codificar({ timestamp: 1, metricas: [{ nombre: 'bdSeq', tipo: 'Int64', valor: 3 }] }));
    assert.equal(host.nodo.estado, S.VIGENCIA.OBSOLETO);
    assert.equal(host.metrica('Status/MODBUS/OK').vigencia, S.VIGENCIA.OBSOLETO);
    assert.equal(host.metrica('Inputs/Pulsador').vigencia, S.VIGENCIA.OBSOLETO);
});

test('comando: ENVIADO -> CONFIRMADO solo con el DDATA; SIN CONFIRMAR si no vuelve', () => {
    const host = enLinea(nuevoHost());
    const r = host.comandar('Outputs/LedDigital', true);
    const dcmd = codec.decodificar(r.publicar[0].bytes);
    assert.equal(r.publicar[0].topico, T('DCMD'));
    assert.equal(dcmd.seq, null);
    assert.equal(dcmd.metricas[0].nombre, null, 'solo alias (payloads-alias-data-cmd-requirement)');
    assert.equal(dcmd.metricas[0].alias, 103);
    assert.equal(host.comandos.get('Outputs/LedDigital').estado, 'enviado');
    assert.equal(host.metrica('Outputs/LedDigital').valor, false, 'el valor mostrado NO cambia al enviar');
    msg(host, 'DDATA', 2, [{ alias: 103, tipo: 'Boolean', valor: true }]);
    assert.equal(host.comandos.get('Outputs/LedDigital').estado, 'confirmado');

    host.comandar('Outputs/LedPWM', 128);
    host.avanzar(5001);
    assert.match(host.tick().eventos[0].texto, /SIN CONFIRMAR/);
    assert.equal(host.comandos.get('Outputs/LedPWM').estado, 'sin confirmar');
});

test('comando rechazado sin dispositivo EN LINEA o sin cambio de valor', () => {
    const host = nuevoHost();
    assert.equal(host.comandar('Outputs/LedDigital', true).publicar.length, 0);
    enLinea(host);
    assert.equal(host.comandar('Outputs/LedDigital', false).publicar.length, 0, 'ya vale false');
    msg(host, 'DDEATH', 2, []);
    assert.equal(host.comandar('Outputs/LedPWM', 10).publicar.length, 0);
});

test('perder el broker deja todo OBSOLETO y al volver se pide un BIRTH', () => {
    const host = enLinea(nuevoHost());
    host.comandar('Outputs/LedPWM', 9);
    const r = host.alDesconectar();
    assert.equal(host.metrica('Inputs/Pulsador').vigencia, S.VIGENCIA.OBSOLETO);
    assert.match(r.eventos[0].texto, /SIN CONFIRMAR/);
    host.avanzar(6000);
    assert.equal(ncmdRebirth(host.alConectar()).length, 1);
});

test('mensajes de otro nodo, topicos ajenos y payload roto no rompen nada', () => {
    const host = enLinea(nuevoHost());
    assert.equal(host.procesar('spBv1.0/UNRaf_PdCI_2026/NDATA/OTRO', codec.codificar({ timestamp: 1, seq: 9, metricas: [] })).publicar.length, 0);
    assert.equal(host.procesar('otra/cosa', new Uint8Array([1])).tipo, null);
    assert.equal(host.procesar(T('DDATA'), new Uint8Array([0xff, 0xff, 0xff])).eventos[0].nivel, 'error');
    const st = host.procesar('spBv1.0/STATE/HA01_WebDashboard', new TextEncoder().encode(S.payloadState(true, 5)), true);
    assert.deepEqual(st.state, { online: true, timestamp: 5 });
});
