// =====================================================================
// D2 · repartir respuestas — Dashboard de configuracion
// ---------------------------------------------------------------------
// Descripcion: recibe las respuestas del maestro (salida 5 de M1) y manda a
//   cada panel solo lo suyo. Guarda la configuracion vigente en el contexto
//   del flow (la usa D1) y la adjunta en msg.config a TODOS los mensajes: los
//   ui-template reenvian su ultimo mensaje al recargar la pagina, y asi ningun
//   panel queda sin la configuracion aunque su ultimo mensaje sea otro.
// Salidas: [1] enlace y sondeo  [2] mapa de registros  [3] prueba y trama
//          manual  [4] descubrimiento y exploracion
// =====================================================================
if (msg.topic === 'config') flow.set('config', msg.payload);
msg.config = flow.get('config') || null;
if (msg.topic === 'config') msg.origen = msg.origen || 'usuario';

const copia = () => RED.util.cloneMessage(msg);
switch (msg.topic) {
    case 'config':
        return [copia(), copia(), copia(), copia()];
    case 'reconfiguracion':
        return [copia(), copia(), null, copia()];
    case 'prueba':
    case 'trama-manual':
        return [null, null, msg, null];
    case 'progreso':
    case 'descubrimiento':
    case 'exploracion':
        return [null, null, null, msg];
    default:
        return null;          // escritura, etc.: los atiende el panel de estadisticas
}
