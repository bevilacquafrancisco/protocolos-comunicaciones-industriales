/**
 * maestro.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Maestro MODBus RTU del dispositivo 2: la maquina de estados de
 * docs/diagramas/flujo-maestro.mmd, independiente de Node-RED y del medio fisico.
 *
 *   - Ciclo de sondeo con periodo configurable que recorre el mapa de registros.
 *   - Escrituras pendientes desde las capas superiores, con prioridad sobre las lecturas y
 *     UNA pendiente por variable (la orden nueva reemplaza a la vieja, no se encola).
 *   - Por peticion: armar ADU -> esperar t3,5 -> transmitir -> esperar la respuesta con
 *     timeout -> validar -> contadores -> estado.
 *   - Contadores OK / CRC_ERROR / TIMEOUT / EXCEPTION y estado DONE / CRC ERROR /
 *     DEVICE NOT REACHED (consigna 1.c, I-05). "CRC_ERROR" cuenta tambien las tramas que no
 *     se pudieron recomponer (MALFORMED, WRONG_SLAVE), como pide la consigna; el detalle
 *     queda en contadores.detalle.
 *   - Ultima trama transmitida y recibida en hexadecimal, y latencia.
 *   - Reconfiguracion en vivo (I-04), prueba de conexion, trama manual, asistente de
 *     descubrimiento (barrido de Unit ID x baud x paridad) y exploracion de direcciones.
 *
 * El transporte se inyecta: { enviar(Buffer), reconfigurar(puerto) => Promise }.
 * En Node-RED es node-red-node-serialport (serial out / serial control); en desarrollo,
 * lib/transporte_tcp.js contra el simulador. El reloj tambien se inyecta (pruebas).
 *
 * Eventos (EventEmitter):
 *   'valor'  ({nombre, valor, calidad: 'good'|'bad', ts})   cambio de una variable
 *   'estado' (instantanea())                                tras cada peticion contada
 *   'evento' ({ts, nivel, capa: 'MODBUS', texto})           transiciones y acciones
 *   'trama'  ({tx, rx, resultado, latenciaMs})              cada peticion (diagnostico)
 *
 * Dependencias externas: ninguna (node:events, lib/modbus, lib/tipos, lib/configuracion).
 */
'use strict';

const { EventEmitter } = require('node:events');
const modbus = require('./modbus');
const tipos = require('./tipos');
const configuracion = require('./configuracion');

const { ERROR_TYPE } = modbus;

/** Estados textuales de la consigna (I-05). */
const ESTADO = Object.freeze({
    DONE: 'DONE',
    CRC_ERROR: 'CRC ERROR',
    NO_ALCANZADO: 'DEVICE NOT REACHED',
});

/** Errores que se reintentan (un timeout o una trama danada pueden ser ruido). */
const REINTENTABLES = new Set([ERROR_TYPE.TIMEOUT, ERROR_TYPE.CRC_ERROR, ERROR_TYPE.MALFORMED,
    ERROR_TYPE.WRONG_SLAVE]);
/** Errores que cuentan como CRC_ERROR en la consigna ("no se pudo recomponer la trama o error del CRC"). */
const COMO_CRC = new Set([ERROR_TYPE.CRC_ERROR, ERROR_TYPE.MALFORMED, ERROR_TYPE.WRONG_SLAVE]);

/**
 * Unit ID que el descubrimiento prueba primero: 1-10 (valores de fabrica habituales), 17 y
 * 247 (el maximo, usado por algunos equipos como direccion de servicio).
 */
const PRIORITARIOS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 17, 247];

/** Reloj real; las pruebas inyectan uno controlado. */
const RELOJ_REAL = { ahora: () => Date.now(), setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: (t) => clearTimeout(t) };

/** Contadores en cero. */
const contadoresVacios = () => ({
    OK: 0, CRC_ERROR: 0, TIMEOUT: 0, EXCEPTION: 0,
    detalle: { CRC_ERROR: 0, MALFORMED: 0, WRONG_SLAVE: 0, BYTES_ESPURIOS: 0 },
});

/**
 * Maestro MODBus RTU.
 *
 * Responsabilidad: ejecutar el ciclo de peticiones contra un esclavo y llevar la estadistica.
 * Atributos principales:
 *   config (object)       configuracion validada vigente (lib/configuracion.js)
 *   contadores (object)   OK, CRC_ERROR, TIMEOUT, EXCEPTION y detalle
 *   estado (string)       DONE | CRC ERROR | DEVICE NOT REACHED
 *   valores (Map)         nombre -> {valor, calidad, ts}
 * Relaciones: usa lib/modbus (protocolo) y un transporte inyectado; lo crea y lo maneja el
 *   function node "M1 · maestro MODBus" del flow modbus-master.
 */
