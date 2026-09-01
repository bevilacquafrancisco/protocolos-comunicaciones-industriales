"""
main.py  (ESCLAVO MODBus RTU)
Autor: Francisco Bevilacqua
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Firmware del dispositivo Esclavo MODBus RTU sobre RS-485 (Partes 1 y 3 de la
Tarea Nº1). Un mismo archivo corre en el Esclavo 1 y en el Esclavo 2: la
direccion fisica (Unit ID) se determina en el arranque leyendo un jumper de
hardware, tal como un modulo de E/S remoto industrial la toma de sus llaves DIP.

El esclavo es un dispositivo PASIVO: nunca inicia una transaccion. Solo responde
cuando un maestro lo interroga con su Unit ID, y permanece callado en cualquier
otro caso. Esa asimetria es la esencia del modelo maestro-esclavo por sondeo.

Mapa de registros implementado (identico en ambos esclavos)
-----------------------------------------------------------
  Modicon 10001  Discrete Input  0x0000  0x02        Switch / pulsador
  Modicon 30001  Input Register  0x0000  0x04        Potenciometro (ADC, 0-4095)
  Modicon 00001  Coil            0x0000  0x01 / 0x05 LED 1 digital
  Modicon 40001  Holding Reg.    0x0000  0x03 / 0x06 LED 2 PWM (0-255)

Correspondencia con el diagrama de flujo (diagramas/flujo_esclavo.md)
---------------------------------------------------------------------
  Bloque E1  INICIO / CONFIGURACION      -> funcion configurar_nodo()
  Bloque E2  LEER JUMPER DE UNIT ID      -> funcion leer_unit_id()
  Bloque E3  PUBLICAR ENTRADAS FISICAS   -> funcion publicar_entradas()
  Bloque E4  ATENDER PETICION DEL BUS    -> llamada a cliente.process()
  Bloque E5  APLICAR SALIDAS FISICAS     -> funcion aplicar_salidas()
  Bloque E6  LAZO INFINITO               -> funcion main()

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32.
- micropython-modbus (brainelectronics), paquete `umodbus`.
  Instalacion documentada en firmware/README.md.
- Modulos locales: config.py y perifericos.py, que deben copiarse a la raiz del
  sistema de archivos del ESP32 junto a este main.py.
"""

import time

from machine import Pin
from umodbus.serial import ModbusRTU

import config
from perifericos import EntradaDigital, EntradaAnalogica, SalidaDigital, SalidaPWM


# =============================================================================
# BLOQUE E2 del diagrama de flujo — Determinacion de la direccion fisica
# =============================================================================

def leer_unit_id():
    """
    Determina el Unit ID de este esclavo leyendo el jumper de direccionamiento.

    La consigna exige una "direccion fisica fija". Se implementa con un jumper
    en config.PIN_SELECTOR y no con una constante en el codigo porque:

      1. Es literalmente una direccion fisica, como las llaves DIP de un modulo
         de E/S remoto o de un variador de frecuencia real.
      2. Permite que ambos esclavos ejecuten el MISMO firmware (principio DRY),
         eliminando la clase de error "actualice un esclavo y me olvide del
         otro", que en un bus de campo se manifiesta como un fallo intermitente
         dificilisimo de atribuir.

    El pin se lee con pull-up interno, por lo que el jumper abierto da nivel alto.

        Jumper ABIERTO      -> pin en 1 -> Unit ID 1 (Esclavo 1)
        Jumper PUENTEADO a GND -> pin en 0 -> Unit ID 2 (Esclavo 2)

    La lectura se hace una sola vez, en el arranque: cambiar la direccion de un
    dispositivo MODBus en caliente dejaria al maestro hablandole a un nodo que ya
    no existe, y en la practica industrial el redireccionamiento siempre exige
    reiniciar el equipo.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    int
        config.ID_ESCLAVO_1 o config.ID_ESCLAVO_2.

    Excepciones
    -----------
    Ninguna.
    """
    jumper = Pin(config.PIN_SELECTOR, Pin.IN, Pin.PULL_UP)

    # Pequena espera para que la resistencia de pull-up cargue la capacidad
    # parasita del cableado antes de muestrear. Sin esto, una lectura inmediata
    # tras la configuracion del pin puede devolver un valor espurio.
    time.sleep_ms(10)

    return config.ID_ESCLAVO_1 if jumper.value() else config.ID_ESCLAVO_2


# =============================================================================
# BLOQUE E1 del diagrama de flujo — Inicializacion del nodo
# =============================================================================

def configurar_perifericos():
    """
    Instancia los cuatro perifericos fisicos del esclavo.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    dict
        Diccionario con las claves 'switch', 'potenciometro', 'led_digital' y
        'led_pwm', cada una con su objeto de la capa de perifericos.

    Excepciones
    -----------
    ValueError
        Propagada desde la capa de perifericos si algun pin de config.py fuera
        incompatible con el uso que se le da (por ejemplo, un GPIO de solo
        entrada asignado a una salida). Es deliberado que falle en el arranque:
        un nodo mal configurado debe negarse a operar, no operar a medias.
    """
    return {
        "switch": EntradaDigital(config.PIN_SWITCH),
        "potenciometro": EntradaAnalogica(config.PIN_POTENCIOMETRO),
        "led_digital": SalidaDigital(config.PIN_LED_DIGITAL, estado_inicial=False),
        "led_pwm": SalidaPWM(config.PIN_LED_PWM),
    }


