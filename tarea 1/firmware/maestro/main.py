"""
main.py  (MAESTRO MODBus RTU)
Autor: Francisco Bevilacqua
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Firmware del dispositivo Maestro MODBus RTU sobre RS-485 (Partes 2 y 3 de la
Tarea Nº1). Es el unico nodo que inicia transacciones en el bus: sondea
periodicamente al esclavo seleccionado, replica en sus salidas locales las
entradas remotas, y escribe en las salidas remotas sus propias entradas locales.

La logica esta implementada como una MAQUINA DE ESTADOS FINITOS explicita y no
como una secuencia de banderas booleanas. Los motivos son concretos:

  1. Se corresponde uno a uno con el diagrama de flujo que exige la consigna, lo
     que hace verificable la trazabilidad entre codigo y documentacion.
  2. Cada estado ejecuta UNA sola transaccion MODBus, por lo que el lazo nunca
     queda bloqueado mas de un timeout: el maestro sigue atendiendo el switch
     selector aunque un esclavo este caido.
  3. Agregar un tercer esclavo o una transaccion nueva es agregar un estado, sin
     tocar los existentes (principio abierto/cerrado).

Ciclo de sondeo (Parte 3 completa)
----------------------------------
    LEER_SELECTOR -> INDICAR_SELECCION -> LEER_DI_REMOTO -> LEER_IR_REMOTO
        -> ESCRIBIR_COIL_REMOTO -> ESCRIBIR_HREG_REMOTO -> ESPERA -> (vuelve)

Correspondencia con el diagrama de flujo (diagramas/flujo_maestro.md)
----------------------------------------------------------------------
  Bloque M1  INICIO / CONFIGURACION        -> configurar_perifericos(), configurar_maestro_modbus()
  Bloque M2  LEER SWITCH SELECTOR          -> estado LEER_SELECTOR
  Bloque M3  ENCENDER LED INDICADOR        -> estado INDICAR_SELECCION
  Bloque M4  LEER ENTRADA DIGITAL REMOTA   -> estado LEER_DI_REMOTO      (funcion 0x02)
  Bloque M5  LEER ENTRADA ANALOGICA REMOTA -> estado LEER_IR_REMOTO      (funcion 0x04)
  Bloque M6  ESCRIBIR SALIDA DIGITAL       -> estado ESCRIBIR_COIL_REMOTO(funcion 0x05)
  Bloque M7  ESCRIBIR SALIDA PWM           -> estado ESCRIBIR_HREG_REMOTO(funcion 0x06)
  Bloque M8  ESPERAR FIN DE PERIODO        -> estado ESPERA
  Bloque M9  MANEJO DE TIMEOUT             -> funcion registrar_fallo()

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32.
- micropython-modbus (brainelectronics), paquete `umodbus`.
- Modulos locales: config.py y perifericos.py en la raiz del ESP32.
"""

import time

from machine import Pin
from umodbus.serial import Serial as ModbusRTUMaster

import config
from perifericos import (
    EntradaDigital,
    EntradaAnalogica,
    SalidaDigital,
    SalidaPWM,
    adc_a_pwm,
)


# =============================================================================
# Definicion de los estados de la maquina de estados
# =============================================================================
# Se usan constantes enteras y no cadenas: la comparacion es mas rapida y no
# genera basura en el heap, algo que importa en un lazo que corre miles de veces
# por minuto en un interprete con recoleccion de basura.

ESTADO_LEER_SELECTOR = 0
ESTADO_INDICAR_SELECCION = 1
ESTADO_LEER_DI_REMOTO = 2
ESTADO_LEER_IR_REMOTO = 3
ESTADO_ESCRIBIR_COIL_REMOTO = 4
ESTADO_ESCRIBIR_HREG_REMOTO = 5
ESTADO_ESPERA = 6

#: Nombres legibles de los estados, solo para los mensajes de diagnostico.
NOMBRES_ESTADO = {
    ESTADO_LEER_SELECTOR: "LEER_SELECTOR",
    ESTADO_INDICAR_SELECCION: "INDICAR_SELECCION",
    ESTADO_LEER_DI_REMOTO: "LEER_DI_REMOTO",
    ESTADO_LEER_IR_REMOTO: "LEER_IR_REMOTO",
    ESTADO_ESCRIBIR_COIL_REMOTO: "ESCRIBIR_COIL_REMOTO",
    ESTADO_ESCRIBIR_HREG_REMOTO: "ESCRIBIR_HREG_REMOTO",
    ESTADO_ESPERA: "ESPERA",
}

