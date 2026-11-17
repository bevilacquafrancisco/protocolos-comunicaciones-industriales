/**
 * tramas.test.js — decodificacion didactica (tramas.js), modelo estatico (modelo.js) contra la
 * fuente de verdad, y marcas de tiempo de los comandos (sparkplug.js). Sin navegador ni broker.
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-16 · v1.0
 * Uso: node --test test/   (en tarea-3/hmi-web)
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const protobuf = require('protobufjs');
const Tr = require('../tramas');
const M = require('../modelo');
const S = require('../sparkplug');

const RAIZ = path.join(__dirname, '..');
const DOCS = path.join(RAIZ, '..', 'docs');
const codec = S.crearCodec(protobuf, fs.readFileSync(path.join(RAIZ, 'proto', 'sparkplug_b.proto'), 'utf8'));
const B = Tr.hexABytes;

// ---------------------------------------------------------------------------- CRC-16
test('CRC-16: tramas reales del sistema (banco, diccionario y verificacion OPC UA)', () => {
    // Fuentes: banco 2026-11-16 (01 03 ... 84 0A / B8 44), diccionario §2 (31 CA), opcua-espacio-direcciones.md (B9 E4)
    const casos = [['01 03 00 00 00 01', '84 0A'], ['01 04 00 00 00 01', '31 CA'], ['01 03 02 00 00', 'B8 44'], ['01 03 02 00 80', 'B9 E4']];
    for (const [datos, crc] of casos) {
        assert.equal(Tr.crcPasoAPaso(B(datos)).enLinea, crc, datos);
        assert.equal(Tr.verificarCrc(B(`${datos} ${crc}`)).ok, true);
        assert.equal(Tr.verificarCrc(B(`${datos} ${crc}`)).residuo, '0x0000', 'datos + CRC dan residuo 0');
    }
});

test('CRC paso a paso: arranca en 0xFFFF, 8 desplazamientos por byte, y termina en el CRC', () => {
    const r = Tr.crcPasoAPaso(B('01 03 00 00 00 01'));
    assert.equal(r.pasos.length, 6);
    assert.equal(r.pasos[0].antes, '0xFFFF');
    assert.equal(r.pasos[0].trasXor, '0xFFFE');                       // 0xFFFF XOR 0x01
    assert.ok(r.pasos.every((p) => p.desplazamientos.length === 8));
    assert.equal(r.pasos[5].despues, `0x${Tr.hex4(r.crc)}`);
    assert.equal(r.crc, Tr.crc16(B('01 03 00 00 00 01')));
    assert.equal(Tr.verificarCrc(B('01 03 00 00 00 01 84 0B')).ok, false, 'un bit cambiado se detecta');
});

// ---------------------------------------------------------------------------- MODBus
test('MODBus: peticion y respuesta FC 03 decodificadas campo por campo', () => {
    const pet = Tr.decodificarModbus(B('01 03 00 00 00 01 84 0A'), 'peticion', M.variableModbus);
    assert.deepEqual(pet.filas.map((f) => f.campo), ['Dirección', 'Función', 'Dirección inicial', 'Cantidad', 'CRC-16']);
    assert.match(pet.filas[2].significado, /registro holding 40001 · Outputs\/LedPWM/);
    assert.equal(pet.segmentos.length, 8);
    const resp = Tr.decodificarModbus(B('01 03 02 00 80 B9 E4'), 'respuesta', M.variableModbus);
    assert.match(resp.filas.find((f) => f.campo === 'Datos').significado, /valor = 128/);
    assert.equal(resp.crc.ok, true);
});

test('MODBus: excepcion, eco de FC 05 y trama reconstruida del comando', () => {
    const exc = Tr.hexABytes('01 83 02');
    const c = Tr.crc16(exc);
    const r = Tr.decodificarModbus(exc.concat([c & 0xFF, c >>> 8]), 'respuesta');
    assert.equal(r.excepcion, true);
    assert.match(r.filas[2].significado, /dirección ilegal/);
    const on = Tr.tramaEscritura(5, true);
    assert.equal(Tr.bytesAHex(on), '01 05 00 00 FF 00 8C 3A');             // la misma que genera fake_edge_node.py
    assert.match(Tr.decodificarModbus(on, 'peticion').filas[3].significado, /ENCENDER/);
    assert.deepEqual(Tr.decodificarModbus([], 'respuesta').filas, [], 'TIMEOUT: RX vacia, sin filas');
});

// ---------------------------------------------------------------------------- Protobuf
test('Protobuf: el payload real se segmenta byte por byte con el nombre de cada campo', () => {
    const bytes = codec.codificar({ timestamp: 1794868918000, seq: 42, metricas: [
        { alias: 103, tipo: 'Boolean', valor: true }, { nombre: 'Status/MODBUS/Estado', alias: 10, tipo: 'String', valor: 'DONE' },
        { alias: 105, tipo: 'Float', valor: 52.5 }, { alias: 11, tipo: 'UInt32', valor: 43011 }] });
    const nombres = { 103: 'Outputs/LedDigital' };
    const s = Tr.segmentarPayload(bytes, (a) => nombres[a]);
    assert.equal(s.completo, true);
    assert.equal(s.segmentos.length, bytes.length, 'cada byte tiene su rotulo');
    const campos = s.filas.map((f) => f.campo).join('\n');
    for (const esperado of ['seq = 42', 'alias = 103 → Outputs/LedDigital', 'boolean_value = true', 'name = «Status/MODBUS/Estado»',
        'string_value = «DONE»', 'float_value = 52.5', 'int_value = 43011', 'datatype = 11 (Boolean)']) {
        assert.ok(campos.includes(esperado), `falta "${esperado}" en:\n${campos}`);
    }
    const roto = Tr.segmentarPayload(bytes.slice(0, bytes.length - 3));
    assert.equal(roto.completo, false, 'un payload truncado se marca, no se inventa');
});

// ---------------------------------------------------------------------------- modelo.js = fuente de verdad
test('modelo.js coincide con el diccionario de datos (I-06): nombre, tipo, alias y NodeId', () => {
    const dic = fs.readFileSync(path.join(DOCS, 'diccionario-de-datos.md'), 'utf8');
    // "\|" dentro de una celda (p. ej. `DONE` \| `ERROR`) no separa columnas
    const filas = dic.split('\n').filter((l) => l.startsWith('|'))
        .map((l) => l.replace(/\\\|/g, '¦').split('|').slice(1, -1).map((c) => c.trim()));
    const enDiccionario = new Map();
    for (const c of filas) {
        if (c.length >= 9 && /`(Inputs|Outputs)\//.test(c[6])) enDiccionario.set(c[6].replace(/`/g, ''), { tipo: c[7], alias: c[8], nodo: c[5] });
        if (c.length === 6 && /^`[A-Za-z]/.test(c[0]) && /^`\w+`$/.test(c[1])) enDiccionario.set(c[0].replace(/`/g, ''), { tipo: c[1], alias: c[3], nodo: c[2] });
    }
    assert.deepEqual([...enDiccionario.keys()].sort(), M.METRICAS.map((m) => m.nombre).sort(), 'mismo conjunto de métricas');
    for (const m of M.METRICAS) {
        const d = enDiccionario.get(m.nombre);
        assert.ok(d.tipo.includes(`\`${m.tipo}\``), `${m.nombre}: tipo ${m.tipo} ≠ ${d.tipo}`);
        assert.equal(d.alias.replace(/\D/g, '') || null, m.alias === null ? null : String(m.alias), `${m.nombre}: alias`);
        if (m.nodeId) assert.ok(d.nodo.includes(m.nodeId.replace('ns=1;', '')), `${m.nombre}: NodeId ${m.nodeId}`);
    }
});

test('modelo.js coincide con la verificacion del servidor OPC UA (DataType y AccessLevel)', () => {
    const doc = fs.readFileSync(path.join(DOCS, 'opcua-espacio-direcciones.md'), 'utf8');
    for (const v of M.VARIABLES_OPCUA) {
        const fila = doc.split('\n').find((l) => l.startsWith(`| \`ns=1;s=${v.id}\``));
        assert.ok(fila, `${v.id} no figura en la verificación`);
        const c = fila.split('|').map((x) => x.trim());
        assert.equal(c[3], v.tipo, `${v.id}: DataType`);
        assert.equal(c[4], v.acceso === 'RW' ? 'CurrentRead + CurrentWrite' : 'CurrentRead', `${v.id}: AccessLevel`);
    }
    for (const n of M.ARBOL.filter((x) => x.nodeId && x.nodeId.startsWith('ns=1'))) {
        assert.ok(doc.includes(`\`${n.nodeId}\``), `objeto ${n.nodeId} no verificado`);
    }
});

// ---------------------------------------------------------------------------- marcas de tiempo
test('comando: marcas de tiempo de envio, eco del broker y confirmacion (ADR-028)', () => {
    let reloj = 1_000_000;
    const host = new S.HostSparkplug({ codec, grupo: 'G', nodo: 'N', dispositivo: 'D', hostId: 'H', ahora: () => reloj });
    const T = (tipo) => (tipo.startsWith('D') ? `spBv1.0/G/${tipo}/N/D` : `spBv1.0/G/${tipo}/N`);
    host.procesar(T('NBIRTH'), codec.codificar({ timestamp: 1, seq: 0, metricas: [{ nombre: 'bdSeq', tipo: 'Int64', valor: 1 }] }));
    host.procesar(T('DBIRTH'), codec.codificar({ timestamp: 1, seq: 1, metricas: [{ nombre: 'Outputs/LedDigital', alias: 103, tipo: 'Boolean', valor: false }] }));
    const r = host.comandar('Outputs/LedDigital', true);
    reloj += 40;
    host.procesar(T('DCMD'), r.publicar[0].bytes);                              // el broker devuelve el DCMD
    reloj += 150;
    const conf = host.procesar(T('DDATA'), codec.codificar({ timestamp: 999_900, seq: 2,
        metricas: [{ alias: 103, tipo: 'Boolean', valor: true, timestamp: 999_850 }] }));
    const c = host.comandos.get('Outputs/LedDigital');
    assert.deepEqual(conf.confirmados, ['Outputs/LedDigital']);
    assert.equal(c.tEco - c.t, 40, 'ida y vuelta página ↔ broker');
    assert.equal(c.tConfirmado - c.t, 190, 'total, con un solo reloj');
    assert.equal(c.tsPayload, 999_900);
    assert.ok(c.bytes instanceof Uint8Array && c.alias === 103);
});
