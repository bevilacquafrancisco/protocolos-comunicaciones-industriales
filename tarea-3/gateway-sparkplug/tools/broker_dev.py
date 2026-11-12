#!/usr/bin/env python3
"""
broker_dev.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Broker MQTT de DESARROLLO (amqtt, Python puro) con TLS y usuario/contrasena, para probar el
Edge Node sin hardware ni nube. Reproduce las condiciones del broker real que importan al
ciclo de vida Sparkplug: TLS, autenticacion obligatoria, Last Will y retenidos.

    I-03: este broker NUNCA se usa en la demo. La demo va contra el broker en la nube.

Genera en <carpeta> una CA efimera, un certificado de servidor para 127.0.0.1/localhost y un
archivo de usuarios con hash Argon2 (el formato que exige amqtt). Las claves privadas de
desarrollo quedan en esa carpeta (temporal en las pruebas, gitignored en uso manual).

Uso manual (en gateway-sparkplug/):
    python tools/broker_dev.py --carpeta .dev-broker --puerto 8883
    -> imprime la ruta de la CA (para --mqtt-ca) y las credenciales creadas.
    Las claves de desarrollo se leen del entorno (DEV_MQTT_CLAVE_EDGE, DEV_MQTT_CLAVE_HOST,
    DEV_MQTT_CLAVE_OBSERVADOR) o se generan al azar y se imprimen UNA vez.

Uso desde las pruebas: ver BrokerDesarrollo.

Dependencias externas: amqtt 0.12.1, cryptography 50.0.2 (solo desarrollo).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import ipaddress
import os
import secrets
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

#: Usuarios del broker (ADR-005): uno por rol, con permisos distintos en el broker real.
USUARIOS_POR_DEFECTO = ("edge_node", "host_app", "observador")


def _guardar_clave(clave, ruta: Path) -> None:
    ruta.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    try:
        os.chmod(ruta, 0o600)
    except OSError:       # en Windows chmod no aplica permisos POSIX
        pass


def generar_pki(carpeta: Path) -> dict[str, Path]:
    """
    Crea una CA efimera y un certificado de servidor para 127.0.0.1 y localhost.

    Parametros:
        carpeta (Path): donde dejar ca.pem, servidor.pem y servidor_key.pem.
    Retorna:
        dict[str, Path]: rutas 'ca', 'cert', 'clave'.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora = dt.datetime.now(dt.timezone.utc)
    clave_ca = ec.generate_private_key(ec.SECP256R1())
    nombre_ca = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PdCI-T3 CA de desarrollo")])
    ca = (x509.CertificateBuilder().subject_name(nombre_ca).issuer_name(nombre_ca)
          .public_key(clave_ca.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(ahora - dt.timedelta(minutes=5)).not_valid_after(ahora + dt.timedelta(days=7))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(clave_ca, hashes.SHA256()))
    clave_srv = ec.generate_private_key(ec.SECP256R1())
    srv = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
           .issuer_name(nombre_ca).public_key(clave_srv.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(ahora - dt.timedelta(minutes=5)).not_valid_after(ahora + dt.timedelta(days=7))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                       x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
           .sign(clave_ca, hashes.SHA256()))
    rutas = {"ca": carpeta / "ca.pem", "cert": carpeta / "servidor.pem", "clave": carpeta / "servidor_key.pem"}
    rutas["ca"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    rutas["cert"].write_bytes(srv.public_bytes(serialization.Encoding.PEM))
    _guardar_clave(clave_srv, rutas["clave"])
    return rutas


def escribir_usuarios(ruta: Path, credenciales: dict[str, str]) -> None:
    """Archivo usuario:hash_argon2 (formato de amqtt FileAuthPlugin)."""
    from amqtt.plugins.authentication import Argon2Hasher   # solo desarrollo
    hasher = Argon2Hasher()
    ruta.write_text("".join(f"{u}:{hasher.hash(c)}\n" for u, c in credenciales.items()), encoding="utf-8")


def configuracion(puerto: int, pki: dict[str, Path], usuarios: Path) -> dict:
    """Configuracion de amqtt: un listener TLS, sin anonimo, con archivo de usuarios."""
    return {
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{puerto}", "ssl": True,
                                  "certfile": str(pki["cert"]), "keyfile": str(pki["clave"])}},
        "plugins": {
            "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": False},
            "amqtt.plugins.authentication.FileAuthPlugin": {"password_file": str(usuarios)},
        },
    }


class BrokerDesarrollo:
    """
    Broker amqtt corriendo en un hilo propio con su event loop (asi las pruebas pueden
    usar paho, que es sincrono, sin bloquear al broker).

    Atributos:
        puerto (int), ca (Path): datos para conectarse.
        credenciales (dict[str, str]): usuario -> clave en claro (solo desarrollo).
    """

    def __init__(self, carpeta: Path, puerto: int, credenciales: dict[str, str]):
        self.puerto = puerto
        self.credenciales = credenciales
        self._pki = generar_pki(carpeta)
        self.ca = self._pki["ca"]
        self._usuarios = carpeta / "usuarios.txt"
        escribir_usuarios(self._usuarios, credenciales)
        self._loop = asyncio.new_event_loop()
        self._hilo = threading.Thread(target=self._loop.run_forever, daemon=True, name="broker-dev")
        self._broker = None

    def iniciar(self) -> "BrokerDesarrollo":
        """Arranca el hilo y el broker; vuelve cuando el broker escucha."""
        from amqtt.broker import Broker
        self._hilo.start()

        async def _arrancar():
            self._broker = Broker(configuracion(self.puerto, self._pki, self._usuarios))
            await self._broker.start()

        asyncio.run_coroutine_threadsafe(_arrancar(), self._loop).result(timeout=15)
        return self

    def reiniciar(self, pausa_s: float = 0.0) -> None:
        """Apaga y vuelve a levantar el broker con la misma PKI y el mismo puerto (corte del broker)."""
        from amqtt.broker import Broker

        async def _ciclo():
            await self._broker.shutdown()
            await asyncio.sleep(pausa_s)
            self._broker = Broker(configuracion(self.puerto, self._pki, self._usuarios))
            await self._broker.start()

        asyncio.run_coroutine_threadsafe(_ciclo(), self._loop).result(timeout=30 + pausa_s)

    def detener(self) -> None:
        """Apaga el broker (los clientes ven la conexion cerrada) y el hilo."""
        if self._broker is not None:
            asyncio.run_coroutine_threadsafe(self._broker.shutdown(), self._loop).result(timeout=15)
            self._broker = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._hilo.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Broker MQTT de desarrollo (TLS + usuarios). NO para la demo (I-03).")
    parser.add_argument("--carpeta", type=Path, default=Path(".dev-broker"))
    parser.add_argument("--puerto", type=int, default=8883)
    args = parser.parse_args()
    credenciales = {}
    for usuario in USUARIOS_POR_DEFECTO:
        variable = f"DEV_MQTT_CLAVE_{usuario.split('_')[0].upper()}"
        credenciales[usuario] = os.environ.get(variable) or secrets.token_urlsafe(12)
    broker = BrokerDesarrollo(args.carpeta, args.puerto, credenciales).iniciar()
    print(f"broker de desarrollo en mqtts://127.0.0.1:{args.puerto}  CA: {broker.ca.resolve()}")
    for usuario, clave in credenciales.items():
        print(f"  usuario {usuario:10s} clave {clave}")
    print("Ctrl+C para detener.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        broker.detener()


if __name__ == "__main__":
    main()
