// =====================================================================
// BLOQUE C2 · Rampa triangular — Raspberry Pi 2
// diagramas/flujo_cliente.md, bloque C2 · consigna Parte 3.2
// ---------------------------------------------------------------------
// Descripcion: cada 50 ms calcula la rampa triangular 0-65535 de periodo
//   8 s (4 s de subida, 4 s de bajada) a partir del reloj. Solo actualiza
//   el contexto: la escritura en Cliente.Rampa la hace C5 cada 100 ms, que
//   es la tasa que pide la consigna (generar a 50 ms, escribir a 100 ms).
// Entrada: msg del inject "C2 · Tick".
// Salida: ninguna.
// Excepciones: ninguna.
//
// Firma: senales.triangular(tMs: number, periodoMs: number, tickMs: number,
//   maximo?: number) : number
// =====================================================================
const config = global.get('config');
const senales = global.get('senales');
const valor = senales.triangular(Date.now(), config.senales.periodoTriangularMs, config.senales.tickMs,
    config.senales.maximo);
flow.set('rampaGenerada', valor);
return null;
