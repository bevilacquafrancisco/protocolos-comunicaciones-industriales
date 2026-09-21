# -*- coding: utf-8 -*-
"""
demo_retencion_estado.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-20
Version: 1.0

Descripcion general
-------------------
Reproduce en la PC la consola del Esclavo 2 durante la secuencia que verifica
el tercer requisito de la Parte 3: "el esclavo que no esta seleccionado
mantiene el ultimo estado recibido en sus salidas hasta recibir una nueva
orden".

Ejecuta la misma logica de deteccion de retencion que firmware/esclavo/main.py,
contra un servidor MODBus simulado, y sirve para dos cosas: comprender que
evidencia produce el firmware antes de ir al banco, y tener una referencia
contra la cual comparar la corrida real.

No reemplaza la verificacion en hardware, que es la que vale para el informe.

Uso
---
    python herramientas/demo_retencion_estado.py

Dependencias externas
---------------------
- Python 3 en la PC. Ninguna biblioteca de terceros.
"""
import sys, types, time as _t

import os
# Ruta derivada del propio archivo: funciona desde cualquier directorio.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "firmware", "comun"))

_reloj = [0]
_t.ticks_ms = lambda: _reloj[0]
_t.ticks_diff = lambda a, b: a - b
_t.sleep_ms = lambda ms: None

cfg = types.ModuleType("config")
cfg.NIVEL_LOG = 3
cfg.CAPTURA_TRAMAS = 24
sys.modules["config"] = cfg

import diagnostico as d


def crc(t):
    v = 0xFFFF
    for b in t:
        v ^= b
        for _ in range(8):
            v = (v >> 1) ^ 0xA001 if v & 1 else v >> 1
    return bytes([v & 0xFF, v >> 8])


def tr(c):
    return bytes(c) + crc(bytes(c))


LOG = d.Registrador("ESCLAVO 2")
CAP = d.CapturaTramas(24)
INST = d.InstrumentacionBus(CAP, LOG, unit_id=2, tx_es_peticion=False)

# Estado de las salidas, como lo guardaria el servidor MODBus.
registros = {"coil": 0, "hreg": 0}

# Lazo simplificado del esclavo, con la misma logica que main.py
umbral = 1500
periodo = 5000
reteniendo = False
salidas_al_retener = (None, None)
instante_resumen = 0


def paso():
    """Una vuelta del lazo del esclavo: evalua retencion y emite el latido."""
    global reteniendo, salidas_al_retener, instante_resumen
    sin_ordenes = INST.ms_sin_ordenes()
    salidas = (registros["coil"], registros["hreg"])

    if not reteniendo and sin_ordenes >= umbral:
        reteniendo = True
        salidas_al_retener = salidas
        LOG.aviso("RETENCION: sin ordenes hace {} ms. Salidas mantenidas en "
                  "LED={} PWM={}".format(sin_ordenes, salidas[0], salidas[1]))
    elif reteniendo and sin_ordenes < umbral:
        reteniendo = False
        intactas = salidas == salidas_al_retener
        LOG.aviso("FIN DE RETENCION: llego una orden. Salidas durante la pausa: "
                  "{} (LED={} PWM={})".format(
                      "SIN CAMBIOS" if intactas else "MODIFICADAS, revisar",
                      salidas_al_retener[0], salidas_al_retener[1]))

    if _t.ticks_diff(_t.ticks_ms(), instante_resumen) >= periodo:
        instante_resumen = _t.ticks_ms()
        LOG.info("latido: tramas={} propias={} ajenas={} errores=0 | DI=0 IR=2047".format(
            INST.tramas_recibidas, INST.tramas_propias,
            INST.tramas_recibidas - INST.tramas_propias))
        LOG.continuacion(d.INFO, "salidas: LED={} PWM={} | {} ordenes, ultima hace {} ms{}"
                         .format(salidas[0], salidas[1], INST.ordenes_escritura,
                                 sin_ordenes, "  <- RETENIENDO" if reteniendo else ""))


def recibir(trama, escribe=None):
    """Simula la llegada de una trama y, si es una escritura, su efecto."""
    INST._registrar_recepcion(trama)
    if escribe:
        registros.update(escribe)


def avanzar(ms, paso_ms=250):
    for _ in range(ms // paso_ms):
        _reloj[0] += paso_ms
        paso()


print("=" * 88)
print("CONSOLA DEL ESCLAVO 2")
print("=" * 88)
print()
print(">>> El maestro esta sondeando al Esclavo 2. Se le ordena LED=1 y PWM=200.")
for ciclo in range(6):
    recibir(tr([0x02, 0x02, 0x00, 0x00, 0x00, 0x01]))
    recibir(tr([0x02, 0x04, 0x00, 0x00, 0x00, 0x01]))
    recibir(tr([0x02, 0x05, 0x00, 0x00, 0xFF, 0x00]), {"coil": 1})
    recibir(tr([0x02, 0x06, 0x00, 0x00, 0x00, 0xC8]), {"hreg": 200})
    avanzar(200, 200)

print()
print(">>> Se conmuta el selector al Esclavo 1. El Esclavo 2 deja de ser sondeado,")
print(">>> pero sigue oyendo el trafico ajeno del bus.")
for ciclo in range(75):
    recibir(tr([0x01, 0x02, 0x00, 0x00, 0x00, 0x01]))
    recibir(tr([0x01, 0x06, 0x00, 0x00, 0x00, 0x40]))
    avanzar(200, 200)

print()
print(">>> Se vuelve a conmutar el selector al Esclavo 2.")
recibir(tr([0x02, 0x02, 0x00, 0x00, 0x00, 0x01]))
recibir(tr([0x02, 0x05, 0x00, 0x00, 0xFF, 0x00]), {"coil": 1})
avanzar(400, 200)

print()
print("=" * 88)
print("Salidas al final: LED={} PWM={}  (las mismas que antes de la pausa)".format(
    registros["coil"], registros["hreg"]))
print("=" * 88)
