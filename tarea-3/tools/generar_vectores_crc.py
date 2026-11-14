#!/usr/bin/env python3
"""
generar_vectores_crc.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Genera tests/fixtures/crc_vectors.json: los vectores "golden" del CRC-16/MODBUS que
deben pasar TODAS las implementaciones del trabajo (el esclavo en MicroPython y el
maestro en JavaScript de Node-RED). Plan de pruebas N1.1.

Los vectores NO los calcula el codigo bajo prueba. Se usan dos oraculos
independientes de el, y el script aborta si discrepan en un solo vector:

  1. pymodbus 3.8.6, FramerRTU.compute_CRC  -> oraculo externo (biblioteca de terceros).
     Se usa SOLO como oraculo: nunca forma parte del firmware ni del maestro (I-01).
  2. tarea-1/herramientas/modbus_tramas.py, calcular_crc16 -> implementacion de la T1,
     verificada contra el vector estandar "123456789" -> 0x4B37.

Detalle que los vectores fijan a proposito: pymodbus devuelve el CRC con los bytes
INVERTIDOS (compute_CRC(b"123456789") = 0x374B), es decir, en el orden en que viaja
por el cable leido como big-endian. El valor del registro CRC es 0x4B37 y en la trama
viaja primero el byte bajo: 37 4B. El JSON guarda los dos datos por separado para
que una implementacion que confunda el orden falle de forma visible.

Dependencias externas
---------------------
pymodbus==3.8.6 (ver tools/requirements-dev.txt). Solo para regenerar los vectores;
las pruebas no lo necesitan.

Uso
---
    pip install -r tarea-3/tools/requirements-dev.txt
    python tarea-3/tools/generar_vectores_crc.py

Retorna codigo 1 si los dos oraculos discrepan.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymodbus import __version__ as VERSION_PYMODBUS
from pymodbus.framer.rtu import FramerRTU

RAIZ_T3 = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_T3.parent
SALIDA = RAIZ_T3 / "tests" / "fixtures" / "crc_vectors.json"

sys.path.insert(0, str(RAIZ_REPO / "tarea-1" / "herramientas"))
from modbus_tramas import calcular_crc16 as crc_t1  # noqa: E402  (segundo oraculo)


def crc_pymodbus(datos):
    """
    CRC segun pymodbus, convertido al VALOR del registro CRC.

    Parametros:
        datos (bytes): mensaje sin CRC.
    Retorna:
        int: valor del CRC (0x0000-0xFFFF), no el orden de transmision.
    """
    invertido = FramerRTU.compute_CRC(bytes(datos))
    return ((invertido & 0xFF) << 8) | (invertido >> 8)


def h(texto):
    """Convierte '01 04 00 00' en bytes."""
    return bytes.fromhex(texto.replace(" ", ""))


def hexa(datos):
    """Convierte bytes en '01 04 00 00' (mayusculas, separado por espacios)."""
    return " ".join("{:02X}".format(b) for b in datos)


# =============================================================================
# Casos (plan de pruebas N1.1)
# =============================================================================
# Cada tupla: (nombre, descripcion, mensaje SIN CRC)
TRAMA_MAXIMA = bytes([0x01, 0x03, 0xFA]) + bytes((i * 37 + 11) % 256 for i in range(251))

CASOS = [
    ("vector_estandar", "Cadena ASCII '123456789': vector de referencia del CRC-16/MODBUS",
     b"123456789"),
    # --- Peticiones y respuestas tipicas del mapa del dispositivo 1 ---------
    ("fc01_peticion", "Read Coils, ID 1, offset 0, 1 coil", h("01 01 00 00 00 01")),
    ("fc01_respuesta", "Read Coils: 1 byte de datos, bit 0 = 1", h("01 01 01 01")),
    ("fc02_peticion", "Read Discrete Inputs, ID 1, offset 0, 1 entrada", h("01 02 00 00 00 01")),
    ("fc02_respuesta", "Read Discrete Inputs: pulsador presionado", h("01 02 01 01")),
    ("fc03_peticion", "Read Holding Registers, ID 1, offset 0, 1 registro", h("01 03 00 00 00 01")),
    ("fc03_respuesta", "Read Holding Registers: LED PWM = 128", h("01 03 02 00 80")),
    ("fc04_peticion", "Read Input Registers, ID 1, offset 0, 1 registro", h("01 04 00 00 00 01")),
    ("fc04_respuesta", "Read Input Registers: potenciometro = 2047", h("01 04 02 07 FF")),
    ("fc05_peticion_on", "Write Single Coil ON (0xFF00); la respuesta es el eco", h("01 05 00 00 FF 00")),
    ("fc05_peticion_off", "Write Single Coil OFF (0x0000); la respuesta es el eco", h("01 05 00 00 00 00")),
    ("fc06_peticion", "Write Single Register = 128; la respuesta es el eco", h("01 06 00 00 00 80")),
    ("fc06_peticion_255", "Write Single Register = 255 (maximo del LED PWM)", h("01 06 00 00 00 FF")),
    # --- Respuestas de excepcion ------------------------------------------
    ("excepcion_01", "Excepcion 01 ILLEGAL FUNCTION sobre FC 0x07", h("01 87 01")),
    ("excepcion_02", "Excepcion 02 ILLEGAL DATA ADDRESS sobre FC 04", h("01 84 02")),
    ("excepcion_03", "Excepcion 03 ILLEGAL DATA VALUE sobre FC 06", h("01 86 03")),
    ("excepcion_04", "Excepcion 04 SLAVE DEVICE FAILURE sobre FC 03", h("01 83 04")),
    # --- Perfil del esclavo desconocido (ADR-007) --------------------------
    ("desconocido_fc03", "Perfil DESCONOCIDO: ID 17, HR 0x0200, 2 registros", h("11 03 02 00 00 02")),
    ("difusion_fc06", "Difusion (ID 0): Write Single Register, no genera respuesta", h("00 06 00 00 00 40")),
    # --- Casos borde -------------------------------------------------------
    ("longitud_minima", "Trama de 4 bytes (2 de mensaje + 2 de CRC)", h("01 07")),
    ("longitud_maxima", "Trama de 256 bytes (254 de mensaje + 2 de CRC): limite RTU", TRAMA_MAXIMA),
    ("todo_ceros", "Seis bytes en 0x00", bytes(6)),
    ("todo_unos", "Seis bytes en 0xFF", bytes([0xFF] * 6)),
]


def main():
    """Genera el JSON y verifica que los dos oraculos coincidan. Retorna 0 o 1."""
    vectores, discrepancias = [], 0
    for nombre, descripcion, mensaje in CASOS:
        crc_a, crc_b = crc_pymodbus(mensaje), crc_t1(mensaje)
        if crc_a != crc_b:
            discrepancias += 1
            print("DISCREPANCIA {}: pymodbus 0x{:04X} / T1 0x{:04X}".format(nombre, crc_a, crc_b))
        cable = bytes([crc_a & 0xFF, crc_a >> 8])        # byte bajo primero
        vectores.append({
            "nombre": nombre,
            "descripcion": descripcion,
            "mensaje_hex": hexa(mensaje),
            "longitud_trama": len(mensaje) + 2,
            "crc": crc_a,
            "crc_hex": "0x{:04X}".format(crc_a),
            "crc_en_cable_hex": hexa(cable),
            "trama_hex": hexa(mensaje + cable),
        })
    if discrepancias:
        print("{} discrepancia(s): no se escribe el archivo".format(discrepancias))
        return 1

    documento = {
        "descripcion": "Vectores golden del CRC-16/MODBUS (polinomio 0xA001 reflejado, valor "
                       "inicial 0xFFFF). 'crc' es el valor del registro; en la trama viaja "
                       "primero el byte bajo ('crc_en_cable_hex').",
        "oraculos": [
            "pymodbus {} (FramerRTU.compute_CRC, convertido de orden de cable a valor)".format(
                VERSION_PYMODBUS),
            "tarea-1/herramientas/modbus_tramas.py (calcular_crc16)",
        ],
        "generado_por": "tarea-3/tools/generar_vectores_crc.py",
        "generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vectores": vectores,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(documento, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("{} vectores, oraculos coincidentes -> {}".format(len(vectores), SALIDA))
    return 0


if __name__ == "__main__":
    sys.exit(main())
