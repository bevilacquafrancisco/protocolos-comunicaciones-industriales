// =====================================================================
// BLOQUES S6 / C4 · LED PWM (comun a ambas placas)
// diagramas/flujo_servidor.md S6 · diagramas/flujo_cliente.md C4
// consigna Partes 2.4 y 3.7
// ---------------------------------------------------------------------
// Descripcion: escala la Rampa recibida del OTRO equipo (UInt16) a ciclo
//   de trabajo 0-255, con correccion gamma opcional (config.senales), y
//   la convierte al porcentaje que espera "pi gpiod out" en modo PWM.
// Entrada: msg.payload entero 0-65535.
// Salida: msg.payload porcentaje 0-100 (exacto para pigpio, ver
//   senales.dutyAPorcentajePiGpiod); msg.duty con el 0-255 para la traza.
// Excepciones: un valor fuera de rango se descarta con advertencia.
//
// Firmas: senales.escala255(valor: number, maximo?: number,
//   gamma?: number) : number · senales.dutyAPorcentajePiGpiod(duty: number)
//   : number
// =====================================================================
const config = global.get('config');
const senales = global.get('senales');
if (!senales.esUInt16(msg.payload)) {
    node.warn('Rampa fuera de rango: ' + msg.payload);
    return null;
}
const gamma = config.senales.usarGamma ? config.senales.gamma : 1;
const duty = senales.escala255(msg.payload, config.senales.maximo, gamma);
return { payload: senales.dutyAPorcentajePiGpiod(duty), duty };
