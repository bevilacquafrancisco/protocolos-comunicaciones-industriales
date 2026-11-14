#!/usr/bin/env python3
"""
host_comandos.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Envia los comandos que en F6 enviara la Host Application web, para probar el camino de comando
sin la pagina: NCMD "Node Control/Rebirth" y DCMD sobre Outputs/*. Usa el usuario 'host_app'
(ADR-005). Los CMD van con QoS 0, sin retener, con timestamp y sin seq (Sparkplug 3.0,
payloads-ncmd-* / payloads-dcmd-*); las metricas viajan SOLO con alias
(payloads-alias-data-cmd-requirement), salvo Rebirth, que va por nombre porque no tiene alias.

Uso (en gateway-sparkplug/, con el .env: MQTT_HOST, MQTT_USUARIO_HOST, MQTT_CLAVE_HOST):
    python tools/host_comandos.py rebirth
    python tools/host_comandos.py dcmd Outputs/LedDigital true
    python tools/host_comandos.py dcmd Outputs/LedPWM 128

Dependencias externas: paho-mqtt 2.1.0, protobuf 7.36.2.
"""

from __future__ import annotations

import argparse
import threading
import os
import sys
from pathlib import Path

import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))
import sparkplug as spb                                      # noqa: E402
from metrics import NOMBRE_REBIRTH, cargar_metricas          # noqa: E402
from observador_sparkplug import crear_cliente               # noqa: E402


def payload_rebirth() -> bytes:
    """NCMD con Node Control/Rebirth = true (data-commands-ncmd-rebirth-*)."""
    return spb.armar_payload([spb.ValorMetrica(NOMBRE_REBIRTH, None, "Boolean", True)], seq=None)


def payload_dcmd(metricas, nombre: str, valor) -> bytes:
    """
    DCMD con UNA metrica, por alias.

    Excepciones:
        ValueError: metrica desconocida, no escribible o valor fuera del tipo.
    """
    m = metricas.por_nombre(nombre)
    if m is None or not m.escribible:
        raise ValueError(f"{nombre} no es una salida escribible del dispositivo")
    return spb.armar_payload([spb.ValorMetrica(None, m.alias, m.tipo, valor)], seq=None)


def convertir(tipo: str, texto: str):
    """Texto de la linea de comandos -> valor Python del tipo Sparkplug."""
    if tipo == "Boolean":
        if texto.lower() not in ("true", "false", "1", "0", "on", "off"):
            raise ValueError("Boolean: true/false")
        return texto.lower() in ("true", "1", "on")
    if tipo in ("UInt16", "UInt32", "Int64"):
        return int(texto, 0)
    if tipo in ("Float", "Double"):
        return float(texto)
    return texto


def main() -> None:
    p = argparse.ArgumentParser(description="Comandos Sparkplug B de prueba (NCMD Rebirth, DCMD)")
    p.add_argument("--env", type=Path, default=RAIZ.parent / ".env")
    p.add_argument("--host"), p.add_argument("--puerto", type=int), p.add_argument("--mqtt-ca", type=Path)
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("rebirth")
    d = sub.add_parser("dcmd")
    d.add_argument("metrica"), d.add_argument("valor")
    args = p.parse_args()

    from sparkplug_edge_node import cargar_env
    cargar_env(args.env)
    topicos = spb.Topicos(os.environ.get("SPB_GROUP_ID", "UNRaf_PdCI_2026"), os.environ.get("SPB_EDGE_NODE_ID", "EN01_Gateway"),
                          os.environ.get("SPB_DEVICE_ID", "DEV01_ESP32_Slave"), os.environ.get("SPB_HOST_ID", "HA01_WebDashboard"))
    if args.comando == "rebirth":
        topico, datos = topicos.de("NCMD"), payload_rebirth()
    else:
        metricas = cargar_metricas()
        m = metricas.por_nombre(args.metrica)
        if m is None:
            raise SystemExit(f"metrica desconocida: {args.metrica}")
        topico, datos = topicos.de("DCMD"), payload_dcmd(metricas, args.metrica, convertir(m.tipo, args.valor))

    host = args.host or os.environ.get("MQTT_HOST")
    puerto = args.puerto or int(os.environ.get("MQTT_PUERTO_TLS", "8883"))
    c = crear_cliente(host, puerto, os.environ.get("MQTT_USUARIO_HOST", "host_app"),
                      os.environ.get("MQTT_CLAVE_HOST", ""), ca=args.mqtt_ca, id_cliente=f"host-cli-{os.getpid()}")
    # Hay que esperar el CONNACK: un publish QoS 0 ANTES de la conexion paho lo descarta en
    # silencio (medido: el primer DCMD de la prueba de punta a punta nunca llego al broker).
    conectado = threading.Event()
    c.on_connect = lambda cl, u, f, rc, p: conectado.set() if not rc.is_failure else print(f"CONNACK: {rc}")
    c.connect(host, puerto, 30)
    c.loop_start()
    try:
        if not conectado.wait(10):
            raise SystemExit("sin conexion con el broker (credenciales, CA o red)")
        info = c.publish(topico, datos, qos=0, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise SystemExit(f"publish fallo: {mqtt.error_string(info.rc)}")
        info.wait_for_publish(5)
        print(f"publicado {topico} ({len(datos)} bytes)")
    finally:
        c.disconnect()
        c.loop_stop()


if __name__ == "__main__":
    main()
