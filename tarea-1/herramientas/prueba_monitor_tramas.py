"""
prueba_monitor_tramas.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-29
Version: 1.0

Descripcion general
-------------------
Verifica en la PC, sin hardware, firmware/monitor_tramas_maestro.py:

  1-3. El decodificador de tramas: CRC-16 contrastado con el de
       modbus_tramas.py (oraculo independiente), campos de peticiones y
       respuestas, excepciones, CRC corrupto y tramas truncadas.
  4.   La NO INTERFERENCIA: con el monitor instalado, cada transaccion devuelve
       exactamente lo mismo y relanza exactamente la misma excepcion que sin el.
  5.   El enganche completo sobre un main.py simulado: que ejecutar() llame al
       main() original, detecte el fin de cada ciclo e imprima el resumen al
       recibir Ctrl+C.

Devuelve codigo de salida 1 si algo falla, 0 si todo pasa.

Uso
---
    python tarea-1/herramientas/prueba_monitor_tramas.py

Dependencias externas
---------------------
Ninguna (Python 3 estandar).
"""

import contextlib
import importlib.util
import io
import os
import sys
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import modbus_tramas  # noqa: E402  (oraculo independiente del CRC)

_ruta = os.path.join(AQUI, "..", "firmware", "monitor_tramas_maestro.py")
_spec = importlib.util.spec_from_file_location("monitor_tramas_maestro", _ruta)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

fallos = 0


def check(cond, texto):
    """Informa una verificacion y cuenta los fallos."""
    global fallos
    print(("  OK   " if cond else "  FALLA") + "  " + texto)
    if not cond:
        fallos += 1


def con_crc(cuerpo):
    """Agrega el CRC (LSB primero) calculado por el ORACULO, no por el monitor."""
    crc = modbus_tramas.calcular_crc16(bytes(cuerpo))
    return bytes(cuerpo) + bytes([crc & 0xFF, crc >> 8])


def campo(campos, nombre):
    """Valor del primer campo con ese nombre, o cadena vacia."""
    for clave, valor in campos:
        if clave == nombre:
            return valor
    return ""


class RelojFalso:
    """Reemplaza time.ticks_* de MicroPython: avanza 500 us por consulta."""

    def __init__(self):
        self.us = 0

    def ticks_us(self):
        self.us += 500
        return self.us

    def ticks_ms(self):
        return self.us // 1000

    def ticks_diff(self, a, b):
        return a - b


class ConfigFalso:
    DIR_DISCRETE_INPUT_SWITCH = 0
    DIR_INPUT_REGISTER_POTE = 0
    DIR_COIL_LED_DIGITAL = 0
    DIR_HOLDING_REGISTER_PWM = 0


MAPA = m.construir_mapa(ConfigFalso)

# =============================================================================
print("\n1. crc16() contra el oraculo de modbus_tramas.py")
check(m.crc16(b"123456789") == 0x4B37, "vector estandar 123456789 -> 0x4B37")
for muestra in (b"\x01\x04\x00\x00\x00\x01", b"\x02\x06\x00\x00\x00\x80", b"\xff" * 7):
    check(m.crc16(muestra) == modbus_tramas.calcular_crc16(muestra),
          "coincide con el oraculo para {}".format(m.hexa(muestra)))

# =============================================================================
print("\n2. desglosar_trama(): peticiones")
pet_ir = bytes.fromhex("01 04 00 00 00 01 31 CA".replace(" ", ""))
resumen, campos, ok = m.desglosar_trama(pet_ir, True, mapa=MAPA)
check(ok, "trama de referencia del repositorio: CRC OK")
check("30001" in campo(campos, "Direccion"), "0x04 offset 0 -> Modicon 30001")
check("potenciometro" in campo(campos, "Direccion"), "nombra el registro segun config.py")
check(campo(campos, "Cantidad").endswith("= 1"), "cantidad 1")
check("en linea 31 CA (LSB primero) = 0xCA31" in campo(campos, "CRC"),
      "CRC mostrado LSB primero en linea y compuesto 0xCA31")

