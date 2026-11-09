/**
 * flujos.test.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-11-09
 * Version: 1.0
 *
 * Descripcion general
 * -------------------
 * Verifica los flows de Node-RED sin levantar Node-RED:
 *   - flows/*.json estan al dia con generar_flujos.js (nadie los edito a mano);
 *   - todo cable apunta a un nodo existente y los links son reciprocos;
 *   - el codigo de cada function node compila (On Start, On Message, On Stop);
 *   - I-01: no hay nodos de protocolo MODBus de la paleta (node-red-contrib-modbus y afines);
 *   - las tres trampas de Dashboard 2.0 encontradas en el banco de PC quedan como regresion:
 *     <v-table> con filas, etiquetas v-* autocerradas y atributos con mayusculas. Dashboard 2.0
 *     parsea la plantilla con el HTML del navegador, que (1) saca los <tr> de un elemento que no
 *     es <table>, (2) no tiene etiquetas autocerradas para elementos propios y (3) pasa los
 *     nombres de atributo a minusculas.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { generar, serializar } = require('../generar_flujos');

const FLUJOS = generar();
const TODOS = Object.values(FLUJOS).flat();
const porId = new Map(TODOS.map((n) => [n.id, n]));

describe('flows generados', () => {
    test.each(Object.keys(FLUJOS))('flows/%s esta al dia con generar_flujos.js', (archivo) => {
        const enDisco = fs.readFileSync(path.join(__dirname, '..', 'flows', archivo), 'utf8');
        expect(enDisco).toBe(serializar(FLUJOS[archivo]));
    });

    test('IDs unicos', () => {
        expect(porId.size).toBe(TODOS.length);
    });

    test('todo nodo con pestana pertenece a una pestana existente', () => {
        const tabs = new Set(TODOS.filter((n) => n.type === 'tab').map((n) => n.id));
        for (const n of TODOS.filter((x) => x.z)) expect(tabs.has(n.z)).toBe(true);
    });

    test('todos los cables apuntan a nodos existentes', () => {
        for (const n of TODOS) {
            for (const salida of n.wires || []) for (const destino of salida) {
                expect({ desde: n.name, destino, existe: porId.has(destino) }).toMatchObject({ existe: true });
            }
        }
    });

    test('links reciprocos: cada link out figura en el link in al que apunta', () => {
        for (const salida of TODOS.filter((n) => n.type === 'link out')) {
            for (const destino of salida.links) {
                const entrada = porId.get(destino);
                expect(entrada && entrada.type).toBe('link in');
                expect(entrada.links).toContain(salida.id);
            }
        }
    });

    test('I-01: ningun nodo de protocolo MODBus de la paleta', () => {
        const prohibidos = TODOS.filter((n) => /modbus/i.test(n.type));
        expect(prohibidos).toEqual([]);
        const puerto = TODOS.find((n) => n.type === 'serial-port');
        expect(puerto).toMatchObject({ bin: 'bin', out: 'interbyte', addchar: '' });   // bytes crudos
    });

    test('cada ui-template de un grupo apunta a un grupo existente con pagina existente', () => {
        for (const t of TODOS.filter((n) => n.type === 'ui-template' && n.templateScope === 'local')) {
            const grupo = porId.get(t.group);
            expect(grupo && grupo.type).toBe('ui-group');
            expect(porId.get(grupo.page).type).toBe('ui-page');
        }
    });
});

describe('codigo de los function nodes', () => {
    const funciones = TODOS.filter((n) => n.type === 'function');
    test.each(funciones.map((f) => [f.name, f]))('%s compila', (_nombre, f) => {
        const params = ['msg', 'node', 'context', 'flow', 'global', 'env', 'RED'];
        for (const codigo of [f.func, f.initialize, f.finalize].filter(Boolean)) {
            // Node-RED envuelve el codigo en una funcion asincronica: se compila igual, sin ejecutarlo.
            expect(() => vm.compileFunction(`return (async () => {\n${codigo}\n})();`, params)).not.toThrow();
        }
    });
    test('cada function node nombra su bloque (M, D o E) para la trazabilidad (I-09)', () => {
        for (const f of funciones) expect(f.name).toMatch(/^[MDE]\d · /);
    });
});

describe('plantillas Vue: trampas de Dashboard 2.0 (regresion)', () => {
    const plantillas = TODOS.filter((n) => n.type === 'ui-template' && n.templateScope === 'local');
    const cuerpo = (t) => t.format.slice(t.format.indexOf('<template>'), t.format.indexOf('<script>'));
    test.each(plantillas.map((t) => [t.name, t]))('%s', (_nombre, t) => {
        const html = cuerpo(t);
        expect(html).not.toMatch(/<v-table[\s>]/);                       // (1) filas fuera de <table>
        expect(html).not.toMatch(/<v-[\w-]+[^<>]*\/>/);                   // (2) autocerradas
        const conMayusculas = [...html.matchAll(/\s([@:]?[\w:.-]*[A-Z][\w:.-]*)=/g)].map((m) => m[1]);
        expect(conMayusculas).toEqual([]);                                // (3) atributos camelCase
        expect(t.format).toMatch(/<script>[\s\S]*export default/);
    });
});
