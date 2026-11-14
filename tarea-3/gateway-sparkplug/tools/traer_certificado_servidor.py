#!/usr/bin/env python3
"""
traer_certificado_servidor.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Obtiene el certificado X.509 del servidor OPC UA (dispositivo 2) con un GetEndpoints sobre el
canal None, muestra su huella SHA-1 y lo guarda en <pki>/servidor_cert.der SOLO si se confirma
que coincide con la que muestra el panel de Node-RED ("Huella del servidor"). Es el lado
CLIENTE de la confianza mutua (docs/seguridad-opcua.md §3-§4): sin comparar la huella por un
canal distinto de la red, un impostor en la LAN podria plantar su propio certificado.

Uso (en gateway-sparkplug/):
    python tools/traer_certificado_servidor.py opc.tcp://192.168.10.1:4840
    python tools/traer_certificado_servidor.py <url> --huella <sha1 del panel>   (sin preguntar)

Dependencias externas: asyncua 2.1.0.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

from asyncua import Client

RAIZ = Path(__file__).resolve().parents[1]


async def traer(url: str) -> bytes:
    """Certificado DER del primer endpoint que lo informe (todos llevan el mismo)."""
    cliente = Client(url=url, timeout=4)
    # Client.connect_and_get_server_endpoints() -> list[EndpointDescription] (canal None temporal)
    endpoints = await cliente.connect_and_get_server_endpoints()
    certificado = next((bytes(e.ServerCertificate) for e in endpoints if e.ServerCertificate), None)
    if certificado is None:
        raise SystemExit("el servidor no informa certificado (¿solo endpoint None?)")
    return certificado


def main() -> None:
    p = argparse.ArgumentParser(description="Trae y confia (con verificacion de huella) el certificado del servidor OPC UA")
    p.add_argument("url")
    p.add_argument("--pki", type=Path, default=RAIZ / "pki")
    p.add_argument("--huella", help="huella SHA-1 esperada (la del panel de Node-RED); sin ella, se pregunta")
    args = p.parse_args()
    der = asyncio.run(traer(args.url))
    huella = hashlib.sha1(der).hexdigest()
    print(f"Huella SHA-1 del servidor: {huella}")
    if args.huella:
        if args.huella.replace(":", "").lower() != huella:
            raise SystemExit("NO coincide con la huella esperada: no se guarda (posible impostor)")
    elif input("¿Coincide con la del panel de Node-RED? [s/N] ").strip().lower() != "s":
        raise SystemExit("no se guarda")
    args.pki.mkdir(parents=True, exist_ok=True)
    destino = args.pki / "servidor_cert.der"
    destino.write_bytes(der)
    print(f"guardado en {destino}")


if __name__ == "__main__":
    main()
