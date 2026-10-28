#!/usr/bin/env python3
"""
cliente_base.py
Autores: Peralta Agustina (version original), Bevilacqua Francisco (correccion)
Fecha de creacion: 2026-10-20
Version: 2.0

Descripcion general
-------------------
Todo lo que comparten los dos clientes de la RPi 2. Lo unico que cambia entre
cliente.py (Modo A) y cliente_suscripcion.py (Modo B) es el bloque C3, la
forma de LEER el servidor: justo lo que la consigna 3.4 pide comparar. El
resto es identico, asi la comparacion de tramas no queda sesgada.

Bloques de diagramas/flujo_cliente.md:
C1 conexion y seguridad · C2 rampa triangular · C4 replicacion en LED ·
C5 escrituras · C6 consola · C7 reconexion ante perdida del canal.
(C3 esta en cada cliente.)

Dependencias externas
---------------------
asyncua 2.1.0, gpiozero (+ lgpio en la Raspberry Pi).
"""

import argparse
import asyncio
import os
import time
from pathlib import Path

from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

import comun
from comun import ahora_iso, formatear_ts

INTERVALO_ESCRITURA_S = 0.100   # Cliente.Rampa cada 100 ms (3.3)
INTERVALO_RECONEXION_S = 2.0
TIMEOUT_PEDIDO_S = 4.0          # cada pedido espera respuesta 4 s
# La sesion abandonada (cable cortado) se libera en el servidor a los 60 s;
# asyncua pide 1 h por defecto.
TIMEOUT_SESION_MS = 60_000

MODOS_SEGURIDAD = {
    "None": ua.MessageSecurityMode.None_,
    "Sign": ua.MessageSecurityMode.Sign,
    "SignAndEncrypt": ua.MessageSecurityMode.SignAndEncrypt,
}


def leer_argumentos(descripcion):
    """
    Opciones comunes a los dos clientes.

    Parametros:
        descripcion (str): texto de ayuda del programa.
    Retorna:
        argparse.Namespace
    """
    parser = argparse.ArgumentParser(description=descripcion)
    parser.add_argument("--seguridad", choices=MODOS_SEGURIDAD, default="None",
                        help="modo de seguridad, politica Basic256Sha256 (consigna 4.7)")
    parser.add_argument("--anonimo", action="store_true",
                        help="conectar sin usuario aunque haya credenciales (prueba 4.9)")
    parser.add_argument("--sin-escritura", action="store_true",
                        help="no escribir Cliente.Rampa (captura de KeepAlive, 3.4)")
    parser.add_argument("--gamma", action="store_true",
                        help="correccion gamma 2,2 en el LED PWM (3.7)")
    parser.add_argument("--url", default=comun.URL_SERVIDOR,
                        help="endpoint del servidor (por defecto la IP de eth0)")
    parser.add_argument("--pki", type=Path, default=comun.PKI_POR_DEFECTO,
                        help="carpeta de certificados (por defecto ./pki)")
    return parser.parse_args()


class EstadoCliente:
    """Valores locales y recibidos que comparten las tareas (C2..C6)."""

    def __init__(self):
        self.conectado = False
        self.rampa_local = 0
        self.pulsador_local = False
        self.rampa_remota = 0
        self.ts_rampa_remota = None
        self.pulsador_remoto = False


# =============================================================================
# BLOQUE C1 · Conexion: endpoint, seguridad y usuario
# =============================================================================

