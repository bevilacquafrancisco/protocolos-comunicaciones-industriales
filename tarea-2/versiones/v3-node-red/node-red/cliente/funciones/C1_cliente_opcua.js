// =====================================================================
// BLOQUE C5 -> C1 · Escrituras del cliente
// diagramas/flujo_cliente.md, bloque C5 · consigna Parte 3.3
// ---------------------------------------------------------------------
// Descripcion: escribe el pulsador local en Cliente.EstadoPulsador y la
//   rampa local en Cliente.Rampa. Si no hay conexion, o el Write anterior
//   de esa variable sigue pendiente, la escritura se omite y se cuenta: al
//   reconectar se escribe el valor vigente, no una cola de valores viejos.
// Entrada: msg.topic 'pulsador' (boolean) | 'rampa' (0-65535).
// Salida: ninguna.
// Excepciones: los errores de escritura llegan como evento por la salida 2
//   (write_error) desde cliente_opcua.js.
// =====================================================================
const controlador = context.get('controlador');
if (!controlador) {
    context.set('omitidasSinConexion', (context.get('omitidasSinConexion') || 0) + 1);
    return null;
}
if (msg.topic === 'pulsador') {
    controlador.escribirPulsador(msg.payload === true).then((sc) => {
        if (sc && sc !== 'Good') node.warn('Write Cliente.EstadoPulsador -> ' + sc);
    });
} else if (msg.topic === 'rampa') {
    controlador.escribirRampa(msg.payload).then((sc) => {
        if (sc && sc !== 'Good') node.warn('Write Cliente.Rampa -> ' + sc);
    });
}
return null;
