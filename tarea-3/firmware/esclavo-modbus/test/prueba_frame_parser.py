#!/usr/bin/env python3
"""
prueba_frame_parser.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Plan de pruebas N1.2: parser y procesamiento de tramas del esclavo, sin placa.

Casos de N1.2: trama correcta · CRC corrupto en un bit · ID de esclavo ajeno (silencio) ·
FC no soportado (excepcion 01) · direccion fuera de rango (02) · cantidad fuera de rango
(03) · trama truncada · dos tramas pegadas sin silencio t3,5.
Ademas: las seis funciones, excepcion 04, difusion, tiempos t1,5/t3,5 calculados,
delimitacion por silencio (EnsambladorTramas) y robustez ante tramas aleatorias.

Las respuestas esperadas se comparan con los vectores golden (oraculos independientes)
cuando existen, no con bytes calculados por el mismo codigo bajo prueba.

Uso:  python tarea-3/firmware/esclavo-modbus/test/prueba_frame_parser.py   (exit 1 si falla)
"""

import random
import sys

from _comun import Verificador, cargar_vectores, desde_hex, hexa
import config
from modbus_slave import crc16, frame_parser as fp
from modbus_slave.data_model import ModeloDatos

VEC = cargar_vectores()


def modelo_d1():
    """Modelo del perfil DISPOSITIVO_1 con entradas conocidas (pulsador 1, pote 2047)."""
    m = ModeloDatos(config.PERFILES["DISPOSITIVO_1"]["mapa"])
    m.fijar_entrada("pulsador", True)
    m.fijar_entrada("potenciometro", 2047)
    return m


def peticion(texto):
    """'01 04 00 00 00 01' -> trama con CRC propio (los CRC se contrastan aparte)."""
    return bytes(crc16.agregar_crc(desde_hex(texto)))


def procesar(trama, modelo=None, unit_id=1, defectuosa=False):
    """Atajo: procesa con el modelo del dispositivo 1. Retorna (hex o None, motivo)."""
    respuesta, motivo = fp.procesar_trama(trama, unit_id, modelo or modelo_d1(), defectuosa)
    return (None if respuesta is None else hexa(respuesta)), motivo


