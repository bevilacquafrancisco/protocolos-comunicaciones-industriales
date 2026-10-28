# -*- coding: utf-8 -*-
"""
eficiencia_trama.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-13
Version: 1.0

Descripcion general
-------------------
Consigna, Parte 4.6: "calcular, para la transmision de una sola word, la
relacion entre bytes utiles y bytes totales, considerando las cabeceras
Ethernet, IP, TCP y OPC UA. Comparar con la trama MODBus RTU equivalente de
la Tarea N.o 1 y discutir el resultado."

- El tamano del mensaje OPC UA NO se supone: se toma del WriteRequest real de
  Cliente.Rampa en herramientas/vectores/sesion_None.json (pila node-opcua).
  Con --ua-bytes N se reemplaza por el MessageSize medido en Wireshark.
- La trama MODBus se reconstruye con el CRC propio de la Tarea 1
  (tarea-1/herramientas/modbus_tramas.py) y se compara contra la trama real
  documentada en tarea-1/docs/mapa-registros.md §6.4: 01 06 00 00 00 80 88 6A.

Uso
---
    python eficiencia_trama.py                 # con el WriteRequest de los vectores
    python eficiencia_trama.py --ua-bytes 114  # con el MessageSize medido
    python eficiencia_trama.py --tcp-opciones 0  # si la captura muestra TCP sin opciones

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "..", "tarea-1", "herramientas"))

import opcua_tramas  # noqa: E402

try:
    import modbus_tramas  # noqa: E402  (Tarea 1)
except ImportError:  # el repositorio se copio sin tarea-1
    modbus_tramas = None

# =============================================================================
# Constantes de capa fisica y enlace (IEEE 802.3, RFC 791, RFC 793)
# =============================================================================

PREAMBULO_SFD = 8      # 7 bytes de preambulo + 1 de SFD (IEEE 802.3 §3.2.1)
CABECERA_ETH = 14      # MAC destino 6 + MAC origen 6 + EtherType 2
FCS = 4                # CRC-32 de la trama
IFG = 12               # 96 tiempos de bit de silencio entre tramas
CARGA_MINIMA_ETH = 46  # por debajo se rellena (trama minima de 64 bytes)
CABECERA_IPV4 = 20     # sin opciones
CABECERA_TCP = 20      # sin opciones
#: Linux negocia TCP Timestamps (RFC 7323) por defecto: 10 bytes de opcion +
#: 2 NOP de alineacion = 12. Se verifica en la captura (TCP "Header Length:
#: 32 bytes"); si no aparece, usar --tcp-opciones 0.
OPCIONES_TCP_LINUX = 12
VELOCIDAD_ETH = 100e6  # bit/s negociados por ethtool en la RPi (Parte 1.3)

BYTES_UTILES = 2       # una word UInt16

# MODBus RTU, Tarea 1: 9600 baudios, 8N1 -> 10 bits por caracter
BAUDIOS = 9600
BITS_POR_CARACTER = 10
SILENCIO_T35 = 3.5     # caracteres de silencio que delimitan la trama
#: Trama real capturada en la Tarea 1 (mapa-registros.md §6.4): LED PWM = 128.
TRAMA_REAL_TAREA1 = bytes.fromhex("01 06 00 00 00 80 88 6A")


def tamano_write_request_real():
    """
    MessageSize del primer WriteRequest de Cliente.Rampa en los vectores.

    Retorna
    -------
    tuple (int, int) | None
        (bytes del WriteRequest, bytes del WriteResponse), o None si no hay
        vectores.
    """
    ruta = os.path.join(AQUI, "vectores", "sesion_None.json")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        mensajes = json.load(f)["mensajes"]
    peticion = respuesta = None
    for m in mensajes:
        r = opcua_tramas.decodificar_opcua(bytes.fromhex(m["hex"]))
        texto = " ".join(str(c["valor"]) for c in r["campos"])
        if peticion is None and r["servicio"] == "WriteRequest" and "s=Cliente.Rampa" in texto:
            peticion = r["resumen"]["tamano"]
        elif peticion and respuesta is None and r["servicio"] == "WriteResponse":
            respuesta = r["resumen"]["tamano"]
    return (peticion, respuesta) if peticion and respuesta else None


def trama_ethernet(ua_bytes, opciones_tcp):
    """
    Desglose de una trama Ethernet que transporta `ua_bytes` de OPC UA.

    Parametros
    ----------
    ua_bytes : int
        MessageSize del mensaje OPC UA.
    opciones_tcp : int
        Bytes de opciones TCP.

    Retorna
    -------
    dict
        Bytes por componente, total "en el cable" y total "visto por
        Wireshark" (sin preambulo, FCS ni IFG).
    """
    carga_eth = CABECERA_IPV4 + CABECERA_TCP + opciones_tcp + ua_bytes
    relleno = max(0, CARGA_MINIMA_ETH - carga_eth)
    partes = {
        "Preambulo + SFD": PREAMBULO_SFD,
        "Cabecera Ethernet II": CABECERA_ETH,
        "Cabecera IPv4": CABECERA_IPV4,
        "Cabecera TCP (+ opciones)": CABECERA_TCP + opciones_tcp,
        "Mensaje OPC UA": ua_bytes,
        "Relleno Ethernet": relleno,
        "FCS": FCS,
        "IFG": IFG,
    }
    return {
        "partes": partes,
        "cable": sum(partes.values()),
        "wireshark": CABECERA_ETH + carga_eth + relleno,
    }


def trama_modbus():
    """
    La escritura equivalente de la Tarea 1: FC 0x06 al registro 40001 (LED PWM).

    Retorna
    -------
    dict
        trama (bytes), bits en la linea con y sin silencio t3,5.
    """
    if modbus_tramas is not None:
        trama = modbus_tramas.agregar_crc(bytes([0x01, 0x06, 0x00, 0x00, 0x00, 0x80]))
    else:
        trama = TRAMA_REAL_TAREA1
    bits = len(trama) * BITS_POR_CARACTER
    bits_silencio = SILENCIO_T35 * BITS_POR_CARACTER
    return {"trama": trama, "bits": bits, "bits_con_silencio": bits + bits_silencio}


def main(argumentos):
    """Imprime el calculo completo, listo para el informe."""
    ua_req, ua_resp = 114, 64
    origen = "valor por defecto"
    real = tamano_write_request_real()
    if real:
        ua_req, ua_resp = real
        origen = "WriteRequest/Response reales (vectores/sesion_None.json)"
    opciones = OPCIONES_TCP_LINUX
    if "--ua-bytes" in argumentos:
        ua_req = int(argumentos[argumentos.index("--ua-bytes") + 1])
        origen = "medido en la captura (--ua-bytes)"
    if "--tcp-opciones" in argumentos:
        opciones = int(argumentos[argumentos.index("--tcp-opciones") + 1])

    eth = trama_ethernet(ua_req, opciones)
    print("=" * 72)
    print("OPC UA: WriteRequest de una word (Cliente.Rampa, UInt16) - " + origen)
    print("=" * 72)
    for nombre, n in eth["partes"].items():
        print("  {:<28} {:>5} bytes".format(nombre, n))
    print("  {:<28} {:>5} bytes".format("TOTAL en el cable", eth["cable"]))
    print("  {:<28} {:>5} bytes".format("TOTAL que muestra Wireshark", eth["wireshark"]))
    ef_cable = BYTES_UTILES / eth["cable"]
    ef_ws = BYTES_UTILES / eth["wireshark"]
    ef_ua = BYTES_UTILES / ua_req
    t_us = eth["cable"] * 8 / VELOCIDAD_ETH * 1e6
    print("\n  Eficiencia = {} / {} = {:.2%} (en el cable)".format(BYTES_UTILES, eth["cable"], ef_cable))
    print("  Eficiencia = {} / {} = {:.2%} (trama vista por Wireshark)".format(BYTES_UTILES, eth["wireshark"], ef_ws))
    print("  Eficiencia = {} / {} = {:.2%} (solo el mensaje OPC UA)".format(BYTES_UTILES, ua_req, ef_ua))
    print("  Tiempo en el cable a 100 Mbit/s: {:.1f} us".format(t_us))

    eth_r = trama_ethernet(ua_resp, opciones)
    total_tx = eth["cable"] + eth_r["cable"]
    print("\n  Transaccion completa (Write + WriteResponse de {} B): {} bytes -> {:.2%}".format(
        ua_resp, total_tx, BYTES_UTILES / total_tx))

    mb = trama_modbus()
    print("\n" + "=" * 72)
    print("MODBus RTU, Tarea 1: FC 0x06 Write Single Register (LED PWM)")
    print("=" * 72)
    coincide = mb["trama"] == TRAMA_REAL_TAREA1
    print("  Trama: " + mb["trama"].hex(" ").upper() +
          ("   (coincide con la trama real de mapa-registros.md sec. 6.4)" if coincide
           else "   (NO coincide con la trama real de la Tarea 1)"))
    print("  Direccion 1 + Funcion 1 + Registro 2 + Valor 2 + CRC 2 = {} bytes".format(len(mb["trama"])))
    print("  Eficiencia por bytes = {} / {} = {:.1%}".format(BYTES_UTILES, len(mb["trama"]), BYTES_UTILES / len(mb["trama"])))
    print("  Eficiencia por bits (8N1, 10 bits/caracter) = 16 / {} = {:.1%}".format(
        mb["bits"], 16 / mb["bits"]))
    print("  Con el silencio t3,5 que delimita la trama = 16 / {:g} = {:.1%}".format(
        mb["bits_con_silencio"], 16 / mb["bits_con_silencio"]))
    t_mb_ms = mb["bits_con_silencio"] / BAUDIOS * 1e3
    print("  Tiempo en la linea a 9600 baudios: {:.2f} ms".format(t_mb_ms))
    print("  Transaccion (peticion + eco de la respuesta): {:.2f} ms".format(2 * t_mb_ms))

    print("\n" + "=" * 72)
    print("COMPARACION")
    print("=" * 72)
    print("  {:<38} {:>12} {:>12}".format("", "OPC UA/TCP", "MODBus RTU"))
    print("  {:<38} {:>12} {:>12}".format("Bytes para transmitir 1 word", eth["cable"], len(mb["trama"])))
    print("  {:<38} {:>11.2%} {:>11.1%}".format("Eficiencia (bytes en el medio)", ef_cable,
                                                  BYTES_UTILES / len(mb["trama"])))
    print("  {:<38} {:>10.1f}us {:>10.2f}ms".format("Tiempo de la trama en el medio", t_us, t_mb_ms))
    print("  {:<38} {:>12.0f}x".format("OPC UA es mas rapido en el medio", t_mb_ms * 1000 / t_us))
    print("  {:<38} {:>12.0f}x".format("OPC UA usa mas bytes", eth["cable"] / len(mb["trama"])))
    print("\nLectura: OPC UA es ~{:.0f} veces MENOS eficiente en bytes, pero la trama ocupa el medio".format(
        (BYTES_UTILES / len(mb["trama"])) / ef_cable))
    print("~{:.0f} veces MENOS tiempo, porque el medio es ~10 400 veces mas rapido (100 Mbit/s contra".format(
        t_mb_ms * 1000 / t_us))
    print("9600 baudios). La sobrecarga es FIJA por mensaje: se amortiza agrupando varios valores")
    print("en un mismo Write o Publish (ver docs/protocolo-opcua.md sec. 9).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
