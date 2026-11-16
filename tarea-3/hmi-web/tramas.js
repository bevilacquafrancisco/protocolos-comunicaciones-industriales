/**
 * tramas.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-16
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Decodificacion DIDACTICA de tramas para la Host Application (ADR-028), sin DOM ni red:
 *
 *   - CRC-16 MODBus paso a paso, para MOSTRAR la logica que implementan el maestro
 *     (edge-nodered/lib/modbus.js) y el esclavo (firmware/.../crc16.py). Este archivo no
 *     participa del enlace MODBus: I-01 exige el CRC propio en el maestro y en el esclavo, y
 *     eso no cambia. Aca se recalcula para verificar y explicar lo que llego por Sparkplug.
 *   - Decodificacion de una trama MODBus RTU (peticion o respuesta) campo por campo.
 *   - Segmentacion del formato binario Protobuf de un Payload Sparkplug B, byte a byte,
 *     con el nombre de cada campo de sparkplug_b.proto (la decodificacion de VALORES la hace
 *     protobuf.js en sparkplug.js; esto muestra COMO viajan los bytes).
 *   - Reconstruccion de la trama de escritura FC 05/06 de un comando (se rotula como
 *     reconstruida: no es una captura).
 *
 * Bloques de docs/diagramas/flujo-host-app.mmd: [DF-4.15] (decodificacion para la vista).
 * Se prueba en Node con node:test (test/tramas.test.js) y corre igual en el navegador.
 *
 * Dependencias externas: ninguna.
 */
