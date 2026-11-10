/**
 * servidor_opcua.test.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-10
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Fase F4: el servidor OPC UA real (lib/servidor_opcua.js) contra un cliente node-opcua real,
 * en loopback, con un maestro MODBus falso cuyo resultado de escritura se controla.
 *
 *   - Espacio de direcciones del diccionario §3: NodeIds, tipos, AccessLevel y EURange.
 *   - Escritura sobre un nodo de solo lectura -> BadNotWritable (con usuario).
 *   - Escritura anonima sobre Outputs -> BadUserAccessDenied.
 *   - Escritura con usuario: Good SOLO si el maestro confirma; si falla, el StatusCode del
 *     fallo y el valor OPC UA queda como estaba ("no mentir sobre el estado").
 *   - Tres endpoints; Sign y SignAndEncrypt rechazan un certificado no confiado y aceptan el
 *     mismo cliente despues de moverlo a trusted/ (procedimiento de docs/seguridad-opcua.md).
 *   - Clave incorrecta rechazada.
 *   - Status.OPCUA.Estado: DONE con datos frescos, ERROR con datos vencidos.
 */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const opcua = require('node-opcua');
const { iniciarServidor } = require('../lib/servidor_opcua');
const { hashearClave } = require('../lib/credenciales');

jest.setTimeout(180000);

const PUERTO = 48840 + Math.floor(Math.random() * 100);
const URL = `opc.tcp://127.0.0.1:${PUERTO}`;
const USUARIO = 'operador';
const CLAVE = 'clave-de-prueba-solo-para-test';   // [SEC] solo en esta prueba, nunca en produccion
const DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-t3-opcua-'));
const ns = (s) => `ns=1;s=${s}`;

let servidor;
const maestroFalso = { resultado: { ok: true, errorType: 'NONE', error: null }, pedidos: [] };

// PKI del cliente SIN aceptacion automatica: la confianza es mutua y se prueba en las dos
// direcciones (docs/seguridad-opcua.md §3).
const pkiCliente = new opcua.OPCUACertificateManager({
    rootFolder: path.join(DIR, 'pki-cliente'), automaticallyAcceptUnknownCertificate: false });

/** Conecta, ejecuta fn(sesion) y desconecta. */
async function conSesion(opciones, fn) {
    const cliente = opcua.OPCUAClient.create(Object.assign({
        endpointMustExist: false, connectionStrategy: { maxRetry: 0 },
        clientCertificateManager: pkiCliente,
    }, opciones.cliente || {}));
    await cliente.connect(URL);
    try {
        const sesion = await cliente.createSession(opciones.identidad || { type: opcua.UserTokenType.Anonymous });
        try { return await fn(sesion); } finally { await sesion.close(); }
    } finally {
        await cliente.disconnect();
    }
}
const comoUsuario = { identidad: { type: opcua.UserTokenType.UserName, userName: USUARIO, password: CLAVE } };
const escribir = (sesion, nodeId, tipo, valor) => sesion.write({ nodeId, attributeId: opcua.AttributeIds.Value,
    value: { value: { dataType: opcua.DataType[tipo], value: valor } } });

beforeAll(async () => {
    servidor = await iniciarServidor({
        opcua, puerto: PUERTO, namespaceUri: 'urn:unraf:pdci:t3', directorioPki: path.join(DIR, 'pki-servidor'),
        credenciales: { usuario: USUARIO, hashClave: await hashearClave(CLAVE) },
        escribir: async (nombre, valor) => { maestroFalso.pedidos.push([nombre, valor]); return maestroFalso.resultado; },
    });
    // El maestro "lee" el dispositivo 1.
    servidor.publicarValor('Inputs/Pulsador', true, 'good');
    servidor.publicarValor('Inputs/Potenciometro', 2047, 'good');
    servidor.publicarValor('Inputs/Potenciometro_pct', 50, 'good');
    servidor.publicarValor('Outputs/LedDigital', false, 'good');
    servidor.publicarValor('Outputs/LedPWM', 10, 'good');
    servidor.publicarEstadoModbus({ estado: 'DONE', contadores: { OK: 120, CRC_ERROR: 1, TIMEOUT: 2, EXCEPTION: 0 },
        ultimaTx: '01 04 00 00 00 01 31 CA', ultimaRx: '01 04 02 07 FF FB 40', latenciaMs: 16 });
});

