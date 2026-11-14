"""
test_metrics.py — el diccionario de datos como unica fuente de las metricas (I-06).
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
"""

from pathlib import Path

import pytest

from metrics import ErrorDiccionario, cargar_metricas

DICCIONARIO = Path(__file__).resolve().parents[2] / "docs" / "diccionario-de-datos.md"


def test_diccionario_real_completo(metricas):
    assert [m.nombre for m in metricas.dispositivo] == [
        "Inputs/Pulsador", "Inputs/Potenciometro", "Outputs/LedDigital", "Outputs/LedPWM", "Inputs/Potenciometro_pct"]
    assert {m.nombre for m in metricas.nodo} == {
        "bdSeq", "Node Control/Rebirth", "Status/MODBUS/Estado", "Status/MODBUS/OK", "Status/MODBUS/CRC_ERROR",
        "Status/MODBUS/TIMEOUT", "Status/MODBUS/EXCEPTION", "Status/OPCUA/Estado", "Status/MQTT/Reconexiones",
        "Status/Sparkplug/Rebirths"}


def test_tipos_y_node_ids_iguales_a_los_del_servidor(metricas):
    # Los mismos NodeIds que expone edge-nodered/lib/servidor_opcua.js (I-06).
    assert metricas.por_nombre("Outputs/LedPWM").node_id == "ns=1;s=Dispositivo1.Outputs.LedPWM"
    assert metricas.por_nombre("Outputs/LedPWM").tipo == "UInt16"
    assert metricas.por_nombre("Inputs/Potenciometro_pct").tipo == "Float"
    assert metricas.por_nombre("Status/MODBUS/OK").node_id == "ns=1;s=Status.MODBUS.OK"
    assert metricas.por_nombre("bdSeq").tipo == "Int64"


def test_solo_las_salidas_son_escribibles(metricas):
    assert {m.nombre for m in metricas.todas() if m.escribible} == {"Outputs/LedDigital", "Outputs/LedPWM"}


def test_origen_interno_no_se_suscribe(metricas):
    # Status/OPCUA/Estado tiene NodeId en el servidor, pero lo calcula el dispositivo 3.
    estado = metricas.por_nombre("Status/OPCUA/Estado")
    assert estado.origen == "interno" and estado.node_id is None
    assert "Status/OPCUA/Estado" not in {m.nombre for m in metricas.suscriptas()}
    assert len(metricas.suscriptas()) == 10


def test_alias_unicos_y_rebirth_sin_alias(metricas):
    alias = [m.alias for m in metricas.todas() if m.alias is not None]
    assert len(alias) == len(set(alias)) == 13
    assert metricas.por_nombre("Node Control/Rebirth").alias is None
    assert metricas.por_alias(104).nombre == "Outputs/LedPWM"


def _diccionario_modificado(tmp_path, viejo, nuevo):
    texto = DICCIONARIO.read_text(encoding="utf-8")
    assert viejo in texto
    ruta = tmp_path / "dicc.md"
    ruta.write_text(texto.replace(viejo, nuevo, 1), encoding="utf-8")
    return ruta


@pytest.mark.parametrize("viejo,nuevo,motivo", [
    ("`Outputs/LedPWM` | `UInt16` | 104", "`Outputs/LedPWM` | `UInt16` | 101", "alias repetidos"),
    ("`Outputs/LedPWM` | `UInt16` | 104", "`Outputs/LedPWM` | `Int128` | 104", "no soportado"),
    ("| `Node Control/Rebirth` | `Boolean` | — | — |", "| `Node Control/Rebirth` | `Boolean` | — | 99 |", "SIN alias"),
    ("`Inputs/Pulsador` | `Boolean` | 101", "`Inputs/Pulsador` | `Boolean` | —", "sin alias"),
    ("| `bdSeq` | `Int64` |", "| `bdSeq` | `UInt64` |", "bdSeq"),
])
def test_diccionario_invalido_se_rechaza(tmp_path, viejo, nuevo, motivo):
    with pytest.raises(ErrorDiccionario, match=motivo):
        cargar_metricas(_diccionario_modificado(tmp_path, viejo, nuevo))
