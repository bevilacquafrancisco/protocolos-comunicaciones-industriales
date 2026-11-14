"""
test_sparkplug.py — codificacion Sparkplug B (plan de pruebas N1.3).
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
"""

import subprocess
import sys
from pathlib import Path

import pytest

import sparkplug as spb
import sparkplug_b_pb2 as pb

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tipo,valor,campo", [
    ("Boolean", True, "boolean_value"), ("Boolean", False, "boolean_value"),
    ("UInt16", 0, "int_value"), ("UInt16", 65535, "int_value"),
    ("UInt32", 4_294_967_295, "int_value"),          # UInt32 va en int_value (Sparkplug 3.0 §6.4.16)
    ("Int64", -1, "long_value"), ("Int64", 255, "long_value"), ("Int16", -32768, "int_value"),
    ("Float", 59.7, "float_value"), ("String", "DEVICE NOT REACHED", "string_value"),
])
def test_ida_y_vuelta_por_tipo(tipo, valor, campo):
    datos = spb.armar_payload([spb.ValorMetrica("m", 1, tipo, valor)], seq=7, timestamp=123)
    m = spb.decodificar(datos).metrics[0]
    assert m.WhichOneof("value") == campo
    assert pb.DataType.Name(m.datatype) == tipo
    leido = spb.leer_valor(m)
    assert leido == pytest.approx(valor) if tipo == "Float" else leido == valor


@pytest.mark.parametrize("tipo,valor,error", [
    ("UInt16", 65536, ValueError), ("UInt16", -1, ValueError), ("Boolean", 1, TypeError), ("UInt16", True, TypeError),
])
def test_valor_fuera_de_rango_o_de_tipo(tipo, valor, error):
    with pytest.raises(error):
        spb.armar_payload([spb.ValorMetrica("m", 1, tipo, valor)], seq=0)


def test_nulo_usa_is_null_sin_valor():
    m = spb.decodificar(spb.armar_payload([spb.ValorMetrica("m", 1, "UInt32", None)], seq=0)).metrics[0]
    assert m.is_null and m.WhichOneof("value") is None and spb.leer_valor(m) is None


def test_timestamp_en_ms_y_seq():
    p = spb.decodificar(spb.armar_payload([], seq=255, timestamp=1_763_000_000_123))
    assert p.timestamp == 1_763_000_000_123 and p.seq == 255
    assert abs(spb.ahora_ms() - spb.decodificar(spb.armar_payload([], seq=0)).timestamp) < 5000


def test_seq_fuera_de_rango_y_ndeath_sin_seq():
    with pytest.raises(ValueError):
        spb.armar_payload([], seq=256)
    assert not spb.decodificar(spb.armar_payload([], seq=None)).HasField("seq")


def test_secuencia_envuelve_de_255_a_0():
    s = spb.Secuencia()
    with pytest.raises(RuntimeError):
        s.siguiente()                         # sin NBIRTH no hay seq
    assert s.para_nbirth() == 0
    valores = [s.siguiente() for _ in range(300)]
    assert valores[:3] == [1, 2, 3] and valores[254] == 255 and valores[255] == 0 and valores[256] == 1


def test_topicos(topicos):
    assert topicos.de("NBIRTH") == "spBv1.0/UNRaf_PdCI_2026/NBIRTH/EN01_Gateway"
    assert topicos.de("DCMD") == "spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/DEV01_ESP32_Slave"
    assert topicos.state() == "spBv1.0/STATE/HA01_WebDashboard"
    assert spb.analizar_topico(topicos.de("DDATA"))["dispositivo"] == "DEV01_ESP32_Slave"
    assert spb.analizar_topico("spBv1.0/STATE/HA01_WebDashboard")["tipo"] == "STATE"
    assert spb.analizar_topico("spBv1.0/G/NDATA/N/D") is None          # NDATA no lleva dispositivo
    assert spb.analizar_topico("otro/G/NDATA/N") is None
    with pytest.raises(ValueError):
        spb.Topicos("G", "nodo/malo", "D", "H")


def test_state_json():
    assert spb.leer_state(spb.payload_state(True, 5)) == (True, 5)
    assert spb.leer_state(b'{"online": "si", "timestamp": 5}') is None
    assert spb.leer_state(b"\xff") is None


def test_payload_invalido():
    with pytest.raises(ValueError):
        spb.decodificar(b"\xff\xff\xff")


def test_proto_sin_modificar_y_pb2_al_dia(tmp_path):
    """El .proto es el oficial de Eclipse Tahu y el _pb2.py corresponde a el (protoc de grpcio-tools)."""
    import hashlib
    proto = RAIZ / "proto" / "sparkplug_b.proto"
    # SHA-256 del sparkplug_b.proto de eclipse-tahu/tahu (master, verificado byte a byte el 2026-11-12).
    assert hashlib.sha256(proto.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == \
        "4432c5c483b7fb9732d0594c98a2e97dca5e517e39c5374a8b918d837f0b4a19"
    pytest.importorskip("grpc_tools")
    subprocess.run([sys.executable, "-m", "grpc_tools.protoc", f"-I{RAIZ / 'proto'}", f"--python_out={tmp_path}",
                    str(proto)], check=True)
    generado = (tmp_path / "sparkplug_b_pb2.py").read_text(encoding="utf-8")
    assert generado == (RAIZ / "src" / "sparkplug_b_pb2.py").read_text(encoding="utf-8")
