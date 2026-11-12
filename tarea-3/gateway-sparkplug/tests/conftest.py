"""
conftest.py — configuracion comun de las pruebas del dispositivo 3.
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0

Agrega src/ y tools/ al sys.path (el codigo se ejecuta como scripts, no como paquete) y
ofrece fixtures: metricas del diccionario REAL, topicos y un nucleo con reloj controlable.
"""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))

import sparkplug as spb                                          # noqa: E402
from ciclo_vida import AlmacenBdSeqMemoria, NucleoEdgeNode       # noqa: E402
from metrics import cargar_metricas                              # noqa: E402


class Reloj:
    """Reloj en ms controlable desde la prueba."""

    def __init__(self, inicio=1_763_000_000_000):
        self.ms = inicio

    def __call__(self):
        return self.ms

    def avanzar(self, ms):
        self.ms += ms


@pytest.fixture(scope="session")
def metricas():
    return cargar_metricas()


@pytest.fixture
def topicos():
    return spb.Topicos(grupo="UNRaf_PdCI_2026", nodo="EN01_Gateway", dispositivo="DEV01_ESP32_Slave",
                       host="HA01_WebDashboard")


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def nucleo(metricas, topicos, reloj):
    return NucleoEdgeNode(metricas, topicos, AlmacenBdSeqMemoria(), reloj=reloj)


#: Valores iniciales tipicos de las 15 metricas que llegan por OPC UA.
VALORES_DISPOSITIVO = {"Inputs/Pulsador": False, "Inputs/Potenciometro": 2048, "Outputs/LedDigital": False,
                       "Outputs/LedPWM": 0, "Inputs/Potenciometro_pct": 50.0}
VALORES_ESTADO = {"Status/MODBUS/Estado": "DONE", "Status/MODBUS/OK": 10, "Status/MODBUS/CRC_ERROR": 0,
                  "Status/MODBUS/TIMEOUT": 0, "Status/MODBUS/EXCEPTION": 0}


def alimentar(nucleo, valores):
    """Entrega varios valores al nucleo y junta los mensajes producidos."""
    salida = []
    for nombre, valor in valores.items():
        salida += nucleo.al_dato(nombre, valor, None, True)
    return salida


def nucleo_en_linea(nucleo):
    """Conecta, OPC UA sano y todos los valores: deja NBIRTH + DBIRTH publicados. Retorna los mensajes."""
    nucleo.preparar_conexion()
    salida = nucleo.al_conectar()
    salida += nucleo.al_estado_opcua(True)
    salida += alimentar(nucleo, {**VALORES_ESTADO, **VALORES_DISPOSITIVO})
    return salida
