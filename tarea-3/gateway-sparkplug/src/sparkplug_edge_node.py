#!/usr/bin/env python3
"""
sparkplug_edge_node.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Dispositivo 3: cliente OPC UA (opcua_client.py) + Edge Node Sparkplug B 3.0 hacia un broker MQTT
en la nube (I-03). Este archivo solo hace E/S: la logica del ciclo de vida esta en ciclo_vida.py
(maquina de estados pura, probada sin red). Diagrama: docs/diagramas/flujo-edge-node.mmd.

    [DF-3.1]  main(): .env, diccionario, bdSeq persistido, Status/OPCUA/Estado = ERROR
    [DF-3.2]  ClienteOpcua en segundo plano
    [DF-3.3]  NDEATH registrado como Last Will ANTES de conectar, con el bdSeq de ESA conexion
    [DF-3.4]  CONNECT con TLS, usuario y contrasena, clean session, keepalive 10 s
    [DF-3.5]  SUBSCRIBE NCMD, DCMD y STATE (QoS 1) y espera del SUBACK antes del NBIRTH
    [DF-3.9]  bucle de eventos (MQTT, OPC UA, tick de NDATA)
    [DF-3.15] DCMD valido -> OPC UA Write -> (dispositivo 2) FC 05/06 -> el LED
    [DF-3.17] perdida de MQTT: cliente NUEVO (otro Will, bdSeq + 1), retroceso 1-30 s

Por que un cliente paho por conexion: el Will viaja en el CONNECT. Con la reconexion automatica
de paho el Will seria el de la PRIMERA conexion (bdSeq viejo) y el NDEATH no coincidiria con el
NBIRTH nuevo (viola tck-id-payloads-nbirth-bdseq-repeat).

Hilos: paho corre su red en un hilo propio (loop_start); sus callbacks NO tocan el estado: ponen
un evento en una asyncio.Queue con call_soon_threadsafe, y todo el estado se modifica en el event
loop (un solo hilo, sin carreras). publish() de paho es seguro entre hilos.

Registro (consigna F5.6): cada mensaje publicado y recibido va a <logs>/edge-node-<fecha>.jsonl,
una linea JSON con topico, tipo, seq, bdSeq y metricas (nombre, alias, tipo, valor). Es la
evidencia del anexo del informe.

Uso (en gateway-sparkplug/, con el .env completo; ver README):
    python src/sparkplug_edge_node.py
    python src/sparkplug_edge_node.py --env ../.env --mqtt-ca .dev-broker/ca.pem   (desarrollo)

Dependencias externas: paho-mqtt 2.1.0, asyncua 2.1.0, protobuf 7.36.2.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import ipaddress
import json
import logging
import os
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent))   # permite "python src/sparkplug_edge_node.py"

import sparkplug as spb                                   # noqa: E402
from ciclo_vida import AlmacenBdSeq, Escritura, Mensaje, NucleoEdgeNode   # noqa: E402
from metrics import DICCIONARIO_POR_DEFECTO, cargar_metricas    # noqa: E402
from opcua_client import ClienteOpcua, ConfigOpcua, espera_reintento    # noqa: E402

_log = logging.getLogger("edge")
RAIZ = Path(__file__).resolve().parents[1]
#: Keepalive MQTT: el broker publica el Will 1,5 x 10 s = 15 s despues de un corte SILENCIOSO
#: (cable). Un kill del proceso cierra el socket y el Will sale al instante. PINGREQ = 2 bytes.
KEEPALIVE_S = 10
TIMEOUT_CONNACK_S = 15
PERIODO_TICK_S = 0.2


# =============================================================================
# Configuracion
# =============================================================================

def cargar_env(ruta: Path) -> None:
    """
    Carga un .env (CLAVE=valor por linea) SIN pisar variables ya definidas en el entorno.
    No interpreta comillas ni sustituciones: es intencionalmente minimo (sin dependencia nueva).
    """
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


def _es_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class ConfigMqtt:
    """
    Atributos:
        host, puerto: broker (en la demo, el de la nube por TLS 8883).
        usuario, clave: del usuario edge_node (ADR-005), desde MQTT_USUARIO_EDGE / MQTT_CLAVE_EDGE.
        ca (Path | None): CA a confiar; None = las del sistema (alcanza para un broker con
            certificado publico). tls (bool): False SOLO contra loopback (pruebas).
        id_cliente (str): estable entre reinicios: el broker desaloja la sesion vieja con el mismo id.
    """

    host: str
    puerto: int
    usuario: str
    clave: str
    id_cliente: str
    ca: Path | None = None
    tls: bool = True

    def __post_init__(self):
        if not self.tls and not _es_loopback(self.host):
            # [SEC] Sin TLS la contrasena y los comandos viajarian en claro por internet.
            raise ValueError("MQTT sin TLS solo se admite contra 127.0.0.1 (pruebas)")
        if not self.usuario or not self.clave:
            raise ValueError("faltan MQTT_USUARIO_EDGE / MQTT_CLAVE_EDGE")


# =============================================================================
# Registro de mensajes (evidencia, JSON por linea)
# =============================================================================

class RegistroMensajes:
    """
    Escribe una linea JSON por mensaje Sparkplug publicado ('tx') o recibido ('rx').

    Atributos:
        ruta (Path | None): archivo .jsonl; None = solo memoria (pruebas).
        lineas (list[dict]): las ultimas 1000, para las pruebas y el diagnostico.
    """

    def __init__(self, ruta: Path | None, metricas):
        self.ruta = ruta
        self._metricas = metricas
        self.lineas: list[dict[str, Any]] = []
        if ruta:
            ruta.parent.mkdir(parents=True, exist_ok=True)

    def _resolver(self, alias: int):
        m = self._metricas.por_alias(alias)
        return (m.nombre, m.tipo) if m else None

    def anotar(self, direccion: str, topico: str, payload: bytes, *, tipo: str | None = None,
               qos: int | None = None, retenido: bool = False, bd_seq: int | None = None, **extra) -> dict:
        """Agrega una linea y la devuelve."""
        linea: dict[str, Any] = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
                                 "dir": direccion, "topico": topico, "tipo": tipo, "qos": qos, "retenido": retenido}
        if tipo == "STATE":
            linea["state"] = spb.leer_state(payload)
        else:
            try:
                d = spb.describir(payload, self._resolver)
                linea.update(seq=d["seq"], timestamp=d["timestamp"], metricas=d["metricas"])
                bd = next((m["valor"] for m in d["metricas"] if m["nombre"] == "bdSeq"), None)
                linea["bdSeq"] = bd if bd is not None else bd_seq
            except ValueError as exc:
                linea["error"] = str(exc)
        linea.update(extra)
        self.lineas = (self.lineas + [linea])[-1000:]
        if self.ruta:
            with self.ruta.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
        return linea


# =============================================================================
# Edge Node (E/S)
# =============================================================================

class EdgeNode:
    """
    Conecta el nucleo (ciclo_vida.NucleoEdgeNode) con MQTT y con OPC UA.

    Relaciones:
        nucleo: decide QUE publicar. opcua: fuente de datos y destino de las escrituras
        (ClienteOpcua o un sustituto con escribir() y ejecutar(), en las pruebas).
    """

    def __init__(self, nucleo: NucleoEdgeNode, cfg: ConfigMqtt, registro: RegistroMensajes, opcua=None):
        self.nucleo = nucleo
        self.cfg = cfg
        self.registro = registro
        self.opcua = opcua
        self._cliente: mqtt.Client | None = None
        self._cola: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.conexiones = 0
        self._vaciado_programado = False

    # ------------------------------------------------------------------ eventos de OPC UA
    def al_dato(self, nombre: str, valor: Any, ts: int, bueno: bool) -> None:
        """
        Callback del cliente OPC UA (corre en el event loop). asyncua entrega las notificaciones
        de un mismo PublishResponse una tras otra, sin ceder el loop: el DDATA se arma con
        call_soon, despues de la ultima, y lleva todos los cambios juntos (ADR-021).
        """
        self._publicar(self.nucleo.al_dato(nombre, valor, ts, bueno, diferir=True))
        if not self._vaciado_programado:
            self._vaciado_programado = True
            asyncio.get_running_loop().call_soon(self._vaciar_ddata)

    def _vaciar_ddata(self) -> None:
        self._vaciado_programado = False
        self._publicar(self.nucleo.vaciar_ddata())

    def al_estado_opcua(self, ok: bool) -> None:
        _log.info("Status/OPCUA/Estado = %s", "DONE" if ok else "ERROR")
        self._publicar(self.nucleo.al_estado_opcua(ok))

    # ------------------------------------------------------------------ publicar
    def _publicar(self, mensajes: list[Mensaje]) -> None:
        """Publica si hay conexion. El nucleo ya no genera mensajes sin NBIRTH vigente."""
        cliente = self._cliente
        for m in mensajes:
            if cliente is None or not self.nucleo.conectado:
                return
            info = cliente.publish(m.topico, m.payload, qos=m.qos, retain=m.retener)
            self.registro.anotar("tx", m.topico, m.payload, tipo=m.tipo, qos=m.qos, retenido=m.retener,
                                 bd_seq=m.bd_seq, mid=info.mid, rc=info.rc)

    # ------------------------------------------------------------------ paho -> asyncio
    def _encolar(self, *evento) -> None:
        """Llamado desde el hilo de paho: solo pasa el evento al event loop."""
        self._loop.call_soon_threadsafe(self._cola.put_nowait, evento)

    def _crear_cliente(self, will: Mensaje) -> mqtt.Client:
        """[DF-3.3/3.4] Cliente nuevo con el Will de ESTA conexion."""
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.cfg.id_cliente,
                        clean_session=True, protocol=mqtt.MQTTv311)
        c.username_pw_set(self.cfg.usuario, self.cfg.clave)
        if self.cfg.tls:
            # TLS 1.2+ con verificacion del certificado y del nombre del broker (por defecto en
            # ssl.create_default_context). ca=None -> almacen de CAs del sistema.
            contexto = ssl.create_default_context(cafile=str(self.cfg.ca) if self.cfg.ca else None)
            contexto.minimum_version = ssl.TLSVersion.TLSv1_2
            c.tls_set_context(contexto)
        # Last Will: NDEATH con QoS 1 y SIN retener (payloads-ndeath-will-message-qos/-retain).
        c.will_set(will.topico, will.payload, qos=will.qos, retain=False)
        c.on_connect = lambda cl, u, flags, rc, props: self._encolar("connack", rc)
        c.on_subscribe = lambda cl, u, mid, rcs, props: self._encolar("suback", mid, rcs)
        c.on_disconnect = lambda cl, u, flags, rc, props: self._encolar("desconectado", rc)
        c.on_message = lambda cl, u, msg: self._encolar("mensaje", msg.topic, bytes(msg.payload), msg.retain, msg.qos)
        return c

    async def _esperar(self, tipo: str, timeout: float):
        """Espera un evento de paho de cierto tipo; los demas (mensajes) no pueden llegar todavia."""
        while True:
            evento = await asyncio.wait_for(self._cola.get(), timeout)
            if evento[0] == tipo:
                return evento
            if evento[0] == "desconectado":
                raise ConnectionError(f"desconexion durante el establecimiento: {evento[1]}")

    async def _sesion(self) -> None:
        """Una conexion MQTT completa: CONNECT -> SUBSCRIBE -> BIRTH -> eventos, hasta caer."""
        will = self.nucleo.preparar_conexion()
        _log.info("CONNECT a %s:%d (TLS=%s) bdSeq=%d", self.cfg.host, self.cfg.puerto, self.cfg.tls, will.bd_seq)
        self._cola = asyncio.Queue()
        cliente = self._crear_cliente(will)
        cliente.connect_async(self.cfg.host, self.cfg.puerto, keepalive=KEEPALIVE_S)
        cliente.loop_start()
        try:
            _, rc = await self._esperar("connack", TIMEOUT_CONNACK_S)
            if rc.is_failure:
                raise PermissionError(f"CONNACK rechazado: {rc}")
            t = self.nucleo.topicos
            # QoS 1 para NCMD (tck-id-message-flow-edge-node-ncmd-subscribe) y DCMD.
            _, mid = cliente.subscribe([(t.de("NCMD"), 1), (t.de("DCMD"), 1), (t.state(), 1)])
            _, _, codigos = await self._esperar("suback", TIMEOUT_CONNACK_S)
            if any(c.is_failure for c in codigos):
                # Un SUBACK 0x80 = el broker no autoriza ese topico (ACL mal configurada).
                raise PermissionError(f"SUBACK rechazado: {[str(c) for c in codigos]}")
            self._cliente = cliente
            self.conexiones += 1
            self._publicar(self.nucleo.al_conectar())          # NBIRTH (+ DBIRTH)
            while True:
                evento = await self._cola.get()
                if evento[0] == "desconectado":
                    raise ConnectionError(f"MQTT desconectado: {evento[1]}")
                if evento[0] == "mensaje":
                    await self._al_mensaje(*evento[1:])
        finally:
            self._cliente = None
            self.nucleo.al_desconectar()
            cliente.loop_stop()
            try:
                cliente.disconnect()
            except Exception:
                pass

    async def _al_mensaje(self, topico: str, payload: bytes, retenido: bool, qos: int) -> None:
        """NCMD, DCMD o STATE: valida en el nucleo, publica lo que corresponda y ejecuta escrituras."""
        r = self.nucleo.al_mensaje(topico, payload, retenido)
        self.registro.anotar("rx", topico, payload, tipo=r.tipo, qos=qos, retenido=retenido,
                             bd_seq=self.nucleo.bd_seq, rechazos=r.rechazos,
                             escrituras=[{"nombre": e.nombre, "valor": e.valor} for e in r.escrituras])
        for motivo in r.rechazos:
            _log.warning("rechazado: %s", motivo)
        self._publicar(r.mensajes)
        for e in r.escrituras:
            asyncio.create_task(self._escribir(e))
        if r.accion == "reconectar" and self._cliente is not None:
            # La Host Application primaria se fue (modo esperar_host): NDEATH y nueva conexion.
            self._publicar([self.nucleo.ndeath()])
            self._cliente.disconnect()

    async def _escribir(self, e: Escritura) -> None:
        """[DF-3.15] DCMD -> OPC UA Write. El valor real vuelve por la suscripcion (DDATA)."""
        if self.opcua is None:
            return
        resultado = await self.opcua.escribir(e.node_id, e.tipo, e.valor)
        _log.info("Write %s = %r -> %s", e.nombre, e.valor, resultado)
        self.registro.anotar("write", e.node_id, b"", tipo="OPCUA_WRITE", nombre=e.nombre,
                             valor=e.valor, resultado=resultado)

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(PERIODO_TICK_S)
            self._publicar(self.nucleo.tick())

    async def _bucle_mqtt(self) -> None:
        """[DF-3.17] Reconexion con retroceso exponencial 1-30 s (mismo criterio que OPC UA)."""
        intento = 0
        while True:
            conexiones_antes = self.conexiones
            try:
                await self._sesion()
            except asyncio.CancelledError:
                raise
            except (ConnectionError, OSError, asyncio.TimeoutError, PermissionError, ssl.SSLError) as exc:
                _log.warning("MQTT: %s: %s", type(exc).__name__, exc)
            intento = 1 if self.conexiones > conexiones_antes else intento + 1
            espera = espera_reintento(intento)
            _log.info("MQTT: reintento %d en %.0f s", intento, espera)
            await asyncio.sleep(espera)

    async def ejecutar(self, detener: asyncio.Event) -> None:
        """Corre todo hasta que 'detener' se active; al salir publica el NDEATH (desconexion intencional)."""
        self._loop = asyncio.get_running_loop()
        tareas = [asyncio.create_task(self._bucle_mqtt()), asyncio.create_task(self._tick())]
        if self.opcua is not None and hasattr(self.opcua, "ejecutar"):
            tareas.append(asyncio.create_task(self.opcua.ejecutar()))
        try:
            await detener.wait()
        finally:
            cliente = self._cliente
            if cliente is not None and self.nucleo.conectado:
                # tck-id-operational-behavior-edge-node-intentional-disconnect-ndeath
                m = self.nucleo.ndeath()
                info = cliente.publish(m.topico, m.payload, qos=1, retain=False)
                self.registro.anotar("tx", m.topico, m.payload, tipo="NDEATH", qos=1, bd_seq=m.bd_seq,
                                     intencional=True)
                try:
                    await asyncio.to_thread(info.wait_for_publish, 3)
                except (RuntimeError, ValueError):
                    pass
            for t in tareas:
                t.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)


# =============================================================================
# Programa
# =============================================================================

def leer_argumentos(argv=None):
    p = argparse.ArgumentParser(description="Dispositivo 3: cliente OPC UA + Edge Node Sparkplug B")
    p.add_argument("--env", type=Path, default=RAIZ.parent / ".env", help="archivo .env (por defecto tarea-3/.env)")
    p.add_argument("--diccionario", type=Path, default=DICCIONARIO_POR_DEFECTO)
    p.add_argument("--mqtt-ca", type=Path, help="CA del broker (por defecto, las del sistema)")
    p.add_argument("--sin-tls-local", action="store_true", help="MQTT sin TLS, SOLO contra 127.0.0.1")
    p.add_argument("--opcua-modo", choices=("suscripcion", "lectura"), default="suscripcion",
                   help="suscripcion (ADR-004) o lectura ciclica (Modo A de la T2, para comparar)")
    p.add_argument("--esperar-host", action="store_true",
                   help="no publicar BIRTH hasta que la Host Application publique STATE online")
    p.add_argument("--estado", type=Path, default=RAIZ / "estado" / "bdseq.json", help="bdSeq persistido")
    p.add_argument("--logs", type=Path, default=RAIZ / "logs")
    return p.parse_args(argv)


def construir(args) -> EdgeNode:
    """Arma el Edge Node desde el entorno y los argumentos [DF-3.1]."""
    cargar_env(args.env)
    metricas = cargar_metricas(args.diccionario)
    topicos = spb.Topicos(grupo=os.environ.get("SPB_GROUP_ID", "UNRaf_PdCI_2026"),
                          nodo=os.environ.get("SPB_EDGE_NODE_ID", "EN01_Gateway"),
                          dispositivo=os.environ.get("SPB_DEVICE_ID", "DEV01_ESP32_Slave"),
                          host=os.environ.get("SPB_HOST_ID", "HA01_WebDashboard"))
    nucleo = NucleoEdgeNode(metricas, topicos, AlmacenBdSeq(args.estado), esperar_host=args.esperar_host)
    host = os.environ.get("MQTT_HOST", "")
    if not host or "<" in host:
        raise SystemExit("MQTT_HOST no configurado (.env): el broker de la demo esta en la nube (I-03)")
    cfg = ConfigMqtt(host=host, puerto=int(os.environ.get("MQTT_PUERTO_TLS", "8883")),
                     usuario=os.environ.get("MQTT_USUARIO_EDGE", ""), clave=os.environ.get("MQTT_CLAVE_EDGE", ""),
                     id_cliente=f"{topicos.grupo}-{topicos.nodo}", ca=args.mqtt_ca or (
                         Path(os.environ["MQTT_CA"]) if os.environ.get("MQTT_CA") else None),
                     tls=not args.sin_tls_local)
    fecha = dt.datetime.now().strftime("%Y%m%d")
    registro = RegistroMensajes(args.logs / f"edge-node-{fecha}.jsonl", metricas)
    edge = EdgeNode(nucleo, cfg, registro)
    edge.opcua = ClienteOpcua(ConfigOpcua.desde_entorno(modo=args.opcua_modo), metricas,
                              al_dato=edge.al_dato, al_estado=edge.al_estado_opcua)
    return edge


async def principal(argv=None) -> None:
    args = leer_argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-5s %(levelname)-7s %(message)s")
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    edge = construir(args)
    _log.info("Edge Node %s del grupo %s · registro %s", edge.nucleo.topicos.nodo, edge.nucleo.topicos.grupo,
              edge.registro.ruta)
    detener = asyncio.Event()
    try:
        await edge.ejecutar(detener)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        # asyncio.run cancela la tarea principal; el finally de ejecutar() ya publico el NDEATH.
        print("\nEdge Node detenido por el usuario.")
