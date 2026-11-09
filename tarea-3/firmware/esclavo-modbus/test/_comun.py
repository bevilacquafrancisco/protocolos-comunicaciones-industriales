"""
_comun.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Utilidades compartidas por las pruebas del esclavo, que corren en CPython en la PC
(sin placa): rutas de importacion, verificador check() con conteo de fallas y lectura
de los vectores golden. Mismo patron que las pruebas de la Tarea 1: scripts con codigo
de salida 1 si algo falla, sin pytest.

Dependencias externas
---------------------
Ninguna (biblioteca estandar).
"""

import json
import sys
from pathlib import Path

#: firmware/esclavo-modbus/
RAIZ_FIRMWARE = Path(__file__).resolve().parents[1]
#: tarea-3/
RAIZ_T3 = RAIZ_FIRMWARE.parents[1]
#: Vectores golden del CRC, compartidos con el maestro en JavaScript.
VECTORES_CRC = RAIZ_T3 / "tests" / "fixtures" / "crc_vectors.json"

# El stack (lib/) y la configuracion (src/config.py) se importan como en el ESP32.
for ruta in (RAIZ_FIRMWARE / "lib", RAIZ_FIRMWARE / "src"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))


class Verificador:
    """
    Cuenta verificaciones y fallas, e imprime una linea por cada una.

    Atributos:
        total (int), fallas (int).
    """

    def __init__(self, titulo):
        self.total = 0
        self.fallas = 0
        print("=" * 70)
        print(titulo)
        print("=" * 70)

    def check(self, condicion, texto, detalle=""):
        """
        Registra una verificacion.

        Parametros:
            condicion (bool): resultado.
            texto (str): que se verifica.
            detalle (str): dato adicional que se muestra si falla.
        Retorna:
            bool: la condicion.
        """
        self.total += 1
        if condicion:
            print("  OK     " + texto)
        else:
            self.fallas += 1
            print("  FALLA  " + texto + ("  -> " + detalle if detalle else ""))
        return bool(condicion)

    def lanza(self, excepcion, funcion, texto):
        """Verifica que funcion() lance la excepcion indicada. Retorna la excepcion o None."""
        try:
            funcion()
        except excepcion as error:
            self.check(True, texto)
            return error
        except Exception as error:     # otra excepcion: falla con el detalle
            self.check(False, texto, "lanzo {}: {}".format(type(error).__name__, error))
            return None
        self.check(False, texto, "no lanzo {}".format(excepcion.__name__))
        return None

    def terminar(self):
        """Imprime el resumen y retorna el codigo de salida (0 o 1)."""
        print("-" * 70)
        print("{} verificaciones, {} falla(s)".format(self.total, self.fallas))
        return 1 if self.fallas else 0


def hexa(datos):
    """bytes -> '01 04 00 00'."""
    return " ".join("{:02X}".format(b) for b in datos)


def desde_hex(texto):
    """'01 04 00 00' -> bytes."""
    return bytes.fromhex(texto.replace(" ", ""))


def cargar_vectores():
    """Retorna dict nombre -> vector de tests/fixtures/crc_vectors.json."""
    documento = json.loads(VECTORES_CRC.read_text(encoding="utf-8"))
    return {v["nombre"]: v for v in documento["vectores"]}
