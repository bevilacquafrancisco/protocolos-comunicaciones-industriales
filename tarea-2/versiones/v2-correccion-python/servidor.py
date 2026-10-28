#!/usr/bin/env python3
"""
servidor.py — Raspberry Pi 1 (Servidor OPC UA)
Autores: Peralta Agustina (version original: servidor_ns1.py),
         Bevilacqua Francisco (correccion)
Fecha de creacion: 2026-10-20
Version: 2.0
UNRaf - Protocolos de Comunicaciones Industriales - Tarea 2

Descripcion general
-------------------
Servidor OPC UA en opc.tcp://192.168.10.1:4840 (escucha en 0.0.0.0) con el
modelo de la consigna en ns=1, la rampa diente de sierra, el pulsador local
y los LED que reflejan lo que escribe el cliente. Tres endpoints (None, Sign
y SignAndEncrypt con Basic256Sha256), lista de confianza de certificados y
usuario/contrasena ademas del acceso anonimo.

Cada seccion lleva el bloque del diagrama diagramas/flujo_servidor.md:
S1 inicializacion · S2 espacio de direcciones · S3 rampa · S4 pulsador ·
S5 atencion de escrituras · S6 LED · S7 consola.

Uso
---
    python servidor.py                    # funcionamiento normal
    python servidor.py --rampa-detenida   # captura de KeepAlive (3.4)
    python servidor.py --gamma            # correccion gamma del LED PWM (3.7)

Requiere los certificados (generar_certificados.py servidor) y, para el
usuario, la variable OPCUA_CLAVE_HASH (generar_hash.py). Ver README.md.

Dependencias externas
---------------------
asyncua 2.1.0, gpiozero (+ lgpio en la Raspberry Pi), cryptography.
"""

import argparse
import asyncio
import hashlib
import hmac
import os
import time
from pathlib import Path

from asyncua import Server, ua
from asyncua.common.callback import CallbackType
from asyncua.common.utils import ServiceError
from asyncua.crypto import uacrypto
from asyncua.crypto.permission_rules import USER_TYPES, PermissionRuleset, User, UserRole
from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
from asyncua.server.user_managers import UserManager

import comun
from comun import ahora_iso, formatear_ts

# =============================================================================
# BLOQUE S1 · Inicializacion: argumentos, seguridad y usuarios
# =============================================================================

def leer_argumentos():
    """Retorna argparse.Namespace con las opciones de linea de comandos."""
    parser = argparse.ArgumentParser(description="Servidor OPC UA - Tarea 2 (RPi 1)")
    parser.add_argument("--rampa-detenida", action="store_true",
                        help="no actualiza Servidor.Rampa (captura de KeepAlive, consigna 3.4)")
    parser.add_argument("--gamma", action="store_true",
                        help="correccion gamma 2,2 en el LED PWM (consigna 3.7)")
    parser.add_argument("--pki", type=Path, default=comun.PKI_POR_DEFECTO,
                        help="carpeta de certificados (por defecto ./pki)")
    return parser.parse_args()


def clave_valida(clave, hash_guardado):
    """
    Compara una clave contra el hash scrypt de generar_hash.py.

    Parametros:
        clave (str): clave recibida en el ActivateSession (ya descifrada).
        hash_guardado (str): "scrypt:N:r:p:sal_hex:hash_hex".
    Retorna:
        bool: True si coincide. Comparacion en tiempo constante
        (hmac.compare_digest) para no filtrar informacion por tiempos.
    """
    try:
        algoritmo, n, r, p, sal, esperado = hash_guardado.split(":")
        if algoritmo != "scrypt":
            return False
        calculado = hashlib.scrypt(clave.encode("utf-8"), salt=bytes.fromhex(sal),
                                   n=int(n), r=int(r), p=int(p), maxmem=256 * 1024 * 1024)
        return hmac.compare_digest(calculado.hex(), esperado)
    except (ValueError, TypeError):
        return False


class GestorUsuarios(UserManager):
    """
    Decide quien es cada sesion en el ActivateSession.

    Reemplaza al PermissiveUserManager de asyncua (el que usaba la version
    original), que acepta CUALQUIER usuario con CUALQUIER contrasena.

    Atributos:
        usuario (str): nombre del unico usuario habilitado.
        hash_clave (str): hash scrypt de su clave; vacio = sin usuario.
    """

    def __init__(self, usuario, hash_clave):
        self.usuario = usuario
        self.hash_clave = hash_clave

    def get_user(self, iserver, username=None, password=None, certificate=None):
        """
        Retorna User con su rol, o None para rechazar (BadUserAccessDenied).
        """
        # `certificate` es el del canal (o de un token X509, que no se
        # habilita): sin nombre de usuario la sesion es anonima.
        if username is None:
            return User(role=UserRole.Anonymous)
        if (self.hash_clave and username == self.usuario and password
                and clave_valida(password, self.hash_clave)):
            return User(role=UserRole.User, name=username)
        # [SEC] se registra el intento, nunca la clave.
        print(f"{ahora_iso()} [S1] Usuario rechazado: {username!r}", flush=True)
        return None