class MaestroModbus extends EventEmitter {
    /**
     * @param {object} opciones
     * @param {object} opciones.config configuracion ya validada
     * @param {{enviar: function(Buffer): void, reconfigurar: function(object): Promise<void>}} opciones.transporte
     * @param {{ahora: function(): number, setTimeout: function, clearTimeout: function}} [opciones.reloj]
     */
    constructor({ config, transporte, reloj = RELOJ_REAL }) {
        super();
        const r = configuracion.validar(config);
        if (!r.ok) throw new Error(`configuracion invalida: ${r.errores.join('; ')}`);
        this.config = r.config;
        this.transporte = transporte;
        this.reloj = reloj;

        this.contadores = contadoresVacios();
        this.estado = ESTADO.NO_ALCANZADO;
        this.ultimoExito = null;          // ms del ultimo intento exitoso (OK o excepcion)
        this.ultimaFalla = null;          // errorType del ultimo intento fallido
        this.ultimaTx = '';
        this.ultimaRx = '';
        this.latenciaMs = null;
        this.ultimaExcepcion = null;
        this.valores = new Map();
        this.ciclos = 0;
        this.duracionCicloMs = null;

        this._activo = false;
        this._pausas = 0;                 // >0: no se sondea (descubrimiento, reconfiguracion)
        this._enCurso = null;             // intento esperando respuesta
        this._ocupado = false;            // hay una transaccion (con sus reintentos) en marcha
        this._temporizador = null;        // proxima ejecucion del planificador
        this._ultimaActividad = -Infinity; // fin estimado de la ultima trama en el bus
        this._indice = 0;                 // posicion en el ciclo de lectura
        this._inicioCiclo = null;
        this._escrituras = new Map();     // nombre -> {valor, resolver}
        this._releer = new Set();         // variables a leer ya (tras escribirlas)
        this._manuales = [];              // transacciones unicas (prueba, trama manual)
        this._colaBus = Promise.resolve(); // mutex del bus (_tomarBus)
        this._cancelarBarrido = false;
    }

    // =========================================================================
    // Ciclo de vida
    // =========================================================================

    /** [DF-2.1] Arranca el sondeo. */
    iniciar() {
        if (this._activo) return;
        this._activo = true;
        this._evento('info', `maestro iniciado: Unit ID ${this.config.esclavo.id}, ${this._textoPuerto()}`);
        this._planificar(0);
    }

    /** Detiene el sondeo y libera los temporizadores (finalize del function node). */
    detener() {
        this._activo = false;
        if (this._temporizador) this.reloj.clearTimeout(this._temporizador);
        this._temporizador = null;
        if (this._enCurso) this._completar(null, 'detenido');
        for (const [, p] of this._escrituras) p.resolver({ ok: false, errorType: 'DETENIDO', error: 'maestro detenido' });
        this._escrituras.clear();
    }

    // =========================================================================
    // Entrada de bytes — [DF-2.8]
    // =========================================================================

    /**
     * [DF-2.8] Recibe un bloque de bytes del puerto (serial in, o el socket TCP).
     * Delimita la respuesta por LONGITUD ESPERADA (ADR-012), no por silencio.
     * @param {Buffer} bloque
     */
    recibir(bloque) {
        if (!bloque || bloque.length === 0) return;
        const ahora = this.reloj.ahora();
        this._ultimaActividad = Math.max(this._ultimaActividad, ahora);
        const intento = this._enCurso;
        if (!intento) {
            // Bytes fuera de una transaccion: ruido, o la respuesta tardia a una peticion que
            // ya vencio. Se descartan y se cuentan (diagnostico de capa fisica).
            this.contadores.detalle.BYTES_ESPURIOS += bloque.length;
            return;
        }
        intento.buffer = Buffer.concat([intento.buffer, bloque]);
        if (intento.buffer.length > 256) { this._completar(intento.buffer, null); return; }
        if (intento.delimitacion === 'silencio') {
            // Trama manual: la longitud no se conoce; termina tras un silencio.
            if (intento.temporizadorSilencio) this.reloj.clearTimeout(intento.temporizadorSilencio);
            intento.temporizadorSilencio = this.reloj.setTimeout(
                () => this._completar(intento.buffer, null), intento.silencioMs);
            return;
        }
        const largo = modbus.responseLengthSoFar(intento.buffer, intento.req);
        if (largo !== null && intento.buffer.length >= largo) {
            // Si llegaron bytes de mas, la trama no se puede recomponer: se pasa entera y
            // parseResponse la marcara MALFORMED por largo invalido.
            this._completar(intento.buffer, null);
        }
    }

    // =========================================================================
    // Planificador — [DF-2.2] a [DF-2.4]
    // =========================================================================

