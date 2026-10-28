# -*- coding: utf-8 -*-
"""
prueba_opcua_tramas.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-13
Version: 1.0

Descripcion general
-------------------
Banco de pruebas de opcua_tramas.py. Corre en la PC, sin hardware ni
node-opcua: usa los vectores de herramientas/vectores/, que son mensajes
REALES generados por la pila node-opcua 2.160.0 con capturar_tramas_local.js
(servidor y cliente del trabajo comunicandose por un proxy TCP local).

Verifica tres cosas:
  1. Que las tablas del decodificador (identificadores de servicio y
     StatusCodes) coinciden con las de la pila real.
  2. Que cada mensaje real se decodifica sin error y con MessageSize
     coherente, en los tres modos de seguridad.
  3. Que los campos que pide la consigna (Partes 3.4, 4.5 y 4.9) aparecen
     con el valor y la codificacion esperados.

Uso
---
    python tarea-2/herramientas/prueba_opcua_tramas.py

Devuelve codigo de salida 0 si todo pasa y 1 si algo falla (igual que
prueba_diagnostico.py de la Tarea 1).

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import opcua_tramas as o  # noqa: E402

fallos = 0


def check(cond, texto):
    global fallos
    print(("  OK   " if cond else "  FALLA") + "  " + texto)
    if not cond:
        fallos += 1


def cargar(nombre):
    with open(os.path.join(AQUI, "vectores", nombre + ".json"), encoding="utf-8") as f:
        return json.load(f)


def decodificar_todos(vector):
    return [(m, o.decodificar_opcua(bytes.fromhex(m["hex"]))) for m in vector["mensajes"]]


def campo(resultado, sufijo):
    """Primer campo cuya ruta termina en `sufijo`."""
    for c in resultado["campos"]:
        if c["campo"].endswith(sufijo):
            return c
    return None


VECTORES = {n: cargar(n) for n in ("sesion_None", "sesion_Sign", "sesion_SignAndEncrypt", "sesion_None_usuario")}
NONE = decodificar_todos(VECTORES["sesion_None"])

# ---------------------------------------------------------------------------
print("\n1. Tablas contra la pila real (node-opcua {})".format(VECTORES["sesion_None"]["node_opcua"]))
for nombre, valor in VECTORES["sesion_None"]["constantes"].items():
    check((o.TIPOS_SERVICIO.get(valor) or o.TIPOS_EXTENSION.get(valor)) == nombre,
          "{} = i={}".format(nombre, valor))
for nombre, valor in VECTORES["sesion_None"]["status"].items():
    check(o.STATUS_CODES.get(valor) == nombre, "{} = 0x{:08X}".format(nombre, valor))

# ---------------------------------------------------------------------------
print("\n2. Todos los mensajes reales se decodifican, en los tres modos")
for nombre, vector in VECTORES.items():
    errores, inconsistentes = 0, 0
    for m in vector["mensajes"]:
        try:
            r = o.decodificar_opcua(bytes.fromhex(m["hex"]))
            inconsistentes += "advertencia" in r["resumen"]
        except Exception:  # noqa: BLE001 - se cuenta cualquier falla
            errores += 1
    check(errores == 0 and inconsistentes == 0,
          "{}: {} mensajes, {} errores, {} con MessageSize incoherente".format(
              nombre, len(vector["mensajes"]), errores, inconsistentes))

# ---------------------------------------------------------------------------
print("\n3. Secuencia de una sesion completa en modo None (Parte 4.2)")
secuencia = [(m["sentido"], r["tipo"], r["servicio"]) for m, r in NONE]
esperada_inicio = [
    ("C->S", "HEL", None), ("S->C", "ACK", None),
    ("C->S", "OPN", "OpenSecureChannelRequest"), ("S->C", "OPN", "OpenSecureChannelResponse"),
    ("C->S", "MSG", "GetEndpointsRequest"), ("S->C", "MSG", "GetEndpointsResponse"),
    ("C->S", "MSG", "CreateSessionRequest"), ("S->C", "MSG", "CreateSessionResponse"),
    ("C->S", "MSG", "ActivateSessionRequest"), ("S->C", "MSG", "ActivateSessionResponse"),
]
check(secuencia[:10] == esperada_inicio, "HEL/ACK -> OPN -> GetEndpoints -> CreateSession -> ActivateSession")
check(secuencia[-1] == ("C->S", "CLO", "CloseSecureChannelRequest"), "termina con CLO")
servicios = [s for _, _, s in secuencia]
for nombre in ("CreateSubscriptionRequest", "CreateMonitoredItemsRequest", "PublishRequest",
               "PublishResponse", "WriteRequest", "WriteResponse", "CloseSessionRequest"):
    check(nombre in servicios, nombre + " presente")
check(servicios.index("CloseSessionRequest") < len(servicios) - 1, "CloseSession antes que CLO")

# ---------------------------------------------------------------------------
print("\n4. OPN: el servidor asigna SecureChannelId y TokenId")
opn = next(r for _, r in NONE if r["servicio"] == "OpenSecureChannelResponse")
canal = campo(opn, "SecurityToken.ChannelId")["valor"]
token = campo(opn, "SecurityToken.TokenId")["valor"]
msgs = [r for _, r in NONE if r["tipo"] == "MSG"]
check(all(campo(r, "SecureChannelId")["valor"] == canal for r in msgs),
      "todos los MSG usan SecureChannelId = {}".format(canal))
check(all(campo(r, "TokenId")["valor"] == token for r in msgs),
      "todos los MSG usan TokenId = {}".format(token))
opn_req = next(r for _, r in NONE if r["servicio"] == "OpenSecureChannelRequest")
check(campo(opn_req, "SecureChannelId")["valor"] == 0, "el primer OPN viaja con SecureChannelId 0")
check(campo(opn_req, "SecurityMode")["significado"] == "None", "SecurityMode None en el cuerpo del OPN")

# ---------------------------------------------------------------------------
print("\n5. WriteRequest/WriteResponse byte a byte (Parte 4.5)")
writes = [r for _, r in NONE if r["servicio"] == "WriteRequest"]
rampa = [r for r in writes if campo(r, "NodesToWrite[0].NodeId")["valor"].endswith("s=Cliente.Rampa")]
pulsador = [r for r in writes if campo(r, "NodesToWrite[0].NodeId")["valor"].endswith("s=Cliente.EstadoPulsador")]
check(len(rampa) == 2 and len(pulsador) == 2, "dos Write de cada variable")
r = rampa[0]
v = campo(r, "Value.Value.Value")
check(campo(r, "TypeId")["valor"] == "ns=0;i=673", "TypeId WriteRequest = i=673 (FourByte 01 00 a1 02)")
check(campo(r, "TypeId")["bytes"].hex(" ") == "01 00 a1 02", "673 = 0x02A1 en little-endian")
check(campo(r, "NodesToWrite[0].NodeId")["valor"] == "ns=1;s=Cliente.Rampa", "NodeId String ns=1")
check(campo(r, "NodesToWrite[0].NodeId")["bytes"][0] == 0x03, "mascara de NodeId 0x03 = String")
check(campo(r, "AttributeId")["valor"] == 13, "AttributeId 13 = Value")
check(campo(r, "Value.EncodingMask")["valor"] & 0x01 == 0x01, "DataValue con bit Value")
check(campo(r, "Value.Value.EncodingMask")["valor"] == 5, "Variant tipo 5 = UInt16")
check(v["valor"] == 0x1234 and v["bytes"] == b"\x34\x12", "0x1234 viaja como 34 12 (little-endian)")
b = campo(pulsador[0], "Value.Value.Value")
check(campo(pulsador[0], "Value.Value.EncodingMask")["valor"] == 1, "Variant tipo 1 = Boolean")
check(b["valor"] is True and b["bytes"] == b"\x01", "true viaja como un byte 01")
check(campo(pulsador[1], "Value.Value.Value")["bytes"] == b"\x00", "false viaja como un byte 00")
resp = [r for _, r in NONE if r["servicio"] == "WriteResponse"]
check(all(o.nombre_status(campo(x, "Results[0].StatusCode")["valor"]) == "Good" for x in resp),
      "los cuatro WriteResponse devuelven Good")
handles_req = sorted(campo(x, "RequestHeader.RequestHandle")["valor"] for x in writes)
handles_resp = sorted(campo(x, "ResponseHeader.RequestHandle")["valor"] for x in resp)
check(handles_req == handles_resp, "cada respuesta repite el RequestHandle de su peticion")
check(len(r["campos"]) and sum(len(c["bytes"]) for c in r["campos"]) == r["resumen"]["tamano"],
      "los campos cubren exactamente los {} bytes del mensaje".format(r["resumen"]["tamano"]))

# ---------------------------------------------------------------------------
print("\n6. Suscripcion: parametros pedidos y revisados (Parte 3.4)")
sub_resp = next(r for _, r in NONE if r["servicio"] == "CreateSubscriptionResponse")
check(campo(sub_resp, "RevisedPublishingInterval")["valor"] == 100.0, "PublishingInterval revisado = 100 ms")
check(campo(sub_resp, "RevisedMaxKeepAliveCount")["valor"] == 10, "MaxKeepAliveCount = 10 (KeepAlive cada 1 s)")
mon_req = next(r for _, r in NONE if r["servicio"] == "CreateMonitoredItemsRequest")
check(campo(mon_req, "ItemsToCreate.Length")["valor"] == 2, "un unico CreateMonitoredItems con los dos nodos")
mon_resp = next(r for _, r in NONE if r["servicio"] == "CreateMonitoredItemsResponse")
check(campo(mon_resp, "RevisedSamplingInterval")["valor"] == 100.0, "SamplingInterval revisado = 100 ms")
check(campo(mon_resp, "RevisedQueueSize")["valor"] == 1, "QueueSize revisado = 1")
publish = [r for _, r in NONE if r["servicio"] == "PublishResponse"]
keepalive = [r for r in publish if "KeepAlive" in campo(r, "NotificationData.Length")["significado"]]
con_datos = [r for r in publish if campo(r, "MonitoredItems.Length")]
check(len(keepalive) >= 2, "{} KeepAlive (PublishResponse sin notificaciones)".format(len(keepalive)))
check(len(con_datos) >= 5, "{} PublishResponse con DataChangeNotification".format(len(con_datos)))
check(any(campo(r, "Value.SourceTimestamp") for r in con_datos), "las notificaciones traen SourceTimestamp")
faults = [r for _, r in NONE if r["servicio"] == "ServiceFault"]
check(faults and all(o.nombre_status(campo(r, "ServiceResult")["valor"]) == "BadNoSubscription" for r in faults),
      "al borrar la suscripcion, los {} Publish encolados vuelven con BadNoSubscription".format(len(faults)))

# ---------------------------------------------------------------------------
print("\n7. Modos de seguridad: que queda legible (Parte 4.8)")
sign = decodificar_todos(VECTORES["sesion_Sign"])
enc = decodificar_todos(VECTORES["sesion_SignAndEncrypt"])
w_sign = [r for _, r in sign if r["servicio"] == "WriteRequest"]
check(w_sign and all(campo(r, "Resto")["significado"].startswith("firma HMAC-SHA256") for r in w_sign),
      "Sign: el Write se lee entero y termina en 32 bytes de firma")
check(campo(w_sign[0], "Value.Value.Value")["valor"] == 0x1234, "Sign: el valor 0x1234 sigue legible")
opn_seguro = [r for _, r in sign if r["tipo"] == "OPN" and r["cifrado"]]
check(len(opn_seguro) == 2, "Sign: el OPN con Basic256Sha256 va cifrado con RSA (pedido y respuesta)")
msg_enc = [r for _, r in enc if r["tipo"] == "MSG" and r["cifrado"]]
check(len(msg_enc) > 50, "SignAndEncrypt: {} MSG cifrados".format(len(msg_enc)))
legibles = {c["campo"] for r in msg_enc for c in r["campos"] if c["campo"] != "Opaco"}
check(legibles == {"Cabecera.MessageType", "Cabecera.ChunkType", "Cabecera.MessageSize",
                   "SecureChannelId", "CabeceraSeguridadSimetrica.TokenId"},
      "SignAndEncrypt: en claro solo MessageType, ChunkType, MessageSize, SecureChannelId y TokenId")
check(sum(1 for _, r in enc if r["servicio"] == "GetEndpointsRequest") >= 1,
      "SignAndEncrypt: GetEndpoints viaja antes por un canal None (descubrimiento)")

# ---------------------------------------------------------------------------
print("\n8. Token de identidad (Parte 4.9)")
usuario = decodificar_todos(VECTORES["sesion_None_usuario"])
act = next(r for _, r in usuario if r["servicio"] == "ActivateSessionRequest")
check(campo(act, "UserIdentityToken.TypeId")["valor"] == "ns=0;i=324", "UserNameIdentityToken (i=324)")
check(campo(act, "UserNameIdentityToken.UserName")["valor"] == "operador", "el nombre de usuario es legible")
alg = campo(act, "UserNameIdentityToken.EncryptionAlgorithm")["valor"]
check(alg and alg.endswith("rsa-oaep"), "la contrasena va cifrada con RSA-OAEP aun en modo None")
anon = next(r for _, r in NONE if r["servicio"] == "ActivateSessionRequest")
check(campo(anon, "UserIdentityToken.TypeId")["valor"] == "ns=0;i=321", "sesion anonima: AnonymousIdentityToken (i=321)")

# ---------------------------------------------------------------------------
print("\n9. Encapsulamiento Ethernet/IPv4/TCP (Parte 4.4)")
cuerpo = bytes.fromhex(next(m["hex"] for m, r in NONE if r["servicio"] == "WriteRequest"))
eth = bytes.fromhex("b827eb000002" "b827eb000001" "0800")
tcp_len = 32
ip_total = 20 + tcp_len + len(cuerpo)
ip = bytes([0x45, 0x00]) + ip_total.to_bytes(2, "big") + bytes.fromhex("1c46 4000 4006 0000 c0a80a02 c0a80a01".replace(" ", ""))
tcp = (bytes.fromhex("c35a 12e8".replace(" ", "")) + (1000).to_bytes(4, "big") + (2000).to_bytes(4, "big") +
       bytes([0x80, 0x18]) + bytes.fromhex("01f5 0000 0000") + bytes(12))
r = o.decodificar_ethernet(eth + ip + tcp + cuerpo)
check(r["capas"] == {"Ethernet": 14, "IPv4": 20, "TCP": 32, "OPC UA": len(cuerpo)}, "bytes por capa: {}".format(r["capas"]))
check(campo(r, "PuertoDestino")["valor"] == 4840, "puerto destino 4840")
check(campo(r, "IPv4.Origen")["valor"] == "192.168.10.2", "IP origen 192.168.10.2 (cliente)")
check(r["servicio"] == "WriteRequest", "el mensaje OPC UA se decodifica dentro de la trama")
check(campo(r, "Cabecera.MessageType")["offset"] == 66, "el OPC UA empieza en el byte 66 (14 + 20 + 32)")

# ---------------------------------------------------------------------------
print("\n10. Codificador propio: ida y vuelta")
for tipo, valor in ((5, 0), (5, 65535), (1, False), (1, True)):
    msg = o.construir_write_request(1, "Cliente.Rampa", tipo, valor)
    check(campo(o.decodificar_opcua(msg), "Value.Value.Value")["valor"] == valor,
          "Write tipo {} valor {}".format(tipo, valor))
check(o.parsear_hex("4d:53 47\n46") == b"MSGF", "parsear_hex acepta ':' y saltos de linea")
check(o.datetime_a_texto(0) == "nulo (0)", "DateTime 0 = nulo")

print("\n{} fallo(s)".format(fallos))
sys.exit(1 if fallos else 0)
