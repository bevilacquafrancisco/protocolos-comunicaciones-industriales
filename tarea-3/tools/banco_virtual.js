/**
 * banco_virtual.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-12
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * "Banco virtual" de la Tarea 3: levanta la cadena COMPLETA con el software real y sin hardware,
 * inyecta las fallas del plan de pruebas N4, mide y guarda la evidencia (F7).
 *
 *   simulador (stack del firmware) --TCP 5020--> Node-RED (maestro + servidor OPC UA)
 *     --opc.tcp 4840, SignAndEncrypt + usuario--> Edge Node --TLS--> proxy_corte --> broker (amqtt)
 *     --WebSocket--> Host Application en Chrome         observador (verifica seq/bdSeq) --TLS--> broker
 *
 * Lo unico que no es el producto: el ESP32 (lo reemplaza el simulador, que ejecuta SU stack), el
 * bus RS-485 (TCP con la misma trama RTU) y el broker en la nube (amqtt local con TLS). Todo lo
 * medido aca es "en la PC" y se informa asi (docs/mediciones.md).
 *
 * Modos:
 *   node tools/banco_virtual.js campana    [--salida <dir>]   fallas F-01..F-10, latencias, trafico, capturas
 *   node tools/banco_virtual.js resistencia [--minutos 30] [--salida <dir>]   memoria y seq en el tiempo
 *   node tools/banco_virtual.js levantar                       solo la cadena (para scripts/inyectar-fallas.sh)
 *
 * Requisitos: venv de gateway-sparkplug, npm ci en edge-nodered y hmi-web, Chrome, Wireshark
 * (dumpcap y tshark) para las capturas, y la PKI OPC UA de F4/F5 ya confiada (README F5 §5).
 *
 * Dependencias externas: puppeteer-core (de hmi-web/node_modules), Node >= 18.
 */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');

const T3 = path.join(__dirname, '..');
const GW = path.join(T3, 'gateway-sparkplug');
const NR = path.join(T3, 'edge-nodered');
const WEB = path.join(T3, 'hmi-web');
const WIN = process.platform === 'win32';
const PY = path.join(GW, '.venv', WIN ? 'Scripts/python.exe' : 'bin/python');
const CHROME = process.env.CHROME_PATH || ['C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome',
    '/usr/bin/chromium'].find((p) => fs.existsSync(p));
const WS_BIN = WIN ? 'C:/Program Files/Wireshark' : '/usr/bin';
const DUMPCAP = path.join(WS_BIN, WIN ? 'dumpcap.exe' : 'dumpcap');
const INTERFAZ_LOOPBACK = WIN ? '\\Device\\NPF_Loopback' : 'lo';
const PUERTOS = { modbus: 5020, opcua: 4840, broker: 28883, ws: 28884, proxy: 28893, nodered: 1880 };

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const ahora = () => Date.now();

// =============================================================================
// Procesos
// =============================================================================

class Proceso {
    /**
     * Lanza un proceso y espera una linea "marca" en su salida.
     * @param {string} nombre  para el registro
     * @param {string} cmd, @param {string[]} args, @param {object} o {cwd, env, marca, log}
     */
    constructor(nombre, cmd, args, { cwd, env = {}, log }) {
        this.nombre = nombre;
        this.lineas = [];
        this.oyentes = [];
        this.p = spawn(cmd, args, { cwd, env: Object.assign({}, process.env, env, { PYTHONUNBUFFERED: '1' }) });
        const archivo = fs.createWriteStream(log, { flags: 'a' });
        const leer = (d) => {
            archivo.write(d);
            for (const linea of String(d).split(/\r?\n/)) {
                if (!linea) continue;
                const t = ahora();
                this.lineas.push({ t, linea });
                for (const o of this.oyentes) o(linea, t);
            }
        };
        this.p.stdout.on('data', leer);
        this.p.stderr.on('data', leer);
        this.terminado = new Promise((r) => this.p.on('exit', r));
    }

    /** Espera una linea que cumpla 'patron' (desde 'desde' ms). @returns {Promise<{t, linea}>} */
    esperarLinea(patron, timeoutMs = 30000, desde = 0) {
        const previa = this.lineas.find((l) => l.t >= desde && patron.test(l.linea));
        if (previa) return Promise.resolve(previa);
        return new Promise((resolver, rechazar) => {
            const t = setTimeout(() => rechazar(new Error(`${this.nombre}: sin "${patron}" en ${timeoutMs} ms`)), timeoutMs);
            const oyente = (linea, ts) => {
                if (ts >= desde && patron.test(linea)) {
                    clearTimeout(t);
                    this.oyentes = this.oyentes.filter((o) => o !== oyente);
                    resolver({ t: ts, linea });
                }
            };
            this.oyentes.push(oyente);
        });
    }

    escribir(texto) { this.p.stdin.write(texto + '\n'); }

    /** Termina el ARBOL de procesos sin aviso (kill -9 / TerminateProcess): es la falla, no un cierre. */
    matar() {
        if (this.p.exitCode !== null) return this.terminado;
        if (WIN) spawnSync('taskkill', ['/F', '/T', '/PID', String(this.p.pid)]);
        else this.p.kill('SIGKILL');
        return this.terminado;
    }
}

