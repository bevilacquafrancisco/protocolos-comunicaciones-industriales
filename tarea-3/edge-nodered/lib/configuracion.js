/**
 * configuracion.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Configuracion del maestro MODBus: carga, validacion, normalizacion y persistencia en
 * archivo. Materializa el invariante I-04: el maestro se reconfigura EN VIVO (puerto,
 * enlace, Unit ID, tiempos y mapa de registros) desde el Dashboard, sin recompilar ni
 * reiniciar, y la configuracion sobrevive a un reinicio porque se guarda en disco.
 *
 * Fuentes, en orden:
 *   1. archivo del usuario (por defecto <userDir>/pdci-t3-config.json), lo que se aplico
 *      desde el Dashboard;
 *   2. config/config.default.json, versionado.
 * Un archivo del usuario invalido NO detiene el maestro: se usa el de fabrica y se avisa
 * (misma regla que la T1: un nodo con configuracion vieja arranca avisando, nunca aborta).
 *
 * Seguridad: todo lo que llega del Dashboard es entrada no confiable; validar() rechaza
 * tipos, rangos y combinaciones invalidas ANTES de tocar el puerto o el archivo.
 *
 * Dependencias externas: ninguna (node:fs, node:path).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

/** Configuracion de fabrica, versionada. */
const RUTA_DEFECTO = path.join(__dirname, '..', 'config', 'config.default.json');

/** Valores admitidos. */
const PARIDADES = ['none', 'even', 'odd'];
const TIPOS_PUERTO = ['serie', 'tcp'];
/** Tipos de dato del mapa y cuantos registros de 16 bits ocupan. */
const TIPOS = { bool: 1, uint16: 1, int16: 1, uint32: 2, int32: 2, float32: 2 };
/** Funciones de lectura admitidas en el mapa y la tabla que leen. */
const FC_LECTURA = { 1: 'coils', 2: 'discrete_inputs', 3: 'holding_registers', 4: 'input_registers' };
/** Maximo de variables en el mapa: acota el tiempo de un ciclo y el tamano del formulario. */
const MAX_VARIABLES = 64;
/** Nombres: los mismos caracteres que admiten las metricas Sparkplug B (I-06). */
const PATRON_NOMBRE = /^[A-Za-z0-9_][A-Za-z0-9_/.-]{0,63}$/;

/**
 * Entero en [min, max] a partir de un numero o texto (el Dashboard manda texto).
 * @returns {number|null} null si no es un entero valido en el rango
 */
function entero(valor, min, max) {
    const n = typeof valor === 'string' && valor.trim() !== '' ? Number(valor) : valor;
    return Number.isInteger(n) && n >= min && n <= max ? n : null;
}

/** Copia profunda de datos JSON. */
const clonar = (o) => JSON.parse(JSON.stringify(o));

/**
 * Valida y normaliza una configuracion completa.
 *
 * @param {object} cfg configuracion candidata (puede venir del Dashboard, con numeros como texto)
 * @returns {{ok: boolean, errores: string[], config: object|null}}
 *   config normalizada (numeros como numeros, campos opcionales completados) si ok
 */
