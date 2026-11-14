/**
 * estadisticas.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Estadistica de las cuatro capas (I-05: "en todo momento se visualiza la estadistica de
 * MODBUS, OPC UA, MQTT y Sparkplug B") y un historial breve de eventos.
 *
 *   RegistroCapas  cada capa publica su estado y sus contadores con actualizar(); el panel de
 *                  estadisticas lee instantanea(). En F3 solo MODBUS tiene datos; OPC UA (F4) y
 *                  MQTT/Sparkplug B (F5) se registran con el mismo metodo, sin tocar el panel.
 *   Historial      buffer circular de los ultimos N eventos {ts, nivel, capa, texto}.
 *
 * Se instancian una vez en settings.js (functionGlobalContext) y los comparten todos los flows.
 *
 * Dependencias externas: ninguna.
 */
'use strict';

/** Capas de la cadena, en el orden en que se muestran. */
const CAPAS = ['MODBUS', 'OPCUA', 'MQTT', 'SPARKPLUG'];

/**
 * Estado y contadores de cada capa.
 * Atributos: _capas (Map capa -> {estado, contadores, detalle, ts}).
 */
class RegistroCapas {
    constructor(reloj = () => Date.now()) {
        this._reloj = reloj;
        this._capas = new Map(CAPAS.map((c) => [c, { estado: 'SIN DATOS', contadores: {}, detalle: {}, ts: null }]));
    }

    /**
     * Publica el estado de una capa.
     * @param {string} capa MODBUS | OPCUA | MQTT | SPARKPLUG
     * @param {{estado: string, contadores?: object, detalle?: object}} datos
     * @throws {RangeError} capa desconocida
     */
    actualizar(capa, { estado, contadores = {}, detalle = {} }) {
        if (!this._capas.has(capa)) throw new RangeError(`capa desconocida: ${capa}`);
        this._capas.set(capa, { estado, contadores, detalle, ts: this._reloj() });
    }

    /** @returns {object} {MODBUS: {...}, OPCUA: {...}, MQTT: {...}, SPARKPLUG: {...}} */
    instantanea() {
        return Object.fromEntries([...this._capas].map(([k, v]) => [k, JSON.parse(JSON.stringify(v))]));
    }
}

/**
 * Historial circular de eventos.
 * Atributos: capacidad (int), _eventos (array).
 */
class Historial {
    /** @param {number} [capacidad=200] */
    constructor(capacidad = 200) {
        this.capacidad = capacidad;
        this._eventos = [];
    }

    /**
     * @param {{ts:number, nivel:string, capa:string, texto:string}} evento
     */
    agregar(evento) {
        this._eventos.push({ ts: evento.ts || Date.now(), nivel: evento.nivel || 'info',
            capa: evento.capa || '-', texto: String(evento.texto).slice(0, 300) });
        if (this._eventos.length > this.capacidad) this._eventos.splice(0, this._eventos.length - this.capacidad);
    }

    /**
     * @param {number} [n=50]
     * @returns {object[]} los n mas recientes, del mas nuevo al mas viejo
     */
    ultimos(n = 50) {
        return this._eventos.slice(-n).reverse();
    }
}

module.exports = { CAPAS, RegistroCapas, Historial };