/** Arbol de procesos de un PID (Windows: el python del venv es un lanzador que crea un hijo). */
function memoriaArbol(pids) {
    if (!WIN) return {};
    const ps = spawnSync('powershell', ['-NoProfile', '-Command',
        'Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,WorkingSetSize | ConvertTo-Json -Compress'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    const todos = JSON.parse(ps.stdout || '[]');
    const hijos = new Map();
    for (const p of todos) hijos.set(p.ParentProcessId, (hijos.get(p.ParentProcessId) || []).concat(p));
    const porPid = new Map(todos.map((p) => [p.ProcessId, p]));
    const salida = {};
    for (const [nombre, pid] of Object.entries(pids)) {
        let total = 0;
        const pila = [pid];
        const vistos = new Set();
        while (pila.length) {
            const actual = pila.pop();
            if (vistos.has(actual)) continue;
            vistos.add(actual);
            const p = porPid.get(actual);
            if (p) total += Number(p.WorkingSetSize);
            for (const h of hijos.get(actual) || []) pila.push(h.ProcessId);
        }
        salida[nombre] = Math.round(total / 1024 / 1024 * 10) / 10;      // MiB
    }
    return salida;
}

// =============================================================================
// Observador (lee el JSONL que escribe tools/observador_sparkplug.py)
// =============================================================================

class Lector {
    constructor(archivo) { this.archivo = archivo; this.mensajes = []; this._leidos = 0; }

    actualizar() {
        if (!fs.existsSync(this.archivo)) return;
        // Solo lineas COMPLETAS: el observador puede estar escribiendo la ultima, y una linea a
        // medias rompia JSON.parse (en la segunda corrida F-07 "no veia" un NBIRTH que si llego).
        const texto = fs.readFileSync(this.archivo, 'utf8');
        const lineas = texto.slice(0, texto.lastIndexOf('\n') + 1).split('\n').filter(Boolean);
        for (const l of lineas.slice(this._leidos)) {
            const m = JSON.parse(l);
            m.t = Date.parse(m.ts);
            this.mensajes.push(m);
        }
        this._leidos = lineas.length;
    }

    /** Primer mensaje desde 'desde' que cumple 'cond'. @returns {Promise<object>} */
    async esperar(cond, desde, timeoutMs = 30000) {
        const fin = ahora() + timeoutMs;
        for (;;) {
            this.actualizar();
            const m = this.mensajes.find((x) => x.t >= desde && cond(x));
            if (m) return m;
            if (ahora() > fin) throw new Error(`observador: timeout (${timeoutMs} ms)`);
            await esperar(50);
        }
    }
}
const valorDe = (m, nombre) => ((m.metricas || []).find((x) => x.nombre === nombre) || {}).valor;
const tiene = (m, nombre, valor) => (m.metricas || []).some((x) => x.nombre === nombre && (valor === undefined || x.valor === valor));

// =============================================================================
// La cadena
// =============================================================================

class Cadena {
    constructor(dir) {
        this.dir = dir;
        this.p = {};
        this.claves = { edge: rand(), host: rand(), obs: rand(), opcua: rand() };
        this.lector = new Lector(path.join(dir, 'observador.jsonl'));
    }

    log(n) { return path.join(this.dir, `${n}.log`); }

    async verificarRequisitos() {
        const faltan = [];
        if (!fs.existsSync(PY)) faltan.push(`venv de gateway-sparkplug (${PY})`);
        if (!CHROME) faltan.push('Chrome (o CHROME_PATH)');
        if (!fs.existsSync(path.join(NR, 'node_modules', 'node-red'))) faltan.push('npm ci en edge-nodered');
        if (!fs.existsSync(path.join(WEB, 'node_modules', 'puppeteer-core'))) faltan.push('npm ci en hmi-web');
        if (!fs.existsSync(path.join(GW, 'pki', 'servidor_cert.der'))) faltan.push('PKI OPC UA del dispositivo 3 (README F5 §5)');
        if (faltan.length) throw new Error(`faltan: ${faltan.join(', ')}`);
    }

    async iniciarBroker() {
        this.p.broker = new Proceso('broker', PY, ['tools/broker_dev.py', '--carpeta', path.join(this.dir, 'broker'),
            '--puerto', String(PUERTOS.broker), '--puerto-ws', String(PUERTOS.ws)], { cwd: GW, log: this.log('broker'),
            env: { DEV_MQTT_CLAVE_EDGE: this.claves.edge, DEV_MQTT_CLAVE_HOST: this.claves.host, DEV_MQTT_CLAVE_OBSERVADOR: this.claves.obs } });
        await this.p.broker.esperarLinea(/Ctrl\+C/);
        this.ca = path.join(this.dir, 'broker', 'ca.pem');
    }

    async iniciarProxy() {
        this.p.proxy = new Proceso('proxy', PY, ['tools/proxy_corte.py', '--escucha', String(PUERTOS.proxy),
            '--destino', `127.0.0.1:${PUERTOS.broker}`], { cwd: GW, log: this.log('proxy') });
        await this.p.proxy.esperarLinea(/LISTO/);
    }

    async iniciarSimulador(script = 'simuladores/esclavo_modbus_sim.py') {
        this.p.sim = new Proceso('simulador', PY, [script, '--tcp', `127.0.0.1:${PUERTOS.modbus}`], { cwd: T3, log: this.log('simulador') });
        await this.p.sim.esperarLinea(/LISTO/);
    }

    async iniciarNodeRed() {
        // Configuracion del maestro en un archivo temporal (no se toca la de desarrollo)
        const config = JSON.parse(fs.readFileSync(path.join(NR, 'config', 'config.default.json'), 'utf8'));
        Object.assign(config.puerto, { tipo: 'tcp', tcp: `127.0.0.1:${PUERTOS.modbus}` });
        this.rutaConfig = this.rutaConfig || path.join(this.dir, 'maestro-config.json');
        if (!fs.existsSync(this.rutaConfig)) fs.writeFileSync(this.rutaConfig, JSON.stringify(config, null, 2));
        if (!this.hashOpcua) this.hashOpcua = await require(path.join(NR, 'lib', 'credenciales')).hashearClave(this.claves.opcua);
        this.p.nodered = new Proceso('nodered', process.execPath, [path.join(NR, 'node_modules', 'node-red', 'red.js'),
            '--settings', 'settings.js', '--userDir', '.node-red'], { cwd: NR, log: this.log('nodered'),
            env: { PDCI_T3_CONFIG: this.rutaConfig, PDCI_T3_OPCUA_USUARIO: 'operador', PDCI_T3_OPCUA_HASH: this.hashOpcua } });
        await this.p.nodered.esperarLinea(/Status\.OPCUA\.Estado = DONE/, 60000);
    }

    async iniciarEdge({ seguridad = 'SignAndEncrypt', claveMqtt } = {}) {
        const env = path.join(this.dir, 'dev3.env');
        fs.writeFileSync(env, [`MQTT_HOST=127.0.0.1`, `MQTT_PUERTO_TLS=${PUERTOS.proxy}`, 'MQTT_USUARIO_EDGE=edge_node',
            `MQTT_CLAVE_EDGE=${claveMqtt || this.claves.edge}`, `OPCUA_URL=opc.tcp://127.0.0.1:${PUERTOS.opcua}`,
            `OPCUA_SEGURIDAD=${seguridad}`, 'OPCUA_CLIENTE_USUARIO=operador', `OPCUA_CLIENTE_CLAVE=${this.claves.opcua}`, ''].join('\n'));
        this.p.edge = new Proceso('edge', PY, ['src/sparkplug_edge_node.py', '--env', env, '--mqtt-ca', this.ca,
            '--estado', path.join(this.dir, 'bdseq.json'), '--logs', path.join(this.dir, 'logs')], { cwd: GW, log: this.log('edge') });
    }

    async iniciarObservador() {
        const env = path.join(this.dir, 'obs.env');
        fs.writeFileSync(env, `MQTT_USUARIO_OBSERVADOR=observador\nMQTT_CLAVE_OBSERVADOR=${this.claves.obs}\n`);
        this.p.obs = new Proceso('observador', PY, ['-u', 'tools/observador_sparkplug.py', '--env', env, '--host', '127.0.0.1',
            '--puerto', String(PUERTOS.broker), '--mqtt-ca', this.ca, '--salida', path.join(this.dir, 'observador.jsonl')],
        { cwd: GW, log: this.log('observador') });
        await this.p.obs.esperarLinea(/observando/);
    }

    configWeb(clave = this.claves.host) {
        return `window.PDCI_CONFIG = Object.freeze({ url: 'ws://127.0.0.1:${PUERTOS.ws}/mqtt', usuario: 'host_app', clave: '${clave}',
            grupo: 'UNRaf_PdCI_2026', nodo: 'EN01_Gateway', dispositivo: 'DEV01_ESP32_Slave', hostId: 'HA01_WebDashboard' });`;
    }

    async iniciarWeb() {
        const { crearServidor } = require(path.join(WEB, 'tools', 'servir'));
        this.claveWeb = this.claves.host;
        this.servidorWeb = crearServidor(WEB, { config: undefined });
        // config dinamica: permite abrir una pagina con credenciales malas (F-09)
        this.servidorWeb.removeAllListeners('request');
        const base = crearServidor(WEB, {});
        this.servidorWeb.on('request', (req, res) => {
            // /mala/...: la misma pagina con una clave incorrecta (F-09 desde el menu, a mano).
            const mala = req.url.startsWith('/mala/');
            if (mala) req.url = req.url.slice('/mala'.length);
            if (req.url.startsWith('/config.js')) {
                res.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'no-store' });
                res.end(this.configWeb(mala || new URL(req.url, 'http://x').searchParams.get('mala') ? 'clave-incorrecta' : this.claveWeb));
                return;
            }
            base.emit('request', req, res);
        });
        await new Promise((r) => this.servidorWeb.listen(0, '127.0.0.1', r));
        this.urlWeb = `http://127.0.0.1:${this.servidorWeb.address().port}/`;
        const puppeteer = require(path.join(WEB, 'node_modules', 'puppeteer-core'));
        this.navegador = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
        this.pagina = await this.abrirPagina();
    }

    async abrirPagina() {
        const p = await this.navegador.newPage();
        await p.setViewport({ width: 1366, height: 900 });
        await p.goto(this.urlWeb, { waitUntil: 'load' });
        // Marcas de tiempo de cada cambio visible (para la latencia extremo a extremo)
        await p.evaluate(() => {
            window.__cambios = [];
            const vigilar = (id, opciones) => new MutationObserver(() => window.__cambios.push({
                id, t: Date.now(), texto: document.getElementById(id).textContent,
                estado: document.getElementById(id).dataset.estado })).observe(document.getElementById(id), opciones);
            vigilar('pulsador-valor', { childList: true, characterData: true, subtree: true });
            vigilar('cmd-led', { attributes: true, attributeFilter: ['data-estado'] });
        });
        return p;
    }

    async enLinea(timeoutMs = 60000) {
        await this.pagina.waitForFunction(() => document.getElementById('spb-estado').textContent === 'NODO EN LÍNEA'
            && document.getElementById('disp-vigencia').textContent === 'EN LÍNEA', { timeout: timeoutMs });
    }

    async levantar() {
        await this.verificarRequisitos();
        fs.mkdirSync(this.dir, { recursive: true });
        await this.iniciarBroker();
        await this.iniciarProxy();
        await this.iniciarObservador();
        await this.iniciarSimulador();
        await this.iniciarNodeRed();
        await this.iniciarEdge();
        await this.iniciarWeb();
        await this.enLinea();
    }

    pids() {
        const r = {};
        for (const [n, pr] of Object.entries(this.p)) if (pr.p.exitCode === null) r[n] = pr.p.pid;
        if (this.navegador && this.navegador.process()) r.chrome = this.navegador.process().pid;
        return r;
    }

    async bajar() {
        if (this.navegador) await this.navegador.close().catch(() => {});
        if (this.servidorWeb) this.servidorWeb.close();
        for (const pr of Object.values(this.p)) await pr.matar();
    }
}

