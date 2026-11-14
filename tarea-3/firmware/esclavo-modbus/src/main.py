"""
main.py  (ESCLAVO MODBus RTU — Tarea 3, dispositivo 1)
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Capa de hardware y lazo principal del esclavo MODBus RTU sobre RS-485. Es el esclavo de
la Tarea Nº1 con la capa de protocolo reescrita: ya no usa umodbus; el CRC, la
delimitacion por silencio t3,5 y el despacho de funciones son propios (invariante I-01)
y viven en lib/modbus_slave/, que no depende del hardware y se prueba en la PC.

Esta capa hace solo lo que exige el hardware:
  - elegir el perfil (dispositivo 1 o esclavo desconocido) y configurar el UART2;
  - controlar DE/RE del MAX485, vaciando el buffer de transmision antes de soltar la linea;
  - leer el pulsador y el ADC, y llevar el coil y el holding register a los LED.

Correspondencia con el diagrama de flujo (docs/diagramas/flujo-esclavo.mmd)
---------------------------------------------------------------------------
  [DF-1.1]  Inicio                       -> elegir_perfil(), Esclavo.__init__()
  [DF-1.2]  Tiempos del enlace           -> Esclavo.__init__() (frame_parser.tiempos_us)
  [DF-1.3]  Publicar entradas            -> Esclavo.publicar_entradas()
  [DF-1.4]  ¿Hay bytes en el UART?       -> Esclavo.atender_bus()
  [DF-1.5]  Acumular bytes               -> Esclavo.atender_bus() (EnsambladorTramas.alimentar)
  [DF-1.6]  ¿Silencio >= t3,5?           -> Esclavo.atender_bus() (EnsambladorTramas.trama_completa)
  [DF-1.7]  a [DF-1.15]                  -> Esclavo.procesar() (frame_parser.procesar_trama)
  [DF-1.16] Transmitir                   -> Esclavo.transmitir()
  [DF-1.17] Aplicar salidas              -> Esclavo.aplicar_salidas()
  [DF-1.18] a [DF-1.20] Descartes        -> contadores en Esclavo.procesar()

Dependencias externas
---------------------
- MicroPython >= 1.20 para ESP32 (UART.flush). Se verifica al arrancar.
- Archivos en la raiz del ESP32: main.py, config.py, perifericos.py.
- Paquete en /lib/modbus_slave/: __init__.py, crc16.py, data_model.py, frame_parser.py.
  Procedimiento de carga con Thonny: firmware/README.md.
"""

import time

from machine import Pin, UART

import config
import modbus_slave

# -----------------------------------------------------------------------------
# Verificacion de despliegue (mismo mecanismo que la T1: el despliegue es manual
# con Thonny y una version vieja de un archivo debe detectarse con un mensaje claro,
# no con un AttributeError ilegible).
# -----------------------------------------------------------------------------
_VERSION_STACK_REQUERIDA = 1
if getattr(modbus_slave, "VERSION", 0) < _VERSION_STACK_REQUERIDA:
    raise SystemExit("lib/modbus_slave desactualizado en esta placa: version {} < {}. "
                     "Volver a subir la carpeta lib/modbus_slave con Thonny.".format(
                         getattr(modbus_slave, "VERSION", 0), _VERSION_STACK_REQUERIDA))

from modbus_slave import frame_parser                 # noqa: E402
from modbus_slave.data_model import ModeloDatos       # noqa: E402
from perifericos import (EntradaAnalogica, EntradaDigital,  # noqa: E402
                         SalidaDigital, SalidaPWM)

#: Paridad de config.py -> argumento de machine.UART en el ESP32 (None, 0 = par, 1 = impar).
_PARIDAD_UART = {"N": None, "E": 0, "O": 1}


# =============================================================================
# [DF-1.1] Seleccion del perfil
# =============================================================================

def elegir_perfil():
    """
    [DF-1.1] Determina el perfil activo (dispositivo 1 o esclavo desconocido).

    Con config.PERFIL = "JUMPER" se lee GPIO13 con pull-up una sola vez, al arrancar:
    cambiar la identidad de un esclavo en caliente dejaria al maestro hablandole a un
    dispositivo que ya no existe (mismo criterio que el jumper de Unit ID de la T1).

    Parametros:
        Ninguno.
    Retorna:
        tuple[str, dict]: (nombre del perfil, perfil de config.PERFILES).
    Excepciones:
        ValueError: config.PERFIL no es "JUMPER" ni un perfil existente.
    """
    nombre = config.PERFIL
    if nombre == "JUMPER":
        jumper = Pin(config.PIN_JUMPER_PERFIL, Pin.IN, Pin.PULL_UP)
        time.sleep_ms(10)      # que el pull-up cargue la capacidad del cableado
        nombre = "DISPOSITIVO_1" if jumper.value() else "DESCONOCIDO"
    if nombre not in config.PERFILES:
        raise ValueError("perfil inexistente en config.py: {}".format(nombre))
    return nombre, config.PERFILES[nombre]


