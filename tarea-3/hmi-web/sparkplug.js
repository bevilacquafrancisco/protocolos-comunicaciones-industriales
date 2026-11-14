/**
 * sparkplug.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-12
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Nucleo de la Host Application Sparkplug B 3.0, SIN DOM y SIN MQTT (mismo criterio que
 * ciclo_vida.py del dispositivo 3, ADR-020): cada mensaje entra por procesar() y sale el estado
 * nuevo mas lo que hay que publicar (Rebirth). app.js solo dibuja y mueve bytes. Se prueba en
 * Node con node:test (test/sparkplug.test.js) y corre igual en el navegador.
 *
 * Bloques de docs/diagramas/flujo-host-app.mmd: [DF-4.x] en cada funcion.
 *
 * La regla central de Sparkplug (y de la defensa): una metrica solo es VALIDA si llego en un
 * BIRTH de la sesion vigente, o en un DATA posterior a ese BIRTH. Por eso cada metrica tiene
 * vigencia:
 *     EN LÍNEA     llego en el BIRTH vigente (o en un DATA posterior)
 *     OBSOLETO     hubo NDEATH / DDEATH (o la web perdio el broker): el valor es el ULTIMO
 *                  conocido, no el actual
 *     DESCONOCIDO  no hay BIRTH en esta sesion: no se muestra como valido
 *
 * Dependencias externas: protobuf.js 8.8.1 (se inyecta: window.protobuf o require('protobufjs')).
 */
