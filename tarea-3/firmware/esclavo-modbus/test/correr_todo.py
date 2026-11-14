#!/usr/bin/env python3
"""
correr_todo.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Ejecuta todas las pruebas del esclavo en la PC, cada una en su propio proceso, y
resume. Retorna codigo 1 si alguna falla.

Uso:  python tarea-3/firmware/esclavo-modbus/test/correr_todo.py
"""

import subprocess
import sys
from pathlib import Path

PRUEBAS = ["prueba_crc.py", "prueba_data_model.py", "prueba_frame_parser.py", "prueba_config.py"]


def main():
    """Corre las pruebas y retorna 0 si todas pasan."""
    carpeta = Path(__file__).resolve().parent
    resultados = []
    for prueba in PRUEBAS:
        proceso = subprocess.run([sys.executable, str(carpeta / prueba)], cwd=str(carpeta),
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        ultima = (proceso.stdout.strip().splitlines() or ["(sin salida)"])[-1]
        resultados.append((prueba, proceso.returncode, ultima))
        if proceso.returncode:
            print(proceso.stdout)
            print(proceso.stderr)
    print("=" * 70)
    for prueba, codigo, ultima in resultados:
        print("{:<26} {}  {}".format(prueba, "OK   " if codigo == 0 else "FALLA", ultima))
    fallas = sum(1 for _, codigo, _ in resultados if codigo)
    print("=" * 70)
    print("TODO OK" if not fallas else "{} prueba(s) con fallas".format(fallas))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
