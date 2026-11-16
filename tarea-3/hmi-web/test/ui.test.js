/**
 * ui.test.js — la PAGINA real en Chrome (sin cabeza) contra el broker de desarrollo y el
 * fake_edge_node (que usa el Edge Node real del dispositivo 3 con datos sinteticos).
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v2.0 (2026-11-16: ingreso, pestañas, ADR-028)
 *
 * Requiere: Chrome instalado (o CHROME_PATH) y el venv de gateway-sparkplug. Si falta alguno,
 * la prueba se SALTEA (no falla): las del nucleo (sparkplug.test.js) corren igual.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { crearServidor } = require('../tools/servir');

const RAIZ = path.join(__dirname, '..');
const GATEWAY = path.join(RAIZ, '..', 'gateway-sparkplug');
const PYTHON = path.join(GATEWAY, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const CHROME = process.env.CHROME_PATH || ['C:/Program Files/Google/Chrome/Application/chrome.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    .find((p) => fs.existsSync(p));
const CLAVES = { edge: 'clave-edge-ui', host: 'clave-host-ui', obs: 'clave-obs-ui' };

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

/** Lanza un proceso y espera la linea 'marca' en su salida. */
function lanzar(args, env, marca) {
    return new Promise((resolver, rechazar) => {
        const p = spawn(PYTHON, args, { cwd: GATEWAY, env: Object.assign({}, process.env, env, { PYTHONUNBUFFERED: '1' }) });
        let salida = '';
        const t = setTimeout(() => rechazar(new Error(`sin "${marca}": ${salida.slice(-500)}`)), 20000);
        const leer = (d) => { salida += d; if (salida.includes(marca)) { clearTimeout(t); resolver(p); } };
        p.stdout.on('data', leer);
        p.stderr.on('data', leer);
        p.on('exit', (c) => { if (!salida.includes(marca)) rechazar(new Error(`salio con ${c}: ${salida.slice(-500)}`)); });
    });
}