    _planificar(retardoMs) {
        if (!this._activo) return;
        if (this._temporizador) this.reloj.clearTimeout(this._temporizador);
        this._temporizador = this.reloj.setTimeout(() => {
            this._temporizador = null;
            this._siguiente().catch((e) => this._evento('error', `error interno del maestro: ${e.message}`));
        }, Math.max(0, retardoMs));
    }

    /** [DF-2.2] REPOSO: elige el proximo trabajo. */
    async _siguiente() {
        if (!this._activo || this._ocupado) return;
        // 1) Transacciones unicas (prueba de conexion, trama manual, descubrimiento).
        if (this._manuales.length) {
            const trabajo = this._manuales.shift();
            await this._ejecutar(trabajo.fn, trabajo.resolver);
            return this._planificar(0);
        }
        if (this._pausas > 0) return;   // una operacion exclusiva tiene el bus; replanifica al terminar
        // 2) [DF-2.3] Escrituras pendientes: tienen prioridad.
        if (this._escrituras.size) {
            const [nombre, pendiente] = this._escrituras.entries().next().value;
            this._escrituras.delete(nombre);
            await this._ejecutar(() => this._escribirAhora(nombre, pendiente.valor), pendiente.resolver);
            return this._planificar(0);
        }
        // 3) Relecturas tras una escritura (confirmacion visible, ADR-015).
        if (this._releer.size) {
            const nombre = this._releer.values().next().value;
            this._releer.delete(nombre);
            const variable = this.config.mapa.find((v) => v.nombre === nombre);
            if (variable) await this._ejecutar(() => this._leerVariable(variable));
            return this._planificar(0);
        }
        // 4) [DF-2.4b] Proxima lectura del ciclo.
        const ahora = this.reloj.ahora();
        if (this._indice === 0) {
            if (this._inicioCiclo !== null) {
                const restante = this._inicioCiclo + this.config.sondeo.periodoMs - ahora;
                if (restante > 0) return this._planificar(restante);
            }
            this._inicioCiclo = ahora;
        }
        const variable = this.config.mapa[this._indice];
        await this._ejecutar(() => this._leerVariable(variable));
        this._indice = (this._indice + 1) % this.config.mapa.length;
        if (this._indice === 0) {
            this.ciclos += 1;
            this.duracionCicloMs = this.reloj.ahora() - this._inicioCiclo;
        }
        this._planificar(0);
    }

    /**
     * Mutex del bus: RS-485 es semiduplex y MODBus admite UNA transaccion a la vez. Todo uso
     * del bus (sondeo, escritura, prueba, descubrimiento) pasa por esta cola, de modo que dos
     * origenes concurrentes (p. ej. "Probar conexion" durante un descubrimiento) nunca
     * transmiten superpuestos.
     * @param {function(): Promise<*>} fn
     * @returns {Promise<*>}
     */
    _tomarBus(fn) {
        const ejecucion = this._colaBus.then(() => {
            this._ocupado = true;
            return fn();
        }).finally(() => { this._ocupado = false; });
        this._colaBus = ejecucion.catch(() => {});
        return ejecucion;
    }

    /** Ejecuta un trabajo con el bus tomado y entrega el resultado a resolver. */
    async _ejecutar(fn, resolver) {
        try {
            const r = await this._tomarBus(fn);
            if (resolver) resolver(r);
        } catch (e) {
            if (resolver) resolver({ ok: false, errorType: 'ERROR', error: e.message });
            else this._evento('error', e.message);
        }
    }

    /** Pausa el sondeo, ejecuta fn con el bus tomado durante toda la operacion y reanuda. */
    async _conBusLibre(fn) {
        this._pausas += 1;
        try {
            return await this._tomarBus(fn);
        } finally {
            this._pausas -= 1;
            if (this._pausas === 0) this._planificar(0);
        }
    }

    // =========================================================================
    // Transaccion — [DF-2.5] a [DF-2.14]
    // =========================================================================

    /**
     * [DF-2.5] a [DF-2.14] Una transaccion con reintentos.
     * @param {object} req {slaveId, fc, address, quantity, value}
     * @param {object} [op]
     * @param {boolean} [op.contar=true]      actualizar contadores y estado (falso en el descubrimiento)
     * @param {number}  [op.reintentos]       por defecto, config.sondeo.reintentos
     * @param {number}  [op.timeoutMs]        por defecto, config.sondeo.timeoutMs
     * @param {Buffer}  [op.trama]            trama ya armada (trama manual)
     * @param {string}  [op.delimitacion='longitud']  'longitud' | 'silencio'
     * @returns {Promise<object>} resultado de parseResponse + {tx, rx, latenciaMs, intentos}
     */
    async _transaccion(req, op = {}) {
        const contar = op.contar !== false;
        const reintentos = op.reintentos ?? this.config.sondeo.reintentos;
        let resultado = null;
        for (let intento = 0; intento <= reintentos; intento++) {
            resultado = await this._intento(req, op);
            resultado.intentos = intento + 1;
            if (contar) this._contar(resultado);
            this.emit('trama', { tx: resultado.tx, rx: resultado.rx, resultado: resultado.errorType,
                latenciaMs: resultado.latenciaMs, contada: contar });
            if (resultado.ok || !REINTENTABLES.has(resultado.errorType)) break;   // [DF-2.14]
        }
        return resultado;
    }

