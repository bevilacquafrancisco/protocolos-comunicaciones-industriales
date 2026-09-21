# -*- coding: utf-8 -*-
"""
prueba_version_despliegue.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-17
Version: 1.1

Descripcion general
-------------------
Verifica el mecanismo que detecta un despliegue incompleto sobre las placas.

El despliegue de este proyecto es manual y sobre tres ESP32: se copian cinco
archivos a cada uno desde Thonny, y olvidar uno es un error frecuente. Cada
firmware declara la version de diagnostico.py que necesita y la comprueba antes
de importar nombres concretos, de modo que una placa desactualizada se detenga
con un mensaje accionable en lugar de un ImportError.

Esta prueba comprueba tres cosas:

  1. Que el bloque de comprobacion detiene el arranque ante un modulo viejo, y
     lo deja pasar cuando esta al dia.
  2. Que la version que declara diagnostico.py alcanza la que exigen los dos
     firmwares. El numero NO se escribe aqui: se LEE de los propios firmwares,
     para que la prueba no quede obsoleta al subir la version, que es
     exactamente lo que le paso a su primera redaccion.
  3. Que maestro y esclavo exigen la misma version, porque comparten el modulo.

Uso
---
    python herramientas/prueba_version_despliegue.py

Dependencias externas
---------------------
- Python 3 en la PC. Ninguna biblioteca de terceros.
"""

import os
import re
import sys
import types
import time as _t

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE = os.path.join(_RAIZ, "firmware")

fallos = 0


def check(condicion, texto):
    """Informa una verificacion y acumula los fallos."""
    global fallos
    print(("  OK   " if condicion else "  FALLA") + "  " + texto)
    if not condicion:
        fallos += 1


def version_requerida(ruta):
    """
    Lee _VERSION_DIAGNOSTICO_REQUERIDA de un firmware, sin importarlo.

    Se usa una expresion regular y no un import porque estos archivos dependen
    de modulos que solo existen en el ESP32 (machine, umodbus).

    Parametros
    ----------
    ruta : str
        Ruta del main.py a inspeccionar.

    Retorna
    -------
    int | None
        La version exigida, o None si el firmware no declara ninguna.
    """
    texto = io.open(ruta, encoding="utf-8").read() if False else open(
        ruta, encoding="utf-8").read()
    encontrado = re.search(r"_VERSION_DIAGNOSTICO_REQUERIDA\s*=\s*(\d+)", texto)
    return int(encontrado.group(1)) if encontrado else None


def simular_arranque(version_en_placa, requerida):
    """
    Ejecuta el mismo bloque de comprobacion que llevan los firmwares.

    Parametros
    ----------
    version_en_placa : int | None
        Version del diagnostico.py instalado, o None si es tan viejo que no
        declara ninguna.
    requerida : int
        Version que exige el firmware.

    Retorna
    -------
    str
        "DETENIDO" o "ARRANCA".
    """
    diagnostico = types.SimpleNamespace()
    if version_en_placa is not None:
        diagnostico.VERSION = version_en_placa

    if getattr(diagnostico, "VERSION", 0) < requerida:
        print("  " + "-" * 62)
        print("  ERROR DE DESPLIEGUE")
        print("  diagnostico.py en esta placa es de una version anterior.")
        print("    version en la placa : {}".format(getattr(diagnostico, "VERSION", 0)))
        print("    version requerida   : {}".format(requerida))
        print("  Subir firmware/comun/diagnostico.py y reiniciar con Ctrl+D.")
        print("  " + "-" * 62)
        return "DETENIDO"
    return "ARRANCA"


# =============================================================================
# 1. Version exigida por cada firmware
# =============================================================================
print("\n1. Version exigida por los firmwares")
maestro = version_requerida(os.path.join(_FIRMWARE, "maestro", "main.py"))
esclavo = version_requerida(os.path.join(_FIRMWARE, "esclavo", "main.py"))
print("     maestro exige v{}   esclavo exige v{}".format(maestro, esclavo))
check(maestro is not None, "el maestro declara una version requerida")
check(esclavo is not None, "el esclavo declara una version requerida")
check(maestro == esclavo, "ambos firmwares exigen la misma version")

requerida = maestro or esclavo or 1

# =============================================================================
# 2. El bloque de comprobacion se comporta como corresponde
# =============================================================================
print("\n2. Comportamiento ante una placa desactualizada")
check(simular_arranque(None, requerida) == "DETENIDO",
      "modulo tan viejo que no declara VERSION: detiene")
check(simular_arranque(requerida - 1, requerida) == "DETENIDO",
      "modulo una version por detras: detiene")
check(simular_arranque(requerida, requerida) == "ARRANCA",
      "modulo al dia: arranca")
check(simular_arranque(requerida + 1, requerida) == "ARRANCA",
      "modulo mas nuevo que lo exigido: arranca")

# =============================================================================
# 3. El modulo real satisface lo que exigen los firmwares
# =============================================================================
print("\n3. El diagnostico.py del repositorio")
_t.ticks_ms = lambda: 0
_t.ticks_diff = lambda a, b: a - b
_t.sleep_ms = lambda ms: None
cfg = types.ModuleType("config")
cfg.NIVEL_LOG = 3
sys.modules["config"] = cfg
sys.path.insert(0, os.path.join(_FIRMWARE, "comun"))
import diagnostico as real

print("     diagnostico.py declara v{}".format(getattr(real, "VERSION", 0)))
check(getattr(real, "VERSION", 0) >= requerida,
      "la version del modulo alcanza la que exigen los firmwares")

for nombre in ("Registrador", "CapturaTramas", "UARTObservado",
               "InstrumentacionBus", "localizar_interfaz", "EstadisticaEsclavo"):
    check(hasattr(real, nombre), "expone {}".format(nombre))

print("\n" + "=" * 60)
print("FALLAS: {}".format(fallos))
sys.exit(1 if fallos else 0)