function validar(cfg) {
    const errores = [];
    const err = (texto) => errores.push(texto);
    if (!cfg || typeof cfg !== 'object') return { ok: false, errores: ['configuracion vacia'], config: null };

    const p = cfg.puerto || {};
    const puerto = {
        tipo: TIPOS_PUERTO.includes(p.tipo) ? p.tipo : (err(`tipo de puerto invalido: ${p.tipo}`), 'serie'),
        ruta: typeof p.ruta === 'string' && /^[\w./:\\-]{1,128}$/.test(p.ruta) ? p.ruta
            : (err(`ruta de puerto invalida: ${p.ruta}`), ''),
        tcp: typeof p.tcp === 'string' && /^[\w.-]+:\d{1,5}$/.test(p.tcp) ? p.tcp
            : (p.tipo === 'tcp' ? (err(`direccion TCP invalida: ${p.tcp}`), '') : (p.tcp || '127.0.0.1:5020')),
        baud: entero(p.baud, 1200, 115200) ?? (err(`baud rate fuera de 1200-115200: ${p.baud}`), 0),
        bitsDatos: [7, 8].includes(entero(p.bitsDatos, 7, 8)) ? entero(p.bitsDatos, 7, 8)
            : (err(`bits de datos invalidos: ${p.bitsDatos}`), 8),
        paridad: PARIDADES.includes(p.paridad) ? p.paridad : (err(`paridad invalida: ${p.paridad}`), 'none'),
        bitsParada: [1, 2].includes(entero(p.bitsParada, 1, 2)) ? entero(p.bitsParada, 1, 2)
            : (err(`bits de parada invalidos: ${p.bitsParada}`), 1),
        esperaReconfiguracionMs: entero(p.esperaReconfiguracionMs ?? 300, 0, 5000)
            ?? (err('espera de reconfiguracion fuera de 0-5000 ms'), 300),
    };
    if (puerto.bitsDatos === 7) {
        // MODBus RTU exige 8 bits; 7 es del modo ASCII. Se admite solo para descartar que
        // el esclavo este mal configurado, y se avisa.
        errores.push('AVISO: MODBus RTU usa 8 bits de datos; con 7 solo funcionara un esclavo mal configurado');
    }

    const esclavo = { id: entero(cfg.esclavo && cfg.esclavo.id, 1, 247) ?? (err('Unit ID fuera de 1-247'), 1) };

    const s = cfg.sondeo || {};
    const sondeo = {
        periodoMs: entero(s.periodoMs, 50, 60000) ?? (err('periodo de sondeo fuera de 50-60000 ms'), 250),
        timeoutMs: entero(s.timeoutMs, 20, 5000) ?? (err('timeout fuera de 20-5000 ms'), 300),
        reintentos: entero(s.reintentos, 0, 10) ?? (err('reintentos fuera de 0-10'), 1),
        ausenciaMs: entero(s.ausenciaMs ?? 2000, 100, 60000) ?? (err('ausencia sostenida fuera de 100-60000 ms'), 2000),
    };

    const mapa = [];
    const nombres = new Set();
    if (!Array.isArray(cfg.mapa) || cfg.mapa.length === 0) err('el mapa de registros esta vacio');
    else if (cfg.mapa.length > MAX_VARIABLES) err(`el mapa admite hasta ${MAX_VARIABLES} variables`);
    else {
        cfg.mapa.forEach((v, i) => {
            const pos = `variable ${i + 1}`;
            if (!v || typeof v !== 'object') { err(`${pos}: invalida`); return; }
            const nombre = typeof v.nombre === 'string' ? v.nombre.trim() : '';
            if (!PATRON_NOMBRE.test(nombre)) { err(`${pos}: nombre invalido "${v.nombre}"`); return; }
            if (nombres.has(nombre)) { err(`${pos}: nombre repetido "${nombre}"`); return; }
            nombres.add(nombre);
            const fc = entero(v.fc, 1, 4);
            if (fc === null) { err(`${nombre}: codigo de funcion de lectura invalido (1-4): ${v.fc}`); return; }
            const direccion = entero(v.direccion, 0, 0xFFFF);
            if (direccion === null) { err(`${nombre}: direccion fuera de 0-65535`); return; }
            const tipo = v.tipo in TIPOS ? v.tipo : null;
            if (!tipo) { err(`${nombre}: tipo invalido "${v.tipo}"`); return; }
            const esBit = fc === 1 || fc === 2;
            if (esBit !== (tipo === 'bool')) { err(`${nombre}: FC ${fc} lee ${esBit ? 'bits' : 'registros'}; el tipo ${tipo} no corresponde`); return; }
            if (direccion + TIPOS[tipo] - 1 > 0xFFFF) { err(`${nombre}: el tipo ${tipo} pasa de la direccion 0xFFFF`); return; }
            const escritura = v.escritura === true || v.escritura === 'true';
            if (escritura && !(fc === 1 || (fc === 3 && TIPOS[tipo] === 1))) {
                err(`${nombre}: solo se escriben coils (FC 01 -> 05) o registros simples (FC 03 -> 06)`); return;
            }
            const orden = v.orden === 'CDAB' ? 'CDAB' : 'ABCD';
            const variable = { nombre, fc, direccion, tipo, escritura, orden };
            if (v.min !== undefined && v.min !== '' && v.min !== null) variable.min = Number(v.min);
            if (v.max !== undefined && v.max !== '' && v.max !== null) variable.max = Number(v.max);
            if ([variable.min, variable.max].some((x) => x !== undefined && !Number.isFinite(x))) {
                err(`${nombre}: min o max no numerico`); return;
            }
            if (variable.min !== undefined && variable.max !== undefined && variable.min > variable.max) {
                err(`${nombre}: min > max`); return;
            }
            mapa.push(variable);
        });
    }

    const derivadas = [];
    for (const d of Array.isArray(cfg.derivadas) ? cfg.derivadas : []) {
        if (d && PATRON_NOMBRE.test(d.nombre) && nombres.has(d.de) && Number.isFinite(Number(d.factor))
            && !nombres.has(d.nombre)) {
            derivadas.push({ nombre: d.nombre, de: d.de, factor: Number(d.factor),
                decimales: entero(d.decimales ?? 2, 0, 6) ?? 2 });
        }
        // Una derivada cuya fuente ya no existe (se quito del mapa) se descarta sin error:
        // es lo esperable al reconfigurar para el esclavo desconocido.
    }

    const de = cfg.descubrimiento || {};
    const combinaciones = (Array.isArray(de.combinaciones) ? de.combinaciones : [])
        .map((c) => ({ baud: entero(c && c.baud, 1200, 115200), paridad: c && c.paridad }))
        .filter((c) => c.baud !== null && PARIDADES.includes(c.paridad));
    const descubrimiento = {
        idDesde: entero(de.idDesde ?? 1, 1, 247) ?? 1,
        idHasta: entero(de.idHasta ?? 247, 1, 247) ?? 247,
        fc: entero(de.fc ?? 3, 1, 4) ?? 3,
        direccion: entero(de.direccion ?? 0, 0, 0xFFFF) ?? 0,
        timeoutMs: entero(de.timeoutMs ?? 60, 10, 2000) ?? 60,
        detenerEnPrimero: de.detenerEnPrimero !== false,
        combinaciones: combinaciones.length ? combinaciones : [{ baud: 19200, paridad: 'even' }, { baud: 9600, paridad: 'none' }],
    };
    if (descubrimiento.idDesde > descubrimiento.idHasta) err('descubrimiento: Unit ID inicial mayor que el final');

    const graves = errores.filter((e) => !e.startsWith('AVISO'));
    return {
        ok: graves.length === 0,
        errores,
        config: graves.length ? null : { version: 1, puerto, esclavo, sondeo, mapa, derivadas, descubrimiento },
    };
}