# =============================================================================
# Esclavo
# =============================================================================

class Esclavo:
    """
    El dispositivo 1: une el stack MODBus con el UART, el MAX485 y los perifericos.

    Responsabilidad:
        Ejecutar el lazo del diagrama de flujo del esclavo sin perder bytes del bus.
    Atributos principales:
        unit_id (int): direccion propia en el bus.
        modelo (ModeloDatos): las cuatro tablas, construidas desde el mapa del perfil.
        uart (machine.UART): UART2 con el baud rate y la paridad del perfil.
        de_re (machine.Pin): control de direccion del MAX485.
        ensamblador (frame_parser.EnsambladorTramas): delimitacion por silencio t3,5.
        t_car_us, t15_us, t35_us (int): tiempos calculados del baud rate (no constantes).
        contadores (dict[str, int]): tramas por motivo (frame_parser.MOTIVO_*).
    Relaciones:
        Usa modbus_slave (protocolo) y perifericos (HAL de la Tarea 1).
    """

    def __init__(self, nombre_perfil, perfil):
        """
        [DF-1.1] Inicializacion y [DF-1.2] calculo de los tiempos del enlace.

        Parametros:
            nombre_perfil (str), perfil (dict): de elegir_perfil().
        Excepciones:
            ValueError: mapa invalido (lo lanza ModeloDatos) o senal desconocida.
            SystemExit: MicroPython sin UART.flush (no se puede garantizar no truncar
                el ultimo byte al soltar DE/RE).
        """
        self.nombre_perfil = nombre_perfil
        self.unit_id = perfil["unit_id"]
        if not 1 <= self.unit_id <= 247:
            raise ValueError("Unit ID fuera de 1-247: {}".format(self.unit_id))
        self.baud = perfil["baud"]

        # El modelo valida el mapa: si esta mal escrito, el esclavo no arranca.
        self.modelo = ModeloDatos(perfil["mapa"])

        # [DF-1.2] Tiempos a partir del baud rate (formula en frame_parser.tiempos_us).
        self.t_car_us, self.t15_us, self.t35_us = frame_parser.tiempos_us(self.baud)
        self.ensamblador = frame_parser.EnsambladorTramas(
            self.t15_us, self.t35_us, config.VERIFICAR_T15, time.ticks_diff)

        # Control de direccion: arranca escuchando, para no bloquear el bus.
        self.de_re = Pin(config.PIN_DE_RE, Pin.OUT, value=0)

        self.uart = UART(config.UART_ID,
                         baudrate=self.baud, bits=8,
                         parity=_PARIDAD_UART[perfil["paridad"]],
                         stop=perfil["bits_parada"],
                         tx=config.PIN_UART_TX, rx=config.PIN_UART_RX,
                         rxbuf=config.UART_RXBUF, timeout=0)
        if not hasattr(self.uart, "flush"):
            raise SystemExit("Este MicroPython no tiene UART.flush (requiere >= 1.20): "
                             "no se puede garantizar el vaciado antes de soltar DE/RE.")

        self.perifericos = self._crear_perifericos()
        self.contadores = {
            frame_parser.MOTIVO_RESPONDIDA: 0, frame_parser.MOTIVO_EXCEPCION: 0,
            frame_parser.MOTIVO_DIFUSION: 0, frame_parser.MOTIVO_AJENA: 0,
            frame_parser.MOTIVO_CRC: 0, frame_parser.MOTIVO_INVALIDA: 0,
        }
        self.errores_internos = 0
        self._inicio_ms = time.ticks_ms()
        self._ultimo_latido_ms = self._inicio_ms

    def _crear_perifericos(self):
        """
        [DF-1.1] Crea solo los perifericos que el mapa del perfil activo usa.

        Retorna:
            dict[str, object]: senal -> objeto de perifericos.py.
        Excepciones:
            ValueError: el mapa nombra una senal que este hardware no tiene.
        """
        fabricas = {
            "pulsador": lambda: EntradaDigital(config.PIN_PULSADOR),
            "potenciometro": lambda: EntradaAnalogica(config.PIN_POTENCIOMETRO),
            "led_digital": lambda: SalidaDigital(config.PIN_LED_DIGITAL, estado_inicial=False),
            "led_pwm": lambda: SalidaPWM(config.PIN_LED_PWM),
            "uptime_s": lambda: None,          # calculada, sin hardware
        }
        creados = {}
        for senal in self.modelo.senales():
            if senal not in fabricas:
                raise ValueError("senal sin hardware asociado: {}".format(senal))
            creados[senal] = fabricas[senal]()
        return creados

    # -------------------------------------------------------------------------
    # [DF-1.3] Entradas y [DF-1.17] salidas
    # -------------------------------------------------------------------------

    def publicar_entradas(self):
        """
        [DF-1.3] Publica las entradas fisicas en las tablas de solo lectura.

        Se llama solo con el bus en reposo (ninguna trama a medio recibir): leer el
        ADC promediando 8 muestras no debe demorar la recepcion.

        Retorna:
            None
        """
        p = self.perifericos
        if "pulsador" in p:
            self.modelo.fijar_entrada("pulsador", p["pulsador"].leer())
        if "potenciometro" in p:
            # Valor CRUDO 0-4095: el escalado lo hace el borde (ADR-003).
            self.modelo.fijar_entrada("potenciometro", p["potenciometro"].leer())
        if "uptime_s" in p:
            segundos = time.ticks_diff(time.ticks_ms(), self._inicio_ms) // 1000
            self.modelo.fijar_entrada("uptime_s", segundos & 0xFFFF)

    def aplicar_salidas(self):
        """
        [DF-1.17] Lleva el coil y el holding register a los LED.

        La retencion de estado (Parte 3 de la T1) se cumple por construccion: las
        variables conservan su valor mientras nadie las escriba, y aca solo se reflejan.

        Retorna:
            None
        """
        p = self.perifericos
        if "led_digital" in p:
            p["led_digital"].escribir(bool(self.modelo.valor_de_senal("led_digital")))
        if "led_pwm" in p:
            p["led_pwm"].escribir(self.modelo.valor_de_senal("led_pwm"))

    # -------------------------------------------------------------------------
    # [DF-1.4] a [DF-1.16] Bus
    # -------------------------------------------------------------------------

    def atender_bus(self):
        """
        [DF-1.4] a [DF-1.6] Recibe bytes y detecta el fin de trama por silencio t3,5.

        Retorna:
            bool: True si hubo actividad en el bus en esta vuelta (el lazo no debe hacer
            tareas lentas), False si el bus esta en reposo.
        """
        ahora = time.ticks_us()
        disponibles = self.uart.any()                       # [DF-1.4]
        if disponibles:
            datos = self.uart.read(disponibles)
            if datos:
                cerrada = self.ensamblador.alimentar(datos, ahora)    # [DF-1.5]
                if cerrada is not None:
                    self.procesar(cerrada[0], cerrada[1])
            return True
        trama = self.ensamblador.trama_completa(ahora)      # [DF-1.6]
        if trama is not None:
            self.procesar(trama[0], trama[1])
            return True
        return self.ensamblador.en_curso()

    def procesar(self, trama, defectuosa):
        """
        [DF-1.7] a [DF-1.15] Procesa una trama completa y, si corresponde, responde.

        Parametros:
            trama (bytes), defectuosa (bool): de EnsambladorTramas.
        Retorna:
            None
        """
        respuesta, motivo = frame_parser.procesar_trama(
            trama, self.unit_id, self.modelo, defectuosa)
        self.contadores[motivo] += 1                        # [DF-1.18] a [DF-1.20]
        if respuesta is not None:
            self.transmitir(respuesta)                      # [DF-1.16]
        if motivo in (frame_parser.MOTIVO_RESPONDIDA, frame_parser.MOTIVO_DIFUSION):
            self.aplicar_salidas()      # una escritura se ve en el LED sin esperar otra vuelta
        # La traza va DESPUES de responder: imprimir antes demoraria la respuesta.
        if config.NIVEL_LOG >= 2:
            print("RX {} -> {}{}".format(_hex(trama), motivo,
                                        "" if respuesta is None else " TX " + _hex(respuesta)))

    def transmitir(self, respuesta):
        """
        [DF-1.16] Transmite la respuesta con control de DE/RE del MAX485.

        Secuencia:
          1. DE/RE = 1 y espera config.ESPERA_HABILITACION_DE_US.
          2. uart.write(): encola los bytes y vuelve enseguida.
          3. uart.flush(): bloquea hasta que el UART termino de transmitir. Soltar DE/RE
             antes cortaria el ultimo byte, que quedaria en el bus a medias: es la causa
             mas frecuente de tramas truncadas en montajes de laboratorio.
          4. Un tiempo de caracter mas de margen (la misma practica de umodbus 2.3.7,
             que la T1 valido con 0,0 % de error), y DE/RE = 0.
          5. Se descarta lo que haya entrado durante la transmision: con RE = 1 el RO
             queda en alta impedancia y el pull-up de 680 Ohm deberia evitar bytes
             espurios, pero si llegara alguno no debe mezclarse con la proxima peticion.

        Parametros:
            respuesta (bytearray): trama completa con CRC.
        Retorna:
            None
        """
        self.de_re.value(1)
        time.sleep_us(config.ESPERA_HABILITACION_DE_US)
        self.uart.write(respuesta)
        self.uart.flush()
        time.sleep_us(self.t_car_us)
        self.de_re.value(0)
        if self.uart.any():
            self.uart.read()

    # -------------------------------------------------------------------------
    # Consola
    # -------------------------------------------------------------------------

    def mostrar_arranque(self):
        """Imprime la identidad del esclavo y su mapa (solo en el arranque)."""
        print("=" * 64)
        print("ESCLAVO MODBus RTU · perfil {} · Unit ID {}".format(
            self.nombre_perfil, self.unit_id))
        print("UART{} {} bps · 8{}{} · TX GPIO{} RX GPIO{} DE/RE GPIO{}".format(
            config.UART_ID, self.baud,
            config.PERFILES[self.nombre_perfil]["paridad"],
            config.PERFILES[self.nombre_perfil]["bits_parada"],
            config.PIN_UART_TX, config.PIN_UART_RX, config.PIN_DE_RE))
        print("t_car {} us · t1,5 {} us · t3,5 {} us (calculados del baud rate)".format(
            self.t_car_us, self.t15_us, self.t35_us))
        for tabla in ("discrete_inputs", "coils", "input_registers", "holding_registers"):
            for v in self.modelo.variables(tabla):
                print("  {:<18} 0x{:04X}  {:<22} {}..{}".format(
                    tabla, v.direccion, v.nombre, v.minimo, v.maximo))
        print("=" * 64)

    def latido(self):
        """Imprime los contadores cada config.PERIODO_LATIDO_MS (con el bus en reposo)."""
        ahora = time.ticks_ms()
        if time.ticks_diff(ahora, self._ultimo_latido_ms) < config.PERIODO_LATIDO_MS:
            return
        self._ultimo_latido_ms = ahora
        c = self.contadores
        print("latido: respondidas={} excepciones={} difusion={} ajenas={} crc={} "
              "invalidas={} escrituras={} errores={}".format(
                  c["respondida"], c["excepcion"], c["difusion"], c["ajena"],
                  c["crc_error"], c["invalida"], self.modelo.escrituras,
                  self.errores_internos))

    # -------------------------------------------------------------------------
    # Lazo principal
    # -------------------------------------------------------------------------

    def ejecutar(self):
        """
        Lazo principal. No tiene esperas fijas: cualquier pausa reduce el tiempo en que el
        esclavo escucha el bus (leccion de la T1). Las tareas lentas -ADC, LED, consola-
        se hacen solo con el bus en reposo.

        Retorna:
            None: no retorna. Ctrl+C en Thonny lo interrumpe (KeyboardInterrupt no es
            Exception y no lo atrapa el except).
        """
        if config.NIVEL_LOG >= 1:
            self.mostrar_arranque()
        self.publicar_entradas()
        self.aplicar_salidas()
        while True:
            try:
                if self.atender_bus():
                    continue                    # hay trafico: seguir atendiendo el UART
                self.publicar_entradas()        # [DF-1.3]
                self.aplicar_salidas()          # [DF-1.17]
                if config.NIVEL_LOG >= 1:
                    self.latido()
            except Exception as error:
                # Un dispositivo de campo que se detiene ante un error es peor que uno
                # que lo registra y sigue: se cuenta y se informa.
                self.errores_internos += 1
                print("ERROR interno: {}".format(error))


def _hex(datos):
    """Formatea bytes como '01 04 00 00' (bytes.hex(sep) no existe en todo MicroPython)."""
    return " ".join("{:02X}".format(b) for b in datos)


def main():
    """Punto de entrada: [DF-1.1] perfil, construccion del esclavo y lazo."""
    nombre, perfil = elegir_perfil()
    Esclavo(nombre, perfil).ejecutar()


if __name__ == "__main__":
    main()