    /** [DF-2.6] a [DF-2.12] Un intento: silencio t3,5, transmision y respuesta. */
    async _intento(req, op) {
        const baud = this.config.puerto.baud;
        // [DF-2.5] ADU con CRC propio (o la trama manual ya armada).
        const trama = op.trama || modbus.buildRequest(req);
        // [DF-2.6] Silencio >= t3,5 desde la ultima actividad: es una COTA INFERIOR, y un
        // setTimeout solo puede atrasarse, nunca adelantarse; +1 ms por la granularidad.
        const espera = this._ultimaActividad + modbus.t35ms(baud) + 1 - this.reloj.ahora();
        if (espera > 0) await new Promise((r) => this.reloj.setTimeout(r, espera));

        return new Promise((resolver) => {
            const inicio = this.reloj.ahora();
            const intento = {
                req, buffer: Buffer.alloc(0), inicio, resolver,
                delimitacion: op.delimitacion || 'longitud',
                silencioMs: op.silencioMs || 30,
                temporizador: null, temporizadorSilencio: null,
            };
            this._enCurso = intento;
            // [DF-2.7] Transmitir. El fin de la trama en el bus se estima por su duracion.
            this._ultimaActividad = inicio + modbus.txMs(trama.length, baud);
            this.ultimaTx = modbus.toHex(trama);
            intento.tx = this.ultimaTx;
            try {
                this.transporte.enviar(trama);
            } catch (e) {
                this._evento('error', `no se pudo transmitir: ${e.message}`);
            }
            // [DF-2.9] Timeout de respuesta (configurable; en el descubrimiento, mas corto).
            // Si vence con una respuesta a medias, se entrega lo recibido: parseResponse la
            // clasifica como trama no recomponible (MALFORMED o CRC_ERROR), no como TIMEOUT.
            intento.temporizador = this.reloj.setTimeout(
                () => this._completar(intento.buffer.length ? intento.buffer : null),
                op.timeoutMs ?? this.config.sondeo.timeoutMs);
        });
    }

    /** Cierra el intento en curso con lo recibido (o null). */
    _completar(buffer, _motivo) {
        const intento = this._enCurso;
        if (!intento) return;
        this._enCurso = null;
        if (intento.temporizador) this.reloj.clearTimeout(intento.temporizador);
        if (intento.temporizadorSilencio) this.reloj.clearTimeout(intento.temporizadorSilencio);
        const ahora = this.reloj.ahora();
        // [DF-2.10] a [DF-2.12] Validacion.
        let resultado;
        if (intento.delimitacion === 'silencio') {
            // Trama manual: solo se informa lo recibido y si el CRC es valido.
            resultado = buffer && buffer.length
                ? { ok: modbus.checkCrc(buffer), data: null, errorType: modbus.checkCrc(buffer) ? ERROR_TYPE.NONE : ERROR_TYPE.CRC_ERROR,
                    error: modbus.checkCrc(buffer) ? null : 'CRC invalido o trama incompleta', exceptionCode: null }
                : modbus.parseResponse(null, intento.req);
        } else {
            resultado = modbus.parseResponse(buffer, intento.req);
        }
        resultado.tx = intento.tx;
        resultado.rx = modbus.toHex(buffer);
        resultado.crcValido = buffer && buffer.length >= 4 ? modbus.checkCrc(buffer) : null;
        resultado.latenciaMs = buffer && buffer.length ? ahora - intento.inicio : null;
        if (buffer && buffer.length) {
            this.ultimaRx = resultado.rx;
            this.latenciaMs = resultado.latenciaMs;
        }
        intento.resolver(resultado);
    }

