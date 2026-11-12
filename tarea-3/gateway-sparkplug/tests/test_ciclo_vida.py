"""
test_ciclo_vida.py — maquina de estados del Edge Node SIN red (invariantes I-07 e I-10).
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0

Cada prueba cita la regla de Sparkplug 3.0 (tck-id) que verifica.
"""

import pytest

import sparkplug as spb
from ciclo_vida import AlmacenBdSeq, AlmacenBdSeqMemoria, NucleoEdgeNode
from conftest import VALORES_DISPOSITIVO, VALORES_ESTADO, alimentar, nucleo_en_linea


def metricas_de(mensaje, metricas):
    """{nombre: valor} de un mensaje, resolviendo alias."""
    d = spb.describir(mensaje.payload, lambda a: (metricas.por_alias(a).nombre, metricas.por_alias(a).tipo))
    return {m["nombre"]: m["valor"] for m in d["metricas"]}


def dcmd(topicos, metricas_pb, retenido=False):
    p = spb.pb.Payload()
    p.timestamp = 1
    for nombre, alias, tipo, valor in metricas_pb:
        m = p.metrics.add()
        if nombre:
            m.name = nombre
        if alias is not None:
            m.alias = alias
        spb.poner_valor(m, tipo, valor)
    return topicos.de("DCMD"), p.SerializeToString()


# ----------------------------------------------------------------------------- nacimiento
def test_nbirth_seq0_bdseq_rebirth_y_estado_de_las_cuatro_capas(nucleo, metricas):
    will = nucleo.preparar_conexion()
    [nbirth] = nucleo.al_conectar()                   # sin OPC UA todavia: solo NBIRTH
    assert nbirth.tipo == "NBIRTH" and nbirth.seq == 0 and nbirth.qos == 0 and not nbirth.retener
    p = spb.decodificar(nbirth.payload)
    nombres = {m.name for m in p.metrics}
    assert nombres == {m.nombre for m in metricas.nodo}              # todas las del nodo (ADR-006)
    v = metricas_de(nbirth, metricas)
    assert v["bdSeq"] == 0 and v["Node Control/Rebirth"] is False   # tck-id-topics-nbirth-rebirth-metric
    assert v["Status/OPCUA/Estado"] == "ERROR" and v["Status/MODBUS/OK"] is None   # is_null hasta que llegue
    rebirth = next(m for m in p.metrics if m.name == "Node Control/Rebirth")
    assert not rebirth.HasField("alias")                            # data-commands-rebirth-name-aliases
    assert all(m.HasField("alias") for m in p.metrics if m.name not in ("bdSeq", "Node Control/Rebirth"))
    # El Will: NDEATH QoS 1, no retenido, sin seq, solo bdSeq (payloads-ndeath-*)
    pw = spb.decodificar(will.payload)
    assert will.qos == 1 and not will.retener and not pw.HasField("seq")
    assert [m.name for m in pw.metrics] == ["bdSeq"] and pw.metrics[0].long_value == v["bdSeq"]


def test_dbirth_con_todas_las_metricas_y_seq_siguiente(nucleo, metricas):
    salida = nucleo_en_linea(nucleo)
    tipos = [m.tipo for m in salida]
    assert tipos[0] == "NBIRTH" and "DBIRTH" in tipos
    dbirth = next(m for m in salida if m.tipo == "DBIRTH")
    v = metricas_de(dbirth, metricas)
    assert v == VALORES_DISPOSITIVO                         # tck-id-topics-dbirth-metric-reqs
    assert all(m.name and m.HasField("alias") for m in spb.decodificar(dbirth.payload).metrics)
    seqs = [m.seq for m in salida]
    assert seqs == list(range(len(salida)))                # un solo contador, sin huecos


def test_sin_dbirth_mientras_falte_algun_valor(nucleo):
    nucleo.preparar_conexion()
    nucleo.al_conectar()
    nucleo.al_estado_opcua(True)
    salida = alimentar(nucleo, {**VALORES_ESTADO, "Inputs/Pulsador": True})
    assert "DBIRTH" not in [m.tipo for m in salida]
    assert not nucleo.dispositivo_disponible()


