#!/usr/bin/env python3
"""
prueba_data_model.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Modelo de datos del esclavo (lib/modbus_slave/data_model.py): limites, desbordes y
direcciones fuera de rango, sin placa.

Cubre: validacion del mapa al arrancar (un mapa mal escrito no debe arrancar), lecturas
de rangos, escrituras desde el bus con sus excepciones 02 y 03, y la interfaz del
hardware (saturacion de entradas, senales inexistentes).

Uso:  python tarea-3/firmware/esclavo-modbus/test/prueba_data_model.py   (exit 1 si falla)
"""

import sys

from _comun import Verificador
from modbus_slave import data_model as dm
from modbus_slave.data_model import ErrorModbus, ModeloDatos

MAPA = [
    {"tabla": "discrete_inputs", "direccion": 0, "nombre": "Inputs/Pulsador", "senal": "pulsador"},
    {"tabla": "input_registers", "direccion": 0, "nombre": "Inputs/Potenciometro",
     "senal": "potenciometro", "maximo": 4095},
    {"tabla": "coils", "direccion": 0, "nombre": "Outputs/LedDigital", "senal": "led_digital"},
    {"tabla": "holding_registers", "direccion": 0, "nombre": "Outputs/LedPWM",
     "senal": "led_pwm", "maximo": 255},
    {"tabla": "holding_registers", "direccion": 1, "nombre": "Libre"},       # 0..65535
    {"tabla": "holding_registers", "direccion": 0xFFFF, "nombre": "Ultimo", "minimo": 10,
     "maximo": 20, "inicial": 15},
]


def codigo(v, funcion, texto):
    """Verifica que funcion() lance ErrorModbus y retorna su codigo (o None)."""
    error = v.lanza(ErrorModbus, funcion, texto)
    return None if error is None else error.codigo