class ReglasPorRol(PermissionRuleset):
    """
    Que servicios puede pedir cada rol (autorizacion).

    - Anonimo: leer, navegar y suscribirse; NO escribir.
    - Usuario autenticado: ademas, Write.
    Sin esta regla, autenticar no cambiaria nada. Y la regla por defecto de
    asyncua (SimpleRoleRuleset) deja al anonimo sin ningun servicio, ni Read:
    UaExpert en modo anonimo no podria ni navegar.
    """

    WRITE = ua.NodeId(ua.ObjectIds.WriteRequest_Encoding_DefaultBinary)

    def __init__(self):
        servicios = set(map(ua.NodeId, USER_TYPES))
        self._permisos = {
            UserRole.Admin: set(),          # sin administracion remota
            UserRole.User: servicios,
            UserRole.Anonymous: servicios - {self.WRITE},
        }

    def check_validity(self, user, action_type_id, body):
        return action_type_id in self._permisos.get(user.role, set())


class ListaDeConfianza:
    """
    Validador de certificados de cliente con carpetas trusted/ y rechazados/.

    Un certificado desconocido se guarda en pki/rechazados/ y la conexion se
    rechaza con BadCertificateUntrusted. Para confiar en el, se compara la
    huella SHA-256 con la del cliente y se mueve a pki/trusted/ (no hace falta
    reiniciar: la carpeta se relee en cada CreateSession). Es el mismo
    procedimiento que UaExpert y los servidores comerciales.
    """

    def __init__(self, carpeta_pki):
        self._confiables = carpeta_pki / "trusted"
        self._rechazados = carpeta_pki / "rechazados"
        self._confiables.mkdir(parents=True, exist_ok=True)
        self._rechazados.mkdir(parents=True, exist_ok=True)
        # Ademas de la confianza: vigencia y URI del certificado = ApplicationUri.
        self._basica = CertificateValidator(
            CertificateValidatorOptions.BASIC_VALIDATION | CertificateValidatorOptions.PEER_CLIENT)

    async def __call__(self, certificado, descripcion):
        der = uacrypto.der_from_x509(certificado)
        confiables = {p.read_bytes() for p in self._confiables.glob("*.der")}
        if der not in confiables:
            huella = hashlib.sha256(der).hexdigest()
            (self._rechazados / f"{huella[:16]}.der").write_bytes(der)
            print(f"{ahora_iso()} [S1] Certificado NO confiable de "
                  f"{descripcion.ApplicationUri}: SHA256={huella} -> pki/rechazados/", flush=True)
            raise ServiceError(ua.StatusCodes.BadCertificateUntrusted)
        await self._basica.validate(certificado, descripcion)


async def configurar_seguridad(server, args):
    """
    Tres endpoints (consigna 4.7), confianza (4.8) y usuario (4.9).

    Parametros:
        server (asyncua.Server): servidor ya inicializado.
        args (argparse.Namespace): opciones (carpeta pki).
    Excepciones:
        SystemExit: si faltan los certificados del servidor.
    """
    cert = args.pki / "own" / "servidor_cert.der"
    clave = args.pki / "own" / "servidor_key.pem"
    if not (cert.is_file() and clave.is_file()):
        raise SystemExit(f"Faltan {cert} y {clave}: ejecutar primero "
                         "'python generar_certificados.py servidor' (README §5).")
    await server.load_certificate(str(cert))
    await server.load_private_key(str(clave))

    server.set_security_policy(
        [
            ua.SecurityPolicyType.NoSecurity,                      # UaExpert (2.5) y captura (4.1)
            ua.SecurityPolicyType.Basic256Sha256_Sign,
            ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
        ],
        permission_ruleset=ReglasPorRol(),
    )
    server.set_certificate_validator(ListaDeConfianza(args.pki))

    hash_clave = os.environ.get("OPCUA_CLAVE_HASH", "")
    usuario = os.environ.get("OPCUA_USUARIO", "operador")
    server.iserver.set_user_manager(GestorUsuarios(usuario, hash_clave))
    if hash_clave:
        server.set_identity_tokens([ua.AnonymousIdentityToken, ua.UserNameIdentityToken])
        print(f"Usuarios: anonimo (solo lectura) y '{usuario}' (lectura y escritura)")
    else:
        server.set_identity_tokens([ua.AnonymousIdentityToken])
        print("ATENCION: falta OPCUA_CLAVE_HASH; solo acceso anonimo (nadie puede escribir).")


