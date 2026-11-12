"""
test_opcua_client.py — cliente OPC UA (T2 adaptado) contra un servidor real en loopback.
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
"""

import asyncio
import random

import pytest

from opcua_client import ClienteOpcua, ConfigOpcua, espera_reintento
from servidor_prueba import ServidorPrueba

pytestmark = pytest.mark.red


def test_retroceso_exponencial_con_tope():
    assert [espera_reintento(i) for i in range(1, 9)] == [1, 2, 4, 8, 16, 30, 30, 30]


async def esperar(condicion, timeout=10.0):
    fin = asyncio.get_running_loop().time() + timeout
    while not condicion():
        if asyncio.get_running_loop().time() > fin:
            raise AssertionError("timeout esperando la condicion")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_suscripcion_escritura_caida_y_reconexion(metricas):
    puerto = 48500 + random.randint(0, 400)
    servidor = await ServidorPrueba(metricas, puerto).iniciar()
    datos, estados, esperas = {}, [], []

    async def dormir(s):                       # registra el retroceso y espera poco (prueba rapida)
        esperas.append(s)
        await asyncio.sleep(0.2)

    cliente = ClienteOpcua(ConfigOpcua(url=servidor.url, seguridad="None"), metricas,
                           al_dato=lambda n, v, ts, ok: datos.__setitem__(n, (v, ts, ok)),
                           al_estado=estados.append, dormir=dormir)
    tarea = asyncio.create_task(cliente.ejecutar())
    try:
        # Notificacion inicial de los 10 MonitoredItems (5 del dispositivo + 5 Status/MODBUS)
        await esperar(lambda: len(datos) == 10)
        assert estados == [True] and cliente.conectado
        assert datos["Status/MODBUS/Estado"][0] == "DONE"

        await servidor.escribir("ns=1;s=Dispositivo1.Inputs.Potenciometro", 3000)
        await esperar(lambda: datos["Inputs/Potenciometro"][0] == 3000)
        assert datos["Inputs/Potenciometro"][1] > 1_700_000_000_000     # SourceTimestamp en ms

        # C5: Write -> Good, y el valor vuelve por la suscripcion
        assert await cliente.escribir("ns=1;s=Dispositivo1.Outputs.LedPWM", "UInt16", 128) == "Good"
        await esperar(lambda: datos["Outputs/LedPWM"][0] == 128)
        # Un nodo de solo lectura: el servidor responde Bad (no corta la sesion)
        r = await cliente.escribir("ns=1;s=Dispositivo1.Inputs.Pulsador", "Boolean", True)
        assert r.startswith("Bad") and cliente.conectado

        # C7: cae el servidor -> ERROR; vuelve -> reconecta solo, DONE, valores nuevos
        await servidor.detener()
        await esperar(lambda: estados[-1] is False, timeout=15)
        assert await cliente.escribir("ns=1;s=Dispositivo1.Outputs.LedPWM", "UInt16", 1) == "BadNotConnected"
        await asyncio.sleep(1.5)                   # algunos reintentos fallidos
        servidor = await ServidorPrueba(metricas, puerto).iniciar()
        datos.clear()
        await esperar(lambda: estados[-1] is True and len(datos) == 10, timeout=20)
        assert cliente.sesiones == 2
        assert esperas[:2] == [1.0, 2.0]           # retroceso exponencial mientras estuvo caido
    finally:
        tarea.cancel()
        await asyncio.gather(tarea, return_exceptions=True)
        await servidor.detener()
