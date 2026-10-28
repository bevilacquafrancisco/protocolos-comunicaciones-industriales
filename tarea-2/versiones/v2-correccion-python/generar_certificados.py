#!/usr/bin/env python3
"""
generar_certificados.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-20
Version: 1.0

Descripcion general
-------------------
Genera el certificado X.509 de APLICACION autofirmado (RSA 2048, SHA-256,
1 ano) y su clave privada, con el generador de asyncua (consigna 4.8).

    pki/own/<rol>_cert.der   certificado: se puede copiar a la otra placa
    pki/own/<rol>_key.pem    clave privada: NUNCA sale de la placa (permisos 600)
    pki/trusted/             certificados en los que se confia (servidor)
    pki/rechazados/          certificados desconocidos que intentaron conectar

La URI del certificado (campo SubjectAltName) tiene que coincidir con el
ApplicationUri que presenta el programa; si no, BadCertificateUriInvalid.

Uso
---
    python generar_certificados.py servidor     # en la RPi 1
    python generar_certificados.py cliente      # en la RPi 2

Si el certificado ya existe y es valido no se regenera.

Dependencias externas
---------------------
asyncua 2.1.0 (asyncua.crypto.cert_gen), cryptography.
"""

import argparse
import asyncio
import hashlib
import os
import socket
from pathlib import Path

from asyncua.crypto.cert_gen import setup_self_signed_certificate
from cryptography.x509.oid import ExtendedKeyUsageOID

import comun

ROLES = {
    "servidor": (comun.NAMESPACE_URI, ExtendedKeyUsageOID.SERVER_AUTH, "TP2 Servidor OPC UA"),
    "cliente": (comun.URI_CLIENTE, ExtendedKeyUsageOID.CLIENT_AUTH, "TP2 Cliente OPC UA"),
}


async def main():
    parser = argparse.ArgumentParser(description="Certificado de aplicacion OPC UA")
    parser.add_argument("rol", choices=ROLES)
    parser.add_argument("--pki", type=Path, default=comun.PKI_POR_DEFECTO)
    args = parser.parse_args()

    uri, uso, nombre = ROLES[args.rol]
    propios = args.pki / "own"
    for carpeta in (propios, args.pki / "trusted", args.pki / "rechazados"):
        carpeta.mkdir(parents=True, exist_ok=True)
    os.chmod(propios, 0o700)

    clave = propios / f"{args.rol}_key.pem"
    cert = propios / f"{args.rol}_cert.der"
    # setup_self_signed_certificate(key_file, cert_file, app_uri, host_name,
    #     cert_use: list[OID], subject_attrs: dict) -> None
    await setup_self_signed_certificate(
        clave, cert, uri, socket.gethostname(), [uso],
        {"commonName": nombre, "organizationName": "UNRaf PdCI", "countryName": "AR"})
    os.chmod(clave, 0o600)

    huella = hashlib.sha256(cert.read_bytes()).hexdigest()
    print(f"Certificado: {cert}\nClave privada: {clave} (permisos 600, no copiar)")
    print(f"ApplicationUri: {uri}\nHuella SHA-256: {':'.join(huella[i:i + 2] for i in range(0, 64, 2))}")


if __name__ == "__main__":
    asyncio.run(main())
