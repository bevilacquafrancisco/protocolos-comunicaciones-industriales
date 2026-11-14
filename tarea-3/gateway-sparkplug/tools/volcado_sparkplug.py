#!/usr/bin/env python3
"""
volcado_sparkplug.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Volcado hexadecimal de un payload Sparkplug B con su decodificacion CAMPO POR CAMPO, al nivel del
formato de cable de Protocol Buffers (para el informe, seccion 6.4, y la defensa):

    clave = (numero_de_campo << 3) | tipo_de_cable      (varint)
    tipo 0 = varint · 1 = 64 bits · 2 = longitud + bytes (submensaje, string) · 5 = 32 bits

Los NOMBRES de los campos salen del descriptor de sparkplug_b.proto (sparkplug_b_pb2), no de una
tabla escrita a mano: no pueden quedar desalineados con el .proto oficial.

Uso (en gateway-sparkplug/):
    python tools/volcado_sparkplug.py <hex>
    python tools/volcado_sparkplug.py --jsonl ../docs/capturas/sparkplug-pc-observador.jsonl --tipo DDATA [--indice 0]
    ... --markdown   (tabla para el informe)

Dependencias externas: protobuf 7.36.2 (solo el descriptor).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sparkplug_b_pb2 as pb   # noqa: E402

TIPOS_CABLE = {0: "varint", 1: "64 bits", 2: "longitud", 5: "32 bits"}


def leer_varint(datos: bytes, i: int) -> tuple[int, int]:
    """Varint (7 bits por byte, el bit 7 indica 'sigue'). @returns (valor, nueva posicion)."""
    valor, corrimiento = 0, 0
    while True:
        b = datos[i]
        valor |= (b & 0x7F) << corrimiento
        i += 1
        if not b & 0x80:
            return valor, i
        corrimiento += 7


def volcar(datos: bytes, descriptor=pb.Payload.DESCRIPTOR, prefijo: str = "", base: int = 0) -> list[dict]:
    """
    Recorre un mensaje Protobuf y devuelve una fila por campo (los submensajes, recursivamente).

    Retorna:
        list[dict]: offset, bytes (hex), campo, cable, valor, nota.
    """
    filas, i = [], 0
    while i < len(datos):
        inicio = i
        clave, i = leer_varint(datos, i)
        numero, cable = clave >> 3, clave & 7
        campo = descriptor.fields_by_number.get(numero)
        nombre = f"{prefijo}{campo.name if campo else f'?{numero}'}"
        if cable == 0:
            valor, i = leer_varint(datos, i)
            nota = ""
            if campo and campo.name == "datatype":
                nota = pb.DataType.Name(valor)
            elif campo and campo.name in ("timestamp",):
                nota = "ms desde 1970-01-01 UTC"
            elif campo and campo.type == campo.TYPE_BOOL:
                valor = bool(valor)
            filas.append(dict(offset=base + inicio, hex=datos[inicio:i].hex(" "), campo=nombre,
                              cable=f"{numero}:{TIPOS_CABLE[cable]}", valor=valor, nota=nota))
        elif cable == 2:
            largo, j = leer_varint(datos, i)
            contenido = datos[j:j + largo]
            if campo and campo.message_type is not None:
                filas.append(dict(offset=base + inicio, hex=datos[inicio:j].hex(" "), campo=nombre,
                                  cable=f"{numero}:{TIPOS_CABLE[cable]}", valor=f"submensaje de {largo} bytes",
                                  nota=campo.message_type.name))
                filas += volcar(contenido, campo.message_type, prefijo=f"{nombre}.", base=base + j)
            else:
                texto = contenido.decode("utf-8", errors="replace")
                filas.append(dict(offset=base + inicio, hex=datos[inicio:j + largo].hex(" "), campo=nombre,
                                  cable=f"{numero}:{TIPOS_CABLE[cable]}", valor=repr(texto), nota=f"{largo} bytes UTF-8"))
            i = j + largo
        elif cable == 5:
            crudo = datos[i:i + 4]
            valor = struct.unpack("<f", crudo)[0] if campo and campo.type == campo.TYPE_FLOAT else struct.unpack("<I", crudo)[0]
            filas.append(dict(offset=base + inicio, hex=datos[inicio:i + 4].hex(" "), campo=nombre,
                              cable=f"{numero}:{TIPOS_CABLE[cable]}", valor=round(valor, 6) if isinstance(valor, float) else valor,
                              nota="IEEE 754, little-endian" if isinstance(valor, float) else ""))
            i += 4
        elif cable == 1:
            crudo = datos[i:i + 8]
            valor = struct.unpack("<d", crudo)[0] if campo and campo.type == campo.TYPE_DOUBLE else struct.unpack("<Q", crudo)[0]
            filas.append(dict(offset=base + inicio, hex=datos[inicio:i + 8].hex(" "), campo=nombre,
                              cable=f"{numero}:{TIPOS_CABLE[cable]}", valor=valor, nota=""))
            i += 8
        else:
            raise ValueError(f"tipo de cable {cable} no soportado en el offset {inicio}")
    return filas


def main():
    p = argparse.ArgumentParser(description="Volcado campo por campo de un payload Sparkplug B")
    p.add_argument("hex", nargs="?")
    p.add_argument("--jsonl", type=Path, help="archivo del observador (con el campo 'hex')")
    p.add_argument("--tipo", default="DDATA")
    p.add_argument("--indice", type=int, default=0)
    p.add_argument("--markdown", action="store_true")
    args = p.parse_args()
    if args.jsonl:
        mensajes = [json.loads(l) for l in args.jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
        elegidos = [m for m in mensajes if m.get("tipo") == args.tipo and m.get("hex")]
        if not elegidos:
            raise SystemExit(f"no hay {args.tipo} con bytes crudos en {args.jsonl}")
        m = elegidos[args.indice]
        datos, encabezado = bytes.fromhex(m["hex"]), f"{m['tipo']} {m['topico']} ({len(bytes.fromhex(m['hex']))} bytes)"
    else:
        datos, encabezado = bytes.fromhex(args.hex.replace(" ", "")), f"payload de {len(bytes.fromhex(args.hex.replace(' ', '')))} bytes"
    filas = volcar(datos)
    print(encabezado)
    print("Hex: " + datos.hex(" "))
    if args.markdown:
        print("\n| Offset | Bytes | Campo | Nº:tipo de cable | Valor | Nota |\n|---|---|---|---|---|---|")
        for f in filas:
            print(f"| {f['offset']} | `{f['hex']}` | `{f['campo']}` | {f['cable']} | {f['valor']} | {f['nota']} |")
    else:
        for f in filas:
            print(f"{f['offset']:4d}  {f['hex']:<32s} {f['campo']:<28s} {f['cable']:<12s} {f['valor']!s:<22s} {f['nota']}")


if __name__ == "__main__":
    main()
