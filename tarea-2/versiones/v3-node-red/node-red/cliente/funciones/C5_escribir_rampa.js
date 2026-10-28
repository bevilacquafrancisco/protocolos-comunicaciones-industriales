// =====================================================================
// BLOQUE C5 · Escritura periodica de la rampa — Raspberry Pi 2
// diagramas/flujo_cliente.md, bloque C5 · consigna Parte 3.3
// ---------------------------------------------------------------------
// Descripcion: cada 100 ms toma el ultimo valor de la rampa local (C2) y
//   lo envia a C1 para escribirlo en Cliente.Rampa.
//   Los botones "C5 · Detener rampa" / "C5 · Reanudar rampa" envian
//   msg.topic = 'pausa' (true/false): detenida, no se escribe nada, asi la
//   captura de KeepAlive de la Parte 3.4 queda sin Writes intercalados.
// Entrada: msg del inject "C5 · Cada 100 ms", o { topic: 'pausa', payload }.
// Salida: { topic: 'rampa', payload: UInt16 } -> C1.
// Excepciones: si C2 todavia no genero ningun valor, no se envia nada.
// =====================================================================
if (msg.topic === 'pausa') {
    const pausada = msg.payload === true;
    flow.set('rampaPausada', pausada);
    node.status(pausada ? { fill: 'grey', shape: 'ring', text: 'escritura detenida' } : {});
    node.log(new Date().toISOString() + ' escritura de rampa ' + (pausada ? 'DETENIDA' : 'reanudada'));
    return null;
}
if (flow.get('rampaPausada')) return null;
const valor = flow.get('rampaGenerada');
if (valor === undefined) return null;
return { topic: 'rampa', payload: valor };