async def conectar(args):
    """
    Crea el cliente, aplica seguridad y usuario, y conecta.

    Parametros:
        args (argparse.Namespace): --url, --seguridad, --anonimo, --pki.
    Retorna:
        asyncua.Client: conectado (sesion activa).
    Excepciones:
        SystemExit: faltan certificados para Sign/SignAndEncrypt.
        ua.UaStatusCodeError, OSError, asyncio.TimeoutError: fallo de conexion.
    """
    client = Client(url=args.url, timeout=TIMEOUT_PEDIDO_S, watchdog_intervall=1.0)
    client.application_uri = comun.URI_CLIENTE    # = URI de su certificado
    client.session_timeout = TIMEOUT_SESION_MS

    # Descubrimiento: canal temporal en modo None -> GetEndpoints -> CLO.
    # asyncua no lo hace por su cuenta; asi el cliente comprueba que el
    # servidor ofrece el modo pedido antes de abrir la sesion, y la captura
    # muestra GetEndpoints (consigna 4.2).
    # Client.connect_and_get_server_endpoints() -> list[EndpointDescription]
    endpoints = await client.connect_and_get_server_endpoints()
    ofrecidos = {(e.SecurityMode, e.SecurityPolicyUri.split("#")[-1]) for e in endpoints}
    pedido = (MODOS_SEGURIDAD[args.seguridad],
              "None" if args.seguridad == "None" else "Basic256Sha256")
    if pedido not in ofrecidos:
        raise SystemExit(f"El servidor no ofrece {args.seguridad}: {sorted(ofrecidos)}")

    if args.seguridad != "None":
        archivos = {
            "certificate": args.pki / "own" / "cliente_cert.der",
            "private_key": args.pki / "own" / "cliente_key.pem",
            "server_certificate": args.pki / "servidor_cert.der",   # copiado de la RPi 1
        }
        for ruta in archivos.values():
            if not ruta.is_file():
                raise SystemExit(f"Falta {ruta} (README §5).")
        await client.set_security(SecurityPolicyBasic256Sha256,
                                  mode=MODOS_SEGURIDAD[args.seguridad],
                                  **{k: str(v) for k, v in archivos.items()})

    # [SEC] Credenciales desde el entorno, nunca en el codigo ni en git.
    usuario = os.environ.get("OPCUA_CLIENTE_USUARIO")
    clave = os.environ.get("OPCUA_CLIENTE_CLAVE")
    if usuario and clave and not args.anonimo:
        client.set_user(usuario)
        client.set_password(clave)
        identidad = f"usuario '{usuario}'"
    else:
        identidad = "anonimo (solo lectura: las escrituras seran rechazadas)"

    print(f"{ahora_iso()} [C1] Conectando a {args.url} | seguridad={args.seguridad} | {identidad}",
          flush=True)
    await client.connect()
    print(f"{ahora_iso()} [C1] Sesion activa", flush=True)
    return client


def nodos_del_modelo(client):
    """Retorna dict[str, asyncua.Node] con las cuatro variables."""
    return {
        "estado_servidor": client.get_node(comun.NODE_ESTADO_SERVIDOR),
        "rampa_servidor": client.get_node(comun.NODE_RAMPA_SERVIDOR),
        "estado_cliente": client.get_node(comun.NODE_ESTADO_CLIENTE),
        "rampa_cliente": client.get_node(comun.NODE_RAMPA_CLIENTE),
    }


# =============================================================================
# BLOQUE C2 · Rampa triangular local
# =============================================================================

async def tarea_rampa(estado):
    """
    Rampa triangular 0..65535 de 8 s, recalculada cada 50 ms (3.2).

    Corre durante TODO el programa, tambien sin conexion: en la prueba de
    desconexion (3.6) el generador local tiene que seguir.
    """
    inicio = time.monotonic()
    proximo = inicio
    while True:
        estado.rampa_local = comun.rampa_triangular(time.monotonic() - inicio)
        proximo = max(proximo + comun.PASO_RAMPA_S, time.monotonic())   # sin rafagas si se atrasa
        await asyncio.sleep(max(0.0, proximo - time.monotonic()))


# =============================================================================
# BLOQUE C4 · Replicacion de los datos recibidos en los LED
# =============================================================================

