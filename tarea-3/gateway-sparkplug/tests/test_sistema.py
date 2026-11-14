"""
test_sistema.py — Edge Node REAL (subproceso) + broker MQTT con TLS + servidor OPC UA, en loopback.
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0

Recorre el ciclo de vida completo que pide la consigna (I-07, I-10) y que la defensa tiene que
mostrar, verificado por el observador (seq y bdSeq) y no a ojo:

    NBIRTH (seq 0) -> DBIRTH -> DDATA ante cambio -> DCMD -> OPC UA Write -> DDATA de confirmacion
    -> DEVICE NOT REACHED: NDATA + DDEATH -> recuperacion: DBIRTH -> NCMD Rebirth: NBIRTH mismo bdSeq
    -> corte del broker: reconexion, bdSeq + 1, NBIRTH seq 0, Reconexiones = 1
    -> kill del proceso: NDEATH emitido POR EL BROKER con el bdSeq del NBIRTH vigente
    -> proceso nuevo: bdSeq + 1 (persistido)
"""

import asyncio
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

import sparkplug as spb
from broker_dev import BrokerDesarrollo
from host_comandos import payload_dcmd, payload_rebirth
from observador_sparkplug import Observador, crear_cliente
from servidor_prueba import ServidorPrueba

pytestmark = pytest.mark.red
RAIZ = Path(__file__).resolve().parents[1]
CLAVES = {"edge_node": "clave-edge-prueba", "host_app": "clave-host-prueba", "observador": "clave-obs-prueba"}


def lanzar_edge(tmp_path, broker, servidor) -> subprocess.Popen:
    entorno = dict(os.environ, MQTT_HOST="127.0.0.1", MQTT_PUERTO_TLS=str(broker.puerto),
                   MQTT_USUARIO_EDGE="edge_node", MQTT_CLAVE_EDGE=CLAVES["edge_node"],
                   OPCUA_URL=servidor.url, OPCUA_SEGURIDAD="None", PYTHONUNBUFFERED="1")
    for v in ("OPCUA_CLIENTE_USUARIO", "OPCUA_CLIENTE_CLAVE", "SPB_GROUP_ID", "SPB_EDGE_NODE_ID"):
        entorno.pop(v, None)
    return subprocess.Popen(
        [sys.executable, str(RAIZ / "src" / "sparkplug_edge_node.py"), "--env", str(tmp_path / "no-existe.env"),
         "--mqtt-ca", str(broker.ca), "--estado", str(tmp_path / "estado" / "bdseq.json"),
         "--logs", str(tmp_path / "logs")],
        env=entorno, stdout=open(tmp_path / f"edge-{len(list(tmp_path.glob('edge-*.log')))}.log", "w"),
        stderr=subprocess.STDOUT)


def ultimo(obs, tipo):
    return obs.de_tipo(tipo)[-1] if obs.de_tipo(tipo) else None


def valor(mensaje, nombre):
    return next((m["valor"] for m in mensaje["metricas"] if m["nombre"] == nombre), None)


async def esperar(obs, condicion, timeout=20.0):
    assert await asyncio.to_thread(obs.esperar, condicion, timeout), "timeout esperando el mensaje"


def cuenta(tipo, n):
    return lambda ms: sum(1 for m in ms if m["tipo"] == tipo) >= n


