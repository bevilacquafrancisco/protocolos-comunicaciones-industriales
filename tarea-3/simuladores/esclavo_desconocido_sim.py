#!/usr/bin/env python3
"""
esclavo_desconocido_sim.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
"Esclavo desconocido" para ensayar el invariante I-04 (ADR-007): otro Unit ID, otro baud
rate, otra paridad y otro mapa de registros que el dispositivo 1. Es el MISMO simulador
(esclavo_modbus_sim.py) arrancado con el perfil DESCONOCIDO del firmware
(firmware/esclavo-modbus/src/config.py): hoy, Unit ID 17, 19200 bps, paridad par, mapa en
las direcciones 0x0010 / 0x0020 / 0x0100 / 0x0200.

Para un ensayo a ciegas, quien lo prepara cambia el perfil DESCONOCIDO en config.py (o usa
--id/--baud/--paridad) y no se lo dice a quien opera el maestro.

Uso
---
    python tarea-3/simuladores/esclavo_desconocido_sim.py --tcp 127.0.0.1:5020
    python tarea-3/simuladores/esclavo_desconocido_sim.py --tcp 127.0.0.1:5020 --id 93 --baud 38400 --paridad odd

Dependencias externas: las de esclavo_modbus_sim.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import esclavo_modbus_sim  # noqa: E402

if __name__ == "__main__":
    esclavo_modbus_sim.main(perfil_por_defecto="DESCONOCIDO")
