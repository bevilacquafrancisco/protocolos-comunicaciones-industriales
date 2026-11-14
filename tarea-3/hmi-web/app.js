/**
 * app.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-12
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Vista y conexion MQTT de la Host Application. La logica Sparkplug esta en sparkplug.js
 * (HostSparkplug); este archivo solo: conecta por WSS, entrega cada mensaje al nucleo, publica lo
 * que el nucleo pide (Rebirth, DCMD) y dibuja. Bloques [DF-4.x] de docs/diagramas/flujo-host-app.mmd.
 *
 * Decisiones (con su motivo):
 * - Un cliente mqtt.js NUEVO por conexion (reconnectPeriod: 0 y reconexion propia): el STATE
 *   online debe llevar el MISMO timestamp que el Will de ESE CONNECT
 *   (tck-id-message-flow-phid-sparkplug-state-publish-payload-timestamp). La reconexion de
 *   mqtt.js reusaria el Will viejo. Mismo criterio que el Edge Node (ADR-020).
 * - Retroceso exponencial 1, 2, 4... 30 s (ADR-023).
 * - Nada se publica antes del CONNACK y la SUBACK: un publish QoS 0 antes de conectar se pierde
 *   en silencio (lo midio F5 con host_comandos.py).
 * - clean: true y MQTT 3.1.1: Sparkplug 3.0 exige Clean Session en la Host Application
 *   (tck-id-message-flow-phid-sparkplug-clean-session-311).
 *
 * Dependencias externas: mqtt.js 5.16.1 (window.mqtt), protobuf.js 8.8.1 (window.protobuf),
 * sparkplug.js (window.Sparkplug), config.js (window.PDCI_CONFIG).
 */
