/**
 * prueba_integracion_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Prueba de integracion de servidor_opcua.js y cliente_opcua.js SIN las
 * Raspberry Pi: levanta el servidor real en 127.0.0.1 y conecta el cliente
 * real contra el. Verifica, contra la consigna, todo lo que no depende del
 * hardware: NodeIds, namespace, tipos, niveles de acceso, EURange, StatusCode
 * de escritura en solo lectura, Modo A, Modo B, los tres endpoints de
 * seguridad y la autenticacion por usuario.
 *
 * Lo que NO verifica (va al banco, PARTE-1..4): GPIO, el enlace eth0, la
 * latencia real, la desconexion fisica del cable y las capturas.
 *
 * Uso
 * ---
 *     NODE_PATH=<carpeta node_modules con node-opcua> node --test tarea-2/herramientas/prueba_integracion_opcua.js
 *
 * En la RPi: NODE_PATH=~/.node-red/node_modules
 *
 * Dependencias externas: node-opcua 2.x (probado con 2.160.0), Node.js >= 18.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');

const opcua = require('node-opcua');
const RAIZ = path.join(__dirname, '..', 'node-red');
const configBase = require(path.join(RAIZ, 'comun', 'config.js'));
const { iniciarServidor } = require(path.join(RAIZ, 'servidor', 'servidor_opcua.js'));
const { iniciarCliente } = require(path.join(RAIZ, 'cliente', 'cliente_opcua.js'));
const { hashearClave } = require(path.join(RAIZ, 'comun', 'credenciales.js'));

const PUERTO = 48401; // distinto de 4840 para no chocar con un servidor real
const ENDPOINT = 'opc.tcp://127.0.0.1:' + PUERTO;
const PKI = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-t2-pki-'));
const USUARIO = 'operador_prueba';
// [SEC] Clave efimera generada en cada corrida: no hay secretos en el repo.
const CLAVE = require('node:crypto').randomBytes(12).toString('base64');

/** Copia profunda de config con sobrescrituras (config original congelada). */
function configCon(sobrescrituras) {
    const copia = JSON.parse(JSON.stringify(configBase));
    for (const [seccion, valores] of Object.entries(sobrescrituras)) Object.assign(copia[seccion], valores);
    copia.red.puertoOpcUa = PUERTO;
    copia.opcua.endpointCliente = ENDPOINT;
    // Prueba local: se aceptan los certificados autofirmados de ambos lados.
    // En el banco esto queda en false y la confianza se da a mano (PARTE-4).
    copia.seguridad.aceptarCertificadosDesconocidos = true;
    return copia;
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const nodo = (id) => opcua.resolveNodeId('ns=1;s=' + id);

let control;
const escriturasRecibidas = [];
const registroServidor = [];

test.before(async () => {
    control = await iniciarServidor({
        opcua,
        config: configCon({}),
        directorioPki: path.join(PKI, 'servidor'),
        credenciales: { usuario: USUARIO, hashClave: await hashearClave(CLAVE) },
        alEscribirCliente: (nombre, valor) => escriturasRecibidas.push([nombre, valor]),
        registrar: (t) => registroServidor.push(t),
    });
});

test.after(async () => {
    await control.detener();
    fs.rmSync(PKI, { recursive: true, force: true });
});

/** Sesion anonima directa con node-opcua (cumple el rol de UaExpert). */
async function sesionGenerica(fn, identidad) {
    const c = opcua.OPCUAClient.create({ endpointMustExist: false, connectionStrategy: { maxRetry: 0 } });
    await c.connect(ENDPOINT);
    try {
        const s = await c.createSession(identidad);
        try { return await fn(s); } finally { await s.close(); }
    } finally { await c.disconnect(); }
}

// --------------------------------------------------------------------------
test('1. namespace urn:unraf:pdci:t2 en ns=1 (Parte 2.2)', async () => {
    await sesionGenerica(async (s) => {
        const arreglo = await s.readNamespaceArray();
        assert.equal(arreglo[1], 'urn:unraf:pdci:t2');
    });
});

test('2. los cuatro NodeIds, tipos y niveles de acceso (Parte 2.2)', async () => {
    const esperados = [
        ['Servidor.EstadoPulsador', 'Boolean', 1],
        ['Servidor.Rampa', 'UInt16', 1],
        ['Cliente.EstadoPulsador', 'Boolean', 3],
        ['Cliente.Rampa', 'UInt16', 3],
    ];
    await sesionGenerica(async (s) => {
        for (const [id, tipo, acceso] of esperados) {
            const [bn, dt, al] = await s.read([
                { nodeId: nodo(id), attributeId: opcua.AttributeIds.BrowseName },
                { nodeId: nodo(id), attributeId: opcua.AttributeIds.DataType },
                { nodeId: nodo(id), attributeId: opcua.AttributeIds.AccessLevel },
            ]);
            assert.equal(bn.statusCode, opcua.StatusCodes.Good, id + ' existe');
            assert.equal(bn.value.value.name, id.split('.')[1]);
            assert.equal(dt.value.value.toString(), opcua.resolveNodeId(opcua.DataType[tipo]).toString(), id + ' tipo');
            assert.equal(al.value.value, acceso, id + ' AccessLevel (1 = CurrentRead, 3 = +CurrentWrite)');
        }
    });
});

test('3. EURange 0..65535 en ambas Rampa (Parte 2.2)', async () => {
    await sesionGenerica(async (s) => {
        for (const id of ['Servidor.Rampa', 'Cliente.Rampa']) {
            const r = await s.translateBrowsePath(opcua.makeBrowsePath(nodo(id), '.EURange'));
            assert.equal(r.statusCode, opcua.StatusCodes.Good, id + ' tiene EURange');
            const dv = await s.read({ nodeId: r.targets[0].targetId, attributeId: opcua.AttributeIds.Value });
            assert.equal(dv.value.value.low, 0);
            assert.equal(dv.value.value.high, 65535);
        }
    });
});

test('4. escribir una variable de solo lectura -> BadNotWritable (Parte 2.5)', async () => {
    await sesionGenerica(async (s) => {
        const sc = await s.write({ nodeId: nodo('Servidor.Rampa'), attributeId: opcua.AttributeIds.Value,
            value: { value: { dataType: opcua.DataType.UInt16, value: 123 } } });
        assert.equal(sc.name, 'BadNotWritable');
    });
});

test('5. escribir un tipo incorrecto -> BadTypeMismatch', async () => {
    await sesionGenerica(async (s) => {
        const sc = await s.write({ nodeId: nodo('Cliente.Rampa'), attributeId: opcua.AttributeIds.Value,
            value: { value: { dataType: opcua.DataType.Boolean, value: true } } });
        assert.equal(sc.name, 'BadTypeMismatch');
    });
});

test('6. SourceTimestamp = instante de generacion en la placa', async () => {
    const instante = new Date(Date.now() - 5000);
    control.publicarRampa(4660, instante);
    await sesionGenerica(async (s) => {
        // session.read(nodo, maxAge) pide TimestampsToReturn = Both por defecto.
        const dv = await s.read({ nodeId: nodo('Servidor.Rampa'), attributeId: opcua.AttributeIds.Value }, 0);
        assert.equal(dv.value.value, 4660);
        assert.equal(dv.sourceTimestamp.getTime(), instante.getTime());
        // node-opcua registra el ServerTimestamp en el mismo instante en que
        // recibe el valor de la fuente; como la fuente esta en la misma placa,
        // ambos coinciden. Ver modelo-informacion.md §6.
        assert.ok(dv.serverTimestamp instanceof Date, 'ServerTimestamp presente');
    });
});

test('7. tres endpoints de seguridad por cada direccion anunciada (Parte 4.7)', () => {
    const lista = control.endpoints();
    const combinaciones = new Set(lista.map((e) => e.split(/\s+/).slice(1).join(' ')));
    assert.deepEqual([...combinaciones].sort(),
        ['None None', 'Sign Basic256Sha256', 'SignAndEncrypt Basic256Sha256'].sort());
    for (const e of lista) assert.ok(e.startsWith('opc.tcp://') && e.includes(':' + PUERTO), e);
});

async function correrCliente(sobrescrituras, ms, entorno) {
    const recibidos = [];
    const eventos = [];
    const c = await iniciarCliente({
        opcua, config: configCon(sobrescrituras),
        directorioPki: path.join(PKI, 'cliente'),
        alRecibir: (d) => recibidos.push(d), alEvento: (e) => eventos.push(e), entorno,
    });
    try {
        const inicio = Date.now();
        for (let t = 0; t < ms; t += 50) {
            control.publicarRampa((t * 37) % 65536);
            await esperar(50);
        }
        const transcurrido = Date.now() - inicio;
        const sc = [await c.escribirRampa(321), await c.escribirPulsador(true)];
        return { recibidos, eventos, sc, est: c.estadisticas(), transcurrido };
    } finally {
        await c.detener();
    }
}

test('8. Modo A: Read periodico cada 100 ms (Parte 3.4)', async () => {
    const r = await correrCliente({ lectura: { modo: 'A' } }, 1500);
    // setTimeout se atrasa en Windows y en la RPi: se compara contra el
    // tiempo realmente transcurrido, con +-3 lecturas de tolerancia.
    const esperadas = r.transcurrido / configBase.lectura.periodoReadMs;
    assert.ok(Math.abs(r.est.lecturas - esperadas) <= 3,
        'lecturas ' + r.est.lecturas + ' en ' + r.transcurrido + ' ms (esperadas ~' + esperadas.toFixed(1) + ')');
    assert.ok(r.recibidos.every((d) => d.modo === 'A' && d.sourceTimestamp instanceof Date));
    assert.deepEqual(r.sc, ['Good', 'Good']);
});

test('9. Modo B: suscripcion con parametros revisados (Parte 3.4)', async () => {
    const r = await correrCliente({ lectura: { modo: 'B' } }, 1500);
    assert.ok(r.est.notificaciones >= 5, 'notificaciones: ' + r.est.notificaciones);
    const sub = r.eventos.find((e) => e.evento === 'subscription_created');
    assert.match(sub.detalle, /publishingInterval=100 ms/);
    const mon = r.eventos.find((e) => e.evento === 'monitored_items_created');
    assert.ok(mon, 'se informan los valores revisados');
    assert.match(mon.detalle, /samplingInterval=100 ms queueSize=1/);
});

test('10. las escrituras del cliente llegan al servidor (Parte 3.3)', () => {
    assert.ok(escriturasRecibidas.some(([n, v]) => n === 'clienteRampa' && v === 321));
    assert.ok(escriturasRecibidas.some(([n, v]) => n === 'clientePulsador' && v === true));
});

test('11. SignAndEncrypt Basic256Sha256 con usuario y contrasena (Partes 4.7 y 4.9)', async () => {
    const r = await correrCliente({
        lectura: { modo: 'B' },
        seguridad: { modoCliente: 'SignAndEncrypt', politicaCliente: 'Basic256Sha256', autenticacionCliente: 'usuario' },
    }, 600, { OPCUA_CLIENTE_USUARIO: USUARIO, OPCUA_CLIENTE_CLAVE: CLAVE });
    assert.deepEqual(r.sc, ['Good', 'Good']);
    assert.ok(registroServidor.some((t) => t.includes('modo=SignAndEncrypt')));
});

test('12. Sign Basic256Sha256 anonimo (Parte 4.7)', async () => {
    const r = await correrCliente({
        lectura: { modo: 'A' }, seguridad: { modoCliente: 'Sign', politicaCliente: 'Basic256Sha256' },
    }, 400);
    assert.deepEqual(r.sc, ['Good', 'Good']);
});

test('13. clave incorrecta -> la sesion se rechaza (Parte 4.9)', async () => {
    await assert.rejects(
        sesionGenerica(async () => {}, { type: opcua.UserTokenType.UserName, userName: USUARIO, password: 'incorrecta-123' }),
        (error) => /BadUserAccessDenied|BadIdentityTokenRejected|BadIdentityTokenInvalid/.test(error.message));
    assert.ok(registroServidor.some((t) => t.includes('clave incorrecta')));
    assert.ok(!registroServidor.some((t) => t.includes('incorrecta-123')), '[SEC] la clave no aparece en el log');
});

test('14. falta de credenciales en el entorno -> error explicito, sin valores por defecto', async () => {
    await assert.rejects(correrCliente({ seguridad: { autenticacionCliente: 'usuario' } }, 0, {}),
        /OPCUA_CLIENTE_USUARIO/);
});

test('15. soloAutenticadosEscriben: anonimo -> BadUserAccessDenied, usuario -> Good (Parte 4.9)', async () => {
    const puerto = PUERTO + 1;
    const cfg = configCon({ seguridad: { soloAutenticadosEscriben: true } });
    cfg.red.puertoOpcUa = puerto;
    const ctl = await iniciarServidor({
        opcua, config: cfg, directorioPki: path.join(PKI, 'servidor2'),
        credenciales: { usuario: USUARIO, hashClave: await hashearClave(CLAVE) },
    });
    const escribir = async (identidad) => {
        const c = opcua.OPCUAClient.create({ endpointMustExist: false, connectionStrategy: { maxRetry: 0 } });
        await c.connect('opc.tcp://127.0.0.1:' + puerto);
        try {
            const s = await c.createSession(identidad);
            try {
                const sc = await s.write({ nodeId: nodo('Cliente.Rampa'), attributeId: opcua.AttributeIds.Value,
                    value: { value: { dataType: opcua.DataType.UInt16, value: 7 } } });
                const leido = await s.read({ nodeId: nodo('Cliente.Rampa'), attributeId: opcua.AttributeIds.Value });
                return [sc.name, leido.statusCode.name];
            } finally { await s.close(); }
        } finally { await c.disconnect(); }
    };
    try {
        assert.deepEqual(await escribir(undefined), ['BadUserAccessDenied', 'Good'], 'el anonimo puede leer pero no escribir');
        assert.deepEqual(await escribir({ type: opcua.UserTokenType.UserName, userName: USUARIO, password: CLAVE }),
            ['Good', 'Good']);
    } finally {
        await ctl.detener();
    }
});
