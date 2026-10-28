// =====================================================================
// BLOQUE C6 · Registro en consola — Raspberry Pi 2
// diagramas/flujo_cliente.md, bloque C6 · consigna Parte 3.5
// ---------------------------------------------------------------------
// Descripcion: una vez por segundo imprime la rampa que genera esta placa,
//   la que recibe del servidor (Servidor.Rampa) y su SourceTimestamp, y
//   ademas la antiguedad del dato: si el cable esta desconectado, la
//   antiguedad crece y se ve en la consola que el LED quedo congelado.
// Entrada: msg del inject "C6 · Cada 1 s".
// Salida: msg.payload con la linea.
// Excepciones: ninguna.
// =====================================================================
const generada = flow.get('rampaGenerada');
const recibido = flow.get('servidorRampa');
let ts = 'sin dato';
let antiguedad = '';
if (recibido && recibido.sourceTimestamp) {
    const t = new Date(recibido.sourceTimestamp);
    ts = t.toISOString();
    antiguedad = ' antiguedad=' + (Date.now() - t.getTime()) + ' ms';
}
const linea = 'CLIENTE generada=' + (generada === undefined ? '-' : generada) +
    ' recibida(Servidor.Rampa)=' + (recibido ? recibido.valor : '-') +
    ' SourceTimestamp=' + ts + antiguedad + (recibido ? ' modo=' + recibido.modo : '');
node.log(linea);
return { payload: linea };