afterAll(async () => {
    if (servidor) await servidor.detener(0);
    fs.rmSync(DIR, { recursive: true, force: true });
});

describe('F4 · espacio de direcciones (diccionario de datos §3)', () => {
    test('namespace urn:unraf:pdci:t3 en ns=1', async () => {
        await conSesion({}, async (s) => {
            const dv = await s.read({ nodeId: 'ns=0;i=2255', attributeId: opcua.AttributeIds.Value });   // NamespaceArray
            expect(dv.value.value[1]).toBe('urn:unraf:pdci:t3');
        });
    });

    test('jerarquia Dispositivo1/{Inputs,Outputs,Status/{MODBUS,OPCUA}} navegable con Browse', async () => {
        await conSesion({}, async (s) => {
            const nombres = async (nodeId) => (await s.browse(nodeId)).references.map((r) => r.browseName.name);
            expect(await nombres(ns('Dispositivo1'))).toEqual(expect.arrayContaining(['Inputs', 'Outputs', 'Status']));
            expect(await nombres(ns('Dispositivo1.Inputs'))).toEqual(expect.arrayContaining(['Pulsador', 'Potenciometro', 'Potenciometro_pct']));
            expect(await nombres(ns('Dispositivo1.Outputs'))).toEqual(expect.arrayContaining(['LedDigital', 'LedPWM']));
            expect(await nombres(ns('Dispositivo1.Status'))).toEqual(expect.arrayContaining(['MODBUS', 'OPCUA']));
            expect(await nombres(ns('Status.MODBUS'))).toEqual(expect.arrayContaining(
                ['Estado', 'OK', 'CRC_ERROR', 'TIMEOUT', 'EXCEPTION', 'UltimaTramaTx', 'UltimaTramaRx', 'LatenciaMs']));
        });
    });

    test.each([
        ['Dispositivo1.Inputs.Pulsador', 'Boolean', 1, true],
        ['Dispositivo1.Inputs.Potenciometro', 'UInt16', 1, 2047],
        ['Dispositivo1.Inputs.Potenciometro_pct', 'Float', 1, 50],
        ['Dispositivo1.Outputs.LedDigital', 'Boolean', 3, false],
        ['Dispositivo1.Outputs.LedPWM', 'UInt16', 3, 10],
        ['Status.MODBUS.Estado', 'String', 1, 'DONE'],
        ['Status.MODBUS.OK', 'UInt32', 1, 120],
        ['Status.MODBUS.TIMEOUT', 'UInt32', 1, 2],
        ['Status.MODBUS.UltimaTramaTx', 'String', 1, '01 04 00 00 00 01 31 CA'],
        ['Status.MODBUS.LatenciaMs', 'UInt16', 1, 16],
        ['Status.OPCUA.Estado', 'String', 1, 'DONE'],
    ])('%s: %s, AccessLevel %i, valor', async (nodeId, tipo, acceso, valor) => {
        await conSesion({}, async (s) => {
            const [dataType, accessLevel, value] = await s.read([
                { nodeId: ns(nodeId), attributeId: opcua.AttributeIds.DataType },
                { nodeId: ns(nodeId), attributeId: opcua.AttributeIds.AccessLevel },
                { nodeId: ns(nodeId), attributeId: opcua.AttributeIds.Value }]);
            expect(dataType.value.value.toString()).toBe(opcua.resolveNodeId(opcua.DataTypeIds[tipo]).toString());
            expect(accessLevel.value.value).toBe(acceso);
            expect(value.statusCode.name).toBe('Good');
            expect(value.value.value).toBe(valor);
            expect(value.sourceTimestamp).toBeInstanceOf(Date);
            expect(value.serverTimestamp).toBeInstanceOf(Date);
        });
    });

    test.each([
        ['Dispositivo1.Inputs.Potenciometro', 0, 4095],
        ['Dispositivo1.Inputs.Potenciometro_pct', 0, 100],
        ['Dispositivo1.Outputs.LedPWM', 0, 255],
    ])('EURange de %s = %i..%i', async (nodeId, low, high) => {
        await conSesion({}, async (s) => {
            const ref = (await s.browse(ns(nodeId))).references.find((r) => r.browseName.name === 'EURange');
            expect(ref).toBeDefined();
            const rango = (await s.read({ nodeId: ref.nodeId, attributeId: opcua.AttributeIds.Value })).value.value;
            expect([rango.low, rango.high]).toEqual([low, high]);
        });
    });
});

