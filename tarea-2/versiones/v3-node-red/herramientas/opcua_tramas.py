# -*- coding: utf-8 -*-
"""
opcua_tramas.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-13
Version: 1.0

Descripcion general
-------------------
Codificador y decodificador del transporte binario OPC UA (UA TCP + UA Binary,
IEC 62541-6) para el subconjunto de mensajes que usa la Tarea 2. Corre en la
PC con CPython, no en las Raspberry Pi.

Cubre la consigna, Parte 4:
  - 4.4 Encapsulamiento: con --ethernet decodifica tambien las cabeceras
    Ethernet II, IPv4 y TCP de una trama copiada de Wireshark
    ("Copy > ...as Hex Stream").
  - 4.5 Decodificacion byte a byte: imprime cada campo con su desplazamiento,
    bytes en hexadecimal, tipo, valor y significado.

Por que una herramienta propia y no solo el disector de Wireshark: Wireshark
muestra los valores, pero no explica la codificacion (mascara del NodeId,
mascara del DataValue, byte de tipo del Variant, orden little-endian). Recorrer
el mensaje con un codigo propio es la evidencia de que esa codificacion se
entiende, igual que el CRC propio de la Tarea 1.

Mensajes soportados
-------------------
HEL, ACK, ERR, OPN (cabeceras), CLO, y dentro de MSG: ReadRequest/Response,
WriteRequest/Response, PublishRequest/Response (DataChangeNotification y
KeepAlive), ServiceFault. Del resto de los servicios se decodifican las
cabeceras y el RequestHeader/ResponseHeader, y el cuerpo se informa como
"no decodificado" (se ven con Wireshark).

Uso
---
    python opcua_tramas.py                       # autoverificacion + ejemplos
    python opcua_tramas.py "4d 53 47 46 ..."     # decodifica un mensaje OPC UA
    python opcua_tramas.py --ethernet "<hex>"    # trama completa desde Ethernet
    python opcua_tramas.py --markdown "<hex>"    # salida en tabla Markdown

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""

import struct
import sys
from datetime import datetime, timedelta, timezone

# =============================================================================
# 1. TABLAS DE LA ESPECIFICACION
# =============================================================================

#: Identificadores numericos (ns=0) de la codificacion binaria por defecto
#: ("_Encoding_DefaultBinary") de cada servicio. Son los que aparecen como
#: TypeId al inicio del cuerpo de un MSG. Fuente: NodeIds.csv de la OPC
#: Foundation (IEC 62541-6, Anexo A). Verificados contra node-opcua-constants
#: en prueba_opcua_tramas.py.
TIPOS_SERVICIO = {
    397: "ServiceFault",
    422: "FindServersRequest", 425: "FindServersResponse",
    428: "GetEndpointsRequest", 431: "GetEndpointsResponse",
    446: "OpenSecureChannelRequest", 449: "OpenSecureChannelResponse",
    452: "CloseSecureChannelRequest", 455: "CloseSecureChannelResponse",
    461: "CreateSessionRequest", 464: "CreateSessionResponse",
    467: "ActivateSessionRequest", 470: "ActivateSessionResponse",
    473: "CloseSessionRequest", 476: "CloseSessionResponse",
    527: "BrowseRequest", 530: "BrowseResponse",
    554: "TranslateBrowsePathsToNodeIdsRequest", 557: "TranslateBrowsePathsToNodeIdsResponse",
    631: "ReadRequest", 634: "ReadResponse",
    673: "WriteRequest", 676: "WriteResponse",
    751: "CreateMonitoredItemsRequest", 754: "CreateMonitoredItemsResponse",
    787: "CreateSubscriptionRequest", 790: "CreateSubscriptionResponse",
    793: "ModifySubscriptionRequest", 796: "ModifySubscriptionResponse",
    826: "PublishRequest", 829: "PublishResponse",
    832: "RepublishRequest", 835: "RepublishResponse",
    847: "DeleteSubscriptionsRequest", 850: "DeleteSubscriptionsResponse",
}

#: Codificaciones de las estructuras que viajan dentro de ExtensionObject.
TIPOS_EXTENSION = {
    811: "DataChangeNotification",
    820: "StatusChangeNotification",
    916: "EventNotificationList",
    321: "AnonymousIdentityToken",
    324: "UserNameIdentityToken",
    327: "X509IdentityToken",
}

#: StatusCodes que aparecen en este trabajo (IEC 62541-4 §7.39 y
#: StatusCode.csv de la OPC Foundation). El bit 31 en 1 indica "Bad".
STATUS_CODES = {
    0x00000000: "Good",
    0x80050000: "BadCommunicationError",
    0x800A0000: "BadTimeout",
    0x800B0000: "BadServiceUnsupported",
    0x80130000: "BadSecurityChecksFailed",
    0x801A0000: "BadCertificateUntrusted",
    0x801F0000: "BadUserAccessDenied",
    0x80200000: "BadIdentityTokenInvalid",
    0x80210000: "BadIdentityTokenRejected",
    0x80250000: "BadSessionIdInvalid",
    0x80260000: "BadSessionClosed",
    0x80270000: "BadSessionNotActivated",
    0x80340000: "BadNodeIdUnknown",
    0x80350000: "BadAttributeIdInvalid",
    0x803B0000: "BadNotWritable",
    0x803C0000: "BadOutOfRange",
    0x80740000: "BadTypeMismatch",
    0x80780000: "BadTooManyPublishRequests",
    0x80790000: "BadNoSubscription",
    0x80860000: "BadSecureChannelClosed",
    0x808A0000: "BadNotConnected",
    0x80AE0000: "BadConnectionClosed",
}

#: Tipos integrados (Built-in types) que puede llevar un Variant
#: (IEC 62541-6 §5.1.2). Solo los que tienen tamano fijo se decodifican.
TIPOS_INTEGRADOS = {
    1: ("Boolean", "<?", 1), 2: ("SByte", "<b", 1), 3: ("Byte", "<B", 1),
    4: ("Int16", "<h", 2), 5: ("UInt16", "<H", 2), 6: ("Int32", "<i", 4),
    7: ("UInt32", "<I", 4), 8: ("Int64", "<q", 8), 9: ("UInt64", "<Q", 8),
    10: ("Float", "<f", 4), 11: ("Double", "<d", 8),
    12: ("String", None, None), 13: ("DateTime", None, None),
}

#: Bits de la mascara de codificacion del DataValue (IEC 62541-6 §5.2.2.17).
BITS_DATAVALUE = [
    (0x01, "Value"), (0x02, "StatusCode"), (0x04, "SourceTimestamp"),
    (0x08, "ServerTimestamp"), (0x10, "SourcePicoseconds"), (0x20, "ServerPicoseconds"),
]

#: AttributeId (IEC 62541-6 Anexo A.1). 13 = Value es el que se escribe.
ATRIBUTOS = {1: "NodeId", 2: "NodeClass", 3: "BrowseName", 4: "DisplayName",
             13: "Value", 14: "DataType", 17: "AccessLevel", 18: "UserAccessLevel"}

TIMESTAMPS_TO_RETURN = {0: "Source", 1: "Server", 2: "Both", 3: "Neither"}

#: Epoca del DateTime de OPC UA: 1601-01-01 UTC, en unidades de 100 ns
#: (la misma que FILETIME de Windows).
EPOCA_OPCUA = datetime(1601, 1, 1, tzinfo=timezone.utc)


def nombre_status(codigo):
    """
    Nombre simbolico de un StatusCode.

    Parametros
    ----------
    codigo : int
        StatusCode de 32 bits.

    Retorna
    -------
    str
        Nombre conocido, o la severidad (Good/Uncertain/Bad) con el valor en
        hexadecimal si no esta en la tabla.

    Excepciones
    -----------
    Ninguna.
    """
    if codigo in STATUS_CODES:
        return STATUS_CODES[codigo]
    severidad = {0: "Good", 1: "Uncertain", 2: "Bad", 3: "Bad"}[codigo >> 30]
    return "{} (0x{:08X})".format(severidad, codigo)


def datetime_a_texto(ticks):
    """
    Convierte un DateTime de OPC UA (Int64, 100 ns desde 1601-01-01 UTC) a
    texto ISO 8601. El valor 0 significa "sin fecha".

    Parametros
    ----------
    ticks : int
        Valor crudo del campo.

    Retorna
    -------
    str

    Excepciones
    -----------
    Ninguna: un valor fuera de rango se informa como tal.
    """
    if ticks == 0:
        return "nulo (0)"
    try:
        instante = EPOCA_OPCUA + timedelta(microseconds=ticks // 10)
        return instante.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"
    except OverflowError:
        return "fuera de rango ({})".format(ticks)


def texto_a_datetime(instante):
    """
    Inversa de datetime_a_texto(): datetime (con zona) a ticks de 100 ns.

    Parametros
    ----------
    instante : datetime
        Fecha con tzinfo.

    Retorna
    -------
    int

    Excepciones
    -----------
    ValueError si el datetime no tiene zona horaria.
    """
    if instante.tzinfo is None:
        raise ValueError("el datetime debe tener zona horaria")
    delta = instante - EPOCA_OPCUA
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


# =============================================================================
# 2. DECODIFICADOR
# =============================================================================

class TramaIncompleta(ValueError):
    """Se intento leer mas alla del final del mensaje."""


class Lector:
    """
    Recorre un mensaje de bytes y registra cada campo leido.

    Responsabilidad: es la unica clase que toca los bytes crudos. Cada lectura
    primitiva agrega un registro (desplazamiento, bytes, nombre, tipo, valor,
    significado) a `campos`, que luego se imprime como volcado anotado.

    Atributos
    ---------
    datos : bytes
        Mensaje completo.
    pos : int
        Desplazamiento de la proxima lectura.
    campos : list[dict]
        Campos decodificados, en orden.
    prefijo : list[str]
        Pila de nombres de la estructura actual ("RequestHeader", ...), para
        que cada campo se imprima con su ruta completa.
    """

    def __init__(self, datos, desplazamiento_base=0):
        self.datos = bytes(datos)
        self.pos = 0
        self.base = desplazamiento_base
        self.campos = []
        self.prefijo = []

    # ---- infraestructura -------------------------------------------------

    def _tomar(self, n):
        if self.pos + n > len(self.datos):
            raise TramaIncompleta(
                "se pidieron {} bytes en el desplazamiento {} y quedan {}".format(
                    n, self.pos, len(self.datos) - self.pos))
        trozo = self.datos[self.pos:self.pos + n]
        self.pos += n
        return trozo

    def registrar(self, inicio, nombre, tipo, valor, significado=""):
        """Agrega un campo ya leido (desde `inicio` hasta la posicion actual)."""
        ruta = ".".join(self.prefijo + [nombre]) if nombre else ".".join(self.prefijo)
        self.campos.append({
            "offset": self.base + inicio,
            "bytes": self.datos[inicio:self.pos],
            "campo": ruta,
            "tipo": tipo,
            "valor": valor,
            "significado": significado,
        })

    def entrar(self, nombre):
        self.prefijo.append(nombre)

    def salir(self):
        self.prefijo.pop()

    def restante(self):
        return len(self.datos) - self.pos

    # ---- tipos primitivos (todos little-endian, IEC 62541-6 §5.2.2) -------

    def _primitivo(self, fmt, n, nombre, tipo, significado):
        inicio = self.pos
        valor = struct.unpack(fmt, self._tomar(n))[0]
        texto = significado(valor) if callable(significado) else significado
        self.registrar(inicio, nombre, tipo, valor, texto)
        return valor

    def byte(self, nombre, significado=""):
        return self._primitivo("<B", 1, nombre, "Byte", significado)

    def boolean(self, nombre, significado=""):
        return self._primitivo("<?", 1, nombre, "Boolean", significado)

    def uint16(self, nombre, significado=""):
        return self._primitivo("<H", 2, nombre, "UInt16", significado)

    def uint32(self, nombre, significado=""):
        return self._primitivo("<I", 4, nombre, "UInt32", significado)

    def int32(self, nombre, significado=""):
        return self._primitivo("<i", 4, nombre, "Int32", significado)

    def double(self, nombre, significado=""):
        return self._primitivo("<d", 8, nombre, "Double", significado)

    def status_code(self, nombre):
        return self._primitivo("<I", 4, nombre, "StatusCode", nombre_status)

    def date_time(self, nombre):
        return self._primitivo("<q", 8, nombre, "DateTime", datetime_a_texto)

    def ascii(self, n, nombre, significado=""):
        inicio = self.pos
        valor = self._tomar(n).decode("ascii", errors="replace")
        self.registrar(inicio, nombre, "ASCII[{}]".format(n), valor, significado)
        return valor

    def string(self, nombre, significado=""):
        """String: Int32 de longitud (-1 = nulo) seguido de los bytes UTF-8."""
        inicio = self.pos
        largo = struct.unpack("<i", self._tomar(4))[0]
        if largo < 0:
            valor = None
        else:
            valor = self._tomar(largo).decode("utf-8", errors="replace")
        self.registrar(inicio, nombre, "String", valor,
                       significado or ("nulo (longitud -1)" if valor is None
                                       else "longitud {} + texto UTF-8".format(largo)))
        return valor

    def byte_string(self, nombre, significado=""):
        inicio = self.pos
        largo = struct.unpack("<i", self._tomar(4))[0]
        valor = None if largo < 0 else self._tomar(largo)
        texto = significado or ("nulo (longitud -1)" if valor is None
                                else "{} bytes".format(largo))
        self.registrar(inicio, nombre, "ByteString",
                       None if valor is None else valor.hex(" "), texto)
        return valor

    # ---- tipos compuestos -----------------------------------------------

    def node_id(self, nombre, tabla=None):
        """
        NodeId codificado (IEC 62541-6 §5.2.2.9). El primer byte es la mascara
        de codificacion, que define el formato de lo que sigue:
          0x00 TwoByte   : 1 byte de identificador, ns = 0
          0x01 FourByte  : 1 byte de ns + UInt16 de identificador
          0x02 Numeric   : UInt16 de ns + UInt32 de identificador
          0x03 String    : UInt16 de ns + String
          0x04 Guid      : UInt16 de ns + 16 bytes
          0x05 ByteString: UInt16 de ns + ByteString
        Los bits 0x80 y 0x40 solo se usan en ExpandedNodeId.

        Retorna
        -------
        tuple (ns, identificador)
        """
        inicio = self.pos
        mascara = self._tomar(1)[0]
        formato = mascara & 0x3F
        if formato == 0x00:
            ns, ident, desc = 0, self._tomar(1)[0], "TwoByte"
        elif formato == 0x01:
            ns = self._tomar(1)[0]
            ident, desc = struct.unpack("<H", self._tomar(2))[0], "FourByte"
        elif formato == 0x02:
            ns, ident = struct.unpack("<HI", self._tomar(6))
            desc = "Numeric"
        elif formato == 0x03:
            ns = struct.unpack("<H", self._tomar(2))[0]
            largo = struct.unpack("<i", self._tomar(4))[0]
            ident = "" if largo < 0 else self._tomar(largo).decode("utf-8", errors="replace")
            desc = "String"
        elif formato == 0x04:
            ns = struct.unpack("<H", self._tomar(2))[0]
            ident, desc = self._tomar(16).hex(), "Guid"
        elif formato == 0x05:
            ns = struct.unpack("<H", self._tomar(2))[0]
            largo = struct.unpack("<i", self._tomar(4))[0]
            ident = "" if largo < 0 else self._tomar(largo).hex()
            desc = "ByteString"
        else:
            raise ValueError("mascara de NodeId desconocida: 0x{:02X}".format(mascara))
        if mascara & 0x80:  # ExpandedNodeId con NamespaceUri
            largo = struct.unpack("<i", self._tomar(4))[0]
            if largo > 0:
                self._tomar(largo)
        if mascara & 0x40:  # ExpandedNodeId con ServerIndex
            self._tomar(4)
        texto_id = ("s=" + ident) if desc == "String" else (
            ("g=" if desc == "Guid" else "b=" if desc == "ByteString" else "i=") + str(ident))
        valor = "ns={};{}".format(ns, texto_id)
        significado = "mascara 0x{:02X} ({})".format(mascara, desc)
        if tabla and isinstance(ident, int) and ns == 0 and ident in tabla:
            significado += " -> " + tabla[ident]
        self.registrar(inicio, nombre, "NodeId", valor, significado)
        return ns, ident

    def extension_object(self, nombre, decodificar_cuerpo=None):
        """
        ExtensionObject: NodeId del tipo + byte de codificacion
        (0x00 sin cuerpo, 0x01 cuerpo binario, 0x02 XML) + Int32 de longitud +
        cuerpo. Si el tipo es conocido y se paso un decodificador, se
        decodifica el cuerpo en el lugar.
        """
        self.entrar(nombre)
        _, tipo = self.node_id("TypeId", TIPOS_EXTENSION)
        codificacion = self.byte("Encoding", lambda v: {0: "sin cuerpo", 1: "cuerpo binario",
                                                        2: "cuerpo XML"}.get(v, "?"))
        if codificacion in (1, 2):
            largo = self.int32("Length", "bytes del cuerpo")
            fin = self.pos + largo
            if decodificar_cuerpo and tipo in decodificar_cuerpo:
                decodificar_cuerpo[tipo](self)
                self.pos = fin
            else:
                inicio = self.pos
                self._tomar(largo)
                self.registrar(inicio, "Cuerpo", "Byte[]", "...", "no decodificado")
        self.salir()
        return tipo

    def variant(self, nombre):
        """
        Variant (IEC 62541-6 §5.2.2.16): un byte de mascara cuyos 6 bits bajos
        son el tipo integrado y el bit 0x80 indica arreglo; luego el valor en
        su codificacion propia. Un Boolean ocupa 1 byte (0x00/0x01); un UInt16,
        2 bytes little-endian.
        """
        self.entrar(nombre)
        mascara = self.byte("EncodingMask",
                            lambda v: "tipo {} = {}{}".format(
                                v & 0x3F, TIPOS_INTEGRADOS.get(v & 0x3F, ("?",))[0],
                                ", arreglo" if v & 0x80 else ""))
        tipo = mascara & 0x3F
        if mascara & 0x80:
            cantidad = self.int32("ArrayLength")
            valores = [self._valor_integrado(tipo, "[{}]".format(i)) for i in range(max(cantidad, 0))]
            self.salir()
            return valores
        valor = self._valor_integrado(tipo, "Value")
        self.salir()
        return valor

    def _valor_integrado(self, tipo, nombre):
        if tipo not in TIPOS_INTEGRADOS:
            raise ValueError("tipo de Variant no soportado: {}".format(tipo))
        nombre_tipo, fmt, n = TIPOS_INTEGRADOS[tipo]
        if nombre_tipo == "String":
            return self.string(nombre)
        if nombre_tipo == "DateTime":
            return self.date_time(nombre)
        inicio = self.pos
        valor = struct.unpack(fmt, self._tomar(n))[0]
        significado = ""
        if nombre_tipo == "UInt16":
            significado = "0x{:04X}: byte bajo 0x{:02X} primero (little-endian)".format(
                valor, valor & 0xFF)
        elif nombre_tipo == "Boolean":
            significado = "1 byte: 0x00 = false, 0x01 = true"
        self.registrar(inicio, nombre, nombre_tipo, valor, significado)
        return valor

    def data_value(self, nombre):
        """
        DataValue (IEC 62541-6 §5.2.2.17): mascara de un byte que indica que
        campos opcionales siguen, en este orden fijo: Value, StatusCode,
        SourceTimestamp, SourcePicoseconds, ServerTimestamp, ServerPicoseconds.
        Un campo ausente no ocupa bytes: un StatusCode Good no se envia.
        """
        self.entrar(nombre)
        mascara = self.byte("EncodingMask", lambda v: " + ".join(
            n for b, n in BITS_DATAVALUE if v & b) or "vacio")
        resultado = {}
        if mascara & 0x01:
            resultado["valor"] = self.variant("Value")
        if mascara & 0x02:
            resultado["status"] = self.status_code("StatusCode")
        if mascara & 0x04:
            resultado["source_ts"] = self.date_time("SourceTimestamp")
        if mascara & 0x10:
            self.uint16("SourcePicoseconds")
        if mascara & 0x08:
            resultado["server_ts"] = self.date_time("ServerTimestamp")
        if mascara & 0x20:
            self.uint16("ServerPicoseconds")
        self.salir()
        return resultado

    def diagnostic_info(self, nombre):
        """DiagnosticInfo: solo se soporta el caso vacio (mascara 0x00)."""
        mascara = self.byte(nombre, lambda v: "vacio" if v == 0 else "con campos")
        if mascara != 0:
            raise ValueError("DiagnosticInfo con contenido no soportado")

    def arreglo(self, nombre, leer_elemento):
        """Arreglo: Int32 de cantidad (-1 = nulo) y luego cada elemento."""
        cantidad = self.int32(nombre + ".Length",
                              lambda v: "arreglo nulo" if v < 0 else "{} elemento(s)".format(v))
        elementos = []
        for i in range(max(cantidad, 0)):
            self.entrar("{}[{}]".format(nombre, i))
            elementos.append(leer_elemento(self))
            self.salir()
        return elementos


# ---- cabeceras de servicio ------------------------------------------------

def leer_request_header(lec):
    """RequestHeader (IEC 62541-4 §7.33)."""
    lec.entrar("RequestHeader")
    lec.node_id("AuthenticationToken")
    lec.date_time("Timestamp")
    lec.uint32("RequestHandle", "lo elige el cliente; la respuesta lo devuelve igual")
    lec.uint32("ReturnDiagnostics", lambda v: "sin diagnosticos" if v == 0 else "mascara 0x{:X}".format(v))
    lec.string("AuditEntryId")
    lec.uint32("TimeoutHint", lambda v: "{} ms".format(v) if v else "sin limite")
    lec.extension_object("AdditionalHeader")
    lec.salir()


def leer_response_header(lec):
    """ResponseHeader (IEC 62541-4 §7.34)."""
    lec.entrar("ResponseHeader")
    lec.date_time("Timestamp")
    lec.uint32("RequestHandle", "igual al de la peticion: asi se empareja")
    lec.status_code("ServiceResult")
    lec.diagnostic_info("ServiceDiagnostics")
    lec.arreglo("StringTable", lambda l: l.string("String"))
    lec.extension_object("AdditionalHeader")
    lec.salir()


# ---- cuerpos de servicio --------------------------------------------------

def _write_value(lec):
    lec.node_id("NodeId")
    lec.uint32("AttributeId", lambda v: ATRIBUTOS.get(v, "?"))
    lec.string("IndexRange")
    return lec.data_value("Value")


def _read_value_id(lec):
    lec.node_id("NodeId")
    lec.uint32("AttributeId", lambda v: ATRIBUTOS.get(v, "?"))
    lec.string("IndexRange")
    lec.uint16("DataEncoding.NamespaceIndex")
    lec.string("DataEncoding.Name")


def _data_change_notification(lec):
    lec.entrar("DataChangeNotification")

    def item(l):
        l.uint32("ClientHandle", "identificador del MonitoredItem elegido por el cliente")
        return l.data_value("Value")

    lec.arreglo("MonitoredItems", item)
    lec.arreglo("DiagnosticInfos", lambda l: l.diagnostic_info("DiagnosticInfo"))
    lec.salir()


def _signature_data(lec, nombre):
    lec.entrar(nombre)
    lec.string("Algorithm")
    lec.byte_string("Signature")
    lec.salir()


def _anonymous_identity_token(lec):
    lec.entrar("AnonymousIdentityToken")
    lec.string("PolicyId", "politica de token anonimo anunciada en el endpoint")
    lec.salir()


def _username_identity_token(lec):
    lec.entrar("UserNameIdentityToken")
    lec.string("PolicyId", "politica de token de usuario anunciada en el endpoint")
    lec.string("UserName", "viaja sin cifrar dentro del token: lo protege solo el canal")
    lec.byte_string("Password")
    algoritmo = lec.string("EncryptionAlgorithm")
    campo_clave = lec.campos[-2]
    if algoritmo:
        campo_clave["significado"] = ("CIFRADA con la clave publica del servidor ({}): "
                                      "longitud + clave + ServerNonce").format(algoritmo.split("#")[-1])
    else:
        campo_clave["significado"] = "EN CLARO: sin EncryptionAlgorithm la contrasena es legible"
    lec.salir()


CUERPOS_EXTENSION = {
    811: _data_change_notification,
    321: _anonymous_identity_token,
    324: _username_identity_token,
}


def _cuerpo_write_request(lec):
    lec.arreglo("NodesToWrite", _write_value)


def _cuerpo_write_response(lec):
    lec.arreglo("Results", lambda l: l.status_code("StatusCode"))
    lec.arreglo("DiagnosticInfos", lambda l: l.diagnostic_info("DiagnosticInfo"))


def _cuerpo_read_request(lec):
    lec.double("MaxAge", lambda v: "0 = leer el valor actual" if v == 0 else "{} ms".format(v))
    lec.uint32("TimestampsToReturn", lambda v: TIMESTAMPS_TO_RETURN.get(v, "?"))
    lec.arreglo("NodesToRead", _read_value_id)


def _cuerpo_read_response(lec):
    lec.arreglo("Results", lambda l: l.data_value("DataValue"))
    lec.arreglo("DiagnosticInfos", lambda l: l.diagnostic_info("DiagnosticInfo"))


def _cuerpo_publish_request(lec):
    def ack(l):
        l.uint32("SubscriptionId")
        l.uint32("SequenceNumber", "confirma la notificacion con ese numero")

    lec.arreglo("SubscriptionAcknowledgements", ack)


def _cuerpo_publish_response(lec):
    lec.uint32("SubscriptionId")
    lec.arreglo("AvailableSequenceNumbers", lambda l: l.uint32("SequenceNumber"))
    lec.boolean("MoreNotifications")
    lec.entrar("NotificationMessage")
    lec.uint32("SequenceNumber")
    lec.date_time("PublishTime")
    datos = lec.arreglo("NotificationData",
                        lambda l: l.extension_object("Notification", CUERPOS_EXTENSION))
    if not datos:
        lec.campos[-1]["significado"] += " -> KeepAlive (sin notificaciones)"
    lec.salir()
    lec.arreglo("Results", lambda l: l.status_code("StatusCode"))
    lec.arreglo("DiagnosticInfos", lambda l: l.diagnostic_info("DiagnosticInfo"))


MODOS_SEGURIDAD = {0: "Invalid", 1: "None", 2: "Sign", 3: "SignAndEncrypt"}


def _cuerpo_open_request(lec):
    lec.uint32("ClientProtocolVersion")
    lec.uint32("RequestType", lambda v: {0: "Issue (canal nuevo)", 1: "Renew (renovar claves)"}.get(v, "?"))
    lec.uint32("SecurityMode", lambda v: MODOS_SEGURIDAD.get(v, "?"))
    nonce = lec.byte_string("ClientNonce")
    lec.campos[-1]["significado"] = ("vacio: modo None, no se derivan claves" if not nonce
                                     else "aleatorio; con el ServerNonce deriva las claves simetricas")
    lec.uint32("RequestedLifetime", lambda v: "{} ms de vida del token".format(v))


def _cuerpo_open_response(lec):
    lec.uint32("ServerProtocolVersion")
    lec.entrar("SecurityToken")
    lec.uint32("ChannelId", "SecureChannelId que usaran todos los MSG siguientes")
    lec.uint32("TokenId", "TokenId que usaran todos los MSG siguientes")
    lec.date_time("CreatedAt")
    lec.uint32("RevisedLifetime", lambda v: "{} ms (al 75 % el cliente renueva con OPN Renew)".format(v))
    lec.salir()
    lec.byte_string("ServerNonce")


def _cuerpo_create_subscription_request(lec):
    lec.double("RequestedPublishingInterval", lambda v: "{:g} ms".format(v))
    lec.uint32("RequestedLifetimeCount", "en ciclos de publicacion")
    lec.uint32("RequestedMaxKeepAliveCount", "ciclos sin cambios antes de un KeepAlive")
    lec.uint32("MaxNotificationsPerPublish", lambda v: "sin limite" if v == 0 else "")
    lec.boolean("PublishingEnabled")
    lec.byte("Priority")


def _cuerpo_create_subscription_response(lec):
    lec.uint32("SubscriptionId")
    lec.double("RevisedPublishingInterval", lambda v: "{:g} ms (valor que rige)".format(v))
    lec.uint32("RevisedLifetimeCount")
    lec.uint32("RevisedMaxKeepAliveCount")


def _item_create_request(lec):
    lec.entrar("ItemToMonitor")
    _read_value_id(lec)
    lec.salir()
    lec.uint32("MonitoringMode", lambda v: {0: "Disabled", 1: "Sampling", 2: "Reporting"}.get(v, "?"))
    lec.entrar("RequestedParameters")
    lec.uint32("ClientHandle")
    lec.double("SamplingInterval", lambda v: "{:g} ms pedido".format(v))
    lec.extension_object("Filter")
    lec.uint32("QueueSize")
    lec.boolean("DiscardOldest")
    lec.salir()


def _item_create_result(lec):
    lec.status_code("StatusCode")
    lec.uint32("MonitoredItemId")
    lec.double("RevisedSamplingInterval", lambda v: "{:g} ms (valor que rige)".format(v))
    lec.uint32("RevisedQueueSize")
    lec.extension_object("FilterResult")


def _cuerpo_create_monitored_request(lec):
    lec.uint32("SubscriptionId")
    lec.uint32("TimestampsToReturn", lambda v: TIMESTAMPS_TO_RETURN.get(v, "?"))
    lec.arreglo("ItemsToCreate", _item_create_request)


def _cuerpo_create_monitored_response(lec):
    lec.arreglo("Results", _item_create_result)
    lec.arreglo("DiagnosticInfos", lambda l: l.diagnostic_info("DiagnosticInfo"))


def _cuerpo_activate_session_request(lec):
    _signature_data(lec, "ClientSignature")

    def certificado(l):
        l.byte_string("CertificateData")
        l.byte_string("Signature")

    lec.arreglo("ClientSoftwareCertificates", certificado)
    lec.arreglo("LocaleIds", lambda l: l.string("LocaleId"))
    lec.extension_object("UserIdentityToken", CUERPOS_EXTENSION)
    _signature_data(lec, "UserTokenSignature")


def _cuerpo_close_session_request(lec):
    lec.boolean("DeleteSubscriptions")


#: tipo de servicio -> (es_peticion, decodificador del cuerpo o None).
#: None = solo se decodifica la cabecera (RequestHeader/ResponseHeader).
SERVICIOS = {
    631: (True, _cuerpo_read_request), 634: (False, _cuerpo_read_response),
    673: (True, _cuerpo_write_request), 676: (False, _cuerpo_write_response),
    826: (True, _cuerpo_publish_request), 829: (False, _cuerpo_publish_response),
    446: (True, _cuerpo_open_request), 449: (False, _cuerpo_open_response),
    787: (True, _cuerpo_create_subscription_request), 790: (False, _cuerpo_create_subscription_response),
    751: (True, _cuerpo_create_monitored_request), 754: (False, _cuerpo_create_monitored_response),
    467: (True, _cuerpo_activate_session_request),
    473: (True, _cuerpo_close_session_request), 476: (False, None),
    452: (True, None), 397: (False, None),
}

#: Servicios que no tienen nada despues de la cabecera.
SIN_CUERPO = {452, 397, 476}


def _opaco(lec, inicio_campos, inicio_pos, motivo):
    """Descarta lo decodificado desde un punto y marca el resto como opaco."""
    del lec.campos[inicio_campos:]
    lec.prefijo = []
    lec.pos = inicio_pos
    if lec.restante() > 0:
        lec._tomar(lec.restante())
        lec.registrar(inicio_pos, "Opaco", "Byte[]", "...", motivo)


def _cuerpo_servicio(lec):
    """
    Decodifica TypeId + cabecera + cuerpo. Si los bytes no forman un servicio
    conocido (canal SignAndEncrypt: todo esta cifrado) retrocede y devuelve
    None, para no mostrar campos inventados a partir de bytes cifrados.

    Retorna
    -------
    str | None
        Nombre del servicio, o None si el contenido no es interpretable.
    """
    inicio_campos, inicio_pos = len(lec.campos), lec.pos
    try:
        _, ident = lec.node_id("TypeId", TIPOS_SERVICIO)
    except (ValueError, TramaIncompleta):
        ident = None
    if ident not in TIPOS_SERVICIO:
        del lec.campos[inicio_campos:]
        lec.pos = inicio_pos
        return None
    servicio = TIPOS_SERVICIO[ident]
    es_peticion, cuerpo = SERVICIOS.get(ident, (servicio.endswith("Request"), None))
    completo = ident in SIN_CUERPO
    lec.entrar(servicio)
    try:
        (leer_request_header if es_peticion else leer_response_header)(lec)
        if cuerpo:
            cuerpo(lec)
            completo = True
    except (ValueError, TramaIncompleta):
        _opaco(lec, inicio_campos, inicio_pos, "no se pudo decodificar (cifrado o servicio no soportado)")
        return None
    lec.salir()
    if lec.restante() > 0:
        inicio = lec.pos
        n = lec.restante()
        lec._tomar(n)
        if completo and n == 32:
            motivo = "firma HMAC-SHA256 (32 bytes): canal en modo Sign"
        elif completo:
            motivo = "relleno + firma"
        else:
            motivo = "cuerpo de este servicio: no lo decodifica esta herramienta (ver Wireshark)"
        lec.registrar(inicio, "Resto", "Byte[]", "...", motivo)
    return servicio


def decodificar_opcua(datos, desplazamiento_base=0):
    """
    Decodifica UN mensaje UA TCP completo (desde MessageType).

    Parametros
    ----------
    datos : bytes
        El mensaje OPC UA (carga util TCP).
    desplazamiento_base : int
        Desplazamiento del primer byte dentro de la trama Ethernet, para que
        los offsets impresos coincidan con Wireshark cuando se usa --ethernet.

    Retorna
    -------
    dict
        {"tipo": "MSG", "servicio": "WriteRequest" | None, "cifrado": bool,
         "campos": [...], "resumen": {...}}

    Excepciones
    -----------
    TramaIncompleta si la cabecera de 8 bytes esta truncada. Un cuerpo cifrado
    NO es una excepcion: se marca como "Opaco" y cifrado = True.
    """
    lec = Lector(datos, desplazamiento_base)
    resumen = {}
    cifrado = False

    lec.entrar("Cabecera")
    tipo = lec.ascii(3, "MessageType", "HEL/ACK/ERR/RHE/OPN/MSG/CLO")
    lec.ascii(1, "ChunkType", "F = final, C = intermedio, A = abortado")
    tamano = lec.uint32("MessageSize", "bytes totales del mensaje, cabecera incluida")
    lec.salir()
    resumen["tipo"], resumen["tamano"] = tipo, tamano
    if tamano != len(datos):
        resumen["advertencia"] = "MessageSize ({}) distinto de los bytes recibidos ({})".format(
            tamano, len(datos))

    servicio = None
    if tipo in ("HEL", "ACK"):
        lec.entrar(tipo)
        lec.uint32("ProtocolVersion")
        lec.uint32("ReceiveBufferSize", "bytes")
        lec.uint32("SendBufferSize", "bytes")
        lec.uint32("MaxMessageSize", lambda v: "sin limite" if v == 0 else "bytes")
        lec.uint32("MaxChunkCount", lambda v: "sin limite" if v == 0 else "chunks")
        if tipo == "HEL":
            lec.string("EndpointUrl")
        lec.salir()
    elif tipo == "ERR":
        lec.status_code("Error")
        lec.string("Reason")
    elif tipo in ("OPN", "MSG", "CLO"):
        lec.uint32("SecureChannelId", "0 en el primer OPN; luego lo asigna el servidor")
        legible = True
        if tipo == "OPN":
            lec.entrar("CabeceraSeguridadAsimetrica")
            politica = lec.string("SecurityPolicyUri") or ""
            lec.byte_string("SenderCertificate")
            lec.byte_string("ReceiverCertificateThumbprint")
            lec.salir()
            if not politica.endswith("#None"):
                # Con una politica real el OPN va firmado con la clave privada
                # del emisor y cifrado con la publica del receptor (RSA): desde
                # la cabecera de secuencia en adelante no hay nada legible.
                legible = False
                inicio = lec.pos
                lec._tomar(lec.restante())
                lec.registrar(inicio, "Opaco", "Byte[]", "...",
                              "cifrado asimetrico (RSA-OAEP) con el certificado del receptor + firma RSA")
        else:
            lec.entrar("CabeceraSeguridadSimetrica")
            lec.uint32("TokenId", "identifica las claves simetricas vigentes del canal")
            lec.salir()
        if legible:
            inicio_campos, inicio_pos = len(lec.campos), lec.pos
            lec.entrar("CabeceraSecuencia")
            lec.uint32("SequenceNumber", "crece en 1 por chunk enviado; detecta perdidas y repeticiones")
            lec.uint32("RequestId", "empareja peticion y respuesta")
            lec.salir()
            servicio = _cuerpo_servicio(lec)
            if servicio is None:
                # Sin TypeId valido, la cabecera de secuencia tambien estaba
                # cifrada: SignAndEncrypt cifra desde ella hasta la firma.
                _opaco(lec, inicio_campos, inicio_pos,
                       "cifrado (SignAndEncrypt): cabecera de secuencia, cuerpo, relleno y firma; "
                       "en claro solo quedan MessageType, MessageSize, SecureChannelId y TokenId")
        cifrado = any(c["campo"] == "Opaco" for c in lec.campos)
    if lec.restante() > 0:
        inicio = lec.pos
        lec._tomar(lec.restante())
        lec.registrar(inicio, "Resto", "Byte[]", "...", "no decodificado")
    resumen["servicio"] = servicio
    return {"tipo": tipo, "servicio": servicio, "cifrado": cifrado,
            "campos": lec.campos, "resumen": resumen}


# =============================================================================
# 3. ENCAPSULAMIENTO: Ethernet II / IPv4 / TCP (consigna Parte 4.4)
# =============================================================================

def decodificar_ethernet(trama):
    """
    Decodifica una trama Ethernet II con IPv4 y TCP y luego el mensaje OPC UA
    que transporta.

    Parametros
    ----------
    trama : bytes
        Trama tal como la copia Wireshark (sin preambulo ni FCS, que la placa
        de red agrega y quita en hardware).

    Retorna
    -------
    dict
        Como decodificar_opcua(), con los campos de las tres capas inferiores
        al principio y "capas": bytes por capa.

    Excepciones
    -----------
    ValueError si no es IPv4/TCP.
    """
    lec = Lector(trama)
    capas = {}

    lec.entrar("Ethernet")
    inicio = lec.pos
    lec._tomar(6)
    lec.registrar(inicio, "Destino", "MAC", trama[0:6].hex(":"))
    inicio = lec.pos
    lec._tomar(6)
    lec.registrar(inicio, "Origen", "MAC", trama[6:12].hex(":"))
    inicio = lec.pos
    ethertype = struct.unpack(">H", lec._tomar(2))[0]
    lec.registrar(inicio, "EtherType", "UInt16 BE", "0x{:04X}".format(ethertype),
                  "0x0800 = IPv4 (big-endian, orden de red)")
    lec.salir()
    capas["Ethernet"] = 14
    if ethertype != 0x0800:
        raise ValueError("no es IPv4")

    ip = trama[14:]
    ihl = (ip[0] & 0x0F) * 4
    largo_total = struct.unpack(">H", ip[2:4])[0]
    lec.entrar("IPv4")
    campos_ip = [
        (1, "Version/IHL", "0x{:02X}".format(ip[0]), "version 4, cabecera de {} bytes".format(ihl)),
        (1, "DSCP/ECN", "0x{:02X}".format(ip[1]), ""),
        (2, "TotalLength", largo_total, "bytes desde la cabecera IP hasta el final"),
        (2, "Identification", struct.unpack(">H", ip[4:6])[0], ""),
        (2, "Flags/FragmentOffset", "0x{:04X}".format(struct.unpack(">H", ip[6:8])[0]),
         "0x4000 = Don't Fragment"),
        (1, "TTL", ip[8], "saltos restantes"),
        (1, "Protocol", ip[9], "6 = TCP"),
        (2, "HeaderChecksum", "0x{:04X}".format(struct.unpack(">H", ip[10:12])[0]), ""),
        (4, "Origen", ".".join(str(b) for b in ip[12:16]), ""),
        (4, "Destino", ".".join(str(b) for b in ip[16:20]), ""),
    ]
    for n, nombre, valor, sig in campos_ip:
        inicio = lec.pos
        lec._tomar(n)
        lec.registrar(inicio, nombre, "BE", valor, sig)
    if ihl > 20:
        inicio = lec.pos
        lec._tomar(ihl - 20)
        lec.registrar(inicio, "Opciones", "Byte[]", "...", "")
    lec.salir()
    capas["IPv4"] = ihl
    if ip[9] != 6:
        raise ValueError("no es TCP")

    tcp = ip[ihl:]
    largo_tcp = (tcp[12] >> 4) * 4
    lec.entrar("TCP")
    banderas = tcp[13]
    nombres = [n for b, n in ((0x01, "FIN"), (0x02, "SYN"), (0x04, "RST"), (0x08, "PSH"),
                              (0x10, "ACK")) if banderas & b]
    campos_tcp = [
        (2, "PuertoOrigen", struct.unpack(">H", tcp[0:2])[0], ""),
        (2, "PuertoDestino", struct.unpack(">H", tcp[2:4])[0], "4840 = OPC UA"),
        (4, "NumeroSecuencia", struct.unpack(">I", tcp[4:8])[0],
         "primer byte de esta carga dentro del flujo (Wireshark lo muestra relativo)"),
        (4, "NumeroAcuse", struct.unpack(">I", tcp[8:12])[0], "proximo byte que se espera del otro extremo"),
        (1, "DataOffset", tcp[12] >> 4, "cabecera de {} bytes".format(largo_tcp)),
        (1, "Banderas", "0x{:02X}".format(banderas), "+".join(nombres)),
        (2, "Ventana", struct.unpack(">H", tcp[14:16])[0], "bytes que acepta recibir (sin escalar)"),
        (2, "Checksum", "0x{:04X}".format(struct.unpack(">H", tcp[16:18])[0]), ""),
        (2, "Urgente", struct.unpack(">H", tcp[18:20])[0], ""),
    ]
    for n, nombre, valor, sig in campos_tcp:
        inicio = lec.pos
        lec._tomar(n)
        lec.registrar(inicio, nombre, "BE", valor, sig)
    if largo_tcp > 20:
        inicio = lec.pos
        lec._tomar(largo_tcp - 20)
        lec.registrar(inicio, "Opciones", "Byte[]", "...",
                      "{} bytes (Linux agrega Timestamps: 10 + 2 de relleno)".format(largo_tcp - 20))
    lec.salir()
    capas["TCP"] = largo_tcp

    inicio_ua = 14 + ihl + largo_tcp
    fin_ua = 14 + largo_total
    resultado = decodificar_opcua(trama[inicio_ua:fin_ua], desplazamiento_base=inicio_ua)
    resultado["campos"] = lec.campos + resultado["campos"]
    capas["OPC UA"] = fin_ua - inicio_ua
    resultado["capas"] = capas
    return resultado


# =============================================================================
# 4. CODIFICADOR (para generar ejemplos y vectores de prueba)
# =============================================================================

class Escritor:
    """
    Construye mensajes UA Binary. Es la inversa de Lector y existe para:
    (a) generar la trama "esperada" de un Write antes de tener capturas, y
    (b) probar el decodificador con ida y vuelta.
    """

    def __init__(self):
        self.buf = bytearray()

    def byte(self, v): self.buf += struct.pack("<B", v); return self
    def boolean(self, v): self.buf += struct.pack("<?", v); return self
    def uint16(self, v): self.buf += struct.pack("<H", v); return self
    def uint32(self, v): self.buf += struct.pack("<I", v); return self
    def int32(self, v): self.buf += struct.pack("<i", v); return self
    def int64(self, v): self.buf += struct.pack("<q", v); return self
    def double(self, v): self.buf += struct.pack("<d", v); return self

    def string(self, v):
        if v is None:
            return self.int32(-1)
        datos = v.encode("utf-8")
        self.int32(len(datos))
        self.buf += datos
        return self

    def node_id(self, ns, ident):
        """Elige la codificacion mas corta posible, como exige el estandar."""
        if isinstance(ident, str):
            self.byte(0x03).uint16(ns).string(ident)
        elif isinstance(ident, (bytes, bytearray)):
            self.byte(0x05).uint16(ns).int32(len(ident))
            self.buf += ident
        elif ns == 0 and ident <= 0xFF:
            self.byte(0x00).byte(ident)
        elif ns <= 0xFF and ident <= 0xFFFF:
            self.byte(0x01).byte(ns).uint16(ident)
        else:
            self.byte(0x02).uint16(ns).uint32(ident)
        return self

    def extension_object_vacio(self):
        return self.node_id(0, 0).byte(0x00)

    def variant(self, tipo, valor):
        nombre, fmt, _ = TIPOS_INTEGRADOS[tipo]
        self.byte(tipo)
        self.buf += struct.pack(fmt, valor)
        return self

    def data_value(self, tipo=None, valor=None, status=None, source_ts=None, server_ts=None):
        mascara = ((0x01 if tipo is not None else 0) | (0x02 if status is not None else 0) |
                   (0x04 if source_ts is not None else 0) | (0x08 if server_ts is not None else 0))
        self.byte(mascara)
        if tipo is not None:
            self.variant(tipo, valor)
        if status is not None:
            self.uint32(status)
        if source_ts is not None:
            self.int64(source_ts)
        if server_ts is not None:
            self.int64(server_ts)
        return self

    def request_header(self, token, timestamp, handle, timeout_ms):
        self.node_id(*token).int64(timestamp).uint32(handle).uint32(0).string(None)
        return self.uint32(timeout_ms).extension_object_vacio()

    def response_header(self, timestamp, handle, resultado=0):
        self.int64(timestamp).uint32(handle).uint32(resultado).byte(0x00).int32(-1)
        return self.extension_object_vacio()


def envolver_msg(cuerpo, canal=1, token=1, secuencia=1, peticion=1):
    """
    Antepone las cabeceras de un MSG con SecurityMode None: cabecera de
    mensaje (8), SecureChannelId (4), TokenId (4) y cabecera de secuencia (8).

    Retorna
    -------
    bytes
        Mensaje completo con MessageSize correcto.
    """
    resto = struct.pack("<IIII", canal, token, secuencia, peticion) + bytes(cuerpo)
    return b"MSGF" + struct.pack("<I", 8 + len(resto)) + resto


def construir_write_request(ns, identificador, tipo, valor, *, token=(0, 1), timestamp=0,
                            handle=1, timeout_ms=10000, **cabecera):
    """
    WriteRequest de un unico valor al atributo Value (13).

    Parametros
    ----------
    ns : int
        Indice de namespace del nodo destino.
    identificador : str | int
        Identificador del nodo (s= o i=).
    tipo : int
        Tipo integrado del Variant (1 = Boolean, 5 = UInt16).
    valor : bool | int
        Valor a escribir.
    token : tuple (ns, identificador)
        AuthenticationToken de la sesion.
    timestamp : int
        DateTime del RequestHeader.
    handle : int
        RequestHandle.
    timeout_ms : int
        TimeoutHint.
    **cabecera
        canal, token_id (TokenId), secuencia, peticion para envolver_msg().

    Retorna
    -------
    bytes

    Excepciones
    -----------
    struct.error si el valor no entra en el tipo.
    """
    e = Escritor().node_id(0, 673).request_header(token, timestamp, handle, timeout_ms)
    e.int32(1).node_id(ns, identificador).uint32(13).string(None).data_value(tipo, valor)
    return envolver_msg(e.buf, **_cab(cabecera))


def construir_write_response(*, timestamp=0, handle=1, resultado=0, **cabecera):
    """WriteResponse con un unico StatusCode de resultado."""
    e = Escritor().node_id(0, 676).response_header(timestamp, handle)
    e.int32(1).uint32(resultado).int32(0)
    return envolver_msg(e.buf, **_cab(cabecera))


def construir_publish_response(items, *, subscripcion=1, secuencia_notif=1, timestamp=0,
                               handle=1, **cabecera):
    """
    PublishResponse con una DataChangeNotification (o KeepAlive si items es
    vacio).

    Parametros
    ----------
    items : list[tuple(client_handle, tipo, valor, source_ts, server_ts)]
    """
    e = Escritor().node_id(0, 829).response_header(timestamp, handle)
    e.uint32(subscripcion).int32(1).uint32(secuencia_notif).boolean(False)
    e.uint32(secuencia_notif).int64(timestamp)
    if items:
        cuerpo = Escritor().int32(len(items))
        for handle_item, tipo, valor, sts, svts in items:
            cuerpo.uint32(handle_item).data_value(tipo, valor, source_ts=sts, server_ts=svts)
        cuerpo.int32(0)
        e.int32(1).node_id(0, 811).byte(0x01).int32(len(cuerpo.buf))
        e.buf += cuerpo.buf
    else:
        e.int32(0)
    e.int32(0).int32(0)
    return envolver_msg(e.buf, **_cab(cabecera))


def _cab(cabecera):
    """Traduce los nombres de cabecera de construir_* a los de envolver_msg()."""
    mapa = {"canal": "canal", "token_id": "token", "secuencia": "secuencia", "peticion": "peticion"}
    return {mapa[k]: v for k, v in cabecera.items()}


# =============================================================================
# 5. PRESENTACION
# =============================================================================

def parsear_hex(texto):
    """
    Convierte texto hexadecimal en bytes. Acepta espacios, ':' y saltos de
    linea, como los copia Wireshark.

    Excepciones
    -----------
    ValueError si hay caracteres no hexadecimales o cantidad impar de digitos.
    """
    limpio = "".join(c for c in texto if c not in " :\n\r\t-")
    if len(limpio) % 2:
        raise ValueError("cantidad impar de digitos hexadecimales")
    return bytes.fromhex(limpio)


def formatear(resultado, markdown=False):
    """
    Volcado hexadecimal anotado, un campo por linea.

    Parametros
    ----------
    resultado : dict
        Salida de decodificar_opcua() o decodificar_ethernet().
    markdown : bool
        True para emitir una tabla Markdown lista para el informe.

    Retorna
    -------
    str
    """
    lineas = []
    if markdown:
        lineas.append("| Offset | Bytes | Campo | Tipo | Valor | Significado |")
        lineas.append("|---|---|---|---|---|---|")
    for c in resultado["campos"]:
        hexa = c["bytes"].hex(" ")
        if len(hexa) > 47:
            hexa = hexa[:44] + "..."
        valor = "" if c["valor"] is None else str(c["valor"])
        if markdown:
            lineas.append("| {} | `{}` | {} | {} | {} | {} |".format(
                c["offset"], hexa, c["campo"], c["tipo"], valor.replace("|", "\\|"),
                c["significado"]))
        else:
            lineas.append("{:>4}  {:<48} {:<58} {:<10} {}{}".format(
                c["offset"], hexa, c["campo"], c["tipo"], valor,
                ("  # " + c["significado"]) if c["significado"] else ""))
    if "capas" in resultado:
        total = sum(resultado["capas"].values())
        lineas.append("")
        lineas.append("Bytes por capa: " + ", ".join(
            "{} {}".format(k, v) for k, v in resultado["capas"].items()) +
            " = {} (sin preambulo, FCS ni IFG)".format(total))
    if resultado["resumen"].get("advertencia"):
        lineas.append("ADVERTENCIA: " + resultado["resumen"]["advertencia"])
    return "\n".join(lineas)


# =============================================================================
# 6. AUTOVERIFICACION Y EJEMPLOS
# =============================================================================

#: Instante fijo para que los ejemplos sean reproducibles.
INSTANTE_EJEMPLO = texto_a_datetime(datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc))


def autoverificar():
    """
    Verificaciones minimas de ida y vuelta. Las exhaustivas estan en
    prueba_opcua_tramas.py.

    Retorna
    -------
    bool
        True si todas pasan.
    """
    ok = True
    for tipo, valor in ((5, 0x1234), (1, True)):
        msg = construir_write_request(1, "Cliente.Rampa", tipo, valor)
        r = decodificar_opcua(msg)
        hallado = [c["valor"] for c in r["campos"] if c["campo"].endswith("Value.Value")]
        ok &= r["servicio"] == "WriteRequest" and hallado == [valor]
    ok &= datetime_a_texto(INSTANTE_EJEMPLO).startswith("2026-10-13 12:00:00")
    return bool(ok)


def mostrar_ejemplos():
    """Imprime los cuatro mensajes Write de la consigna, Parte 4.5."""
    ejemplos = [
        ("WriteRequest Cliente.Rampa = 0x1234 (4660)",
         construir_write_request(1, "Cliente.Rampa", 5, 0x1234, timestamp=INSTANTE_EJEMPLO,
                                 handle=42, secuencia=57, peticion=7)),
        ("WriteResponse (Good)",
         construir_write_response(timestamp=INSTANTE_EJEMPLO, handle=42, secuencia=58, peticion=7)),
        ("WriteRequest Cliente.EstadoPulsador = true",
         construir_write_request(1, "Cliente.EstadoPulsador", 1, True, timestamp=INSTANTE_EJEMPLO,
                                 handle=43, secuencia=59, peticion=8)),
        ("PublishResponse KeepAlive",
         construir_publish_response([], timestamp=INSTANTE_EJEMPLO, secuencia=60, peticion=9)),
    ]
    for titulo, msg in ejemplos:
        print("\n=== {} ({} bytes) ===".format(titulo, len(msg)))
        print(msg.hex(" "))
        print(formatear(decodificar_opcua(msg)))
    print("\nNota: son mensajes CONSTRUIDOS con la codificacion del estandar. El "
          "AuthenticationToken real depende de la pila del servidor; reemplazar por "
          "las tramas capturadas (evidencia/capturas).")


def main(argumentos):
    """Punto de entrada de linea de comandos."""
    markdown = "--markdown" in argumentos
    ethernet = "--ethernet" in argumentos
    resto = [a for a in argumentos if not a.startswith("--")]
    if not resto:
        estado = autoverificar()
        print("Autoverificacion: " + ("OK" if estado else "FALLA"))
        mostrar_ejemplos()
        return 0 if estado else 1
    try:
        datos = parsear_hex(" ".join(resto))
        resultado = decodificar_ethernet(datos) if ethernet else decodificar_opcua(datos)
    except ValueError as error:
        print("Error: {}".format(error))
        return 2
    print(formatear(resultado, markdown))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