def configurar_servidor_modbus(unit_id):
    """
    Crea el servidor MODBus RTU y da de alta las cuatro areas de datos.

    Parametros
    ----------
    unit_id : int
        Direccion fisica de este esclavo en el bus (1 a 247).

    Retorna
    -------
    umodbus.serial.ModbusRTU
        Instancia ya configurada, lista para atender peticiones con process().

    Excepciones
    -----------
    OSError
        Si el UART indicado en config.UART_ID no puede inicializarse (pines
        ocupados o identificador de UART inexistente en la placa).

    Detalle de la configuracion de la libreria
    ------------------------------------------
    Constructor ModbusRTU(addr, baudrate, data_bits, stop_bits, parity, pins,
    ctrl_pin, uart_id):

      addr      : int   -> Unit ID propio; solo responde a tramas con este valor
                          (y descarta las dirigidas a cualquier otro nodo).
      baudrate  : int   -> debe coincidir con todos los nodos del bus.
      data_bits : int   -> 8, obligatorio en modo RTU.
      stop_bits : int   -> 1.
      parity    : int   -> None (sin paridad).
      pins      : tupla -> (TX, RX) en ese orden.
      ctrl_pin  : int   -> GPIO conectado a DE y RE del MAX485. La libreria lo
                          pone en alto antes de transmitir y en bajo al terminar,
                          que es lo que hace posible el half-duplex.
      uart_id   : int   -> 2, para no invadir el UART0 de la consola REPL.

    El diccionario de registros usa las claves COILS, HREGS, ISTS e IREGS, y
    dentro de cada una: 'register' (offset dentro del area) y 'val' (valor
    inicial). Los valores iniciales definen el estado seguro del dispositivo
    antes de recibir la primera orden del maestro: ambas salidas en reposo.
    """
    cliente = ModbusRTU(
        addr=unit_id,
        baudrate=config.BAUDRATE,
        data_bits=config.BITS_DATOS,
        stop_bits=config.BITS_PARADA,
        parity=config.PARIDAD,
        pins=(config.PIN_UART_TX, config.PIN_UART_RX),
        ctrl_pin=config.PIN_DE_RE,
        uart_id=config.UART_ID,
    )

    definicion_registros = {
        # Coil 0x0000 (Modicon 00001) — LED 1. Escribible por el maestro con la
        # funcion 0x05 y legible con la 0x01.
        "COILS": {
            "led_digital": {
                "register": config.DIR_COIL_LED_DIGITAL,
                "val": False,
            },
        },
        # Holding Register 0x0000 (Modicon 40001) — intensidad PWM del LED 2.
        # Escribible con 0x06 y legible con 0x03.
        "HREGS": {
            "led_pwm": {
                "register": config.DIR_HOLDING_REGISTER_PWM,
                "val": 0,
            },
        },
        # Discrete Input 0x0000 (Modicon 10001) — switch. Solo lectura (0x02):
        # el maestro no puede escribirlo, y eso es correcto porque refleja el
        # estado de un contacto fisico, no una orden.
        "ISTS": {
            "switch": {
                "register": config.DIR_DISCRETE_INPUT_SWITCH,
                "val": False,
            },
        },
        # Input Register 0x0000 (Modicon 30001) — ADC del potenciometro.
        # Solo lectura (0x04), por el mismo motivo.
        "IREGS": {
            "potenciometro": {
                "register": config.DIR_INPUT_REGISTER_POTE,
                "val": 0,
            },
        },
    }

    cliente.setup_registers(registers=definicion_registros)
    return cliente


# =============================================================================
# BLOQUE E3 del diagrama de flujo — Publicacion de las entradas fisicas
# =============================================================================

def publicar_entradas(cliente, perifericos):
    """
    Lee los sensores fisicos y actualiza las areas de solo lectura del servidor.

    Este paso se ejecuta ANTES de atender el bus para que la respuesta que el
    maestro reciba refleje el estado mas reciente posible de las entradas. El
    orden importa: si se publicara despues de process(), cada respuesta llevaria
    el valor del ciclo anterior y se agregaria un periodo de sondeo completo de
    retardo (200 ms) sin ninguna necesidad.

    Parametros
    ----------
    cliente : umodbus.serial.ModbusRTU
        Servidor MODBus cuyas areas ISTS e IREGS se actualizan.
    perifericos : dict
        Diccionario devuelto por configurar_perifericos().

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna.
    """
    # Discrete Input 10001: estado del switch, ya filtrado de rebotes.
    cliente.set_ist(
        address=config.DIR_DISCRETE_INPUT_SWITCH,
        value=perifericos["switch"].leer(),
    )

    # Input Register 30001: valor CRUDO del ADC, 0-4095, sin escalar.
    # Decision documentada en docs/MAPA_REGISTROS.md §3.2: el esclavo transporta
    # la medicion, no su interpretacion; el escalado a PWM es responsabilidad de
    # quien consume el dato.
    cliente.set_ireg(
        address=config.DIR_INPUT_REGISTER_POTE,
        value=perifericos["potenciometro"].leer(),
    )


