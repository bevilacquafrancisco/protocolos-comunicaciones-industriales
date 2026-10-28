/**
 * prueba_flujos.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-14
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Verifica los flows.json de Node-RED sin Node-RED ni placas:
 *   1. Estan al dia: regenerarlos desde config.js y funciones/*.js da
 *      exactamente el mismo contenido que el archivo versionado.
 *   2. Coherencia con config.js: pines, antirrebote, frecuencia de PWM y
 *      periodos de los inject (ningun numero tipeado a mano).
 *   3. Cableado: todo destino existe y toda function node tiene sus salidas.
 *   4. El codigo de cada function node compila, envuelto igual que lo
 *      envuelve Node-RED (async function para On Message y On Start).
 *   5. Trazabilidad (requerimiento adicional 3): cada nodo del flujo nombra
 *      un bloque, y ese bloque y su archivo figuran en el diagrama de flujo.
 *
 * Uso
 * ---
 *     node --test tarea-2/herramientas/prueba_flujos.js
 *
 * Dependencias externas: ninguna (Node.js >= 18).
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const RAIZ = path.join(__dirname, '..');
const NR = path.join(RAIZ, 'node-red');
const config = require(path.join(NR, 'comun', 'config.js'));
const { flujoServidor, flujoCliente } = require(path.join(NR, 'generar_flujos.js'));

const FLUJOS = {
    servidor: { generado: flujoServidor(), diagrama: 'flujo_servidor.md', prefijo: 'S' },
    cliente: { generado: flujoCliente(), diagrama: 'flujo_cliente.md', prefijo: 'C' },
};

for (const [nombre, f] of Object.entries(FLUJOS)) {
    const archivo = path.join(NR, nombre, 'flows.json');
    const nodos = f.generado;
    const porId = new Map(nodos.map((n) => [n.id, n]));
    const deTipo = (t) => nodos.filter((n) => n.type === t);

    test(nombre + ': flows.json esta al dia (regenerar con generar_flujos.js si falla)', () => {
        const versionado = JSON.parse(fs.readFileSync(archivo, 'utf8'));
        assert.deepEqual(versionado, nodos);
    });

    test(nombre + ': GPIO coherente con config.gpio', () => {
        const entradas = deTipo('pi-gpiod in');
        const salidas = deTipo('pi-gpiod out');
        assert.equal(entradas.length, 1);
        assert.equal(entradas[0].pin, String(config.gpio.pulsador));
        assert.equal(entradas[0].intype, 'PUD_UP', 'pulsador a GND con pull-up');
        assert.equal(entradas[0].debounce, String(config.gpio.antirreboteUs), 'antirrebote en MICROsegundos (I-01)');
        assert.equal(entradas[0].host, '127.0.0.1', 'pigpiod por IPv4 de loopback');
        const pwm = salidas.find((n) => n.out === 'pwm');
        const dig = salidas.find((n) => n.out === 'out');
        assert.equal(pwm.pin, String(config.gpio.ledPwm));
        assert.equal(pwm.freq, String(config.gpio.frecuenciaPwmHz));
        assert.equal(dig.pin, String(config.gpio.ledDigital));
        for (const s of salidas) assert.equal(s.set, true, s.name + ' arranca en un nivel definido');
    });

    test(nombre + ': periodos de los inject = config', () => {
        const repeticiones = deTipo('inject').map((n) => n.repeat).filter(Boolean).map(Number).sort((a, b) => a - b);
        const esperadas = (nombre === 'servidor'
            ? [config.senales.tickMs, config.consola.periodoMs]
            : [config.senales.tickMs, config.senales.periodoEscrituraRampaMs, config.consola.periodoMs])
            .map((ms) => ms / 1000).sort((a, b) => a - b);
        assert.deepEqual(repeticiones, esperadas);
    });

    test(nombre + ': cableado sin destinos inexistentes', () => {
        for (const n of nodos) {
            for (const salida of n.wires || []) {
                for (const destino of salida) assert.ok(porId.has(destino), n.name + ' -> ' + destino + ' no existe');
            }
            if (n.type === 'function') assert.equal(n.wires.length, n.outputs, n.name + ': una lista de cables por salida');
            if (n.z) assert.equal(n.z, nodos[0].id, n.name + ' en la pestana del flujo');
        }
        const ids = nodos.map((n) => n.id);
        assert.equal(new Set(ids).size, ids.length, 'IDs unicos');
    });

    test(nombre + ': el codigo de cada function node compila como en Node-RED', () => {
        for (const n of deTipo('function')) {
            // Mismo envoltorio que @node-red/nodes/core/function/10-function.js
            assert.doesNotThrow(() => new vm.Script('(async function(msg,__send__,__done__){\n' + n.func + '\n})'),
                n.name + ' (On Message)');
            if (n.initialize) {
                assert.doesNotThrow(() => new vm.Script('(async function(__send__){\n' + n.initialize + '\n})'),
                    n.name + ' (On Start)');
            }
            if (n.finalize) {
                assert.doesNotThrow(() => new vm.Script('(function(){\n' + n.finalize + '\n})'), n.name + ' (On Close)');
            }
        }
    });

    test(nombre + ': trazabilidad nodo <-> diagrama de flujo', () => {
        const diagrama = fs.readFileSync(path.join(RAIZ, 'diagramas', f.diagrama), 'utf8');
        for (const n of nodos.filter((x) => ['function', 'inject', 'pi-gpiod in', 'pi-gpiod out', 'rbe', 'debug'].includes(x.type))) {
            const bloque = (n.name.match(/^([SC]\d)\s·/) || [])[1];
            assert.ok(bloque && bloque[0] === f.prefijo, '"' + n.name + '" no nombra un bloque ' + f.prefijo + 'n');
            assert.ok(diagrama.includes(bloque + ' ·'), 'el bloque ' + bloque + ' no figura en ' + f.diagrama);
        }
        for (const n of deTipo('function')) {
            const nombreEnDiagrama = n.name.normalize('NFD').replace(/[̀-ͯ]/g, '');
            const diagramaSinTildes = diagrama.normalize('NFD').replace(/[̀-ͯ]/g, '');
            assert.ok(diagramaSinTildes.includes(nombreEnDiagrama), 'la function node "' + n.name + '" no figura en la tabla de ' + f.diagrama);
        }
        // Cada archivo enlazado desde la tabla de trazabilidad existe.
        for (const [, ruta] of diagrama.matchAll(/\]\((\.\.\/node-red\/[^)#]+\.js)\)/g)) {
            assert.ok(fs.existsSync(path.join(RAIZ, 'diagramas', ruta)), f.diagrama + ' enlaza ' + ruta + ', que no existe');
        }
    });
}
