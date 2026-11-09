"""
config.py  (ESCLAVO MODBus RTU — Tarea 3)
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
UNICA fuente de verdad del esclavo: pines, parametros del enlace serie, Unit ID y mapa
de registros. No contiene logica. Se importa igual desde MicroPython (ESP32) y desde
CPython (test/prueba_config.py), por eso no importa `machine`.

Dos perfiles en el mismo archivo:
  DISPOSITIVO_1  el esclavo de la Tarea Nº1 tal como se defendio: 9600 8N1, Unit ID 1,
                 mapa en el offset 0 de cada tabla (docs/diccionario-de-datos.md §1).
  DESCONOCIDO    el "esclavo desconocido" del ensayo de ADR-007: otro Unit ID, otro baud
                 rate, otra paridad y otro mapa. Quien prepara el ensayo edita SOLO este
                 perfil y no le cuenta los valores a quien opera el maestro.

Cual se usa lo decide PERFIL. Con "JUMPER" lo elige el jumper de GPIO13 al arrancar
(abierto = DISPOSITIVO_1, a GND = DESCONOCIDO): las dos placas cargan exactamente los
mismos archivos, igual que en la T1 los dos esclavos compartian firmware (un solo firmware
elimina el error "actualice una placa y me olvide de la otra").

Justificacion de cada valor: tarea-1/docs/ (pines, niveles, baud) y tarea-3/docs/
(diccionario de datos, ADR-007, ADR-010, ADR-014).

Dependencias externas
---------------------
Ninguna.
"""

# =============================================================================
# 1. SELECCION DEL PERFIL
# =============================================================================

#: "JUMPER" (recomendado), "DISPOSITIVO_1" o "DESCONOCIDO".
PERFIL = "JUMPER"

#: Jumper de seleccion de perfil, con pull-up interno: abierto = 1 = DISPOSITIVO_1,
#: puenteado a GND = 0 = DESCONOCIDO. Es el mismo pin que en la T1 elegia el Unit ID.
PIN_JUMPER_PERFIL = 13


# =============================================================================
# 2. INTERFAZ RS-485 (identica en todas las placas; tarea-1/docs/arquitectura.md §8)
# =============================================================================

#: UART2: el UART0 esta ocupado por la consola REPL de Thonny sobre USB.
UART_ID = 2

#: UART2 TX -> DI del MAX485 (conexion directa: VIH >= 2,0 V contra 3,3 V).
PIN_UART_TX = 17

#: UART2 RX <- RO del MAX485, OBLIGATORIAMENTE por el divisor 2,2 kOhm / 3,3 kOhm y con
#: el pull-up de 680 Ohm de RO a 5 V (tarea-1/evidencia/INCONVENIENTES.md §4).
PIN_UART_RX = 16

#: DE y RE del MAX485 unidos: 1 = transmite, 0 = escucha.
PIN_DE_RE = 4

#: Espera entre subir DE/RE y empezar a transmitir, en microsegundos. Es el valor que
#: usaba umodbus 2.3.7 (serial.py, _send) y con el que la T1 midio 0,0 % de error:
#: cubre el tiempo de conmutacion del GPIO en MicroPython (~90 us medidos por los autores
#: de esa biblioteca) con margen. El MAX485 en si habilita el driver en < 1 us.
ESPERA_HABILITACION_DE_US = 200

#: Tamano del buffer de recepcion del UART, en bytes. Una trama RTU tiene como maximo
#: 256 bytes: 512 da margen para dos tramas si el lazo se demora.
UART_RXBUF = 512


# =============================================================================
# 3. PERIFERICOS (tarea-1/docs/arquitectura.md §8.2)
# =============================================================================

#: Pulsador a GND, pull-up interno, activo en bajo (perifericos.EntradaDigital invierte).
PIN_PULSADOR = 18

#: Potenciometro en ADC1_CH6 (pin de solo entrada; ADC1 es compatible con Wi-Fi).
PIN_POTENCIOMETRO = 34

#: LED digital, 330 Ohm a GND.
PIN_LED_DIGITAL = 19

#: LED PWM, 330 Ohm a GND, canal LEDC de machine.PWM.
PIN_LED_PWM = 21

# --- Constantes que usa perifericos.py (copiado sin cambios de la Tarea 1) ---

#: Ventana de antirrebote del pulsador, en ms (rebotes tipicos de 1 a 10 ms).
ANTIRREBOTE_MS = 20
#: Muestras promediadas por lectura del ADC (potencia de 2: promedio por desplazamiento).
MUESTRAS_ADC = 8
#: Fondo de escala del ADC de 12 bits.
ADC_MAXIMO = 4095
#: Portadora del PWM, muy por encima del umbral de parpadeo del ojo (~60-90 Hz).
PWM_FRECUENCIA_HZ = 1000
#: Maximo del LED PWM que fija la consigna (0-255).
PWM_MAXIMO = 255
#: 4095 >> 4 = 255 (no se usa en el esclavo: el escalado lo hace el borde, ADR-003).
DESPLAZAMIENTO_ADC_A_PWM = 4