(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const V = window.Sparkplug ? window.Sparkplug.VIGENCIA : {};
    const MAX_EVENTOS = 300;
    const ICONO = { ok: '✔', aviso: '▲', error: '✖', obsoleto: '◌', info: '·' };

    const red = { estado: 'DESCONECTADO', intento: 0, conexiones: 0, reconexiones: 0, tsState: null,
        credencialesRechazadas: false };
    let host = null;
    let cliente = null;
    let sucio = true;
    let ultimoDibujo = 0;
    let dibujoPedido = false;

    // =========================================================================
    // Configuracion
    // =========================================================================

    /**
     * Valida config.js. [SEC] ws:// (sin TLS) solo contra localhost: en internet la clave y los
     * comandos viajarian en claro.
     * @returns {string|null} el error, o null si esta bien
     */
    function validarConfig(c) {
        if (!c) return 'Falta config.js: copiar config.example.js a config.js y completarlo (README).';
        let url;
        try { url = new URL(c.url); } catch (e) { return `URL del broker inválida: ${c.url}`; }
        const local = ['127.0.0.1', 'localhost'].includes(url.hostname);
        if (url.protocol !== 'wss:' && !(url.protocol === 'ws:' && local)) {
            return 'El broker debe ser wss:// (TLS). ws:// solo se admite contra localhost (desarrollo).';
        }
        for (const k of ['usuario', 'clave', 'grupo', 'nodo', 'dispositivo', 'hostId']) {
            if (!c[k] || /[<>]/.test(c[k])) return `config.js: falta completar "${k}".`;
        }
        return null;
    }

    // =========================================================================
    // Registro de eventos [DF-4.12]
    // =========================================================================

    function hora(ts) {
        const d = new Date(ts);
        return d.toLocaleTimeString('es-AR', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
    }

    function registrar(nivel, texto) {
        const li = document.createElement('li');
        li.dataset.nivel = nivel;
        const t = document.createElement('span');
        t.textContent = hora(Date.now());
        const i = document.createElement('span');
        i.textContent = ICONO[nivel] || ICONO.info;
        i.setAttribute('aria-hidden', 'true');
        const x = document.createElement('span');
        x.textContent = texto;                       // textContent: nada del broker se interpreta como HTML
        li.append(t, i, x);
        const lista = $('eventos');
        lista.prepend(li);
        while (lista.children.length > MAX_EVENTOS) lista.lastChild.remove();
        // El banner explica el POR QUE (aviso o error); el eco 'info' del propio NCMD no lo pisa.
        if (nivel !== 'info' && /Rebirth|Salto de seq/.test(texto)) avisar(texto);
    }

    let temporizadorAviso = null;
    function avisar(texto) {
        const a = $('aviso');
        a.textContent = `▲ ${texto}`;
        a.hidden = false;
        clearTimeout(temporizadorAviso);
        temporizadorAviso = setTimeout(() => { a.hidden = true; }, 10000);
    }

    // =========================================================================
    // MQTT [DF-4.2, DF-4.3, DF-4.13]
    // =========================================================================

    /** Aplica el resultado del nucleo: eventos al registro y mensajes al broker. */
    function aplicar(r) {
        for (const e of r.eventos) registrar(e.nivel, e.texto);
        for (const p of r.publicar) publicar(p);
        sucio = true;
        // Dibujar en el proximo cuadro (~16 ms) y no esperar el ciclo de 250 ms: ese ciclo sumaba
        // 0-250 ms a la latencia de lectura (medido en F7, docs/mediciones.md).
        if (!dibujoPedido && host) {
            dibujoPedido = true;
            requestAnimationFrame(() => { dibujoPedido = false; dibujar(); sucio = false; ultimoDibujo = Date.now(); });
        }
    }

    function publicar(p) {
        if (!cliente || !cliente.connected || red.estado !== 'CONECTADO') {
            registrar('error', `No se publica en ${p.topico}: sin conexión con el broker`);
            return;
        }
        cliente.publish(p.topico, p.bytes, { qos: p.qos, retain: p.retener }, (err) => {
            if (err) registrar('error', `Error al publicar en ${p.topico}: ${err.message}`);
        });
    }

    /** [DF-4.2] Un CONNECT nuevo con su propio Will (STATE offline con el timestamp de ESTA conexion). */
    function conectar() {
        const cfg = window.PDCI_CONFIG;
        const ts = Date.now();
        red.tsState = ts;
        red.estado = 'CONECTANDO';
        sucio = true;
        const c = window.mqtt.connect(cfg.url, {
            username: cfg.usuario,
            password: cfg.clave,
            // Sufijo aleatorio: dos pestanas abiertas no se desalojan mutuamente en bucle.
            clientId: `${cfg.hostId}-${Math.random().toString(16).slice(2, 10)}`,
            clean: true,
            protocolVersion: 4,
            reconnectPeriod: 0,
            connectTimeout: 10000,
            keepalive: 30,
            will: { topic: host.topicos.state, payload: window.Sparkplug.payloadState(false, ts), qos: 1, retain: true },
        });
        cliente = c;
        let cerrado = false;

        c.on('connect', () => {
            // [DF-4.3] Suscribir ANTES de anunciarse: lo que llegue despues del STATE online ya se recibe.
            c.subscribe([host.topicos.suscripcion, host.topicos.state], { qos: 1 }, (err, concedidas) => {
                if (err || (concedidas || []).some((g) => g.qos === 128)) {
                    // SUBACK 0x80: el broker no autoriza el topico (ACL del usuario host_app).
                    registrar('error', `Suscripción rechazada por el broker: ${err ? err.message : 'SUBACK 0x80'}`);
                    c.end(true);
                    return;
                }
                c.publish(host.topicos.state, window.Sparkplug.payloadState(true, ts), { qos: 1, retain: true });
                red.estado = 'CONECTADO';
                red.intento = 0;
                red.credencialesRechazadas = false;
                if (red.conexiones++ > 0) red.reconexiones += 1;
                registrar('info', `MQTT conectado a ${new URL(cfg.url).host} · STATE online (timestamp ${ts})`);
                aplicar(host.alConectar());
            });
        });
        c.on('message', (topico, payload, paquete) => {
            let r;
            try {
                r = host.procesar(topico, new Uint8Array(payload), paquete.retain);
            } catch (e) {
                // Un error al procesar NO es un error del broker: se informa como lo que es
                // (antes mqtt.js lo entregaba al callback de subscribe y parecia un SUBACK rechazado).
                registrar('error', `Error al procesar ${topico}: ${e.message}`);
                return;
            }
            if (r.state && r.state.online === false && r.state.timestamp === ts && red.estado === 'CONECTADO') {
                // El broker publico NUESTRO Will aunque seguimos conectados (p. ej. otra sesion vieja):
                // se reafirma el STATE online de esta conexion.
                c.publish(host.topicos.state, window.Sparkplug.payloadState(true, ts), { qos: 1, retain: true });
            }
            aplicar(r);
        });
        c.on('error', (e) => {
            // F-09: CONNACK 4 (usuario o clave) o 5 (no autorizado) no es un corte de red: se
            // avisa aparte, porque reintentar no lo arregla (hay que corregir config.js).
            if (e.code === 4 || e.code === 5 || /Not authorized|Bad User/i.test(e.message)) {
                avisar('Credenciales MQTT rechazadas por el broker: revisar usuario y clave en config.js');
                red.credencialesRechazadas = true;
            }
            registrar('error', `MQTT: ${e.message}`);
        });
        c.on('close', () => {
            if (cerrado || c !== cliente) return;
            cerrado = true;
            const estabaConectado = red.estado === 'CONECTADO';
            red.estado = 'DESCONECTADO';
            if (estabaConectado) {
                registrar('error', 'MQTT desconectado: lo que se muestra pasa a OBSOLETO');
                aplicar(host.alDesconectar());
            }
            programarReconexion();
        });
    }

    /** [DF-4.13] Retroceso exponencial: 1, 2, 4, 8, 16, 30, 30... s (ADR-023). */
    function programarReconexion() {
        red.intento += 1;
        const espera = Math.min(1000 * 2 ** (red.intento - 1), 30000);
        registrar('aviso', `Reintento de conexión ${red.intento} en ${espera / 1000} s`);
        sucio = true;
        setTimeout(conectar, espera);
    }

    // =========================================================================
    // Vista [DF-4.12]
    // =========================================================================

    function fijarCapa(id, nivel, estado) {
        const capa = $(id);
        capa.dataset.nivel = nivel;
        capa.querySelector('.icono').textContent = ICONO[nivel];
        return estado;
    }

    function texto(id, valor) {
        const el = $(id);
        const t = valor === null || valor === undefined ? '—' : String(valor);
        if (el.textContent !== t) el.textContent = t;
    }

    function edad(ts) {
        if (!ts) return '';
        const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
        return s < 60 ? `hace ${s} s` : `hace ${Math.floor(s / 60)} min`;
    }

    /** Muestra una metrica con su vigencia: un valor sin BIRTH vigente nunca aparece como valido. */
    function variable(idCaja, idMeta, m) {
        $(idCaja).dataset.v = m.vigencia;
        texto(idMeta, m.vigencia === V.DESCONOCIDO ? 'sin BIRTH: no válido'
            : `${m.vigencia}${m.ts ? ' · ' + edad(m.ts) : ''}`);
    }

    function dibujar() {
        const m = (n) => host.metrica(n);
        const vigente = (x) => x.vigencia === V.EN_LINEA;

        // MODBUS
        const est = m('Status/MODBUS/Estado');
        // F-04: el estado MODBUS llega A TRAVES de OPC UA. Con OPC UA en ERROR, el ultimo valor no
        // dice nada del bus actual: se muestra OBSOLETO, no un DONE verde que ya nadie verifica.
        // La falla se informa en la capa que fallo (OPC UA) y la de abajo, como desconocida.
        const opcuaCaido = m('Status/OPCUA/Estado').valor === 'ERROR';
        const nivelModbus = !vigente(est) || opcuaCaido ? 'obsoleto'
            : { 'DONE': 'ok', 'CRC ERROR': 'aviso', 'DEVICE NOT REACHED': 'error' }[est.valor] || 'aviso';
        texto('modbus-estado', fijarCapa('capa-modbus', nivelModbus,
            opcuaCaido ? 'SIN DATOS (OPC UA en ERROR)'
                : vigente(est) ? est.valor : `${est.valor ?? '—'} (${est.vigencia})`));
        texto('modbus-ok', m('Status/MODBUS/OK').valor);
        texto('modbus-crc', m('Status/MODBUS/CRC_ERROR').valor);
        texto('modbus-timeout', m('Status/MODBUS/TIMEOUT').valor);
        texto('modbus-exception', m('Status/MODBUS/EXCEPTION').valor);

        // OPC UA
        const op = m('Status/OPCUA/Estado');
        const nivelOpcua = !vigente(op) ? 'obsoleto' : (op.valor === 'DONE' ? 'ok' : 'error');
        texto('opcua-estado', fijarCapa('capa-opcua', nivelOpcua, vigente(op) ? op.valor : `${op.valor ?? '—'} (${op.vigencia})`));

        // MQTT (la conexion de ESTA web)
        const nivelMqtt = { CONECTADO: 'ok', CONECTANDO: 'aviso', DESCONECTADO: 'error' }[red.estado];
        texto('mqtt-estado', fijarCapa('capa-mqtt', nivelMqtt,
            red.estado !== 'CONECTADO' && red.credencialesRechazadas ? 'CREDENCIALES RECHAZADAS' : red.estado));
        texto('mqtt-reconexiones', red.reconexiones);
        texto('mqtt-reconexiones-edge', m('Status/MQTT/Reconexiones').valor);

        // SPARKPLUG
        const nodo = host.nodo.estado;
        const disp = host.disp.estado;
        const nivelSpb = nodo !== V.EN_LINEA ? (nodo === V.OBSOLETO ? 'error' : 'obsoleto')
            : (disp === V.EN_LINEA ? 'ok' : 'aviso');
        texto('spb-estado', fijarCapa('capa-sparkplug', nivelSpb, `NODO ${nodo}`));
        texto('spb-disp', disp);
        texto('spb-bdseq', host.nodo.bdSeq);
        texto('spb-seq', host.nodo.seq);
        texto('spb-rebirths', host.rebirthsSolicitados);
        texto('spb-rebirths-edge', m('Status/Sparkplug/Rebirths').valor);

        // Dispositivo 1
        const dv = $('disp-vigencia');
        dv.dataset.v = disp;
        texto('disp-vigencia', disp);
        const pul = m('Inputs/Pulsador');
        texto('pulsador-valor', pul.valor === null ? null : (pul.valor ? '● PRESIONADO' : '○ LIBRE'));
        variable('v-pulsador', 'pulsador-meta', pul);
        const crudo = m('Inputs/Potenciometro');
        const pct = m('Inputs/Potenciometro_pct');
        texto('pote-crudo', crudo.valor);
        texto('pote-pct', pct.valor === null ? null : Number(pct.valor).toFixed(1));
        $('pote-medidor').value = pct.valor || 0;
        variable('v-pote', 'pote-meta', crudo);
        const led = m('Outputs/LedDigital');
        texto('led-valor', led.valor === null ? null : (led.valor ? '● ENCENDIDO' : '○ APAGADO'));
        variable('v-led', 'led-meta', led);
        const pwm = m('Outputs/LedPWM');
        texto('pwm-valor', pwm.valor);
        $('pwm-medidor').value = pwm.valor || 0;
        variable('v-pwm', 'pwm-meta', pwm);

        // Controles: habilitados solo con el dispositivo EN LINEA y la web conectada.
        const operable = disp === V.EN_LINEA && red.estado === 'CONECTADO';
        const btn = $('btn-led');
        btn.disabled = !operable;
        btn.setAttribute('aria-checked', String(led.valor === true));      // SOLO el valor confirmado
        texto('btn-led-texto', led.valor === null ? '—' : (led.valor ? 'ENCENDIDO (tocar para apagar)' : 'APAGADO (tocar para encender)'));
        const slider = $('pwm');
        slider.disabled = !operable;
        if (document.activeElement !== slider && pwm.valor !== null) {
            slider.value = pwm.valor;                                       // vuelve al confirmado
            texto('pwm-pedido', pwm.valor);
        }
        estadoComando('cmd-led', 'Outputs/LedDigital');
        estadoComando('cmd-pwm', 'Outputs/LedPWM');
    }

    function estadoComando(id, nombre) {
        const c = host.comandos.get(nombre);
        const el = $(id);
        el.dataset.estado = c ? c.estado : 'ninguno';
        const icono = { enviado: '▲', confirmado: '✔', 'sin confirmar': '✖' };
        texto(id, c ? `${icono[c.estado]} ${c.estado.toUpperCase()}: ${c.valor} · ${edad(c.t)}` : 'Sin comandos');
    }

    // =========================================================================
    // Inicio [DF-4.1]
    // =========================================================================

    async function iniciar() {
        const cfg = window.PDCI_CONFIG;
        const error = validarConfig(cfg) || (!window.mqtt || !window.protobuf || !window.Sparkplug
            ? 'No se cargaron las bibliotecas (vendor/): ver README.' : null);
        if (error) {
            $('fatal').textContent = `✖ ${error}`;
            $('fatal').hidden = false;
            return;
        }
        $('ids').textContent = `grupo ${cfg.grupo} · nodo ${cfg.nodo} · dispositivo ${cfg.dispositivo} · host ${cfg.hostId}`;
        let proto;
        try {
            const resp = await fetch('proto/sparkplug_b.proto', { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            proto = await resp.text();
        } catch (e) {
            $('fatal').textContent = `✖ No se pudo cargar proto/sparkplug_b.proto (${e.message}). ¿Se abrió con file://? Usar el servidor (README).`;
            $('fatal').hidden = false;
            return;
        }
        const codec = window.Sparkplug.crearCodec(window.protobuf, proto);
        host = new window.Sparkplug.HostSparkplug({ codec, grupo: cfg.grupo, nodo: cfg.nodo,
            dispositivo: cfg.dispositivo, hostId: cfg.hostId });

        $('btn-led').addEventListener('click', () => {
            const actual = host.metrica('Outputs/LedDigital').valor;
            if (actual !== null) aplicar(host.comandar('Outputs/LedDigital', !actual));
        });
        const slider = $('pwm');
        slider.addEventListener('input', () => texto('pwm-pedido', slider.value));
        // 'change' (al soltar), no 'input': arrastrar no debe generar un DCMD por cada pixel.
        slider.addEventListener('change', () => {
            aplicar(host.comandar('Outputs/LedPWM', Number(slider.value)));
            slider.blur();
        });

        // Cierre intencional: STATE offline con la hora actual ANTES de desconectar
        // (tck-id-host-topic-phid-death-payload-disconnect-clean). Mejor esfuerzo: el navegador
        // puede cortar antes; si pasa, el Will hace lo mismo.
        window.addEventListener('pagehide', () => {
            if (cliente && cliente.connected) {
                cliente.publish(host.topicos.state, window.Sparkplug.payloadState(false, Date.now()), { qos: 1, retain: true });
                cliente.end(false);
            }
        });

        registrar('info', 'Host Application iniciada · sparkplug_b.proto cargado');
        conectar();
        setInterval(() => {
            aplicar(host.tick());
            const ahora = Date.now();
            if (sucio || ahora - ultimoDibujo > 1000) {         // 1 s: refresca las "hace X s"
                dibujar();
                sucio = false;
                ultimoDibujo = ahora;
            }
        }, 250);
    }

    iniciar();
}());
