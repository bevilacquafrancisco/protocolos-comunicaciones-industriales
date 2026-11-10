// =====================================================================
// O1 · servidor OPC UA — "On Message" del function node
// docs/diagramas/flujo-servidor-opcua.mmd, bloques [DF-5.3], [DF-5.6] y [DF-5.7]
// ---------------------------------------------------------------------
// Descripcion: segun msg.topic:
//   estado          instantanea del maestro (link de M1)  -> Status.MODBUS.*      [DF-5.3]
//   <nombre>        valor de una variable (link de M1)    -> Inputs/Outputs/Mapa  [DF-5.3]
//   salud           tick de 1 s -> Status.OPCUA.Estado y capa OPCUA del panel   [DF-5.6]
//   certificados    pide la lista de confianza                                   [DF-5.7]
//   confiar/revocar huella SHA-1 desde el panel                                  [DF-5.7]
// Salida 1: lista de certificados para el panel.
// =====================================================================
const servidor = context.get('servidor');
if (!servidor) return null;   // todavia arrancando (o no arranco: ver el estado del nodo)
const pdci = global.get('pdci');

const enviarCertificados = (aviso) => node.send({ topic: 'certificados',
    payload: Object.assign(servidor.listarCertificados(), { huellaPropia: servidor.huellaPropia(), aviso: aviso || null }) });

switch (msg.topic) {
    case 'estado':
        servidor.publicarEstadoModbus(msg.payload);
        return null;
    case 'salud':
        pdci.capas.actualizar('OPCUA', servidor.estadisticas());
        return null;
    case 'certificados':
        enviarCertificados();
        return null;
    case 'confiar':
    case 'revocar': {
        const accion = msg.topic === 'confiar' ? servidor.confiarCertificado : servidor.revocarCertificado;
        accion(String(msg.payload || ''))
            .then((r) => enviarCertificados(r.ok ? `${msg.topic}: hecho` : r.error))
            .catch((e) => enviarCertificados(e.message));
        return null;
    }
    default:
        // Valor de una variable del mapa: topic = nombre (Inputs/Pulsador, ...).
        if (typeof msg.topic === 'string' && msg.payload !== undefined) {
            servidor.publicarValor(msg.topic, msg.payload, msg.calidad || 'good', msg.ts);
        }
        return null;
}