function rand() { return crypto.randomBytes(12).toString('base64url'); }

/** Captura con dumpcap durante 'segundos' (autostop: el pcapng queda bien cerrado). */
function capturar(archivo, filtro, segundos) {
    if (!fs.existsSync(DUMPCAP)) return Promise.resolve(null);
    return new Promise((r) => {
        const p = spawn(DUMPCAP, ['-q', '-i', INTERFAZ_LOOPBACK, '-f', filtro, '-a', `duration:${segundos}`, '-w', archivo]);
        p.on('exit', () => r(archivo));
    });
}

// =============================================================================
// Campana
// =============================================================================

async function campana(dir, fases) {
    const c = new Cadena(dir);
    const hacer = (f) => !fases || fases.includes(f);
    const R = { fecha: new Date().toISOString(), commit: git('rev-parse --short HEAD'), fallas: {}, latencias: {}, ventanas: {}, capturas: {} };
    const guardar = () => fs.writeFileSync(path.join(dir, 'resultados.json'), JSON.stringify(R, null, 2));
    const foto = async (nombre) => { await c.pagina.screenshot({ path: path.join(dir, `${nombre}.png`) }); R.capturas[nombre] = `${nombre}.png`; };
    const paso = (t) => console.log(`[${new Date().toISOString().slice(11, 23)}] ${t}`);
    try {
        paso('levantando la cadena completa');
        await c.levantar();
        await esperar(3000);
        await foto('web-modbus-done-opcua-done');

        // ------------------------------------------------------------ latencia de lectura
        if (hacer('latencia')) {
        paso('latencia de lectura: pulsador del simulador -> pantalla (40 muestras)');
        c.p.sim.escribir('pulsador 0');
        await esperar(1500);
        const lect = [];
        for (let i = 0; i < 40; i++) {
            const valor = i % 2 === 0;
            const t0 = ahora();
            c.p.sim.escribir(`pulsador ${valor ? 1 : 0}`);
            const texto = valor ? 'PRESIONADO' : 'LIBRE';
            await c.pagina.waitForFunction((t, x) => window.__cambios.some((m) => m.id === 'pulsador-valor' && m.t >= t && m.texto.includes(x)),
                { timeout: 10000 }, t0, texto);
            const tw = await c.pagina.evaluate((t, x) => window.__cambios.find((m) => m.id === 'pulsador-valor' && m.t >= t && m.texto.includes(x)).t, t0, texto);
            const dd = await c.lector.esperar((m) => m.tipo === 'DDATA' && tiene(m, 'Inputs/Pulsador', valor), t0, 10000);
            const ts = (dd.metricas.find((x) => x.nombre === 'Inputs/Pulsador') || {}).timestamp;
            lect.push({ t0, campoAopcua: ts - t0, opcuaAbroker: dd.t - ts, brokerAweb: tw - dd.t, total: tw - t0 });
            await esperar(700 + Math.random() * 500);            // fase aleatoria respecto del ciclo de 250 ms
        }
        R.latencias.lectura = lect;
        guardar();

        // ------------------------------------------------------------ latencia de comando
        paso('latencia de comando: clic en la web -> LED del simulador -> CONFIRMADO (30 muestras)');
        const cmd = [];
        for (let i = 0; i < 30; i++) {
            const actual = await c.pagina.$eval('#btn-led', (e) => e.getAttribute('aria-checked') === 'true');
            const t0 = await c.pagina.evaluate(() => { const t = Date.now(); document.getElementById('btn-led').click(); return t; });
            const led = await c.p.sim.esperarLinea(new RegExp(`LED digital=${actual ? 0 : 1}`), 10000, t0);
            await c.pagina.waitForFunction((t) => window.__cambios.some((m) => m.id === 'cmd-led' && m.t >= t && m.estado === 'confirmado'),
                { timeout: 10000 }, t0);
            const tc = await c.pagina.evaluate((t) => window.__cambios.find((m) => m.id === 'cmd-led' && m.t >= t && m.estado === 'confirmado').t, t0);
            cmd.push({ t0, alLed: led.t - t0, aConfirmado: tc - t0 });
            await esperar(800 + Math.random() * 400);
        }
        R.latencias.comando = cmd;
        guardar();
        }

        // ------------------------------------------------------------ trafico: regimen y reposo
        const filtro = Object.entries(PUERTOS).filter(([k]) => ['modbus', 'opcua', 'proxy', 'ws'].includes(k))
            .map(([, v]) => `tcp port ${v}`).join(' or ');
        if (hacer('trafico')) for (const [nombre, preparar] of [['regimen', 'auto on'], ['reposo', 'pote 1000']]) {
            paso(`trafico en ${nombre} (60 s)`);
            if (nombre === 'reposo') c.p.sim.escribir('pulsador 0');
            c.p.sim.escribir(preparar);
            await esperar(3000);
            const t0 = ahora();
            const archivo = await capturar(path.join(dir, `trafico-${nombre}.pcapng`), filtro, 60);
            R.ventanas[nombre] = { t0, t1: ahora(), pcap: archivo && path.basename(archivo) };
            guardar();
        }

        // ------------------------------------------------------------ eficiencia: una word (DCMD LedPWM)
        if (hacer('eficiencia')) {
        paso('eficiencia: DCMD LedPWM en SignAndEncrypt y en None (captura de las tres capas)');
        for (const modo of ['SignAndEncrypt', 'None']) {
            if (modo === 'None') {
                await c.p.edge.matar();
                await c.iniciarEdge({ seguridad: 'None' });
                await c.enLinea();
            }
            const archivo = path.join(dir, `eficiencia-${modo}.pcapng`);
            const cap = capturar(archivo, filtro, 14);
            await esperar(2000);
            const marcas = [];
            for (const v of [11, 22, 33, 44, 55]) {
                marcas.push(ahora());
                await c.pagina.evaluate((x) => { const s = document.getElementById('pwm'); s.value = x; s.dispatchEvent(new Event('change')); }, v);
                await esperar(2000);
            }
            await cap;
            R.capturas[`eficiencia-${modo}`] = { pcap: path.basename(archivo), marcas };
            guardar();
        }
        await c.p.edge.matar();
        await c.iniciarEdge();
        await c.enLinea();

        // ------------------------------------------------------------ captura del bus (sniffer virtual)
        paso('captura del enlace MODBus (transporte TCP de desarrollo, 5 s)');
        await capturar(path.join(dir, 'modbus-rtu-tcpdev.pcapng'), `tcp port ${PUERTOS.modbus}`, 5);
        R.capturas.modbus = 'modbus-rtu-tcpdev.pcapng';
        }

        // ------------------------------------------------------------ fallas
        const falla = async (id, desc, inyectar, detectado, restaurar, recuperado, fotos = {}) => {
            paso(`${id}: ${desc}`);
            const r = { id, desc };
            let restaurado = false;
            try {
                let ti = ahora();
                const marca = await inyectar();
                // Solo una marca EXPLICITA {t}: matar() devuelve el codigo de salida del proceso, que
                // es un numero y se tomaba como instante (deteccion de 1,79e12 ms en la segunda corrida).
                if (marca && typeof marca.t === 'number') ti = marca.t;
                r.inyeccion = ti;
                const d = await detectado(ti);
                r.deteccionMs = d.t - ti;
                r.detalleDeteccion = d.detalle;
                if (fotos.durante) await foto(fotos.durante);
                if (restaurar) {
                    await esperar(fotos.espera || 1500);
                    const tr = ahora();
                    restaurado = true;
                    await restaurar();
                    const rec = await recuperado(tr);
                    r.recuperacionMs = rec.t - tr;
                    r.detalleRecuperacion = rec.detalle;
                    if (fotos.despues) await foto(fotos.despues);
                }
                r.resultado = 'OK';
            } catch (e) {
                r.resultado = 'FALLA';
                r.error = e.message;
                await foto(`error-${id}`).catch(() => {});
                // Una falla que no se restaura contamina a las siguientes (paso en la primera corrida:
                // el simulador quedo en silencio y F-03..F-06 "fallaron" por eso).
                if (restaurar && !restaurado) await restaurar().catch(() => {});
            }
            R.fallas[id] = r;
            guardar();
            await esperar(2000);
        };
        const webCumple = async (fn, arg, timeout = 60000) => {
            await c.pagina.waitForFunction(fn, { timeout }, arg);
            return ahora();
        };
        const obs = (cond, detalle) => async (desde) => {
            const m = await c.lector.esperar(cond, desde, 60000);
            return { t: m.t, detalle: detalle(m) };
        };
        // OJO: puppeteer serializa la FUNCION al navegador sin sus variables: el valor esperado va
        // como argumento (con un cierre, 'v' era undefined en la pagina y F-01 nunca se cumplia).
        const DISP = (v) => document.getElementById('disp-vigencia').textContent === v;

        c.p.sim.escribir('auto on');
        await esperar(2000);
        if (hacer('fallas')) {

        await falla('F-01', 'el esclavo no responde (simulador en silencio = sin alimentacion)',
            async () => c.p.sim.escribir('falla silencio'),
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'DDEATH', ti, 30000);
                await webCumple(DISP, 'OBSOLETO'); return { t: m.t, detalle: `DDEATH seq=${m.seq} (web: dispositivo OBSOLETO)` }; },
            async () => c.p.sim.escribir('falla ninguna'),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'DBIRTH', tr, 30000);
                const tw = await webCumple(DISP, 'EN LÍNEA'); return { t: tw, detalle: `DBIRTH seq=${m.seq} a los ${m.t - tr} ms; web EN LÍNEA` }; },
            { durante: 'web-modbus-device-not-reached' });

        await falla('F-02', 'error de CRC (el simulador corrompe el CRC del 30 % de las respuestas)',
            async () => c.p.sim.escribir('falla crc 0.3'),
            obs((x) => x.tipo === 'NDATA' && tiene(x, 'Status/MODBUS/Estado', 'CRC ERROR'), (m) => `NDATA Estado=CRC ERROR, CRC_ERROR=${valorDe(m, 'Status/MODBUS/CRC_ERROR') ?? '(otro NDATA)'}`),
            async () => { await c.pagina.waitForFunction(() => document.getElementById('modbus-estado').textContent === 'CRC ERROR', { timeout: 30000 }).catch(() => {});
                await foto('web-modbus-crc-error'); c.p.sim.escribir('falla ninguna'); },
            obs((x) => x.tipo === 'NDATA' && tiene(x, 'Status/MODBUS/Estado', 'DONE'), () => 'NDATA Estado=DONE (el contador CRC_ERROR queda como historico)'));

        await falla('F-03', 'Unit ID equivocado desde el Dashboard (1 -> 7) y correccion (7 -> 1)',
            async () => cambiarUnitId(c, 7),
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'DDEATH', ti, 30000); return { t: m.t, detalle: 'DEVICE NOT REACHED -> DDEATH' }; },
            async () => cambiarUnitId(c, 1),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'DBIRTH', tr, 30000); return { t: m.t, detalle: 'DBIRTH sin reiniciar nada' }; });

        await falla('F-04', 'cae el servidor OPC UA (se detiene Node-RED)',
            async () => c.p.nodered.matar(),
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'NDATA' && tiene(x, 'Status/OPCUA/Estado', 'ERROR'), ti, 30000);
                await webCumple(() => document.getElementById('capa-opcua').dataset.nivel === 'error');
                return { t: m.t, detalle: 'NDATA Status/OPCUA/Estado=ERROR + DDEATH; web: OPC UA en ERROR, MODBUS SIN DATOS' }; },
            async () => c.iniciarNodeRed(),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'DBIRTH', tr, 90000);
                return { t: m.t, detalle: 'reconexion del cliente con retroceso, OPC UA DONE, DBIRTH' }; },
            { durante: 'web-opcua-error', despues: 'web-opcua-done-recuperado' });

        await falla('F-05', 'cae el Edge Node (kill del proceso)',
            async () => c.p.edge.matar(),
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'NDEATH', ti, 30000);
                await webCumple(() => document.getElementById('spb-estado').textContent === 'NODO OBSOLETO');
                return { t: m.t, detalle: `NDEATH del broker (Will), bdSeq=${valorDe(m, 'bdSeq')}, coincide=${m.bdSeq_coincide}` }; },
            async () => c.iniciarEdge(),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'NBIRTH', tr, 60000); await c.enLinea();
                return { t: ahora(), detalle: `NBIRTH seq=${m.seq} bdSeq=${valorDe(m, 'bdSeq')}, DBIRTH, web EN LINEA` }; },
            { durante: 'web-ndeath-nodo-obsoleto' });

        await falla('F-06', 'se corta internet en el dispositivo 3 (corte silencioso en el proxy)',
            async () => c.p.proxy.escribir('cortar'),
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'NDEATH', ti, 60000);
                return { t: m.t, detalle: `NDEATH por keepalive del broker a los ${m.t - ti} ms (esperado ~15 s)` }; },
            async () => c.p.proxy.escribir('restaurar'),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'NBIRTH', tr, 90000); await c.enLinea();
                return { t: ahora(), detalle: `NBIRTH bdSeq=${valorDe(m, 'bdSeq')} Reconexiones=${valorDe(m, 'Status/MQTT/Reconexiones')}` }; },
            { durante: 'web-recuperacion-1-corte', despues: 'web-recuperacion-2-restablecido', espera: 3000 });

        await falla('F-07', 'mensajes perdidos (Edge de prueba que salta un seq)',
            async () => {
                await c.p.edge.matar();
                const env = path.join(dir, 'fake.env');
                fs.writeFileSync(env, `MQTT_HOST=127.0.0.1\nMQTT_PUERTO_TLS=${PUERTOS.proxy}\nMQTT_USUARIO_EDGE=edge_node\nMQTT_CLAVE_EDGE=${c.claves.edge}\n`);
                c.p.fake = new Proceso('fake', PY, ['tools/fake_edge_node.py', '--env', env, '--mqtt-ca', c.ca,
                    '--estado', path.join(dir, 'bdseq-fake.json')], { cwd: GW, log: c.log('fake') });
                await c.lector.esperar((x) => x.tipo === 'DBIRTH', ahora() - 1000, 30000);
                await c.enLinea();
                await esperar(6000);                     // fuera de la espera minima entre Rebirth de la web
                const t = ahora();
                c.p.fake.escribir('saltar');
                return { t };
            },
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'NCMD', ti, 20000);
                return { t: m.t, detalle: 'la web detecto el salto y publico NCMD Rebirth' }; },
            null, null);
        if (R.fallas['F-07'].resultado === 'OK') {
            const tNcmd = R.fallas['F-07'].inyeccion + R.fallas['F-07'].deteccionMs;
            const m = await c.lector.esperar((x) => x.tipo === 'NBIRTH', tNcmd, 20000).catch(() => null);
            R.fallas['F-07'].recuperacionMs = m ? m.t - tNcmd : null;
            R.fallas['F-07'].detalleRecuperacion = m ? `NBIRTH seq=0 tras el NCMD (Rebirths=${valorDe(m, 'Status/Sparkplug/Rebirths')})` : 'sin NBIRTH';
            await foto('web-rebirth-por-salto-de-seq');
        }
        await c.p.fake.matar();
        await c.iniciarEdge();
        await c.enLinea();

        await falla('F-08', 'se cae la Host Application (se mata el navegador)',
            async () => { R.fallas.__navegador = true; c.navegador.process().kill('SIGKILL'); },
            obs((x) => x.tipo === 'STATE' && x.state && x.state[0] === false, (m) => `STATE offline (Will) retenido=${m.retenido}`),
            async () => { const puppeteer = require(path.join(WEB, 'node_modules', 'puppeteer-core'));
                c.navegador = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
                c.pagina = await c.abrirPagina(); },
            async (tr) => { await c.enLinea(); return { t: ahora(), detalle: 'STATE online, Rebirth pedido al conectar, web EN LINEA' }; });
        delete R.fallas.__navegador;

        await falla('F-09', 'credenciales MQTT invalidas en la web',
            async () => { c.paginaMala = await c.navegador.newPage(); await c.paginaMala.setViewport({ width: 1366, height: 900 });
                await c.paginaMala.setRequestInterception(true);
                c.paginaMala.on('request', (q) => (q.url().endsWith('/config.js') ? q.continue({ url: q.url() + '?mala=1' }) : q.continue()));
                await c.paginaMala.goto(c.urlWeb); },
            async () => { await c.paginaMala.waitForFunction(() => document.getElementById('mqtt-estado').textContent === 'CREDENCIALES RECHAZADAS', { timeout: 20000 });
                await c.paginaMala.screenshot({ path: path.join(dir, 'web-credenciales-rechazadas.png') });
                R.capturas['web-credenciales-rechazadas'] = 'web-credenciales-rechazadas.png';
                await c.paginaMala.close(); return { t: ahora(), detalle: 'semaforo MQTT: CREDENCIALES RECHAZADAS + aviso' }; },
            null, null);

        await falla('F-10', 'esclavo desconocido (ID 17, 19200 8E1, otro mapa): descubrimiento desde el Dashboard',
            async () => { await c.p.sim.matar(); await c.iniciarSimulador('simuladores/esclavo_desconocido_sim.py'); },
            async (ti) => { const m = await c.lector.esperar((x) => x.tipo === 'DDEATH', ti, 30000); return { t: m.t, detalle: 'el maestro no comunica: DDEATH' }; },
            async () => descubrirYAplicar(c),
            async (tr) => { const m = await c.lector.esperar((x) => x.tipo === 'NDATA' && tiene(x, 'Status/MODBUS/Estado', 'DONE'), tr, 60000);
                return { t: m.t, detalle: 'descubrimiento + Aplicar: Status/MODBUS/Estado=DONE con el esclavo nuevo, sin recompilar' }; });

        }
        paso('violaciones de seq/bdSeq registradas por el observador');
        R.violaciones = c.p.obs.lineas.filter((l) => /violaci/i.test(l.linea)).map((l) => l.linea);
        guardar();
    } finally {
        await c.bajar();
    }
    return R;
}

