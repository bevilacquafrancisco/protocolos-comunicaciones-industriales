#!/usr/bin/env python3
"""
fake_edge_node.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Edge Node de PRUEBA para desarrollar la Host Application web (hmi-web/) sin la cadena real.

No reimplementa Sparkplug: usa el MISMO Edge Node del dispositivo 3 (sparkplug_edge_node.EdgeNode
y ciclo_vida.NucleoEdgeNode). Solo reemplaza al cliente OPC UA por una fuente de datos sintetica,
asi la web se prueba contra el protocolo exacto que vera en la demo (mensajes sinteticos en el
contenido, reales en la forma).

Datos sinteticos: potenciometro en rampa triangular de 8 s, pulsador que cambia cada 4 s,
Status/MODBUS/OK +1 cada 250 ms (como el sondeo del maestro), y la ultima trama TX/RX con su
latencia (diagnostico, ADR-028): las cuatro lecturas del ciclo FC 02, 04, 01 y 03 con CRC-16
valido, FC 05/06 al escribir, y RX vacia con DEVICE NOT REACHED. Las escrituras (DCMD) se
"confirman" 50 ms despues, como el eco MODBus (ADR-015), salvo que se pida lo contrario.

Comandos por la entrada estandar (para provocar cada situacion que la web debe mostrar):
    dnr | ok | crc         Status/MODBUS/Estado = DEVICE NOT REACHED (-> DDEATH) | DONE | CRC ERROR
    opcua off | opcua on   cae / vuelve la sesion OPC UA (Status/OPCUA/Estado, DDEATH/DBIRTH)
    saltar                 consume un seq sin publicar: la web debe detectar el salto y pedir Rebirth
    escrituras falla|ok    los DCMD no se confirman (BadCommunicationError) | vuelven a confirmarse
    pulsador 0|1 · pote N  valores manuales (detiene la animacion de esa senal)
    matar                  termina el proceso SIN NDEATH: el broker publica el Will

Uso (en gateway-sparkplug/):
    python tools/fake_edge_node.py --env <archivo .env> [--mqtt-ca .dev-broker/ca.pem]
    (MQTT_HOST, MQTT_PUERTO_TLS, MQTT_USUARIO_EDGE, MQTT_CLAVE_EDGE como el Edge Node real)

Dependencias externas: las del Edge Node (paho-mqtt, protobuf).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import sparkplug as spb                                                       # noqa: E402
from ciclo_vida import AlmacenBdSeq, NucleoEdgeNode                           # noqa: E402
from metrics import DICCIONARIO_POR_DEFECTO, cargar_metricas                  # noqa: E402
from sparkplug_edge_node import ConfigMqtt, EdgeNode, RegistroMensajes, cargar_env   # noqa: E402

_log = logging.getLogger("fake")


def _crc16(datos: bytes) -> bytes:
    """
    CRC-16 MODBus (polinomio reflejado 0xA001, inicio 0xFFFF), byte bajo primero. Solo para que las
    tramas SINTETICAS sean validas: el CRC del sistema es el del maestro (edge-nodered/lib/modbus.js)
    y el del esclavo (firmware/.../crc16.py), I-01.

    Parametros:
        datos (bytes): trama sin CRC.
    Retorna:
        bytes: los dos bytes del CRC, en el orden en que viajan.
    """
    crc = 0xFFFF
    for b in datos:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


def _hex(datos: bytes) -> str:
    return " ".join(f"{b:02X}" for b in datos)


def trama_sintetica(fc: int, valor: int, responde: bool = True) -> tuple[str, str]:
    """
    Par TX/RX de una transaccion con el esclavo 1, direccion 0 (el mapa del diccionario §1).

    Parametros:
        fc (int): 1-4 lectura de 1 elemento; 5/6 escritura (la respuesta es el eco).
        valor (int): valor leido (o escrito).
        responde (bool): False = TIMEOUT (RX vacia).
    Retorna:
        tuple[str, str]: (TX, RX) en hexadecimal separado por espacios, como los nodos OPC UA.
    """
    if fc in (5, 6):
        cuerpo = bytes([1, fc, 0, 0]) + (bytes([0xFF if valor else 0, 0]) if fc == 5 else valor.to_bytes(2, "big"))
        tx = cuerpo + _crc16(cuerpo)
        return _hex(tx), _hex(tx) if responde else ""
    pet = bytes([1, fc, 0, 0, 0, 1])
    tx = pet + _crc16(pet)
    if not responde:
        return _hex(tx), ""
    resp = bytes([1, fc, 1, 1 if valor else 0]) if fc in (1, 2) else bytes([1, fc, 2]) + int(valor).to_bytes(2, "big")
    return _hex(tx), _hex(resp + _crc16(resp))


class OpcuaFalso:
    """Sustituto del ClienteOpcua: misma interfaz (ejecutar, escribir) y mismos callbacks."""

    def __init__(self, edge: EdgeNode, metricas):
        self._edge = edge
        self._metricas = metricas
        self._valores = {"Inputs/Pulsador": False, "Inputs/Potenciometro": 0, "Outputs/LedDigital": False,
                         "Outputs/LedPWM": 0, "Inputs/Potenciometro_pct": 0.0, "Status/MODBUS/Estado": "DONE",
                         "Status/MODBUS/OK": 0, "Status/MODBUS/CRC_ERROR": 0, "Status/MODBUS/TIMEOUT": 0,
                         "Status/MODBUS/EXCEPTION": 0, "Status/MODBUS/UltimaTramaTx": "",
                         "Status/MODBUS/UltimaTramaRx": "", "Status/MODBUS/LatenciaMs": 0}
        self._fc_ciclo = (2, 4, 1, 3)
        self._indice = 0
        self._opcua_ok = True
        self.escrituras_ok = True
        self.pote_auto = True
        self.pulsador_auto = True

    def fijar(self, nombre, valor):
        """Cambia un valor y lo entrega al Edge Node como lo haria la suscripcion OPC UA."""
        self._valores[nombre] = valor
        if self._opcua_ok:
            self._edge.al_dato(nombre, valor, spb.ahora_ms(), True)

    def opcua(self, ok: bool):
        self._opcua_ok = ok
        self._edge.al_estado_opcua(ok)
        if ok:
            for nombre, valor in self._valores.items():       # notificacion inicial de la sesion nueva
                self._edge.al_dato(nombre, valor, spb.ahora_ms(), True)

    def _transaccion(self, fc: int, valor: int, responde: bool = True):
        """Publica la ultima trama como lo hace el maestro en Status.MODBUS.UltimaTrama* (ADR-028)."""
        tx, rx = trama_sintetica(fc, valor, responde)
        self.fijar("Status/MODBUS/UltimaTramaTx", tx)
        self.fijar("Status/MODBUS/UltimaTramaRx", rx)
        if responde:
            self.fijar("Status/MODBUS/LatenciaMs", 22 + (self._indice * 7) % 9)

    async def ejecutar(self):
        self.opcua(True)
        t0 = time.monotonic()
        while True:
            await asyncio.sleep(0.25)
            if not self._opcua_ok:
                continue
            t = time.monotonic() - t0
            if self._valores["Status/MODBUS/Estado"] != "DEVICE NOT REACHED":
                self.fijar("Status/MODBUS/OK", self._valores["Status/MODBUS/OK"] + 1)
                fc = self._fc_ciclo[self._indice % 4]
                self._indice += 1
                valores = {2: self._valores["Inputs/Pulsador"], 4: self._valores["Inputs/Potenciometro"],
                           1: self._valores["Outputs/LedDigital"], 3: self._valores["Outputs/LedPWM"]}
                self._transaccion(fc, int(valores[fc]))
                if self.pote_auto:
                    fase = (t % 8) / 8
                    crudo = int(4095 * (2 * fase if fase < 0.5 else 2 - 2 * fase))
                    self.fijar("Inputs/Potenciometro", crudo)
                    self.fijar("Inputs/Potenciometro_pct", round(crudo * 100 / 4095, 1))
                if self.pulsador_auto:
                    self.fijar("Inputs/Pulsador", int(t // 4) % 2 == 1)
            else:
                self.fijar("Status/MODBUS/TIMEOUT", self._valores["Status/MODBUS/TIMEOUT"] + 1)
                self._transaccion(4, 0, responde=False)

    async def escribir(self, node_id, tipo, valor):
        nombre = self._metricas.por_node_id(node_id).nombre
        await asyncio.sleep(0.05)                                   # el eco MODBus
        if not self._opcua_ok:
            return "BadNotConnected"
        if not self.escrituras_ok or self._valores["Status/MODBUS/Estado"] == "DEVICE NOT REACHED":
            return "BadCommunicationError"                          # el valor NO cambia (ADR-015)
        self._transaccion(5 if nombre == "Outputs/LedDigital" else 6, int(valor))
        self.fijar(nombre, valor)
        return "Good"


def consola(loop, edge: EdgeNode, fuente: OpcuaFalso):
    """Lee comandos de la entrada estandar (hilo aparte) y los ejecuta en el event loop."""
    def ejecutar(partes):
        cmd = partes[0]
        if cmd in ("dnr", "ok", "crc"):
            if cmd == "crc":
                fuente.fijar("Status/MODBUS/CRC_ERROR", fuente._valores["Status/MODBUS/CRC_ERROR"] + 1)
            fuente.fijar("Status/MODBUS/Estado", {"dnr": "DEVICE NOT REACHED", "ok": "DONE", "crc": "CRC ERROR"}[cmd])
        elif cmd == "opcua" and len(partes) == 2:
            fuente.opcua(partes[1] == "on")
        elif cmd == "saltar":
            edge.nucleo._seq.siguiente()        # seq consumido y NO publicado: un salto real en el cable
            _log.info("seq consumido sin publicar (el proximo mensaje llega con un salto)")
        elif cmd == "escrituras" and len(partes) == 2:
            fuente.escrituras_ok = partes[1] == "ok"
        elif cmd == "pulsador" and len(partes) == 2:
            fuente.pulsador_auto = False
            fuente.fijar("Inputs/Pulsador", partes[1] == "1")
        elif cmd == "pote" and len(partes) == 2:
            fuente.pote_auto = False
            crudo = max(0, min(4095, int(partes[1])))
            fuente.fijar("Inputs/Potenciometro", crudo)
            fuente.fijar("Inputs/Potenciometro_pct", round(crudo * 100 / 4095, 1))
        elif cmd == "matar":
            os._exit(1)                         # sin NDEATH propio: lo publica el broker (Will)
        else:
            _log.warning("comando desconocido: %s", " ".join(partes))
        print(f"[FAKE] {' '.join(partes)}", flush=True)

    for linea in sys.stdin:
        partes = linea.split()
        if partes:
            loop.call_soon_threadsafe(ejecutar, partes)


async def principal(args):
    cargar_env(args.env)
    metricas = cargar_metricas(args.diccionario)
    topicos = spb.Topicos(os.environ.get("SPB_GROUP_ID", "UNRaf_PdCI_2026"), os.environ.get("SPB_EDGE_NODE_ID", "EN01_Gateway"),
                          os.environ.get("SPB_DEVICE_ID", "DEV01_ESP32_Slave"), os.environ.get("SPB_HOST_ID", "HA01_WebDashboard"))
    nucleo = NucleoEdgeNode(metricas, topicos, AlmacenBdSeq(args.estado))
    cfg = ConfigMqtt(host=os.environ.get("MQTT_HOST", "127.0.0.1"), puerto=int(os.environ.get("MQTT_PUERTO_TLS", "8883")),
                     usuario=os.environ.get("MQTT_USUARIO_EDGE", ""), clave=os.environ.get("MQTT_CLAVE_EDGE", ""),
                     id_cliente=f"{topicos.grupo}-{topicos.nodo}", ca=args.mqtt_ca, tls=not args.sin_tls_local)
    edge = EdgeNode(nucleo, cfg, RegistroMensajes(None, metricas))
    fuente = OpcuaFalso(edge, metricas)
    edge.opcua = fuente
    threading.Thread(target=consola, args=(asyncio.get_running_loop(), edge, fuente), daemon=True).start()
    print("LISTO", flush=True)                  # marca para las pruebas automaticas
    await edge.ejecutar(asyncio.Event())


def main():
    p = argparse.ArgumentParser(description="Edge Node de prueba (datos sinteticos, protocolo real)")
    p.add_argument("--env", type=Path, default=RAIZ.parent / ".env")
    p.add_argument("--diccionario", type=Path, default=DICCIONARIO_POR_DEFECTO)
    p.add_argument("--mqtt-ca", type=Path)
    p.add_argument("--sin-tls-local", action="store_true")
    p.add_argument("--estado", type=Path, default=RAIZ / "estado" / "bdseq-fake.json",
                   help="bdSeq propio, separado del Edge Node real")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-5s %(levelname)-7s %(message)s")
    try:
        asyncio.run(principal(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