@pytest.mark.asyncio
async def test_ciclo_de_vida_completo(tmp_path, metricas, topicos):
    puerto = 18800 + random.randint(0, 500)
    broker = BrokerDesarrollo(tmp_path / "broker", puerto, CLAVES).iniciar()
    servidor = await ServidorPrueba(metricas, 48100 + random.randint(0, 300)).iniciar()
    obs = Observador(tmp_path / "observador.jsonl", metricas)
    c_obs = crear_cliente("127.0.0.1", puerto, "observador", CLAVES["observador"], ca=broker.ca, id_cliente="obs")
    obs.conectar(c_obs, "127.0.0.1", puerto)
    host = crear_cliente("127.0.0.1", puerto, "host_app", CLAVES["host_app"], ca=broker.ca, id_cliente="host")
    host.connect("127.0.0.1", puerto, 30)
    host.loop_start()
    assert await asyncio.to_thread(obs.suscripto.wait, 10)
    edge = lanzar_edge(tmp_path, broker, servidor)
    try:
        # 1. NBIRTH seq 0 + DBIRTH con los valores actuales
        await esperar(obs, cuenta("DBIRTH", 1))
        nbirth = obs.de_tipo("NBIRTH")[0]
        assert nbirth["seq"] == 0 and valor(nbirth, "bdSeq") == 0 and valor(nbirth, "Node Control/Rebirth") is False
        assert valor(nbirth, "Status/OPCUA/Estado") == "DONE" or obs.de_tipo("NDATA")
        assert obs.de_tipo("DBIRTH")[0]["seq"] >= 1 and not nbirth["retenido"]
        # (La QoS que ve un suscriptor es la de ENTREGA; amqtt entrega con QoS 1 lo publicado con 0.
        # La QoS de publicacion se verifica en el registro del propio Edge Node, al final.)

        # 2. DDATA solo ante cambio, con alias y el valor nuevo
        await servidor.escribir("ns=1;s=Dispositivo1.Inputs.Potenciometro", 3210)
        await esperar(obs, lambda ms: any(m["tipo"] == "DDATA" and valor(m, "Inputs/Potenciometro") == 3210 for m in ms))

        # 3. Camino de comando: DCMD -> Write OPC UA -> valor en el servidor -> DDATA de confirmacion
        host.publish(topicos.de("DCMD"), payload_dcmd(metricas, "Outputs/LedDigital", True), qos=0)
        await esperar(obs, lambda ms: any(m["tipo"] == "DDATA" and valor(m, "Outputs/LedDigital") is True for m in ms))
        assert await servidor.leer("ns=1;s=Dispositivo1.Outputs.LedDigital") is True
        host.publish(topicos.de("DCMD"), payload_dcmd(metricas, "Outputs/LedPWM", 200), qos=0)
        await esperar(obs, lambda ms: any(m["tipo"] == "DDATA" and valor(m, "Outputs/LedPWM") == 200 for m in ms))

        # 4. Perdida del esclavo (DEVICE NOT REACHED sostenido) -> DDEATH; vuelve -> DBIRTH nuevo
        await servidor.escribir("ns=1;s=Status.MODBUS.Estado", "DEVICE NOT REACHED")
        await esperar(obs, cuenta("DDEATH", 1))
        await servidor.escribir("ns=1;s=Status.MODBUS.Estado", "DONE")
        await esperar(obs, cuenta("DBIRTH", 2))

        # 5. NCMD Rebirth -> NBIRTH seq 0, MISMO bdSeq, Rebirths = 1, y DBIRTH
        host.publish(topicos.de("NCMD"), payload_rebirth(), qos=0)
        await esperar(obs, cuenta("DBIRTH", 3))
        rebirth = obs.de_tipo("NBIRTH")[1]
        assert rebirth["seq"] == 0 and valor(rebirth, "bdSeq") == 0 and valor(rebirth, "Status/Sparkplug/Rebirths") == 1

        # 6. Corte del broker -> reconexion sola: bdSeq + 1, NBIRTH seq 0, Reconexiones = 1 (I-10)
        await asyncio.to_thread(broker.reiniciar, 0.5)
        await esperar(obs, cuenta("NBIRTH", 3), timeout=40)
        reconexion = obs.de_tipo("NBIRTH")[2]
        assert reconexion["seq"] == 0 and valor(reconexion, "bdSeq") == 1
        assert valor(reconexion, "Status/MQTT/Reconexiones") == 1
        await esperar(obs, cuenta("DBIRTH", 4))

        # 7. kill del proceso -> el BROKER publica el NDEATH (Will) con el bdSeq del NBIRTH vigente
        edge.kill()
        edge.wait(10)
        await esperar(obs, cuenta("NDEATH", 1))
        ndeath = obs.de_tipo("NDEATH")[0]
        assert ndeath["seq"] is None and valor(ndeath, "bdSeq") == 1 and ndeath["bdSeq_coincide"] is True

        # 8. Proceso nuevo: el bdSeq persistido sigue la cuenta
        edge = lanzar_edge(tmp_path, broker, servidor)
        await esperar(obs, cuenta("NBIRTH", 4))
        assert valor(obs.de_tipo("NBIRTH")[3], "bdSeq") == 2

        # Los siete tipos de la evidencia N2.4 y ninguna violacion de seq/bdSeq
        assert {"NBIRTH", "DBIRTH", "NDATA", "DDATA", "DCMD", "DDEATH", "NDEATH"} <= {m["tipo"] for m in obs.mensajes}
        assert obs.violaciones == []
        # El registro JSONL del propio Edge Node tiene tx y rx con seq y bdSeq
        registro = (tmp_path / "logs").glob("edge-node-*.jsonl")
        lineas = [__import__("json").loads(l) for f in registro for l in f.read_text(encoding="utf-8").splitlines()]
        assert {"tx", "rx", "write"} <= {l["dir"] for l in lineas}
        assert all("bdSeq" in l and "metricas" in l for l in lineas if l["dir"] == "tx")
        qos = {l["tipo"]: l["qos"] for l in lineas if l["dir"] == "tx"}
        assert {qos[t] for t in ("NBIRTH", "DBIRTH", "NDATA", "DDATA", "DDEATH")} == {0}   # payloads-*-qos
    finally:
        edge.kill()
        edge.wait(10)
        host.loop_stop()
        c_obs.loop_stop()
        await servidor.detener()
        broker.detener()