    /** [DF-2.9] [DF-2.11] [DF-2.12b] [DF-2.13] [DF-2.15] Contadores y estado. */
    _contar(r) {
        const anterior = this.estado;
        const ahora = this.reloj.ahora();
        if (r.ok) {
            this.contadores.OK += 1;
            this.ultimoExito = ahora;
            this.ultimaFalla = null;
        } else if (r.errorType === ERROR_TYPE.EXCEPTION) {
            // El esclavo esta vivo y rechazo la peticion: cuenta como alcanzado.
            this.contadores.EXCEPTION += 1;
            this.ultimoExito = ahora;
            this.ultimaFalla = null;
            this.ultimaExcepcion = r.exceptionCode;
        } else if (r.errorType === ERROR_TYPE.TIMEOUT) {
            this.contadores.TIMEOUT += 1;
            this.ultimaFalla = r.errorType;
        } else if (COMO_CRC.has(r.errorType)) {
            this.contadores.CRC_ERROR += 1;
            this.contadores.detalle[r.errorType] += 1;
            this.ultimaFalla = r.errorType;
        }
        // [DF-2.15] DEVICE NOT REACHED por AUSENCIA SOSTENIDA, no por un fallo aislado
        // (ADR-014: contar fallos sueltos hacia parpadear los indicadores en la T1).
        if (this.ultimoExito === null || ahora - this.ultimoExito >= this.config.sondeo.ausenciaMs) {
            this.estado = ESTADO.NO_ALCANZADO;
        } else if (this.ultimaFalla && COMO_CRC.has(this.ultimaFalla)) {
            this.estado = ESTADO.CRC_ERROR;
        } else {
            this.estado = ESTADO.DONE;
        }
        if (this.estado !== anterior) {
            this._evento(this.estado === ESTADO.DONE ? 'info' : 'aviso', `estado MODBUS: ${anterior} -> ${this.estado}`);
            if (this.estado === ESTADO.NO_ALCANZADO) this._marcarCalidad('bad');
        }
        this.emit('estado', this.instantanea());
    }

    // =========================================================================
    // Lectura y escritura de variables del mapa
    // =========================================================================

    /** [DF-2.4b] [DF-2.13] Lee una variable y publica su valor si cambio. */
    async _leerVariable(variable) {
        const req = { slaveId: this.config.esclavo.id, fc: variable.fc, address: variable.direccion,
            quantity: tipos.cantidad(variable.tipo) };
        const r = await this._transaccion(req);
        if (r.ok) {
            let valor = tipos.decodificar(variable.tipo, r.data, variable.orden);
            if (variable.tipo === 'float32') valor = Number(valor.toPrecision(7));
            this._publicar(variable.nombre, valor, 'good');
            for (const d of this.config.derivadas.filter((x) => x.de === variable.nombre)) {
                this._publicar(d.nombre, Number((valor * d.factor).toFixed(d.decimales)), 'good');
            }
        }
        return r;
    }

    /** [DF-2.4a] Escribe ya (FC 05 o FC 06). */
    async _escribirAhora(nombre, valor) {
        const variable = this.config.mapa.find((v) => v.nombre === nombre);
        if (!variable) return { ok: false, errorType: 'DESCONOCIDA', error: `variable desconocida: ${nombre}` };
        const req = variable.fc === 1
            ? { slaveId: this.config.esclavo.id, fc: 5, address: variable.direccion, value: valor }
            : { slaveId: this.config.esclavo.id, fc: 6, address: variable.direccion, value: valor };
        const r = await this._transaccion(req);
        if (r.ok) this._releer.add(nombre);              // confirmar con una lectura (ADR-015)
        else this._evento('aviso', `escritura de ${nombre} = ${valor} fallida: ${r.error}`);
        return { ok: r.ok, errorType: r.errorType, error: r.error, exceptionCode: r.exceptionCode, tx: r.tx, rx: r.rx };
    }

    /**
     * [DF-2.3] Encola una escritura desde las capas superiores (OPC UA, Dashboard).
     * Una sola pendiente por variable: si llega otra antes de transmitir, reemplaza a la
     * anterior, que se resuelve como SUPERSEDED (una orden vieja ya no tiene sentido).
     * Por ADR-015 la promesa se resuelve con el ECO del esclavo, no al encolar.
     *
     * @param {string} nombre variable del mapa con escritura habilitada
     * @param {*} valor boolean para coils; entero para registros
     * @returns {Promise<{ok: boolean, errorType: string, error: string|null}>}
     */
    escribir(nombre, valor) {
        const variable = this.config.mapa.find((v) => v.nombre === nombre);
        if (!variable || !variable.escritura) {
            return Promise.resolve({ ok: false, errorType: 'NO_ESCRIBIBLE', error: `${nombre} no es escribible` });
        }
        let arg;
        try {
            arg = tipos.codificar(variable.tipo, valor);
            const num = typeof arg === 'boolean' ? Number(arg) : Number(valor);
            if ((variable.min !== undefined && num < variable.min) || (variable.max !== undefined && num > variable.max)) {
                throw new RangeError(`${valor} fuera de ${variable.min}..${variable.max}`);
            }
        } catch (e) {
            return Promise.resolve({ ok: false, errorType: 'VALOR_INVALIDO', error: e.message });
        }
        const previa = this._escrituras.get(nombre);
        if (previa) previa.resolver({ ok: false, errorType: 'SUPERSEDED', error: 'reemplazada por una orden mas nueva' });
        return new Promise((resolver) => {
            this._escrituras.set(nombre, { valor: arg, resolver });
            if (!this._ocupado && this._activo && this._pausas === 0) this._planificar(0);
        });
    }

