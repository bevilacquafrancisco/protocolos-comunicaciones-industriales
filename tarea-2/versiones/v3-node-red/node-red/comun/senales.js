/**
 * senales.js
 * Autores: Bevilacqua Francisco, Peralta Agustina
 * Fecha de creacion: 2026-10-13
 * Version: 1
 *
 * Descripcion general
 * -------------------
 * Logica pura de las senales del trabajo: rampa diente de sierra (servidor),
 * rampa triangular (cliente), escalado de UInt16 a ciclo de trabajo PWM 0-255
 * con correccion gamma opcional y validacion de los valores que llegan por
 * OPC UA.
 *
 * Es un modulo aparte, y no codigo pegado dentro de las function nodes, para
 * que haya UNA sola implementacion y se pueda verificar en la PC sin las
 * placas (herramientas/prueba_senales.js). settings.js lo expone en
 * functionGlobalContext y las function nodes lo usan con global.get('senales').
 *
 * Decision de diseno: las rampas se CALCULAN A PARTIR DEL RELOJ y no con un
 * contador que se incrementa en cada tick. El event loop de Node.js no
 * garantiza que un temporizador de 50 ms dispare cada 50 ms exactos. Con un
 * contador, cada atraso se acumula y el periodo real se estira; calculando la
 * fase como t mod T, el error de cada muestra queda acotado a un tick y el
 * periodo medio es exacto.
 *
 * Dependencias externas: ninguna (Node.js >= 18).
 */
'use strict';

const MAXIMO_UINT16 = 65535;

// ==========================================================================
// Validacion de parametros
// ==========================================================================

/**
 * Descripcion: verifica que periodo y tick sean enteros positivos y que el
 *   periodo sea multiplo del tick, para que cada periodo tenga una cantidad
 *   entera de muestras.
 * Parametros:
 *   periodoMs (number): periodo de la senal en milisegundos.
 *   tickMs (number): intervalo de actualizacion en milisegundos.
 * Retorna: (number) cantidad de muestras por periodo.
 * Excepciones: RangeError si los parametros no cumplen las condiciones.
 */
function muestrasPorPeriodo(periodoMs, tickMs) {
    if (!Number.isInteger(periodoMs) || !Number.isInteger(tickMs) ||
        periodoMs <= 0 || tickMs <= 0) {
        throw new RangeError('periodo y tick deben ser enteros positivos');
    }
    if (periodoMs % tickMs !== 0) {
        throw new RangeError('el periodo debe ser multiplo del tick');
    }
    return periodoMs / tickMs;
}

/**
 * Descripcion: indice de la muestra (0..n-1) que corresponde al instante t.
 * Parametros:
 *   tMs (number): instante en ms (tipicamente Date.now()).
 *   periodoMs (number), tickMs (number): ver muestrasPorPeriodo().
 * Retorna: (number) indice entero de muestra dentro del periodo.
 * Excepciones: RangeError (propagada de muestrasPorPeriodo).
 */
function indiceMuestra(tMs, periodoMs, tickMs) {
    muestrasPorPeriodo(periodoMs, tickMs);
    // Doble modulo: hace que la fase sea positiva aun para t negativo.
    const fase = ((Math.floor(tMs) % periodoMs) + periodoMs) % periodoMs;
    return Math.floor(fase / tickMs);
}

// ==========================================================================
// BLOQUE S3 — Rampa diente de sierra del servidor (consigna Parte 2.3)
// ==========================================================================

/**
 * Descripcion: diente de sierra ascendente de 0 a maximo. La primera muestra
 *   del periodo vale 0 y la ultima vale exactamente maximo; en la muestra
 *   siguiente vuelve a 0 ("al llegar al maximo, el valor vuelve a 0").
 *   Con T = 4000 ms y tick = 50 ms hay 80 escalones de 65535/79 = 829,6.
 * Parametros:
 *   tMs (number): instante en ms.
 *   periodoMs (number): periodo, 4000 en la consigna.
 *   tickMs (number): actualizacion, 50 en la consigna.
 *   maximo (number): valor tope, 65535 por defecto.
 * Retorna: (number) entero en [0, maximo].
 * Excepciones: RangeError si el periodo no es multiplo del tick.
 * Ejemplo: sierra(0, 4000, 50) -> 0 ; sierra(3950, 4000, 50) -> 65535
 */
function sierra(tMs, periodoMs, tickMs, maximo = MAXIMO_UINT16) {
    const n = muestrasPorPeriodo(periodoMs, tickMs);
    if (n < 2) throw new RangeError('se necesitan al menos 2 muestras');
    const k = indiceMuestra(tMs, periodoMs, tickMs);
    return Math.round((k * maximo) / (n - 1));
}

// ==========================================================================
// BLOQUE C2 — Rampa triangular del cliente (consigna Parte 3.2)
// ==========================================================================