def replicar(estado, salidas, estado_servidor=None, rampa_servidor=None):
    """
    Lleva al LED digital y al LED PWM los valores recibidos del servidor.

    Sin datos nuevos no se toca nada: ante una desconexion los LED quedan
    congelados en el ultimo valor bueno (3.6).

    Parametros:
        estado (EstadoCliente), salidas (comun.Salidas).
        estado_servidor (ua.DataValue | None): Servidor.EstadoPulsador.
        rampa_servidor (ua.DataValue | None): Servidor.Rampa.
    """
    if estado_servidor is not None and estado_servidor.StatusCode.is_good():
        estado.pulsador_remoto = bool(estado_servidor.Value.Value)
        salidas.led_digital(estado.pulsador_remoto)
    if rampa_servidor is not None and rampa_servidor.StatusCode.is_good():
        estado.rampa_remota = int(rampa_servidor.Value.Value)
        estado.ts_rampa_remota = rampa_servidor.SourceTimestamp
        salidas.led_pwm(estado.rampa_remota)


# =============================================================================
# BLOQUE C5 · Escrituras
# =============================================================================

def dato(valor, tipo):
    """
    DataValue con SourceTimestamp = ahora: la marca indica cuando se genero
    el dato en ESTA placa, que es su significado en OPC UA.
    """
    return ua.DataValue(ua.Variant(valor, tipo), SourceTimestamp=comun.ahora_utc())


class Escritor:
    """
    Escribe una variable e informa el StatusCode cuando la escritura es
    rechazada (p. ej. BadUserAccessDenied si la sesion es anonima).

    Un rechazo es una RESPUESTA del servidor: el canal sigue vivo y la sesion
    no se corta. Se informa solo cuando el resultado cambia, para no repetir
    la misma linea cada 100 ms. Los errores de transporte si se propagan (C7).
    """

    def __init__(self, nodo, nombre):
        self._nodo = nodo
        self._nombre = nombre
        self._ultimo_error = None

    async def escribir(self, valor, tipo):
        try:
            await self._nodo.write_value(dato(valor, tipo))
            if self._ultimo_error is not None:
                print(f"{ahora_iso()} [C5] Write {self._nombre}: Good", flush=True)
            self._ultimo_error = None
        except ua.UaStatusCodeError as exc:
            if exc.code != self._ultimo_error:
                print(f"{ahora_iso()} [C5] Write {self._nombre} rechazado: "
                      f"StatusCode={ua.StatusCode(exc.code).name} (0x{exc.code:08X})", flush=True)
            self._ultimo_error = exc.code


async def tarea_escribir_pulsador(nodo, pulsador, estado):
    """Cliente.EstadoPulsador al conectar y en cada cambio (3.3)."""
    escritor = Escritor(nodo, "Cliente.EstadoPulsador")
    while True:
        estado.pulsador_local = pulsador.presionado
        await escritor.escribir(estado.pulsador_local, ua.VariantType.Boolean)
        await pulsador.cambio.wait()
        pulsador.cambio.clear()


async def tarea_escribir_rampa(nodo, estado):
    """Cliente.Rampa cada 100 ms sobre tiempos absolutos (3.3)."""
    escritor = Escritor(nodo, "Cliente.Rampa")
    proximo = time.monotonic()
    while True:
        await escritor.escribir(estado.rampa_local, ua.VariantType.UInt16)
        proximo = max(proximo + INTERVALO_ESCRITURA_S, time.monotonic())
        await asyncio.sleep(max(0.0, proximo - time.monotonic()))


# =============================================================================
# BLOQUE C6 · Registro en consola
# =============================================================================

async def tarea_consola(estado, salidas):
    """Cada 0,5 s: rampa generada, rampa recibida y su SourceTimestamp (3.5)."""
    while True:
        enlace = "" if estado.conectado else " | SIN CONEXION (LED congelados)"
        print(f"{ahora_iso()} [C6] generada={estado.rampa_local:5d} | "
              f"recibida Servidor.Rampa={estado.rampa_remota:5d} (PWM {salidas.duty:3d}/255) "
              f"SourceTimestamp={formatear_ts(estado.ts_rampa_remota)} | "
              f"pulsador local={int(estado.pulsador_local)} remoto={int(estado.pulsador_remoto)}"
              f"{enlace}", flush=True)
        await asyncio.sleep(comun.INTERVALO_LOG_S)


