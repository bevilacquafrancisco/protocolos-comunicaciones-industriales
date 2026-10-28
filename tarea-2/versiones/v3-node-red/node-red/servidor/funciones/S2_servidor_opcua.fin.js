// =====================================================================
// BLOQUE S2 · Servidor OPC UA — "On Close" de la function node
// ---------------------------------------------------------------------
// Descripcion: detiene el servidor al redesplegar o al detener Node-RED.
//   On Close es sincrono en Node-RED: se lanza el cierre sin esperarlo y
//   sin demora de cortesia (detener(0)), para liberar el puerto 4840 lo
//   antes posible. Si el nuevo despliegue llega antes, On Start reintenta.
// =====================================================================
const controlador = context.get('controlador');
if (controlador) {
    controlador.detener(0).catch((e) => node.warn('cierre del servidor: ' + e.message));
    context.set('controlador', undefined);
}