pet_di = con_crc(b"\x02\x02\x00\x00\x00\x01")
_, campos, ok = m.desglosar_trama(pet_di, True, mapa=MAPA)
check(ok and "10001" in campo(campos, "Direccion"), "0x02 -> Modicon 10001")

pet_co = con_crc(b"\x01\x05\x00\x00\xff\x00")
_, campos, _ = m.desglosar_trama(pet_co, True, mapa=MAPA)
check("ON" in campo(campos, "Valor")
      and "-> 00001 Coils" in campo(campos, "Direccion"), "0x05 FF00 = ON sobre coil 00001")
_, campos, _ = m.desglosar_trama(con_crc(b"\x01\x05\x00\x00\x00\x01"), True, mapa=MAPA)
check("INVALIDO" in campo(campos, "Valor"), "0x05 con valor 0x0001 se marca invalido")

pet_hr = con_crc(b"\x02\x06\x00\x00\x00\x80")
resumen, campos, _ = m.desglosar_trama(pet_hr, True, mapa=MAPA)
check("128" in campo(campos, "Valor") and "40001" in resumen, "0x06 escribe 128 en 40001")

# =============================================================================
print("\n3. desglosar_trama(): respuestas, excepciones y tramas defectuosas")
resp_di = con_crc(b"\x02\x02\x01\x01")
resumen, campos, ok = m.desglosar_trama(resp_di, False, peticion=pet_di, mapa=MAPA)
check(ok and "10001 = 1" in resumen, "0x02 respuesta: bit 0 = 1 en 10001")

resp_ir = con_crc(b"\x01\x04\x02\x0f\xff")
resumen, campos, ok = m.desglosar_trama(resp_ir, False, peticion=pet_ir, mapa=MAPA,
                                        escalar=lambda v: v >> 4)
dato = campo(campos, "Dato")
check("MSB 0F LSB FF -> 4095" in dato, "0x04 respuesta big-endian 0x0FFF = 4095")
check("PWM local 255" in dato, "anota el PWM local que produce la lectura")

_, campos, _ = m.desglosar_trama(pet_hr, False, peticion=pet_hr, mapa=MAPA)
check("confirmada" in campo(campos, "Eco"), "0x06 eco identico -> escritura confirmada")
eco_malo = con_crc(b"\x02\x06\x00\x00\x00\x81")
resumen, campos, _ = m.desglosar_trama(eco_malo, False, peticion=pet_hr, mapa=MAPA)
check("DISTINTO" in campo(campos, "Eco") and "ECO DISTINTO" in resumen, "eco distinto se detecta")

excepcion = con_crc(b"\x01\x84\x02")
resumen, campos, ok = m.desglosar_trama(excepcion, False, peticion=pet_ir, mapa=MAPA)
check(ok and "Illegal Data Address" in campo(campos, "Excepcion"), "0x84 02 = Illegal Data Address")
check("EXCEPCION" in campo(campos, "Funcion"), "bit 7 de excepcion identificado")

corrupta = bytearray(resp_ir)
corrupta[3] ^= 0x01
resumen, campos, ok = m.desglosar_trama(bytes(corrupta), False, peticion=pet_ir, mapa=MAPA)
check(not ok and "CRC ERROR" in resumen, "un bit invertido -> CRC ERROR")

resumen, campos, ok = m.desglosar_trama(b"\x00", False)
check(not ok and "truncada" in resumen, "trama de 1 byte (glitch) -> truncada, sin excepcion")

otro_id = con_crc(b"\x02\x04\x02\x00\x10")
_, campos, _ = m.desglosar_trama(otro_id, False, peticion=pet_ir, mapa=MAPA)
check("responde el ID 2" in campo(campos, "Aviso"), "respuesta de otro ID se avisa")