/**
 * Carga la configuracion: la del usuario si es valida, si no la de fabrica.
 *
 * @param {string} rutaUsuario archivo persistido por el Dashboard
 * @param {string} [rutaDefecto=RUTA_DEFECTO]
 * @returns {{config: object, origen: 'usuario'|'defecto', avisos: string[]}}
 * @throws {Error} solo si la configuracion de FABRICA es invalida (error del repositorio)
 */
function cargar(rutaUsuario, rutaDefecto = RUTA_DEFECTO) {
    const avisos = [];
    if (rutaUsuario && fs.existsSync(rutaUsuario)) {
        try {
            const r = validar(JSON.parse(fs.readFileSync(rutaUsuario, 'utf8')));
            if (r.ok) return { config: r.config, origen: 'usuario', avisos: r.errores };
            avisos.push(`configuracion guardada invalida, se usa la de fabrica: ${r.errores.join('; ')}`);
        } catch (e) {
            avisos.push(`no se pudo leer ${rutaUsuario}: ${e.message}; se usa la de fabrica`);
        }
    }
    const r = validar(JSON.parse(fs.readFileSync(rutaDefecto, 'utf8')));
    if (!r.ok) throw new Error(`config.default.json invalida: ${r.errores.join('; ')}`);
    return { config: r.config, origen: 'defecto', avisos: avisos.concat(r.errores) };
}

/**
 * Guarda la configuracion de forma atomica: escribe un temporal y lo renombra, para que un
 * corte de energia a mitad de la escritura no deje un archivo truncado.
 *
 * @param {string} ruta
 * @param {object} config ya validada
 * @returns {void}
 * @throws {Error} si la configuracion no es valida o no se puede escribir
 */
function guardar(ruta, config) {
    const r = validar(config);
    if (!r.ok) throw new Error(`no se guarda una configuracion invalida: ${r.errores.join('; ')}`);
    fs.mkdirSync(path.dirname(ruta), { recursive: true });
    const temporal = `${ruta}.${process.pid}.tmp`;
    fs.writeFileSync(temporal, JSON.stringify(r.config, null, 2) + '\n', 'utf8');
    fs.renameSync(temporal, ruta);
}

/**
 * Parametros del puerto en el formato del nodo "serial control" de node-red-node-serialport.
 * @param {object} puerto config.puerto
 * @returns {{serialport:string, serialbaud:number, databits:number, parity:string, stopbits:number}}
 */
function paraSerialControl(puerto) {
    return { serialport: puerto.ruta, serialbaud: puerto.baud, databits: puerto.bitsDatos,
        parity: puerto.paridad, stopbits: puerto.bitsParada };
}

/**
 * Diferencias entre dos configuraciones que obligan a reabrir el puerto.
 * @returns {boolean}
 */
function cambiaPuerto(a, b) {
    const k = ['tipo', 'ruta', 'tcp', 'baud', 'bitsDatos', 'paridad', 'bitsParada'];
    return k.some((c) => a.puerto[c] !== b.puerto[c]);
}

module.exports = {
    RUTA_DEFECTO, PARIDADES, TIPOS, FC_LECTURA, MAX_VARIABLES,
    validar, cargar, guardar, paraSerialControl, cambiaPuerto, clonar,
};