(function (raiz, fabrica) {
    if (typeof module === 'object' && module.exports) module.exports = fabrica();
    else raiz.Tramas = fabrica();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // =========================================================================
    // Utilidades
    // =========================================================================

    /** @param {number} n @returns {string} dos digitos hexadecimales en mayuscula */
    const hex2 = (n) => (n & 0xFF).toString(16).toUpperCase().padStart(2, '0');

    /** @param {number} n @returns {string} cuatro digitos hexadecimales (16 bits) */
    const hex4 = (n) => (n & 0xFFFF).toString(16).toUpperCase().padStart(4, '0');

    /**
     * Convierte "01 03 00 00" (o "01030000") en bytes.
     * @param {string} texto
     * @returns {number[]} bytes; [] si el texto esta vacio o no es hexadecimal valido
     */
    function hexABytes(texto) {
        const limpio = String(texto || '').replace(/\s+/g, '');
        if (!limpio || limpio.length % 2 !== 0 || /[^0-9a-f]/i.test(limpio)) return [];
        const salida = [];
        for (let i = 0; i < limpio.length; i += 2) salida.push(parseInt(limpio.slice(i, i + 2), 16));
        return salida;
    }

    /** @param {ArrayLike<number>} bytes @returns {string} "01 03 00 00" */
    const bytesAHex = (bytes) => Array.from(bytes, hex2).join(' ');

    // =========================================================================
    // CRC-16 MODBus (logica, paso a paso)
    // =========================================================================

    /** Polinomio 0x8005 reflejado (los bits se procesan del menos significativo al mas). */
    const POLINOMIO = 0xA001;
    const INICIO = 0xFFFF;

    /**
     * CRC-16 MODBus de un conjunto de bytes.
     * @param {ArrayLike<number>} bytes
     * @returns {number} CRC de 16 bits (viaja byte bajo primero)
     */
    function crc16(bytes) {
        let crc = INICIO;
        for (const b of Array.from(bytes)) {
            crc ^= b;
            for (let k = 0; k < 8; k++) crc = (crc & 1) ? ((crc >>> 1) ^ POLINOMIO) : (crc >>> 1);
        }
        return crc;
    }

    /**
     * El calculo byte por byte, para mostrarlo (pestana MODBus, seccion CRC).
     * @param {ArrayLike<number>} bytes trama SIN el CRC
     * @returns {{pasos: Array<{indice:number, byte:string, antes:string, trasXor:string, despues:string,
     *            desplazamientos: Array<{n:number, lsb:number, accion:string, resultado:string}>}>,
     *            crc: number, enLinea: string}}
     */
    function crcPasoAPaso(bytes) {
        let crc = INICIO;
        const pasos = Array.from(bytes).map((b, indice) => {
            const antes = crc;
            crc ^= b;
            const trasXor = crc;
            const desplazamientos = [];
            for (let n = 1; n <= 8; n++) {
                const lsb = crc & 1;
                crc = lsb ? ((crc >>> 1) ^ POLINOMIO) : (crc >>> 1);
                desplazamientos.push({ n, lsb, accion: lsb ? 'desplazar y XOR 0xA001' : 'solo desplazar',
                    resultado: '0x' + hex4(crc) });
            }
            return { indice: indice + 1, byte: hex2(b), antes: '0x' + hex4(antes), trasXor: '0x' + hex4(trasXor),
                despues: '0x' + hex4(crc), desplazamientos };
        });
        return { pasos, crc, enLinea: `${hex2(crc & 0xFF)} ${hex2(crc >>> 8)}` };
    }

    /**
     * Verifica el CRC de una trama completa como lo hace el receptor: recalcula sobre los datos
     * y compara con los dos ultimos bytes. Propiedad util para la defensa: el CRC calculado
     * sobre la trama ENTERA (datos + CRC) da 0x0000 si llego sin errores.
     * @param {ArrayLike<number>} trama trama con CRC
     * @returns {{ok:boolean, calculado:string, recibido:string, residuo:string}|null} null si es muy corta
     */
    function verificarCrc(trama) {
        const b = Array.from(trama);
        if (b.length < 4) return null;
        const c = crc16(b.slice(0, -2));
        return { ok: (c & 0xFF) === b[b.length - 2] && (c >>> 8) === b[b.length - 1],
            calculado: `${hex2(c & 0xFF)} ${hex2(c >>> 8)}`, recibido: bytesAHex(b.slice(-2)),
            residuo: '0x' + hex4(crc16(b)) };
    }

    // =========================================================================
    // MODBus RTU: decodificacion campo por campo
    // =========================================================================

    const FUNCIONES = {
        1: 'Read Coils', 2: 'Read Discrete Inputs', 3: 'Read Holding Registers', 4: 'Read Input Registers',
        5: 'Write Single Coil', 6: 'Write Single Register', 15: 'Write Multiple Coils', 16: 'Write Multiple Registers',
    };
    const EXCEPCIONES = { 1: 'función ilegal', 2: 'dirección ilegal', 3: 'valor ilegal', 4: 'falla del esclavo' };
    /** Referencia MODBus clasica (base 1) de cada tabla, segun la FC. */
    const TABLA = { 1: [1, 'coil'], 5: [1, 'coil'], 15: [1, 'coil'], 2: [10001, 'entrada discreta'],
        4: [30001, 'registro de entrada'], 3: [40001, 'registro holding'], 6: [40001, 'registro holding'],
        16: [40001, 'registro holding'] };

    /**
     * Decodifica una trama MODBus RTU.
     * @param {ArrayLike<number>} trama bytes con CRC
     * @param {'peticion'|'respuesta'} rol
     * @param {function(number, number): ?string} [nombreDe] (fc, offset) -> nombre de la variable
     * @returns {{segmentos: Array<{h:string, tono:string, campo:string}>, filas: Array<{bytes:string,
     *            campo:string, significado:string}>, fc:?number, unidad:?number, crc:?object, excepcion:boolean}}
     */
    function decodificarModbus(trama, rol, nombreDe = () => null) {
        const b = Array.from(trama);
        const segmentos = [];
        const filas = [];
        const agregar = (desde, cantidad, tono, campo, significado) => {
            const trozo = b.slice(desde, desde + cantidad);
            for (const x of trozo) segmentos.push({ h: hex2(x), tono, campo });
            if (trozo.length) filas.push({ bytes: bytesAHex(trozo), campo, significado });
        };
        const crc = verificarCrc(b);
        if (b.length < 4 || !crc) return { segmentos, filas, fc: null, unidad: null, crc: null, excepcion: false };

        const unidad = b[0];
        const fcCruda = b[1];
        const excepcion = (fcCruda & 0x80) !== 0;
        const fc = fcCruda & 0x7F;
        const fin = b.length - 2;                       // indice del primer byte del CRC
        agregar(0, 1, 'addr', 'Dirección', unidad === 0 ? 'Difusión (0)' : `Esclavo con Unit ID ${unidad}`);
        agregar(1, 1, 'fc', 'Función', excepcion ? `FC ${hex2(fc)} con el bit 7 en 1: EXCEPCIÓN`
            : `FC ${hex2(fc)} · ${FUNCIONES[fc] || 'función no usada por el sistema'}`);

        const palabra = (i) => (b[i] << 8) | b[i + 1];
        const referencia = (offset) => {
            const t = TABLA[fc];
            const nombre = nombreDe(fc, offset);
            return `offset ${offset} (0x${hex4(offset)})${t ? ` → ${t[1]} ${t[0] + offset}` : ''}${nombre ? ` · ${nombre}` : ''}`;
        };

        if (excepcion) {
            agregar(2, 1, 'data', 'Código de excepción', `${hex2(b[2])} · ${EXCEPCIONES[b[2]] || 'código no estándar'}`);
        } else if (rol === 'peticion' && fc >= 1 && fc <= 4 && fin === 6) {
            agregar(2, 2, 'data', 'Dirección inicial', referencia(palabra(2)));
            agregar(4, 2, 'data2', 'Cantidad', `${palabra(4)} ${fc <= 2 ? 'bit(s)' : 'registro(s) de 16 bits'}`);
        } else if ((fc === 5 || fc === 6) && fin === 6) {
            agregar(2, 2, 'data', 'Dirección', referencia(palabra(2)));
            const v = palabra(4);
            agregar(4, 2, 'data2', 'Valor', fc === 5 ? (v === 0xFF00 ? 'FF00 = ENCENDER' : v === 0 ? '0000 = APAGAR' : 'valor inválido para FC 05')
                : `${v}${rol === 'respuesta' ? ' · la respuesta es el ECO de la petición' : ''}`);
        } else if (rol === 'respuesta' && fc >= 1 && fc <= 4) {
            const n = b[2];
            agregar(2, 1, 'data2', 'Cantidad de bytes', `${n} byte(s) de datos`);
            const datos = b.slice(3, fin);
            const sig = fc <= 2 ? `bits: ${datos.map((x) => x.toString(2).padStart(8, '0')).join(' ')} (bit 0 = primer elemento)`
                : datos.length === 2 ? `valor = ${palabra(3)} (byte alto primero)` : `${datos.length / 2} registro(s)`;
            agregar(3, fin - 3, 'data', 'Datos', sig);
        } else {
            agregar(2, fin - 2, 'data', 'Datos', 'formato no detallado');
        }
        agregar(fin, 2, 'crc', 'CRC-16', crc.ok ? `válido · byte bajo primero (residuo ${crc.residuo})`
            : `INVÁLIDO: calculado ${crc.calculado}, llegó ${crc.recibido}`);
        return { segmentos, filas, fc, unidad, crc, excepcion };
    }

    /**
     * Trama de escritura de un comando, RECONSTRUIDA en el navegador (no es una captura):
     * lo que el maestro transmite para Outputs/LedDigital (FC 05) u Outputs/LedPWM (FC 06).
     * @param {number} fc 5 o 6
     * @param {boolean|number} valor
     * @param {number} [unidad=1] Unit ID
     * @param {number} [offset=0]
     * @returns {number[]} trama con CRC
     */
    function tramaEscritura(fc, valor, unidad = 1, offset = 0) {
        const v = fc === 5 ? (valor ? 0xFF00 : 0) : Number(valor) & 0xFFFF;
        const cuerpo = [unidad, fc, offset >> 8, offset & 0xFF, v >> 8, v & 0xFF];
        const c = crc16(cuerpo);
        return cuerpo.concat([c & 0xFF, c >>> 8]);
    }

    // =========================================================================
    // Protobuf (formato de cable de un Payload Sparkplug B)
    // =========================================================================

    const CAMPOS_PAYLOAD = { 1: 'timestamp', 2: 'metric', 3: 'seq', 4: 'uuid', 5: 'body' };
    const CAMPOS_METRICA = { 1: 'name', 2: 'alias', 3: 'timestamp', 4: 'datatype', 5: 'is_historical',
        6: 'is_transient', 7: 'is_null', 8: 'metadata', 9: 'properties', 10: 'int_value', 11: 'long_value',
        12: 'float_value', 13: 'double_value', 14: 'boolean_value', 15: 'string_value', 16: 'bytes_value',
        17: 'dataset_value', 18: 'template_value', 19: 'extension_value' };
    /** Sparkplug 3.0 §6.4.16, enum DataType. */
    const TIPOS = { 1: 'Int8', 2: 'Int16', 3: 'Int32', 4: 'Int64', 5: 'UInt8', 6: 'UInt16', 7: 'UInt32', 8: 'UInt64',
        9: 'Float', 10: 'Double', 11: 'Boolean', 12: 'String', 13: 'DateTime', 14: 'Text' };
    const TONO = { timestamp: 'ts', seq: 'seq', alias: 'alias', datatype: 'dt', name: 'name' };

    /** Lee un varint desde i. @returns {{valor:number, fin:number}} (exacto hasta 2^53) */
    function leerVarint(b, i) {
        let valor = 0;
        let escala = 1;
        let j = i;
        for (;;) {
            if (j >= b.length) throw new RangeError('varint truncado');
            const x = b[j++];
            valor += (x & 0x7F) * escala;
            if (!(x & 0x80)) break;
            escala *= 128;
            if (j - i > 10) throw new RangeError('varint de más de 10 bytes');
        }
        return { valor, fin: j };
    }

    /**
     * Segmenta un Payload Sparkplug B en sus campos Protobuf, byte por byte.
     * @param {ArrayLike<number>} bytes payload binario
     * @param {function(number): ?string} [nombreAlias] alias -> nombre de la metrica (del BIRTH)
     * @returns {{segmentos: Array<{h:string, tono:string, campo:string}>, filas: Array<{bytes:string,
     *            campo:string}>, completo:boolean}}
     */
    function segmentarPayload(bytes, nombreAlias = () => null) {
        const b = Array.from(bytes);
        const segmentos = [];
        const marcar = (desde, hasta, tono, campo) => {
            for (let k = desde; k < hasta; k++) segmentos.push({ h: hex2(b[k]), tono, campo });
        };
        let completo = true;

        /** Recorre un mensaje entre [i, fin): campos del Payload (nivel 0) o de una Metric (nivel 1). */
        function recorrer(i, fin, nivel, prefijo) {
            let tipoDato = null;
            while (i < fin) {
                const tag = leerVarint(b, i);
                const numero = Math.floor(tag.valor / 8);
                const cable = tag.valor % 8;
                const nombres = nivel === 0 ? CAMPOS_PAYLOAD : CAMPOS_METRICA;
                const nombre = nombres[numero] || `campo ${numero}`;
                marcar(i, tag.fin, 'tag', `${prefijo}tag: campo ${numero} (${nombre}), tipo de cable ${cable}`);
                i = tag.fin;
                if (cable === 0) {                                          // varint
                    const v = leerVarint(b, i);
                    let texto = `${prefijo}${nombre} = ${v.valor}`;
                    if (nombre === 'datatype') { tipoDato = TIPOS[v.valor]; texto += ` (${tipoDato || '?'})`; }
                    if (nombre === 'alias') { const n = nombreAlias(v.valor); if (n) texto += ` → ${n}`; }
                    if (nombre === 'boolean_value') texto = `${prefijo}boolean_value = ${v.valor === 1}`;
                    if (nombre === 'timestamp') texto += ` ms (${new Date(v.valor).toISOString().slice(11, 23)} UTC)`;
                    marcar(i, v.fin, TONO[nombre] || 'val', texto);
                    i = v.fin;
                } else if (cable === 2) {                                   // longitud + bytes
                    const l = leerVarint(b, i);
                    const desde = l.fin;
                    const hasta = desde + l.valor;
                    if (hasta > fin) throw new RangeError('longitud fuera del mensaje');
                    if (nivel === 0 && numero === 2) {
                        marcar(i, l.fin, 'tag', `${prefijo}longitud de la métrica: ${l.valor} B`);
                        recorrer(desde, hasta, 1, '· ');
                    } else {
                        marcar(i, l.fin, 'tag', `${prefijo}longitud: ${l.valor} B`);
                        let texto = `${prefijo}${nombre}`;
                        if (nombre === 'name' || nombre === 'string_value' || nombre === 'uuid') {
                            texto += ` = «${new TextDecoder().decode(new Uint8Array(b.slice(desde, hasta)))}»`;
                        }
                        marcar(desde, hasta, nombre === 'name' ? 'name' : 'val', texto);
                    }
                    i = hasta;
                } else if (cable === 5) {                                   // 32 bits (float)
                    const dv = new DataView(new Uint8Array(b.slice(i, i + 4)).buffer);
                    marcar(i, i + 4, 'val', `${prefijo}${nombre} = ${Math.round(dv.getFloat32(0, true) * 1000) / 1000} (IEEE 754, little endian)`);
                    i += 4;
                } else if (cable === 1) {                                   // 64 bits (double)
                    const dv = new DataView(new Uint8Array(b.slice(i, i + 8)).buffer);
                    marcar(i, i + 8, 'val', `${prefijo}${nombre} = ${dv.getFloat64(0, true)}`);
                    i += 8;
                } else {
                    throw new RangeError(`tipo de cable ${cable} no soportado`);
                }
            }
        }

        try {
            recorrer(0, b.length, 0, '');
        } catch (e) {
            completo = false;
            const hechos = segmentos.length;
            marcar(hechos, b.length, 'tag', `sin decodificar (${e.message})`);
        }
        // Filas: bytes consecutivos con el mismo rotulo
        const filas = [];
        for (const s of segmentos) {
            const ultima = filas[filas.length - 1];
            if (ultima && ultima.campo === s.campo) ultima.bytes += ' ' + s.h;
            else filas.push({ bytes: s.h, campo: s.campo });
        }
        return { segmentos, filas, completo };
    }

    return Object.freeze({ hex2, hex4, hexABytes, bytesAHex, crc16, crcPasoAPaso, verificarCrc,
        decodificarModbus, tramaEscritura, segmentarPayload, FUNCIONES, EXCEPCIONES, TIPOS });
}));
