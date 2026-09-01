"""
config.py
Autor: Francisco Bevilacqua
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Parametros de configuracion compartidos por los tres nodos del trabajo practico
(Maestro, Esclavo 1 y Esclavo 2): asignacion de pines, parametros de la linea
serie RS-485, mapa de direcciones MODBus y constantes de temporizacion.

Este modulo NO contiene logica: es la unica fuente de verdad para los valores que
deben coincidir entre los tres firmwares. Centralizarlo evita la clase de error
mas cara del trabajo, que es tener un nodo configurado a 9600 baudios y otro a
19200 y perder horas diagnosticando el bus.

La justificacion numerica de cada valor esta en docs/PINOUT.md (pines y niveles
electricos) y en docs/MAPA_REGISTROS.md (baudrate, paridad, escalas).

Dependencias externas
---------------------
Ninguna. Se importa tanto desde MicroPython como desde CPython (las herramientas
de analisis de tramas en herramientas/ leen de aca los parametros del bus).
"""

# =============================================================================
# 1. PARAMETROS DE LA LINEA SERIE (identicos en TODOS los nodos y en Modbus Poll)
# =============================================================================

#: Velocidad del bus en baudios.
#: 9600 y no 19200/115200: a 9600 el intervalo inter-caracter permitido antes de
#: descartar una trama (t1,5) es de 1,72 ms, suficiente para absorber una pausa
#: del recolector de basura de MicroPython. A 115200 ese margen cae a 143 us y
#: una sola pausa del GC corrompe la recepcion. Ver docs/MAPA_REGISTROS.md §2.1.
BAUDRATE = 9600

#: Bits de datos. En modo RTU son obligatoriamente 8 (el modo ASCII usa 7).
BITS_DATOS = 8

#: Paridad. None = sin paridad. La trama ya viaja protegida por CRC-16, que es
#: estrictamente mas fuerte que la paridad. Ver docs/MAPA_REGISTROS.md §2.2.
PARIDAD = None

#: Bits de parada. 1, que es lo que corresponde cuando no se usa paridad.
BITS_PARADA = 1

#: Identificador del periferico UART del ESP32. Se usa el UART2 porque el UART0
#: esta ocupado por la consola REPL de MicroPython sobre USB: si se usara el
#: UART0 para el bus, cada mensaje de depuracion se inyectaria en el bus RS-485.
UART_ID = 2


# =============================================================================
# 2. ASIGNACION DE PINES
# =============================================================================
# Criterios de seleccion y descarte de GPIO documentados en docs/PINOUT.md §2.
# Resumen: se evitan GPIO 6-11 (flash SPI interna), GPIO 0/2/12/15 (strapping,
# afectan el modo de arranque) y se usa ADC1 (GPIO 32-39) por compatibilidad
# futura con WiFi.

# --- Interfaz RS-485 (identica en los tres nodos) ---------------------------

#: UART2 TX -> pin DI del MAX485. Conexion directa: el MAX485 exige VIH >= 2,0 V
#: y el ESP32 entrega 3,3 V (margen de 1,3 V).
PIN_UART_TX = 17

#: UART2 RX <- pin RO del MAX485, OBLIGATORIAMENTE a traves del divisor
#: resistivo 2,2 kOhm / 3,3 kOhm. RO entrega hasta ~5 V y el maximo absoluto del
#: GPIO del ESP32 es 3,6 V. Ver docs/PINOUT.md §1.2.
PIN_UART_RX = 16

#: Pin de control de direccion del transceptor. Se conecta a DE y a RE unidos
#: entre si: alto = el nodo transmite, bajo = el nodo escucha. RS-485 es
#: half-duplex, por lo que el firmware debe conmutar explicitamente este pin
#: antes y despues de cada transmision (lo hace la libreria umodbus).
PIN_DE_RE = 4

# --- Perifericos comunes a maestro y esclavos -------------------------------

#: Switch / pulsador. Configurado con pull-up interno, por lo que es ACTIVO EN
#: BAJO: pin en 0 significa "presionado". Ver perifericos.EntradaDigital.
PIN_SWITCH = 18

#: Potenciometro. GPIO34 pertenece al ADC1 y es un pin de solo entrada, lo que lo
#: hace inmune a quedar configurado como salida por error.
PIN_POTENCIOMETRO = 34

#: LED gobernado de forma digital (on/off).
PIN_LED_DIGITAL = 19

#: LED gobernado por PWM (intensidad regulable).
PIN_LED_PWM = 21

# --- Selector (significado distinto segun el nodo) --------------------------

#: En un ESCLAVO: jumper que fija la direccion fisica. Abierto = Unit ID 1,
#: puenteado a GND = Unit ID 2. Equivale a las llaves DIP de direccionamiento de
#: un modulo de E/S remoto industrial, y permite que ambos esclavos corran
#: exactamente el mismo firmware.
#: En el MAESTRO: switch selector del esclavo destino. Abierto = Esclavo 1,
#: a GND = Esclavo 2.
PIN_SELECTOR = 13

# --- Perifericos exclusivos del maestro (Parte 3) ---------------------------

#: LED que indica que la comunicacion en curso es con el Esclavo 1.
PIN_LED_INDICADOR_1 = 22

#: LED que indica que la comunicacion en curso es con el Esclavo 2.
PIN_LED_INDICADOR_2 = 23


# =============================================================================
# 3. MAPA DE DIRECCIONES MODBUS
# =============================================================================
# Las cuatro variables comparten el offset 0x0000 y eso NO es una colision: cada
# area de MODBus tiene su propio espacio de direcciones, y el codigo de funcion
# empleado es el que determina en que area se busca el offset.
#
# Correspondencia con la notacion Modicon que pide la consigna:
#   Discrete Input  0x0000  <->  10001
#   Input Register  0x0000  <->  30001
#   Coil            0x0000  <->  00001
#   Holding Reg.    0x0000  <->  40001