    _publicar(nombre, valor, calidad) {
        const previo = this.valores.get(nombre);
        if (previo && previo.valor === valor && previo.calidad === calidad) return;
        const registro = { nombre, valor, calidad, ts: this.reloj.ahora() };
        this.valores.set(nombre, registro);
        this.emit('valor', registro);
    }

    _marcarCalidad(calidad) {
        for (const [nombre, v] of this.valores) this._publicar(nombre, v.valor, calidad);
    }

    // =========================================================================
    // I-04: reconfiguracion en vivo, prueba, trama manual, descubrimiento, exploracion
    // =========================================================================

    /**
     * [DF-2.17] Aplica una configuracion nueva sin reiniciar. Conserva los contadores.
     * @param {object} nueva configuracion completa
     * @returns {Promise<{ok: boolean, errores: string[], config: object|null}>}
     */
    reconfigurar(nueva) {
        const r = configuracion.validar(nueva);
        if (!r.ok) return Promise.resolve(r);
        return this._conBusLibre(async () => {
            const anterior = this.config;
            if (configuracion.cambiaPuerto(anterior, r.config)) {
                await this.transporte.reconfigurar(r.config.puerto);
                await this._dormir(r.config.puerto.esperaReconfiguracionMs);
            }
            this.config = r.config;
            this._indice = 0;
            this._inicioCiclo = null;
            this._escrituras.forEach((p) => p.resolver({ ok: false, errorType: 'RECONFIGURADO', error: 'configuracion cambiada' }));
            this._escrituras.clear();
            const vigentes = new Set(r.config.mapa.map((v) => v.nombre).concat(r.config.derivadas.map((d) => d.nombre)));
            for (const nombre of [...this.valores.keys()]) if (!vigentes.has(nombre)) this.valores.delete(nombre);
            this.ultimoExito = null;                       // el esclavo nuevo hay que alcanzarlo
            this.estado = ESTADO.NO_ALCANZADO;
            this._evento('info', `reconfigurado: Unit ID ${r.config.esclavo.id}, ${this._textoPuerto()}, ${r.config.mapa.length} variables`);
            this.emit('estado', this.instantanea());
            return r;
        });
    }

    /**
     * Una peticion unica con la configuracion vigente ("Probar conexion"). Cuenta en los
     * contadores: es una peticion real.
     * @param {{fc:number, direccion:number, cantidad?:number}} p
     * @returns {Promise<object>} resultado con tx, rx, crcValido, latenciaMs
     */
    probar({ fc = 3, direccion = 0, cantidad = 1 } = {}) {
        let req;
        try {
            req = { slaveId: this.config.esclavo.id, fc: Number(fc), address: Number(direccion), quantity: Number(cantidad) };
            modbus.buildRequest(req);
        } catch (e) {
            return Promise.resolve({ ok: false, errorType: 'PARAMETRO', error: e.message });
        }
        return this._unica(() => this._transaccion(req, { reintentos: 0 }));
    }

    /**
     * Trama manual: el usuario escribe ID + PDU en hexadecimal; el maestro agrega el CRC
     * propio y delimita la respuesta por silencio (no conoce su longitud). Sirve para
     * dialogar con un esclavo desconocido con cualquier funcion, sin programar (R-05).
     * @param {string} hex p. ej. "11 03 02 00 00 02"
     * @returns {Promise<object>}
     */
    tramaManual(hex) {
        let mensaje;
        try {
            mensaje = modbus.fromHex(hex);
            if (mensaje.length < 2 || mensaje.length > 254) throw new RangeError('entre 2 y 254 bytes sin CRC');
        } catch (e) {
            return Promise.resolve({ ok: false, errorType: 'PARAMETRO', error: e.message });
        }
        const trama = modbus.appendCrc(mensaje);
        return this._unica(() => this._transaccion({ slaveId: mensaje[0], fc: mensaje[1] }, {
            trama, delimitacion: 'silencio', reintentos: 0, contar: false,
            silencioMs: Math.max(20, Math.ceil(modbus.t35ms(this.config.puerto.baud)) + 15) }));
    }