describe('F4 · escrituras', () => {
    test('nodo de solo lectura: BadNotWritable (aun con usuario)', async () => {
        await conSesion(comoUsuario, async (s) => {
            expect((await escribir(s, ns('Dispositivo1.Inputs.Potenciometro'), 'UInt16', 5)).name).toBe('BadNotWritable');
            expect((await escribir(s, ns('Status.MODBUS.OK'), 'UInt32', 0)).name).toBe('BadNotWritable');
        });
    });

    test('anonimo sobre Outputs: BadUserAccessDenied y no llega al maestro', async () => {
        maestroFalso.pedidos = [];
        await conSesion({}, async (s) => {
            expect((await escribir(s, ns('Dispositivo1.Outputs.LedPWM'), 'UInt16', 99)).name).toBe('BadUserAccessDenied');
        });
        expect(maestroFalso.pedidos).toEqual([]);
    });

    test('usuario: Good solo cuando el maestro confirma (eco), y el valor cambia', async () => {
        maestroFalso.resultado = { ok: true, errorType: 'NONE', error: null };
        await conSesion(comoUsuario, async (s) => {
            expect((await escribir(s, ns('Dispositivo1.Outputs.LedPWM'), 'UInt16', 128)).name).toBe('Good');
            expect((await escribir(s, ns('Dispositivo1.Outputs.LedDigital'), 'Boolean', true)).name).toBe('Good');
            const [pwm, led] = await s.read([{ nodeId: ns('Dispositivo1.Outputs.LedPWM') }, { nodeId: ns('Dispositivo1.Outputs.LedDigital') }]);
            expect([pwm.value.value, led.value.value]).toEqual([128, true]);
        });
        expect(maestroFalso.pedidos).toEqual([['Outputs/LedPWM', 128], ['Outputs/LedDigital', true]]);
    });

    test.each([
        ['TIMEOUT', 'BadCommunicationError'],
        ['CRC_ERROR', 'BadCommunicationError'],
        ['EXCEPTION', 'BadDeviceFailure'],
        ['VALOR_INVALIDO', 'BadOutOfRange'],
    ])('si la escritura MODBus falla con %s: %s y el valor NO queda como escrito', async (errorType, status) => {
        maestroFalso.resultado = { ok: false, errorType, error: 'simulado' };
        await conSesion(comoUsuario, async (s) => {
            const antes = (await s.read({ nodeId: ns('Dispositivo1.Outputs.LedPWM') })).value.value;
            expect((await escribir(s, ns('Dispositivo1.Outputs.LedPWM'), 'UInt16', 222)).name).toBe(status);
            expect((await s.read({ nodeId: ns('Dispositivo1.Outputs.LedPWM') })).value.value).toBe(antes);
        });
        maestroFalso.resultado = { ok: true, errorType: 'NONE', error: null };
    });

    test('tipo equivocado: BadTypeMismatch sin llegar al maestro', async () => {
        maestroFalso.pedidos = [];
        await conSesion(comoUsuario, async (s) => {
            expect((await escribir(s, ns('Dispositivo1.Outputs.LedPWM'), 'String', 'cien')).name).toBe('BadTypeMismatch');
        });
        expect(maestroFalso.pedidos).toEqual([]);
    });
});