/** F-03: cambia el Unit ID desde el panel "Enlace" del Dashboard (como lo haria el operador). */
async function cambiarUnitId(c, id) {
    const p = await c.navegador.newPage();
    try {
        await p.goto(`http://127.0.0.1:${PUERTOS.nodered}/dashboard/configuracion`, { waitUntil: 'networkidle2' });
        const [campo] = await p.$$('xpath/.//label[contains(., "Unit ID")]/ancestor::div[contains(@class,"v-field")]//input');
        // Seleccionar todo con el teclado: el triple clic no selecciona en un input numerico y el
        // valor se AGREGABA (1 -> 17 -> 171 en la segunda corrida).
        await campo.click();
        await p.keyboard.down('Control');
        await p.keyboard.press('KeyA');
        await p.keyboard.up('Control');
        await campo.type(String(id));
        const escrito = await campo.evaluate((e) => e.value);
        if (escrito !== String(id)) throw new Error(`el campo Unit ID quedo en "${escrito}", no en ${id}`);
        const [boton] = await p.$$('xpath/.//button[contains(., "Aplicar sin reiniciar")]');
        await boton.click();
        await esperar(500);
    } finally {
        await p.close();
    }
}

/** F-10: asistente de descubrimiento del Dashboard -> Aplicar el hallazgo. */
async function descubrirYAplicar(c) {
    const p = await c.navegador.newPage();
    try {
        await p.goto(`http://127.0.0.1:${PUERTOS.nodered}/dashboard/configuracion`, { waitUntil: 'networkidle2' });
        const [buscar] = await p.$$('xpath/.//button[contains(., "Descubrir")]');
        await buscar.click();
        await p.waitForFunction(() => [...document.querySelectorAll('button')].some((b) => /^\s*Aplicar\s*$/.test(b.textContent)
            && b.closest('tr')), { timeout: 120000 });
        const [aplicar] = await p.$$('xpath/.//tr//button[normalize-space(.)="Aplicar"]');
        await aplicar.click();
        await esperar(500);
    } finally {
        await p.close();
    }
}

