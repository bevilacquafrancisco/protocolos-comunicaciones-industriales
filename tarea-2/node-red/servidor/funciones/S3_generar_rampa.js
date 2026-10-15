// =====================================================================
// BLOQUE S3 · Rampa diente de sierra — Raspberry Pi 1
// diagramas/flujo_servidor.md, bloque S3 · consigna Parte 2.3
// ---------------------------------------------------------------------
// Descripcion: cada 50 ms (inject "S3 · Tick") calcula el valor de la
//   sierra 0-65535 de periodo 4 s A PARTIR DEL RELOJ (senales.sierra) y lo
//   envia a S2 para publicarlo en Servidor.Rampa.
//   Los botones "S3 · Detener rampa" / "S3 · Reanudar rampa" envian
//   msg.topic = 'pausa' (true/false): con la rampa detenida el valor queda
//   fijo y la suscripcion solo emite KeepAlive (consigna Parte 3.4).
// Entrada: msg del inject de 50 ms, o { topic: 'pausa', payload: boolean }.
// Salida: { topic: 'rampa', payload: UInt16, instante: Date } -> S2.
// Excepciones: ninguna (senales.sierra solo falla con una config invalida,
//   que prueba_senales.js descarta antes del despliegue).
//
// Firma: senales.sierra(tMs: number, periodoMs: number, tickMs: number,
//   maximo?: number) : number
// =====================================================================
if (msg.topic === 'pausa') {
    const pausada = msg.payload === true;
    flow.set('rampaPausada', pausada);
    node.status(pausada ? { fill: 'grey', shape: 'ring', text: 'rampa detenida' } : {});
    node.log(new Date().toISOString() + ' rampa ' + (pausada ? 'DETENIDA' : 'reanudada'));
    return null;
}
// Detenida: no se publica nada, asi el valor (y su SourceTimestamp) no cambia.
if (flow.get('rampaPausada')) return null;

const config = global.get('config');
const senales = global.get('senales');
const instante = new Date();
const valor = senales.sierra(instante.getTime(), config.senales.periodoSierraMs, config.senales.tickMs,
    config.senales.maximo);
flow.set('rampaGenerada', valor); // para la consola (S7)
return { topic: 'rampa', payload: valor, instante };