describe('F4 · calidad y salud', () => {
    test('esclavo no alcanzado: UncertainLastUsableValue con el ultimo valor', async () => {
        servidor.publicarValor('Inputs/Potenciometro', 2047, 'bad');
        await conSesion({}, async (s) => {
            const dv = await s.read({ nodeId: ns('Dispositivo1.Inputs.Potenciometro') });
            expect(dv.statusCode.name).toBe('UncertainLastUsableValue');
            expect(dv.value.value).toBe(2047);
        });
        servidor.publicarValor('Inputs/Potenciometro', 2047, 'good');
    });

    test('variable del mapa que no esta en el diccionario: se publica en Dispositivo1.Mapa (I-04)', async () => {
        servidor.publicarValor('Outputs/Consigna', 500, 'good');
        await conSesion({}, async (s) => {
            expect((await s.read({ nodeId: ns('Dispositivo1.Mapa.Outputs_Consigna') })).value.value).toBe(500);
        });
    });

    test('estadisticas de la capa OPC UA para el panel de las cuatro capas', () => {
        const e = servidor.estadisticas();
        expect(e.estado).toBe('DONE');
        expect(e.contadores).toEqual(expect.objectContaining({ escriturasOk: expect.any(Number), escriturasRechazadas: expect.any(Number) }));
        expect(e.contadores.escriturasRechazadas).toBeGreaterThanOrEqual(4);
    });
});

describe('F4 · seguridad (ADR-009)', () => {
    test('tres endpoints: None, Basic256Sha256 Sign y SignAndEncrypt', async () => {
        const cliente = opcua.OPCUAClient.create({ endpointMustExist: false, connectionStrategy: { maxRetry: 0 } });
        await cliente.connect(URL);
        const endpoints = await cliente.getEndpoints();
        await cliente.disconnect();
        const combinaciones = new Set(endpoints.map((e) =>
            `${opcua.MessageSecurityMode[e.securityMode]}/${String(e.securityPolicyUri).split('#').pop()}`));
        expect(combinaciones).toEqual(new Set(['None/None', 'Sign/Basic256Sha256', 'SignAndEncrypt/Basic256Sha256']));
    });

    test('clave incorrecta: la sesion se rechaza', async () => {
        await expect(conSesion({ identidad: { type: opcua.UserTokenType.UserName, userName: USUARIO, password: 'otra' } },
            async () => null)).rejects.toThrow();
        expect(servidor.estadisticas().detalle.usuariosRechazados).toBeGreaterThanOrEqual(1);
    });

    test('paso 1: el cliente no confia en un servidor desconocido; confia tras agregar su certificado', async () => {
        const opciones = { cliente: { securityMode: opcua.MessageSecurityMode.Sign, securityPolicy: opcua.SecurityPolicy.Basic256Sha256 } };
        await expect(conSesion(opciones, async () => null)).rejects.toThrow();
        // El operador del dispositivo 3 copia own/certs/ del servidor a trusted/certs/ del cliente.
        await pkiCliente.trustCertificate(servidor.servidor.getCertificate());
    });

    const pkiServidor = path.join(DIR, 'pki-servidor');
    const seguro = (modo) => ({ cliente: { securityMode: opcua.MessageSecurityMode[modo],
        securityPolicy: opcua.SecurityPolicy.Basic256Sha256 } });

    test('paso 2: el servidor rechaza al cliente no confiado y deja su certificado en rejected/', async () => {
        const error = await conSesion(seguro('Sign'), async () => null).then(() => null, (e) => e);
        expect(error).not.toBeNull();
        // node-opcua escribe el certificado rechazado de forma asincronica: se espera hasta 3 s.
        const rechazados = path.join(pkiServidor, 'rejected');
        let archivos = [];
        for (let i = 0; i < 30 && !archivos.length; i++) {
            archivos = fs.existsSync(rechazados) ? fs.readdirSync(rechazados).filter((f) => f.endsWith('.pem')) : [];
            if (!archivos.length) await new Promise((r) => setTimeout(r, 100));
        }
        expect(archivos).toEqual([expect.stringMatching(/^NodeOPCUA-Client/)]);
        const { rechazados: lista } = servidor.listarCertificados();
        expect(lista).toHaveLength(1);
        expect(lista[0].huella).toMatch(/^[0-9a-f]{40}$/);
    });

    test('mover el archivo a trusted/ con el servidor corriendo NO alcanza (indice en memoria)', async () => {
        const rechazados = path.join(pkiServidor, 'rejected');
        const confiables = path.join(pkiServidor, 'trusted', 'certs');
        const [archivo] = fs.readdirSync(rechazados).filter((f) => f.endsWith('.pem'));
        fs.renameSync(path.join(rechazados, archivo), path.join(confiables, archivo));
        await new Promise((r) => setTimeout(r, 2000));
        await expect(conSesion(Object.assign({}, seguro('Sign'), comoUsuario), async () => null)).rejects.toThrow();
        // Se deshace para probar el camino en vivo.
        fs.renameSync(path.join(confiables, archivo), path.join(rechazados, archivo));
    });

    test('confiar en vivo por huella (API del gestor de certificados)', async () => {
        const [c] = servidor.listarCertificados().rechazados;
        expect(await servidor.confiarCertificado('0'.repeat(40))).toMatchObject({ ok: false });
        expect(await servidor.confiarCertificado(c.huella)).toEqual({ ok: true });
        expect(servidor.listarCertificados().confiables.map((x) => x.huella)).toContain(c.huella);
        // El certificado propio del servidor no se lista (no se puede revocar desde el panel).
        expect(servidor.listarCertificados().confiables.map((x) => x.huella)).not.toContain(servidor.huellaPropia());
    });

    test.each(['Sign', 'SignAndEncrypt'])('paso 3, %s: con el cliente confiado la sesion se acepta', async (modo) => {
        const valor = await conSesion(Object.assign({}, seguro(modo), comoUsuario), async (s) =>
            (await s.read({ nodeId: ns('Status.MODBUS.Estado') })).value.value);
        expect(valor).toBe('DONE');
    });

    test('revocar: la siguiente sesion segura se rechaza', async () => {
        const [c] = servidor.listarCertificados().confiables.filter((x) => x.sujeto.startsWith('NodeOPCUA-Client'));
        expect(await servidor.revocarCertificado(c.huella)).toEqual({ ok: true });
        await expect(conSesion(Object.assign({}, seguro('SignAndEncrypt'), comoUsuario), async () => null)).rejects.toThrow();
    });
});

