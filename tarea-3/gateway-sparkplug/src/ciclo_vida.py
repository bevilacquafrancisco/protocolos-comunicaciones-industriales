"""
ciclo_vida.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Nucleo del Edge Node Sparkplug B 3.0: una maquina de estados PURA (sin red, sin hilos, sin
reloj propio). Cada evento entra por un metodo y sale la lista de mensajes que hay que publicar.
sparkplug_edge_node.py solo mueve esos bytes por MQTT; toda la logica del ciclo de vida
(invariantes I-07 e I-10) vive aca y se prueba sin broker (tests/test_ciclo_vida.py).

Bloques de docs/diagramas/flujo-edge-node.mmd que implementa:
    [DF-3.3]  preparar_conexion: bdSeq nuevo y persistido + NDEATH para el Last Will
    [DF-3.6]  NBIRTH (seq = 0)            [DF-3.7] disponibilidad del dispositivo
    [DF-3.8]  DBIRTH                      [DF-3.10] NDATA (agrupado)   [DF-3.11] DDATA
    [DF-3.12] DDEATH / DBIRTH al cambiar la disponibilidad
    [DF-3.13] Rebirth                     [DF-3.14] validacion de DCMD
    [DF-3.16] estado OPC UA               [DF-3.17] reconexion (Reconexiones++)

Reglas de la especificacion que se aplican (identificadores tck-id de Sparkplug 3.0):
    - un solo seq por Edge Node para NBIRTH, DBIRTH, NDATA, DDATA y DDEATH; 255 -> 0
      (payloads-sequence-num-incrementing); NDEATH sin seq (payloads-ndeath-seq)
    - bdSeq Int64, +1 en cada CONNECT, 255 -> 0, igual en el Will y en el NBIRTH
      (message-flow-edge-node-birth-publish-will-message-payload-bdSeq, payloads-nbirth-bdseq-repeat)
    - BIRTH con nombre + alias; DATA y CMD solo con alias (payloads-alias-data-cmd-requirement)
    - Rebirth: dejar de publicar DATA y republicar NBIRTH (mismo bdSeq) + DBIRTH
      (operational-behavior-data-commands-rebirth-action-1..3)
    - NBIRTH, DBIRTH, DATA y DDEATH con QoS 0 y sin retener; Will con QoS 1 sin retener

Dependencias externas: ninguna propia (usa metrics.py y sparkplug.py).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import sparkplug as spb
from metrics import NOMBRE_BDSEQ, NOMBRE_REBIRTH, ConjuntoMetricas, Metrica

#: Estado MODBus que el maestro publica tras la ausencia sostenida del esclavo (ADR-014).
ESTADO_NO_ALCANZADO = "DEVICE NOT REACHED"
#: Status/OPCUA/Estado (docs/diccionario-de-datos.md §2).
OPCUA_DONE, OPCUA_ERROR = "DONE", "ERROR"
#: Un CMD mas grande se descarta sin decodificar: el payload legitimo mas grande (dos salidas)
#: ocupa menos de 100 bytes; 16 KiB acota la memoria ante un publicador malicioso (STRIDE: DoS).
MAXIMO_BYTES_CMD = 16 * 1024


# =============================================================================
# Persistencia de bdSeq
# =============================================================================

class AlmacenBdSeq:
    """
    bdSeq persistido en un archivo JSON (escritura atomica).

    Por que se persiste: si el proceso se reinicia y vuelve a empezar en 0, el broker puede
    publicar DESPUES el Will de la sesion anterior (tambien con bdSeq 0, si esa sesion era la
    primera) y la Host Application daria por muerta la sesion NUEVA, porque el bdSeq coincide.
    Con el contador persistido, el Will viejo trae un bdSeq distinto y se ignora
    (tck-id-operational-behavior-edge-node-termination-host-action-ndeath-node-offline + §5.7).
    """

    def __init__(self, ruta: Path | str):
        self._ruta = Path(ruta)

    def ultimo(self) -> int | None:
        """El ultimo bdSeq usado, o None si nunca se conecto (o el archivo esta corrupto)."""
        try:
            valor = json.loads(self._ruta.read_text(encoding="utf-8")).get("bdSeq")
        except (OSError, ValueError, AttributeError):
            return None
        return valor if isinstance(valor, int) and 0 <= valor <= 255 else None

    def siguiente(self) -> int:
        """Calcula, PERSISTE y devuelve el bdSeq del proximo CONNECT (0 la primera vez)."""
        ultimo = self.ultimo()
        nuevo = 0 if ultimo is None else (ultimo + 1) % 256
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self._ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps({"bdSeq": nuevo}), encoding="utf-8")
        os.replace(temporal, self._ruta)          # atomico: nunca queda un archivo a medias
        return nuevo


class AlmacenBdSeqMemoria:
    """Mismo contrato que AlmacenBdSeq, en memoria (pruebas)."""

    def __init__(self, ultimo: int | None = None):
        self._ultimo = ultimo

    def ultimo(self) -> int | None:
        return self._ultimo

    def siguiente(self) -> int:
        self._ultimo = 0 if self._ultimo is None else (self._ultimo + 1) % 256
        return self._ultimo


# =============================================================================
# Tipos de salida
# =============================================================================

@dataclass(frozen=True)
class Mensaje:
    """Un mensaje MQTT a publicar (o el Will)."""

    tipo: str            # NBIRTH, DBIRTH, NDATA, DDATA, DDEATH, NDEATH
    topico: str
    payload: bytes
    qos: int
    retener: bool
    seq: int | None
    bd_seq: int


@dataclass(frozen=True)
class Escritura:
    """Una escritura OPC UA pedida por un DCMD valido [DF-3.15]."""

    nombre: str
    node_id: str
    tipo: str
    valor: Any


@dataclass
class Resultado:
    """
    Lo que produjo un mensaje recibido.

    Atributos:
        mensajes: a publicar (Rebirth, BIRTH al aparecer la Host Application).
        escrituras: OPC UA Write a ejecutar (DCMD).
        rechazos: motivo de cada metrica descartada (se registran; no se escribe nada).
        accion: 'reconectar' si la Host Application primaria se desconecto (modo esperar_host).
        tipo: tipo Sparkplug del mensaje recibido (para el registro).
    """

    mensajes: list[Mensaje] = field(default_factory=list)
    escrituras: list[Escritura] = field(default_factory=list)
    rechazos: list[str] = field(default_factory=list)
    accion: str | None = None
    tipo: str | None = None


# =============================================================================
# Nucleo
# =============================================================================

class NucleoEdgeNode:
    """
    Estado y reglas del ciclo de vida de UN Edge Node con UN dispositivo.

    Atributos principales:
        bd_seq (int | None): el de la conexion MQTT vigente (o la que se esta por abrir).
        nacido (bool): se publico el NBIRTH en esta conexion.
        dispositivo_nacido (bool): hay un DBIRTH vigente (sin DDEATH posterior).
        reconexiones, rebirths (int): Status/MQTT/Reconexiones y Status/Sparkplug/Rebirths.
    """

    def __init__(self, metricas: ConjuntoMetricas, topicos: spb.Topicos, almacen_bdseq,
                 esperar_host: bool = False, periodo_ndata_ms: int = 1000,
                 reloj: Callable[[], int] = spb.ahora_ms):
        """
        Parametros:
            metricas: leidas del diccionario (metrics.cargar_metricas).
            topicos: identificadores Sparkplug.
            almacen_bdseq: AlmacenBdSeq o AlmacenBdSeqMemoria.
            esperar_host (bool): no publicar BIRTH hasta que la Host Application primaria
                publique STATE online (Sparkplug 3.0 §5.3, opcional).
            periodo_ndata_ms (int): agrupamiento de los contadores en NDATA (ADR-021).
            reloj: ms UTC; inyectable para las pruebas.
        """
        self.metricas = metricas
        self.topicos = topicos
        self._almacen = almacen_bdseq
        self._esperar_host = esperar_host
        self._periodo_ndata_ms = periodo_ndata_ms
        self._reloj = reloj
        self._seq = spb.Secuencia()

        self.bd_seq: int | None = None
        self.conectado = False
        self.nacido = False
        self.dispositivo_nacido = False
        self._sesiones_mqtt = 0
        self.reconexiones = 0
        self.rebirths = 0
        self.host_online: bool | None = None
        self._ts_state_host: int | None = None

        self._opcua_ok = False
        # Ultimo valor conocido: nombre -> (valor, timestamp ms). None = nunca llego.
        self._valores: dict[str, tuple[Any, int] | None] = {m.nombre: None for m in metricas.todas()}
        self._fijar(NOMBRE_REBIRTH, False)
        self._fijar("Status/OPCUA/Estado", OPCUA_ERROR)
        self._fijar("Status/MQTT/Reconexiones", 0)
        self._fijar("Status/Sparkplug/Rebirths", 0)
        self._ndata_pendiente: dict[str, spb.ValorMetrica] = {}
        self._ddata_pendiente: dict[str, spb.ValorMetrica] = {}
        self._ultimo_ndata_ms = 0

    # ------------------------------------------------------------------ utilidades
    def _fijar(self, nombre: str, valor: Any, ts: int | None = None) -> bool:
        """Actualiza el ultimo valor; True si cambio (o si es el primero)."""
        if nombre not in self._valores:
            return False
        anterior = self._valores[nombre]
        self._valores[nombre] = (valor, self._reloj() if ts is None else ts)
        return anterior is None or anterior[0] != valor or type(anterior[0]) is not type(valor)

    def valor(self, nombre: str) -> Any:
        v = self._valores.get(nombre)
        return None if v is None else v[0]

    def _mensaje(self, tipo: str, metricas: list[spb.ValorMetrica], seq: int | None, qos: int = 0) -> Mensaje:
        return Mensaje(tipo=tipo, topico=self.topicos.de(tipo), payload=spb.armar_payload(metricas, seq, self._reloj()),
                       qos=qos, retener=False, seq=seq, bd_seq=self.bd_seq)

    def _para_birth(self, m: Metrica) -> spb.ValorMetrica:
        v = self._valores[m.nombre]
        return spb.ValorMetrica(nombre=m.nombre, alias=m.alias, tipo=m.tipo,
                                valor=None if v is None else v[0], timestamp=None if v is None else v[1])

    def _para_data(self, m: Metrica) -> spb.ValorMetrica:
        valor, ts = self._valores[m.nombre]
        return spb.ValorMetrica(nombre=None, alias=m.alias, tipo=m.tipo, valor=valor, timestamp=ts)

    @staticmethod
    def _agrupable(m: Metrica) -> bool:
        """
        Contadores MODBus (UInt32 leidos por OPC UA): cambian ~16 veces por segundo con el sondeo
        de 250 ms, y se agrupan en un NDATA por periodo (ADR-021). Los estados (String) y los
        contadores internos se publican al instante: son eventos que el operador debe ver ya.
        """
        return m.ambito == "nodo" and m.origen == "opcua" and m.tipo == "UInt32"

    # ------------------------------------------------------------------ disponibilidad [DF-3.7]
    def dispositivo_disponible(self) -> bool:
        """
        El dispositivo 1 se considera vivo si: hay sesion OPC UA con el dispositivo 2, el maestro
        no declaro DEVICE NOT REACHED (ausencia sostenida, ADR-014) y se conoce el valor actual
        de TODAS sus metricas (el DBIRTH debe llevarlas, tck-id-topics-dbirth-metric-reqs).
        """
        estado = self.valor("Status/MODBUS/Estado")
        return (self._opcua_ok and estado is not None and estado != ESTADO_NO_ALCANZADO
                and all(self._valores[m.nombre] is not None for m in self.metricas.dispositivo))

    def _evaluar_dispositivo(self) -> list[Mensaje]:
        """[DF-3.12] DDEATH al perderlo, DBIRTH al recuperarlo (solo con NBIRTH vigente)."""
        if not self.nacido:
            return []
        disponible = self.dispositivo_disponible()
        if self.dispositivo_nacido and not disponible:
            # Primero lo pendiente (datos validos de antes de la caida y el NDATA con el estado que
            # la explica), despues el DDEATH.
            salida = self._vaciar_ddata() + self._vaciar_ndata()
            salida.append(self._mensaje("DDEATH", [], self._seq.siguiente()))
            self.dispositivo_nacido = False
            return salida
        if not self.dispositivo_nacido and disponible:
            return self._vaciar_ndata() + [self._dbirth()]
        return []

    def _dbirth(self) -> Mensaje:
        """[DF-3.8] DBIRTH con TODAS las metricas del dispositivo y su valor actual."""
        self.dispositivo_nacido = True
        return self._mensaje("DBIRTH", [self._para_birth(m) for m in self.metricas.dispositivo], self._seq.siguiente())

    def _nacimiento(self) -> list[Mensaje]:
        """[DF-3.6] NBIRTH (seq = 0, bdSeq de la conexion, Rebirth = false) y DBIRTH si corresponde."""
        self._fijar(NOMBRE_BDSEQ, self.bd_seq)
        self._fijar(NOMBRE_REBIRTH, False)
        self._ndata_pendiente.clear()               # el NBIRTH ya lleva todos los valores actuales
        self._ddata_pendiente.clear()               # y el DBIRTH, los del dispositivo
        nbirth = self._mensaje("NBIRTH", [self._para_birth(m) for m in self.metricas.nodo], self._seq.para_nbirth())
        self.nacido = True
        self.dispositivo_nacido = False
        salida = [nbirth]
        if self.dispositivo_disponible():
            salida.append(self._dbirth())
        return salida

    # ------------------------------------------------------------------ NDATA [DF-3.10]
    def _cambio_nodo(self, m: Metrica, inmediato: bool) -> list[Mensaje]:
        if not self.nacido:
            return []
        self._ndata_pendiente[m.nombre] = self._para_data(m)
        if inmediato or not self._agrupable(m):
            # Un DDATA diferido es ANTERIOR a este cambio: sale primero (orden cronologico).
            return self._vaciar_ddata() + self._vaciar_ndata()
        return []

    def _vaciar_ndata(self) -> list[Mensaje]:
        if not self._ndata_pendiente or not self.nacido:
            return []
        metricas = sorted(self._ndata_pendiente.values(), key=lambda v: v.timestamp or 0)   # orden cronologico
        self._ndata_pendiente.clear()
        self._ultimo_ndata_ms = self._reloj()
        return [self._mensaje("NDATA", metricas, self._seq.siguiente())]

    def tick(self) -> list[Mensaje]:
        """Llamar periodicamente (p. ej. cada 200 ms): publica los contadores agrupados."""
        if self._ndata_pendiente and self._reloj() - self._ultimo_ndata_ms >= self._periodo_ndata_ms:
            return self._vaciar_ndata()
        return []

    # ------------------------------------------------------------------ conexion MQTT
    def preparar_conexion(self) -> Mensaje:
        """
        [DF-3.3] Antes de CADA CONNECT: bdSeq nuevo (persistido) y el NDEATH para el Last Will.

        Retorna:
            Mensaje NDEATH (QoS 1, no retenido, sin seq, solo la metrica bdSeq).
        """
        self.bd_seq = self._almacen.siguiente()
        return self.ndeath()

    def ndeath(self) -> Mensaje:
        """NDEATH con el bdSeq de la conexion vigente (Will o desconexion intencional)."""
        bd = spb.ValorMetrica(nombre=NOMBRE_BDSEQ, alias=None, tipo="Int64", valor=self.bd_seq)
        return Mensaje(tipo="NDEATH", topico=self.topicos.de("NDEATH"),
                       payload=spb.armar_payload([bd], seq=None, timestamp=self._reloj()),
                       qos=1, retener=False, seq=None, bd_seq=self.bd_seq)

    def al_conectar(self) -> list[Mensaje]:
        """[DF-3.5/3.6] CONNACK recibido y NCMD/DCMD suscriptos. Si es una REconexion, Reconexiones++."""
        self.conectado = True
        self._sesiones_mqtt += 1
        if self._sesiones_mqtt > 1:
            self.reconexiones += 1                                     # [DF-3.17]
            self._fijar("Status/MQTT/Reconexiones", self.reconexiones)
        if self._esperar_host and self.host_online is not True:
            return []                      # el BIRTH espera al STATE online (§5.3)
        return self._nacimiento()

    def al_desconectar(self) -> None:
        """Se perdio la conexion MQTT: nada mas se publica hasta el proximo CONNECT + NBIRTH."""
        self.conectado = False
        self.nacido = False
        self.dispositivo_nacido = False
        self._ndata_pendiente.clear()
        self._ddata_pendiente.clear()

    # ------------------------------------------------------------------ datos de OPC UA
    def _vaciar_ddata(self) -> list[Mensaje]:
        if not self._ddata_pendiente or not (self.nacido and self.dispositivo_nacido):
            self._ddata_pendiente.clear()
            return []
        metricas = sorted(self._ddata_pendiente.values(), key=lambda v: v.timestamp or 0)
        self._ddata_pendiente.clear()
        return [self._mensaje("DDATA", metricas, self._seq.siguiente())]

    def vaciar_ddata(self) -> list[Mensaje]:
        """
        Publica en UN DDATA los cambios diferidos (al_dato(..., diferir=True)). El Edge Node lo
        llama una vez que se procesaron todas las notificaciones de un PublishResponse: asi
        Potenciometro y Potenciometro_pct, que cambian juntos, viajan en el mismo mensaje
        (consistentes entre si y con la mitad de mensajes, ADR-021).
        """
        return self._vaciar_ddata()

    def al_dato(self, nombre: str, valor: Any, ts: int | None = None, bueno: bool = True,
                diferir: bool = False) -> list[Mensaje]:
        """
        Un MonitoredItem cambio [DF-3.10, DF-3.11].

        Parametros:
            nombre: metrica (el cliente OPC UA ya tradujo NodeId -> nombre).
            valor: valor Python; ts: SourceTimestamp en ms (el instante de la lectura MODBus).
            bueno: StatusCode Good. Un valor Bad o Uncertain NO se publica: se conserva el ultimo
                bueno; si el esclavo cayo, lo informa el DDEATH (no se miente con un dato viejo).
            diferir: acumular el cambio del dispositivo hasta vaciar_ddata() en vez de publicarlo ya.
        """
        m = self.metricas.por_nombre(nombre)
        if m is None or m.origen != "opcua" or not bueno:
            return []
        if not self._fijar(nombre, valor, ts):
            return self._evaluar_dispositivo()          # sin cambio: no hay DATA (report by exception)
        if m.ambito == "nodo":
            # Status/MODBUS/Estado se publica antes de evaluar: si causa un DDEATH, el NDATA va primero.
            return self._cambio_nodo(m, inmediato=False) + self._evaluar_dispositivo()
        if self.nacido and self.dispositivo_nacido:
            self._ddata_pendiente[m.nombre] = self._para_data(m)
        salida = [] if diferir else self._vaciar_ddata()
        return salida + self._evaluar_dispositivo()

    def al_estado_opcua(self, ok: bool) -> list[Mensaje]:
        """
        [DF-3.16] Cambio de la sesion OPC UA con el dispositivo 2.

        Al perderla, los valores del dispositivo dejan de ser actuales: se olvidan, para que el
        DBIRTH siguiente lleve solo valores leidos en la sesion nueva.
        """
        if ok == self._opcua_ok:
            return []
        self._opcua_ok = ok
        if not ok:
            for m in self.metricas.dispositivo:
                self._valores[m.nombre] = None
            # Status/MODBUS/* conserva el ultimo valor: es diagnostico del nodo (ADR-006) y la
            # disponibilidad ya exige la sesion OPC UA, asi que no hace falta borrarlo.
        m = self.metricas.por_nombre("Status/OPCUA/Estado")
        self._fijar(m.nombre, OPCUA_DONE if ok else OPCUA_ERROR)
        return self._cambio_nodo(m, inmediato=True) + self._evaluar_dispositivo()

    # ------------------------------------------------------------------ mensajes recibidos
    def al_mensaje(self, topico: str, payload: bytes, retenido: bool = False) -> Resultado:
        """
        NCMD, DCMD o STATE recibido [DF-3.13, DF-3.14].

        Nada de lo que llega se ejecuta sin validar: el broker esta en internet y el usuario
        de la Host Application es publico de hecho (ADR-005).
        """
        datos = spb.analizar_topico(topico)
        if datos is None:
            return Resultado(rechazos=[f"topico no Sparkplug: {topico}"])
        tipo = datos["tipo"]
        if tipo == "STATE":
            return self._al_state(datos["host"], payload)
        r = Resultado(tipo=tipo)
        if retenido:
            # NCMD y DCMD se publican SIN retener (topics-ncmd-mqtt): uno retenido es viejo o ajeno.
            r.rechazos.append(f"{tipo} retenido: se ignora")
            return r
        if datos["grupo"] != self.topicos.grupo or datos["nodo"] != self.topicos.nodo:
            r.rechazos.append(f"{tipo} para otro nodo: {topico}")
            return r
        if len(payload) > MAXIMO_BYTES_CMD:
            r.rechazos.append(f"{tipo} de {len(payload)} bytes (maximo {MAXIMO_BYTES_CMD})")
            return r
        try:
            p = spb.decodificar(payload)
        except ValueError as exc:
            r.rechazos.append(str(exc))
            return r
        if tipo == "NCMD":
            self._al_ncmd(p, r)
        elif tipo == "DCMD" and datos["dispositivo"] == self.topicos.dispositivo:
            self._al_dcmd(p, r)
        else:
            r.rechazos.append(f"{tipo} no esperado en {topico}")
        return r

    def _al_ncmd(self, p, r: Resultado) -> None:
        """[DF-3.13] Solo se acepta Node Control/Rebirth = true (las metricas del nodo son de lectura)."""
        for m in p.metrics:
            if m.name != NOMBRE_REBIRTH:
                r.rechazos.append(f"NCMD sobre {m.name or f'alias {m.alias}'}: el nodo no acepta escrituras")
                continue
            try:
                pedido = spb.leer_valor(m, "Boolean")
            except ValueError as exc:
                r.rechazos.append(f"NCMD Rebirth invalido: {exc}")
                continue
            if pedido is True and self.conectado:
                # Dejar de publicar DATA (lo pendiente se descarta: el NBIRTH lleva el valor actual)
                # y republicar el nacimiento con el MISMO bdSeq.
                self.rebirths += 1
                self._fijar("Status/Sparkplug/Rebirths", self.rebirths)
                r.mensajes.extend(self._nacimiento())
            elif pedido is not True:
                r.rechazos.append("NCMD Rebirth = false: no hay nada que hacer")

    def _al_dcmd(self, p, r: Resultado) -> None:
        """[DF-3.14] Cada metrica: conocida, del dispositivo, escribible, tipo y rango validos."""
        if not self.dispositivo_nacido:
            r.rechazos.append("DCMD sin DBIRTH vigente: el dispositivo no esta disponible")
            return
        for m in p.metrics:
            definida = (self.metricas.por_alias(m.alias) if m.HasField("alias") else None) or \
                (self.metricas.por_nombre(m.name) if m.name else None)
            etiqueta = m.name or f"alias {m.alias}"
            if definida is None or definida.ambito != "dispositivo":
                r.rechazos.append(f"DCMD sobre metrica desconocida: {etiqueta}")
                continue
            if m.name and m.HasField("alias") and m.name != definida.nombre:
                r.rechazos.append(f"DCMD: el nombre {m.name!r} no corresponde al alias {m.alias}")
                continue
            if not definida.escribible:
                r.rechazos.append(f"DCMD sobre {definida.nombre}: es de solo lectura")
                continue
            if m.datatype and spb.pb.DataType.Name(m.datatype) != definida.tipo:
                r.rechazos.append(f"DCMD {definida.nombre}: tipo {spb.pb.DataType.Name(m.datatype)} "
                                  f"(se esperaba {definida.tipo})")
                continue
            try:
                valor = spb.leer_valor(m, definida.tipo)
                spb.poner_valor(spb.pb.Payload.Metric(), definida.tipo, valor)     # valida el rango
            except (ValueError, TypeError) as exc:
                r.rechazos.append(f"DCMD {definida.nombre}: {exc}")
                continue
            if valor is None:
                r.rechazos.append(f"DCMD {definida.nombre}: valor nulo")
                continue
            r.escrituras.append(Escritura(definida.nombre, definida.node_id, definida.tipo, valor))

    def _al_state(self, host: str, payload: bytes) -> Resultado:
        """STATE de una Host Application (opcional: solo cambia el comportamiento con esperar_host)."""
        r = Resultado(tipo="STATE")
        if host != self.topicos.host:
            return r
        leido = spb.leer_state(payload)
        if leido is None:
            r.rechazos.append("STATE con formato invalido: se ignora")
            return r
        online, ts = leido
        if self._ts_state_host is not None and ts < self._ts_state_host:
            # Un STATE con timestamp anterior es viejo (p. ej. un Will retrasado): se ignora
            # (tck-id-message-flow-edge-node-birth-publish-phid-wait-timestamp).
            r.rechazos.append("STATE anterior al ultimo conocido: se ignora")
            return r
        self._ts_state_host = ts
        self.host_online = online
        if self._esperar_host:
            if online and self.conectado and not self.nacido:
                r.mensajes.extend(self._nacimiento())
            elif not online and self.nacido:
                r.accion = "reconectar"
        return r
