#!/usr/bin/env python3
"""
cliente.py — Raspberry Pi 2 (Cliente OPC UA, Modo A: Read periodico)
Autores: Peralta Agustina (version original), Bevilacqua Francisco (correccion)
Fecha de creacion: 2026-10-20
Version: 2.0
UNRaf - Protocolos de Comunicaciones Industriales - Tarea 2

Descripcion general
-------------------
Modo A de la consigna 3.4: servicio Read cada 100 ms (polling). Solo el
bloque C3 es propio de este archivo; C1, C2 y C4-C7 estan en cliente_base.py
(iguales a los del Modo B, para que la comparacion sea justa).

Uso
---
    python cliente.py                          # None, con el usuario del entorno
    python cliente.py --seguridad Sign         # o SignAndEncrypt (4.7)
    python cliente.py --sin-escritura          # captura de KeepAlive (3.4)
    python cliente.py --anonimo                # prueba de autorizacion (4.9)

Dependencias externas
---------------------
asyncua 2.1.0, gpiozero (+ lgpio en la Raspberry Pi).
"""

import asyncio
import time

import cliente_base

INTERVALO_POLLING_S = 0.100


# =============================================================================
# BLOQUE C3 (Modo A) · Read periodico cada 100 ms
# =============================================================================

async def leer_por_polling(client, nodos, estado, salidas):
    """
    Un unico ReadRequest con los DOS nodos cada 100 ms.

    La version original hacia dos Read de un nodo cada uno: el doble de
    pedidos, lo que sesgaba la comparacion A frente a B.

    Parametros:
        client (asyncua.Client), nodos (dict), estado (EstadoCliente),
        salidas (comun.Salidas).
    Excepciones:
        ua.UaStatusCodeError, asyncio.TimeoutError, OSError: se propagan a C7.
    """
    proximo = time.monotonic()
    while True:
        # Client.read_attributes(nodes: list[Node], attr=Value) -> list[DataValue]
        dv_estado, dv_rampa = await client.read_attributes(
            [nodos["estado_servidor"], nodos["rampa_servidor"]])
        cliente_base.replicar(estado, salidas, dv_estado, dv_rampa)        # C4
        proximo = max(proximo + INTERVALO_POLLING_S, time.monotonic())
        await asyncio.sleep(max(0.0, proximo - time.monotonic()))


if __name__ == "__main__":
    argumentos = cliente_base.leer_argumentos("Cliente OPC UA - Modo A (Read cada 100 ms)")
    try:
        asyncio.run(cliente_base.main(argumentos, leer_por_polling))
    except KeyboardInterrupt:
        print("\nCliente detenido por el usuario.")
