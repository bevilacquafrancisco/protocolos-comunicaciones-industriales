#!/usr/bin/env python3
"""
prueba_crc.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Plan de pruebas N1.1: el CRC-16/MODBUS propio (lib/modbus_slave/crc16.py) contra los
vectores golden de tests/fixtures/crc_vectors.json, generados con pymodbus y con la
rutina de la T1 como oraculos independientes (tools/generar_vectores_crc.py).

Verifica, para cada vector: version por tabla y bit a bit, orden de bytes en la trama
(byte bajo primero), verificacion de la trama completa, la propiedad de residuo
(CRC de mensaje + CRC = 0) y que cualquier bit alterado invalide la trama.

Uso:  python tarea-3/firmware/esclavo-modbus/test/prueba_crc.py   (exit 1 si falla)
"""

import sys

from _comun import Verificador, cargar_vectores, desde_hex, hexa
from modbus_slave import crc16


def main():
    """Ejecuta las verificaciones. Retorna el codigo de salida."""
    v = Verificador("N1.1 · CRC-16/MODBUS propio contra vectores golden")
    vectores = cargar_vectores()
    v.check(len(vectores) >= 20, "hay al menos 20 vectores golden ({})".format(len(vectores)))

    for nombre, vector in vectores.items():
        mensaje = desde_hex(vector["mensaje_hex"])
        esperado = vector["crc"]
        tabla = crc16.crc16(mensaje)
        bit = crc16.crc16_bit_a_bit(mensaje)
        trama = crc16.agregar_crc(mensaje)
        ok = (tabla == esperado and bit == esperado
              and hexa(trama) == vector["trama_hex"]
              and crc16.verificar_crc(trama)
              and crc16.crc16(trama) == 0)          # residuo: el CRC de todo es 0
        v.check(ok, "{:<20} 0x{:04X}  {}".format(nombre, esperado, vector["crc_en_cable_hex"]),
                "tabla 0x{:04X}, bit 0x{:04X}, trama {}".format(tabla, bit, hexa(trama)))

    # El error clasico: transmitir el CRC big-endian. El vector estandar lo fija.
    est = vectores["vector_estandar"]
    v.check(est["crc"] == 0x4B37 and est["crc_en_cable_hex"] == "37 4B",
            "vector estandar '123456789' = 0x4B37, en el cable 37 4B (byte bajo primero)")

    # Un bit alterado en CUALQUIER posicion invalida la trama (CRC detecta todo error de 1 bit).
    for nombre in ("fc04_peticion", "fc06_peticion", "fc03_respuesta", "longitud_maxima"):
        trama = desde_hex(vectores[nombre]["trama_hex"])
        detectados = 0
        for i in range(len(trama) * 8):
            alterada = bytearray(trama)
            alterada[i // 8] ^= 1 << (i % 8)
            detectados += not crc16.verificar_crc(alterada)
        v.check(detectados == len(trama) * 8,
                "{}: los {} errores de 1 bit se detectan".format(nombre, len(trama) * 8))

    # Dos bits alterados (detectados siempre por CRC-16), muestreo exhaustivo en una trama corta.
    trama = desde_hex(vectores["fc04_peticion"]["trama_hex"])
    bits = len(trama) * 8
    no_detectados = 0
    for a in range(bits):
        for b in range(a + 1, bits):
            alterada = bytearray(trama)
            alterada[a // 8] ^= 1 << (a % 8)
            alterada[b // 8] ^= 1 << (b % 8)
            no_detectados += crc16.verificar_crc(alterada)
    v.check(no_detectados == 0, "fc04_peticion: los {} errores de 2 bits se detectan".format(
        bits * (bits - 1) // 2))

    # Casos borde de verificar_crc
    v.check(not crc16.verificar_crc(b""), "trama vacia: rechazada")
    v.check(not crc16.verificar_crc(desde_hex("01 04 31")), "trama de 3 bytes: rechazada")
    v.check(crc16.verificar_crc(desde_hex(vectores["longitud_minima"]["trama_hex"])),
            "trama de 4 bytes (minimo) con CRC correcto: aceptada")
    # inicio/fin: calcular sobre un tramo sin copiar
    buf = desde_hex("FF FF 01 04 00 00 00 01 EE")
    v.check(crc16.crc16(buf, 2, 8) == 0xCA31 and crc16.crc16_bit_a_bit(buf, 2, 8) == 0xCA31,
            "crc16(datos, inicio, fin) calcula solo sobre el tramo indicado")
    v.check(crc16.crc16(memoryview(desde_hex("01 04 00 00 00 01"))) == 0xCA31,
            "acepta memoryview (sin copias en el ESP32)")
    return v.terminar()


if __name__ == "__main__":
    sys.exit(main())