    /** Encola una transaccion unica con prioridad sobre el sondeo. */
    _unica(fn) {
        return new Promise((resolver) => {
            this._manuales.push({ fn, resolver });
            if (!this._ocupado && this._activo) this._planificar(0);
            else if (!this._activo) this._ejecutar(fn, resolver);
        });
    }

    /**
     * ASISTENTE DE DESCUBRIMIENTO (ADR-007): barre combinaciones de baud x paridad y, para
     * cada una, Unit ID desde..hasta con una lectura (FC 03 sobre la direccion 0 por
     * defecto). Un esclavo que responde, aunque sea con una EXCEPCION (p. ej. 02 porque no
     * tiene esa direccion), queda descubierto: demostro que escucha en ese Unit ID, baud y
     * paridad. No toca los contadores del sondeo. Al terminar restaura el puerto.
     *
     * Orden de las combinaciones: primero la que la norma fija por defecto (19200 8E1,
     * MODBus over Serial Line §2.5.1) y despues las habituales (config.descubrimiento).
     *
     * @param {object} [op] sobrescribe campos de config.descubrimiento
     * @param {function(object): void} [alProgreso] {combinacion, id, probadas, total}
     * @returns {Promise<{encontrados: object[], probadas: number, duracionMs: number, cancelado: boolean}>}
     */
    descubrir(op = {}, alProgreso = () => {}) {
        const d = Object.assign({}, this.config.descubrimiento, op);
        return this._conBusLibre(async () => {
            const inicio = this.reloj.ahora();
            const encontrados = [];
            const total = d.combinaciones.length * (d.idHasta - d.idDesde + 1);   // pruebas maximas (ambas fases)
            let probadas = 0;
            this._cancelarBarrido = false;
            const puertoOriginal = this.config.puerto;
            this._evento('info', `descubrimiento: ${d.combinaciones.length} combinaciones x Unit ID ${d.idDesde}-${d.idHasta}`);
            // Dos fases. El barrido completo cuesta combinaciones x IDs x timeout (12 x 247 x
            // 60 ms = 178 s): demasiado para la defensa. La fase 1 prueba en TODAS las
            // combinaciones solo los Unit ID mas habituales (1-10 de fabrica, 17, 247), lo que
            // acota el caso tipico a 12 x 12 x 60 ms = 8,6 s; la fase 2 barre el resto.
            const rango = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
            const todos = rango(d.idDesde, d.idHasta);
            const prioritarios = (d.idsPrioritarios || PRIORITARIOS).filter((id) => id >= d.idDesde && id <= d.idHasta);
            const fases = [prioritarios, todos.filter((id) => !prioritarios.includes(id))];
            try {
                barrido:
                for (const ids of fases) for (const combinacion of d.combinaciones) {
                    if (!ids.length) continue;
                    const puerto = Object.assign({}, puertoOriginal, { baud: combinacion.baud, paridad: combinacion.paridad });
                    await this.transporte.reconfigurar(puerto);
                    await this._dormir(puerto.esperaReconfiguracionMs);
                    this.config = Object.assign({}, this.config, { puerto });
                    for (const id of ids) {
                        if (this._cancelarBarrido) break barrido;
                        const r = await this._transaccion({ slaveId: id, fc: d.fc, address: d.direccion, quantity: 1 },
                            { contar: false, reintentos: 0, timeoutMs: d.timeoutMs });
                        probadas += 1;
                        if (r.ok || r.errorType === ERROR_TYPE.EXCEPTION) {
                            const hallazgo = { id, baud: combinacion.baud, paridad: combinacion.paridad,
                                respuesta: r.ok ? 'normal' : `excepcion ${r.exceptionCode}`, tx: r.tx, rx: r.rx,
                                segundos: (this.reloj.ahora() - inicio) / 1000 };
                            encontrados.push(hallazgo);
                            this._evento('info', `descubierto: Unit ID ${id}, ${combinacion.baud} bps, paridad ${combinacion.paridad} (${hallazgo.respuesta})`);
                            if (d.detenerEnPrimero) break barrido;
                        }
                        if (probadas % 8 === 0) alProgreso({ combinacion, id, probadas, total });
                    }
                }
            } finally {
                // Restaurar el puerto vigente: el descubrimiento no cambia la configuracion;
                // aplicarla es una decision del operador (boton "Aplicar").
                this.config = Object.assign({}, this.config, { puerto: puertoOriginal });
                await this.transporte.reconfigurar(puertoOriginal);
                await this._dormir(puertoOriginal.esperaReconfiguracionMs);
            }
            const resultado = { encontrados, probadas, total, duracionMs: this.reloj.ahora() - inicio, cancelado: this._cancelarBarrido };
            this._evento(encontrados.length ? 'info' : 'aviso',
                `descubrimiento terminado: ${encontrados.length} esclavo(s) en ${(resultado.duracionMs / 1000).toFixed(1)} s, ${probadas} pruebas`);
            return resultado;
        });
    }

