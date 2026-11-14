#!/usr/bin/env python3
"""
prueba_config.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Comprueba, sin placa, que la configuracion del esclavo sea desplegable:

- config.py se importa en CPython (no depende de `machine`) y cada perfil construye un
  modelo de datos valido;
- los parametros respetan la norma y las decisiones del proyecto (Unit ID 1-247, baud
  <= 19200 por ADR-010, paridad N/E/O, pines fuera de strapping y de la flash);
- el perfil DISPOSITIVO_1 usa los nombres del diccionario de datos (I-06);
- el stack lib/modbus_slave no importa `machine` (debe probarse en la PC, I-01/§6);
- main.py y perifericos.py compilan (sintaxis) aunque no puedan ejecutarse sin placa.

Uso:  python tarea-3/firmware/esclavo-modbus/test/prueba_config.py   (exit 1 si falla)
"""

import py_compile
import sys
from pathlib import Path

from _comun import RAIZ_FIRMWARE, Verificador
import config
from modbus_slave.data_model import ModeloDatos

#: Senales que main.py sabe manejar (Esclavo._crear_perifericos).
SENALES_CONOCIDAS = {"pulsador", "potenciometro", "led_digital", "led_pwm", "uptime_s", None}

#: GPIO prohibidos (tarea-1/docs/arquitectura.md §8.1): strapping y flash SPI.
PINES_PROHIBIDOS = {0, 2, 5, 12, 15, 6, 7, 8, 9, 10, 11}

#: Diccionario de datos §1 (I-06): tabla, direccion, nombre del perfil DISPOSITIVO_1.
DICCIONARIO_D1 = {
    ("discrete_inputs", 0x0000, "Inputs/Pulsador"),
    ("input_registers", 0x0000, "Inputs/Potenciometro"),
    ("coils", 0x0000, "Outputs/LedDigital"),
    ("holding_registers", 0x0000, "Outputs/LedPWM"),
}


def main():
    """Ejecuta las verificaciones. Retorna el codigo de salida."""
    v = Verificador("Configuracion del esclavo y aptitud para desplegar")

    v.check(config.PERFIL in ("JUMPER",) + tuple(config.PERFILES),
            "PERFIL valido: {}".format(config.PERFIL))
    v.check(set(config.PERFILES) >= {"DISPOSITIVO_1", "DESCONOCIDO"},
            "existen los perfiles DISPOSITIVO_1 y DESCONOCIDO")

    for nombre, perfil in config.PERFILES.items():
        print("-- Perfil " + nombre)
        try:
            modelo = ModeloDatos(perfil["mapa"])
            v.check(True, "el mapa construye un modelo valido")
        except ValueError as error:
            v.check(False, "el mapa construye un modelo valido", str(error))
            continue
        v.check(1 <= perfil["unit_id"] <= 247, "Unit ID {} en 1-247".format(perfil["unit_id"]))
        v.check(1200 <= perfil["baud"] <= 19200,
                "baud {} <= 19200 (ADR-010, salvaguarda a)".format(perfil["baud"]))
        v.check(perfil["paridad"] in ("N", "E", "O"), "paridad {}".format(perfil["paridad"]))
        v.check(perfil["bits_parada"] in (1, 2), "bits de parada {}".format(perfil["bits_parada"]))
        senales = {e.get("senal") for e in perfil["mapa"]}
        v.check(senales <= SENALES_CONOCIDAS, "todas las senales tienen hardware en main.py",
                str(senales - SENALES_CONOCIDAS))
        v.check(modelo.valor_de_senal("led_pwm") in (0, None)
                and modelo.valor_de_senal("led_digital") in (0, None),
                "las salidas arrancan apagadas (estado seguro)")

    d1 = {(e["tabla"], e["direccion"], e["nombre"]) for e in config.PERFILES["DISPOSITIVO_1"]["mapa"]}
    v.check(d1 == DICCIONARIO_D1, "DISPOSITIVO_1 = diccionario de datos §1 (nombres y offsets, I-06)")
    p1, p2 = config.PERFILES["DISPOSITIVO_1"], config.PERFILES["DESCONOCIDO"]
    v.check(p1["unit_id"] != p2["unit_id"] and (p1["baud"], p1["paridad"]) != (p2["baud"], p2["paridad"]),
            "DESCONOCIDO difiere del dispositivo 1 en Unit ID, baud y paridad (ADR-007)")
    v.check(p1["baud"] == 9600 and p1["paridad"] == "N" and p1["unit_id"] == 1,
            "DISPOSITIVO_1 conserva 9600 8N1, Unit ID 1 de la Tarea 1")

    print("-- Pines")
    pines = {n: getattr(config, n) for n in dir(config) if n.startswith("PIN_")}
    v.check(not set(pines.values()) & PINES_PROHIBIDOS,
            "ningun pin de strapping ni de la flash SPI", str(pines))
    v.check(len(set(pines.values())) == len(pines), "ningun pin asignado dos veces", str(pines))
    v.check(34 <= config.PIN_POTENCIOMETRO <= 39, "potenciometro en ADC1 (GPIO 32-39, apto con Wi-Fi)")

    print("-- Separacion hardware / protocolo")
    for archivo in sorted((RAIZ_FIRMWARE / "lib" / "modbus_slave").glob("*.py")):
        texto = archivo.read_text(encoding="utf-8")
        v.check("import machine" not in texto and "from machine" not in texto,
                "lib/modbus_slave/{} no importa machine".format(archivo.name))
    for archivo in ("main.py", "perifericos.py", "config.py"):
        try:
            py_compile.compile(str(RAIZ_FIRMWARE / "src" / archivo), doraise=True)
            v.check(True, "src/{} compila (sintaxis)".format(archivo))
        except py_compile.PyCompileError as error:
            v.check(False, "src/{} compila (sintaxis)".format(archivo), str(error))

    # CPython acepta sintaxis que MicroPython no: si esta mpy-cross (el compilador oficial
    # de MicroPython, tools/requirements-dev.txt), se compila todo para el ESP32.
    print("-- Compilacion con mpy-cross para ESP32 (xtensawin)")
    try:
        import mpy_cross
    except ImportError:
        print("  OMITIDA  mpy-cross no instalado (pip install -r tarea-3/tools/requirements-dev.txt)")
        return v.terminar()
    import subprocess
    import tempfile
    archivos = sorted((RAIZ_FIRMWARE / "lib" / "modbus_slave").glob("*.py")) + \
        sorted((RAIZ_FIRMWARE / "src").glob("*.py"))
    with tempfile.TemporaryDirectory() as salida:
        for archivo in archivos:
            destino = Path(salida) / (archivo.stem + ".mpy")
            proceso = mpy_cross.run("-march=xtensawin", "-o", str(destino), str(archivo),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, error = proceso.communicate()
            v.check(proceso.returncode == 0, "mpy-cross: {} compila para MicroPython".format(
                archivo.relative_to(RAIZ_FIRMWARE).as_posix()), error.decode(errors="replace"))
    return v.terminar()


if __name__ == "__main__":
    sys.exit(main())