largo_malo = con_crc(b"\x01\x04\x02\x0f")
resumen, _, _ = m.desglosar_trama(largo_malo, False, peticion=pet_ir, mapa=MAPA)
check("LARGO" in resumen, "byte count incoherente con el largo -> mal formada")


# =============================================================================
print("\n4. No interferencia sobre un bus simulado")


class UARTFalso:
    """UART con una cola de lectura programable; registra lo escrito."""

    def __init__(self):
        self.escrito = []
        self.pendiente = None

    def write(self, datos):
        self.escrito.append(bytes(datos))
        return len(datos)

    def read(self):
        datos, self.pendiente = self.pendiente, None
        return datos

    def any(self):
        return 0

    def flush(self):
        return None


class BusFalso:
    """
    Imita umodbus.serial.Serial + MaestroRTUConTimeout: vacia el RX, transmite,
    drena la ventana de guarda con una lectura y devuelve la respuesta guionada.
    """

    def __init__(self):
        self._uart = UARTFalso()
        # Referencia al UART real: el monitor reemplaza self._uart por su proxy.
        self._fuente = self._uart
        self.respuestas = []
        self.glitch = None

    def _uart_read_frame(self, timeout=None):
        self._fuente.pendiente = self.glitch
        self._uart.read()              # drenaje de la ventana de guarda
        return self.respuestas.pop(0)

    def _transaccion(self, peticion):
        self._uart.read()              # vaciado previo del RX, como umodbus
        self._uart.write(peticion)
        respuesta = self._uart_read_frame()
        if not respuesta:
            raise OSError("no data received from slave")
        if respuesta[1] & 0x80:
            raise ValueError("slave returned exception code: {}".format(respuesta[2]))
        return respuesta

    def read_input_registers(self, slave_addr, starting_addr, register_qty, signed=True):
        r = self._transaccion(pet_ir)
        return (r[3] << 8 | r[4],)

    def write_single_register(self, slave_addr, register_address, register_value, signed=True):
        self._transaccion(pet_hr)
        return True


def correr(bus, instalar):
    """Corre tres transacciones (OK, timeout, excepcion) y devuelve lo observado."""
    salida = []
    monitor = m.MonitorBus(mapa=MAPA, reloj=RelojFalso(), imprimir=salida.append)
    if instalar:
        monitor.instrumentar(bus)
    bus.glitch = b"\x00"
    bus.respuestas = [resp_ir, b"", excepcion]
    resultados = [bus.read_input_registers(slave_addr=1, starting_addr=0,
                                           register_qty=1, signed=False)]
    for _ in range(2):
        try:
            bus.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1, signed=False)
        except Exception as error:
            resultados.append((type(error), str(error)))
    monitor.cerrar_ciclo(1)
    return resultados, bus._uart, monitor, salida


sin_monitor, uart_sin, _, _ = correr(BusFalso(), instalar=False)
con_monitor, uart_con, monitor, salida = correr(BusFalso(), instalar=True)
texto = "\n".join(salida)

check(sin_monitor == con_monitor, "mismos resultados y mismas excepciones con y sin monitor")
check(uart_con._uart.escrito == uart_sin.escrito, "mismos bytes transmitidos con y sin monitor")
check(monitor.estadistica["tx"] == 3 and monitor.estadistica["rx"] == 2,
      "cuenta 3 TX y 2 RX")
check(monitor.estadistica["timeouts"] == 1, "registra el timeout como RX vacia")
check(monitor.estadistica["excepciones"] == 1, "registra la excepcion MODBus")
check(monitor.estadistica["descartes"] == 3, "registra el byte descartado en cada guarda")
check(uart_con.read == uart_con._read_real, "read vuelve al metodo real tras la guarda")
check("SIN RESPUESTA" in texto and "DESCARTADO" in texto, "el volcado muestra timeout y descarte")
check("Illegal Data Address" in texto, "el volcado decodifica la excepcion")
check("REINTENTO" in texto, "una repeticion tras un fallo se marca como reintento")
check("potenciometro" in texto and "4095" in texto, "el volcado detalla la lectura 0x04")