#: Offset del Discrete Input que expone el estado del switch (Modicon 10001).
#: Se lee con la funcion 0x02 (Read Discrete Inputs). Solo lectura.
DIR_DISCRETE_INPUT_SWITCH = 0x0000

#: Offset del Input Register que expone el valor crudo del ADC (Modicon 30001).
#: Se lee con la funcion 0x04 (Read Input Registers). Solo lectura.
DIR_INPUT_REGISTER_POTE = 0x0000

#: Offset del Coil que gobierna el LED digital (Modicon 00001).
#: Se lee con 0x01 y se escribe con 0x05 (Write Single Coil).
DIR_COIL_LED_DIGITAL = 0x0000

#: Offset del Holding Register que gobierna el PWM del LED 2 (Modicon 40001).
#: Se lee con 0x03 y se escribe con 0x06 (Write Single Register).
DIR_HOLDING_REGISTER_PWM = 0x0000


# =============================================================================
# 4. DIRECCIONES DE ESCLAVO (Unit ID)
# =============================================================================
# Rango valido en MODBus serie: 1 a 247. El 0 se reserva para difusion
# (broadcast) y no se usa en este trabajo, porque un mensaje de difusion no
# genera respuesta y por lo tanto no permite confirmar que la orden llego.

ID_ESCLAVO_1 = 1
ID_ESCLAVO_2 = 2


# =============================================================================
# 5. RANGOS Y ESCALAS
# =============================================================================

#: Valor maximo del ADC del ESP32 configurado a 12 bits de resolucion.
#: Un Arduino UNO daria 1023 (10 bits): el rango es una caracteristica del
#: hardware del esclavo y por eso se documenta en el mapa de registros.
ADC_MAXIMO = 4095

#: Valor maximo admitido en el Holding Register de PWM. Lo fija la consigna
#: ("rango 0 a 255"), no el hardware: el ESP32 podria manejar 16 bits de
#: resolucion de PWM. Se respeta el rango pedido y se convierte internamente.
PWM_MAXIMO = 255

#: Frecuencia de la portadora PWM en Hz. Muy por encima del umbral de fusion de
#: parpadeo del ojo humano (~60-90 Hz), por lo que la variacion de intensidad se
#: percibe continua y no como titileo.
PWM_FRECUENCIA_HZ = 1000

#: Desplazamiento a derecha para convertir una lectura del ADC (0-4095) al rango
#: de PWM (0-255). Equivale a dividir por 16, es exacto y no requiere punto
#: flotante: 4095 >> 4 = 255. Ver docs/MAPA_REGISTROS.md §3.2.
DESPLAZAMIENTO_ADC_A_PWM = 4


# =============================================================================
# 6. TEMPORIZACION
# =============================================================================

#: Periodo del ciclo de sondeo del maestro, en milisegundos.
#:
#: NO es un numero elegido "porque queda bien": surge de calcular cuanto tiempo
#: ocupa el bus un ciclo completo de cuatro transacciones y dejar margen.
#:
#:   Bytes por transaccion (peticion + respuesta), segun la especificacion:
#:     0x02 Read Discrete Inputs   ->  8 +  6 = 14 bytes
#:     0x04 Read Input Registers   ->  8 +  7 = 15 bytes
#:     0x05 Write Single Coil      ->  8 +  8 = 16 bytes  (la respuesta es un eco)
#:     0x06 Write Single Register  ->  8 +  8 = 16 bytes  (la respuesta es un eco)
#:                                          Total = 61 bytes
#:
#:   Tiempo de transmision:  61 bytes x 11 bits/byte / 9600 bit/s = 69,9 ms
#:   Silencios entre tramas: 8 tramas x t3,5 (4,01 ms)            = 32,1 ms
#:                                        Ocupacion minima del bus = 102,0 ms
#:
#: Con un periodo de 100 ms el bus quedaria al 100 % de ocupacion: no habria
#: margen para reintentos ni para la latencia de procesamiento del esclavo, y el
#: sistema entraria en timeouts permanentes. Con 200 ms la ocupacion es del 51 %,
#: que deja lugar a un reintento completo dentro del mismo ciclo, y la respuesta
#: al mover el potenciometro sigue percibiendose como instantanea.
#:
#: Trade-off explicito: se resigna frecuencia de actualizacion (5 Hz en vez de
#: 10 Hz) a cambio de margen temporal. Es la decision correcta en un bus
#: half-duplex, donde saturar el medio no acelera nada: solo genera colisiones
#: de turno y reintentos.
PERIODO_SONDEO_MS = 200

#: Tiempo maximo de espera de la respuesta de un esclavo, en milisegundos.
#: Si vence, la transaccion se da por perdida y el ciclo continua sin bloquearse:
#: un maestro que se cuelga esperando a un esclavo caido deja de atender al resto
#: del bus, que es exactamente lo que no debe pasar en un sistema de control.
TIMEOUT_RESPUESTA_MS = 300

#: Ventana de antirrebote del switch, en milisegundos. Los contactos mecanicos
#: rebotan tipicamente entre 1 y 10 ms; 20 ms cubre ese fenomeno con margen sin
#: que el usuario perciba retardo.
ANTIRREBOTE_MS = 20

#: Cantidad de muestras que se promedian en cada lectura del ADC. El ADC del
#: ESP32 tiene un ruido de algunas unidades de LSB; sin promediar, el Input
#: Register cambiaria de valor en cada sondeo aun con el potenciometro quieto, y
#: el LED PWM del maestro titilaria. 8 muestras es potencia de 2, por lo que el
#: promedio se calcula con un desplazamiento en vez de una division.
MUESTRAS_ADC = 8
