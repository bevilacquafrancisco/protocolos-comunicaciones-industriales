/**
 * verificar_opcua.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-10
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Verificacion F4 del servidor OPC UA, reproducible (complementa -no reemplaza- el recorrido
 * manual con UaExpert):
 *   1. Abre UNA sesion completa (HEL -> OPN -> CreateSession -> ActivateSession -> ... ->
 *      CloseSession -> CLO) en el modo de seguridad pedido: sirve para la captura de Wireshark.
 *   2. Recorre Dispositivo1 con Browse y lee, por cada variable, NodeId, BrowseName, DataType,
 *      AccessLevel, UserAccessLevel, Value, StatusCode, SourceTimestamp y ServerTimestamp
 *      (y EURange de los AnalogItem).
 *   3. Escribe un nodo de solo lectura y registra el StatusCode devuelto.
 *   4. Con usuario: escribe LedDigital y LedPWM y relee (el valor solo cambia si el esclavo
 *      confirmo, ADR-015).
 *   5. Con --informe, vuelca todo a Markdown (docs/opcua-espacio-direcciones.md).
 *
 * Uso (en tarea-3/; usa node-opcua de edge-nodered/node_modules)
 *   node tools/verificar_opcua.js [--url opc.tcp://127.0.0.1:4840] [--modo None|Sign|SignAndEncrypt]
 *        [--usuario operador] [--pki <carpeta PKI del cliente>] [--informe docs/opcua-espacio-direcciones.md]
 *   La contrasena del usuario se lee de la variable de entorno PDCI_T3_OPCUA_CLAVE (nunca por
 *   argumento: quedaria en el historial y en la lista de procesos).
 *   Con Sign o SignAndEncrypt, la primera vez el servidor rechaza el certificado del cliente
 *   (BadSecurityChecksFailed): confiarlo segun docs/seguridad-opcua.md §4 y repetir.
 *
 * Salida: codigo 1 si alguna verificacion falla.
 * Dependencias externas: node-opcua 2.160.0 (edge-nodered/node_modules).
 */
'use strict';

const path = require('node:path');
const fs = require('node:fs');
const opcua = require(path.join(__dirname, '..', 'edge-nodered', 'node_modules', 'node-opcua'));

// ----------------------------------------------------------------- argumentos
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, v) =>
    (a.startsWith('--') ? acc.concat([[a.slice(2), v[i + 1] && !v[i + 1].startsWith('--') ? v[i + 1] : true]]) : acc), []));
const URL = args.url || 'opc.tcp://127.0.0.1:4840';
const MODO = args.modo || 'None';
const USUARIO = args.usuario || null;
const CLAVE = process.env.PDCI_T3_OPCUA_CLAVE || '';
const PKI = args.pki || path.join(require('node:os').homedir(), '.pdci-t3', 'opcua-cliente-pki');

let fallas = 0;
const resultados = [];
/** Registra una verificacion. */
function check(nombre, ok, detalle = '') {
    resultados.push({ nombre, ok, detalle });
    if (!ok) fallas += 1;
    console.log(`${ok ? 'OK   ' : 'FALLA'} ${nombre}${detalle ? ` — ${detalle}` : ''}`);
}

/** Nombre simbolico de un AccessLevel (bits de OPC UA Part 3 §8.57). */
// Bits 0 y 1 de AccessLevel (OPC UA Part 3 §5.6.2); separados con "+" para no romper la tabla Markdown.
const nivelAcceso = (n) => ['CurrentRead', 'CurrentWrite'].filter((_, i) => n & (1 << i)).join(' + ') || 'None';
const fecha = (d) => (d ? new Date(d).toISOString() : '—');

/**
 * Recorre recursivamente un nodo y devuelve los NodeId de sus variables.
 * @param {opcua.ClientSession} s
 * @param {string} nodeId
 * @returns {Promise<Array<{nodeId:string, ruta:string, clase:string}>>}
 */
async function recorrer(s, nodeId, ruta = '') {
    const r = await s.browse({ nodeId, referenceTypeId: 'HierarchicalReferences', includeSubtypes: true,
        browseDirection: opcua.BrowseDirection.Forward, nodeClassMask: 0, resultMask: 63 });
    const salida = [];
    for (const ref of r.references || []) {
        if (ref.nodeId.namespace !== 1) continue;   // solo el espacio propio (EURange y cia. son ns=0)
        const clase = opcua.NodeClass[ref.nodeClass];
        const hijo = ref.nodeId.toString();
        salida.push({ nodeId: hijo, ruta: `${ruta}/${ref.browseName.name}`, clase });
        if (clase === 'Object') salida.push(...await recorrer(s, hijo, `${ruta}/${ref.browseName.name}`));
    }
    return salida;
}

