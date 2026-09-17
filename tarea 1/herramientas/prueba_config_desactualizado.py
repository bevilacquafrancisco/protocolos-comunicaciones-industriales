# -*- coding: utf-8 -*-
"""
prueba_config_desactualizado.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-17
Version: 1.0

Descripcion general
-------------------
Reproduce en la PC un fallo de despliegue concreto: subir diagnostico.py a una
placa y olvidar el config.py actualizado. Verifica que el nodo arranque con
valores por defecto y un aviso claro, en lugar de abortar con AttributeError.

Es una prueba de la estrategia de tolerancia a configuracion incompleta, no de
la logica del protocolo.

Uso
---
    python herramientas/prueba_config_desactualizado.py

Dependencias externas
---------------------
- Python 3 en la PC. Ninguna biblioteca de terceros.
"""
import sys, os, types, time as _t

# Ruta derivada del propio archivo: funciona desde cualquier directorio.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "firmware", "comun"))

_t.ticks_ms = lambda: int(_t.monotonic() * 1000)
_t.ticks_diff = lambda a, b: a - b
_t.sleep_ms = lambda ms: None

# config.py "viejo": solo las constantes que existian antes de esta version
viejo = types.ModuleType("config")
viejo.BAUDRATE = 9600
viejo.PERIODO_SONDEO_MS = 200
sys.modules["config"] = viejo

import diagnostico as d

print("--- verificar_config() ---")
ausentes = d.verificar_config()
print("ausentes ->", ausentes)

print("\n--- construccion con config viejo ---")
log = d.Registrador("MAESTRO")
log.info("el nodo arranco igual, con el nivel por defecto")

class PinFalso:
    def value(self): return 1
e = d.EntradaConfirmada(PinFalso())
print("EntradaConfirmada leyo:", e.leer())

print("\nRESULTADO: el nodo arranca y avisa, en lugar de abortar.")