# ----------------------------------------------------------------------------- DATA
def test_ddata_solo_ante_cambio_y_solo_con_alias(nucleo, metricas):
    nucleo_en_linea(nucleo)
    assert nucleo.al_dato("Inputs/Pulsador", False, None, True) == []        # igual al anterior
    [ddata] = nucleo.al_dato("Inputs/Pulsador", True, 1_763_000_000_500, True)
    p = spb.decodificar(ddata.payload)
    assert ddata.tipo == "DDATA" and len(p.metrics) == 1
    m = p.metrics[0]
    assert m.name == "" and m.alias == 101 and m.boolean_value is True        # payloads-alias-data-cmd-requirement
    assert m.timestamp == 1_763_000_000_500                                 # SourceTimestamp de la lectura MODBus


def test_valor_no_good_no_se_publica(nucleo):
    nucleo_en_linea(nucleo)
    assert nucleo.al_dato("Inputs/Potenciometro", 9, None, bueno=False) == []
    assert nucleo.valor("Inputs/Potenciometro") == 2048


def test_contadores_agrupados_en_un_ndata_por_periodo(nucleo, metricas, reloj):
    nucleo_en_linea(nucleo)
    reloj.avanzar(5000)
    assert nucleo.tick() == []
    for i in range(16):                                   # 16 respuestas MODBus en 1 s
        assert nucleo.al_dato("Status/MODBUS/OK", 11 + i, None, True) == []
    assert nucleo.al_dato("Status/MODBUS/TIMEOUT", 1, None, True) == []
    [ndata] = nucleo.tick()
    assert metricas_de(ndata, metricas) == {"Status/MODBUS/OK": 26, "Status/MODBUS/TIMEOUT": 1}
    assert nucleo.tick() == []
    nucleo.al_dato("Status/MODBUS/OK", 27, None, True)
    assert nucleo.tick() == []                           # todavia no paso el periodo
    reloj.avanzar(1000)
    assert len(nucleo.tick()) == 1


def test_seq_compartido_por_ndata_y_ddata_envuelve_255_a_0(nucleo):
    salida = nucleo_en_linea(nucleo)
    for i in range(600):
        if i % 3 == 0:
            salida += nucleo.al_dato("Status/MODBUS/Estado", "CRC ERROR" if i % 2 else "DONE", None, True)  # NDATA
        else:
            salida += nucleo.al_dato("Inputs/Potenciometro", i, None, True)                                # DDATA
    tipos = {m.tipo for m in salida}
    assert {"NDATA", "DDATA"} <= tipos
    seqs = [m.seq for m in salida]
    assert seqs[0] == 0
    for anterior, actual in zip(seqs, seqs[1:]):
        assert actual == (anterior + 1) % 256             # tck-id-payloads-sequence-num-incrementing
    assert seqs.count(0) >= 3 and max(seqs) == 255


# ----------------------------------------------------------------------------- DDEATH / DBIRTH
def test_device_not_reached_publica_ndata_y_ddeath_y_dbirth_al_volver(nucleo, metricas):
    nucleo_en_linea(nucleo)
    salida = nucleo.al_dato("Status/MODBUS/Estado", "DEVICE NOT REACHED", None, True)
    assert [m.tipo for m in salida] == ["NDATA", "DDEATH"]     # primero la causa, despues la muerte
    assert metricas_de(salida[0], metricas) == {"Status/MODBUS/Estado": "DEVICE NOT REACHED"}
    assert spb.decodificar(salida[1].payload).HasField("seq") and salida[1].qos == 0
    assert nucleo.al_dato("Inputs/Pulsador", True, None, True) == []        # sin DBIRTH no hay DDATA
    salida = nucleo.al_dato("Status/MODBUS/Estado", "DONE", None, True)
    assert [m.tipo for m in salida] == ["NDATA", "DBIRTH"]
    assert metricas_de(salida[1], metricas)["Inputs/Pulsador"] is True      # valor actual en el DBIRTH


