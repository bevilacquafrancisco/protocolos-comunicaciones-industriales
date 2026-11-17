/**
 * modelo.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-16
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Datos ESTATICOS que la Host Application explica en sus pestanas MODBus, OPC UA y Sparkplug B:
 * mapa de registros, metricas con su alias y su NodeId, nodos del espacio de direcciones con
 * su acceso, y tipos de mensaje.
 *
 * Fuente de verdad: docs/diccionario-de-datos.md (I-06) y docs/opcua-espacio-direcciones.md
 * (verificado contra el servidor real con tools/verificar_opcua.js). Esta copia existe porque
 * la pagina es estatica y no puede leer el Markdown; test/modelo.test.js FALLA si se aparta del
 * diccionario o de la verificacion, asi que no puede desactualizarse en silencio.
 *
 * Los VALORES vivos no estan aca: llegan por Sparkplug B (sparkplug.js).
 *
 * Dependencias externas: ninguna.
 */
(function (raiz, fabrica) {
    if (typeof module === 'object' && module.exports) module.exports = fabrica();
    else raiz.Modelo = fabrica();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    /** Diccionario §1: cada E/S del dispositivo 1 en la capa MODBus. */
    const MAPA_MODBUS = Object.freeze([
        { metrica: 'Inputs/Pulsador', senal: 'Pulsador · GPIO 18', tabla: 'Discrete Input', referencia: '10001',
            offset: 0, fcLectura: 2, fcEscritura: null, tipo: 'bit', rango: '0 · 1' },
        { metrica: 'Inputs/Potenciometro', senal: 'Potenciómetro · GPIO 34', tabla: 'Input Register', referencia: '30001',
            offset: 0, fcLectura: 4, fcEscritura: null, tipo: 'word 16 bits', rango: '0 – 4095' },
        { metrica: 'Outputs/LedDigital', senal: 'LED digital · GPIO 19', tabla: 'Coil', referencia: '00001',
            offset: 0, fcLectura: 1, fcEscritura: 5, tipo: 'bit', rango: '0 · 1' },
        { metrica: 'Outputs/LedPWM', senal: 'LED PWM · GPIO 21', tabla: 'Holding Register', referencia: '40001',
            offset: 0, fcLectura: 3, fcEscritura: 6, tipo: 'word 16 bits', rango: '0 – 255 (más → excepción 03)' },
    ]);

    /** Diccionario §1 y §2: metricas Sparkplug con su alias, tipo y NodeId OPC UA de origen. */
    const METRICAS = Object.freeze([
        { nombre: 'Inputs/Pulsador', alias: 101, tipo: 'Boolean', ambito: 'dispositivo', nodeId: 'ns=1;s=Dispositivo1.Inputs.Pulsador' },
        { nombre: 'Inputs/Potenciometro', alias: 102, tipo: 'UInt16', ambito: 'dispositivo', nodeId: 'ns=1;s=Dispositivo1.Inputs.Potenciometro' },
        { nombre: 'Outputs/LedDigital', alias: 103, tipo: 'Boolean', ambito: 'dispositivo', nodeId: 'ns=1;s=Dispositivo1.Outputs.LedDigital' },
        { nombre: 'Outputs/LedPWM', alias: 104, tipo: 'UInt16', ambito: 'dispositivo', nodeId: 'ns=1;s=Dispositivo1.Outputs.LedPWM' },
        { nombre: 'Inputs/Potenciometro_pct', alias: 105, tipo: 'Float', ambito: 'dispositivo', nodeId: 'ns=1;s=Dispositivo1.Inputs.Potenciometro_pct' },
        { nombre: 'bdSeq', alias: null, tipo: 'Int64', ambito: 'nodo', nodeId: null },
        { nombre: 'Node Control/Rebirth', alias: null, tipo: 'Boolean', ambito: 'nodo', nodeId: null },
        { nombre: 'Status/MODBUS/Estado', alias: 10, tipo: 'String', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.Estado' },
        { nombre: 'Status/MODBUS/OK', alias: 11, tipo: 'UInt32', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.OK' },
        { nombre: 'Status/MODBUS/CRC_ERROR', alias: 12, tipo: 'UInt32', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.CRC_ERROR' },
        { nombre: 'Status/MODBUS/TIMEOUT', alias: 13, tipo: 'UInt32', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.TIMEOUT' },
        { nombre: 'Status/MODBUS/EXCEPTION', alias: 14, tipo: 'UInt32', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.EXCEPTION' },
        { nombre: 'Status/MODBUS/UltimaTramaTx', alias: 15, tipo: 'String', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.UltimaTramaTx' },
        { nombre: 'Status/MODBUS/UltimaTramaRx', alias: 16, tipo: 'String', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.UltimaTramaRx' },
        { nombre: 'Status/MODBUS/LatenciaMs', alias: 17, tipo: 'UInt16', ambito: 'nodo', nodeId: 'ns=1;s=Status.MODBUS.LatenciaMs' },
        { nombre: 'Status/OPCUA/Estado', alias: 20, tipo: 'String', ambito: 'nodo', nodeId: null },
        { nombre: 'Status/MQTT/Reconexiones', alias: 30, tipo: 'UInt32', ambito: 'nodo', nodeId: null },
        { nombre: 'Status/Sparkplug/Rebirths', alias: 40, tipo: 'UInt32', ambito: 'nodo', nodeId: null },
    ]);

    /**
     * Variables del espacio de direcciones (docs/opcua-espacio-direcciones.md, verificado).
     * acceso: 'R' = CurrentRead; 'RW' = CurrentRead + CurrentWrite (solo con el usuario operador:
     * el anonimo lee, ADR-009). metrica: la metrica Sparkplug que trae su valor (o null).
     */
    const VARIABLES_OPCUA = Object.freeze([
        { id: 'Dispositivo1.Inputs.Pulsador', tipo: 'Boolean', acceso: 'R', euRange: '—', metrica: 'Inputs/Pulsador' },
        { id: 'Dispositivo1.Inputs.Potenciometro', tipo: 'UInt16', acceso: 'R', euRange: '0 … 4095', metrica: 'Inputs/Potenciometro' },
        { id: 'Dispositivo1.Inputs.Potenciometro_pct', tipo: 'Float', acceso: 'R', euRange: '0 … 100', metrica: 'Inputs/Potenciometro_pct' },
        { id: 'Dispositivo1.Outputs.LedDigital', tipo: 'Boolean', acceso: 'RW', euRange: '—', metrica: 'Outputs/LedDigital' },
        { id: 'Dispositivo1.Outputs.LedPWM', tipo: 'UInt16', acceso: 'RW', euRange: '0 … 255', metrica: 'Outputs/LedPWM' },
        { id: 'Status.MODBUS.Estado', tipo: 'String', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/Estado' },
        { id: 'Status.MODBUS.OK', tipo: 'UInt32', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/OK' },
        { id: 'Status.MODBUS.CRC_ERROR', tipo: 'UInt32', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/CRC_ERROR' },
        { id: 'Status.MODBUS.TIMEOUT', tipo: 'UInt32', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/TIMEOUT' },
        { id: 'Status.MODBUS.EXCEPTION', tipo: 'UInt32', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/EXCEPTION' },
        { id: 'Status.MODBUS.UltimaTramaTx', tipo: 'String', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/UltimaTramaTx' },
        { id: 'Status.MODBUS.UltimaTramaRx', tipo: 'String', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/UltimaTramaRx' },
        { id: 'Status.MODBUS.LatenciaMs', tipo: 'UInt16', acceso: 'R', euRange: '—', metrica: 'Status/MODBUS/LatenciaMs' },
        // Existe en el servidor, pero la metrica Status/OPCUA/Estado la calcula el dispositivo 3 (diccionario §2)
        { id: 'Status.OPCUA.Estado', tipo: 'String', acceso: 'R', euRange: '—', metrica: 'Status/OPCUA/Estado' },
    ]);

    /** Objetos verificados (NodeId conocido) y el arbol que se dibuja. */
    const ARBOL = Object.freeze([
        { id: 'Objects', etiqueta: 'Objects', nivel: 0, nodeId: 'i=85' },
        { id: 'Dispositivo1', etiqueta: 'Dispositivo1', nivel: 1, nodeId: null },
        { id: 'Dispositivo1.Inputs', etiqueta: 'Inputs', nivel: 2, nodeId: 'ns=1;s=Dispositivo1.Inputs' },
        { id: 'Dispositivo1.Inputs.Pulsador', nivel: 3 }, { id: 'Dispositivo1.Inputs.Potenciometro', nivel: 3 },
        { id: 'Dispositivo1.Inputs.Potenciometro_pct', nivel: 3 },
        { id: 'Dispositivo1.Outputs', etiqueta: 'Outputs', nivel: 2, nodeId: 'ns=1;s=Dispositivo1.Outputs' },
        { id: 'Dispositivo1.Outputs.LedDigital', nivel: 3 }, { id: 'Dispositivo1.Outputs.LedPWM', nivel: 3 },
        { id: 'Dispositivo1.Status', etiqueta: 'Status', nivel: 2, nodeId: 'ns=1;s=Dispositivo1.Status' },
        { id: 'Status.MODBUS', etiqueta: 'MODBUS', nivel: 3, nodeId: 'ns=1;s=Status.MODBUS' },
        { id: 'Status.MODBUS.Estado', nivel: 4 }, { id: 'Status.MODBUS.OK', nivel: 4 }, { id: 'Status.MODBUS.CRC_ERROR', nivel: 4 },
        { id: 'Status.MODBUS.TIMEOUT', nivel: 4 }, { id: 'Status.MODBUS.EXCEPTION', nivel: 4 },
        { id: 'Status.MODBUS.UltimaTramaTx', nivel: 4 }, { id: 'Status.MODBUS.UltimaTramaRx', nivel: 4 },
        { id: 'Status.MODBUS.LatenciaMs', nivel: 4 },
        { id: 'Status.OPCUA', etiqueta: 'OPCUA', nivel: 3, nodeId: 'ns=1;s=Status.OPCUA' },
        { id: 'Status.OPCUA.Estado', nivel: 4 },
        { id: 'Dispositivo1.Mapa', etiqueta: 'Mapa', nivel: 2, nodeId: 'ns=1;s=Dispositivo1.Mapa' },
    ]);

    /** Tipos de mensaje Sparkplug B y quien los publica en este sistema. */
    const TIPOS_MENSAJE = Object.freeze([
        ['NBIRTH', 'Edge Node', 'Al conectarse o ante un Rebirth (seq 0, bdSeq)'],
        ['DBIRTH', 'Edge Node', 'Cuando el dispositivo 1 está disponible'],
        ['NDATA', 'Edge Node', 'Contadores y diagnóstico, agrupados a 1 Hz'],
        ['DDATA', 'Edge Node', 'Solo cuando cambia una E/S'],
        ['NDEATH', 'Broker (Last Will)', 'Si el Edge Node muere o pierde internet'],
        ['DDEATH', 'Edge Node', 'Si el esclavo no responde por 2 s'],
        ['NCMD', 'Host Application', 'Pedido de Rebirth'],
        ['DCMD', 'Host Application', 'Comandos del LED y del PWM'],
        ['STATE', 'Host Application', 'online / offline, retenido (JSON)'],
    ].map(([tipo, quien, cuando]) => Object.freeze({ tipo, quien, cuando })));

    /** NodeId de la metrica (o null) y nombre de la variable MODBus de (fc, offset). */
    const nodeIdDe = (nombre) => (METRICAS.find((m) => m.nombre === nombre) || {}).nodeId || null;
    function variableModbus(fc, offset) {
        const v = MAPA_MODBUS.find((x) => x.offset === offset && (x.fcLectura === fc || x.fcEscritura === fc));
        return v ? v.metrica : null;
    }

    return Object.freeze({ MAPA_MODBUS, METRICAS, VARIABLES_OPCUA, ARBOL, TIPOS_MENSAJE, nodeIdDe, variableModbus });
}));
