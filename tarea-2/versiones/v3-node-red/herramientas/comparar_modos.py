# -*- coding: utf-8 -*-
"""
comparar_modos.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-14
Version: 1.0

Descripcion general
-------------------
Consigna, Parte 3.4: "comparar la cantidad de tramas y de bytes" entre el
Modo A (Read periodico cada 100 ms) y el Modo B (suscripcion con
PublishingInterval de 100 ms), con la rampa en movimiento y con la rampa
detenida.

Trabaja sobre los vectores de regimen generados con capturar_tramas_local.js
(servidor y cliente reales del trabajo, 10 s, proxy TCP local). Es la
PREDICCION que se contrasta despues con la captura tcpdump del banco: si el
banco da otra cosa, la diferencia es un hallazgo a explicar.

Que se cuenta
-------------
- Solo la ventana de regimen: desde el primer intercambio de datos hasta el
  cierre (sin el establecimiento de sesion ni el cierre).
- Mensajes UA y bytes UA (MessageSize).
- Bytes estimados en tramas Ethernet: UA + 66 bytes por mensaje (Ethernet 14
  + IPv4 20 + TCP 32 con Timestamps), suponiendo un segmento por mensaje y
  sin contar los ACK TCP puros. La captura real los incluye: por eso el
  banco va a dar algo mas.

Uso
---
    python comparar_modos.py

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""
import json
import os
import sys
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import opcua_tramas as o  # noqa: E402

CABECERAS_POR_MENSAJE = 14 + 20 + 32
ESCENARIOS = [
    ("A - Read", "rampa en movimiento", "sesion_None_lecturaA_regimen"),
    ("B - Suscripcion", "rampa en movimiento", "sesion_None_regimen"),
    ("A - Read", "rampa detenida", "sesion_None_lecturaA_regimen_quieto"),
    ("B - Suscripcion", "rampa detenida", "sesion_None_regimen_quieto"),
]


def analizar(nombre):
    """
    Cuenta mensajes y bytes en la ventana de regimen de un vector.

    Parametros
    ----------
    nombre : str
        Nombre del archivo en vectores/, sin extension.

    Retorna
    -------
    dict | None
        duracion_s, mensajes, bytes_ua, por_servicio (Counter), keepalives;
        None si el vector no existe.
    """
    ruta = os.path.join(AQUI, "vectores", nombre + ".json")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        mensajes = json.load(f)["mensajes"]
    dec = [(m, o.decodificar_opcua(bytes.fromhex(m["hex"]))) for m in mensajes]
    servicios = [r["servicio"] for _, r in dec]
    if "CreateMonitoredItemsResponse" in servicios:
        inicio = servicios.index("CreateMonitoredItemsResponse") + 1
    else:
        # Modo A: el primer ReadResponse es el del NamespaceArray.
        inicio = [i for i, s in enumerate(servicios) if s == "ReadResponse"][1]
    fin = min(i for i, s in enumerate(servicios)
              if s in ("DeleteSubscriptionsRequest", "CloseSessionRequest"))
    ventana = dec[inicio:fin]
    duracion = (ventana[-1][0]["t_ms"] - ventana[0][0]["t_ms"]) / 1000.0
    keepalives = sum(
        1 for _, r in ventana if r["servicio"] == "PublishResponse"
        and any("KeepAlive" in c["significado"] for c in r["campos"]
                if c["campo"].endswith("NotificationData.Length")))
    return {
        "duracion_s": duracion,
        "mensajes": len(ventana),
        "bytes_ua": sum(len(m["hex"]) // 2 for m, _ in ventana),
        "por_servicio": Counter(r["servicio"] for _, r in ventana),
        "keepalives": keepalives,
    }


def main():
    """Imprime la tabla comparativa normalizada a 60 s (duracion de la consigna)."""
    print("Prediccion por 60 s (vectores locales; contrastar con la captura del banco)\n")
    print("| Modo | Escenario | Mensajes UA | Bytes UA | Bytes en tramas (est.) | KeepAlive |")
    print("|---|---|---|---|---|---|")
    resultados = {}
    for modo, escenario, nombre in ESCENARIOS:
        r = analizar(nombre)
        if r is None:
            print("| {} | {} | (falta vectores/{}.json) | | | |".format(modo, escenario, nombre))
            continue
        k = 60.0 / r["duracion_s"]
        resultados[(modo[0], escenario)] = (r["mensajes"] * k, r["bytes_ua"] * k)
        print("| {} | {} | {:.0f} | {:.0f} | {:.0f} | {:.0f} |".format(
            modo, escenario, r["mensajes"] * k, r["bytes_ua"] * k,
            (r["bytes_ua"] + CABECERAS_POR_MENSAJE * r["mensajes"]) * k, r["keepalives"] * k))
    print()
    for escenario in ("rampa en movimiento", "rampa detenida"):
        a, b = resultados.get(("A", escenario)), resultados.get(("B", escenario))
        if a and b:
            print("{}: el Modo B usa {:.0%} de los mensajes y {:.0%} de los bytes del Modo A".format(
                escenario, b[0] / a[0], b[1] / a[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
