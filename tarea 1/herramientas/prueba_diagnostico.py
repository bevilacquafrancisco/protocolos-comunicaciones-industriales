# -*- coding: utf-8 -*-
"""
prueba_diagnostico.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-17
Version: 1.0

Descripcion general
-------------------
Banco de pruebas de firmware/comun/diagnostico.py. Se ejecuta en la PC y no en
el ESP32: las clases del modulo son logica pura y pueden verificarse sin
hardware, lo que permite corregirlas antes de subirlas a tres placas.

La API de tiempo de MicroPython (ticks_ms, ticks_diff, sleep_ms) no existe en
CPython y se emula al inicio. Es la misma tecnica que se emplearia para probar
firmware embebido en un servidor de integracion continua.

Uso
---
    python herramientas/prueba_diagnostico.py

Devuelve codigo de salida 0 si todas las verificaciones pasan y 1 en caso
contrario, de modo que pueda encadenarse en un script.

Dependencias externas
---------------------
- Python 3 en la PC. Ninguna biblioteca de terceros.
"""
import sys, os, time as _t

# Ruta derivada del propio archivo: el banco funciona desde cualquier
# directorio de trabajo y no depende de donde este clonado el repositorio.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "firmware", "comun"))

# Emulacion de la API de tiempo de MicroPython
_t.ticks_ms = lambda: int(_t.monotonic() * 1000)
_t.ticks_diff = lambda a, b: a - b
_t.ticks_add = lambda a, b: a + b
_t.sleep_ms = lambda ms: _t.sleep(ms / 1000.0)
_t.sleep_us = lambda us: None

import diagnostico as d

fallos = 0
def check(cond, texto):
    global fallos
    print(("  OK   " if cond else "  FALLA") + "  " + texto)
    if not cond: fallos += 1

print("\n1. hexa()")
check(d.hexa(b'\x01\x04\x00\x00') == "01 04 00 00", "formato con separadores")

print("\n2. nombre_funcion()")
check(d.nombre_funcion(0x04) == "Read Input Registers", "codigo conocido")
check(d.nombre_funcion(0x84) == "Read Input Registers", "ignora el bit de excepcion")
check("0x63" in d.nombre_funcion(0x63), "codigo desconocido se reporta tal cual")

print("\n3. describir_trama()")
peticion = b'\x01\x04\x00\x00\x00\x01\x31\xCA'
check(d.describir_trama(peticion, True)
      == "E1 FC=0x04 Read Input Registers  dir=0x0000 n=1", "peticion de lectura")
check(d.describir_trama(b'\x01\x04\x02\x08\x00\xBE\xF0', False).endswith("-> 2048"),
      "respuesta de lectura, valor recompuesto big-endian")
check(d.describir_trama(b'\x01\x02\x01\x00\xA1\x88', False).endswith("bits=0b00000000"),
      "respuesta de lectura de bits")
check("(ON)" in d.describir_trama(b'\x01\x05\x00\x00\xFF\x00\x8C\x3A'),
      "0xFF00 se traduce a ON, no a 65280")
check("(OFF)" in d.describir_trama(b'\x01\x05\x00\x00\x00\x00\x00\x00'),
      "0x0000 se traduce a OFF")
check(d.describir_trama(b'\x02\x06\x00\x00\x00\x80\x00\x00')
      == "E2 FC=0x06 Write Single Register  dir=0x0000 valor=128", "escritura de registro")
check("EXCEPCION" in d.describir_trama(b'\x01\x84\x02\x00\x00'), "respuesta de excepcion")
check("direccion invalida" in d.describir_trama(b'\x01\x84\x02\x00\x00'), "codigo 02 traducido")
check("Read Input Registers" in d.describir_trama(b'\x01\x84\x02\x00\x00'),
      "la excepcion nombra la funcion original")
check(d.describir_trama(None) == "sin trama", "ausencia de trama")

# La ambiguedad que resuelve es_peticion: la MISMA trama de 8 bytes se
# interpreta distinto segun el sentido, y sin el dato hay que adivinar.
eco = b'\x01\x03\x02\x00\x7F\xF8\x44'
check(d.describir_trama(eco, False).endswith("-> 127"),
      "con sentido conocido, la respuesta se lee bien")

