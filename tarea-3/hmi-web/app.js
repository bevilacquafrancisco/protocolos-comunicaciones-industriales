/**
 * app.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-12
 * Version: 2.0 (2026-11-16, ADR-028)
 *
 * Descripcion general
 * -------------------
 * Vista y conexion MQTT de la Host Application. La logica Sparkplug esta en sparkplug.js
 * (HostSparkplug), la decodificacion didactica en tramas.js y el modelo estatico en modelo.js.
 * Este archivo: pide usuario y clave del broker, conecta por WSS, entrega cada mensaje al
 * nucleo, publica lo que el nucleo pide (Rebirth, DCMD) y dibuja las cinco pestanas.
 * Bloques [DF-4.x] de docs/diagramas/flujo-host-app.mmd.
 *
 * Decisiones (con su motivo):
 * - [DF-4.0] Usuario y clave se piden al entrar y viven SOLO en memoria (ADR-028): la pagina
 *   puede publicarse sin ningun secreto adentro (antes la clave estaba en config.js y el
 *   navegador la descargaba, R-08). Recargar la pagina los borra.
 * - Un cliente mqtt.js NUEVO por conexion (reconnectPeriod: 0 y reconexion propia): el STATE
 *   online debe llevar el MISMO timestamp que el Will de ESE CONNECT
 *   (tck-id-message-flow-phid-sparkplug-state-publish-payload-timestamp). Mismo criterio que
 *   el Edge Node (ADR-020).
 * - Retroceso exponencial 1, 2, 4... 30 s (ADR-023), solo despues del primer ingreso: al
 *   entrar, un error se informa y se vuelve a pedir la clave (reintentar una clave mala no sirve).
 * - Nada se publica antes del CONNACK y la SUBACK: un publish QoS 0 antes de conectar se pierde
 *   en silencio (lo midio F5 con host_comandos.py).
 * - clean: true y MQTT 3.1.1: Sparkplug 3.0 exige Clean Session en la Host Application.
 * - Todo lo que llega del broker se escribe con textContent, nunca como HTML.
 *
 * Dependencias externas: mqtt.js 5.16.1 (window.mqtt), protobuf.js 8.8.1 (window.protobuf),
 * sparkplug.js (window.Sparkplug), tramas.js (window.Tramas), modelo.js (window.Modelo),
 * config.js (window.PDCI_CONFIG).
 */