    /** Cancela el descubrimiento o la exploracion en curso. */
    cancelar() { this._cancelarBarrido = true; }

    /**
     * Exploracion de direcciones: con el enlace y el Unit ID vigentes, prueba una funcion
     * de lectura sobre un rango de direcciones (de a una) e informa cuales existen. Sirve
     * para reconstruir el mapa de un esclavo sin documentacion.
     * @param {{fc:number, desde:number, hasta:number, timeoutMs?:number}} op
     * @returns {Promise<{existentes: number[], excepciones: number, sinRespuesta: number, duracionMs: number}>}
     */
    explorar({ fc = 3, desde = 0, hasta = 31, timeoutMs } = {}) {
        fc = Number(fc); desde = Number(desde); hasta = Number(hasta);
        if (![1, 2, 3, 4].includes(fc) || !(desde >= 0 && hasta <= 0xFFFF && desde <= hasta) || hasta - desde > 1023) {
            return Promise.resolve({ ok: false, error: 'rango invalido (FC 1-4, hasta 1024 direcciones)' });
        }
        return this._conBusLibre(async () => {
            const inicio = this.reloj.ahora();
            const existentes = [];
            let excepciones = 0; let sinRespuesta = 0;
            this._cancelarBarrido = false;
            for (let dir = desde; dir <= hasta && !this._cancelarBarrido; dir++) {
                const r = await this._transaccion({ slaveId: this.config.esclavo.id, fc, address: dir, quantity: 1 },
                    { contar: false, reintentos: 0, timeoutMs: timeoutMs ?? this.config.sondeo.timeoutMs });
                if (r.ok) existentes.push({ direccion: dir, valor: r.data[0] });
                else if (r.errorType === ERROR_TYPE.EXCEPTION) excepciones += 1;
                else sinRespuesta += 1;
            }
            const res = { ok: true, fc, existentes, excepciones, sinRespuesta, duracionMs: this.reloj.ahora() - inicio };
            this._evento('info', `exploracion FC ${fc} ${desde}-${hasta}: ${existentes.length} direcciones existen`);
            return res;
        });
    }

    /** Pone los contadores en cero (boton del panel de estadisticas). */
    reiniciarContadores() {
        this.contadores = contadoresVacios();
        this._evento('info', 'contadores MODBUS en cero');
        this.emit('estado', this.instantanea());
    }

    /**
     * Restaura contadores persistidos (contexto de Node-RED en archivo).
     * @param {object} guardados instantanea().contadores
     */
    restaurarContadores(guardados) {
        if (!guardados || typeof guardados !== 'object') return;
        const c = contadoresVacios();
        for (const k of ['OK', 'CRC_ERROR', 'TIMEOUT', 'EXCEPTION']) if (Number.isInteger(guardados[k])) c[k] = guardados[k];
        for (const k of Object.keys(c.detalle)) {
            if (guardados.detalle && Number.isInteger(guardados.detalle[k])) c.detalle[k] = guardados.detalle[k];
        }
        this.contadores = c;
    }

    // =========================================================================
    // Consulta
    // =========================================================================

    /**
     * Estado completo para el Dashboard, OPC UA (F4) y la persistencia.
     * @returns {object}
     */
    instantanea() {
        return {
            estado: this.estado,
            contadores: JSON.parse(JSON.stringify(this.contadores)),
            ultimaTx: this.ultimaTx,
            ultimaRx: this.ultimaRx,
            latenciaMs: this.latenciaMs,
            ultimaExcepcion: this.ultimaExcepcion,
            ciclos: this.ciclos,
            duracionCicloMs: this.duracionCicloMs,
            esclavo: this.config.esclavo.id,
            puerto: this._textoPuerto(),
            disponible: this.estado !== ESTADO.NO_ALCANZADO,
            valores: Object.fromEntries([...this.valores].map(([k, v]) => [k, { valor: v.valor, calidad: v.calidad, ts: v.ts }])),
        };
    }

    _textoPuerto() {
        const p = this.config.puerto;
        const donde = p.tipo === 'tcp' ? `tcp ${p.tcp}` : p.ruta;
        return `${donde} ${p.baud} ${p.bitsDatos}${p.paridad[0].toUpperCase()}${p.bitsParada}`;
    }

    _dormir(ms) {
        return ms > 0 ? new Promise((r) => this.reloj.setTimeout(r, ms)) : Promise.resolve();
    }

    _evento(nivel, texto) {
        this.emit('evento', { ts: this.reloj.ahora(), nivel, capa: 'MODBUS', texto });
    }
}

module.exports = { MaestroModbus, ESTADO };