def main():
    """Ejecuta las verificaciones. Retorna el codigo de salida."""
    v = Verificador("N1.2 · Parser y procesamiento de tramas del esclavo")

    # ------------------------------------------------------------------ tiempos
    print("-- [DF-1.2] Tiempos calculados del baud rate")
    v.check(fp.tiempos_us(9600) == (1146, 1719, 4011), "9600 bps: t_car 1146, t1,5 1719, t3,5 4011 us",
            str(fp.tiempos_us(9600)))
    v.check(fp.tiempos_us(19200) == (573, 860, 2006), "19200 bps: t_car 573, t1,5 860, t3,5 2006 us",
            str(fp.tiempos_us(19200)))
    v.check(fp.tiempos_us(38400)[1:] == (750, 1750), "38400 bps: t1,5/t3,5 fijos 750/1750 us")
    v.check(fp.tiempos_us(115200) == (96, 750, 1750), "115200 bps: fijos por norma (t_car 96 us)")
    v.check(fp.tiempos_us(1200)[2] == 32084, "1200 bps: t3,5 = 32084 us (escala con el baud rate)",
            str(fp.tiempos_us(1200)))
    v.lanza(ValueError, lambda: fp.tiempos_us(0), "baud 0: ValueError")

    # ------------------------------------------------------------------ N1.2 casos
    print("-- N1.2 casos del plan de pruebas")
    resp, motivo = procesar(desde_hex(VEC["fc04_peticion"]["trama_hex"]))
    v.check(resp == VEC["fc04_respuesta"]["trama_hex"] and motivo == "respondida",
            "trama correcta FC 04: respuesta = vector golden {}".format(VEC["fc04_respuesta"]["trama_hex"]),
            "{} {}".format(resp, motivo))

    trama = desde_hex(VEC["fc04_peticion"]["trama_hex"])
    silencios = 0
    for i in range(len(trama) * 8):
        alterada = bytearray(trama)
        alterada[i // 8] ^= 1 << (i % 8)
        resp, motivo = procesar(bytes(alterada))
        silencios += resp is None and motivo in ("crc_error", "ajena")
    v.check(silencios == 64, "CRC corrupto en un bit (64 posiciones): nunca se responde")

    resp, motivo = procesar(peticion("02 04 00 00 00 01"))
    v.check(resp is None and motivo == "ajena", "ID de esclavo ajeno: silencio (motivo ajena)")

    for fc in (0x07, 0x0F, 0x10, 0x2B):
        resp, motivo = procesar(peticion("01 {:02X} 00 00 00 01".format(fc)))
        esperado = hexa(crc16.agregar_crc(bytes([1, fc | 0x80, 1])))
        v.check(resp == esperado and motivo == "excepcion",
                "FC 0x{:02X} no soportado: excepcion 01 ({})".format(fc, esperado), str(resp))
    resp, _ = procesar(peticion("01 07 00 00 00 01"))
    v.check(resp == VEC["excepcion_01"]["trama_hex"], "excepcion 01 = vector golden 01 87 01 82 30")

    resp, motivo = procesar(peticion("01 04 00 01 00 01"))
    v.check(resp == VEC["excepcion_02"]["trama_hex"] and motivo == "excepcion",
            "direccion inexistente (IR 0x0001): excepcion 02 = vector golden", str(resp))
    resp, _ = procesar(peticion("01 04 00 00 00 02"))
    v.check(resp == VEC["excepcion_02"]["trama_hex"], "rango que excede el mapa (2 IR desde 0x0000): 02")
    resp, _ = procesar(peticion("01 04 FF FF 00 02"))
    v.check(resp == VEC["excepcion_02"]["trama_hex"], "rango que pasa de 0xFFFF: 02")

    for texto, desc in (("01 03 00 00 00 00", "FC 03 cantidad 0"),
                        ("01 03 00 00 00 7E", "FC 03 cantidad 126 (> 125)"),
                        ("01 01 00 00 07 D1", "FC 01 cantidad 2001 (> 2000)"),
                        ("01 02 00 00 00 00", "FC 02 cantidad 0")):
        resp, motivo = procesar(peticion(texto))
        fc = desde_hex(texto)[1]
        esperado = hexa(crc16.agregar_crc(bytes([1, fc | 0x80, 3])))
        v.check(resp == esperado and motivo == "excepcion", desc + ": excepcion 03", str(resp))
    # El orden importa: cantidad invalida Y direccion inexistente -> 03 (se valida antes)
    resp, _ = procesar(peticion("01 03 00 05 00 00"))
    v.check(resp is not None and desde_hex(resp)[2] == 3,
            "cantidad invalida en direccion inexistente: gana 03 (orden de la especificacion)")

    completa = desde_hex(VEC["fc04_peticion"]["trama_hex"])
    resp, motivo = procesar(completa[:7])
    v.check(resp is None and motivo == "crc_error", "trama truncada (7 de 8 bytes): descartada sin responder")
    resp, motivo = procesar(completa[:3])
    v.check(resp is None and motivo == "invalida", "trama de 3 bytes: descartada (invalida)")

    # Dos tramas pegadas: el ensamblador las ve como una sola de 16 bytes -> CRC invalido.
    _, t15, t35 = fp.tiempos_us(9600)
    ens = fp.EnsambladorTramas(t15, t35)
    ens.alimentar(completa, 0)
    ens.alimentar(completa, 1000)               # 1 ms despues: sin el silencio t3,5
    trama_unida = ens.trama_completa(1000 + t35)
    resp, motivo = procesar(trama_unida[0], defectuosa=trama_unida[1])
    v.check(len(trama_unida[0]) == 16 and resp is None and motivo == "crc_error",
            "dos tramas pegadas sin silencio t3,5: una de 16 bytes, CRC invalido, sin respuesta")

    # ------------------------------------------------------------------ las seis funciones
    print("-- Las seis funciones (perfil DISPOSITIVO_1)")
    m = modelo_d1()
    m.escribir_coil(0, True)
    m.escribir_holding(0, 128)
    for fc, nombre in ((1, "fc01"), (2, "fc02"), (3, "fc03")):
        resp, _ = procesar(desde_hex(VEC[nombre + "_peticion"]["trama_hex"]), m)
        v.check(resp == VEC[nombre + "_respuesta"]["trama_hex"],
                "FC 0{} = vector golden {}".format(fc, VEC[nombre + "_respuesta"]["trama_hex"]), str(resp))

    m = modelo_d1()
    for nombre in ("fc05_peticion_on", "fc05_peticion_off", "fc06_peticion", "fc06_peticion_255"):
        pet = VEC[nombre]["trama_hex"]
        resp, motivo = procesar(desde_hex(pet), m)
        v.check(resp == pet and motivo == "respondida", "{}: respuesta = eco exacto".format(nombre))
    v.check(m.valor_de_senal("led_pwm") == 255 and m.valor_de_senal("led_digital") == 0,
            "las escrituras quedaron aplicadas en el modelo (PWM 255, LED apagado)")

    resp, _ = procesar(peticion("01 06 00 00 01 00"), m)
    v.check(resp == VEC["excepcion_03"]["trama_hex"], "FC 06 valor 256 en LED PWM (0-255): excepcion 03")
    v.check(m.valor_de_senal("led_pwm") == 255, "el valor rechazado no modifico el registro")
    resp, _ = procesar(peticion("01 05 00 00 12 34"), m)
    v.check(resp is not None and desde_hex(resp)[1:3] == bytes([0x85, 3]),
            "FC 05 valor 0x1234 (solo 0xFF00/0x0000): excepcion 03")
    resp, _ = procesar(peticion("01 06 00 07 00 01"), m)
    v.check(resp is not None and desde_hex(resp)[1:3] == bytes([0x86, 2]),
            "FC 06 sobre holding inexistente: excepcion 02")
    resp, _ = procesar(peticion("01 05 00 00 FF 00 00"), m)
    v.check(resp is not None and desde_hex(resp)[1:3] == bytes([0x85, 3]),
            "PDU de longitud incorrecta con CRC valido: excepcion 03")

    # Lecturas multiples con el perfil DESCONOCIDO (direcciones contiguas, empaquetado)
    print("-- Lecturas multiples (perfil DESCONOCIDO, Unit ID 17)")
    md = ModeloDatos(config.PERFILES["DESCONOCIDO"]["mapa"])
    md.fijar_entrada("pulsador", True)
    md.escribir_coil(0x21, True)
    resp, _ = procesar(peticion("11 01 00 20 00 02"), md, unit_id=17)
    v.check(resp == hexa(crc16.agregar_crc(desde_hex("11 01 01 02"))),
            "FC 01 dos coils (LED 0, Bandera 1): byte 0x02, primer bit en el LSB", str(resp))
    resp, _ = procesar(peticion("11 02 00 10 00 02"), md, unit_id=17)
    v.check(resp == hexa(crc16.agregar_crc(desde_hex("11 02 01 03"))),
            "FC 02 dos entradas (Pulsador 1, Listo 1): byte 0x03", str(resp))
    resp, _ = procesar(desde_hex(VEC["desconocido_fc03"]["trama_hex"]), md, unit_id=17)
    v.check(resp == hexa(crc16.agregar_crc(desde_hex("11 03 04 00 00 01 F4"))),
            "FC 03 dos registros (PWM 0, Consigna 500 = 0x01F4) big-endian", str(resp))
    resp, motivo = procesar(desde_hex(VEC["fc04_peticion"]["trama_hex"]), md, unit_id=17)
    v.check(resp is None and motivo == "ajena", "el perfil DESCONOCIDO ignora al Unit ID 1")

    # ------------------------------------------------------------------ excepcion 04
    print("-- Excepcion 04 (fallo del dispositivo)")
    roto = modelo_d1()
    roto.leer_registros = lambda *a: 1 / 0          # simula una falla interna al leer
    resp, motivo = procesar(peticion("01 03 00 00 00 01"), roto)
    v.check(resp == VEC["excepcion_04"]["trama_hex"] and motivo == "excepcion",
            "error interno al ejecutar: excepcion 04 = vector golden 01 83 04 40 F3", str(resp))

    # ------------------------------------------------------------------ difusion
    print("-- Difusion (Unit ID 0)")
    m = modelo_d1()
    resp, motivo = procesar(desde_hex(VEC["difusion_fc06"]["trama_hex"]), m)
    v.check(resp is None and motivo == "difusion" and m.valor_de_senal("led_pwm") == 0x40,
            "FC 06 en difusion: se ejecuta (PWM = 64) y NO se responde")
    resp, motivo = procesar(peticion("00 04 00 00 00 01"), m)
    v.check(resp is None and motivo == "difusion", "lectura en difusion: ignorada, sin respuesta")
    resp, motivo = procesar(peticion("00 06 00 00 01 00"), m)
    v.check(resp is None and m.valor_de_senal("led_pwm") == 0x40,
            "escritura invalida en difusion: no responde ni modifica")

    # ------------------------------------------------------------------ ensamblador
    print("-- [DF-1.4] a [DF-1.7] Delimitacion por silencio (9600 bps)")
    _, t15, t35 = fp.tiempos_us(9600)
    ens = fp.EnsambladorTramas(t15, t35)
    v.check(ens.trama_completa(0) is None and not ens.en_curso(), "sin bytes: no hay trama")
    ens.alimentar(completa[:3], 0)
    ens.alimentar(completa[3:], 1000)
    v.check(ens.en_curso() and ens.trama_completa(1000 + t35 - 1) is None,
            "silencio de t3,5 - 1 us: la trama todavia no termino")
    salida = ens.trama_completa(1000 + t35)
    v.check(salida == (completa, False) and not ens.en_curso(),
            "silencio = t3,5: trama completa, sin defectos, ensamblador vacio")

    ens.alimentar(completa[:4], 0)
    ens.alimentar(completa[4:], t15 + 1)           # hueco entre t1,5 y t3,5
    salida = ens.trama_completa(t15 + 1 + t35)
    v.check(salida is not None and salida[1] is True, "hueco > t1,5 dentro de la trama: marcada defectuosa")
    v.check(procesar(salida[0], defectuosa=salida[1]) == (None, "invalida"),
            "trama con hueco > t1,5: descartada aunque el CRC sea correcto")

    sin_t15 = fp.EnsambladorTramas(t15, t35, verificar_t15=False)
    sin_t15.alimentar(completa[:4], 0)
    sin_t15.alimentar(completa[4:], t15 + 1)
    v.check(sin_t15.trama_completa(t15 + 1 + t35) == (completa, False),
            "con VERIFICAR_T15 = False el mismo hueco se tolera")

    cerrada = ens.alimentar(completa, 0)
    cerrada = ens.alimentar(completa, t35 + 10)       # llega la 2.a sin que se haya consultado
    v.check(cerrada == (completa, False), "si el lazo se demora, alimentar() cierra la trama anterior")
    v.check(ens.trama_completa(2 * t35 + 10) == (completa, False), "y la segunda queda disponible")

    ens.alimentar(bytes(200), 0)
    ens.alimentar(bytes(100), 10)                    # 300 bytes > 256
    salida = ens.trama_completa(10 + t35)
    v.check(salida is not None and salida[1] is True, "mas de 256 bytes: marcada defectuosa")

    desborde = fp.EnsambladorTramas(t15, t35, diferencia=lambda a, b: (a - b) % (1 << 30))
    desborde.alimentar(completa, (1 << 30) - 100)    # ticks_us de MicroPython da la vuelta
    v.check(desborde.trama_completa(t35) is not None,
            "funciona a traves del desborde del contador de ticks (diferencia inyectada)")

    # ------------------------------------------------------------------ robustez
    print("-- Robustez: 20 000 tramas aleatorias")
    azar = random.Random(20261109)
    m = modelo_d1()
    respuestas_validas, fallas = 0, 0
    for _ in range(20000):
        largo = azar.randint(0, 20)
        cruda = bytes(azar.randrange(256) for _ in range(largo))
        if azar.random() < 0.5 and largo >= 2:      # la mitad con CRC correcto
            cruda = bytes(crc16.agregar_crc(cruda[:-2]))
        try:
            respuesta, motivo = fp.procesar_trama(cruda, 1, m)
            if respuesta is not None:
                respuestas_validas += crc16.verificar_crc(respuesta) and respuesta[0] == 1
                fallas += not (crc16.verificar_crc(respuesta) and respuesta[0] == 1)
        except Exception:
            fallas += 1
    v.check(fallas == 0, "ninguna trama aleatoria lanza excepcion ni genera respuesta invalida "
            "({} respuestas, todas con CRC correcto y Unit ID propio)".format(respuestas_validas))

    return v.terminar()


if __name__ == "__main__":
    sys.exit(main())