def test_caida_de_opcua_ddeath_y_dbirth_solo_con_valores_nuevos(nucleo, metricas):
    nucleo_en_linea(nucleo)
    salida = nucleo.al_estado_opcua(False)
    assert [m.tipo for m in salida] == ["NDATA", "DDEATH"]
    assert metricas_de(salida[0], metricas) == {"Status/OPCUA/Estado": "ERROR"}
    salida = nucleo.al_estado_opcua(True)
    assert [m.tipo for m in salida] == ["NDATA"]           # sin valores de la sesion nueva no hay DBIRTH
    salida = alimentar(nucleo, VALORES_DISPOSITIVO)
    assert [m.tipo for m in salida] == ["DBIRTH"]


# ----------------------------------------------------------------------------- reconexion
def test_reconexion_bdseq_mas_uno_nbirth_seq0_y_reconexiones(nucleo, metricas):
    primera = nucleo_en_linea(nucleo)
    bd0 = metricas_de(primera[0], metricas)["bdSeq"]
    nucleo.al_dato("Inputs/Pulsador", True, None, True)
    nucleo.al_desconectar()
    assert nucleo.al_dato("Inputs/Pulsador", False, None, True) == []       # sin conexion no se publica
    will = nucleo.preparar_conexion()
    salida = nucleo.al_conectar()
    assert [m.tipo for m in salida] == ["NBIRTH", "DBIRTH"] and [m.seq for m in salida] == [0, 1]
    v = metricas_de(salida[0], metricas)
    assert v["bdSeq"] == bd0 + 1 == spb.decodificar(will.payload).metrics[0].long_value
    assert v["Status/MQTT/Reconexiones"] == 1
    assert metricas_de(salida[1], metricas)["Inputs/Pulsador"] is False     # el valor actual, no el viejo


def test_bdseq_envuelve_y_se_persiste(tmp_path, metricas, topicos):
    almacen = AlmacenBdSeq(tmp_path / "estado" / "bdseq.json")
    assert almacen.ultimo() is None and almacen.siguiente() == 0             # empieza en 0
    for esperado in range(1, 256):
        assert almacen.siguiente() == esperado
    assert almacen.siguiente() == 0                                          # 255 -> 0
    # Un proceso nuevo con el mismo archivo sigue la cuenta (no repite el bdSeq del Will viejo).
    n = NucleoEdgeNode(metricas, topicos, AlmacenBdSeq(tmp_path / "estado" / "bdseq.json"))
    assert n.preparar_conexion().bd_seq == 1
    (tmp_path / "estado" / "bdseq.json").write_text("basura", encoding="utf-8")
    assert AlmacenBdSeq(tmp_path / "estado" / "bdseq.json").siguiente() == 0


# ----------------------------------------------------------------------------- comandos
def test_rebirth_republica_nbirth_mismo_bdseq_y_cuenta(nucleo, metricas, topicos):
    primera = nucleo_en_linea(nucleo)
    bd = metricas_de(primera[0], metricas)["bdSeq"]
    p = spb.pb.Payload()
    m = p.metrics.add()
    m.name = "Node Control/Rebirth"
    spb.poner_valor(m, "Boolean", True)
    r = nucleo.al_mensaje(topicos.de("NCMD"), p.SerializeToString())
    assert [x.tipo for x in r.mensajes] == ["NBIRTH", "DBIRTH"] and r.mensajes[0].seq == 0
    v = metricas_de(r.mensajes[0], metricas)
    assert v["bdSeq"] == bd and v["Status/Sparkplug/Rebirths"] == 1 and v["Node Control/Rebirth"] is False


def test_dcmd_valido_por_alias_y_por_nombre(nucleo, topicos):
    nucleo_en_linea(nucleo)
    r = nucleo.al_mensaje(*dcmd(topicos, [(None, 103, "Boolean", True), ("Outputs/LedPWM", None, "UInt16", 128)]))
    assert r.rechazos == []
    assert [(e.nombre, e.node_id, e.tipo, e.valor) for e in r.escrituras] == [
        ("Outputs/LedDigital", "ns=1;s=Dispositivo1.Outputs.LedDigital", "Boolean", True),
        ("Outputs/LedPWM", "ns=1;s=Dispositivo1.Outputs.LedPWM", "UInt16", 128)]
    assert r.mensajes == []          # el DCMD no publica nada: el DDATA llega cuando el esclavo confirma


