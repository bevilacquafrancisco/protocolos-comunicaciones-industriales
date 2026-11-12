#!/usr/bin/env python3
"""
observador_sparkplug.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Suscriptor de solo lectura a spBv1.0/# (usuario 'observador', ADR-005): decodifica cada payload
Sparkplug B (Protobuf), lo archiva como JSON por linea y VERIFICA en vivo las reglas que la
defensa tiene que poder mostrar:

    - seq: NBIRTH = 0 y cada mensaje siguiente del mismo Edge Node = anterior + 1 (mod 256)
    - bdSeq: el NDEATH (Will emitido por el broker) trae el mismo bdSeq que el NBIRTH vigente
    - todo DATA/DEATH de un dispositivo llega despues de su DBIRTH

Es la evidencia archivada de los siete tipos de mensaje (plan de pruebas N2.4) y complementa a
MQTT Explorer (que muestra los mensajes pero no verifica la secuencia).

Uso (en gateway-sparkplug/, con el .env: MQTT_HOST, MQTT_USUARIO_OBSERVADOR, MQTT_CLAVE_OBSERVADOR):
    python tools/observador_sparkplug.py --salida ../docs/capturas/sparkplug-sesion.jsonl
    python tools/observador_sparkplug.py --mqtt-ca .dev-broker/ca.pem --puerto 18883 ...

Dependencias externas: paho-mqtt 2.1.0, protobuf 7.36.2.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import sparkplug as spb                      # noqa: E402
from metrics import cargar_metricas          # noqa: E402


def crear_cliente(host, puerto, usuario, clave, ca=None, tls=True, id_cliente="") -> mqtt.Client:
    """Cliente paho MQTT 3.1.1 con TLS verificado (ca=None -> CAs del sistema)."""
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=id_cliente, clean_session=True,
                    protocol=mqtt.MQTTv311)
    c.username_pw_set(usuario, clave)
    if tls:
        contexto = ssl.create_default_context(cafile=str(ca) if ca else None)
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        c.tls_set_context(contexto)
    return c


class Observador:
    """
    Recibe, decodifica, verifica y archiva.

    Atributos:
        mensajes (list[dict]): todo lo recibido, en orden.
        violaciones (list[str]): reglas de Sparkplug incumplidas (vacia = sesion correcta).
    """

    def __init__(self, salida: Path | None = None, metricas=None, eco: bool = False):
        self.mensajes: list[dict] = []
        self.violaciones: list[str] = []
        self._salida = salida
        self._metricas = metricas or cargar_metricas()
        self._eco = eco
        self._lock = threading.Lock()
        self._nodos: dict[str, dict] = {}       # nodo -> {'seq', 'bdSeq', 'dispositivos'}
        self.suscripto = threading.Event()
        if salida:
            salida.parent.mkdir(parents=True, exist_ok=True)

    def _resolver(self, alias):
        m = self._metricas.por_alias(alias)
        return (m.nombre, m.tipo) if m else None

    def al_mensaje(self, topico: str, payload: bytes, retenido: bool, qos: int) -> dict:
        info = spb.analizar_topico(topico) or {"tipo": None}
        linea = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), "topico": topico,
                 "tipo": info["tipo"], "qos": qos, "retenido": retenido, "bytes": len(payload)}
        if info["tipo"] == "STATE":
            linea["state"] = spb.leer_state(payload)
        elif info["tipo"]:
            try:
                linea.update(spb.describir(payload, self._resolver))
            except ValueError as exc:
                linea["error"] = str(exc)
        with self._lock:
            self._verificar(info, linea)
            self.mensajes.append(linea)
            if self._salida:
                with self._salida.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
        if self._eco:
            metricas = ", ".join(f"{m['nombre']}={m['valor']}" for m in linea.get("metricas", []))
            print(f"{linea['ts'][11:23]} {linea['tipo'] or '?':6s} seq={linea.get('seq')!s:4s} {topico}  {metricas}",
                  flush=True)
        return linea

    def _verificar(self, info, linea) -> None:
        """Reglas de seq y bdSeq por Edge Node (tck-id-payloads-sequence-num-incrementing, nbirth-bdseq-repeat)."""
        tipo = info["tipo"]
        if tipo in (None, "STATE", "NCMD", "DCMD"):
            if tipo in ("NCMD", "DCMD") and linea.get("seq") is not None:
                self.violaciones.append(f"{tipo} con seq (payloads-{tipo.lower()}-seq)")
            return
        nodo = self._nodos.setdefault(info["nodo"], {"seq": None, "bdSeq": None, "dispositivos": set()})
        bd = next((m["valor"] for m in linea.get("metricas", []) if m["nombre"] == "bdSeq"), None)
        seq = linea.get("seq")
        if tipo == "NDEATH":
            if seq is not None:
                self.violaciones.append("NDEATH con seq")
            if nodo["bdSeq"] is not None and bd != nodo["bdSeq"]:
                linea["nota"] = f"NDEATH de otra sesion (bdSeq {bd} != {nodo['bdSeq']}): se ignora"
                return
            linea["bdSeq_coincide"] = nodo["bdSeq"] is not None and bd == nodo["bdSeq"]
            nodo.update(seq=None, dispositivos=set())
            return
        if tipo == "NBIRTH":
            if seq != 0:
                self.violaciones.append(f"NBIRTH con seq {seq}")
            nodo.update(seq=0, bdSeq=bd, dispositivos=set())
            return
        if nodo["seq"] is None:
            self.violaciones.append(f"{tipo} sin NBIRTH previo")
        elif seq != (nodo["seq"] + 1) % 256:
            self.violaciones.append(f"{tipo}: seq {seq} despues de {nodo['seq']}")
        nodo["seq"] = seq
        if tipo == "DBIRTH":
            nodo["dispositivos"].add(info["dispositivo"])
        elif tipo in ("DDATA", "DDEATH"):
            if info["dispositivo"] not in nodo["dispositivos"]:
                self.violaciones.append(f"{tipo} sin DBIRTH vigente")
            if tipo == "DDEATH":
                nodo["dispositivos"].discard(info["dispositivo"])

    def conectar(self, cliente: mqtt.Client, host: str, puerto: int, filtro: str = "spBv1.0/#") -> None:
        cliente.on_connect = lambda c, u, f, rc, p: c.subscribe(filtro, 1)
        cliente.on_subscribe = lambda *a: self.suscripto.set()
        cliente.on_message = lambda c, u, m: self.al_mensaje(m.topic, bytes(m.payload), m.retain, m.qos)
        cliente.connect(host, puerto, 30)
        cliente.loop_start()

    def de_tipo(self, tipo: str) -> list[dict]:
        with self._lock:
            return [m for m in self.mensajes if m["tipo"] == tipo]

    def esperar(self, condicion, timeout: float = 10.0) -> bool:
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            with self._lock:
                if condicion(self.mensajes):
                    return True
            time.sleep(0.05)
        return False


def main() -> None:
    p = argparse.ArgumentParser(description="Observador Sparkplug B: decodifica, verifica seq/bdSeq y archiva")
    p.add_argument("--env", type=Path, default=RAIZ.parent / ".env")
    p.add_argument("--host"), p.add_argument("--puerto", type=int)
    p.add_argument("--mqtt-ca", type=Path)
    p.add_argument("--salida", type=Path, help="archivo .jsonl de evidencia")
    args = p.parse_args()
    from sparkplug_edge_node import cargar_env
    cargar_env(args.env)
    host = args.host or os.environ.get("MQTT_HOST")
    puerto = args.puerto or int(os.environ.get("MQTT_PUERTO_TLS", "8883"))
    obs = Observador(args.salida, eco=True)
    cliente = crear_cliente(host, puerto, os.environ.get("MQTT_USUARIO_OBSERVADOR", "observador"),
                            os.environ.get("MQTT_CLAVE_OBSERVADOR", ""), ca=args.mqtt_ca,
                            id_cliente=f"observador-{os.getpid()}")
    obs.conectar(cliente, host, puerto)
    print(f"observando spBv1.0/# en {host}:{puerto} (Ctrl+C para terminar)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cliente.loop_stop()
        tipos = sorted({m["tipo"] for m in obs.mensajes if m["tipo"]})
        print(f"\n{len(obs.mensajes)} mensajes · tipos: {', '.join(tipos)}")
        print("violaciones:", obs.violaciones or "ninguna")


if __name__ == "__main__":
    main()