# Un fallo interno del monitor no debe romper la transaccion.
bus = BusFalso()
monitor = m.MonitorBus(mapa=MAPA, reloj=RelojFalso(), imprimir=lambda *_: None)
monitor.instrumentar(bus)
monitor._reloj = None          # cualquier uso del reloj lanzara AttributeError
bus.glitch = None
bus.respuestas = [resp_ir]
try:
    valor = bus.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1, signed=False)
    check(valor == (4095,), "con el monitor roto la transaccion igual devuelve 4095")
except Exception as error:
    check(False, "el monitor roto propago {!r} a la transaccion".format(error))


# =============================================================================
print("\n5. ejecutar() sobre un main.py simulado")

ESPERA = 6


class MaestroFalso:
    """Maquina minima: LEER (0x04) -> ESCRIBIR (0x06) -> ESPERA -> LEER ..."""

    def __init__(self, bus):
        self._bus = bus
        self._estado = 0
        self._id_activo = 2
        self.pasos = 0

    def ejecutar_paso(self):
        self.pasos += 1
        if self._estado == 0:
            self._bus.read_input_registers(slave_addr=2, starting_addr=0,
                                           register_qty=1, signed=False)
            self._estado = 1
        elif self._estado == 1:
            self._bus.write_single_register(slave_addr=2, register_address=0,
                                            register_value=128, signed=False)
            self._estado = ESPERA
        else:
            self._estado = 0


firmware = types.ModuleType("main")
firmware.ESTADO_ESPERA = ESPERA
firmware.MaestroModbus = MaestroFalso
firmware.llamadas_main = 0


def _configurar():
    bus = BusFalso()
    bus.respuestas = [resp_ir, pet_hr] * 3
    return bus


def _main():
    firmware.llamadas_main += 1
    maestro = firmware.MaestroModbus(firmware.configurar_maestro_modbus())
    for _ in range(9):         # tres ciclos completos
        maestro.ejecutar_paso()
    firmware.maestro = maestro
    raise KeyboardInterrupt


firmware.configurar_maestro_modbus = _configurar
firmware.main = _main
config_falso = types.ModuleType("config")
for nombre in ("DIR_DISCRETE_INPUT_SWITCH", "DIR_INPUT_REGISTER_POTE",
               "DIR_COIL_LED_DIGITAL", "DIR_HOLDING_REGISTER_PWM"):
    setattr(config_falso, nombre, 0)
perifericos_falso = types.ModuleType("perifericos")
perifericos_falso.adc_a_pwm = lambda v: v >> 4

sys.modules.update({"main": firmware, "config": config_falso, "perifericos": perifericos_falso})
m.time = RelojFalso()          # MicroPython tiene ticks_*; CPython no

consola = io.StringIO()
with contextlib.redirect_stdout(consola):
    monitor = m.ejecutar()
texto = consola.getvalue()

check(firmware.llamadas_main == 1, "llama al main() original una sola vez")
check(monitor.ciclos == 3, "detecta el fin de los 3 ciclos")
check(texto.count("CICLO ") == 3, "imprime los 3 ciclos")
check("RESUMEN DEL MONITOR (3 ciclos observados)" in texto, "Ctrl+C imprime el resumen")
check("PWM local 255" in texto, "usa adc_a_pwm() de perifericos.py")
check("escritura confirmada" in texto, "decodifica el eco de la 0x06")
check(firmware.maestro.pasos == 9, "la maquina de estados avanza igual que sin monitor")

# =============================================================================
print("\n" + ("TODO OK" if not fallos else "{} VERIFICACION(ES) FALLARON".format(fallos)))
sys.exit(1 if fallos else 0)
