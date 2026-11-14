"""
sparkplug.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Codificacion Sparkplug B 3.0 SIN estado y sin red: topicos, numero de secuencia y payloads
Protobuf (sparkplug_b.proto de Eclipse Tahu, sin modificar). Invariante I-02: el payload es
SIEMPRE Protobuf; el unico JSON es el STATE de la Host Application, que la especificacion define
asi (tck-id-message-flow-phid-sparkplug-state-publish-payload).

Codificacion de valores (Sparkplug 3.0, §6.4.16 "Datatype Details"):

    Boolean                         -> boolean_value
    Int8/16/32, UInt8/16/32         -> int_value   (uint32; los con signo en complemento a 2)
    Int64, UInt64, DateTime         -> long_value  (uint64; idem)
    Float -> float_value · Double -> double_value · String, Text -> string_value

    Ojo: UInt32 va en int_value (uint32), NO en long_value. Verificado contra el texto de la
    especificacion, no de memoria.

Dependencias externas: protobuf 7.36.2 (sparkplug_b_pb2.py generado, ver README §3).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

import sparkplug_b_pb2 as pb

NAMESPACE = "spBv1.0"

#: Rango de cada tipo entero: (minimo, maximo, campo protobuf, bits del campo).
_ENTEROS = {
    "Int8": (-2**7, 2**7 - 1, "int_value", 32), "Int16": (-2**15, 2**15 - 1, "int_value", 32),
    "Int32": (-2**31, 2**31 - 1, "int_value", 32), "UInt8": (0, 2**8 - 1, "int_value", 32),
    "UInt16": (0, 2**16 - 1, "int_value", 32), "UInt32": (0, 2**32 - 1, "int_value", 32),
    "Int64": (-2**63, 2**63 - 1, "long_value", 64), "UInt64": (0, 2**64 - 1, "long_value", 64),
}
_CON_SIGNO = {"Int8", "Int16", "Int32", "Int64"}

#: Tipos de mensaje que publica el Edge Node (con seq, salvo NDEATH) y los que recibe.
TIPOS_NODO = ("NBIRTH", "NDATA", "NDEATH", "NCMD")
TIPOS_DISPOSITIVO = ("DBIRTH", "DDATA", "DDEATH", "DCMD")


def ahora_ms() -> int:
    """Milisegundos desde la epoca Unix en UTC: la unidad del 'timestamp' de Sparkplug."""
    return time.time_ns() // 1_000_000


# =============================================================================
# Topicos
# =============================================================================

@dataclass(frozen=True)
class Topicos:
    """
    Topicos de un Edge Node y su dispositivo (docs/diccionario-de-datos.md §4).

    Atributos:
        grupo, nodo, dispositivo, host (str): identificadores Sparkplug.
    """

    grupo: str
    nodo: str
    dispositivo: str
    host: str

    def __post_init__(self):
        # Un identificador con '/', '+' o '#' rompe la estructura del topico o lo vuelve un
        # comodin (Sparkplug 3.0 §4.1.1: solo caracteres validos de un nivel de topico MQTT).
        for nombre, valor in (("grupo", self.grupo), ("nodo", self.nodo), ("dispositivo", self.dispositivo),
                              ("host", self.host)):
            if not valor or any(c in valor for c in "/+# "):
                raise ValueError(f"identificador Sparkplug invalido en {nombre}: {valor!r}")

    def del_nodo(self, tipo: str) -> str:
        """spBv1.0/<grupo>/<NBIRTH|NDATA|NDEATH|NCMD>/<nodo>"""
        return f"{NAMESPACE}/{self.grupo}/{tipo}/{self.nodo}"

    def del_dispositivo(self, tipo: str) -> str:
        """spBv1.0/<grupo>/<DBIRTH|DDATA|DDEATH|DCMD>/<nodo>/<dispositivo>"""
        return f"{NAMESPACE}/{self.grupo}/{tipo}/{self.nodo}/{self.dispositivo}"

    def de(self, tipo: str) -> str:
        return self.del_nodo(tipo) if tipo in TIPOS_NODO else self.del_dispositivo(tipo)

    def state(self) -> str:
        """spBv1.0/STATE/<host_id>: el BIRTH/DEATH de la Host Application (JSON, retenido)."""
        return f"{NAMESPACE}/STATE/{self.host}"


def analizar_topico(topico: str) -> dict[str, str | None] | None:
    """
    Descompone un topico Sparkplug.

    Retorna:
        dict con 'tipo', 'grupo', 'nodo', 'dispositivo' (o 'host' para STATE), o None si no es
        un topico Sparkplug B valido.
    """
    partes = topico.split("/")
    if len(partes) == 3 and partes[0] == NAMESPACE and partes[1] == "STATE":
        return {"tipo": "STATE", "host": partes[2], "grupo": None, "nodo": None, "dispositivo": None}
    if partes[0] != NAMESPACE or len(partes) not in (4, 5):
        return None
    tipo = partes[2]
    if len(partes) == 4 and tipo in TIPOS_NODO:
        return {"tipo": tipo, "grupo": partes[1], "nodo": partes[3], "dispositivo": None}
    if len(partes) == 5 and tipo in TIPOS_DISPOSITIVO:
        return {"tipo": tipo, "grupo": partes[1], "nodo": partes[3], "dispositivo": partes[4]}
    return None


# =============================================================================
# Numero de secuencia
# =============================================================================

class Secuencia:
    """
    'seq' del Edge Node: UNO solo para NBIRTH, DBIRTH, NDATA, DDATA y DDEATH (no hay un contador
    por tipo ni por dispositivo). NBIRTH lleva 0; cada mensaje siguiente, el anterior + 1, y
    despues de 255 viene 0 (tck-id-payloads-sequence-num-incrementing). NDEATH no lleva seq.
    """

    def __init__(self) -> None:
        self._ultimo: int | None = None

    def para_nbirth(self) -> int:
        """Reinicia la secuencia: el NBIRTH lleva 0."""
        self._ultimo = 0
        return 0

    def siguiente(self) -> int:
        """
        Valor para el proximo mensaje despues del NBIRTH.

        Excepciones:
            RuntimeError: todavia no se publico un NBIRTH en esta sesion.
        """
        if self._ultimo is None:
            raise RuntimeError("no hay NBIRTH en esta sesion: ningun otro mensaje puede llevar seq")
        self._ultimo = (self._ultimo + 1) % 256
        return self._ultimo

    @property
    def ultimo(self) -> int | None:
        return self._ultimo


# =============================================================================
# Valores
# =============================================================================

def poner_valor(metrica_pb, tipo: str, valor: Any) -> None:
    """
    Escribe 'datatype' y el campo de valor que corresponde al tipo (ver tabla del encabezado).
    valor None -> is_null = true sin valor (tck-id-operational-behavior-data-publish-nbirth-values).

    Excepciones:
        ValueError: valor fuera del rango del tipo, o tipo desconocido.
        TypeError: el valor no es del tipo Python esperado.
    """
    metrica_pb.datatype = pb.DataType.Value(tipo)
    if valor is None:
        metrica_pb.is_null = True
        return
    if tipo == "Boolean":
        if not isinstance(valor, bool):
            raise TypeError(f"Boolean espera bool, llego {type(valor).__name__}")
        metrica_pb.boolean_value = valor
    elif tipo in _ENTEROS:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise TypeError(f"{tipo} espera int, llego {type(valor).__name__}")
        minimo, maximo, campo, bits = _ENTEROS[tipo]
        if not minimo <= valor <= maximo:
            raise ValueError(f"{valor} fuera del rango de {tipo} [{minimo}, {maximo}]")
        setattr(metrica_pb, campo, valor & ((1 << bits) - 1))   # complemento a 2 si es negativo
    elif tipo == "Float":
        metrica_pb.float_value = float(valor)
    elif tipo == "Double":
        metrica_pb.double_value = float(valor)
    elif tipo in ("String", "Text"):
        metrica_pb.string_value = str(valor)
    else:
        raise ValueError(f"tipo Sparkplug no soportado: {tipo}")


def leer_valor(metrica_pb, tipo: str | None = None) -> Any:
    """
    Valor Python de una metrica recibida. 'tipo' manda si se pasa (un CMD puede venir sin
    datatype y con alias: el tipo lo da la definicion local); si no, se usa metrica_pb.datatype.

    Excepciones:
        ValueError: el campo presente no corresponde al tipo (p. ej. string_value para Boolean).
    """
    tipo = tipo or pb.DataType.Name(metrica_pb.datatype)
    if metrica_pb.is_null:
        return None
    campo = metrica_pb.WhichOneof("value")
    if tipo == "Boolean":
        esperado = "boolean_value"
    elif tipo in _ENTEROS:
        esperado = _ENTEROS[tipo][2]
    else:
        esperado = {"Float": "float_value", "Double": "double_value", "String": "string_value",
                    "Text": "string_value"}.get(tipo)
    if esperado is None or campo != esperado:
        raise ValueError(f"metrica {tipo} con el campo {campo!r} (se esperaba {esperado!r})")
    valor = getattr(metrica_pb, campo)
    if tipo in _CON_SIGNO:
        bits = _ENTEROS[tipo][3]
        valor = valor - (1 << bits) if valor >= 1 << (bits - 1) else valor
        minimo, maximo = _ENTEROS[tipo][:2]
        if not minimo <= valor <= maximo:
            raise ValueError(f"{valor} fuera del rango de {tipo}")
    elif tipo in _ENTEROS and valor > _ENTEROS[tipo][1]:
        raise ValueError(f"{valor} fuera del rango de {tipo}")
    return valor


# =============================================================================
# Payloads
# =============================================================================

@dataclass(frozen=True)
class ValorMetrica:
    """
    Una metrica a publicar.

    Atributos:
        nombre (str | None): se incluye en BIRTH (y en NDEATH/NCMD de Rebirth); None en DATA.
        alias (int | None), tipo (str), valor (Any), timestamp (int | None) en ms.
    """

    nombre: str | None
    alias: int | None
    tipo: str
    valor: Any
    timestamp: int | None = None


def armar_payload(metricas: Iterable[ValorMetrica], seq: int | None, timestamp: int | None = None) -> bytes:
    """
    Serializa un Payload Sparkplug B.

    Parametros:
        metricas: ValorMetrica en orden cronologico (tck-id-operational-behavior-data-publish-nbirth-order).
        seq (int | None): 0..255; None SOLO para NDEATH, NCMD y DCMD (no llevan seq).
        timestamp (int | None): ms UTC; por defecto, ahora.
    Retorna:
        bytes: payload Protobuf.
    Excepciones:
        ValueError, TypeError: seq fuera de 0..255 o valor invalido para su tipo.
    """
    payload = pb.Payload()
    payload.timestamp = ahora_ms() if timestamp is None else timestamp
    if seq is not None:
        if not 0 <= seq <= 255:
            raise ValueError(f"seq fuera de 0..255: {seq}")
        payload.seq = seq
    for m in metricas:
        nueva = payload.metrics.add()
        if m.nombre is not None:
            nueva.name = m.nombre
        if m.alias is not None:
            nueva.alias = m.alias
        nueva.timestamp = payload.timestamp if m.timestamp is None else m.timestamp
        poner_valor(nueva, m.tipo, m.valor)
    return payload.SerializeToString()


def decodificar(datos: bytes) -> pb.Payload:
    """
    Payload Sparkplug B desde bytes.

    Excepciones:
        ValueError: los bytes no son un Payload Protobuf valido.
    """
    payload = pb.Payload()
    try:
        payload.ParseFromString(datos)
    except Exception as exc:                     # google.protobuf.message.DecodeError
        raise ValueError(f"payload Protobuf invalido: {exc}") from exc
    return payload


def describir(datos: bytes, resolver_alias=None) -> dict[str, Any]:
    """
    Payload como dict apto para JSON (registro y anexo del informe).

    Parametros:
        resolver_alias (Callable[[int], tuple[str, str] | None] | None): alias -> (nombre, tipo),
            para mostrar el nombre de las metricas que viajan solo con alias.
    """
    p = decodificar(datos)
    metricas = []
    for m in p.metrics:
        nombre, tipo = (m.name or None), (pb.DataType.Name(m.datatype) if m.datatype else None)
        if (not nombre or not tipo) and m.HasField("alias") and resolver_alias:
            definido = resolver_alias(m.alias)
            if definido:
                nombre, tipo = nombre or definido[0], tipo or definido[1]
        try:
            valor = leer_valor(m, tipo)
        except ValueError as exc:
            valor = f"<{exc}>"
        metricas.append({"nombre": nombre, "alias": m.alias if m.HasField("alias") else None,
                         "tipo": tipo, "valor": valor, "timestamp": m.timestamp or None})
    return {"timestamp": p.timestamp if p.HasField("timestamp") else None,
            "seq": p.seq if p.HasField("seq") else None, "metricas": metricas}


def payload_state(online: bool, timestamp: int) -> bytes:
    """STATE de una Host Application: JSON UTF-8 {"online": bool, "timestamp": ms} (Sparkplug 3.0)."""
    return json.dumps({"online": online, "timestamp": timestamp}).encode("utf-8")


def leer_state(datos: bytes) -> tuple[bool, int] | None:
    """(online, timestamp) de un STATE, o None si no cumple el formato (se ignora, no se adivina)."""
    try:
        d = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("online"), bool) or not isinstance(d.get("timestamp"), int):
        return None
    return d["online"], d["timestamp"]