// =============================================================================
// Resistencia
// =============================================================================

async function resistencia(dir, minutos) {
    const c = new Cadena(dir);
    const R = { fecha: new Date().toISOString(), commit: git('rev-parse --short HEAD'), minutos, muestras: [] };
    try {
        await c.levantar();
        c.p.sim.escribir('auto on');
        const fin = ahora() + minutos * 60000;
        while (ahora() < fin) {
            const m = { t: ahora(), memoriaMiB: memoriaArbol(c.pids()) };
            m.webMiB = Math.round((await c.pagina.metrics()).JSHeapUsedSize / 1024 / 1024 * 10) / 10;
            m.web = await c.pagina.evaluate(() => ({ seq: document.getElementById('spb-seq').textContent,
                rebirths: document.getElementById('spb-rebirths').textContent, nodo: document.getElementById('spb-estado').textContent,
                eventos: document.getElementById('eventos').children.length }));
            R.muestras.push(m);
            fs.writeFileSync(path.join(dir, 'resistencia.json'), JSON.stringify(R, null, 2));
            console.log(`[${new Date().toISOString().slice(11, 19)}] ${JSON.stringify(m.memoriaMiB)} web=${m.webMiB} MiB seq=${m.web.seq}`);
            await esperar(30000);
        }
        R.violaciones = c.p.obs.lineas.filter((l) => /violaci/i.test(l.linea)).map((l) => l.linea);
        await c.pagina.screenshot({ path: path.join(dir, 'resistencia-final.png') });
    } finally {
        await c.bajar();
    }
    fs.writeFileSync(path.join(dir, 'resistencia.json'), JSON.stringify(R, null, 2));
}

