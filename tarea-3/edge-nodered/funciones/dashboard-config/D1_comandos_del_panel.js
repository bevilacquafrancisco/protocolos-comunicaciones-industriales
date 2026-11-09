// =====================================================================
// D1 · comandos del panel — I-04 (configuracion en vivo)
// docs/diagramas/flujo-maestro.mmd, bloque [DF-2.17]
// ---------------------------------------------------------------------
// Descripcion: traduce lo que manda el Dashboard en comandos para el maestro.
//   Los cambios parciales (solo el enlace, solo el mapa, el resultado del
//   descubrimiento) se combinan con la configuracion VIGENTE y salen como una
//   configuracion completa con topic "reconfigurar". La validacion definitiva
//   la hace el maestro (lib/configuracion.js): el Dashboard es entrada no confiable.
// Entradas (msg.topic): aplicar-enlace · aplicar-mapa · aplicar-descubierto ·
//   agregar-al-mapa · restaurar-fabrica · y, sin cambios, probar · trama ·
//   descubrir · explorar · cancelar · reiniciar-contadores · escribir · pedir-config
// Salida: comando para M1 (por el link "-> maestro (comandos)").
// =====================================================================
const pdci = global.get('pdci');
const vigente = flow.get('config');
const nueva = () => pdci.configuracion.clonar(vigente);
const enviar = (topic, payload) => ({ topic, payload, _origen: 'dashboard' });

if (!vigente && msg.topic !== 'pedir-config' && msg.topic !== 'restaurar-fabrica') {
    node.warn('todavia no se recibio la configuracion del maestro');
    return enviar('pedir-config', null);
}

switch (msg.topic) {
    case 'aplicar-enlace': {
        const c = nueva();
        const p = msg.payload || {};
        Object.assign(c.puerto, p.puerto || {});
        Object.assign(c.esclavo, p.esclavo || {});
        Object.assign(c.sondeo, p.sondeo || {});
        return enviar('reconfigurar', c);
    }
    case 'aplicar-mapa': {
        const c = nueva();
        c.mapa = Array.isArray(msg.payload) ? msg.payload : [];
        return enviar('reconfigurar', c);
    }
    case 'aplicar-descubierto': {
        // Resultado del asistente: Unit ID, baud y paridad del esclavo encontrado.
        const c = nueva();
        const d = msg.payload || {};
        c.esclavo.id = d.id;
        Object.assign(c.puerto, { baud: d.baud, paridad: d.paridad });
        return enviar('reconfigurar', c);
    }
    case 'agregar-al-mapa': {
        // Una direccion hallada por la exploracion pasa al mapa con un nombre generico,
        // que el operador puede renombrar despues en la tabla.
        const c = nueva();
        const { fc, direccion } = msg.payload || {};
        const esBit = Number(fc) === 1 || Number(fc) === 2;
        const area = { 1: 'Coil', 2: 'DI', 3: 'HR', 4: 'IR' }[Number(fc)] || 'Var';
        c.mapa.push({ nombre: `Descubierto/${area}_${Number(direccion)}`, fc: Number(fc), direccion: Number(direccion),
            tipo: esBit ? 'bool' : 'uint16', escritura: Number(fc) === 1 || Number(fc) === 3 });
        return enviar('reconfigurar', c);
    }
    case 'restaurar-fabrica':
        return enviar('reconfigurar', pdci.configuracion.cargar(null).config);
    case 'probar':
    case 'trama':
    case 'descubrir':
    case 'explorar':
    case 'cancelar':
    case 'reiniciar-contadores':
    case 'escribir':
    case 'pedir-config':
        return enviar(msg.topic, msg.payload);
    default:
        node.warn(`comando del panel desconocido: ${msg.topic}`);
        return null;
}