# =============================================================================
# 4. PERFILES: ENLACE SERIE Y MAPA DE REGISTROS
# =============================================================================
# Cada entrada del mapa:
#   tabla      "coils" | "discrete_inputs" | "holding_registers" | "input_registers"
#   direccion  OFFSET que viaja en la trama (0x0000-0xFFFF), no la notacion Modicon
#   nombre     nombre del diccionario de datos (I-06: el mismo en MODBus, OPC UA y Sparkplug B)
#   senal      senal fisica de main.py, o None si es una variable solo de memoria:
#                "pulsador", "potenciometro", "led_digital", "led_pwm", "uptime_s"
#   minimo, maximo  rango admitido; una escritura fuera de rango -> excepcion 03
#   inicial    valor al arrancar (estado seguro: salidas apagadas)
#
# paridad: "N" (ninguna), "E" (par) u "O" (impar).

PERFILES = {
    # -------------------------------------------------------------------------
    # Dispositivo 1 — el esclavo de la Tarea Nº1 (docs/diccionario-de-datos.md §1)
    # -------------------------------------------------------------------------
    "DISPOSITIVO_1": {
        "unit_id": 1,
        # 9600 y no 19200: t1,5 = 1,72 ms absorbe las pausas del recolector de basura de
        # MicroPython (tarea-1/docs/protocolo-comunicacion.md §3.1).
        "baud": 9600,
        "paridad": "N",
        "bits_parada": 1,
        "mapa": [
            {"tabla": "discrete_inputs", "direccion": 0x0000, "nombre": "Inputs/Pulsador",
             "senal": "pulsador"},                                         # Modicon 10001
            {"tabla": "input_registers", "direccion": 0x0000, "nombre": "Inputs/Potenciometro",
             "senal": "potenciometro", "maximo": 4095},                    # Modicon 30001
            {"tabla": "coils", "direccion": 0x0000, "nombre": "Outputs/LedDigital",
             "senal": "led_digital", "inicial": 0},                        # Modicon 00001
            {"tabla": "holding_registers", "direccion": 0x0000, "nombre": "Outputs/LedPWM",
             "senal": "led_pwm", "maximo": 255, "inicial": 0},             # Modicon 40001
        ],
    },

    # -------------------------------------------------------------------------
    # Esclavo desconocido — ensayo de ADR-007. EDITAR SOLO ESTE BLOQUE para el ensayo.
    # Reglas: Unit ID 1-247; baud <= 19200 (ADR-010, salvaguarda a: por encima, t1,5 cae
    # por debajo de 0,86 ms frente a las pausas del interprete).
    # -------------------------------------------------------------------------
    "DESCONOCIDO": {
        "unit_id": 17,
        "baud": 19200,
        "paridad": "E",
        "bits_parada": 1,
        "mapa": [
            {"tabla": "discrete_inputs", "direccion": 0x0010, "nombre": "Inputs/Pulsador",
             "senal": "pulsador"},
            {"tabla": "discrete_inputs", "direccion": 0x0011, "nombre": "Inputs/Listo",
             "inicial": 1, "minimo": 1},                                    # siempre 1
            {"tabla": "input_registers", "direccion": 0x0100, "nombre": "Inputs/Potenciometro",
             "senal": "potenciometro", "maximo": 4095},
            {"tabla": "input_registers", "direccion": 0x0101, "nombre": "Inputs/Uptime_s",
             "senal": "uptime_s"},                     # segundos desde el arranque, mod 65536
            {"tabla": "coils", "direccion": 0x0020, "nombre": "Outputs/LedDigital",
             "senal": "led_digital", "inicial": 0},
            {"tabla": "coils", "direccion": 0x0021, "nombre": "Outputs/Bandera"},
            {"tabla": "holding_registers", "direccion": 0x0200, "nombre": "Outputs/LedPWM",
             "senal": "led_pwm", "maximo": 255, "inicial": 0},
            {"tabla": "holding_registers", "direccion": 0x0201, "nombre": "Outputs/Consigna",
             "maximo": 1000, "inicial": 500},
        ],
    },
}


# =============================================================================
# 5. DELIMITACION DE TRAMAS
# =============================================================================

#: Aplicar la regla de t1,5 (hueco maximo dentro de una trama). La especificacion manda
#: descartar la trama. Riesgo propio de MicroPython: si el lazo se demora con bytes en
#: vuelo, el hueco MEDIDO es mayor que el real y se descarta una trama sana. Si el
#: contador tramas_invalidas crece con el bus limpio, poner False y documentarlo.
VERIFICAR_T15 = True


# =============================================================================
# 6. DIAGNOSTICO
# =============================================================================
# Efecto sonda (leccion de la T1): cada print() por USB cuesta 1-3 ms y, en medio de una
# trama, puede hacer perder bytes o el t3,5. Por eso solo se imprime en el arranque y en
# el latido, nunca por cada trama salvo con NIVEL_LOG = 2 en capturas cortas.

#: 0 silencio · 1 arranque y latido · 2 ademas, una linea por trama (solo para depurar).
NIVEL_LOG = 1

#: Periodo del latido con los contadores, en ms.
PERIODO_LATIDO_MS = 5000
