#!/usr/bin/env python3
"""
comun.py
Autores: Peralta Agustina (version original), Bevilacqua Francisco (correccion)
Fecha de creacion: 2026-10-20
Version: 2.0

Descripcion general
-------------------
Constantes y funciones que usan el servidor (RPi 1) y los dos clientes (RPi 2).
Antes estaban copiadas en cada archivo; un valor cambiado en uno solo (un pin,
un NodeId) rompia el intercambio sin aviso.

Contenido:
- Configuracion: pines, endpoint, NodeIds, URIs de aplicacion.
- Senales: rampa diente de sierra (servidor), rampa triangular (cliente) y
  escalado a 0-255 para el LED PWM, con correccion gamma opcional (3.7).
- Hora en UTC y lineas LATENCIA para medir_latencia.py (3.4).
- GPIO: pulsador por eventos y salidas (LED digital y LED PWM).

Dependencias externas
---------------------
gpiozero (con el backend lgpio en la Raspberry Pi). Para probar en la PC sin
placas: GPIOZERO_PIN_FACTORY=mock y GPIOZERO_MOCK_PIN_CLASS=mockpwmpin.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from gpiozero import LED, PWMLED, Button

# =============================================================================
# CONFIGURACION
# =============================================================================

# Pines BCM, iguales en las dos placas (pin fisico entre parentesis).
PIN_PULSADOR = 17       # (11) entre 3,3 V y GPIO17, pull-down INTERNO
PIN_LED_DIGITAL = 27    # (13) GPIO27 -> 220 ohm -> LED -> GND
PIN_LED_PWM = 18        # (12) GPIO18 -> 220 ohm -> LED -> GND
ANTIRREBOTE_S = 0.05

# IP literal de eth0: un nombre de host podria resolverse por la Wi-Fi y el
# trafico dejaria de ir por el enlace directo (consigna 1.4).
URL_SERVIDOR = "opc.tcp://192.168.10.1:4840"
ENDPOINT_ESCUCHA = "opc.tcp://0.0.0.0:4840"   # todas las interfaces (2.1)

NAMESPACE_URI = "urn:unraf:pdci:t2"
URI_CLIENTE = "urn:unraf:pdci:t2:cliente"     # debe coincidir con su certificado

NODE_ESTADO_SERVIDOR = "ns=1;s=Servidor.EstadoPulsador"
NODE_RAMPA_SERVIDOR = "ns=1;s=Servidor.Rampa"
NODE_ESTADO_CLIENTE = "ns=1;s=Cliente.EstadoPulsador"
NODE_RAMPA_CLIENTE = "ns=1;s=Cliente.Rampa"

RAMPA_MAX = 65535
PERIODO_RAMPA_SERVIDOR_S = 4.0
PERIODO_RAMPA_CLIENTE_S = 8.0
PASO_RAMPA_S = 0.050          # generacion de las dos rampas (2.3 y 3.2)
INTERVALO_LOG_S = 0.5

# Carpeta de certificados junto a los programas, no una ruta de la maquina.
PKI_POR_DEFECTO = Path(__file__).resolve().parent / "pki"


# =============================================================================
# SENALES
# =============================================================================

def rampa_diente_sierra(t):
    """
    Diente de sierra ascendente 0..65535, periodo 4 s (consigna 2.3).

    Parametros:
        t (float): segundos desde el inicio de la rampa.
    Retorna:
        int: valor en [0, 65535]; al llegar al maximo vuelve a 0.
    """
    fase = (t % PERIODO_RAMPA_SERVIDOR_S) / PERIODO_RAMPA_SERVIDOR_S
    return min(RAMPA_MAX, int(fase * (RAMPA_MAX + 1)))


def rampa_triangular(t):
    """
    Rampa triangular 0..65535, periodo 8 s: 4 s de subida y 4 de bajada (3.2).

    Parametros:
        t (float): segundos desde el inicio de la rampa.
    Retorna:
        int: valor en [0, 65535].
    """
    mitad = PERIODO_RAMPA_CLIENTE_S / 2
    fase = t % PERIODO_RAMPA_CLIENTE_S
    if fase < mitad:
        return min(RAMPA_MAX, int((fase / mitad) * RAMPA_MAX))
    return max(0, int(((PERIODO_RAMPA_CLIENTE_S - fase) / mitad) * RAMPA_MAX))


def escalar_a_pwm(valor, gamma=False):
    """
    Escala la rampa recibida a 0..255, como pide la consigna (2.4).

    Con gamma=True aplica brillo = 255 * (valor / 65535) ^ 2,2 (3.7): el ojo
    percibe el brillo de forma aproximadamente logaritmica, y una rampa
    lineal de ciclo de trabajo se ve "rapida" abajo y plana arriba.

    Parametros:
        valor (int): rampa en [0, 65535]; se satura si viene fuera de rango.
        gamma (bool): aplicar correccion gamma 2,2.
    Retorna:
        int: ciclo de trabajo en [0, 255].
    """
    relativo = max(0, min(RAMPA_MAX, int(valor))) / RAMPA_MAX
    if gamma:
        relativo = relativo ** 2.2
    return round(relativo * 255)


# =============================================================================
# HORA Y REGISTRO
# =============================================================================

def ahora_utc():
    """Retorna datetime: hora actual en UTC (para SourceTimestamp)."""
    return datetime.now(timezone.utc)


def ahora_iso():
    """Retorna str: hora UTC con milisegundos y sufijo Z (formato de medir_latencia.py)."""
    return ahora_utc().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def formatear_ts(ts):
    """
    Formatea un SourceTimestamp para la consola.

    Parametros:
        ts (datetime | None): marca de tiempo de un DataValue.
    Retorna:
        str: hora ISO con milisegundos, o "sin SourceTimestamp".
    """
    if ts is None:
        return "sin SourceTimestamp"
    if ts.tzinfo is None:   # asyncua entrega UTC sin zona
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.strftime("%H:%M:%S.%f")[:-3] + "Z"


class _FormatoCompacto(logging.Formatter):
    """Mensajes de asyncua en una linea, con la excepcion resumida (sin traceback)."""

    def format(self, registro):
        texto = f"{ahora_iso()} [asyncua] {registro.levelname}: {registro.getMessage()}"
        if registro.exc_info and registro.exc_info[1] is not None:
            exc = registro.exc_info[1]
            texto += f" ({type(exc).__name__}: {exc})"[:300]
        return texto


def configurar_registro():
    """
    Avisos y errores internos de asyncua (p. ej. el timeout de sesion
    revisado o una respuesta que llega tarde) en una linea con hora, para
    que el registro de la prueba de desconexion se pueda leer.
    """
    manejador = logging.StreamHandler()
    manejador.setFormatter(_FormatoCompacto())
    logging.basicConfig(level=logging.WARNING, handlers=[manejador])


def registrar_latencia(evento, estado):
    """
    Imprime una linea que medir_latencia.py empareja entre las dos placas.

    Parametros:
        evento (str): "pulsador_local" (flanco en esta placa) o
            "led_digital" (cambio del LED que refleja a la otra placa).
        estado (bool): nuevo estado.
    """
    print(f"LATENCIA {evento}={'ON' if estado else 'OFF'} t={ahora_iso()}", flush=True)


# =============================================================================
# GPIO
# =============================================================================

class Pulsador:
    """
    Pulsador leido por eventos de gpiozero, no por sondeo.

    Responsabilidad: avisar al bucle asyncio de cada flanco. Con sondeo cada
    50-100 ms (version original) una pulsacion breve se podia perder y se
    sumaba hasta 100 ms de latencia que no es del protocolo.

    Atributos:
        cambio (asyncio.Event): se activa en cada flanco; quien lo consume lo
            limpia y lee `presionado`.
    """

    def __init__(self, loop):
        """
        Parametros:
            loop (asyncio.AbstractEventLoop): bucle donde corre el programa.
                gpiozero llama a los manejadores desde su propio hilo, por eso
                el aviso se pasa con call_soon_threadsafe.
        """
        self._loop = loop
        self.cambio = asyncio.Event()
        # pull_up=False: pull-down interno, el pulsador lleva 3,3 V al pin.
        self._boton = Button(PIN_PULSADOR, pull_up=False, bounce_time=ANTIRREBOTE_S)
        self._boton.when_pressed = lambda: self._flanco(True)
        self._boton.when_released = lambda: self._flanco(False)

    def _flanco(self, estado):
        registrar_latencia("pulsador_local", estado)
        self._loop.call_soon_threadsafe(self.cambio.set)

    @property
    def presionado(self):
        """bool: estado actual del pulsador."""
        return bool(self._boton.is_pressed)

    def cerrar(self):
        self._boton.close()


class Salidas:
    """
    LED digital y LED PWM de una placa.

    Atributos:
        estado_led (bool | None): ultimo estado del LED digital.
        duty (int): ultimo ciclo de trabajo 0..255 del LED PWM.
    """

    def __init__(self, gamma=False):
        """
        Parametros:
            gamma (bool): aplicar correccion gamma al escalar (3.7).
        """
        self._gamma = gamma
        self._led = LED(PIN_LED_DIGITAL)
        # PWM por software de lgpio, 100 Hz (valor por defecto de gpiozero).
        self._pwm = PWMLED(PIN_LED_PWM)
        self.estado_led = None
        self.duty = 0

    def led_digital(self, estado):
        """Enciende o apaga el LED; registra LATENCIA solo si cambio."""
        estado = bool(estado)
        if estado == self.estado_led:
            return
        self._led.value = estado
        self.estado_led = estado
        registrar_latencia("led_digital", estado)

    def led_pwm(self, valor_rampa):
        """
        Parametros:
            valor_rampa (int): 0..65535.
        Retorna:
            int: ciclo de trabajo aplicado, 0..255.
        """
        self.duty = escalar_a_pwm(valor_rampa, self._gamma)
        self._pwm.value = self.duty / 255   # gpiozero espera 0.0 .. 1.0
        return self.duty

    def cerrar(self):
        self._led.off()
        self._pwm.off()
        self._led.close()
        self._pwm.close()
