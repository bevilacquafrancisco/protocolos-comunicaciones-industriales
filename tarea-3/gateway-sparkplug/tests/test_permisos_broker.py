"""
test_permisos_broker.py — el sistema con los permisos del broker (ADR-026, ADR-027).
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-14 · v1.1 (2026-11-16: perfiles renombrados)

El broker del banco (EMQX Cloud Serverless, ADR-027) aplica el minimo privilegio del ADR-005: el
perfil 'minimo'. El perfil 'un_filtro' reproduce un broker con UN permiso y UN filtro por credencial
(HiveMQ Cloud Serverless, ADR-026, ya retirado). Con los dos se prueban dos cosas sin la nube:

1. El Edge Node publica aunque el broker le rechace la suscripcion a STATE (opcional en Sparkplug
   3.0 salvo con --esperar-host). Antes de esta correccion, cualquier SUBACK 0x80 cortaba la conexion
   y el nodo no habria arrancado nunca contra el broker del banco.
2. Que cambia en seguridad entre los dos perfiles: con 'minimo', la clave de la web (publica de
   hecho, ADR-005) no puede publicar un NBIRTH falso; con 'un_filtro', si. Es la diferencia de
   riesgo entre el ADR-026 y el ADR-027.
"""

import asyncio
import random
import threading
import time

import pytest

import sparkplug as spb
from broker_dev import BrokerDesarrollo
from observador_sparkplug import Observador, crear_cliente
from servidor_prueba import ServidorPrueba
from test_sistema import CLAVES, lanzar_edge

pytestmark = pytest.mark.red


def broker(tmp_path, perfil):
    return BrokerDesarrollo(tmp_path / f"broker-{perfil}", 19300 + random.randint(0, 600), CLAVES, acl=perfil).iniciar()


def conectar(b, usuario, id_cliente):
    c = crear_cliente("127.0.0.1", b.puerto, usuario, CLAVES[usuario], ca=b.ca, id_cliente=id_cliente)
    listo = threading.Event()
    c.on_connect = lambda *a: listo.set()
    c.connect("127.0.0.1", b.puerto, 30)
    c.loop_start()
    assert listo.wait(10), f"{usuario} no conecto"
    return c


def observar(b):
    obs = Observador(None)
    c = crear_cliente("127.0.0.1", b.puerto, "observador", CLAVES["observador"], ca=b.ca, id_cliente="obs")
    obs.conectar(c, "127.0.0.1", b.puerto)
    assert obs.suscripto.wait(10)
    return obs, c


@pytest.mark.asyncio
async def test_edge_node_publica_con_un_solo_filtro_por_credencial(tmp_path, metricas):
    b = broker(tmp_path, "un_filtro")
    servidor = await ServidorPrueba(metricas, 48500 + random.randint(0, 300)).iniciar()
    obs, c_obs = observar(b)
    edge = lanzar_edge(tmp_path, b, servidor)
    try:
        assert await asyncio.to_thread(obs.esperar, lambda ms: any(m["tipo"] == "DBIRTH" for m in ms), 30), \
            "el Edge Node no publico: un SUBACK rechazado para STATE no debe cortar la conexion"
        log = next(tmp_path.glob("edge-*.log")).read_text(encoding="utf-8", errors="replace")
        assert "no autoriza spBv1.0/STATE/HA01_WebDashboard" in log
    finally:
        edge.kill()
        edge.wait(10)
        c_obs.loop_stop()
        await servidor.detener()
        b.detener()


@pytest.mark.parametrize("perfil,nbirth_falso_llega", [("un_filtro", True), ("minimo", False)])
def test_clave_de_la_web_y_nbirth_falso(tmp_path, perfil, nbirth_falso_llega):
    b = broker(tmp_path, perfil)
    obs, c_obs = observar(b)
    web = conectar(b, "host_app", "web")
    try:
        t = spb.Topicos("UNRaf_PdCI_2026", "EN01_Gateway", "DEV01_ESP32_Slave", "HA01_WebDashboard")
        falso = spb.armar_payload([spb.ValorMetrica("bdSeq", None, "Int64", 99)], seq=0)
        web.publish(t.de("NBIRTH"), falso, qos=1).wait_for_publish(5)
        web.publish(t.de("NCMD"), spb.armar_payload([spb.ValorMetrica("Node Control/Rebirth", None, "Boolean", True)],
                                                     seq=None), qos=1).wait_for_publish(5)
        assert obs.esperar(lambda ms: any(m["tipo"] == "NCMD" for m in ms), 10), "el NCMD de la web debe pasar siempre"
        time.sleep(0.5)
        llego = any(m["tipo"] == "NBIRTH" for m in obs.mensajes)
        assert llego is nbirth_falso_llega
    finally:
        web.loop_stop()
        c_obs.loop_stop()
        b.detener()