function git(args) {
    return spawnSync('git', args.split(' '), { cwd: T3, encoding: 'utf8' }).stdout.trim();
}

// =============================================================================
// Programa
// =============================================================================

if (require.main === module) {
    const [modo, ...resto] = process.argv.slice(2);
    const opcion = (n, d) => (resto.includes(n) ? resto[resto.indexOf(n) + 1] : d);
    const dir = path.resolve(opcion('--salida', path.join(os.tmpdir(), `pdci-banco-${Date.now()}`)));
    fs.mkdirSync(dir, { recursive: true });
    console.log(`banco virtual: ${modo} -> ${dir}`);
    const tareas = {
        campana: () => campana(dir, opcion('--fases', null) && opcion('--fases').split(',')),
        resistencia: () => resistencia(dir, Number(opcion('--minutos', 30))),
        levantar: async () => {
            const c = new Cadena(dir);
            await c.levantar();
            fs.writeFileSync(path.join(dir, 'pids.json'), JSON.stringify(c.pids()));
            console.log(`CADENA LISTA · web ${c.urlWeb} · dashboard http://127.0.0.1:${PUERTOS.nodered}/dashboard`);
            // Comandos del menu (scripts/inyectar-fallas.sh), uno por linea:
            //   <proceso> <texto>       reenvia texto a su entrada (sim falla silencio, proxy cortar...)
            //   matar <proceso>         lo termina sin aviso (kill -9): edge, nodered, sim
            //   iniciar <proceso>       lo vuelve a levantar: edge, nodered, sim, desconocido
            //   saltar-seq              F-07: reemplaza al Edge por el de prueba y salta un seq
            //   bajar                   termina todo
            const acciones = {
                matar: async (n) => c.p[n] && c.p[n].matar(),
                iniciar: async (n) => ({
                    edge: () => c.iniciarEdge(), nodered: () => c.iniciarNodeRed(),
                    sim: () => c.iniciarSimulador(),
                    desconocido: async () => { await c.p.sim.matar(); await c.iniciarSimulador('simuladores/esclavo_desconocido_sim.py'); },
                }[n] || (async () => console.log(`no se como iniciar ${n}`)))(),
                'saltar-seq': async () => {
                    await c.p.edge.matar();
                    const env = path.join(dir, 'fake.env');
                    fs.writeFileSync(env, `MQTT_HOST=127.0.0.1\nMQTT_PUERTO_TLS=${PUERTOS.proxy}\nMQTT_USUARIO_EDGE=edge_node\nMQTT_CLAVE_EDGE=${c.claves.edge}\n`);
                    c.p.fake = new Proceso('fake', PY, ['tools/fake_edge_node.py', '--env', env, '--mqtt-ca', c.ca,
                        '--estado', path.join(dir, 'bdseq-fake.json')], { cwd: GW, log: c.log('fake') });
                    await c.p.fake.esperarLinea(/LISTO/);
                    await esperar(8000);                    // BIRTH del fake y fuera de la espera entre Rebirth
                    c.p.fake.escribir('saltar');
                    console.log('seq saltado: mirar la web (aviso + NCMD Rebirth)');
                },
                'volver-edge': async () => { if (c.p.fake) await c.p.fake.matar(); await c.iniciarEdge(); },
                bajar: async () => { await c.bajar(); process.exit(0); },
            };
            let pendiente = '';
            process.stdin.on('data', (d) => {
                pendiente += String(d);
                const lineas = pendiente.split('\n');
                pendiente = lineas.pop();
                for (const linea of lineas.map((l) => l.trim()).filter(Boolean)) {
                    const [destino, ...cmd] = linea.split(' ');
                    console.log(`> ${linea}`);
                    if (acciones[destino]) acciones[destino](cmd[0]).catch((e) => console.log(`error: ${e.message}`));
                    else if (c.p[destino]) c.p[destino].escribir(cmd.join(' '));
                    else console.log(`comando desconocido: ${linea}`);
                }
            });
        },
    };
    if (!tareas[modo]) {
        console.error('uso: node tools/banco_virtual.js campana|resistencia|levantar [--salida dir] [--minutos N]');
        process.exit(2);
    }
    tareas[modo]().then(() => { if (modo !== 'levantar') process.exit(0); }).catch((e) => { console.error(e); process.exit(1); });
}

module.exports = { Cadena, PUERTOS };