test('Host Application en el navegador: BIRTH, comando confirmado, salto de seq, DDEATH, NDEATH y celular',
    { skip: !CHROME ? 'falta Chrome' : !fs.existsSync(PYTHON) ? 'falta el venv de gateway-sparkplug' : false, timeout: 180000 },
    async () => {
        const puppeteer = require('puppeteer-core');
        const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pdci-hmi-'));
        const puerto = 19000 + Math.floor(Math.random() * 500);
        const puertoWs = puerto + 600;
        const procesos = [];
        let navegador = null;
        let servidor = null;
        try {
            procesos.push(await lanzar(['tools/broker_dev.py', '--carpeta', path.join(tmp, 'broker'), '--puerto', String(puerto),
                '--puerto-ws', String(puertoWs)], { DEV_MQTT_CLAVE_EDGE: CLAVES.edge, DEV_MQTT_CLAVE_HOST: CLAVES.host,
                DEV_MQTT_CLAVE_OBSERVADOR: CLAVES.obs }, 'Ctrl+C'));
            const env = path.join(tmp, 'fake.env');
            fs.writeFileSync(env, `MQTT_HOST=127.0.0.1\nMQTT_PUERTO_TLS=${puerto}\nMQTT_USUARIO_EDGE=edge_node\nMQTT_CLAVE_EDGE=${CLAVES.edge}\n`);
            const fake = await lanzar(['tools/fake_edge_node.py', '--env', env, '--mqtt-ca', path.join(tmp, 'broker', 'ca.pem'),
                '--estado', path.join(tmp, 'bdseq.json')], {}, 'LISTO');
            procesos.push(fake);
            const comando = (c) => fake.stdin.write(c + '\n');

            // ADR-028: config.js SIN clave; usuario y clave se escriben en la pantalla de ingreso
            const config = `window.PDCI_CONFIG = Object.freeze({ url: 'ws://127.0.0.1:${puertoWs}/mqtt',
                grupo: 'UNRaf_PdCI_2026', nodo: 'EN01_Gateway', dispositivo: 'DEV01_ESP32_Slave',
                hostId: 'HA01_WebDashboard' });`;
            servidor = crearServidor(RAIZ, { config });
            await new Promise((r) => servidor.listen(0, '127.0.0.1', r));
            const url = `http://127.0.0.1:${servidor.address().port}/`;

            navegador = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
            const pagina = await navegador.newPage();
            const erroresConsola = [];
            pagina.on('console', (m) => { if (m.type() === 'error') erroresConsola.push(m.text()); });
            pagina.on('pageerror', (e) => erroresConsola.push(e.message));
            await pagina.setViewport({ width: 1366, height: 900 });
            await pagina.goto(url, { waitUntil: 'load' });
            const txt = (id) => pagina.$eval(`#${id}`, (e) => e.textContent.trim());
            const hasta = (fn, arg, ms = 20000) => pagina.waitForFunction(fn, { timeout: ms }, arg);
            const capturas = process.env.HMI_CAPTURAS;          // carpeta opcional para revisar la vista
            const capturar = async (nombre) => { if (capturas) await pagina.screenshot({ path: path.join(capturas, `${nombre}.png`), fullPage: true }); };
            const ingresar = async (usuario, clave) => {
                await pagina.$eval('#usuario', (e) => { e.value = ''; });
                await pagina.type('#usuario', usuario);
                await pagina.$eval('#clave', (e) => { e.value = ''; });
                await pagina.type('#clave', clave);
                await pagina.click('#btn-entrar');
            };

            // 0. [DF-4.0] Ingreso: config.js no tiene clave; una clave equivocada se rechaza (F-09)
            assert.equal(await pagina.$eval('#app', (e) => e.hidden), true, 'sin ingresar no se ve la aplicación');
            await capturar('0-ingreso');
            await ingresar('host_app', 'clave-equivocada');
            await hasta(() => !document.getElementById('login-error').hidden);
            assert.match(await txt('login-error'), /incorrectos|rechaz/);
            await ingresar('host_app', CLAVES.host);
            await hasta(() => !document.getElementById('app').hidden);
            assert.equal(await txt('usuario-actual'), 'host_app');
            assert.equal(await pagina.$eval('#clave', (e) => e.value), '', 'la clave no queda en el formulario');

            // 1. La web se anuncia (STATE), pide BIRTH y queda todo EN LINEA
            await hasta(() => document.getElementById('spb-estado').textContent === 'NODO EN LÍNEA'
                && document.getElementById('disp-vigencia').textContent === 'EN LÍNEA').catch(async (e) => {
                // Diagnostico: sin esto, un timeout no dice POR QUE la pagina no llego a EN LINEA.
                throw new Error(`${e.message}
consola: ${erroresConsola.join(' | ')}
fatal: ${await txt('fatal')}`
                    + `
eventos: ${(await txt('eventos')).slice(0, 600)}`);
            });
            assert.equal(await txt('mqtt-estado'), 'CONECTADO');
            assert.equal(await pagina.$eval('#capa-modbus', (e) => e.dataset.nivel), 'ok');
            assert.match(await txt('eventos'), /STATE online/);
            assert.match(await txt('eventos'), /NBIRTH bdSeq=/);
            await hasta(() => document.getElementById('pote-crudo').textContent !== '—');

            // 2. Comando: ENVIADO -> CONFIRMADO, y el conmutador cambia SOLO con el DDATA
            assert.equal(await pagina.$eval('#btn-led', (e) => e.getAttribute('aria-checked')), 'false');
            await pagina.click('#btn-led');
            await hasta(() => document.getElementById('cmd-led').dataset.estado === 'confirmado');
            assert.equal(await pagina.$eval('#btn-led', (e) => e.getAttribute('aria-checked')), 'true');
            assert.match(await txt('led-valor'), /ENCENDIDO/);

            // 2b. ADR-028: recorrido del comando (FC 05 reconstruida con su CRC) y medicion de tiempos
            await hasta(() => /CONFIRMADO/.test(document.getElementById('rec-pasos').textContent));
            assert.match(await txt('rec-pasos'), /01050000FF008C3A/, 'la FC 05 reconstruida, con CRC');
            assert.match(await txt('rec-pasos'), /CAPTURADO.*RECONSTRUIDO/s);
            const tramos = await txt('tiempos-tramos');
            assert.match(tramos, /T4 − T0\d+ ms/, 'latencia total medida con un solo reloj');
            await capturar('1-general');

            // 2c. Pestana MODBus: trama real del NDATA de diagnostico, decodificada, y el CRC paso a paso
            await pagina.click('#t-modbus');
            await hasta(() => document.querySelectorAll('#tramas-lista .fi').length > 0);
            await hasta(() => /✔ coincide/.test(document.getElementById('crc-resultado').textContent));
            assert.equal(await pagina.$$eval('#crc-pasos tr', (f) => f.length), 6, 'un paso por byte de la petición');
            await capturar('2-modbus');

            // 2d. OPC UA (atributos del nodo) y Sparkplug (payload byte por byte)
            await pagina.click('#t-opcua');
            assert.match(await txt('ua-attrs'), /ns=1;s=Dispositivo1\.Inputs\.Potenciometro/);
            await capturar('3-opcua');
            await pagina.click('#t-sparkplug');
            await hasta(() => document.querySelectorAll('#spb-bytes .by').length > 0);
            assert.match(await txt('spb-filas'), /tag: campo 1 \(timestamp\)/);
            await capturar('4-sparkplug');
            await pagina.click('#t-guia');
            await capturar('5-guia');
            await pagina.click('#t-general');

            // 3. Comando que el dispositivo no confirma -> SIN CONFIRMAR, y el valor mostrado no cambia
            comando('escrituras falla');
            await esperar(300);
            await pagina.click('#btn-led');
            await hasta(() => document.getElementById('cmd-led').dataset.estado === 'sin confirmar', null, 10000);
            assert.match(await txt('led-valor'), /ENCENDIDO/, 'no se muestra lo pedido sin confirmacion');
            comando('escrituras ok');

            // 4. Salto de seq -> NCMD Rebirth, aviso en pantalla y contador +1. (La web ya pidio un
            // Rebirth al conectarse: los BIRTH no se retienen. Por eso se mide el INCREMENTO.)
            await esperar(5200);                      // fuera de la espera minima entre dos Rebirth
            const antes = Number(await txt('spb-rebirths'));
            comando('saltar');
            await hasta((n) => Number(document.getElementById('spb-rebirths').textContent) === n + 1, antes);
            assert.equal(await pagina.$eval('#aviso', (e) => e.hidden), false);
            assert.match(await txt('aviso'), /Salto de seq/);
            await hasta(() => Number(document.getElementById('spb-rebirths-edge').textContent) >= 2);  // el Edge conto ambos

            // 5. DEVICE NOT REACHED -> DDEATH: dispositivo OBSOLETO, MODBUS en rojo con texto
            comando('dnr');
            await hasta(() => document.getElementById('disp-vigencia').textContent === 'OBSOLETO');
            assert.equal(await txt('modbus-estado'), 'DEVICE NOT REACHED');
            assert.equal(await pagina.$eval('#capa-modbus', (e) => e.dataset.nivel), 'error');
            assert.equal(await pagina.$eval('#btn-led', (e) => e.disabled), true, 'sin dispositivo no se comanda');
            comando('ok');
            await hasta(() => document.getElementById('disp-vigencia').textContent === 'EN LÍNEA');

            // 5b. F-04: cae OPC UA -> la capa OPC UA en ERROR y MODBUS como SIN DATOS (no un DONE viejo)
            comando('opcua off');
            await hasta(() => document.getElementById('capa-opcua').dataset.nivel === 'error');
            assert.equal(await pagina.$eval('#capa-modbus', (e) => e.dataset.nivel), 'obsoleto');
            assert.match(await txt('modbus-estado'), /SIN DATOS/);
            comando('opcua on');
            await hasta(() => document.getElementById('capa-modbus').dataset.nivel === 'ok'
                && document.getElementById('disp-vigencia').textContent === 'EN LÍNEA');

            // 6. Celular: una columna, sin desplazamiento horizontal, controles de al menos 44 px
            await pagina.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
            // Pasar a modo celular RECARGA la pagina: la clave vivia solo en memoria (ADR-028), asi
            // que se vuelve a pedir. Es el comportamiento buscado; se ingresa de nuevo.
            await pagina.waitForSelector('#usuario');
            await hasta(() => !document.getElementById('login').hidden);
            await ingresar('host_app', CLAVES.host);
            await hasta(() => document.getElementById('disp-vigencia').textContent === 'EN LÍNEA');
            await esperar(300);
            const movil = await pagina.evaluate(() => ({
                desborde: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                alto: document.getElementById('btn-led').getBoundingClientRect().height }));
            assert.ok(movil.desborde <= 0, `desplazamiento horizontal de ${movil.desborde} px`);
            assert.ok(movil.alto >= 44, `conmutador de ${movil.alto} px (WCAG 2.5.5 pide 44)`);
            await capturar('6-celular');
            for (const t of ['modbus', 'opcua', 'sparkplug', 'guia', 'general']) {      // ninguna pestana desborda
                await pagina.click(`#t-${t}`);
                await esperar(150);
                const d = await pagina.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
                assert.ok(d <= 0, `pestaña ${t}: desplazamiento horizontal de ${d} px en el celular`);
            }

            // 7. Se mata el Edge Node -> el broker publica el NDEATH -> todo OBSOLETO
            comando('matar');
            await hasta(() => document.getElementById('spb-estado').textContent === 'NODO OBSOLETO');
            assert.match(await txt('eventos'), /NDEATH bdSeq=\d+: Edge Node fuera de línea/);
            assert.equal(await pagina.$eval('#capa-sparkplug', (e) => e.dataset.nivel), 'error');

            assert.deepEqual(erroresConsola, [], 'sin errores en la consola (incluida la CSP)');
        } finally {
            if (navegador) await navegador.close();
            if (servidor) servidor.close();
            for (const p of procesos) p.kill();
        }
    });