print("\n4. clasificar_error()")
check(d.clasificar_error(Exception("Modbus timeout")) == "TIMEOUT", "timeout")
check(d.clasificar_error(Exception("Slave returned exception 2")) == "EXCEPCION", "excepcion")
check(d.clasificar_error(Exception("CRC mismatch")) == "TRAMA", "crc")

print("\n5. DetectorDeCambio()")
det = d.DetectorDeCambio()
check((det.cambio(1), det.cambio(1), det.cambio(0), det.cambio(0))
      == (True, False, True, False), "solo transiciones")
check(det.transiciones == 2, "cuenta de transiciones (primera observacion + un cambio)")
det2 = d.DetectorDeCambio(umbral=2)
det2.cambio(100)
check(det2.cambio(101) is False, "variacion dentro de la zona muerta ignorada")
check(det2.cambio(104) is True, "variacion fuera de la zona muerta aceptada")

print("\n6. EntradaConfirmada()  (pin simulado)")
class PinFalso:
    def __init__(self, secuencia): self.s = list(secuencia); self.i = 0
    def value(self):
        v = self.s[min(self.i, len(self.s)-1)]; self.i += 1; return v

# Arranca en 1 y recibe un unico glitch a 0: no debe aceptarlo.
e = d.EntradaConfirmada(PinFalso([1, 1, 0, 1, 1, 1, 1]), confirmaciones=3)
e.leer()
check(e.leer() == 1, "glitch aislado rechazado")
check(e.rechazos >= 1, "el glitch quedo contabilizado como rechazo")

# Cambio sostenido a 0: debe aceptarlo.
e2 = d.EntradaConfirmada(PinFalso([1] + [0]*12), confirmaciones=3)
e2.leer(); e2.leer()
check(e2.leer() == 0, "cambio sostenido aceptado")

print("\n7. porcentaje()")
check(d.porcentaje(239, 2046) == "11.6%", "un decimal, con aritmetica entera")
check(d.porcentaje(0, 100) == "0.0%", "cero observado es 0.0%")
check(d.porcentaje(0, 0) == "-", "sin observaciones no es cero, es indefinido")

print("\n8. EstadisticaEsclavo() — acumulado")
est = d.EstadisticaEsclavo()
for c in [None, None, "TIMEOUT", "TIMEOUT", None, "EXCEPCION"]:
    est.registrar(c)
check(est.intentos == 6 and est.exitos == 3, "intentos y exitos")
check(est.timeouts == 2 and est.excepciones == 1, "desglose por clase")
check(est.peor_racha == 2, "peor racha de fallos consecutivos")
check("50.0%" in est.resumen(), "tasa de error en el resumen: " + est.resumen())
check("2to" in est.resumen() and "1ex" in est.resumen(), "clases no nulas en el resumen")
check("tr" not in est.resumen(), "las clases en cero no se imprimen")

sano = d.EstadisticaEsclavo()
for _ in range(10):
    sano.registrar(None)
check(sano.resumen() == "10tx 0err (0.0%)", "un nodo sano da una linea corta y limpia")

print("\n9. EstadisticaEsclavo() — ventana movil")
# Escenario real del banco: un esclavo que fallo mucho al principio y desde
# entonces funciona bien. El acumulado debe seguir alarmante y la ventana limpia.
v = d.EstadisticaEsclavo()
for _ in range(100):
    v.registrar("TIMEOUT")
for _ in range(900):
    v.registrar(None)
v.cerrar_ventana()
for _ in range(50):
    v.registrar(None)
check("9.5%" in v.resumen(), "el acumulado conserva el historial: " + v.resumen())
check(v.resumen_ventana() == "50tx 0err (0.0%)",
      "la ventana describe el presente: " + v.resumen_ventana())

# Un esclavo no seleccionado no debe confundirse con uno sano.
pausado = d.EstadisticaEsclavo()
for _ in range(20):
    pausado.registrar(None)
pausado.cerrar_ventana()
check(pausado.resumen_ventana() == "sin sondeo",
      "sin sondeo se distingue de cero errores")
check(pausado.intentos == 20, "cerrar_ventana no toca el acumulado")

v.reiniciar()
check(v.intentos == 0 and v.v_intentos == 0 and v.peor_racha == 0,
      "reiniciar() pone a cero acumulado y ventana")

print("\n10. Registrador()")