# =============================================================================
# BLOQUE S2 · Espacio de direcciones
# =============================================================================

async def agregar_eurange(variable):
    """
    Agrega la propiedad EURange = 0..65535 (consigna 2.2).

    Parametros:
        variable (asyncua.Node): variable Rampa.
    Retorna:
        asyncua.Node: la propiedad creada (NodeId fijo "<variable>.EURange").
    """
    rango = ua.Range(Low=0.0, High=float(comun.RAMPA_MAX))
    nodeid = variable.nodeid
    return await variable.add_property(
        ua.NodeId(f"{nodeid.Identifier}.EURange", nodeid.NamespaceIndex),
        ua.QualifiedName("EURange", 0),          # BrowseName estandar (ns=0)
        ua.Variant(rango, ua.VariantType.ExtensionObject),
        datatype=ua.NodeId(ua.ObjectIds.Range),
    )


async def crear_modelo(server):
    """
    Crea Objects/Servidor y Objects/Cliente con sus variables en ns=1.

    asyncua reserva ns=1 para el ApplicationUri del servidor; usar la URI del
    modelo como ApplicationUri es la forma de que el modelo quede en ns=1.
    Aplicacion y modelo son conceptos distintos (se explica en el informe).

    Retorna:
        dict[str, asyncua.Node]: las cuatro variables por nombre corto.
    Excepciones:
        RuntimeError: si el namespace no quedo en ns=1.
    """
    idx = await server.get_namespace_index(comun.NAMESPACE_URI)
    if idx != 1:
        raise RuntimeError(f"El namespace {comun.NAMESPACE_URI} quedo en ns={idx}, se esperaba 1")

    objetos = server.nodes.objects
    obj_servidor = await objetos.add_object(ua.NodeId("Servidor", idx), ua.QualifiedName("Servidor", idx))
    obj_cliente = await objetos.add_object(ua.NodeId("Cliente", idx), ua.QualifiedName("Cliente", idx))

    async def variable(objeto, nombre, valor, tipo):
        return await objeto.add_variable(
            ua.NodeId(f"{(await objeto.read_browse_name()).Name}.{nombre}", idx),
            ua.QualifiedName(nombre, idx),
            ua.Variant(valor, tipo),
        )

    nodos = {
        "estado_servidor": await variable(obj_servidor, "EstadoPulsador", False, ua.VariantType.Boolean),
        "rampa_servidor": await variable(obj_servidor, "Rampa", 0, ua.VariantType.UInt16),
        "estado_cliente": await variable(obj_cliente, "EstadoPulsador", False, ua.VariantType.Boolean),
        "rampa_cliente": await variable(obj_cliente, "Rampa", 0, ua.VariantType.UInt16),
    }
    # Servidor.* queda en AccessLevel 1 (CurrentRead); Cliente.* en 3 (Read|Write).
    await nodos["estado_cliente"].set_writable()
    await nodos["rampa_cliente"].set_writable()
    await agregar_eurange(nodos["rampa_servidor"])
    await agregar_eurange(nodos["rampa_cliente"])
    return nodos


# =============================================================================
# Estado compartido entre tareas
# =============================================================================

class EstadoServidor:
    """Ultimos valores locales y recibidos, para S6 y S7."""

    def __init__(self):
        self.rampa_local = 0
        self.pulsador_local = False
        self.pulsador_remoto = False
        self.rampa_remota = 0
        self.ts_rampa_remota = None


# =============================================================================
# BLOQUE S3 · Generacion de la rampa diente de sierra
# =============================================================================

async def tarea_rampa(nodo, estado, detenida):
    """
    Diente de sierra 0..65535, periodo 4 s, cada 50 ms (consigna 2.3).

    El valor se calcula desde el reloj y el ciclo se programa sobre tiempos
    absolutos: un sleep(0.05) fijo (version original) acumula el tiempo de
    trabajo de cada vuelta y el periodo se alarga.

    Parametros:
        nodo (asyncua.Node): Servidor.Rampa.
        estado (EstadoServidor): se actualiza rampa_local.
        detenida (bool): no escribir (captura de KeepAlive, 3.4).
    """
    if detenida:
        return          # Servidor.Rampa queda fija en 0
    inicio = time.monotonic()
    proximo = inicio
    while True:
        estado.rampa_local = comun.rampa_diente_sierra(time.monotonic() - inicio)
        await nodo.write_value(ua.DataValue(
            ua.Variant(estado.rampa_local, ua.VariantType.UInt16),
            SourceTimestamp=comun.ahora_utc()))
        proximo = max(proximo + comun.PASO_RAMPA_S, time.monotonic())   # sin rafagas si se atrasa
        await asyncio.sleep(max(0.0, proximo - time.monotonic()))


# =============================================================================
# BLOQUE S4 · Lectura del pulsador (por evento)
# =============================================================================