# =============================================================================
# BLOQUE E5 del diagrama de flujo — Aplicacion de las salidas fisicas
# =============================================================================

def aplicar_salidas(cliente, perifericos):
    """
    Lleva a los actuadores el contenido actual de las areas escribibles.

    Aca se materializa el requisito de la Parte 3 de que "el esclavo que no este
    seleccionado mantenga el ultimo estado recibido en sus salidas hasta recibir
    una nueva orden". No hace falta ninguna logica de retencion explicita: el
    Coil y el Holding Register conservan su valor en la memoria del servidor
    mientras nadie los escriba, y esta funcion simplemente los refleja en el
    hardware en cada vuelta del lazo. La retencion es una propiedad del modelo de
    datos de MODBus, no un anadido del firmware.

    El requisito que si depende del firmware es el complementario: NO reinicializar
    estos registros dentro del lazo. Por eso los valores iniciales se fijan una
    unica vez, en configurar_servidor_modbus().

    Parametros
    ----------
    cliente : umodbus.serial.ModbusRTU
        Servidor MODBus del que se leen las areas COILS y HREGS.
    perifericos : dict
        Diccionario devuelto por configurar_perifericos().

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna.
    """
    # Coil 00001 -> LED 1 digital.
    perifericos["led_digital"].escribir(
        cliente.get_coil(address=config.DIR_COIL_LED_DIGITAL)
    )

    # Holding Register 40001 -> LED 2 PWM. La capa de perifericos acota el valor
    # al rango 0-255: si un maestro mal configurado escribe 5000, el esclavo
    # satura y sigue operando en vez de lanzar una excepcion y reiniciarse.
    perifericos["led_pwm"].escribir(
        cliente.get_hreg(address=config.DIR_HOLDING_REGISTER_PWM)
    )


# =============================================================================
# BLOQUE E6 del diagrama de flujo — Lazo principal
# =============================================================================

def main():
    """
    Punto de entrada del firmware del esclavo.

    Secuencia de arranque y lazo infinito:

        E1/E2  Configurar perifericos y determinar el Unit ID por jumper
        E1     Levantar el servidor MODBus RTU sobre el UART2
        ---- lazo ----
        E3     Publicar entradas fisicas en las areas de solo lectura
        E4     Atender una eventual peticion del bus
        E5     Aplicar las areas escribibles a los actuadores

    El lazo NO lleva una espera fija. El ritmo lo impone el maestro: process()
    consume el tiempo que haga falta esperando una trama y retorna en cuanto la
    atiende o vence su propio timeout interno. Agregar un sleep aca reduciria la
    ventana en que el esclavo esta efectivamente escuchando y provocaria
    timeouts en el maestro.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    None. La funcion no retorna: contiene el lazo infinito del dispositivo.

    Excepciones
    -----------
    Ninguna se propaga hacia afuera. Las excepciones del procesamiento MODBus se
    atrapan y se informan por consola sin detener el nodo: en un sistema de
    control, un dispositivo de campo que se detiene ante una trama malformada es
    peor que uno que la descarta y sigue operando.
    """
    unit_id = leer_unit_id()
    perifericos = configurar_perifericos()
    cliente = configurar_servidor_modbus(unit_id)

    print("=" * 58)
    print("ESCLAVO MODBus RTU  |  Unit ID = {}".format(unit_id))
    print("Bus: {} baudios, {}{}{}".format(
        config.BAUDRATE,
        config.BITS_DATOS,
        "N" if config.PARIDAD is None else "E",
        config.BITS_PARADA,
    ))
    print("UART{}  TX=GPIO{}  RX=GPIO{}  DE/RE=GPIO{}".format(
        config.UART_ID, config.PIN_UART_TX, config.PIN_UART_RX, config.PIN_DE_RE,
    ))
    print("Registros: DI 10001 | IR 30001 | Coil 00001 | HR 40001")
    print("=" * 58)

    while True:
        try:
            publicar_entradas(cliente, perifericos)   # Bloque E3
            cliente.process()                          # Bloque E4
            aplicar_salidas(cliente, perifericos)      # Bloque E5
        except Exception as error:
            # Se informa pero no se aborta. Causas esperables: trama truncada por
            # ruido en el bus, o una funcion MODBus no implementada solicitada
            # por una herramienta de diagnostico.
            print("[ESCLAVO {}] Error atendiendo el bus: {}".format(unit_id, error))


if __name__ == "__main__":
    main()
