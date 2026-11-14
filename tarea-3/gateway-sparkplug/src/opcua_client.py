"""
opcua_client.py
Autores: Peralta Agustina (version original, T2), Bevilacqua Francisco (correccion T2 y adaptacion T3)
Fecha de creacion: 2026-10-20 (T2) · adaptado 2026-11-12 (T3)
Version: 3.0

Descripcion general
-------------------
Cliente OPC UA del dispositivo 3 (consigna T3 §2: "Utilizar el OPC client creado en TP Nº2").
Parte de tarea-2/versiones/v2-correccion-python/{cliente_base.py, cliente_suscripcion.py}
(ADR-013, docs/analisis-t2.md §2.5). Bloque [DF-3.2] de docs/diagramas/flujo-edge-node.mmd;
los bloques C1, C3, C5 y C7 conservan el nombre que tenian en la T2.

Que se reutilizo y que cambio
-----------------------------
| Pieza (T2 v2)                          | En la T3      | Motivo                                              |
|----------------------------------------|---------------|-----------------------------------------------------|
| C1 conectar(): GetEndpoints explicito,  | REUTILIZADO   | Independiente del modelo. Se agrego la verificacion |
|   set_security, usuario por entorno     | + 1 control   | de la huella del servidor (abajo, "Seguridad")      |
| C3 Modo B: CreateSubscription + UN      | ADAPTADO      | De 2 NodeIds fijos a todos los del diccionario      |
|   CreateMonitoredItems, parametros      |               | (metrics.py); cada cambio sale con su               |
|   100/100/1, KeepAlive 10, Lifetime 300 |               | SourceTimestamp hacia el Edge Node                  |
| C5 Escritor: write_value con            | ADAPTADO      | Devuelve el StatusCode en vez de imprimirlo: el     |
|   DataValue; rechazo != error de canal  |               | Edge Node lo registra junto al DCMD que lo causo    |
| correr_hasta_falla()                    | REUTILIZADO   | Generico                                            |
| C7 bucle de reconexion, clasificacion   | ADAPTADO      | Reintento fijo 2 s -> retroceso exponencial 1-30 s  |
|   UaStatusCodeError / transporte        |               | (abajo); informa Status/OPCUA/Estado DONE / ERROR   |
| nodos_del_modelo()                      | REESCRITO     | Los NodeIds salen del diccionario, no del codigo    |
| C2 rampa, C4 LED, C6 consola, GPIO      | DESCARTADO    | El dispositivo 3 es una PC: no tiene GPIO           |
| cliente.py (Modo A, Read cada 100 ms)   | CONSERVADO    | --modo lectura: para comparar en la defensa (ADR-004)|

Parametros de la suscripcion (heredados de la T2 v2, cliente_suscripcion.py:32-41)
------------------------------------------------------------------------------------
    PublishingInterval 100 ms  el servidor junta los cambios y responde un PublishRequest cada
                               100 ms como maximo: es el PEOR CASO de latencia de esta capa.
    SamplingInterval   100 ms  cada cuanto el servidor muestrea cada variable. Igual al de
                               publicacion: muestrear mas rapido llenaria una cola de 1 sin uso.
    QueueSize          1       solo interesa el ultimo valor (report by exception). Un contador
                               que salta 2 veces en 100 ms pierde el intermedio: aceptable,
                               porque el siguiente valor ya lo incluye (es acumulativo).
    MaxKeepAliveCount  10      sin cambios, PublishResponse vacio cada 10 x 100 ms = 1 s.
    LifetimeCount      300     30 s sin PublishRequest -> el servidor borra la suscripcion
                               (IEC 62541-4 exige Lifetime >= 3 x KeepAlive).

Reconexion (C7) con retroceso exponencial
-----------------------------------------
Espera = min(1 s x 2^(intento-1), 30 s): 1, 2, 4, 8, 16, 30, 30... Vuelve a 1 s despues de una
sesion que llego a suscribirse. Frente al reintento fijo de 2 s de la T2: reconecta mas rapido
ante un corte breve (1 s) y no satura al dispositivo 2 si esta caido mucho tiempo (un intento
cada 30 s abre canal + sesion: HEL, OPN, CreateSession, ActivateSession). Sin jitter: hay UN
solo cliente por servidor, no existe el problema de reconexiones sincronizadas de muchos clientes.

Seguridad (ADR-009, docs/seguridad-opcua.md)
--------------------------------------------
- Por defecto SignAndEncrypt + Basic256Sha256 con usuario; contrasena desde el entorno
  (OPCUA_CLIENTE_CLAVE), nunca en el codigo ni en los argumentos.
- El certificado del SERVIDOR se toma de un archivo copiado del dispositivo 2 (no se confia en
  el que llega por la red) y se compara con el del GetEndpoints: si difieren, NO se conecta
  (un servidor impostor en la LAN no puede hacerse pasar por el dispositivo 2).
- El certificado propio se genera la primera vez; el servidor lo rechaza hasta que se lo confia
  en el panel de Node-RED (seguridad-opcua.md §4) comparando la huella que se imprime aca.

Dependencias externas: asyncua 2.1.0 (+ cryptography 50.0.2).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

from metrics import ConjuntoMetricas

_log = logging.getLogger("opcua")

TIMEOUT_PEDIDO_S = 4.0          # cada pedido espera respuesta 4 s (T2)
WATCHDOG_S = 1.0                # asyncua lee ServerState cada 1 s (T2: detecta el cable cortado)
TIMEOUT_SESION_MS = 60_000      # la sesion abandonada se libera en el servidor a los 60 s (T2)
PUBLISHING_INTERVAL_MS = 100
SAMPLING_INTERVAL_MS = 100
QUEUE_SIZE = 1
MAX_KEEPALIVE_COUNT = 10
LIFETIME_COUNT = 300
RETROCESO_INICIAL_S = 1.0
RETROCESO_MAXIMO_S = 30.0

URI_APLICACION = "urn:unraf:pdci:t3:gateway"    # debe coincidir con la URI de su certificado

MODOS_SEGURIDAD = {
    "None": ua.MessageSecurityMode.None_,
    "Sign": ua.MessageSecurityMode.Sign,
    "SignAndEncrypt": ua.MessageSecurityMode.SignAndEncrypt,
}

# Tipos del diccionario -> VariantType del Write (node-opcua rechaza otro tipo: BadTypeMismatch).
TIPOS_VARIANT = {"Boolean": ua.VariantType.Boolean, "UInt16": ua.VariantType.UInt16,
                 "UInt32": ua.VariantType.UInt32, "Float": ua.VariantType.Float,
                 "String": ua.VariantType.String, "Int64": ua.VariantType.Int64}


def espera_reintento(intento: int) -> float:
    """
    Retroceso exponencial con tope.

    Parametros:
        intento (int): 1 para el primer reintento.
    Retorna:
        float: segundos a esperar = min(1 x 2^(intento-1), 30).
    """
    return min(RETROCESO_INICIAL_S * 2 ** max(0, intento - 1), RETROCESO_MAXIMO_S)


def huella_sha1(der: bytes) -> str:
    """Huella SHA-1 en hexadecimal: la que muestra el panel de Node-RED y UaExpert."""
    return hashlib.sha1(der).hexdigest()


@dataclass(frozen=True)
class ConfigOpcua:
    """
    Configuracion del cliente.

    Atributos:
        url (str): opc.tcp://<IP literal del dispositivo 2>:4840 (nunca un nombre de host, T2).
        seguridad (str): None | Sign | SignAndEncrypt.
        pki (Path): carpeta con own/cliente_cert.der, own/cliente_key.pem y servidor_cert.(pem|der).
        usuario, clave (str | None): de OPCUA_CLIENTE_USUARIO / OPCUA_CLIENTE_CLAVE.
        modo (str): 'suscripcion' (ADR-004) o 'lectura' (Modo A de la T2, para comparar).
    """

    url: str
    seguridad: str = "SignAndEncrypt"
    pki: Path = Path("pki")
    usuario: str | None = None
    clave: str | None = None
    modo: str = "suscripcion"

    @classmethod
    def desde_entorno(cls, **extra) -> "ConfigOpcua":
        """Lee OPCUA_URL, OPCUA_SEGURIDAD, OPCUA_PKI, OPCUA_CLIENTE_USUARIO y OPCUA_CLIENTE_CLAVE."""
        valores = {"url": os.environ.get("OPCUA_URL", "opc.tcp://192.168.10.1:4840"),
                   "seguridad": os.environ.get("OPCUA_SEGURIDAD", "SignAndEncrypt"),
                   "pki": Path(os.environ.get("OPCUA_PKI") or Path(__file__).resolve().parents[1] / "pki"),
                   "usuario": os.environ.get("OPCUA_CLIENTE_USUARIO") or None,
                   "clave": os.environ.get("OPCUA_CLIENTE_CLAVE") or None}
        valores.update({k: v for k, v in extra.items() if v is not None})
        if valores["seguridad"] not in MODOS_SEGURIDAD:
            raise ValueError(f"OPCUA_SEGURIDAD invalida: {valores['seguridad']}")
        return cls(**valores)


# =============================================================================
# BLOQUE C1 · Conexion: endpoint, seguridad y usuario (T2, reutilizado)
# =============================================================================

async def conectar(cfg: ConfigOpcua) -> Client:
    """
    Crea el cliente, aplica seguridad y usuario, y conecta.

    Parametros:
        cfg (ConfigOpcua)
    Retorna:
        asyncua.Client con la sesion activa.
    Excepciones:
        PermissionError: faltan certificados o el del servidor no coincide con el confiado.
        ua.UaStatusCodeError, OSError, asyncio.TimeoutError: fallo de conexion.
    """
    client = Client(url=cfg.url, timeout=TIMEOUT_PEDIDO_S, watchdog_intervall=WATCHDOG_S)
    client.application_uri = URI_APLICACION
    client.session_timeout = TIMEOUT_SESION_MS

    # Descubrimiento: canal temporal None -> GetEndpoints -> CLO (T2: comprueba que el servidor
    # ofrece el modo pedido ANTES de abrir la sesion, y deja el GetEndpoints en la captura).
    # Client.connect_and_get_server_endpoints() -> list[EndpointDescription]
    endpoints = await client.connect_and_get_server_endpoints()
    politica = "None" if cfg.seguridad == "None" else "Basic256Sha256"
    elegido = next((e for e in endpoints if e.SecurityMode == MODOS_SEGURIDAD[cfg.seguridad]
                    and e.SecurityPolicyUri.split("#")[-1] == politica), None)
    if elegido is None:
        ofrecidos = sorted({(e.SecurityMode.name, e.SecurityPolicyUri.split('#')[-1]) for e in endpoints})
        raise PermissionError(f"el servidor no ofrece {cfg.seguridad}: {ofrecidos}")

    if cfg.seguridad != "None":
        propio_cert = cfg.pki / "own" / "cliente_cert.der"
        propio_clave = cfg.pki / "own" / "cliente_key.pem"
        # Client.setup_self_signed_certificate(key_file, cert_file, subject_attrs) -> (cert, key)
        # Genera RSA 2048 / SHA-256 / 365 dias solo si falta o no es valido (asyncua 2.1.0).
        await client.setup_self_signed_certificate(
            propio_clave, propio_cert,
            subject_attrs={"organizationName": "UNRaf PdCI T3", "countryName": "AR"})
        try:
            os.chmod(propio_clave, 0o600)
        except OSError:
            pass
        servidor = next((cfg.pki / n for n in ("servidor_cert.der", "servidor_cert.pem")
                         if (cfg.pki / n).is_file()), None)
        if servidor is None:
            raise PermissionError(f"falta {cfg.pki / 'servidor_cert.pem'}: copiarlo del dispositivo 2 "
                                  "(tools/traer_certificado_servidor.py, README §5)")
        confiado = await _der(servidor)
        recibido = bytes(elegido.ServerCertificate or b"")
        if huella_sha1(confiado) != huella_sha1(recibido):
            raise PermissionError(f"el certificado del servidor ({huella_sha1(recibido)}) NO es el confiado "
                                  f"({huella_sha1(confiado)}): posible impostor; no se conecta")
        _log.info("[C1] certificado propio %s (huella %s): confiarlo en el panel de Node-RED",
                  propio_cert, huella_sha1(propio_cert.read_bytes()))
        await client.set_security(SecurityPolicyBasic256Sha256, certificate=str(propio_cert),
                                  private_key=str(propio_clave), server_certificate=str(servidor),
                                  mode=MODOS_SEGURIDAD[cfg.seguridad])

    # [SEC] Credenciales desde el entorno, nunca en el codigo ni en git.
    if cfg.usuario and cfg.clave:
        client.set_user(cfg.usuario)
        client.set_password(cfg.clave)
        identidad = f"usuario '{cfg.usuario}'"
    else:
        identidad = "anonimo (solo lectura: los DCMD seran rechazados por el servidor)"
    _log.info("[C1] conectando a %s | seguridad=%s | %s", cfg.url, cfg.seguridad, identidad)
    await client.connect()
    _log.info("[C1] sesion activa")
    return client


async def _der(ruta: Path) -> bytes:
    """Certificado en DER desde un .der o un .pem."""
    from asyncua.crypto import uacrypto
    from cryptography.hazmat.primitives.serialization import Encoding
    cert = await uacrypto.load_certificate(ruta, ruta.suffix.lstrip("."))
    return cert.public_bytes(Encoding.DER)


# =============================================================================
# BLOQUE C3 · Lectura: suscripcion (Modo B) o lectura ciclica (Modo A)
# =============================================================================

AlDato = Callable[[str, Any, int, bool], None]


def _ms(ts: dt.datetime | None) -> int:
    """SourceTimestamp -> ms UTC (el timestamp de la metrica Sparkplug)."""
    if ts is None:
        return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return int(ts.timestamp() * 1000)


class ManejadorSuscripcion:
    """
    Recibe las notificaciones de la suscripcion y las entrega al Edge Node por NOMBRE de
    metrica (la traduccion NodeId -> nombre la da el diccionario: I-06).
    """

    def __init__(self, nombres_por_nodo: dict[str, str], al_dato: AlDato, perdida: asyncio.Future):
        self._nombres = nombres_por_nodo
        self._al_dato = al_dato
        self._perdida = perdida

    def datachange_notification(self, node, val, data):
        """
        Parametros:
            node (asyncua.Node), val (Any), data (DataChangeNotif): data.monitored_item.Value es el
                DataValue completo, con StatusCode y SourceTimestamp.
        """
        dv = data.monitored_item.Value
        nombre = self._nombres.get(node.nodeid.to_string())
        if nombre is not None:
            self._al_dato(nombre, val, _ms(dv.SourceTimestamp), dv.StatusCode.is_good())

    def status_change_notification(self, status):
        """BadTimeout (el servidor borro la suscripcion) o BadShutdown: se trata como perdida."""
        codigo = status.Status if hasattr(status, "Status") else status
        nombre = ua.StatusCode(codigo.value).name
        _log.warning("[C3] estado de la suscripcion: %s", nombre)
        if not ua.StatusCode(codigo.value).is_good() and not self._perdida.done():
            self._perdida.set_exception(ConnectionError(f"suscripcion: {nombre}"))


async def leer_por_suscripcion(client: Client, nodos: dict[str, str], al_dato: AlDato,
                               perdida: asyncio.Future, al_listo: Callable[[], None]) -> None:
    """
    CreateSubscription + UN CreateMonitoredItems con todos los NodeIds del diccionario.
    No hace falta un Read inicial: el servidor manda SIEMPRE la notificacion inicial de cada item.
    """
    parametros = ua.CreateSubscriptionParameters(
        RequestedPublishingInterval=PUBLISHING_INTERVAL_MS, RequestedLifetimeCount=LIFETIME_COUNT,
        RequestedMaxKeepAliveCount=MAX_KEEPALIVE_COUNT, MaxNotificationsPerPublish=0,
        PublishingEnabled=True, Priority=0)
    # Client.create_subscription(params, handler) -> Subscription
    suscripcion = await client.create_subscription(parametros, ManejadorSuscripcion(nodos, al_dato, perdida))
    revisados = suscripcion.parameters
    # Subscription.subscribe_data_change(nodes, sampling_interval: float, queuesize: int) -> list[int]
    handles = await suscripcion.subscribe_data_change(
        [client.get_node(n) for n in nodos], sampling_interval=SAMPLING_INTERVAL_MS, queuesize=QUEUE_SIZE)
    errores = [h for h in handles if isinstance(h, ua.StatusCode)]
    if errores:
        raise ConnectionError(f"CreateMonitoredItems rechazo {len(errores)} item(s): {errores[0].name}")
    _log.info("[C3] suscripcion: PublishingInterval=%s ms MaxKeepAlive=%s Lifetime=%s | %d items, "
              "SamplingInterval=%s ms QueueSize=%s", revisados.RequestedPublishingInterval,
              revisados.RequestedMaxKeepAliveCount, revisados.RequestedLifetimeCount, len(handles),
              SAMPLING_INTERVAL_MS, QUEUE_SIZE)
    al_listo()
    await asyncio.Event().wait()        # las notificaciones llegan por el manejador


async def leer_ciclico(client: Client, nodos: dict[str, str], al_dato: AlDato,
                       perdida: asyncio.Future, al_listo: Callable[[], None]) -> None:
    """Modo A de la T2 (ADR-004): un ReadRequest con todos los nodos cada 100 ms. Solo para comparar."""
    lista = [client.get_node(n) for n in nodos]
    nombres = list(nodos.values())
    al_listo()
    while True:
        # Client.read_attributes(nodes, attr) -> list[DataValue]: UN ReadRequest
        valores = await client.read_attributes(lista, ua.AttributeIds.Value)
        for nombre, dv in zip(nombres, valores):
            al_dato(nombre, dv.Value.Value if dv.Value else None, _ms(dv.SourceTimestamp), dv.StatusCode.is_good())
        await asyncio.sleep(PUBLISHING_INTERVAL_MS / 1000)


# =============================================================================
# BLOQUE C5 · Escrituras (camino DCMD -> Write -> FC 05/06)
# =============================================================================

class Escritor:
    """
    Escribe una variable y devuelve el StatusCode. Un rechazo (BadUserAccessDenied,
    BadOutOfRange, BadCommunicationError del esclavo...) es una RESPUESTA: el canal sigue vivo y la
    sesion no se corta. Los errores de transporte se propagan (C7).
    """

    def __init__(self, client: Client):
        self._client = client

    async def escribir(self, node_id: str, tipo: str, valor: Any) -> str:
        """
        Parametros:
            node_id (str), tipo (str): del diccionario; valor (Any): ya validado por el Edge Node.
        Retorna:
            str: nombre del StatusCode ('Good' solo si el esclavo confirmo, ADR-015).
        """
        dato = ua.DataValue(ua.Variant(valor, TIPOS_VARIANT[tipo]))
        try:
            # Node.write_value(DataValue) -> None; lanza UaStatusCodeError si el WriteResponse es Bad
            await self._client.get_node(node_id).write_value(dato)
            return "Good"
        except ua.UaStatusCodeError as exc:
            return ua.StatusCode(exc.code).name


# =============================================================================
# BLOQUE C7 · Sesion y reconexion
# =============================================================================

async def correr_hasta_falla(*corrutinas):
    """(T2, reutilizado) Si una tarea falla, cancela las demas y propaga la excepcion original."""
    tareas = [asyncio.ensure_future(c) for c in corrutinas]
    try:
        hechas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_EXCEPTION)
        for tarea in hechas:
            tarea.result()
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)


class ClienteOpcua:
    """
    Cliente OPC UA con reconexion propia (C7).

    Atributos:
        conectado (bool): sesion activa Y suscripcion creada.
        sesiones (int): sesiones establecidas desde el arranque.
    Relaciones:
        Entrega datos con al_dato(nombre, valor, ts_ms, bueno) y el estado de la capa con
        al_estado(ok) -> Status/OPCUA/Estado DONE / ERROR en el Edge Node.
    """

    def __init__(self, cfg: ConfigOpcua, metricas: ConjuntoMetricas, al_dato: AlDato,
                 al_estado: Callable[[bool], None], dormir: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._cfg = cfg
        self._nodos = {m.node_id: m.nombre for m in metricas.suscriptas()}
        self._al_dato = al_dato
        self._al_estado = al_estado
        self._dormir = dormir
        self._client: Client | None = None
        self.conectado = False
        self.sesiones = 0

    def _informar(self, ok: bool) -> None:
        if ok != self.conectado:
            self.conectado = ok
            self._al_estado(ok)

    async def escribir(self, node_id: str, tipo: str, valor: Any) -> str:
        """Write sobre la sesion vigente. Sin sesion: 'BadNotConnected' (no se encola: ADR-015)."""
        if self._client is None or not self.conectado:
            return "BadNotConnected"
        try:
            return await Escritor(self._client).escribir(node_id, tipo, valor)
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            return f"BadCommunicationError ({type(exc).__name__})"

    async def _sesion(self) -> None:
        """Una sesion: C1, C3 y el aviso de perdida del canal, hasta que algo falle."""
        client = await conectar(self._cfg)
        perdida = asyncio.get_running_loop().create_future()

        async def al_perder_canal(exc):
            # asyncua sondea ServerState cada 1 s (watchdog): avisa aunque no haya pedidos en curso.
            if not perdida.done():
                perdida.set_exception(exc)

        client.connection_lost_callback = al_perder_canal
        self._client = client
        lectura = leer_por_suscripcion if self._cfg.modo == "suscripcion" else leer_ciclico

        def listo():
            self.sesiones += 1
            self._informar(True)

        try:
            await correr_hasta_falla(perdida, lectura(client, self._nodos, self._al_dato, perdida, listo))
        finally:
            self._informar(False)
            self._client = None
            try:
                await client.disconnect()        # CloseSession + CLO si el canal sigue vivo
            except Exception:                    # con el cable cortado tambien falla:
                pass                             # no debe tapar la excepcion original

    async def ejecutar(self) -> None:
        """Bucle de reconexion con retroceso exponencial (nunca termina salvo cancelacion)."""
        intento = 0
        while True:
            sesiones_antes = self.sesiones
            try:
                await self._sesion()
            except asyncio.CancelledError:
                raise
            except PermissionError as exc:
                _log.error("[C7] %s", exc)              # configuracion: reintentar no lo arregla solo,
            except ua.UaStatusCodeError as exc:         # pero tampoco se aborta (se corrige en caliente)
                _log.warning("[C7] el servidor respondio %s (0x%08X)", ua.StatusCode(exc.code).name, exc.code)
            except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
                _log.warning("[C7] TRANSPORTE %s: %s", type(exc).__name__, exc)
            except Exception as exc:                    # asyncua lanza otros tipos ante un servidor raro
                _log.exception("[C7] error inesperado: %s", exc)
            intento = 1 if self.sesiones > sesiones_antes else intento + 1
            espera = espera_reintento(intento)
            _log.info("[C7] reintento %d en %.0f s", intento, espera)
            await self._dormir(espera)