async def tarea_pulsador(pulsador, nodo, estado):
    """
    Publica Servidor.EstadoPulsador en cada flanco.

    Solo escribe cuando cambia: el SourceTimestamp queda en el instante del
    flanco y la suscripcion del cliente notifica una vez por pulsacion.

    Parametros:
        pulsador (comun.Pulsador), nodo (asyncua.Node), estado (EstadoServidor).
    """
    while True:
        estado.pulsador_local = pulsador.presionado
        await nodo.write_value(ua.DataValue(
            ua.Variant(estado.pulsador_local, ua.VariantType.Boolean),
            SourceTimestamp=comun.ahora_utc()))
        await pulsador.cambio.wait()
        pulsador.cambio.clear()


# =============================================================================
# BLOQUES S5 y S6 · Atencion de escrituras y manejo de los LED
# =============================================================================

def crear_atencion_escrituras(nodos, estado, salidas):
    """
    Arma el manejador que asyncua llama despues de cada Write de un cliente.

    Version original: el bucle releia Cliente.* cada 50 ms (sondeo), lo que
    sumaba hasta 50 ms a la latencia. Ahora el LED cambia en el mismo momento
    en que el servidor acepta la escritura.

    Retorna:
        Callable[[ServerItemCallback, CallbackService], None]
    """
    id_estado = nodos["estado_cliente"].nodeid
    id_rampa = nodos["rampa_cliente"].nodeid

    def al_escribir(evento, _despachador):
        for pedido, resultado in zip(evento.request_params.NodesToWrite, evento.response_params):
            if not resultado.is_good() or pedido.AttributeId != ua.AttributeIds.Value:
                continue
            valor = pedido.Value.Value.Value
            if pedido.NodeId == id_estado:
                estado.pulsador_remoto = bool(valor)
                salidas.led_digital(estado.pulsador_remoto)          # S6
            elif pedido.NodeId == id_rampa:
                estado.rampa_remota = int(valor)
                estado.ts_rampa_remota = pedido.Value.SourceTimestamp
                salidas.led_pwm(estado.rampa_remota)                 # S6

    return al_escribir


# =============================================================================
# BLOQUE S7 · Registro en consola
# =============================================================================

async def tarea_consola(estado, salidas):
    """Cada 0,5 s: rampa generada, rampa recibida y su SourceTimestamp (3.5)."""
    while True:
        print(f"{ahora_iso()} [S7] generada={estado.rampa_local:5d} | "
              f"recibida Cliente.Rampa={estado.rampa_remota:5d} (PWM {salidas.duty:3d}/255) "
              f"SourceTimestamp={formatear_ts(estado.ts_rampa_remota)} | "
              f"pulsador local={int(estado.pulsador_local)} remoto={int(estado.pulsador_remoto)}",
              flush=True)
        await asyncio.sleep(comun.INTERVALO_LOG_S)


# =============================================================================
# Programa principal
# =============================================================================

async def main(args):
    """S1 -> S2 -> arranque -> S3, S4 y S7 concurrentes (S5/S6 por evento)."""
    comun.configurar_registro()
    server = Server()
    await server.init()
    await server.set_application_uri(comun.NAMESPACE_URI)
    server.set_endpoint(comun.ENDPOINT_ESCUCHA)
    server.set_server_name("UNRaf TP2 - Servidor OPC UA")
    await configurar_seguridad(server, args)

    nodos = await crear_modelo(server)

    estado = EstadoServidor()
    salidas = comun.Salidas(gamma=args.gamma)
    pulsador = comun.Pulsador(asyncio.get_running_loop())
    server.subscribe_server_callback(CallbackType.PostWrite,
                                     crear_atencion_escrituras(nodos, estado, salidas))
    try:
        async with server:
            print("=" * 70)
            print("SERVIDOR OPC UA INICIADO")
            print(f"Endpoint: {comun.URL_SERVIDOR} (escucha en todas las interfaces)")
            for ep in await server.get_endpoints():
                print(f"  {ep.SecurityPolicyUri.split('#')[-1]:15s} {ep.SecurityMode.name}")
            print(f"Namespace: {comun.NAMESPACE_URI} (ns=1)"
                  + (" | RAMPA DETENIDA" if args.rampa_detenida else ""))
            print("=" * 70, flush=True)
            await asyncio.gather(
                tarea_rampa(nodos["rampa_servidor"], estado, args.rampa_detenida),
                tarea_pulsador(pulsador, nodos["estado_servidor"], estado),
                tarea_consola(estado, salidas),
            )
    finally:
        pulsador.cerrar()
        salidas.cerrar()


if __name__ == "__main__":
    try:
        asyncio.run(main(leer_argumentos()))
    except KeyboardInterrupt:
        print("\nServidor detenido por el usuario.")
