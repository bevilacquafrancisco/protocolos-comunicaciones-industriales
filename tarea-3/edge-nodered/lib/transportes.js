/**
 * transportes.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Medios por los que el maestro (lib/maestro.js) envia y recibe bytes. El maestro solo ve
 * la interfaz { enviar(Buffer), reconfigurar(puerto) => Promise }.
 *
 *   TransporteTcp       DESARROLLO: tramas RTU crudas sobre TCP contra el simulador
 *                       (simuladores/esclavo_modbus_sim.py --tcp). Existe porque en Windows no
 *                       hay socat, y porque un par de pty de socat IGNORA el baud rate y la
 *                       paridad: con pty el asistente de descubrimiento "encontraria" al esclavo
 *                       en cualquier combinacion y no probaria nada. Para emular la capa
 *                       fisica, al conectar se envia una linea de preambulo:
 *                           PDCI-LINEA <baud> <paridad> <bitsDatos> <bitsParada>\n
 *                       y el simulador, si no coincide con la suya, se comporta como un UART
 *                       real desajustado: recibe basura y no responde.
 *   TransporteCompuesto PRODUCCION y desarrollo: delega en el puerto serie de Node-RED
 *                       (node-red-node-serialport, serial out / serial control) o en
 *                       TransporteTcp segun config.puerto.tipo, y permite pasar de uno a otro
 *                       EN VIVO desde el Dashboard (I-04).
 *
 * Dependencias externas: ninguna (node:net, node:events).
 */
'use strict';

const net = require('node:net');
const { EventEmitter } = require('node:events');

/** Linea de preambulo del enlace TCP de desarrollo. */
const preambulo = (p) => `PDCI-LINEA ${p.baud} ${p.paridad} ${p.bitsDatos} ${p.bitsParada}\n`;

/**
 * Transporte TCP de desarrollo contra el simulador.
 *
 * Atributos: direccion ('host:puerto'), linea (parametros anunciados), socket.
 * Eventos: 'datos' (Buffer), 'evento' ({nivel, texto}).
 */
class TransporteTcp extends EventEmitter {
    /**
     * @param {string} direccion 'host:puerto' del simulador
     */
    constructor(direccion) {
        super();
        this.direccion = direccion;
        this.linea = null;
        this.socket = null;
        this._destruido = false;
        this._reconexion = null;
    }

    /**
     * Abre (o reabre) la conexion anunciando los parametros de linea.
     * @param {object} puerto config.puerto (baud, paridad, bitsDatos, bitsParada, tcp)
     * @returns {Promise<void>} resuelve al conectar, o a los 2 s si el simulador no esta
     *   (el maestro seguira contando TIMEOUT, que es lo correcto si "no hay esclavo")
     */
    reconfigurar(puerto) {
        this.linea = puerto;
        if (puerto.tcp) this.direccion = puerto.tcp;
        return this._conectar();
    }

    _conectar() {
        this._cerrarSocket();
        if (this._destruido) return Promise.resolve();
        const [host, port] = this.direccion.split(':');
        return new Promise((resolver) => {
            let listo = false;
            const terminar = () => { if (!listo) { listo = true; resolver(); } };
            const socket = net.createConnection({ host, port: Number(port) });
            this.socket = socket;
            socket.setNoDelay(true);
            socket.on('connect', () => {
                if (this.linea) socket.write(preambulo(this.linea));
                this.emit('evento', { nivel: 'info', texto: `TCP conectado a ${this.direccion}` });
                terminar();
            });
            socket.on('data', (datos) => this.emit('datos', datos));
            socket.on('error', (e) => this.emit('evento', { nivel: 'aviso', texto: `TCP ${this.direccion}: ${e.code || e.message}` }));
            socket.on('close', () => {
                if (this.socket === socket && !this._destruido) {
                    this._reconexion = setTimeout(() => this._conectar(), 1000);
                    this._reconexion.unref();
                }
            });
            setTimeout(terminar, 2000).unref();   // no retiene el proceso (pruebas, cierre)
        });
    }

    /** @param {Buffer} trama */
    enviar(trama) {
        if (this.socket && this.socket.writable) this.socket.write(trama);
    }

    _cerrarSocket() {
        if (this._reconexion) clearTimeout(this._reconexion);
        this._reconexion = null;
        if (this.socket) {
            const s = this.socket;
            this.socket = null;
            s.removeAllListeners('close');
            s.destroy();
        }
    }

    /** Cierra la conexion para siempre (finalize del function node). */
    destruir() {
        this._destruido = true;
        this._cerrarSocket();
    }
}

/**
 * Transporte que elige entre el puerto serie de Node-RED y el TCP de desarrollo.
 *
 * Responsabilidad: que el maestro no sepa por donde viajan los bytes, y que cambiar de
 * medio sea una reconfiguracion mas.
 */
class TransporteCompuesto extends EventEmitter {
    /**
     * @param {object} serie adaptador del puerto serie de Node-RED:
     *   { enviar(Buffer), reconfigurar(puerto) => Promise, deshabilitar() }
     */
    constructor(serie) {
        super();
        this.serie = serie;
        this.tcp = null;
        this.tipo = null;
    }

    /**
     * @param {object} puerto config.puerto
     * @returns {Promise<void>}
     */
    async reconfigurar(puerto) {
        if (puerto.tipo === 'tcp') {
            if (this.tipo !== 'tcp') this.serie.deshabilitar();
            if (!this.tcp) {
                this.tcp = new TransporteTcp(puerto.tcp);
                this.tcp.on('datos', (d) => this.emit('datos', d));
                this.tcp.on('evento', (e) => this.emit('evento', e));
            }
            this.tipo = 'tcp';
            await this.tcp.reconfigurar(puerto);
        } else {
            if (this.tcp) { this.tcp.destruir(); this.tcp = null; }
            this.tipo = 'serie';
            await this.serie.reconfigurar(puerto);
        }
    }

    /** @param {Buffer} trama */
    enviar(trama) {
        if (this.tipo === 'tcp') { if (this.tcp) this.tcp.enviar(trama); } else this.serie.enviar(trama);
    }

    /** Libera el medio activo. */
    destruir() {
        if (this.tcp) this.tcp.destruir();
        this.tcp = null;
    }
}

module.exports = { TransporteTcp, TransporteCompuesto, preambulo };
