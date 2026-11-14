// =====================================================================
// E2 · variables en vivo
// ---------------------------------------------------------------------
// Descripcion: lleva la tabla de variables del panel. Recibe:
//   - de M1 salida 4: un valor que cambio (topic = nombre, payload = valor, calidad);
//   - de M1 salida 5: la configuracion (para saber que variables se escriben)
//     y el resultado de cada escritura.
//   Arma una sola instantanea para el ui-template, que la reenvia completa al
//   recargar la pagina.
// Salida: {topic: 'variables', payload: {variables: [...], ultimaEscritura}}
// =====================================================================
const variables = flow.get('variables') || {};
let config = flow.get('config');
let ultimaEscritura = flow.get('ultimaEscritura') || null;

if (msg.topic === 'config') {
    config = msg.payload;
    flow.set('config', config);
    // Las variables que ya no estan en el mapa se quitan de la tabla.
    const vigentes = new Set(config.mapa.map((v) => v.nombre).concat(config.derivadas.map((d) => d.nombre)));
    Object.keys(variables).forEach((n) => { if (!vigentes.has(n)) delete variables[n]; });
} else if (msg.topic === 'escritura') {
    ultimaEscritura = Object.assign({ ts: Date.now() }, msg.payload);
    flow.set('ultimaEscritura', ultimaEscritura);
} else if (typeof msg.topic === 'string' && msg.topic !== 'reconfiguracion' && 'calidad' in msg) {
    variables[msg.topic] = { valor: msg.payload, calidad: msg.calidad, ts: msg.ts };
} else {
    return null;
}
flow.set('variables', variables);

const mapa = config ? config.mapa : [];
const filas = mapa.map((v) => Object.assign({ nombre: v.nombre, tipo: v.tipo, escritura: v.escritura,
    min: v.min, max: v.max, fc: v.fc, direccion: v.direccion }, variables[v.nombre] || {}))
    .concat((config ? config.derivadas : []).map((d) => Object.assign({ nombre: d.nombre, tipo: 'derivada',
        escritura: false }, variables[d.nombre] || {})));
return { topic: 'variables', payload: { variables: filas, ultimaEscritura } };