/** Lee los atributos de una variable. */
async function atributos(s, nodeId) {
    const A = opcua.AttributeIds;
    const leer = [A.BrowseName, A.DataType, A.AccessLevel, A.UserAccessLevel, A.Value]
        .map((attributeId) => ({ nodeId, attributeId }));
    const [bn, dt, al, ual, val] = await s.read(leer);
    const tipo = dt.value.value ? (opcua.DataType[dt.value.value.value] || dt.value.value.toString()) : '?';
    let euRange = '';
    try {
        const eu = await s.translateBrowsePath(opcua.makeBrowsePath(nodeId, '/EURange'));
        if (eu.targets && eu.targets.length) {
            const v = (await s.read({ nodeId: eu.targets[0].targetId })).value.value;
            euRange = `${v.low} … ${v.high}`;
        }
    } catch { /* sin EURange */ }
    return { nodeId, browseName: bn.value.value.toString(), tipo, accessLevel: nivelAcceso(al.value.value),
        userAccessLevel: nivelAcceso(ual.value.value), valor: val.value ? val.value.value : null,
        statusCode: val.statusCode.name, sourceTimestamp: fecha(val.sourceTimestamp),
        serverTimestamp: fecha(val.serverTimestamp), euRange };
}

(async () => {
    const cliente = opcua.OPCUAClient.create({
        applicationName: 'PdCI-T3-verificador', applicationUri: 'urn:pdci-t3:verificador',
        securityMode: opcua.MessageSecurityMode[MODO], securityPolicy: MODO === 'None'
            ? opcua.SecurityPolicy.None : opcua.SecurityPolicy.Basic256Sha256,
        endpointMustExist: false, connectionStrategy: { maxRetry: 0 },
        clientCertificateManager: new opcua.OPCUACertificateManager({ rootFolder: PKI,
            automaticallyAcceptUnknownCertificate: false }),
    });
    await cliente.clientCertificateManager.initialize();
    if (MODO !== 'None') {
        // Confianza mutua: el cliente tambien debe confiar en el servidor. Se lee su
        // certificado del GetEndpoints (canal None) y se muestra la huella para compararla
        // con la del panel de Node-RED.
        const descubrimiento = opcua.OPCUAClient.create({ endpointMustExist: false, connectionStrategy: { maxRetry: 0 } });
        await descubrimiento.connect(URL);
        const [ep] = await descubrimiento.getEndpoints();
        await descubrimiento.disconnect();
        const huella = require(path.join(__dirname, '..', 'edge-nodered', 'node_modules', 'node-opcua-crypto'))
            .makeSHA1Thumbprint(ep.serverCertificate).toString('hex');
        console.log(`huella del servidor: ${huella} (compararla con el panel antes de confiar)`);
        await cliente.clientCertificateManager.trustCertificate(ep.serverCertificate);
    }

    const t0 = Date.now();
    await cliente.connect(URL);
    const identidad = USUARIO ? { type: opcua.UserTokenType.UserName, userName: USUARIO, password: CLAVE } : undefined;
    const s = await cliente.createSession(identidad);
    console.log(`sesion abierta: modo ${MODO}, ${USUARIO ? `usuario ${USUARIO}` : 'anonimo'} (${Date.now() - t0} ms)`);

    // 1-2. Browse + atributos
    const nodos = await recorrer(s, 'ns=1;s=Dispositivo1', '/Dispositivo1');
    const variables = [];
    for (const n of nodos.filter((x) => x.clase === 'Variable')) variables.push(Object.assign({ ruta: n.ruta }, await atributos(s, n.nodeId)));
    const objetos = nodos.filter((x) => x.clase === 'Object');
    check('jerarquia Inputs/Outputs/Status', ['Inputs', 'Outputs', 'Status'].every((c) => objetos.some((o) => o.ruta === `/Dispositivo1/${c}`)));
    check('namespace ns=1 = urn:unraf:pdci:t3',
        (await s.read({ nodeId: 'i=2255' })).value.value[1] === 'urn:unraf:pdci:t3');
    check('variables del diccionario presentes', ['Inputs.Pulsador', 'Inputs.Potenciometro', 'Inputs.Potenciometro_pct',
        'Outputs.LedDigital', 'Outputs.LedPWM', 'Status.MODBUS.Estado', 'Status.OPCUA.Estado']
        .every((n) => variables.some((v) => v.nodeId === `ns=1;s=${n.startsWith('Status') ? '' : 'Dispositivo1.'}${n}`)), `${variables.length} variables`);

    // 3. Escritura sobre un nodo de solo lectura
    const ro = 'ns=1;s=Dispositivo1.Inputs.Pulsador';
    const codRo = await s.write({ nodeId: ro, attributeId: opcua.AttributeIds.Value,
        value: { value: { dataType: opcua.DataType.Boolean, value: true } } });
    check('Write sobre Inputs.Pulsador (solo lectura) rechazado', codRo.name === 'BadNotWritable', codRo.toString());

    // 4. Escrituras sobre Outputs
    const escrituras = [];
    for (const [nodo, tipo, valor] of [['Outputs.LedDigital', 'Boolean', true], ['Outputs.LedPWM', 'UInt16', 128],
        ['Outputs.LedPWM', 'UInt16', 300]]) {
        const nodeId = `ns=1;s=Dispositivo1.${nodo}`;
        const t = Date.now();
        const cod = await s.write({ nodeId, attributeId: opcua.AttributeIds.Value,
            value: { value: { dataType: opcua.DataType[tipo], value: valor } } });
        const ms = Date.now() - t;
        const leido = (await s.read({ nodeId })).value.value;
        escrituras.push({ nodo, valor, statusCode: cod.toString(), ms, leido });
        if (!USUARIO) check(`Write anonimo sobre ${nodo} rechazado`, cod.name === 'BadUserAccessDenied', cod.toString());
        else if (valor === 300) check(`Write ${nodo} = 300 fuera de EURange rechazado y valor intacto`, cod.name !== 'Good' && leido !== 300, cod.toString());
        else check(`Write ${nodo} = ${valor} confirmado por el esclavo`, cod.name === 'Good' && leido === valor, `${cod.toString()} en ${ms} ms`);
    }

    await s.close();
    await cliente.disconnect();
    console.log('sesion cerrada (CloseSession + CLO)');

    // 5. Informe
    if (args.informe) {
        const fila = (v) => `| \`${v.nodeId}\` | ${v.browseName} | ${v.tipo} | ${v.accessLevel} | ${v.userAccessLevel} | `
            + `${JSON.stringify(v.valor)} | ${v.statusCode} | ${v.sourceTimestamp} | ${v.serverTimestamp} | ${v.euRange || '—'} |`;
        const md = [
            '# Espacio de direcciones OPC UA — verificación F4',
            '',
            `> Generado por \`tools/verificar_opcua.js\` el ${new Date().toISOString()} contra \`${URL}\`, `
            + `modo **${MODO}**, ${USUARIO ? `usuario **${USUARIO}**` : '**anónimo**'}. `
            + 'Medido **en la PC** (Node-RED + simulador del esclavo por TCP); el banco con la Raspberry Pi queda **pendiente**.',
            '> AccessLevel / UserAccessLevel: el segundo depende de la identidad de la sesión (ADR-009).',
            '',
            '## Objetos',
            '',
            '| NodeId | Ruta |',
            '|---|---|',
            ...objetos.map((o) => `| \`${o.nodeId}\` | ${o.ruta} |`),
            '',
            '## Variables',
            '',
            '| NodeId | BrowseName | DataType | AccessLevel | UserAccessLevel | Value | StatusCode | SourceTimestamp | ServerTimestamp | EURange |',
            '|---|---|---|---|---|---|---|---|---|---|',
            ...variables.map(fila),
            '',
            '## Escrituras',
            '',
            '| Nodo | Valor pedido | StatusCode del WriteResponse | Tiempo (ms) | Valor releído |',
            '|---|---|---|---|---|',
            `| Inputs/Pulsador (solo lectura) | true | ${codRo.toString()} | — | — |`,
            ...escrituras.map((e) => `| ${e.nodo} | ${e.valor} | ${e.statusCode} | ${e.ms} | ${JSON.stringify(e.leido)} |`),
            '',
            '## Verificaciones',
            '',
            '| Resultado | Verificación | Detalle |',
            '|---|---|---|',
            ...resultados.map((r) => `| ${r.ok ? 'OK' : '**FALLA**'} | ${r.nombre} | ${r.detalle} |`),
            '',
        ].join('\n');
        fs.writeFileSync(args.informe, md, 'utf8');
        console.log(`informe: ${args.informe}`);
    }
    process.exit(fallas ? 1 : 0);
})().catch((e) => {
    console.error(`ERROR: ${String(e.message).split('\n')[0]}`);
    process.exit(1);
});
