#!/usr/bin/env python3
"""
analizar_banco.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Convierte la evidencia del banco virtual (tools/banco_virtual.js) en las tablas de
docs/mediciones.md (F7): latencias, trafico por capa, eficiencia de trama, recuperacion de fallas
y resistencia. Nada se estima si se puede medir: los tamanos salen de las capturas (tshark) y del
registro del observador. Lo que se CALCULA (encapsulado Ethernet, ocupacion del bus RS-485) se
calcula con las mismas constantes que la Tarea 2 (se importan de su eficiencia_trama.py).

Uso (en tarea-3/):
    python tools/analizar_banco.py --medicion <dir campana completa> --fallas <dir campana de fallas>
           [--resistencia <dir>] [--salida docs/mediciones.md]

Dependencias externas: Wireshark (tshark) en el PATH o en C:/Program Files/Wireshark.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import statistics as st
import subprocess
import sys
from pathlib import Path

T3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(T3.parent / "tarea-2" / "versiones" / "v3-node-red" / "herramientas"))
import eficiencia_trama as t2   # noqa: E402  (constantes y trama_ethernet de la Tarea 2)

TSHARK = shutil.which("tshark") or "C:/Program Files/Wireshark/tshark.exe"
PUERTOS = {"MODBus RTU (TCP de desarrollo)": 5020, "OPC UA (SignAndEncrypt)": 4840,
           "MQTT/TLS Edge Node ↔ broker": 28893, "MQTT/WebSocket web ↔ broker": 28884}
TOPICO_DCMD = "spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/DEV01_ESP32_Slave"


def tshark(pcap: Path, filtro: str, campos: list[str], decode: str | None = None) -> list[list[str]]:
    args = [TSHARK, "-r", str(pcap), "-Y", filtro, "-T", "fields"] + sum((["-e", c] for c in campos), [])
    if decode:
        args[1:1] = ["-d", decode]
    salida = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return [l.split("\t") for l in salida.splitlines() if l.strip()]


def stats(xs) -> str:
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, round(0.95 * (len(xs) - 1)))]
    return f"{xs[0]:.0f} | {st.median(xs):.0f} | {p95:.0f} | {xs[-1]:.0f} | {len(xs)}"


# =============================================================================
# Secciones
# =============================================================================

def latencias(r) -> list[str]:
    L, C = r["latencias"]["lectura"], r["latencias"]["comando"]
    return [
        "## 1. Latencia extremo a extremo",
        "",
        "### 1.1 Lectura: el pulsador cambia en el esclavo → se ve en la pantalla",
        "",
        "Se cambia el pulsador del simulador por su entrada estándar (t₀) y se toma el instante en que la",
        "página lo muestra (MutationObserver en Chrome). El instante intermedio sale del `timestamp` de la",
        "métrica en el DDATA, que es el SourceTimestamp OPC UA, es decir, el momento en que el maestro leyó",
        "el registro. Todos los relojes son de la misma PC, así que las restas son válidas. Entre muestras se",
        "espera un tiempo aleatorio, para no quedar en fase con el ciclo de sondeo.",
        "",
        "| Tramo | mín (ms) | mediana | p95 | máx | n |",
        "|---|---|---|---|---|---|",
        f"| Campo → servidor OPC UA (espera del sondeo + transacción MODBus) | {stats([x['campoAopcua'] for x in L])} |",
        f"| Servidor OPC UA → broker (muestreo + publicación de la suscripción + Edge Node + TLS) | {stats([x['opcuaAbroker'] for x in L])} |",
        f"| Broker → pantalla (WebSocket + decodificación + dibujo) | {stats([x['brokerAweb'] for x in L])} |",
        f"| Total | {stats([x['total'] for x in L])} |",
        "",
        "**Lectura.** El cuello de botella son los dos muestreos periódicos y no la red:",
        "",
        "- **Campo → OPC UA**, con datos medidos en `trafico-regimen.pcapng`:",
        "  - El ciclo de sondeo real mide 262 ms (250 configurados más la sobrecarga). Esperar el FC 02",
        "    siguiente cuesta ≈ 131 ms en promedio.",
        "  - Cada transacción dura ≈ 31 ms. Las cuatro van seguidas, así que el bus está ocupado 124 de cada",
        "    262 ms.",
        "  - Se suma el refresco de entradas del simulador: cada 50 ms, y solo con el bus libre. En el ESP32",
        "    real cumple ese papel el muestreo del pulsador del firmware.",
        "  - El total da una mediana de ≈ 200 ms, que coincide con lo medido.",
        "- **La suscripción OPC UA** (SamplingInterval y PublishingInterval de 100 ms, ADR-004) suma hasta 200 ms.",
        "- La web aporta un orden de magnitud menos, gracias a que dibuja en el cuadro siguiente al mensaje.",
        "  Antes lo hacía en un ciclo fijo de 250 ms; se corrigió en F7.",
        "",
        "Para bajar la latencia habría que acortar el sondeo o la suscripción, a costa de más tráfico (§2).",
        "",
        "### 1.2 Comando: clic en la web → LED del esclavo → confirmación en pantalla",
        "",
        "| Tramo | mín (ms) | mediana | p95 | máx | n |",
        "|---|---|---|---|---|---|",
        f"| Clic → el LED del esclavo cambia (DCMD → Write OPC UA → FC 05) | {stats([x['alLed'] for x in C])} |",
        f"| Clic → la web muestra CONFIRMADO (la lectura siguiente vuelve por DDATA) | {stats([x['aConfirmado'] for x in C])} |",
        "",
        "El comando llega rápido porque no espera ningún muestreo: es un Write que el maestro pone delante",
        "de la cola de lecturas. La **confirmación** sí espera la lectura FC 01 siguiente y la publicación",
        "OPC UA. La web solo marca CONFIRMADO cuando ve el valor real (ADR-015), y por eso tarda más.",
        "",
    ]


def trafico(r, dir_med: Path) -> list[str]:
    obs = [json.loads(l) for l in (dir_med / "observador.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    filas, spb = [], []
    for nombre in ("regimen", "reposo"):
        v = r["ventanas"][nombre]
        pcap = dir_med / v["pcap"]
        dur = (v["t1"] - v["t0"]) / 1000
        for capa, puerto in PUERTOS.items():
            datos = tshark(pcap, f"tcp.port=={puerto} && tcp.len>0", ["tcp.len"])
            tramas, carga = len(datos), sum(int(d[0]) for d in datos)
            eth = sum(t2.trama_ethernet(int(d[0]), t2.OPCIONES_TCP_LINUX)["cable"] for d in datos)
            extra = ""
            if puerto == 5020:
                # Ocupacion del bus RS-485 a 9600 8N1: 10 bits por byte + silencio t3,5 por trama.
                bits = carga * t2.BITS_POR_CARACTER + tramas * t2.SILENCIO_T35 * t2.BITS_POR_CARACTER
                extra = f"{100 * bits / t2.BAUDIOS / dur:.0f} % del bus a 9600 bps"
            # En el producto MODBus viaja por RS-485, no por Ethernet: el TCP es solo el transporte de desarrollo.
            eth_txt = "— (RS-485 en el producto)" if puerto == 5020 else f"{eth / dur:.0f}"
            filas.append(f"| {nombre} | {capa} | {tramas / dur:.1f} | {carga / dur:.0f} | {eth_txt} | {extra} |")
        t0, t1 = v["t0"], v["t1"]
        en = [m for m in obs if t0 <= dt.datetime.fromisoformat(m["ts"]).timestamp() * 1000 <= t1]
        tipos = {}
        for m in en:
            tipos.setdefault(m["tipo"], []).append(m["bytes"])
        spb.append(f"| {nombre} | " + " · ".join(f"{t}: {len(b) / dur:.2f}/s ({st.median(b):.0f} B)"
                                                for t, b in sorted(tipos.items()) if t) + " |")
    return [
        "## 2. Tráfico por capa: régimen y reposo",
        "",
        "Hay dos ventanas de 60 s capturadas con `dumpcap` en el loopback:",
        "",
        "- **Régimen**: el simulador en modo automático mueve el potenciómetro (rampa triangular de 20 s) y",
        "  cambia el pulsador cada 3 s (`simuladores/esclavo_modbus_sim.py`, `actualizar_entradas`).",
        "- **Reposo**: los valores quedan fijos.",
        "",
        "En las columnas, *Carga* son los bytes de la aplicación (payload TCP) y *Ethernet* es lo mismo",
        "encapsulado en Ethernet II + IPv4 + TCP con timestamps. Esto último se calcula con `trama_ethernet`",
        "de la T2.",
        "",
        "| Ventana | Capa | Tramas/s | Carga (B/s) | Ethernet (B/s) | Nota |",
        "|---|---|---|---|---|---|",
        *filas,
        "",
        "Mensajes Sparkplug B por tipo (registro del observador), con tasa y tamaño mediano del payload Protobuf:",
        "",
        "| Ventana | Mensajes |",
        "|---|---|",
        *spb,
        "",
        "**Lectura**",
        "",
        "- **MODBus no se entera del reposo**: el maestro sondea igual. Es el costo de un protocolo de",
        "  sondeo frente a uno por excepción.",
        "- **OPC UA y Sparkplug sí bajan en reposo**, pero no a cero. Los contadores `Status/MODBUS/OK`",
        "  cambian con cada respuesta: en OPC UA viajan en cada PublishResponse, y en Sparkplug en un",
        "  NDATA por segundo (ADR-021).",
        "- **Hay además un piso fijo en OPC UA**: el watchdog del cliente asyncua lee `ServerState` una vez",
        "  por segundo (T2), y se suman los KeepAlive de la suscripción.",
        "",
    ]


def eficiencia(r, dir_med: Path) -> list[str]:
    """Una word (UInt16) del comando LedPWM, medida en las tres capas."""
    pc = dir_med / r["capturas"]["eficiencia-None"]["pcap"]
    pe = dir_med / r["capturas"]["eficiencia-SignAndEncrypt"]["pcap"]
    fc06 = tshark(pc, "tcp.port==5020 && tcp.len>0 && tcp.payload[1:1]==06", ["tcp.len", "tcp.payload"])
    mb = int(fc06[0][0])
    trama_mb = fc06[0][1]
    ua_none = {int(d[0]): int(d[1]) for d in tshark(pc, "opcua.servicenodeid.numeric==673 || opcua.servicenodeid.numeric==676",
                                                    ["opcua.servicenodeid.numeric", "tcp.len"], decode="tcp.port==4840,opcua")}
    # SignAndEncrypt: el cifrado oculta el servicio. El WriteRequest se identifica por tamano: es el mensaje
    # cliente->servidor que NO es PublishRequest (el mas frecuente) y comparte tamano con el Read del
    # watchdog porque AES-CBC rellena a bloques de 16 bytes.
    tam_c = sorted({int(d[0]) for d in tshark(pe, "tcp.dstport==4840 && tcp.len>0", ["tcp.len"])})
    tam_s = [int(d[0]) for d in tshark(pe, "tcp.srcport==4840 && tcp.len>0", ["tcp.len"])]
    ua_sae_req = max(tam_c)
    ua_sae_resp = min(t for t in set(tam_s) if tam_s.count(t) >= 5)
    obs = [json.loads(l) for l in (dir_med / "observador.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    payload_dcmd = st.median(m["bytes"] for m in obs if m["tipo"] == "DCMD")
    mqtt_pub = 1 + 1 + 2 + len(TOPICO_DCMD) + int(payload_dcmd)     # QoS 0: sin Packet Identifier
    # Registro TLS broker -> Edge que lleva el DCMD: PUBLISH + 22 B de TLS 1.3. amqtt lo entrega con QoS 1
    # (desvio ya visto en F5: sube la QoS de entrega), lo que agrega el Packet Identifier de 2 B; con un
    # broker que respete min(QoS publicada, QoS suscripta) serian +22 y no +24.
    tam_tls = {int(d[0]) for d in tshark(pe, "tcp.srcport==28893 && tcp.len>0", ["tcp.len"])}
    tls_dcmd = next(t for t in (mqtt_pub + 24, mqtt_pub + 22) if t in tam_tls)
    util = t2.BYTES_UTILES

    def fila(capa, mensaje, app, nota=""):
        eth = t2.trama_ethernet(app, t2.OPCIONES_TCP_LINUX)["cable"]
        return f"| {capa} | {mensaje} | {app} | {100 * util / app:.1f} % | {eth} | {100 * util / eth:.2f} % | {nota} |"

    bits_mb = mb * t2.BITS_POR_CARACTER + t2.SILENCIO_T35 * t2.BITS_POR_CARACTER
    return [
        "## 3. Eficiencia de trama: una word, en las tres capas",
        "",
        "Es la misma pregunta de la T2 (consigna 4.6), extendida a la T3: cuántos bytes útiles hay sobre los",
        "bytes totales al transmitir **una word**. Se toma el comando `Outputs/LedPWM` (UInt16), porque es",
        "el único dato que atraviesa las tres capas como un mensaje de un solo valor: DCMD → WriteRequest →",
        "FC 06. Útiles = 2 bytes.",
        "",
        "Todos los tamaños de mensaje están **medidos**: `eficiencia-*.pcapng` para MODBus, OPC UA y MQTT/TLS,",
        "y el registro del observador para el payload Protobuf. El encapsulado Ethernet (preámbulo, cabeceras",
        "con timestamps TCP, FCS e IFG) se calcula con `trama_ethernet` de la T2.",
        "",
        "| Capa | Mensaje | Bytes del mensaje | Eficiencia | Bytes en el cable Ethernet | Eficiencia en el cable | Nota |",
        "|---|---|---|---|---|---|---|",
        f"| MODBus RTU | FC 06 `{' '.join(trama_mb[i:i+2] for i in range(0, len(trama_mb), 2))}` | {mb} | "
        f"{100 * util / mb:.1f} % | — (RS-485: {bits_mb:.0f} bits con t3,5 = {1000 * bits_mb / t2.BAUDIOS:.2f} ms) | "
        f"{100 * util * 8 / bits_mb:.1f} % de los bits | 9600 8N1 |",
        fila("OPC UA None", "WriteRequest", ua_none[673], f"respuesta {ua_none[676]} B"),
        fila("OPC UA SignAndEncrypt", "WriteRequest (identificado por tamaño)", ua_sae_req, f"respuesta {ua_sae_resp} B"),
        fila("Sparkplug B (MQTT)", f"DCMD: PUBLISH {mqtt_pub} B = 2 + 2 + tópico {len(TOPICO_DCMD)} + Protobuf {int(payload_dcmd)}",
             mqtt_pub, "sin TLS"),
        fila("Sparkplug B (MQTT/TLS 1.3)", "el mismo PUBLISH en un registro TLS (medido, broker → Edge)", tls_dcmd,
             "+22 B de TLS (cabecera 5, tipo 1, tag AEAD 16)" + (" +2 B de Packet Id (amqtt entrega con QoS 1)" if tls_dcmd == mqtt_pub + 24 else "")),
        "",
        "**Lectura**",
        "",
        f"- **MODBus RTU es la más eficiente en bytes** ({100 * util / mb:.0f} %) **y la más lenta en el medio**",
        "  (9600 bps).",
        f"- **OPC UA ocupa {ua_none[673] // mb} veces más bytes** que MODBus para la misma word. El cifrado lo lleva",
        f"  a {ua_sae_req // mb} veces, por la firma HMAC de 32 B y el relleno AES.",
        f"- **El DCMD Sparkplug está en el medio en tamaño**: lo que más pesa es el **tópico** ({len(TOPICO_DCMD)} de",
        f"  {mqtt_pub} B), no el Protobuf. Es la misma razón por la que Sparkplug 3.0 manda los DATA solo con",
        "  alias: si cada métrica llevara su nombre (`Inputs/Potenciometro_pct`, 24 B), el payload pesaría tanto",
        "  como el tópico.",
        "- **En el cable Ethernet las tres variantes TCP quedan por debajo del 2 %.** La sobrecarga es fija",
        "  por mensaje. Se amortiza agrupando valores: un DDATA con potenciómetro y porcentaje (ADR-021), o",
        "  un PublishResponse con varias notificaciones.",
        "- **Con SignAndEncrypt, el tamaño ya no revela el servicio**: el Write y el Read del watchdog miden",
        "  igual. Es un efecto del relleno a bloques que también protege contra el análisis de tráfico.",
        "",
    ]


def fallas(r) -> list[str]:
    filas = []
    for fid, f in r["fallas"].items():
        rec = f"{f['recuperacionMs'] / 1000:.1f} s" if f.get("recuperacionMs") is not None else "—"
        filas.append(f"| {fid} | {f['desc']} | {f['resultado']} | {f['deteccionMs'] / 1000:.2f} s · {f.get('detalleDeteccion', '')} | "
                     f"{rec} · {f.get('detalleRecuperacion', '') or 'sin recuperación automática: hay que corregir la causa'} |")
    return [
        "## 4. Detección y recuperación de cada falla (plan de pruebas N4)",
        "",
        "*Detección* se mide desde que se inyecta la falla hasta el primer síntoma en la capa que",
        "corresponde, visto por el observador o por la web. *Recuperación* se mide desde que se quita la",
        f"causa hasta que todo vuelve EN LÍNEA. Campaña del {r['fecha'][:10]}, commit `{r['commit']}`.",
        f"El observador registró **{len(r.get('violaciones') or [])} violaciones** de `seq`/`bdSeq` en toda la campaña.",
        "",
        "| ID | Falla | Resultado | Detección | Recuperación |",
        "|---|---|---|---|---|",
        *filas,
        "",
        "**Lectura de los tiempos**",
        "",
        "- **F-01 y F-03 detectan en ≈ 2 s** por diseño: es la ausencia sostenida de 2000 ms (ADR-014). Un",
        "  timeout aislado no mata al dispositivo.",
        "- **F-06 detecta en ≈ 15-18 s**: es el keepalive MQTT (10 s × 1,5), el único mecanismo posible",
        "  cuando un cable se corta sin FIN ni RST.",
        "- **F-05 (kill) detecta en milisegundos**, porque el sistema operativo cierra el socket.",
        "- **Los tiempos de recuperación incluyen el retroceso exponencial (ADR-023)**. Una caída larga puede",
        "  tardar hasta 30 s más en recuperarse.",
        "",
    ]


def resistencia(dir_res: Path) -> list[str]:
    r = json.loads((dir_res / "resistencia.json").read_text(encoding="utf-8"))
    m = r["muestras"]
    procesos = list(m[0]["memoriaMiB"])
    filas = []
    for p in procesos + ["web (heap JS)"]:
        serie = [x["webMiB"] if p == "web (heap JS)" else x["memoriaMiB"].get(p) for x in m]
        serie = [v for v in serie if v is not None]
        n = max(1, len(serie) // 5)
        filas.append(f"| {p} | {st.mean(serie[:n]):.1f} | {st.mean(serie[-n:]):.1f} | {st.mean(serie[-n:]) - st.mean(serie[:n]):+.1f} | {max(serie):.1f} |")
    obs = [json.loads(l) for l in (dir_res / "observador.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    seqs = [x["seq"] for x in obs if x.get("seq") is not None and x["tipo"] in ("NDATA", "DDATA", "DBIRTH", "DDEATH")]
    vueltas = sum(1 for a, b in zip(seqs, seqs[1:]) if a == 255 and b == 0)
    tipos = {}
    for x in obs:
        tipos[x["tipo"]] = tipos.get(x["tipo"], 0) + 1
    def delta(nombre):
        """Crecimiento de un contador durante la prueba (los contadores se persisten: importa la diferencia)."""
        v = [x2["valor"] for x in obs for x2 in x.get("metricas", []) if x2["nombre"] == nombre and x2["valor"] is not None]
        return v[-1] - v[0] if v else None
    contadores = {n: delta(f"Status/MODBUS/{n}") for n in ("OK", "CRC_ERROR", "TIMEOUT", "EXCEPTION")}
    return [
        f"## 5. Resistencia: {r['minutos']} minutos (plan de pruebas E2E-05)",
        "",
        f"La cadena completa funcionó con el simulador en modo automático. Se tomó una muestra de memoria",
        f"cada 30 s ({len(m)} muestras): working set del árbol de procesos y heap JS de la página. Commit",
        f"`{r['commit']}` con los cambios de F7.",
        "",
        "| Proceso | Primer 20 % (MiB) | Último 20 % (MiB) | Diferencia | Máximo |",
        "|---|---|---|---|---|",
        *filas,
        "",
        "**Cómo leer la memoria.**",
        "",
        "- En Windows, el *working set* lo recorta el propio sistema operativo cuando un proceso está",
        "  estable. Por eso que baje **no** prueba que se liberó memoria.",
        "- Lo que sí indica es que **ningún proceso crece de forma sostenida** en 30 minutos.",
        "- El dato más limpio es el heap JS de la página, que lo mide el propio motor de JavaScript, sin",
        "  intervención del sistema operativo. Varía menos de 1 MiB.",
        "- Los picos de Node-RED son ciclos del recolector de basura, no una tendencia.",
        "- Para afirmar que no hay fugas en el producto, hay que repetir la prueba en la Raspberry Pi midiendo",
        "  RSS o PSS (`/proc/<pid>/smaps_rollup`). Queda **pendiente del banco**.",
        "",
        f"- **Mensajes Sparkplug**: {', '.join(f'{k} {v}' for k, v in sorted(tipos.items()) if k)}.",
        f"- **`seq`**: dio **{vueltas} vueltas de 255 a 0**, con **{len(r.get('violaciones') or [])} violaciones**.",
        f"- **MODBus durante la prueba**: {contadores['OK']} transacciones correctas; los errores crecieron en",
        f"  CRC_ERROR +{contadores['CRC_ERROR']}, TIMEOUT +{contadores['TIMEOUT']} y EXCEPTION +{contadores['EXCEPTION']}.",
        "  Los valores absolutos de la web son históricos, porque los contadores persisten entre reinicios y",
        "  arrastran las campañas de fallas. El criterio E2E-05 es que no crezcan.",
        f"- **Sin NDEATH ni DDEATH** en toda la prueba: {tipos.get('NDEATH', 0)} y {tipos.get('DDEATH', 0)}.",
        f"- **Rebirths pedidos por la web al final**: {m[-1]['web']['rebirths']}. Uno es el de la conexión inicial;",
        "  uno más indicaría mensajes perdidos.",
        f"- **Registro de eventos de la web**: {m[-1]['web']['eventos']} entradas, acotado a 300 por diseño.",
        "",
    ]


def main():
    p = argparse.ArgumentParser(description="Tablas de docs/mediciones.md desde el banco virtual")
    p.add_argument("--medicion", type=Path, required=True)
    p.add_argument("--fallas", type=Path, required=True)
    p.add_argument("--resistencia", type=Path)
    p.add_argument("--salida", type=Path, default=T3 / "docs" / "mediciones.md")
    a = p.parse_args()
    rm = json.loads((a.medicion / "resultados.json").read_text(encoding="utf-8"))
    rf = json.loads((a.fallas / "resultados.json").read_text(encoding="utf-8"))
    texto = [
        "# Mediciones de la cadena completa (F7)",
        "",
        "> **Dónde y cómo se midió.** Banco virtual en la PC (`tools/banco_virtual.js`), con todo el software",
        "> del producto: el stack MODBus del firmware (en el simulador), Node-RED con el maestro y el servidor",
        "> OPC UA (SignAndEncrypt + usuario), el Edge Node, un broker MQTT con TLS (amqtt local) y la Host",
        "> Application en Chrome.",
        ">",
        "> **No son del banco real**:",
        "> - el ESP32 y el bus RS-485 (los reemplaza el simulador por TCP, con la misma trama RTU);",
        "> - el broker en la nube (la latencia de internet no está incluida).",
        ">",
        "> Los números de banco con hardware quedan **pendientes**, y se miden con este mismo procedimiento.",
        f"> Mediciones del {rm['fecha'][:10]}, sobre el commit `{rm['commit']}` con los cambios de F7 (el commit que agrega",
        "> este archivo). Generado por `tools/analizar_banco.py`.",
        "",
        *latencias(rm),
        *trafico(rm, a.medicion),
        *eficiencia(rm, a.medicion),
        *fallas(rf),
    ]
    if a.resistencia and (a.resistencia / "resistencia.json").exists():
        texto += resistencia(a.resistencia)
    else:
        texto += ["## 5. Resistencia", "", "*Pendiente de la corrida de 30 minutos.*", ""]
    a.salida.write_text("\n".join(texto), encoding="utf-8")
    print(f"escrito {a.salida}")


if __name__ == "__main__":
    main()
