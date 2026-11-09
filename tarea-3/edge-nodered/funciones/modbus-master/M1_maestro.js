// =====================================================================
// M1 · maestro MODBus — "On Message" del function node
// docs/diagramas/flujo-maestro.mmd, bloques [DF-2.3] (comandos pendientes)
// y [DF-2.17] (reconfiguracion en vivo, I-04)
// ---------------------------------------------------------------------
// Descripcion: atiende los mensajes que llegan al maestro, segun msg.topic:
//   bytes                bloque recibido por serial in (lo envia M2)
//   puerto-confirmado    respuesta de serial control (lo envia M3)
//   escribir             {nombre, valor} desde el Dashboard u OPC UA (F4)
//   reconfigurar         configuracion completa (la arma D1 desde el Dashboard)
//   probar               {fc, direccion, cantidad}: una peticion, trama cruda de ida y vuelta
//   trama                "ID PDU" en hexadecimal: el maestro agrega el CRC propio
//   descubrir            opciones del asistente de descubrimiento
//   explorar             {fc, desde, hasta}: que direcciones existen
//   cancelar             corta el descubrimiento o la exploracion
//   reiniciar-contadores pone en cero OK / CRC_ERROR / TIMEOUT / EXCEPTION
//   pedir-config         reenvia la configuracion vigente al panel
// Las respuestas salen por la salida 5 con el topic indicado en cada caso.
// =====================================================================
const pdci = global.get('pdci');
const maestro = context.get('maestro');
if (!maestro) return null;

const responder = (topic, payload, extra) =>
    node.send([null, null, null, null, Object.assign({ topic, payload }, extra || {})]);
const fallar = (topic, error) => responder(topic, { ok: false, error: String(error && error.message || error) });

switch (msg.topic) {
    case 'bytes':
        maestro.recibir(msg.payload);
        return null;

    case 'puerto-confirmado':
        context.get('confirmarPuerto')(msg.payload);
        return null;

    case 'escribir': {
        const { nombre, valor } = msg.payload || {};
        maestro.escribir(nombre, valor)
            .then((r) => responder('escritura', Object.assign({ nombre, valor }, r), { _origen: msg._origen }))
            .catch((e) => fallar('escritura', e));
        return null;
    }

    case 'reconfigurar':                                         // [DF-2.17]
        maestro.reconfigurar(msg.payload).then((r) => {
            if (r.ok) {
                try {
                    pdci.configuracion.guardar(pdci.rutas.config, r.config);   // sobrevive al reinicio
                } catch (e) {
                    node.warn(`configuracion aplicada pero no guardada: ${e.message}`);
                    r.errores = (r.errores || []).concat(`no se pudo guardar: ${e.message}`);
                }
                responder('config', r.config, { origen: 'usuario' });
            }
            responder('reconfiguracion', { ok: r.ok, errores: r.errores });
        }).catch((e) => fallar('reconfiguracion', e));
        return null;

    case 'probar':
        maestro.probar(msg.payload || {}).then((r) => responder('prueba', r)).catch((e) => fallar('prueba', e));
        return null;

    case 'trama':
        maestro.tramaManual(String(msg.payload || '')).then((r) => responder('trama-manual', r))
            .catch((e) => fallar('trama-manual', e));
        return null;

    case 'descubrir':
        maestro.descubrir(msg.payload || {}, (p) => responder('progreso', p))
            .then((r) => responder('descubrimiento', r)).catch((e) => fallar('descubrimiento', e));
        return null;

    case 'explorar':
        maestro.explorar(msg.payload || {}).then((r) => responder('exploracion', r))
            .catch((e) => fallar('exploracion', e));
        return null;

    case 'cancelar':
        maestro.cancelar();
        return null;

    case 'reiniciar-contadores':
        maestro.reiniciarContadores();
        return null;

    case 'pedir-config':
        responder('config', maestro.config);
        return null;

    default:
        node.warn(`comando desconocido: ${msg.topic}`);
        return null;
}