/**
 * Descripcion: rampa triangular simetrica: sube de 0 a maximo en la primera
 *   mitad del periodo y baja a 0 en la segunda (4 s + 4 s en la consigna).
 *   La muestra central vale exactamente maximo.
 * Parametros:
 *   tMs (number): instante en ms.
 *   periodoMs (number): periodo completo, 8000 en la consigna.
 *   tickMs (number): actualizacion, 50 en la consigna.
 *   maximo (number): valor tope, 65535 por defecto.
 * Retorna: (number) entero en [0, maximo].
 * Excepciones: RangeError si el periodo no es multiplo de 2 * tick.
 * Ejemplo: triangular(4000, 8000, 50) -> 65535
 */
function triangular(tMs, periodoMs, tickMs, maximo = MAXIMO_UINT16) {
    const n = muestrasPorPeriodo(periodoMs, tickMs);
    if (n % 2 !== 0) throw new RangeError('el periodo debe tener cantidad par de muestras');
    const mitad = n / 2;
    const k = indiceMuestra(tMs, periodoMs, tickMs);
    const pasos = k <= mitad ? k : n - k;
    return Math.round((pasos * maximo) / mitad);
}

// ==========================================================================
// BLOQUES S6 / C4 — Escalado de UInt16 a PWM 0-255 (consigna Partes 2.4 y 3.7)
// ==========================================================================

/**
 * Descripcion: escala un valor 0..maximo al ciclo de trabajo 0..255 que espera
 *   pigpio. Con gamma = 1 la escala es lineal; con gamma = 2,2 aplica
 *   brillo = 255 * (v / maximo)^2,2 (consigna Parte 3.7).
 * Parametros:
 *   valor (number): entero en [0, maximo].
 *   maximo (number): 65535 por defecto.
 *   gamma (number): exponente > 0; 1 por defecto (lineal).
 * Retorna: (number) entero en [0, 255].
 * Excepciones: RangeError si valor esta fuera de rango o gamma <= 0.
 * Ejemplo: escala255(65535) -> 255 ; escala255(32768, 65535, 2.2) -> 56
 */
function escala255(valor, maximo = MAXIMO_UINT16, gamma = 1) {
    if (!esUInt16(valor) || valor > maximo) {
        throw new RangeError('valor fuera de rango: ' + valor);
    }
    if (!(gamma > 0)) throw new RangeError('gamma debe ser positivo');
    return Math.round(255 * Math.pow(valor / maximo, gamma));
}

/**
 * Descripcion: convierte un ciclo de trabajo 0-255 al porcentaje que espera
 *   el nodo "pi gpiod out" en modo PWM. Ese nodo acepta 0-100 y aplica
 *   set_PWM_dutycycle(parseInt(pct * 2.55)): si se le pasara round(d / 2.55)
 *   solo habria 101 niveles y se perderia resolucion. Sumando medio paso antes
 *   de dividir, parseInt() recupera exactamente el ciclo de trabajo original
 *   para los 256 valores (verificado en prueba_senales.js, prueba 9).
 * Parametros: duty (number): entero en [0, 255].
 * Retorna: (number) porcentaje en [0, 100], posiblemente no entero.
 * Excepciones: RangeError si duty esta fuera de rango.
 */
function dutyAPorcentajePiGpiod(duty) {
    if (!Number.isInteger(duty) || duty < 0 || duty > 255) {
        throw new RangeError('duty fuera de rango: ' + duty);
    }
    return Math.min(100, (duty + 0.5) / 2.55);
}

// ==========================================================================
// BLOQUE S5 — Validacion de escrituras recibidas por OPC UA
// ==========================================================================

/**
 * Descripcion: indica si un valor es un UInt16 valido (entero 0..65535).
 *   Se usa en el setter del servidor antes de aceptar un Write: un DataValue
 *   mal formado no debe llegar al PWM.
 * Parametros: valor (any).
 * Retorna: (boolean).
 * Excepciones: ninguna.
 */
function esUInt16(valor) {
    return Number.isInteger(valor) && valor >= 0 && valor <= MAXIMO_UINT16;
}

/**
 * Descripcion: indica si un valor es un Boolean estricto (true/false). No se
 *   aceptan 0/1 ni cadenas: el tipo del nodo es Boolean y el servidor debe
 *   responder Bad_TypeMismatch ante cualquier otra cosa.
 * Parametros: valor (any).
 * Retorna: (boolean).
 * Excepciones: ninguna.
 */
function esBooleano(valor) {
    return valor === true || valor === false;
}

module.exports = Object.freeze({
    MAXIMO_UINT16,
    muestrasPorPeriodo,
    indiceMuestra,
    sierra,
    triangular,
    escala255,
    dutyAPorcentajePiGpiod,
    esUInt16,
    esBooleano,
});