(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const V = window.Sparkplug ? window.Sparkplug.VIGENCIA : {};
    const Tr = window.Tramas;
    const Mo = window.Modelo;
    const MAX_EVENTOS = 300;
    const MAX_MENSAJES = 40;
    const MAX_TRAMAS = 30;
    const MAX_NOTIFICACIONES = 30;
    const DIAGNOSTICO = new Set(['Status/MODBUS/UltimaTramaTx', 'Status/MODBUS/UltimaTramaRx', 'Status/MODBUS/LatenciaMs']);
    const PESTANAS = ['general', 'modbus', 'opcua', 'sparkplug', 'guia'];

    const red = { estado: 'DESCONECTADO', intento: 0, conexiones: 0, reconexiones: 0, tsState: null,
        credencialesRechazadas: false, fase: 'ingreso' };
    let cred = null;                  // {usuario, clave}: SOLO en memoria (ADR-028)
    let cfg = null;
    let host = null;
    let cliente = null;
    let sucio = true;
    let ultimoDibujo = 0;
    let dibujoPedido = false;
    let pestana = 'general';

    /** Lo que la vista acumula ademas del nucleo: listas en vivo y selecciones. */
    const vista = {
        mensajes: [], selMensaje: null, conteo: {},
        tramas: [], selTrama: null, ultimoTxTs: null,
        notificaciones: [], selNodo: 'Dispositivo1.Inputs.Potenciometro',
        ultimoComando: null, confirmaciones: new Map(), lectura: null,
        version: { mensajes: 0, tramas: 0, notificaciones: 0 }, dibujado: {},
    };

    // =========================================================================
    // Utilidades de DOM
    // =========================================================================

    /**
     * Crea un elemento. El texto va SIEMPRE por textContent.
     * @param {string} etiqueta
     * @param {object} [props] className, texto, title y atributos (aria-*, data-*, type...)
     * @param {...Node} hijos
     * @returns {HTMLElement}
     */
    function el(etiqueta, props = {}, ...hijos) {
        const e = document.createElement(etiqueta);
        for (const [k, v] of Object.entries(props)) {
            if (v === undefined || v === null) continue;
            if (k === 'className') e.className = v;
            else if (k === 'texto') e.textContent = String(v);
            else if (k === 'onclick') e.addEventListener('click', v);
            else e.setAttribute(k, String(v));
        }
        for (const h of hijos) if (h) e.append(h);
        return e;
    }

    /** Fila de tabla: cada celda es texto o {texto, clase}. */
    const fila = (...celdas) => el('tr', {}, ...celdas.map((c) => (typeof c === 'object' && c !== null
        ? el('td', { className: c.clase, texto: c.texto }) : el('td', { texto: c ?? '—' }))));

    /** Bytes coloreados: cada byte con su rotulo como title. */
    const bytesVista = (segmentos) => segmentos.map((s) => el('span', { className: `by ${s.tono}`, title: s.campo, texto: s.h }));

    function texto(id, valor) {
        const e = $(id);
        const t = valor === null || valor === undefined ? '—' : String(valor);
        if (e.textContent !== t) e.textContent = t;
    }

    function insignia(id, tono, valor) {
        const e = $(id);
        e.className = `badge ${tono}`;
        texto(id, valor);
    }

    function hora(ts) {
        if (ts === null || ts === undefined) return '—';
        const d = new Date(ts);
        return d.toLocaleTimeString('es-AR', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
    }

    function edad(ts) {
        if (!ts) return '';
        const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
        return s < 60 ? `hace ${s} s` : `hace ${Math.floor(s / 60)} min`;
    }

    const brokerHost = () => { try { return new URL(cfg.url).host; } catch (e) { return cfg.url; } };

    // =========================================================================
    // Configuracion
    // =========================================================================

    /**
     * Valida config.js. [SEC] ws:// (sin TLS) solo contra localhost: en internet la clave y los
     * comandos viajarian en claro.
     * @returns {{error: ?string, aviso: ?string}}
     */
    function validarConfig(c) {
        if (!c) return { error: 'Falta config.js: copiar config.example.js a config.js y completarlo (README).' };
        let url;
        try { url = new URL(c.url); } catch (e) { return { error: `URL del broker inválida: ${c.url}` }; }
        const local = ['127.0.0.1', 'localhost'].includes(url.hostname);
        if (url.protocol !== 'wss:' && !(url.protocol === 'ws:' && local)) {
            return { error: 'El broker debe ser wss:// (TLS). ws:// solo se admite contra localhost (desarrollo).' };
        }
        for (const k of ['grupo', 'nodo', 'dispositivo', 'hostId']) {
            if (!c[k] || /[<>]/.test(c[k])) return { error: `config.js: falta completar "${k}".` };
        }
        // ADR-028: la clave ya no va en config.js. Si quedo una, no se usa y se pide borrarla.
        return { error: null, aviso: c.clave ? 'config.js todavía tiene una "clave": ya no se usa y conviene borrarla.' : null };
    }

    // =========================================================================
    // Registro de eventos [DF-4.12]
    // =========================================================================

    function registrar(nivel, textoEvento) {
        const li = el('li', { 'data-nivel': nivel }, el('span', { texto: hora(Date.now()) }), el('span', { texto: textoEvento }));
        const lista = $('eventos');
        lista.prepend(li);
        while (lista.children.length > MAX_EVENTOS) lista.lastChild.remove();
        if (nivel !== 'info' && /Rebirth|Salto de seq/.test(textoEvento)) avisar(textoEvento);
    }

    let temporizadorAviso = null;
    function avisar(t) {
        const a = $('aviso');
        a.textContent = `▲ ${t}`;
        a.hidden = false;
        clearTimeout(temporizadorAviso);
        temporizadorAviso = setTimeout(() => { a.hidden = true; }, 10000);
    }

    // =========================================================================
    // [DF-4.0] Ingreso
    // =========================================================================

    function errorIngreso(mensaje) {
        cred = null;
        $('login-error').textContent = mensaje;
        $('login-error').hidden = false;
        $('login-estado').textContent = '';
        $('btn-entrar').disabled = false;
        $('clave').value = '';
        $('clave').focus();
    }

    function alEnviarIngreso(ev) {
        ev.preventDefault();                       // form-action 'none': nunca se navega
        const usuario = $('usuario').value.trim();
        const clave = $('clave').value;
        if (!usuario || !clave) { errorIngreso('Completá usuario y contraseña.'); return; }
        cred = { usuario, clave };
        $('login-error').hidden = true;
        $('login-estado').textContent = `Conectando con ${brokerHost()}…`;
        $('btn-entrar').disabled = true;
        red.fase = 'ingreso';
        red.credencialesRechazadas = false;
        conectar();
    }

    function entrarAplicacion() {
        red.fase = 'operando';
        $('login').hidden = true;
        $('app').hidden = false;
        texto('usuario-actual', cred.usuario);
        texto('usuario-inicial', cred.usuario.charAt(0).toUpperCase());
        $('clave').value = '';
        const pedida = location.hash.replace('#', '');
        fijarPestana(PESTANAS.includes(pedida) ? pedida : 'general');
    }

    /** Salir: STATE offline con la hora actual, cerrar y recargar (borra la clave de la memoria). */
    function salir() {
        const fin = () => location.reload();
        if (cliente && cliente.connected) {
            cliente.publish(host.topicos.state, window.Sparkplug.payloadState(false, Date.now()), { qos: 1, retain: true },
                () => cliente.end(false, {}, fin));
            setTimeout(fin, 1500);                 // mejor esfuerzo: si el broker no confirma, el Will hace lo mismo
        } else {
            fin();
        }
    }

    // =========================================================================
    // MQTT [DF-4.2, DF-4.3, DF-4.13]
    // =========================================================================

    function aplicar(r) {
        for (const e of r.eventos) registrar(e.nivel, e.texto);
        for (const p of r.publicar) publicar(p);
        sucio = true;
        // Dibujar en el proximo cuadro: un ciclo fijo sumaba 0-250 ms a la latencia (F7).
        if (!dibujoPedido && host && red.fase === 'operando') {
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
        if (!cred) return;
        const ts = Date.now();
        red.tsState = ts;
        red.estado = 'CONECTANDO';
        sucio = true;
        const c = window.mqtt.connect(cfg.url, {
            username: cred.usuario,
            password: cred.clave,
            clientId: `${cfg.hostId}-${Math.random().toString(16).slice(2, 10)}`,   // dos pestanas no se desalojan
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
            // [DF-4.3] Suscribir ANTES de anunciarse.
            c.subscribe([host.topicos.suscripcion, host.topicos.state], { qos: 1 }, (err, concedidas) => {
                if (err || (concedidas || []).some((g) => g.qos === 128)) {
                    // SUBACK 0x80: el broker no autoriza el topico para ESTE usuario (permisos, ADR-027).
                    const motivo = `el broker no autoriza a "${cred.usuario}" a suscribirse al grupo (${err ? err.message : 'SUBACK 0x80'})`;
                    if (red.fase === 'ingreso') errorIngreso(`Ingreso rechazado: ${motivo}.`);
                    else registrar('error', `Suscripción rechazada: ${motivo}`);
                    red.credencialesRechazadas = true;
                    c.end(true);
                    return;
                }
                c.publish(host.topicos.state, window.Sparkplug.payloadState(true, ts), { qos: 1, retain: true });
                red.estado = 'CONECTADO';
                red.intento = 0;
                red.credencialesRechazadas = false;
                if (red.conexiones++ > 0) red.reconexiones += 1;
                if (red.fase === 'ingreso') entrarAplicacion();
                registrar('info', `MQTT conectado a ${brokerHost()} como ${cred.usuario} · STATE online (timestamp ${ts})`);
                aplicar(host.alConectar());
            });
        });
        c.on('message', (topico, payload, paquete) => {
            const bytes = new Uint8Array(payload);
            let r;
            try {
                r = host.procesar(topico, bytes, paquete.retain);
            } catch (e) {
                registrar('error', `Error al procesar ${topico}: ${e.message}`);
                return;
            }
            capturar(topico, bytes, r);
            if (r.state && r.state.online === false && r.state.timestamp === ts && red.estado === 'CONECTADO') {
                // El broker publico NUESTRO Will aunque seguimos conectados: se reafirma el STATE online.
                c.publish(host.topicos.state, window.Sparkplug.payloadState(true, ts), { qos: 1, retain: true });
            }
            aplicar(r);
        });
        c.on('error', (e) => {
            // F-09: CONNACK 4 (usuario o clave) o 5 (no autorizado) no es un corte de red.
            if (e.code === 4 || e.code === 5 || /Not authorized|Bad User/i.test(e.message)) {
                red.credencialesRechazadas = true;
                if (red.fase === 'ingreso') errorIngreso('Usuario o contraseña incorrectos: el broker rechazó la conexión.');
                else avisar('El broker rechazó las credenciales: hay que volver a ingresar.');
            }
            registrar('error', `MQTT: ${e.message}`);
        });
        c.on('close', () => {
            if (cerrado || c !== cliente) return;
            cerrado = true;
            const estabaConectado = red.estado === 'CONECTADO';
            red.estado = 'DESCONECTADO';
            if (red.fase === 'ingreso') {
                if (!red.credencialesRechazadas) errorIngreso(`No se pudo conectar con ${brokerHost()}: revisar la red y que el puerto 8084 no esté bloqueado.`);
                return;                                // en el ingreso no se reintenta solo
            }
            if (estabaConectado) {
                registrar('error', 'MQTT desconectado: lo que se muestra pasa a OBSOLETO');
                aplicar(host.alDesconectar());
            }
            if (red.credencialesRechazadas) { location.reload(); return; }   // clave cambiada: volver a pedirla
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
    // [DF-4.15] Captura de lo que llega, para las pestanas
    // =========================================================================

    /** Nombre y valor de una metrica decodificada (resuelve alias con el BIRTH vigente). */
    function nombreYValor(m) {
        const a = m.alias != null ? host.alias.get(m.alias) : null;
        const nombre = m.nombre || (a && a.nombre) || `alias ${m.alias}`;
        const def = host.nodo.metricas.get(nombre) || host.disp.metricas.get(nombre);
        const tipo = m.tipo || (def && def.tipo);
        let valor = '?';
        try { valor = tipo ? host.codec.valor(m.crudo, tipo) : '?'; } catch (e) { /* se muestra '?' */ }
        // Un Float de 32 bits (64.8) llega como 64.80000305175781: se muestra con 2 decimales
        if (typeof valor === 'number' && !Number.isInteger(valor)) valor = Math.round(valor * 100) / 100;
        return { nombre, valor };
    }

    function capturar(topico, bytes, r) {
        const t = window.Sparkplug.analizarTopico(topico);
        if (!t) return;
        if (t.tipo !== 'STATE' && (t.grupo !== cfg.grupo || t.nodo !== cfg.nodo)) return;
        const ahora = Date.now();
        vista.conteo[t.tipo] = (vista.conteo[t.tipo] || 0) + 1;
        let resumen;
        if (t.tipo === 'STATE') resumen = new TextDecoder().decode(bytes);
        else if (r.payload) resumen = r.payload.metricas.map((m) => { const x = nombreYValor(m); return `${x.nombre} = ${x.valor}`; }).join(' · ') || '(sin métricas)';
        else resumen = 'payload inválido';
        vista.mensajes.unshift({ id: `${ahora}-${Math.random()}`, t: ahora, topico, tipo: t.tipo,
            seq: r.payload ? r.payload.seq : null, bytes, resumen });
        if (vista.mensajes.length > MAX_MENSAJES) vista.mensajes.pop();
        vista.version.mensajes += 1;

        for (const nombre of r.confirmados) {
            vista.confirmaciones.set(nombre, { bytes, seq: r.payload ? r.payload.seq : null });
        }

        // Tramas MODBus reales: llegan en el NDATA de diagnostico (ADR-028)
        const tx = host.metrica('Status/MODBUS/UltimaTramaTx');
        if (tx.valor && tx.ts !== vista.ultimoTxTs) {
            vista.ultimoTxTs = tx.ts;
            vista.tramas.unshift({ id: `${tx.ts}-${Math.random()}`, ts: tx.ts, llegada: ahora, tx: tx.valor,
                rx: host.metrica('Status/MODBUS/UltimaTramaRx').valor || '', latencia: host.metrica('Status/MODBUS/LatenciaMs').valor });
            if (vista.tramas.length > MAX_TRAMAS) vista.tramas.pop();
            vista.version.tramas += 1;
        }

        // Notificaciones OPC UA reconstruidas y latencia de lectura
        if (r.payload && /DATA|BIRTH/.test(t.tipo)) {
            for (const m of r.payload.metricas) {
                const x = nombreYValor(m);
                const nodeId = Mo.nodeIdDe(x.nombre);
                if (nodeId && !DIAGNOSTICO.has(x.nombre)) {
                    vista.notificaciones.unshift({ t: m.timestamp ?? r.payload.timestamp, nodeId, valor: x.valor });
                    if (vista.notificaciones.length > MAX_NOTIFICACIONES) vista.notificaciones.pop();
                    vista.version.notificaciones += 1;
                }
                if (t.tipo === 'DDATA' && (x.nombre === 'Inputs/Potenciometro' || x.nombre === 'Inputs/Pulsador')) {
                    vista.lectura = { nombre: x.nombre, valor: x.valor, tsFuente: m.timestamp, tsPayload: r.payload.timestamp, llegada: ahora };
                }
            }
        }
    }

    // =========================================================================
    // Vista [DF-4.12]: barra de capas (siempre) y la pestana activa
    // =========================================================================

    const vigente = (x) => x.vigencia === V.EN_LINEA;
    const m = (n) => host.metrica(n);

    /** Estado de cada capa, en un solo lugar: lo usan la barra y la cadena. */
    function estados() {
        const est = m('Status/MODBUS/Estado');
        const op = m('Status/OPCUA/Estado');
        // F-04: el estado MODBUS llega A TRAVES de OPC UA. Con OPC UA en ERROR, el ultimo valor no
        // dice nada del bus actual: se muestra SIN DATOS, no un DONE verde que ya nadie verifica.
        const opcuaCaido = op.valor === 'ERROR';
        const modbus = !vigente(est) || opcuaCaido ? 'obsoleto'
            : ({ 'DONE': 'ok', 'CRC ERROR': 'aviso', 'DEVICE NOT REACHED': 'error' }[est.valor] || 'aviso');
        const opcua = !vigente(op) ? 'obsoleto' : (op.valor === 'DONE' ? 'ok' : 'error');
        const mqtt = { CONECTADO: 'ok', CONECTANDO: 'aviso', DESCONECTADO: 'error' }[red.estado];
        const nodo = host.nodo.estado;
        const disp = host.disp.estado;
        const spb = nodo !== V.EN_LINEA ? (nodo === V.OBSOLETO ? 'error' : 'obsoleto') : (disp === V.EN_LINEA ? 'ok' : 'aviso');
        return { est, op, opcuaCaido, modbus, opcua, mqtt, nodo, disp, spb };
    }
    const TONO = { ok: 'ok', aviso: 'warn', error: 'err', obsoleto: '' };
    const ETIQUETA = { ok: 'OK', aviso: 'ATENCIÓN', error: 'FALLA', obsoleto: 'SIN DATOS' };

    function dibujarCapas(e) {
        const capa = (id, nivel, tagId) => { $(id).dataset.nivel = nivel; insignia(tagId, TONO[nivel], ETIQUETA[nivel]); };
        capa('capa-modbus', e.modbus, 'modbus-tag');
        texto('modbus-estado', e.opcuaCaido ? 'SIN DATOS (OPC UA en ERROR)'
            : vigente(e.est) ? e.est.valor : `${e.est.valor ?? '—'} (${e.est.vigencia})`);
        texto('modbus-ok', m('Status/MODBUS/OK').valor);
        texto('modbus-crc', m('Status/MODBUS/CRC_ERROR').valor);
        texto('modbus-timeout', m('Status/MODBUS/TIMEOUT').valor);
        texto('modbus-exception', m('Status/MODBUS/EXCEPTION').valor);

        capa('capa-opcua', e.opcua, 'opcua-tag');
        texto('opcua-estado', vigente(e.op) ? e.op.valor : `${e.op.valor ?? '—'} (${e.op.vigencia})`);
        const lat = m('Status/MODBUS/LatenciaMs').valor;
        texto('opcua-latencia', lat === null ? '—' : `${lat} ms`);

        capa('capa-mqtt', e.mqtt, 'mqtt-tag');
        texto('mqtt-estado', red.estado !== 'CONECTADO' && red.credencialesRechazadas ? 'CREDENCIALES RECHAZADAS' : red.estado);
        texto('mqtt-reconexiones', red.reconexiones);
        texto('mqtt-reconexiones-edge', m('Status/MQTT/Reconexiones').valor);

        capa('capa-sparkplug', e.spb, 'spb-tag');
        texto('spb-estado', `NODO ${e.nodo}`);
        texto('spb-disp', e.disp);
        texto('spb-bdseq', host.nodo.bdSeq);
        texto('spb-seq', host.nodo.seq);
        texto('spb-rebirths', host.rebirthsSolicitados);
        texto('spb-rebirths-edge', m('Status/Sparkplug/Rebirths').valor);
    }

    // ---------------------------------------------------------------- Panel general
    function variable(idCaja, idMeta, x) {
        $(idCaja).dataset.v = x.vigencia;
        texto(idMeta, x.vigencia === V.DESCONOCIDO ? 'sin BIRTH: no válido' : `${x.vigencia}${x.ts ? ' · ' + edad(x.ts) : ''}`);
    }

    function dibujarGeneral(e) {
        // Cadena
        const nodoCadena = (id, tono, t) => insignia(id, tono, t);
        const enlace = (id, nivel, det) => { $(id).dataset.nivel = nivel; texto(`${id}-det`, det); };
        const lat = m('Status/MODBUS/LatenciaMs').valor;
        const campo = { ok: ['ok', 'RESPONDE'], aviso: ['warn', 'TRAMAS CON ERROR'], error: ['err', 'SIN RESPUESTA'], obsoleto: ['', 'SIN DATOS'] }[e.modbus];
        nodoCadena('n-d1', campo[0], campo[1]);
        const ultima = vista.tramas[0] ? Tr.hexABytes(vista.tramas[0].tx) : [];
        texto('n-d1-uid', ultima.length ? `Unit ID ${ultima[0]}` : 'Unit ID 1');
        enlace('l-1', e.modbus === 'ok' ? 'ok' : e.modbus === 'error' ? 'error' : '', e.modbus === 'ok' && lat !== null ? `${lat} ms por transacción` : (e.est.valor || 'sin datos'));
        nodoCadena('n-d2', e.opcua === 'ok' ? 'ok' : e.opcua === 'error' ? 'err' : '', e.opcua === 'ok' ? 'EN SERVICIO' : e.opcua === 'error' ? 'SIN SESIÓN OPC UA' : 'SIN DATOS');
        enlace('l-2', e.opcua === 'obsoleto' ? '' : e.opcua, e.opcua === 'ok' ? 'SignAndEncrypt · :4840' : 'sin sesión');
        nodoCadena('n-d3', e.nodo === V.EN_LINEA ? 'ok' : e.nodo === V.OBSOLETO ? 'err' : '', e.nodo === V.EN_LINEA ? 'EN LÍNEA' : e.nodo === V.OBSOLETO ? 'NDEATH' : 'SIN BIRTH');
        enlace('l-3', e.nodo === V.EN_LINEA ? 'ok' : e.nodo === V.OBSOLETO ? 'error' : '', e.nodo === V.EN_LINEA ? 'TLS :8883 · Protobuf' : 'sin datos del Edge Node');
        nodoCadena('n-bk', red.estado === 'CONECTADO' ? 'ok' : 'err', red.estado);
        enlace('l-4', red.estado === 'CONECTADO' ? 'ok' : 'error', 'WSS :8084 · TLS');
        nodoCadena('n-ha', red.estado === 'CONECTADO' ? 'ok' : 'err', red.estado === 'CONECTADO' ? 'STATE online' : 'DESCONECTADA');

        // Dispositivo 1
        insignia('disp-vigencia', e.disp === V.EN_LINEA ? 'ok' : e.disp === V.OBSOLETO ? 'err' : '', e.disp);
        const pul = m('Inputs/Pulsador');
        texto('pulsador-valor', pul.valor === null ? null : (pul.valor ? 'PRESIONADO' : 'SUELTO'));
        variable('v-pulsador', 'pulsador-meta', pul);
        const crudo = m('Inputs/Potenciometro');
        const pct = m('Inputs/Potenciometro_pct');
        texto('pote-crudo', crudo.valor);
        texto('pote-pct', pct.valor === null ? null : Number(pct.valor).toFixed(1));
        $('pote-barra').style.width = `${Math.max(0, Math.min(100, pct.valor || 0))}%`;     // CSSOM: permitido por la CSP
        variable('v-pote', 'pote-meta', crudo);
        const led = m('Outputs/LedDigital');
        texto('led-valor', led.valor === null ? null : (led.valor ? 'ENCENDIDO' : 'APAGADO'));
        variable('v-led', 'led-meta', led);
        const pwm = m('Outputs/LedPWM');
        texto('pwm-valor', pwm.valor);
        $('pwm-barra').style.width = `${Math.round(((pwm.valor || 0) / 255) * 100)}%`;
        variable('v-pwm', 'pwm-meta', pwm);

        // Controles: habilitados solo con el dispositivo EN LINEA y la web conectada
        const operable = e.disp === V.EN_LINEA && red.estado === 'CONECTADO';
        const btn = $('btn-led');
        btn.disabled = !operable;
        btn.setAttribute('aria-checked', String(led.valor === true));        // SOLO el valor confirmado
        texto('btn-led-texto', led.valor === null ? '—' : (led.valor ? 'ENCENDIDO · tocar para apagar' : 'APAGADO · tocar para encender'));
        const slider = $('pwm');
        slider.disabled = !operable;
        $('btn-pwm').disabled = !operable;
        if (document.activeElement !== slider && document.activeElement !== $('btn-pwm') && pwm.valor !== null && !slider.dataset.editando) {
            slider.value = pwm.valor;                                        // vuelve al confirmado
            texto('pwm-pedido', pwm.valor);
        }
        $('ctl-bloqueados').hidden = operable;
        estadoComando('cmd-led', 'Outputs/LedDigital');
        estadoComando('cmd-pwm', 'Outputs/LedPWM');

        dibujarRecorrido();
        dibujarTiempos();
    }

    function estadoComando(id, nombre) {
        const c = host.comandos.get(nombre);
        const e = $(id);
        e.dataset.estado = c ? c.estado : 'ninguno';
        const icono = { enviado: '▲', confirmado: '✔', 'sin confirmar': '✖' };
        const ms = c && c.estado === 'confirmado' ? ` en ${c.tConfirmado - c.t} ms` : '';
        texto(id, c ? `${icono[c.estado]} ${c.estado.toUpperCase()}: ${c.valor}${ms} · ${edad(c.t)}` : 'Sin comandos');
    }

    /** [DF-4.14] Recorrido del ultimo comando: capturado (bytes reales) o reconstruido. */
    function dibujarRecorrido() {
        const nombre = vista.ultimoComando;
        const c = nombre ? host.comandos.get(nombre) : null;
        $('rec-vacio').hidden = !!c;
        if (!c) { $('rec-pasos').replaceChildren(); return; }
        const conf = c.estado === 'confirmado';
        const fallo = c.estado === 'sin confirmar';
        const intermedio = conf ? 'ok' : fallo ? 'falla' : 'run';
        const led = nombre === 'Outputs/LedDigital';
        const fc = led ? 5 : 6;
        const nodeId = Mo.nodeIdDe(nombre);
        const escritura = Tr.decodificarModbus(Tr.tramaEscritura(fc, c.valor), 'peticion', Mo.variableModbus);
        const dd = vista.confirmaciones.get(nombre);
        const etiquetaPaso = (cap) => el('span', { className: `etq ${cap ? 'cap' : 'rec'}`, texto: cap ? 'CAPTURADO' : 'RECONSTRUIDO' });
        const paso = (n, clase, titulo, capa, cap, desc, segs) => el('li', { className: `step ${clase}` },
            el('span', { className: 'n', texto: n }),
            el('div', { className: 'b' },
                el('div', { className: 'cab' }, el('span', { className: 't', texto: titulo }, etiquetaPaso(cap)), el('span', { className: 'badge info', texto: capa })),
                el('div', { className: 'd', texto: desc }),
                segs && segs.length ? el('div', { className: 'bytes' }, ...bytesVista(segs)) : null));
        const nombreAlias = (a) => (host.alias.get(a) || {}).nombre;
        $('rec-pasos').replaceChildren(
            paso(1, 'ok', 'Host Application → broker', 'Sparkplug B · DCMD', true,
                `T0 ${hora(c.t)} · ${host.topicos.dcmd} · QoS 0 · sin seq · alias ${c.alias} · ${c.bytes.length} B de Protobuf`,
                Tr.segmentarPayload(c.bytes, nombreAlias).segmentos),
            paso(2, c.tEco ? 'ok' : intermedio, 'Broker → Host Application (eco)', 'MQTT', true,
                c.tEco ? `T1 ${hora(c.tEco)} · el broker devolvió el DCMD a esta página: ${c.tEco - c.t} ms de ida y vuelta` : 'Esperando que el broker devuelva el DCMD…'),
            paso(3, intermedio, 'Edge Node → servidor OPC UA', 'OPC UA · WriteRequest', false,
                `TypeId 673 · NodeId ${nodeId} · AttributeId 13 (Value) · Variant ${c.tipo} ${c.valor} · cuerpo cifrado (SignAndEncrypt): no se puede capturar desde acá`),
            paso(4, intermedio, 'Maestro MODBus → ESP32', `MODBus RTU · FC ${Tr.hex2(fc)}`, false,
                `${Tr.FUNCIONES[fc]} con CRC-16 calculado en esta página · la respuesta del esclavo es el eco, idéntica · tiene prioridad sobre el sondeo`,
                escritura.segmentos),
            paso(5, intermedio, 'Servidor OPC UA → Edge Node', 'OPC UA · WriteResponse', false,
                'TypeId 676 · StatusCode Good (0x00000000), enviado al llegar el eco MODBus y no al encolar (ADR-015)'),
            paso(6, conf ? 'ok' : intermedio, 'Edge Node → Host Application', 'Sparkplug B · DDATA', conf,
                conf ? `T4 ${hora(c.tConfirmado)} · seq ${dd ? dd.seq : c.seqConfirmacion} · valor confirmado: CONFIRMADO en ${c.tConfirmado - c.t} ms de punta a punta`
                    : fallo ? 'No volvió la confirmación: el control sigue mostrando el valor anterior (SIN CONFIRMAR)' : 'Esperando el DDATA con el valor nuevo…',
                conf && dd ? Tr.segmentarPayload(dd.bytes, nombreAlias).segmentos : null),
        );
        insignia('rec-cabecera', conf ? 'ok' : fallo ? 'err' : 'info',
            `${nombre} = ${c.valor} · ${conf ? `CONFIRMADO en ${c.tConfirmado - c.t} ms` : c.estado.toUpperCase()}`);
    }

    /** [DF-4.16] Marcas de tiempo y tramos del ultimo comando (ADR-028). */
    function dibujarTiempos() {
        const nombre = vista.ultimoComando;
        const c = nombre ? host.comandos.get(nombre) : null;
        if (c) {
            const marcas = [
                ['T0', 'Se publica el DCMD', 'esta página', c.t],
                ['T1', 'Vuelve el eco del DCMD desde el broker', 'esta página', c.tEco],
                ['T2', 'El maestro lee el valor nuevo (SourceTimestamp OPC UA)', 'Raspberry Pi', c.tsFuente],
                ['T3', 'El Edge Node arma el DDATA (timestamp del payload)', 'Edge Node (notebook)', c.tsPayload],
                ['T4', 'Llega la confirmación', 'esta página', c.tConfirmado],
            ];
            $('tiempos-marcas').replaceChildren(...marcas.map(([k, q, reloj, v]) => fila({ texto: k, clase: 'hex' }, q, reloj, { texto: hora(v), clase: 'hex' })));
            const dif = (a, b) => (a != null && b != null ? b - a : null);
            const ms = (d) => (d === null ? '—' : `${d} ms${d < 0 ? ' (desfase de relojes)' : ''}`);
            const lat = m('Status/MODBUS/LatenciaMs').valor;
            const tramos = [
                ['Página ↔ broker (ida y vuelta)', 'T1 − T0', dif(c.t, c.tEco), 'Exacta: un solo reloj'],
                ['Página → campo (DCMD, Write, FC 05/06)', 'T2 − T0', dif(c.t, c.tsFuente), 'Aproximada: navegador y Raspberry, vale con NTP'],
                ['Campo → Edge Node (suscripción OPC UA)', 'T3 − T2', dif(c.tsFuente, c.tsPayload), 'Aproximada: Raspberry y notebook, vale con NTP'],
                ['Edge Node → página (broker)', 'T4 − T3', dif(c.tsPayload, c.tConfirmado), 'Exacta si esta página corre en la notebook del Edge Node'],
                ['Total, de punta a punta', 'T4 − T0', dif(c.t, c.tConfirmado), 'Exacta: un solo reloj'],
                ['Transacción MODBus (última)', 'LatenciaMs', lat, 'Exacta: la mide el maestro con su reloj'],
            ];
            $('tiempos-tramos').replaceChildren(...tramos.map(([q, calc, d, ex]) => fila(q, { texto: calc, clase: 'hex' }, { texto: ms(d), clase: 'num' }, ex)));
            // Barra proporcional: solo si los tres tramos son positivos (relojes sincronizados)
            const tr = [dif(c.t, c.tsFuente), dif(c.tsFuente, c.tsPayload), dif(c.tsPayload, c.tConfirmado)];
            const barra = $('tiempos-barra');
            if (tr.every((d) => d !== null && d >= 0) && tr.some((d) => d > 0)) {
                const total = tr.reduce((a, b) => a + b, 0);
                barra.replaceChildren(...tr.map((d, i) => {
                    const s = el('div', { className: `t${i + 1}`, texto: `${d} ms`, title: ['página → campo', 'campo → Edge Node', 'Edge Node → página'][i] });
                    s.style.width = `${(d / total) * 100}%`;
                    return s;
                }));
                barra.hidden = false;
            } else {
                barra.hidden = true;
            }
        }
        const l = vista.lectura;
        if (l && l.tsFuente) {
            texto('lectura-texto', `${l.nombre} = ${l.valor}: el maestro lo leyó a las ${hora(l.tsFuente)} (SourceTimestamp, reloj de la Raspberry), `
                + `el Edge Node lo publicó a las ${hora(l.tsPayload)} y llegó a esta página a las ${hora(l.llegada)}. `
                + `Del campo a la pantalla: ${l.llegada - l.tsFuente} ms (aproximado: resta relojes distintos, vale con NTP).`);
        }
    }

    // ---------------------------------------------------------------- MODBus
    function clasificarTrama(t) {
        if (!t.rx) return ['err', 'TIMEOUT'];
        const rx = Tr.hexABytes(t.rx);
        const v = Tr.verificarCrc(rx);
        if (!v || !v.ok) return ['warn', 'CRC ERROR'];
        if (rx[1] & 0x80) return ['warn', 'EXCEPCIÓN'];
        return ['ok', 'OK'];
    }

    function dibujarModbus() {
        $('mapa-modbus').replaceChildren(...Mo.MAPA_MODBUS.map((v) => {
            const x = m(v.metrica);
            const valor = x.valor === null ? '—' : (typeof x.valor === 'boolean' ? (x.valor ? '1' : '0') : String(x.valor));
            return fila({ texto: v.metrica, clase: 'hex' }, v.senal, v.tabla, { texto: v.referencia, clase: 'hex' }, { texto: `0x${Tr.hex4(v.offset)}`, clase: 'hex' },
                { texto: `${Tr.hex2(v.fcLectura)} / ${v.fcEscritura ? Tr.hex2(v.fcEscritura) : '—'}`, clase: 'hex' }, v.tipo, v.rango,
                { texto: `${valor}${x.vigencia === V.EN_LINEA ? '' : ` (${x.vigencia})`}`, clase: 'hex' });
        }));

        if (vista.dibujado.tramas !== vista.version.tramas || vista.dibujado.selTrama !== vista.selTrama) {
            vista.dibujado.tramas = vista.version.tramas;
            vista.dibujado.selTrama = vista.selTrama;
            const sel = vista.tramas.find((t) => t.id === vista.selTrama) || vista.tramas[0];
            insignia('tramas-fuente', 'info', `${vista.tramas.length} muestra(s) · Status/MODBUS/UltimaTrama*`);
            $('tramas-lista').replaceChildren(...vista.tramas.map((t) => {
                const [tono, res] = clasificarTrama(t);
                const tx = Tr.hexABytes(t.tx);
                return el('button', { type: 'button', className: 'fi', 'aria-pressed': String(sel && t.id === sel.id),
                    onclick: () => { vista.selTrama = t.id; dibujar(); } },
                el('span', { className: 'tm', texto: hora(t.ts) }), el('span', { className: `badge ${tono}`, texto: res }),
                el('span', { className: 'sm', texto: `FC ${Tr.hex2(tx[1] || 0)} · ${Tr.FUNCIONES[(tx[1] || 0) & 0x7F] || '—'} · ${t.tx}` }));
            }));
            dibujarTramaSeleccionada(sel);
        }
    }

    function dibujarTramaSeleccionada(sel) {
        const filas = (dec) => dec.filas.map((f) => el('tr', {}, el('td', { className: 'hex', texto: f.bytes }),
            el('td', {}, el('b', { texto: f.campo }), el('br'), el('span', { className: 'muted', texto: f.significado }))));
        if (!sel) {
            texto('trama-titulo', 'Todavía no llegó ninguna trama (llegan con el NDATA del Edge Node, una vez por segundo).');
            dibujarCrc(null);
            return;
        }
        const tx = Tr.hexABytes(sel.tx);
        const dTx = Tr.decodificarModbus(tx, 'peticion', Mo.variableModbus);
        texto('trama-titulo', `${hora(sel.ts)} · FC ${Tr.hex2(dTx.fc || 0)} · ${Tr.FUNCIONES[dTx.fc] || '—'}${sel.latencia != null ? ` · latencia ${sel.latencia} ms` : ''} · capturada por el maestro`);
        $('trama-tx').replaceChildren(...bytesVista(dTx.segmentos));
        $('trama-tx-filas').replaceChildren(...filas(dTx));
        const rx = Tr.hexABytes(sel.rx);
        $('trama-sin-rx').hidden = rx.length > 0;
        const dRx = Tr.decodificarModbus(rx, 'respuesta', Mo.variableModbus);
        $('trama-rx').replaceChildren(...bytesVista(dRx.segmentos));
        $('trama-rx-filas').replaceChildren(...filas(dRx));
        dibujarCrc(tx);
    }

    /** CRC paso a paso sobre la peticion real (o un ejemplo si todavia no llego ninguna). */
    function dibujarCrc(trama) {
        const ejemplo = !trama || trama.length < 4;
        const t = ejemplo ? [1, 3, 0, 0, 0, 1, 0x84, 0x0A] : trama;          // la peticion FC 03 del banco
        const datos = t.slice(0, -2);
        const r = Tr.crcPasoAPaso(datos);
        $('crc-trama').replaceChildren(...datos.map((b) => el('span', { className: 'by data', texto: Tr.hex2(b) })),
            ...t.slice(-2).map((b) => el('span', { className: 'by crc', texto: Tr.hex2(b) })));
        $('crc-pasos').replaceChildren(...r.pasos.map((p) => fila({ texto: p.indice, clase: 'num' }, { texto: p.byte, clase: 'hex' },
            { texto: p.antes, clase: 'hex' }, { texto: p.trasXor, clase: 'hex' }, { texto: p.despues, clase: 'hex' })));
        $('crc-detalle').replaceChildren(...r.pasos[0].desplazamientos.map((d) => fila({ texto: d.n, clase: 'num' }, { texto: d.lsb, clase: 'num' },
            d.accion, { texto: d.resultado, clase: 'hex' })));
        const v = Tr.verificarCrc(t);
        const res = $('crc-resultado');
        res.className = `resultado ${v.ok ? 'ok' : 'err'}`;
        res.textContent = `${ejemplo ? 'Ejemplo (todavía no llegó una trama real): ' : ''}CRC calculado 0x${Tr.hex4(r.crc)} → viaja como ${r.enLinea}. `
            + `La trama trae ${v.recibido}: ${v.ok ? '✔ coincide' : '✖ NO coincide, se descartaría'}. `
            + `Sobre la trama entera (datos + CRC) el resultado es ${v.residuo}${v.ok ? ', como corresponde' : ''}.`;
    }

    function dibujarEstadisticaModbus() {
        const n = (x) => Number(m(x).valor || 0);
        const total = n('Status/MODBUS/OK') + n('Status/MODBUS/CRC_ERROR') + n('Status/MODBUS/TIMEOUT') + n('Status/MODBUS/EXCEPTION');
        const tarjeta = (k, v, d) => el('div', { className: 'io' }, el('div', { className: 'io-n', texto: k }), el('div', { className: 'io-v', texto: v }), el('div', { className: 'age', texto: d }));
        const lat = m('Status/MODBUS/LatenciaMs').valor;
        $('mb-stats').replaceChildren(
            tarjeta('Respondidas (OK)', n('Status/MODBUS/OK').toLocaleString('es-AR'), 'CRC válido y trama completa'),
            tarjeta('CRC_ERROR', n('Status/MODBUS/CRC_ERROR'), 'CRC inválido o trama mal formada'),
            tarjeta('TIMEOUT', n('Status/MODBUS/TIMEOUT'), 'Sin respuesta en el tiempo de espera'),
            tarjeta('Tasa de error', total ? `${(((total - n('Status/MODBUS/OK')) / total) * 100).toFixed(2)} %` : '—',
                `Sobre ${total.toLocaleString('es-AR')} transacciones (acumuladas desde siempre)`),
            tarjeta('EXCEPTION', n('Status/MODBUS/EXCEPTION'), 'El esclavo respondió con un código de error'),
            tarjeta('Latencia', lat === null ? '—' : `${lat} ms`, 'Fin de la petición → respuesta completa (incluye el conversor USB)'));
    }

    // ---------------------------------------------------------------- OPC UA
    function valorVariable(v) {
        const x = m(v.metrica);
        if (x.valor === null) return '—';
        return typeof x.valor === 'number' && !Number.isInteger(x.valor) ? x.valor.toFixed(1) : String(x.valor);
    }

    function dibujarOpcua() {
        const variables = new Map(Mo.VARIABLES_OPCUA.map((v) => [v.id, v]));
        $('ua-arbol').replaceChildren(...Mo.ARBOL.map((n) => {
            const v = variables.get(n.id);
            const b = el('button', { type: 'button', className: 'tn', 'aria-pressed': String(vista.selNodo === n.id),
                onclick: () => { vista.selNodo = n.id; dibujar(); } },
            el('span', { className: `ic ${v ? 'v' : 'o'}`, texto: v ? 'VAR' : 'OBJ' }),
            el('span', { texto: n.etiqueta || n.id.split('.').pop() }), v ? el('span', { className: 'vv', texto: valorVariable(v) }) : null);
            b.style.paddingLeft = `${8 + n.nivel * 16}px`;
            return b;
        }));

        const v = variables.get(vista.selNodo);
        let attrs;
        if (v) {
            const x = m(v.metrica);
            const rw = v.acceso === 'RW';
            texto('ua-attr-lead', rw ? 'Variable escribible: un Write con el usuario operador termina en una escritura MODBus.'
                : 'Variable de solo lectura: un Write devuelve BadNotWritable (0x803B0000), verificado.');
            attrs = [['NodeId', `ns=1;s=${v.id}`], ['NodeClass', 'Variable'], ['BrowseName', `1:${v.id.split('.').pop()}`],
                ['DisplayName', v.id.split('.').pop()], ['DataType', v.tipo], ['ValueRank', '−1 (escalar)'],
                ['AccessLevel', rw ? 'CurrentRead + CurrentWrite' : 'CurrentRead'],
                ['UserAccessLevel', rw ? 'CurrentRead + CurrentWrite (operador) · CurrentRead (anónimo)' : 'CurrentRead'],
                ['EURange', v.euRange], ['Value', valorVariable(v)],
                ['SourceTimestamp', x.ts ? new Date(x.ts).toISOString() : '—'],
                ['Métrica Sparkplug', v.metrica], ['Vigencia del dato', x.vigencia]];
        } else {
            const n = Mo.ARBOL.find((a) => a.id === vista.selNodo) || Mo.ARBOL[0];
            const hijos = Mo.ARBOL.filter((a) => a.id !== n.id && a.id.startsWith(`${n.id}.`)).length;
            texto('ua-attr-lead', n.id === 'Dispositivo1.Mapa' ? 'El mapa de registros vigente del maestro (I-04): cambia en vivo si se reconfigura desde Node-RED.'
                : 'Objeto contenedor: agrupa variables para que la jerarquía sea navegable.');
            attrs = [['NodeId', n.nodeId || '(objeto del dispositivo, ns=1)'], ['NodeClass', 'Object'],
                ['BrowseName', n.id === 'Objects' ? '0:Objects' : `1:${n.etiqueta}`], ['Nodos debajo', hijos || '—']];
        }
        $('ua-attrs').replaceChildren(...attrs.map(([k, val]) => fila({ texto: k, clase: '' }, { texto: val, clase: 'hex' })));

        $('ua-nodos').replaceChildren(...Mo.VARIABLES_OPCUA.map((x) => fila({ texto: `ns=1;s=${x.id}`, clase: 'hex' }, x.tipo,
            x.acceso === 'RW' ? 'Read + Write' : 'Read', x.euRange, { texto: valorVariable(x), clase: 'hex' })));

        if (vista.dibujado.notificaciones !== vista.version.notificaciones) {
            vista.dibujado.notificaciones = vista.version.notificaciones;
            $('ua-notifs').replaceChildren(...vista.notificaciones.map((n) => el('li', {},
                el('span', { texto: hora(n.t) }), el('span', { texto: `DataChange · ${n.nodeId} = ${n.valor} · Good` }))));
        }
    }

    // ---------------------------------------------------------------- Sparkplug
    const TONO_MENSAJE = { NBIRTH: 'ok', DBIRTH: 'ok', NDATA: 'info', DDATA: 'info', NDEATH: 'err', DDEATH: 'err', NCMD: 'warn', DCMD: 'warn', STATE: '' };

    function dibujarSparkplug() {
        texto('spb-f-bdseq', host.nodo.bdSeq);
        texto('spb-f-seq', host.nodo.seq);
        if (vista.dibujado.mensajes !== vista.version.mensajes || vista.dibujado.selMensaje !== vista.selMensaje) {
            vista.dibujado.mensajes = vista.version.mensajes;
            vista.dibujado.selMensaje = vista.selMensaje;
            const sel = vista.mensajes.find((x) => x.id === vista.selMensaje) || vista.mensajes[0];
            $('spb-lista').replaceChildren(...vista.mensajes.map((x) => el('button', { type: 'button', className: 'fi',
                'aria-pressed': String(sel && x.id === sel.id), onclick: () => { vista.selMensaje = x.id; dibujar(); } },
            el('span', { className: 'tm', texto: hora(x.t) }), el('span', { className: `badge ${TONO_MENSAJE[x.tipo]}`, texto: x.tipo }),
            el('span', { className: 'sm', texto: `${x.seq !== null && x.seq !== undefined ? `seq ${x.seq} · ` : ''}${x.resumen}` }))));
            if (sel) {
                texto('spb-topico', sel.topico);
                if (sel.tipo === 'STATE') {
                    $('spb-bytes').replaceChildren(...Array.from(sel.bytes, (b) => el('span', { className: 'by name', texto: Tr.hex2(b) })));
                    $('spb-filas').replaceChildren(fila({ texto: sel.resumen, clase: 'hex' }, 'JSON: STATE es la única excepción a Protobuf (Sparkplug 3.0)'));
                    texto('spb-tam', `STATE · ${sel.bytes.length} bytes de JSON`);
                } else {
                    const s = Tr.segmentarPayload(sel.bytes, (a) => (host.alias.get(a) || {}).nombre);
                    $('spb-bytes').replaceChildren(...bytesVista(s.segmentos));
                    $('spb-filas').replaceChildren(...s.filas.map((f) => fila({ texto: f.bytes, clase: 'hex' }, f.campo)));
                    texto('spb-tam', `${sel.tipo} · ${sel.bytes.length} bytes de payload Protobuf${s.completo ? '' : ' · no se pudo decodificar entero'}`);
                }
            }
        }
        $('spb-tipos').replaceChildren(...Mo.TIPOS_MENSAJE.map((t) => fila({ texto: t.tipo, clase: '' }, t.quien, t.cuando,
            { texto: vista.conteo[t.tipo] || 0, clase: 'num' })));
        $('spb-metricas').replaceChildren(...Mo.METRICAS.map((x) => {
            const v = m(x.nombre);
            const valor = v.valor === null ? '—' : typeof v.valor === 'number' && !Number.isInteger(v.valor) ? v.valor.toFixed(1) : String(v.valor);
            return fila({ texto: x.nombre, clase: 'hex' }, { texto: x.alias ?? '—', clase: 'num' }, x.tipo,
                { texto: `${valor}${v.vigencia === V.EN_LINEA ? '' : ` (${v.vigencia})`}`, clase: 'hex' });
        }));
    }

    function dibujar() {
        if (!host || red.fase !== 'operando') return;
        const e = estados();
        dibujarCapas(e);
        if (pestana === 'general') dibujarGeneral(e);
        else if (pestana === 'modbus') { dibujarModbus(); dibujarEstadisticaModbus(); }
        else if (pestana === 'opcua') dibujarOpcua();
        else if (pestana === 'sparkplug') dibujarSparkplug();
    }

    // =========================================================================
    // Pestanas
    // =========================================================================

    function fijarPestana(id) {
        pestana = id;
        for (const p of PESTANAS) {
            $(`t-${p}`).setAttribute('aria-selected', String(p === id));
            $(`t-${p}`).tabIndex = p === id ? 0 : -1;
            $(`p-${p}`).hidden = p !== id;
        }
        history.replaceState(null, '', `#${id}`);
        vista.dibujado = {};                          // la pestana nueva se dibuja completa
        dibujar();
    }

    // =========================================================================
    // Inicio [DF-4.1]
    // =========================================================================

    async function iniciar() {
        cfg = window.PDCI_CONFIG;
        const v = validarConfig(cfg);
        const error = v.error || (!window.mqtt || !window.protobuf || !window.Sparkplug || !Tr || !Mo
            ? 'No se cargaron las bibliotecas (vendor/ o los módulos de la página): ver README.' : null);
        if (error) {
            errorIngreso(`✖ ${error}`);
            $('btn-entrar').disabled = true;
            return;
        }
        if (v.aviso) $('login-estado').textContent = `▲ ${v.aviso}`;
        if (cfg.usuario) $('usuario').value = cfg.usuario;            // sugerencia opcional: el usuario no es secreto
        texto('login-broker', brokerHost());
        texto('ids', `PdCI · TP Nº3 · grupo ${cfg.grupo} · nodo ${cfg.nodo} · dispositivo ${cfg.dispositivo} · host ${cfg.hostId}`);
        const nombreBroker = new URL(cfg.url).hostname;                   // corto, para la tarjeta
        texto('mqtt-broker', nombreBroker.length > 24 ? nombreBroker.split('.').slice(-2).join('.') : nombreBroker);
        texto('n-bk-host', brokerHost());
        texto('spb-broker', brokerHost());
        texto('top-grupo', cfg.grupo);
        texto('top-nodo', cfg.nodo);
        texto('top-disp', cfg.dispositivo);
        texto('top-state', `spBv1.0/STATE/${cfg.hostId}`);

        let proto;
        try {
            const resp = await fetch('proto/sparkplug_b.proto', { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            proto = await resp.text();
        } catch (e) {
            errorIngreso(`✖ No se pudo cargar proto/sparkplug_b.proto (${e.message}). ¿Se abrió con file://? Usar el servidor (README).`);
            $('btn-entrar').disabled = true;
            return;
        }
        const codec = window.Sparkplug.crearCodec(window.protobuf, proto);
        host = new window.Sparkplug.HostSparkplug({ codec, grupo: cfg.grupo, nodo: cfg.nodo,
            dispositivo: cfg.dispositivo, hostId: cfg.hostId });

        $('form-login').addEventListener('submit', alEnviarIngreso);
        $('btn-salir').addEventListener('click', salir);
        for (const p of PESTANAS) $(`t-${p}`).addEventListener('click', () => fijarPestana(p));
        // Flechas izquierda/derecha entre pestanas (patron ARIA de tabs)
        $('t-general').parentElement.addEventListener('keydown', (ev) => {
            if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
            const i = (PESTANAS.indexOf(pestana) + (ev.key === 'ArrowRight' ? 1 : PESTANAS.length - 1)) % PESTANAS.length;
            fijarPestana(PESTANAS[i]);
            $(`t-${PESTANAS[i]}`).focus();
        });

        $('btn-led').addEventListener('click', () => {
            const actual = host.metrica('Outputs/LedDigital').valor;
            if (actual === null) return;
            vista.ultimoComando = 'Outputs/LedDigital';
            aplicar(host.comandar('Outputs/LedDigital', !actual));
        });
        const slider = $('pwm');
        slider.addEventListener('input', () => { slider.dataset.editando = '1'; texto('pwm-pedido', slider.value); });
        $('btn-pwm').addEventListener('click', () => {
            delete slider.dataset.editando;
            vista.ultimoComando = 'Outputs/LedPWM';
            aplicar(host.comandar('Outputs/LedPWM', Number(slider.value)));
        });

        // Cierre intencional: STATE offline con la hora actual ANTES de desconectar (mejor esfuerzo).
        window.addEventListener('pagehide', () => {
            if (cliente && cliente.connected) {
                cliente.publish(host.topicos.state, window.Sparkplug.payloadState(false, Date.now()), { qos: 1, retain: true });
                cliente.end(false);
            }
        });

        registrar('info', 'Host Application iniciada · sparkplug_b.proto cargado');
        $('usuario').value ? $('clave').focus() : $('usuario').focus();
        setInterval(() => {
            if (!host || red.fase !== 'operando') return;
            aplicar(host.tick());
            const ahora = Date.now();
            if (sucio || ahora - ultimoDibujo > 1000) {           // 1 s: refresca las "hace X s"
                dibujar();
                sucio = false;
                ultimoDibujo = ahora;
            }
        }, 250);
    }

    iniciar();
}());