describe('F4 · Status.OPCUA.Estado', () => {
    test('ERROR cuando los datos del maestro estan vencidos', async () => {
        let reloj = Date.now();
        const s2 = await iniciarServidor({
            opcua, puerto: PUERTO + 200, namespaceUri: 'urn:unraf:pdci:t3', directorioPki: path.join(DIR, 'pki-2'),
            credenciales: null, escribir: async () => ({ ok: true }), ahora: () => reloj,
        });
        try {
            s2.publicarEstadoModbus({ estado: 'DONE', contadores: { OK: 1, CRC_ERROR: 0, TIMEOUT: 0, EXCEPTION: 0 } });
            expect(s2.evaluarSalud()).toBe('DONE');
            reloj += 6000;
            expect(s2.evaluarSalud()).toBe('ERROR');
        } finally {
            await s2.detener(0);
        }
    });
});

describe('F4 · certificado X.509 de aplicacion', () => {
    test('sujeto propio (no el de ejemplo de node-opcua), applicationUri y 730 dias', () => {
        const { exploreCertificate } = require('node-opcua-crypto');
        const tbs = exploreCertificate(servidor.servidor.getCertificate()).tbsCertificate;
        expect(tbs.subject).toMatchObject({ commonName: 'PdCI-T3 Dispositivo 2', organizationName: 'UNRaf', countryName: 'AR' });
        expect(tbs.extensions.subjectAltName.uniformResourceIdentifier[0]).toMatch(/^urn:.+:unraf:pdci:t3:servidor$/);
        const dias = (tbs.validity.notAfter - tbs.validity.notBefore) / 86400000;
        expect(Math.round(dias)).toBe(730);
    });
});