log = d.Registrador("PRUEBA", nivel=d.INFO)
check(log.habilitado(d.INFO) and not log.habilitado(d.DETALLE), "filtrado por nivel")
log.info("esta linea debe verse")
log.detalle("esta NO debe verse")
log.fijar_nivel(d.TRAMA)
log.trama("RX", b'\x01\x04\x00\x00\x00\x01\x31\xCA')
log.info("linea principal del reporte")
log.continuacion(d.INFO, "-> linea subordinada, sangrada y sin encabezado")


print("\n11. CapturaTramas()")
cap = d.CapturaTramas(capacidad=3)
cap.registrar("TX", b'\x01\x04\x00\x00\x00\x01\x31\xCA', True)
cap.registrar("RX", b'\x01\x04\x02\x08\x00\xBE\xF0', False)
check(cap.total == 2, "cuenta las tramas registradas")

cap.registrar("TX", b'\x02\x04\x00\x00\x00\x01\x31\xF9', True)
cap.registrar("TX", b'\x02\x03\x00\x00\x00\x01\x84\x39', True)
check(cap.total == 4, "el total cuenta tambien las descartadas")
check(len(cap._tramas) == 3, "el buffer circular respeta la capacidad")

cap.registrar("TX", None, True)
check(cap.total == 4, "una trama vacia no se registra")

apagada = d.CapturaTramas(capacidad=0)
apagada.registrar("TX", b'\x01\x02\x03\x04', True)
check(apagada.total == 0, "capacidad 0 desactiva la captura por completo")

# La copia es obligatoria: la libreria reutiliza sus buffers.
buffer_reutilizado = bytearray(b'\x01\x04\x00\x00\x00\x01\x31\xCA')
cap2 = d.CapturaTramas(capacidad=4)
cap2.registrar("TX", buffer_reutilizado, True)
buffer_reutilizado[0] = 0xFF
check(cap2._tramas[0][2][0] == 0x01, "la trama se copia, no se referencia")

print()
log2 = d.Registrador("VOLCADO", nivel=d.INFO)
cap.volcar(log2, "EJEMPLO DE VOLCADO")
check(len(cap._tramas) == 0, "volcar() limpia el buffer por defecto")

print("\n12. UARTObservado()")
class UARTFalso:
    def __init__(self): self.escrito = []; self.marca = "real"
    def write(self, d): self.escrito.append(bytes(d)); return len(d)
    def any(self): return 7

real = UARTFalso()
cap3 = d.CapturaTramas(capacidad=4)
proxy = d.UARTObservado(real, cap3, es_peticion=True)
proxy.write(b'\x01\x04\x00\x00\x00\x01\x31\xCA')
check(len(real.escrito) == 1, "la escritura llega al UART real")
check(cap3.total == 1, "y queda registrada en la captura")
check(proxy.any() == 7, "los demas metodos se delegan")
check(proxy.marca == "real", "los atributos se delegan")


print("\n13. localizar_interfaz() e InstrumentacionBus()")

# Dobles de las DOS formas en que la libreria organiza sus clases. Esta es la
# distincion que costo un fallo en banco: el maestro hereda de la interfaz serie
# y el esclavo la contiene, de modo que instrumentar por herencia funciona en un
# nodo y falla en silencio en el otro.
class UARTDoble:
    def __init__(self): self.escrito = []
    def write(self, d): self.escrito.append(bytes(d)); return len(d)

class SerialDoble:
    """Como la clase Serial de la libreria: TIENE el UART. La extiende el maestro."""
    def __init__(self):
        self._uart = UARTDoble()
        self._proximas = []
    def _uart_read_frame(self, timeout=None):
        return self._proximas.pop(0) if self._proximas else b''

class ModbusRTUDoble:
    """Como la clase ModbusRTU: CONTIENE una Serial. La usa el esclavo."""
    def __init__(self):
        self._itf = SerialDoble()

directo = SerialDoble()
interfaz, donde = d.localizar_interfaz(directo)
check(interfaz is directo, "herencia: la interfaz es el objeto mismo ({})".format(donde))

contenedor = ModbusRTUDoble()
interfaz, donde = d.localizar_interfaz(contenedor)
check(interfaz is contenedor._itf,
      "composicion: la interfaz es el objeto contenido ({})".format(donde))