#: Cantidad de ciclos consecutivos con fallo tras los cuales se considera que el
#: esclavo esta ausente y se apagan los replicadores locales. Se eligio 3 y no 1
#: para no reaccionar a una unica trama perdida por ruido, que en un bus RS-485
#: es un evento normal y no una falla del dispositivo.
CICLOS_PARA_DECLARAR_AUSENTE = 3


class MaestroModbus:
    """
    Maestro MODBus RTU con seleccion dinamica de esclavo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Ser el unico iniciador de transacciones del bus. Ejecuta ciclicamente cuatro
    transacciones contra el esclavo activo (dos lecturas y dos escrituras),
    gobierna los LED indicadores de seleccion y maneja los timeouts sin bloquear.

    Atributos principales
    ---------------------
    _bus : umodbus.serial.Serial
        Interfaz MODBus RTU sobre el UART2.
    _perifericos : dict
        Perifericos locales (switch, potenciometro, LED replicadores e indicadores).
    _estado : int
        Estado actual de la maquina de estados.
    _id_activo : int
        Unit ID del esclavo con el que se esta interactuando en este ciclo.
    _di_remoto : bool
        Ultimo valor leido del Discrete Input del esclavo (switch remoto).
    _ir_remoto : int
        Ultimo valor leido del Input Register del esclavo (ADC remoto).
    _fallos_consecutivos : int
        Contador de ciclos seguidos en los que alguna transaccion fallo.
    _instante_fin_espera : int
        Marca de tiempo (ticks_ms) en que termina el estado ESPERA.

    Relaciones con otras clases
    ---------------------------
    Depende de la capa de perifericos (composicion) y de la interfaz MODBus de
    umodbus. No conoce detalles de machine.Pin ni de la trama MODBus.
    """

    def __init__(self, bus, perifericos):
        """
        Inicializa la maquina de estados en un estado de arranque conocido.

        Parametros
        ----------
        bus : umodbus.serial.Serial
            Interfaz MODBus RTU ya configurada.
        perifericos : dict
            Diccionario devuelto por configurar_perifericos().

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._bus = bus
        self._perifericos = perifericos

        self._estado = ESTADO_LEER_SELECTOR
        self._id_activo = config.ID_ESCLAVO_1

        self._di_remoto = False
        self._ir_remoto = 0

        self._fallos_consecutivos = 0
        self._instante_fin_espera = time.ticks_ms()

        # Despachador estado -> metodo. Reemplaza una cadena de if/elif por una
        # tabla, que es la forma canonica de implementar una maquina de estados
        # y hace que agregar un estado no implique tocar la logica existente.
        self._acciones = {
            ESTADO_LEER_SELECTOR: self._accion_leer_selector,
            ESTADO_INDICAR_SELECCION: self._accion_indicar_seleccion,
            ESTADO_LEER_DI_REMOTO: self._accion_leer_di_remoto,
            ESTADO_LEER_IR_REMOTO: self._accion_leer_ir_remoto,
            ESTADO_ESCRIBIR_COIL_REMOTO: self._accion_escribir_coil_remoto,
            ESTADO_ESCRIBIR_HREG_REMOTO: self._accion_escribir_hreg_remoto,
            ESTADO_ESPERA: self._accion_espera,
        }

    # -------------------------------------------------------------------------
    # BLOQUE M2 — Lectura del switch selector de esclavo (Parte 3)
    # -------------------------------------------------------------------------
    def _accion_leer_selector(self):
        """
        Determina a que esclavo se dirigiran las transacciones de este ciclo.

        El selector se lee UNA vez por ciclo y no antes de cada transaccion. Es
        una decision deliberada: si se releyera entre transacciones, un cambio
        del switch a mitad de ciclo produciria una secuencia incoherente (leer
        del Esclavo 1 y escribir al Esclavo 2), dejando a ambos en un estado que
        no corresponde a ninguna orden completa. Muestrear al inicio garantiza
        que las cuatro transacciones del ciclo son atomicas respecto del destino.

        Convencion del switch (pull-up interno, contacto a GND):
            abierto   -> pin en 1 -> Esclavo 1
            a GND     -> pin en 0 -> Esclavo 2

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            Siguiente estado: ESTADO_INDICAR_SELECCION.

        Excepciones
        -----------
        Ninguna.
        """
        self._id_activo = (
            config.ID_ESCLAVO_1
            if self._perifericos["selector"].value()
            else config.ID_ESCLAVO_2
        )
        return ESTADO_INDICAR_SELECCION

    # -------------------------------------------------------------------------
    # BLOQUE M3 — Indicacion visual del esclavo activo (Parte 3)
    # -------------------------------------------------------------------------
    def _accion_indicar_seleccion(self):
        """
        Enciende el LED indicador del esclavo activo y apaga el otro.

        Los dos LED son mutuamente excluyentes por construccion: se calculan a
        partir de la misma variable _id_activo, de modo que es imposible que
        queden ambos encendidos o ambos apagados. Derivar los dos estados de una
        unica fuente de verdad, en vez de encender uno y apagar el otro en
        lineas separadas, elimina por diseno el estado invalido.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            Siguiente estado: ESTADO_LEER_DI_REMOTO.

        Excepciones
        -----------
        Ninguna.
        """
        es_esclavo_1 = self._id_activo == config.ID_ESCLAVO_1
        self._perifericos["indicador_1"].escribir(es_esclavo_1)
        self._perifericos["indicador_2"].escribir(not es_esclavo_1)
        return ESTADO_LEER_DI_REMOTO

    # -------------------------------------------------------------------------
    # BLOQUE M4 — Lectura del Discrete Input remoto (funcion 0x02)
    # -------------------------------------------------------------------------
    def _accion_leer_di_remoto(self):
        """
        Lee el switch del esclavo activo y lo replica en el LED digital local.

        Transaccion MODBus emitida (Modicon 10001 -> offset 0x0000):

            Peticion:  [ID][02][00 00][00 01][CRC_lo CRC_hi]        8 bytes
            Respuesta: [ID][02][01][estado][CRC_lo CRC_hi]          6 bytes

        Metodo de la libreria:
            read_discrete_inputs(slave_addr: int, starting_addr: int,
                                 input_qty: int) -> tuple[bool, ...]
            Devuelve una tupla de booleanos con tantos elementos como se pidieron;
            se toma el indice 0 porque se solicita una sola entrada.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_LEER_IR_REMOTO si la lectura fue exitosa; ESTADO_ESPERA si
            fallo, para no encadenar tres transacciones mas contra un esclavo
            que evidentemente no esta respondiendo.

        Excepciones
        -----------
        Ninguna se propaga: se atrapan y se contabilizan en registrar_fallo().
        """
        try:
            respuesta = self._bus.read_discrete_inputs(
                slave_addr=self._id_activo,
                starting_addr=config.DIR_DISCRETE_INPUT_SWITCH,
                input_qty=1,
            )
            self._di_remoto = bool(respuesta[0])

            # Replicacion pedida por la Parte 2: la entrada digital del esclavo
            # se refleja en el LED digital local del maestro.
            self._perifericos["led_replicador_digital"].escribir(self._di_remoto)
            return ESTADO_LEER_IR_REMOTO

        except Exception as error:
            self._registrar_fallo("0x02 Read Discrete Inputs", error)
            return ESTADO_ESPERA

    # -------------------------------------------------------------------------
    # BLOQUE M5 — Lectura del Input Register remoto (funcion 0x04)
    # -------------------------------------------------------------------------
    def _accion_leer_ir_remoto(self):
        """
        Lee el potenciometro del esclavo activo y lo replica en el LED PWM local.

        Transaccion MODBus emitida (Modicon 30001 -> offset 0x0000):

            Peticion:  [ID][04][00 00][00 01][CRC_lo CRC_hi]        8 bytes
            Respuesta: [ID][04][02][val_MSB val_LSB][CRC_lo CRC_hi] 7 bytes

        Sobre el orden de bytes: el valor de 16 bits viaja BIG-ENDIAN dentro del
        registro (primero el byte mas significativo), a diferencia del CRC, que
        viaja little-endian. La libreria ya recompone el entero, por lo que el
        codigo de aplicacion recibe un int y no necesita hacer el corrimiento a
        mano. La verificacion de este punto esta en herramientas/decodificar_trama.py.

        Metodo de la libreria:
            read_input_registers(slave_addr: int, starting_addr: int,
                                 register_qty: int, signed: bool) -> tuple[int, ...]
            signed=False porque el ADC entrega un valor sin signo de 0 a 4095;
            con signed=True, cualquier lectura por encima de 32767 se
            interpretaria como negativa (no ocurre con 12 bits, pero declararlo
            explicitamente documenta la intencion y evita una sorpresa si el
            rango del registro se ampliara).

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESCRIBIR_COIL_REMOTO si tuvo exito, ESTADO_ESPERA si fallo.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        try:
            respuesta = self._bus.read_input_registers(
                slave_addr=self._id_activo,
                starting_addr=config.DIR_INPUT_REGISTER_POTE,
                register_qty=1,
                signed=False,
            )
            self._ir_remoto = respuesta[0]

            # Replicacion pedida por la Parte 2: el ADC remoto (0-4095) gobierna
            # la intensidad del LED PWM local (0-255). El escalado se hace aca,
            # en el consumidor del dato, no en el esclavo.
            self._perifericos["led_replicador_pwm"].escribir(adc_a_pwm(self._ir_remoto))
            return ESTADO_ESCRIBIR_COIL_REMOTO

        except Exception as error:
            self._registrar_fallo("0x04 Read Input Registers", error)
            return ESTADO_ESPERA

    # -------------------------------------------------------------------------
    # BLOQUE M6 — Escritura del Coil remoto (funcion 0x05)
    # -------------------------------------------------------------------------
    def _accion_escribir_coil_remoto(self):
        """
        Escribe el estado del switch local en el LED digital del esclavo activo.

        Transaccion MODBus emitida (Modicon 00001 -> offset 0x0000):

            Peticion:  [ID][05][00 00][FF 00][CRC_lo CRC_hi]        8 bytes
            Respuesta: eco identico a la peticion                   8 bytes

        Sobre el valor 0xFF00: la especificacion MODBus no usa 0x0001 para
        "encendido" en la funcion 0x05, sino los valores 0xFF00 (ON) y 0x0000
        (OFF); cualquier otro valor debe rechazarse con una excepcion 03. La
        libreria hace esa traduccion a partir del booleano, pero conviene
        conocerla porque es lo que se va a ver en la captura de la trama.

        Metodo de la libreria:
            write_single_coil(slave_addr: int, output_address: int,
                              output_value: bool | int) -> bool
            Devuelve True si el esclavo confirmo con el eco esperado.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESCRIBIR_HREG_REMOTO si tuvo exito, ESTADO_ESPERA si fallo.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        try:
            self._bus.write_single_coil(
                slave_addr=self._id_activo,
                output_address=config.DIR_COIL_LED_DIGITAL,
                output_value=self._perifericos["switch_local"].leer(),
            )
            return ESTADO_ESCRIBIR_HREG_REMOTO

        except Exception as error:
            self._registrar_fallo("0x05 Write Single Coil", error)
            return ESTADO_ESPERA

    # -------------------------------------------------------------------------
    # BLOQUE M7 — Escritura del Holding Register remoto (funcion 0x06)
    # -------------------------------------------------------------------------
    def _accion_escribir_hreg_remoto(self):
        """
        Escribe el potenciometro local en el PWM del esclavo activo.

        Transaccion MODBus emitida (Modicon 40001 -> offset 0x0000):

            Peticion:  [ID][06][00 00][00 XX][CRC_lo CRC_hi]        8 bytes
            Respuesta: eco identico a la peticion                   8 bytes

        El valor local del ADC (0-4095) se convierte al rango 0-255 que declara
        el mapa de registros ANTES de enviarlo. Enviar el valor crudo escribiria
        hasta 4095 en un registro documentado como 0-255: el esclavo lo acotaria
        y el sistema funcionaria, pero el contrato del mapa de registros quedaria
        violado y la lectura de vuelta del registro no coincidiria con lo escrito.

        Metodo de la libreria:
            write_single_register(slave_addr: int, register_address: int,
                                  register_value: int, signed: bool) -> bool

        Este es el ultimo estado del ciclo util: cuando termina, se cierra la
        ronda y se pasa a ESPERA. Ademas, un ciclo completado sin errores
        reinicia el contador de fallos consecutivos.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESPERA en cualquier caso (con o sin exito): el ciclo termino.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        try:
            valor_local = adc_a_pwm(self._perifericos["potenciometro_local"].leer())
            self._bus.write_single_register(
                slave_addr=self._id_activo,
                register_address=config.DIR_HOLDING_REGISTER_PWM,
                register_value=valor_local,
                signed=False,
            )
            # Ciclo completo sin errores: el esclavo esta sano.
            self._fallos_consecutivos = 0

        except Exception as error:
            self._registrar_fallo("0x06 Write Single Register", error)

        return ESTADO_ESPERA

    # -------------------------------------------------------------------------
    # BLOQUE M8 — Espera hasta completar el periodo de sondeo
    # -------------------------------------------------------------------------
    def _accion_espera(self):
        """
        Espera de forma NO BLOQUEANTE a que se cumpla el periodo de sondeo.

        No se usa time.sleep(): una espera bloqueante congela el nodo y, si mas
        adelante se agregaran tareas locales (una pantalla, un segundo bus, un
        pulsador de emergencia), quedarian sin atender durante todo el intervalo.
        La comparacion con ticks_diff() permite que el lazo principal siga
        girando libremente.

        Se usa ticks_diff() y no una resta directa porque el contador de
        milisegundos de MicroPython desborda y vuelve a cero; una resta simple
        daria un valor negativo enorme en ese instante y el maestro quedaria
        esperando indefinidamente.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESPERA mientras no se cumpla el periodo; ESTADO_LEER_SELECTOR
            cuando corresponde iniciar un ciclo nuevo.

        Excepciones
        -----------
        Ninguna.
        """
        if time.ticks_diff(self._instante_fin_espera, time.ticks_ms()) > 0:
            return ESTADO_ESPERA

        self._instante_fin_espera = time.ticks_add(
            time.ticks_ms(), config.PERIODO_SONDEO_MS
        )
        return ESTADO_LEER_SELECTOR

    # -------------------------------------------------------------------------
    # BLOQUE M9 — Manejo de fallos de comunicacion
    # -------------------------------------------------------------------------
    def _registrar_fallo(self, funcion, error):
        """
        Contabiliza un fallo de transaccion y degrada de forma segura si persiste.

        Distincion importante para el informe: un TIMEOUT (el esclavo no
        respondio) y una EXCEPCION MODBus (el esclavo respondio con un codigo de
        error 01 a 04) son cosas distintas. La primera indica un problema de bus,
        direccion o alimentacion; la segunda indica que el esclavo esta vivo y
        entiende el protocolo, pero rechaza la peticion concreta. La libreria
        senaliza ambos casos como excepcion de Python, por lo que se registra el
        texto del error para poder distinguirlos en el diagnostico.

        Politica de degradacion: tras CICLOS_PARA_DECLARAR_AUSENTE ciclos
        consecutivos con fallo, se apagan los LED replicadores locales. El
        criterio de ingenieria es que una indicacion congelada es peor que
        ninguna indicacion: un operador que ve el LED replicador encendido
        supone que esa es la lectura actual del esclavo, cuando en realidad es
        un valor viejo de hace varios segundos.

        Notese que esto NO afecta a las salidas del esclavo, que conservan su
        ultimo valor recibido: eso es exactamente lo que pide la Parte 3.

        Parametros
        ----------
        funcion : str
            Nombre de la funcion MODBus que fallo, para el mensaje de consola.
        error : Exception
            Excepcion capturada.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._fallos_consecutivos += 1
        print("[MAESTRO] Fallo {} con Esclavo {} ({} consecutivos): {}".format(
            funcion, self._id_activo, self._fallos_consecutivos, error,
        ))

        if self._fallos_consecutivos >= CICLOS_PARA_DECLARAR_AUSENTE:
            self._perifericos["led_replicador_digital"].escribir(False)
            self._perifericos["led_replicador_pwm"].apagar()

    # -------------------------------------------------------------------------
    # Motor de la maquina de estados
    # -------------------------------------------------------------------------
    def ejecutar_paso(self):
        """
        Ejecuta la accion del estado actual y transiciona al siguiente.

        Es el unico punto donde cambia self._estado, lo que hace que el flujo sea
        facil de seguir y de instrumentar: para depurar el ciclo alcanza con
        imprimir NOMBRES_ESTADO[self._estado] en esta funcion.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna se propaga. Un error inesperado en la accion de un estado se
        informa y la maquina se reinicia en ESTADO_ESPERA, de modo que el maestro
        nunca queda trabado en un estado invalido.
        """
        try:
            self._estado = self._acciones[self._estado]()
        except Exception as error:
            print("[MAESTRO] Error inesperado en estado {}: {}".format(
                NOMBRES_ESTADO.get(self._estado, self._estado), error,
            ))
            self._estado = ESTADO_ESPERA


# =============================================================================
# BLOQUE M1 del diagrama de flujo — Inicializacion del nodo
# =============================================================================

def configurar_perifericos():
    """
    Instancia los perifericos locales del maestro.

    Son ocho en total: los cuatro comunes a todos los nodos (switch,
    potenciometro, LED digital, LED PWM) mas los cuatro que agrega la Parte 3
    (switch selector y dos LED indicadores; el selector se lee como Pin crudo
    porque no necesita antirrebote — ver nota abajo).

    Nota sobre el selector sin antirrebote: se muestrea una sola vez por ciclo de
    sondeo (cada 200 ms), intervalo mucho mayor que la duracion de los rebotes
    (1-10 ms). En el peor caso, un rebote hace que un unico ciclo se dirija al
    esclavo equivocado, y el siguiente ya corrige. Agregar antirrebote aca seria
    resolver un problema que el muestreo lento ya resuelve (YAGNI).

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    dict
        Perifericos indexados por nombre.

    Excepciones
    -----------
    ValueError
        Propagada desde la capa de perifericos si un pin de config.py fuera
        incompatible con su uso.
    """
    return {
        "switch_local": EntradaDigital(config.PIN_SWITCH),
        "potenciometro_local": EntradaAnalogica(config.PIN_POTENCIOMETRO),
        "led_replicador_digital": SalidaDigital(config.PIN_LED_DIGITAL, estado_inicial=False),
        "led_replicador_pwm": SalidaPWM(config.PIN_LED_PWM),
        "selector": Pin(config.PIN_SELECTOR, Pin.IN, Pin.PULL_UP),
        "indicador_1": SalidaDigital(config.PIN_LED_INDICADOR_1, estado_inicial=False),
        "indicador_2": SalidaDigital(config.PIN_LED_INDICADOR_2, estado_inicial=False),
    }


def configurar_maestro_modbus():
    """
    Crea la interfaz MODBus RTU en modo maestro.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    umodbus.serial.Serial
        Interfaz lista para emitir transacciones.

    Excepciones
    -----------
    OSError
        Si el UART indicado no puede inicializarse.

    Detalle de la configuracion de la libreria
    ------------------------------------------
    Constructor Serial(uart_id, baudrate, data_bits, stop_bits, parity, pins,
    ctrl_pin). A diferencia del esclavo, NO recibe un parametro `addr`: un
    maestro MODBus no tiene direccion propia porque nunca es destinatario de una
    trama, solo emisor. Es una diferencia conceptual que conviene tener a mano
    para la defensa oral.
    """
    return ModbusRTUMaster(
        uart_id=config.UART_ID,
        baudrate=config.BAUDRATE,
        data_bits=config.BITS_DATOS,
        stop_bits=config.BITS_PARADA,
        parity=config.PARIDAD,
        pins=(config.PIN_UART_TX, config.PIN_UART_RX),
        ctrl_pin=config.PIN_DE_RE,
    )


def main():
    """
    Punto de entrada del firmware del maestro.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    None. Contiene el lazo infinito del dispositivo.

    Excepciones
    -----------
    Ninguna se propaga hacia afuera.
    """
    perifericos = configurar_perifericos()
    bus = configurar_maestro_modbus()
    maestro = MaestroModbus(bus, perifericos)

    print("=" * 58)
    print("MAESTRO MODBus RTU")
    print("Bus: {} baudios, {}{}{}".format(
        config.BAUDRATE,
        config.BITS_DATOS,
        "N" if config.PARIDAD is None else "E",
        config.BITS_PARADA,
    ))
    print("UART{}  TX=GPIO{}  RX=GPIO{}  DE/RE=GPIO{}".format(
        config.UART_ID, config.PIN_UART_TX, config.PIN_UART_RX, config.PIN_DE_RE,
    ))
    print("Periodo de sondeo: {} ms  |  Timeout: {} ms".format(
        config.PERIODO_SONDEO_MS, config.TIMEOUT_RESPUESTA_MS,
    ))
    print("Selector GPIO{}: abierto = Esclavo 1, a GND = Esclavo 2".format(
        config.PIN_SELECTOR,
    ))
    print("=" * 58)

    while True:
        maestro.ejecutar_paso()


if __name__ == "__main__":
    main()