@pytest.mark.parametrize("metrica,motivo", [
    ((None, 101, "Boolean", True), "solo lectura"),
    ((None, 104, "Boolean", True), "tipo Boolean"),
    ((None, 999, "UInt16", 1), "desconocida"),
    (("Outputs/LedDigital", 104, "UInt16", 1), "no corresponde al alias"),
    (("Status/MODBUS/OK", None, "UInt32", 0), "desconocida"),
])
def test_dcmd_invalido_no_escribe(nucleo, topicos, metrica, motivo):
    nucleo_en_linea(nucleo)
    r = nucleo.al_mensaje(*dcmd(topicos, [metrica]))
    assert r.escrituras == [] and motivo in r.rechazos[0]


def test_dcmd_retenido_sin_dispositivo_o_basura(nucleo, topicos):
    nucleo_en_linea(nucleo)
    topico, datos = dcmd(topicos, [(None, 103, "Boolean", True)])
    assert nucleo.al_mensaje(topico, datos, retenido=True).escrituras == []
    assert nucleo.al_mensaje(topico, b"\xff" * 10).escrituras == []
    assert nucleo.al_mensaje(topico, b"\x00" * 20_000).rechazos[0].startswith("DCMD de 20000 bytes")
    assert nucleo.al_mensaje(topico.replace("EN01_Gateway", "OTRO"), datos).escrituras == []
    nucleo.al_dato("Status/MODBUS/Estado", "DEVICE NOT REACHED", None, True)
    assert "sin DBIRTH" in nucleo.al_mensaje(topico, datos).rechazos[0]


# ----------------------------------------------------------------------------- Host Application
def test_esperar_host_retiene_el_birth_hasta_state_online(metricas, topicos, reloj):
    n = NucleoEdgeNode(metricas, topicos, AlmacenBdSeqMemoria(), esperar_host=True, reloj=reloj)
    n.preparar_conexion()
    assert n.al_conectar() == []
    r = n.al_mensaje(topicos.state(), spb.payload_state(True, 100))
    assert [m.tipo for m in r.mensajes] == ["NBIRTH"]
    assert n.al_mensaje(topicos.state(), spb.payload_state(False, 50)).rechazos      # STATE viejo: se ignora
    assert n.al_mensaje(topicos.state(), spb.payload_state(False, 200)).accion == "reconectar"


def test_state_de_otro_host_no_afecta(nucleo, topicos):
    nucleo_en_linea(nucleo)
    r = nucleo.al_mensaje("spBv1.0/STATE/OTRO", spb.payload_state(False, 1))
    assert r.accion is None and nucleo.host_online is None


def test_cambios_simultaneos_viajan_en_un_solo_ddata(nucleo, metricas):
    nucleo_en_linea(nucleo)
    assert nucleo.al_dato("Inputs/Potenciometro", 4095, 10, True, diferir=True) == []
    assert nucleo.al_dato("Inputs/Potenciometro_pct", 100.0, 10, True, diferir=True) == []
    [ddata] = nucleo.vaciar_ddata()
    assert metricas_de(ddata, metricas) == {"Inputs/Potenciometro": 4095, "Inputs/Potenciometro_pct": 100.0}
    assert nucleo.vaciar_ddata() == []


def test_ddata_diferido_sale_antes_del_ddeath(nucleo):
    nucleo_en_linea(nucleo)
    nucleo.al_dato("Inputs/Pulsador", True, None, True, diferir=True)
    salida = nucleo.al_dato("Status/MODBUS/Estado", "DEVICE NOT REACHED", None, True)
    assert [m.tipo for m in salida] == ["DDATA", "NDATA", "DDEATH"]
