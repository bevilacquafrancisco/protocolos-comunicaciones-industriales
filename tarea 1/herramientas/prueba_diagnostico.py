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

print("\n2. describir_trama()")
check(d.describir_trama(b'\x01\x04\x00\x00\x00\x01\x31\xCA')
      == "ID=1 FC=0x04 dir=0x0000 cant=1", "peticion de lectura")
check(d.describir_trama(b'\x02\x06\x00\x00\x00\x80\x00\x00')
      == "ID=2 FC=0x06 dir=0x0000 valor=0x0080 (128)", "escritura de registro")
check("EXCEPCION" in d.describir_trama(b'\x01\x84\x02\x00\x00'), "respuesta de excepcion")
check("direccion invalida" in d.describir_trama(b'\x01\x84\x02\x00\x00'), "codigo 02 traducido")
check(d.describir_trama(None) == "sin trama", "ausencia de trama")

print("\n3. clasificar_error()")
check(d.clasificar_error(Exception("Modbus timeout")) == "TIMEOUT", "timeout")
check(d.clasificar_error(Exception("Slave returned exception 2")) == "EXCEPCION", "excepcion")
check(d.clasificar_error(Exception("CRC mismatch")) == "TRAMA", "crc")

print("\n4. DetectorDeCambio()")
det = d.DetectorDeCambio()
check((det.cambio(1), det.cambio(1), det.cambio(0), det.cambio(0))
      == (True, False, True, False), "solo transiciones")
check(det.transiciones == 2, "cuenta de transiciones (primera observacion + un cambio)")
det2 = d.DetectorDeCambio(umbral=2)
det2.cambio(100)
check(det2.cambio(101) is False, "variacion dentro de la zona muerta ignorada")
check(det2.cambio(104) is True, "variacion fuera de la zona muerta aceptada")

print("\n5. EntradaConfirmada()  (pin simulado)")
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

print("\n6. EstadisticaEsclavo()")
est = d.EstadisticaEsclavo()
for c in [None, None, "TIMEOUT", "TIMEOUT", None, "EXCEPCION"]:
    est.registrar(c)
check(est.intentos == 6 and est.exitos == 3, "intentos y exitos")
check(est.timeouts == 2 and est.excepciones == 1, "desglose por clase")
check(est.peor_racha == 2, "peor racha de fallos consecutivos")
check("50.0%" in est.resumen(), "tasa de error en el resumen: " + est.resumen())

print("\n7. Registrador()")
log = d.Registrador("PRUEBA", nivel=d.INFO)
check(log.habilitado(d.INFO) and not log.habilitado(d.DETALLE), "filtrado por nivel")
log.info("esta linea debe verse")
log.detalle("esta NO debe verse")
log.fijar_nivel(d.TRAMA)
log.trama("RX", b'\x01\x04\x00\x00\x00\x01\x31\xCA')

print("\n" + "="*60)
print("FALLAS: {}".format(fallos))
sys.exit(1 if fallos else 0)