class SinUART:
    pass
interfaz, motivo = d.localizar_interfaz(SinUART())
check(interfaz is None, "sin UART localizable devuelve None, no una excepcion")

# --- Instrumentacion sobre la forma COMPUESTA, que es la que fallaba ---------
log3 = d.Registrador("PRUEBA", nivel=d.ERROR)   # silenciosa salvo errores
cap4 = d.CapturaTramas(capacidad=8)
inst = d.InstrumentacionBus(cap4, log3, unit_id=2, tx_es_peticion=False)
cliente = ModbusRTUDoble()
check(inst.aplicar(cliente) is True, "instrumenta un objeto por composicion")

# Transmision: el envoltorio debe estar puesto sobre el UART contenido.
cliente._itf._uart.write(b'\x02\x03\x02\x00\x7F\xBD\xA4')
check(cap4.total == 1, "la transmision del objeto contenido queda capturada")

# Recepcion: trama propia y trama ajena.
cliente._itf._proximas = [
    b'\x02\x03\x00\x00\x00\x01\x84\x39',   # dirigida a este esclavo
    b'\x01\x04\x00\x00\x00\x01\x31\xCA',   # dirigida al otro
]
cliente._itf._uart_read_frame()
cliente._itf._uart_read_frame()
check(inst.tramas_recibidas == 2, "cuenta todas las tramas recibidas")
check(inst.tramas_propias == 1, "distingue las propias de las ajenas")
check(cap4.total == 3, "las tres tramas quedaron capturadas")

# El metodo original debe seguir devolviendo su valor: instrumentar no altera
# el protocolo, solo lo observa.
cliente._itf._proximas = [b'\x02\x06\x00\x00\x00\x40\x09\xD2']
check(cliente._itf._uart_read_frame()[1] == 0x06,
      "el envoltorio devuelve la trama sin modificarla")

# --- Degradacion cuando no se puede instrumentar ----------------------------
inst2 = d.InstrumentacionBus(cap4, d.Registrador("PRUEBA", nivel=d.SILENCIO), unit_id=1)
check(inst2.aplicar(SinUART()) is False, "no instrumentable devuelve False")
check(inst2.activa is False, "y queda marcada como inactiva, sin lanzar excepcion")


print("\n14. Retencion de estado: ordenes de escritura (Parte 3, requisito 3)")
cap5 = d.CapturaTramas(capacidad=16)
inst3 = d.InstrumentacionBus(cap5, d.Registrador("PRUEBA", nivel=d.SILENCIO),
                             unit_id=2, tx_es_peticion=False)

def rx(inst, trama):
    inst._registrar_recepcion(trama)

# Las LECTURAS no son ordenes: no pueden modificar una salida.
rx(inst3, b'\x02\x02\x00\x00\x00\x01\xF9\xF9')   # FC02 a este nodo
rx(inst3, b'\x02\x04\x00\x00\x00\x01\x71\xF9')   # FC04 a este nodo
check(inst3.tramas_propias == 2, "las lecturas propias se cuentan como tramas")
check(inst3.ordenes_escritura == 0, "pero NO como ordenes de escritura")

# Las ESCRITURAS si lo son.
rx(inst3, b'\x02\x05\x00\x00\xFF\x00\x8C\x09')   # FC05
rx(inst3, b'\x02\x06\x00\x00\x00\xC8\x09\xF6')   # FC06
check(inst3.ordenes_escritura == 2, "FC05 y FC06 cuentan como ordenes")

# Una escritura dirigida al OTRO esclavo no es una orden para este nodo. Es el
# caso central del requisito: el maestro esta ordenandole al otro, y este debe
# mantener su estado.
antes = inst3.ordenes_escritura
rx(inst3, b'\x01\x06\x00\x00\x00\x40\x89\xD2')   # FC06 al Esclavo 1
check(inst3.ordenes_escritura == antes,
      "una escritura al otro esclavo no cuenta como orden propia")
check(inst3.tramas_recibidas - inst3.tramas_propias == 1,
      "pero si se contabiliza como trafico ajeno")

check(inst3.ms_sin_ordenes() >= 0, "ms_sin_ordenes() devuelve un intervalo valido")

print("\n" + "="*60)
print("FALLAS: {}".format(fallos))
sys.exit(1 if fallos else 0)
