// =====================================================================
// BLOQUE C1 · Cliente OPC UA — "On Close" de la function node
// ---------------------------------------------------------------------
// Descripcion: al redesplegar o detener Node-RED cierra la sesion de forma
//   ordenada (CloseSession + CLO + FIN de TCP), cancela un reintento
//   pendiente y marca el nodo como inactivo para que una conexion que
//   termine despues no quede viva.
// =====================================================================
context.set('activo', false);
const reintento = context.get('reintento');
if (reintento) clearTimeout(reintento);
const controlador = context.get('controlador');
if (controlador) {
    controlador.detener().catch((e) => node.warn('cierre del cliente: ' + e.message));
    context.set('controlador', undefined);
}