def main():
    """Ejecuta las verificaciones. Retorna el codigo de salida."""
    v = Verificador("Modelo de datos: limites, desbordes y direcciones fuera de rango")

    # ------------------------------------------------------------ mapa invalido
    print("-- Validacion del mapa al arrancar")
    malos = [
        ([{"tabla": "registros", "direccion": 0}], "tabla desconocida"),
        ([{"tabla": "coils", "direccion": -1}], "direccion negativa"),
        ([{"tabla": "coils", "direccion": 0x10000}], "direccion 0x10000"),
        ([{"tabla": "coils", "direccion": "0"}], "direccion no entera"),
        ([{"tabla": "coils", "direccion": 3}, {"tabla": "coils", "direccion": 3}], "direccion repetida"),
        ([{"tabla": "coils", "direccion": 0, "maximo": 2}], "coil con maximo 2"),
        ([{"tabla": "holding_registers", "direccion": 0, "maximo": 0x10000}], "registro > 0xFFFF"),
        ([{"tabla": "holding_registers", "direccion": 0, "minimo": 5, "maximo": 4}], "minimo > maximo"),
        ([{"tabla": "holding_registers", "direccion": 0, "maximo": 255, "inicial": 300}],
         "inicial fuera de rango"),
        ([{"tabla": "coils", "direccion": 0, "senal": "x"},
          {"tabla": "coils", "direccion": 1, "senal": "x"}], "senal repetida"),
    ]
    for mapa, texto in malos:
        v.lanza(ValueError, lambda mapa=mapa: ModeloDatos(mapa), "mapa con " + texto + ": ValueError")
    m = ModeloDatos(MAPA)
    v.check(True, "mapa valido: se construye")
    v.check([x.direccion for x in m.variables("holding_registers")] == [0, 1, 0xFFFF],
            "variables() devuelve las direcciones ordenadas")
    otra_tabla = ModeloDatos([{"tabla": "coils", "direccion": 0}, {"tabla": "holding_registers",
                                                                     "direccion": 0}])
    v.check(len(otra_tabla.variables("coils")) == 1,
            "misma direccion en tablas distintas: no es colision (espacios separados)")

    # ------------------------------------------------------------ lecturas
    print("-- Lecturas desde el bus")
    v.check(m.leer_registros("holding_registers", 0, 2) == [0, 0], "lectura de 2 registros contiguos")
    v.check(m.leer_registros("holding_registers", 0xFFFF, 1) == [15],
            "lectura de la ultima direccion (0xFFFF) con su valor inicial")
    v.check(codigo(v, lambda: m.leer_registros("holding_registers", 0xFFFF, 2), "rango que pasa 0xFFFF") == 2,
            "  -> excepcion 02")
    v.check(codigo(v, lambda: m.leer_registros("holding_registers", 0, 3), "rango con hueco (0..2)") == 2,
            "  -> excepcion 02")
    v.check(codigo(v, lambda: m.leer_registros("input_registers", 1, 1), "IR inexistente") == 2,
            "  -> excepcion 02")
    v.check(codigo(v, lambda: m.leer_bits("discrete_inputs", 5, 1), "DI inexistente") == 2,
            "  -> excepcion 02")

    # ------------------------------------------------------------ escrituras
    print("-- Escrituras desde el bus")
    m.escribir_holding(0, 0)
    m.escribir_holding(0, 255)
    v.check(m.valor_de_senal("led_pwm") == 255, "PWM acepta los extremos 0 y 255")
    v.check(codigo(v, lambda: m.escribir_holding(0, 256), "PWM 256") == 3, "  -> excepcion 03 (no satura)")
    v.check(m.valor_de_senal("led_pwm") == 255, "el valor rechazado no se aplico")
    m.escribir_holding(1, 0xFFFF)
    v.check(m.leer_registros("holding_registers", 1, 1) == [0xFFFF], "registro libre acepta 0xFFFF")
    v.check(codigo(v, lambda: m.escribir_holding(0xFFFF, 9), "por debajo del minimo (9 < 10)") == 3,
            "  -> excepcion 03")
    v.check(codigo(v, lambda: m.escribir_holding(0xFFFF, 21), "por encima del maximo (21 > 20)") == 3,
            "  -> excepcion 03")
    v.check(codigo(v, lambda: m.escribir_holding(7, 1), "holding inexistente") == 2, "  -> excepcion 02")
    v.check(codigo(v, lambda: m.escribir_coil(9, True), "coil inexistente") == 2, "  -> excepcion 02")
    antes = m.escrituras
    m.escribir_coil(0, True)
    v.check(m.leer_bits("coils", 0, 1) == [1] and m.escrituras == antes + 1,
            "escribir un coil lo enciende y cuenta UNA escritura aceptada")
    fijo = ModeloDatos([{"tabla": "coils", "direccion": 0, "minimo": 1, "inicial": 1}])
    v.check(codigo(v, lambda: fijo.escribir_coil(0, False), "coil fijo en 1, escribir 0") == 3,
            "  -> excepcion 03")
    v.check(fijo.escrituras == 0, "las escrituras rechazadas no se cuentan")
    v.check(not hasattr(m, "escribir_input") and not hasattr(m, "escribir_discrete"),
            "el bus no tiene forma de escribir Input Registers ni Discrete Inputs")

    # ------------------------------------------------------------ hardware
    print("-- Interfaz del hardware")
    v.check(m.fijar_entrada("potenciometro", 5000) and m.valor_de_senal("potenciometro") == 4095,
            "ADC por encima del maximo: satura en 4095 (no rechaza)")
    m.fijar_entrada("potenciometro", -3)
    v.check(m.valor_de_senal("potenciometro") == 0, "valor negativo: satura en 0")
    m.fijar_entrada("pulsador", True)
    v.check(m.leer_bits("discrete_inputs", 0, 1) == [1], "pulsador True -> DI = 1")
    v.check(m.fijar_entrada("inexistente", 1) is False, "senal que el perfil no tiene: se ignora (False)")
    v.check(m.valor_de_senal("inexistente") is None, "valor_de_senal de senal inexistente: None")
    v.check(sorted(m.senales()) == ["led_digital", "led_pwm", "potenciometro", "pulsador"],
            "senales() lista las senales del mapa")
    v.check(dm.EXC_FUNCION_ILEGAL == 1 and dm.EXC_DIRECCION_ILEGAL == 2
            and dm.EXC_VALOR_ILEGAL == 3 and dm.EXC_FALLO_DISPOSITIVO == 4,
            "codigos de excepcion 01-04 segun MODBUS Application Protocol §7")
    return v.terminar()


if __name__ == "__main__":
    sys.exit(main())