# =============================================================================
# BLOQUE C7 · Sesion y reconexion ante perdida del canal
# =============================================================================

async def correr_hasta_falla(*corrutinas):
    """
    Corre las tareas de la sesion; si una falla, cancela las demas y propaga
    la excepcion original (no un ExceptionGroup), para que C7 la clasifique.
    """
    tareas = [asyncio.ensure_future(c) for c in corrutinas]   # acepta tambien un Future
    try:
        hechas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_EXCEPTION)
        for tarea in hechas:
            tarea.result()
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)


async def ejecutar_sesion(args, estado, pulsador, salidas, lectura):
    """
    Una sesion completa: C1, luego C3 (lectura), C5 (escrituras) y el aviso
    de perdida del canal, en paralelo, hasta que algo falle.

    Parametros:
        lectura (Callable[[Client, dict, EstadoCliente, Salidas], Coroutine]):
            el bloque C3 del cliente (Modo A o Modo B).
    """
    client = await conectar(args)
    perdida = asyncio.get_running_loop().create_future()

    async def al_perder_canal(exc):
        # asyncua sondea ServerState cada 1 s (watchdog): si no responde,
        # avisa aqui aunque no haya ningun pedido nuestro en curso.
        if not perdida.done():
            perdida.set_exception(exc)

    client.connection_lost_callback = al_perder_canal
    estado.conectado = True
    nodos = nodos_del_modelo(client)
    tareas = [
        perdida,
        lectura(client, nodos, estado, salidas),
        tarea_escribir_pulsador(nodos["estado_cliente"], pulsador, estado),
    ]
    if not args.sin_escritura:
        tareas.append(tarea_escribir_rampa(nodos["rampa_cliente"], estado))
    try:
        await correr_hasta_falla(*tareas)
    finally:
        estado.conectado = False
        try:
            await client.disconnect()      # CloseSession + CLO si el canal sigue vivo
        except Exception:                  # con el cable cortado tambien falla:
            pass                           # no debe tapar la excepcion original
        print(f"{ahora_iso()} [C7] Cliente desconectado.", flush=True)


async def main(args, lectura):
    """
    Bucle de reconexion. Cada reconexion abre un canal y una sesion NUEVOS;
    la sesion vieja queda en el servidor hasta su timeout (60 s).

    Parametros:
        args (argparse.Namespace), lectura: bloque C3 (ver ejecutar_sesion).
    """
    comun.configurar_registro()
    estado = EstadoCliente()
    salidas = comun.Salidas(gamma=args.gamma)
    pulsador = comun.Pulsador(asyncio.get_running_loop())
    fondo = [asyncio.create_task(tarea_rampa(estado)),
             asyncio.create_task(tarea_consola(estado, salidas))]
    try:
        while True:
            try:
                await ejecutar_sesion(args, estado, pulsador, salidas, lectura)
            except asyncio.CancelledError:
                raise
            except ua.UaStatusCodeError as exc:
                # El SERVIDOR respondio con un error OPC UA.
                print(f"{ahora_iso()} [C7] StatusCode={ua.StatusCode(exc.code).name} "
                      f"(0x{exc.code:08X})", flush=True)
            except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
                # No hubo respuesta: con el cable cortado no llega ningun
                # StatusCode; vence el timeout del pedido o del watchdog.
                print(f"{ahora_iso()} [C7] TRANSPORTE {type(exc).__name__}: "
                      f"sin respuesta del servidor {exc}", flush=True)
            print(f"{ahora_iso()} [C7] Reintentando en {INTERVALO_RECONEXION_S:.0f} s...", flush=True)
            await asyncio.sleep(INTERVALO_RECONEXION_S)
    finally:
        for tarea in fondo:
            tarea.cancel()
        pulsador.cerrar()
        salidas.cerrar()