(function (raiz, fabrica) {
    if (typeof module === 'object' && module.exports) module.exports = fabrica();
    else raiz.Sparkplug = fabrica();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const NAMESPACE = 'spBv1.0';
    const VIGENCIA = Object.freeze({ EN_LINEA: 'EN LÍNEA', OBSOLETO: 'OBSOLETO', DESCONOCIDO: 'DESCONOCIDO' });
    const REBIRTH = 'Node Control/Rebirth';

    // Sparkplug 3.0 §6.4.16: campo protobuf y rango de cada tipo entero (UInt32 va en intValue).
    const ENTEROS = {
        Int8: [-128, 127, 'intValue', 32], Int16: [-32768, 32767, 'intValue', 32],
        Int32: [-2147483648, 2147483647, 'intValue', 32], UInt8: [0, 255, 'intValue', 32],
        UInt16: [0, 65535, 'intValue', 32], UInt32: [0, 4294967295, 'intValue', 32],
        Int64: [Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, 'longValue', 64],
        UInt64: [0, Number.MAX_SAFE_INTEGER, 'longValue', 64],
    };
    const OTROS = { Boolean: 'booleanValue', Float: 'floatValue', Double: 'doubleValue', String: 'stringValue', Text: 'stringValue' };

    // =========================================================================
    // Topicos
    // =========================================================================

    /**
     * Descompone un topico Sparkplug.
     * @param {string} topico
     * @returns {{tipo:string, grupo:?string, nodo:?string, dispositivo:?string, host:?string}|null}
     */
    function analizarTopico(topico) {
        const p = String(topico).split('/');
        if (p.length === 3 && p[0] === NAMESPACE && p[1] === 'STATE') {
            return { tipo: 'STATE', host: p[2], grupo: null, nodo: null, dispositivo: null };
        }
        if (p[0] !== NAMESPACE) return null;
        if (p.length === 4 && ['NBIRTH', 'NDATA', 'NDEATH', 'NCMD'].includes(p[2])) {
            return { tipo: p[2], grupo: p[1], nodo: p[3], dispositivo: null, host: null };
        }
        if (p.length === 5 && ['DBIRTH', 'DDATA', 'DDEATH', 'DCMD'].includes(p[2])) {
            return { tipo: p[2], grupo: p[1], nodo: p[3], dispositivo: p[4], host: null };
        }
        return null;
    }

    // =========================================================================
    // Codec Protobuf (I-02: nunca JSON propio)
    // =========================================================================

    /**
     * [DF-4.1] Crea el codec a partir del sparkplug_b.proto oficial.
     * @param {object} protobuf  modulo protobuf.js (build completo, con parser)
     * @param {string} textoProto contenido de sparkplug_b.proto
     * @returns {{decodificar: function(Uint8Array): object, codificar: function(object): Uint8Array,
     *            valor: function(object, string): *}}
     * @throws {Error} si el .proto no tiene el tipo Payload
     */
    function crearCodec(protobuf, textoProto) {
        const raizProto = protobuf.parse(textoProto, { keepCase: false }).root;
        const Payload = raizProto.lookupType('org.eclipse.tahu.protobuf.Payload');
        const NUMERO = raizProto.lookupEnum('org.eclipse.tahu.protobuf.DataType').values;   // nombre -> numero
        const NOMBRE = Object.fromEntries(Object.entries(NUMERO).map(([k, v]) => [v, k]));

        /** Valor Python-equivalente de una metrica decodificada, segun su tipo. */
        function valor(m, tipo) {
            if (m.isNull) return null;
            if (ENTEROS[tipo]) {
                const [, , campo, bits] = ENTEROS[tipo];
                let v = m[campo];
                if (v === undefined) throw new Error(`${tipo} sin ${campo}`);
                v = Number(v);
                if (tipo.startsWith('Int') && bits === 32 && v > 2147483647) v -= 4294967296;   // complemento a 2
                if (tipo === 'Int64' && v > Number.MAX_SAFE_INTEGER) v -= 18446744073709551616;
                return v;
            }
            const campo = OTROS[tipo];
            if (!campo || m[campo] === undefined) throw new Error(`metrica ${tipo} sin ${campo}`);
            return m[campo];
        }

        /**
         * @param {Uint8Array} bytes
         * @returns {{timestamp:?number, seq:?number, metricas:Array<{nombre:?string, alias:?number, tipo:?string, timestamp:?number, crudo:object}>}}
         * @throws {Error} si no es un Payload Protobuf valido
         */
        function decodificar(bytes) {
            const p = Payload.toObject(Payload.decode(bytes), { longs: Number, defaults: false });
            return {
                timestamp: p.timestamp ?? null,
                seq: p.seq ?? null,
                metricas: (p.metrics || []).map((m) => ({
                    nombre: m.name ?? null, alias: m.alias ?? null,
                    tipo: m.datatype != null ? NOMBRE[m.datatype] : null,
                    timestamp: m.timestamp ?? null, crudo: m,
                })),
            };
        }

        /**
         * Payload para un NCMD/DCMD: timestamp obligatorio, SIN seq (payloads-ncmd-seq). El seq
         * opcional existe solo para que las pruebas armen BIRTH y DATA; la web nunca lo usa.
         * @param {{timestamp:number, seq?:number, metricas:Array<{nombre?:string, alias?:number, tipo:string, valor:*}>}} p
         * @returns {Uint8Array}
         * @throws {RangeError|TypeError} valor fuera del tipo
         */
        function codificar({ timestamp, seq, metricas }) {
            const obj = { timestamp, metrics: metricas.map((m) => {
                const salida = { datatype: NUMERO[m.tipo], timestamp };
                if (m.nombre) salida.name = m.nombre;
                if (m.alias != null) salida.alias = m.alias;
                if (ENTEROS[m.tipo]) {
                    const [min, max, campo] = ENTEROS[m.tipo];
                    if (!Number.isInteger(m.valor) || m.valor < min || m.valor > max) {
                        throw new RangeError(`${m.valor} fuera de ${m.tipo} [${min}, ${max}]`);
                    }
                    salida[campo] = m.valor < 0 ? m.valor + (campo === 'intValue' ? 4294967296 : 0) : m.valor;
                } else if (m.tipo === 'Boolean') {
                    if (typeof m.valor !== 'boolean') throw new TypeError('Boolean espera true/false');
                    salida.booleanValue = m.valor;
                } else if (OTROS[m.tipo]) {
                    salida[OTROS[m.tipo]] = m.valor;
                } else {
                    throw new TypeError(`tipo no soportado: ${m.tipo}`);
                }
                return salida;
            }) };
            if (seq !== undefined && seq !== null) obj.seq = seq;
            return Payload.encode(Payload.fromObject(obj)).finish();
        }

        return { decodificar, codificar, valor };
    }

    // =========================================================================
    // Host Application
    // =========================================================================

    /**
     * Estado de la Host Application para UN Edge Node con UN dispositivo.
     *
     * Atributos principales:
     *   nodo / disp: {estado, metricas: Map<nombre, {valor, tipo, alias, ts, vigencia}>}
     *   nodo.bdSeq, nodo.seq: de la sesion vigente
     *   rebirthsSolicitados: Rebirth pedidos POR ESTA WEB
     *   comandos: Map<nombre, {valor, estado: 'enviado'|'confirmado'|'sin confirmar', t}>
     */
    class HostSparkplug {
        /**
         * @param {object} o
         * @param {object} o.codec  crearCodec(...)
         * @param {string} o.grupo, o.nodo, o.dispositivo, o.hostId  identificadores (diccionario §4)
         * @param {function(): number} [o.ahora]  ms UTC (inyectable en las pruebas)
         * @param {number} [o.esperaRebirthMs=5000]  minimo entre dos Rebirth (evita tormentas)
         * @param {number} [o.esperaConfirmacionMs=5000]  sin DDATA de confirmacion -> 'sin confirmar'
         */
        constructor({ codec, grupo, nodo, dispositivo, hostId, ahora = () => Date.now(),
            esperaRebirthMs = 5000, esperaConfirmacionMs = 5000 }) {
            this.codec = codec;
            this.ids = { grupo, nodo, dispositivo, hostId };
            this.ahora = ahora;
            this.esperaRebirthMs = esperaRebirthMs;
            this.esperaConfirmacionMs = esperaConfirmacionMs;
            this.nodo = { estado: VIGENCIA.DESCONOCIDO, bdSeq: null, seq: null, metricas: new Map() };
            this.disp = { estado: VIGENCIA.DESCONOCIDO, metricas: new Map() };
            this.alias = new Map();          // alias -> {ambito, nombre} (unicos en todo el nodo)
            this.rebirthsSolicitados = 0;
            this._ultimoRebirth = -Infinity;
            this.comandos = new Map();
            this.topicos = {
                ncmd: `${NAMESPACE}/${grupo}/NCMD/${nodo}`,
                dcmd: `${NAMESPACE}/${grupo}/DCMD/${nodo}/${dispositivo}`,
                state: `${NAMESPACE}/STATE/${hostId}`,
                suscripcion: `${NAMESPACE}/${grupo}/#`,
            };
        }

        // --------------------------------------------------------------- utilidades
        _marcar(destino, vigencia) {
            destino.estado = vigencia;
            for (const m of destino.metricas.values()) m.vigencia = vigencia;
        }

        _cargarBirth(destino, ambito, metricas, tsPayload) {
            destino.metricas = new Map();
            for (const [alias, a] of [...this.alias]) if (a.ambito === ambito) this.alias.delete(alias);
            for (const m of metricas) {
                if (!m.nombre || !m.tipo) continue;          // un BIRTH trae nombre y tipo (payloads-alias-birth-requirement)
                destino.metricas.set(m.nombre, { valor: this.codec.valor(m.crudo, m.tipo), tipo: m.tipo, alias: m.alias,
                    ts: m.timestamp ?? tsPayload, vigencia: VIGENCIA.EN_LINEA });
                if (m.alias != null) this.alias.set(m.alias, { ambito, nombre: m.nombre });
            }
            destino.estado = VIGENCIA.EN_LINEA;
        }

        /** [DF-4.12] Aplica un DATA: resuelve alias; un alias sin BIRTH es dato sin respaldo -> Rebirth. */
        _aplicarData(destino, ambito, metricas, tsPayload, r) {
            for (const m of metricas) {
                const a = m.alias != null ? this.alias.get(m.alias) : null;
                const nombre = a ? a.nombre : m.nombre;
                const def = nombre ? destino.metricas.get(nombre) : null;
                if (!def || (a && a.ambito !== ambito)) {
                    this._pedirRebirth(r, `métrica sin BIRTH (alias ${m.alias ?? '-'}, nombre ${m.nombre ?? '-'})`);
                    continue;
                }
                def.valor = this.codec.valor(m.crudo, m.tipo || def.tipo);
                def.ts = m.timestamp ?? tsPayload;
                def.vigencia = VIGENCIA.EN_LINEA;
                this._confirmar(nombre, def.valor, r);
            }
        }

        _confirmar(nombre, valor, r) {
            const c = this.comandos.get(nombre);
            if (c && c.estado === 'enviado' && c.valor === valor) {
                c.estado = 'confirmado';
                r.eventos.push({ nivel: 'info', texto: `Comando ${nombre} = ${valor} CONFIRMADO (${this.ahora() - c.t} ms)` });
            }
        }

        _comandosSinConfirmar(r, motivo) {
            for (const [nombre, c] of this.comandos) {
                if (c.estado === 'enviado') {
                    c.estado = 'sin confirmar';
                    r.eventos.push({ nivel: 'aviso', texto: `Comando ${nombre} = ${c.valor} SIN CONFIRMAR (${motivo})` });
                }
            }
        }

        /** [DF-4.11] NCMD Node Control/Rebirth = true, con un minimo de esperaRebirthMs entre pedidos. */
        _pedirRebirth(r, motivo) {
            const t = this.ahora();
            if (t - this._ultimoRebirth < this.esperaRebirthMs) {
                // 'info': es la limitacion funcionando (esperado); el banner queda para la causa real.
                r.eventos.push({ nivel: 'info', texto: `${motivo} — Rebirth ya pedido hace ${t - this._ultimoRebirth} ms, se espera` });
                return;
            }
            this._ultimoRebirth = t;
            this.rebirthsSolicitados += 1;
            r.publicar.push({ topico: this.topicos.ncmd, qos: 0, retener: false,
                bytes: this.codec.codificar({ timestamp: t, metricas: [{ nombre: REBIRTH, tipo: 'Boolean', valor: true }] }) });
            r.eventos.push({ nivel: 'aviso', texto: `${motivo} → NCMD Rebirth solicitado (#${this.rebirthsSolicitados})` });
        }

        // --------------------------------------------------------------- API
        /**
         * [DF-4.4/4.5/4.6] Procesa un mensaje: parte el topico, decodifica y despacha por tipo.
         * @param {string} topico
         * @param {Uint8Array} bytes
         * @param {boolean} [retenido=false]
         * @returns {{eventos: Array<{nivel:string, texto:string}>, publicar: Array<object>, state: ?object, tipo: ?string}}
         */
        procesar(topico, bytes, retenido = false) {
            const r = { eventos: [], publicar: [], state: null, tipo: null };
            const t = analizarTopico(topico);
            if (!t) return r;
            r.tipo = t.tipo;
            if (t.tipo === 'STATE') {
                if (t.host === this.ids.hostId) {
                    try {
                        const s = JSON.parse(new TextDecoder().decode(bytes));
                        r.state = s;
                        r.eventos.push({ nivel: 'info', texto: `STATE ${s.online ? 'online' : 'offline'}${retenido ? ' (retenido)' : ''}` });
                    } catch (e) { /* STATE ajeno o roto: se ignora */ }
                }
                return r;
            }
            if (t.grupo !== this.ids.grupo || t.nodo !== this.ids.nodo) return r;   // otro Edge Node del grupo
            if (t.dispositivo && t.dispositivo !== this.ids.dispositivo) return r;
            let p;
            try {
                p = this.codec.decodificar(bytes);
            } catch (e) {
                r.eventos.push({ nivel: 'error', texto: `${t.tipo}: payload Protobuf inválido (${e.message})` });
                return r;
            }

            if (t.tipo === 'NCMD' || t.tipo === 'DCMD') {           // comandos (de esta web o de otra)
                const lista = p.metricas.map((m) => (m.nombre || (this.alias.get(m.alias) || {}).nombre || `alias ${m.alias}`)
                    + ' = ' + this.codec.valor(m.crudo, m.tipo)).join(', ');
                r.eventos.push({ nivel: 'info', texto: `${t.tipo} ${lista}` });
                return r;
            }

            if (t.tipo === 'NBIRTH') {                                // [DF-4.7]
                const bd = p.metricas.find((m) => m.nombre === 'bdSeq');
                this.nodo.bdSeq = bd ? this.codec.valor(bd.crudo, 'Int64') : null;
                this.nodo.seq = p.seq;
                this._cargarBirth(this.nodo, 'nodo', p.metricas, p.timestamp);
                this._marcar(this.disp, VIGENCIA.DESCONOCIDO);    // espera su DBIRTH de esta sesion
                r.eventos.push({ nivel: p.seq === 0 ? 'info' : 'aviso',
                    texto: `NBIRTH bdSeq=${this.nodo.bdSeq} seq=${p.seq}${p.seq === 0 ? '' : ' (debía ser 0)'}` });
                return r;
            }

            if (t.tipo === 'NDEATH') {                                // [DF-4.8]
                const bd = p.metricas.find((m) => m.nombre === 'bdSeq');
                const valorBd = bd ? this.codec.valor(bd.crudo, 'Int64') : null;
                if (this.nodo.bdSeq === null || valorBd !== this.nodo.bdSeq) {
                    // Un Will de una sesion anterior (p. ej. tras un reinicio rapido): no mata a la vigente.
                    r.eventos.push({ nivel: 'info', texto: `NDEATH de otra sesión (bdSeq ${valorBd} ≠ ${this.nodo.bdSeq}): se ignora` });
                    return r;
                }
                this._marcar(this.nodo, VIGENCIA.OBSOLETO);
                this._marcar(this.disp, VIGENCIA.OBSOLETO);
                this.nodo.seq = null;
                this._comandosSinConfirmar(r, 'NDEATH');
                r.eventos.push({ nivel: 'error', texto: `NDEATH bdSeq=${valorBd}: Edge Node fuera de línea, todo OBSOLETO` });
                return r;
            }

            // [DF-4.9] Todo lo demas lleva seq y exige un NBIRTH vigente.
            if (this.nodo.estado !== VIGENCIA.EN_LINEA) {
                this._pedirRebirth(r, `${t.tipo} sin NBIRTH vigente`);
                return r;
            }
            const esperado = (this.nodo.seq + 1) % 256;                 // [DF-4.10]
            if (p.seq !== esperado) {
                // Se perdio al menos un mensaje: el estado puede ser incorrecto -> Rebirth (I-08).
                this._pedirRebirth(r, `Salto de seq: esperado ${esperado}, llegó ${p.seq}`);
            }
            this.nodo.seq = p.seq;

            if (t.tipo === 'NDATA') {
                this._aplicarData(this.nodo, 'nodo', p.metricas, p.timestamp, r);
            } else if (t.tipo === 'DBIRTH') {
                this._cargarBirth(this.disp, 'dispositivo', p.metricas, p.timestamp);
                for (const [nombre, m] of this.disp.metricas) this._confirmar(nombre, m.valor, r);
                r.eventos.push({ nivel: 'info', texto: `DBIRTH seq=${p.seq}: dispositivo EN LÍNEA` });
            } else if (t.tipo === 'DDATA') {
                if (this.disp.estado !== VIGENCIA.EN_LINEA) this._pedirRebirth(r, 'DDATA sin DBIRTH vigente');
                else this._aplicarData(this.disp, 'dispositivo', p.metricas, p.timestamp, r);
            } else if (t.tipo === 'DDEATH') {
                this._marcar(this.disp, VIGENCIA.OBSOLETO);
                this._comandosSinConfirmar(r, 'DDEATH');
                r.eventos.push({ nivel: 'error', texto: `DDEATH seq=${p.seq}: dispositivo fuera de línea, sus métricas OBSOLETAS` });
            }
            return r;
        }

        /**
         * [DF-4.14] Arma un DCMD. No marca nada como aplicado: eso lo hace el DDATA que vuelva.
         * @param {string} nombre  'Outputs/LedDigital' | 'Outputs/LedPWM'
         * @param {*} valor
         * @returns {{eventos: Array, publicar: Array}}
         */
        comandar(nombre, valor) {
            const r = { eventos: [], publicar: [] };
            const m = this.disp.metricas.get(nombre);
            if (this.disp.estado !== VIGENCIA.EN_LINEA || !m) {
                r.eventos.push({ nivel: 'error', texto: `No se envía ${nombre}: el dispositivo no está EN LÍNEA` });
                return r;
            }
            if (m.valor === valor) {
                r.eventos.push({ nivel: 'info', texto: `${nombre} ya vale ${valor}: no se envía nada` });
                return r;
            }
            const t = this.ahora();
            // Solo alias (payloads-alias-data-cmd-requirement); el tipo, el del DBIRTH.
            r.publicar.push({ topico: this.topicos.dcmd, qos: 0, retener: false,
                bytes: this.codec.codificar({ timestamp: t, metricas: [{ alias: m.alias, tipo: m.tipo, valor }] }) });
            this.comandos.set(nombre, { valor, estado: 'enviado', t });
            r.eventos.push({ nivel: 'info', texto: `DCMD ${nombre} = ${valor} ENVIADO` });
            return r;
        }

        /** Vence los comandos sin confirmacion. Llamar periodicamente. */
        tick() {
            const r = { eventos: [], publicar: [] };
            for (const [nombre, c] of this.comandos) {
                if (c.estado === 'enviado' && this.ahora() - c.t > this.esperaConfirmacionMs) {
                    c.estado = 'sin confirmar';
                    r.eventos.push({ nivel: 'aviso', texto: `Comando ${nombre} = ${c.valor} SIN CONFIRMAR (${this.esperaConfirmacionMs} ms sin DDATA)` });
                }
            }
            return r;
        }

        /** [DF-4.3] La web se conecto (o reconecto): sin BIRTH vigente, pide uno (los BIRTH no se retienen). */
        alConectar() {
            const r = { eventos: [], publicar: [] };
            if (this.nodo.estado !== VIGENCIA.EN_LINEA) this._pedirRebirth(r, 'Conexión nueva sin BIRTH vigente');
            return r;
        }

        /** [DF-4.13] La web perdio el broker: lo que muestra deja de ser actual. */
        alDesconectar() {
            const r = { eventos: [], publicar: [] };
            if (this.nodo.estado === VIGENCIA.EN_LINEA) this._marcar(this.nodo, VIGENCIA.OBSOLETO);
            if (this.disp.estado === VIGENCIA.EN_LINEA) this._marcar(this.disp, VIGENCIA.OBSOLETO);
            this.nodo.seq = null;
            this._comandosSinConfirmar(r, 'sin conexión con el broker');
            return r;
        }

        /** Valor de una metrica para la vista: {valor, ts, vigencia} (DESCONOCIDO si nunca llego). */
        metrica(nombre) {
            const m = this.nodo.metricas.get(nombre) || this.disp.metricas.get(nombre);
            return m ? { valor: m.valor, ts: m.ts, vigencia: m.vigencia }
                : { valor: null, ts: null, vigencia: VIGENCIA.DESCONOCIDO };
        }
    }

    /** Payload JSON del STATE de la Host Application (unica excepcion a Protobuf, Sparkplug 3.0). */
    function payloadState(online, timestamp) {
        return JSON.stringify({ online, timestamp });
    }

    return Object.freeze({ NAMESPACE, VIGENCIA, REBIRTH, analizarTopico, crearCodec, HostSparkplug, payloadState });
}));
