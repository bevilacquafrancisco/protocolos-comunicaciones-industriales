"""
perifericos.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Capa de abstraccion de hardware (HAL) para los perifericos fisicos usados por los
tres nodos del trabajo practico: entrada digital con antirrebote, entrada
analogica con promediado, salida digital y salida PWM.

Proposito de ingenieria: separar el "que" del "como". La logica MODBus del
maestro y de los esclavos habla de "leer el switch" o "aplicar la intensidad al
LED", sin conocer los detalles de machine.Pin, machine.ADC ni machine.PWM. Esto
tiene tres consecuencias practicas:

  1. La logica de aplicacion se puede probar en la PC reemplazando estas clases
     por dobles de prueba, sin hardware.
  2. Un cambio de pin o de rango del ADC se hace en un solo lugar.
  3. El antirrebote y el promediado del ADC quedan resueltos una sola vez y no
     se repiten (ni se olvidan) en cada firmware.

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32 (modulos machine y time del firmware oficial).
  No requiere paquetes de terceros.
"""

from machine import Pin, ADC, PWM
import time

import config


class EntradaDigital:
    """
    Entrada digital de un contacto mecanico (switch o pulsador) con filtrado de
    rebotes por software.

    Responsabilidad dentro del sistema
    ----------------------------------
    Entregar un valor booleano estable a partir de un contacto que fisicamente
    rebota. En un esclavo alimenta el Discrete Input 10001; en el maestro provee
    el valor que se escribe al Coil del esclavo.

    Por que hace falta antirrebote
    ------------------------------
    Los contactos metalicos de un pulsador no cierran limpio: rebotan entre 1 y
    10 ms generando decenas de transiciones. Sin filtrar, el maestro escribiria
    una rafaga de ordenes 0x05 contradictorias en el bus por cada pulsacion, y
    el Discrete Input del esclavo reportaria valores distintos en sondeos
    consecutivos. El filtro implementado es de tipo "temporizador de
    estabilidad": un cambio solo se acepta si el nuevo nivel se mantiene durante
    ANTIRREBOTE_MS. Se eligio sobre un filtro RC por hardware porque no cuesta
    componentes y sobre un contador de muestras porque el criterio temporal es
    independiente de la velocidad del lazo principal.

    Logica activa en bajo
    ---------------------
    El pin se configura con pull-up interno y el contacto va a masa. Por lo
    tanto el pin lee 0 cuando el switch esta accionado. La clase invierte esa
    lectura para que el resto del programa trabaje con la convencion natural
    (True = accionado) y nadie tenga que recordar la inversion.

    Atributos principales
    ---------------------
    _pin : machine.Pin
        Pin fisico configurado como entrada con pull-up.
    _estado_estable : bool
        Ultimo valor que supero la ventana de antirrebote. Es el que se publica.
    _estado_candidato : bool
        Lectura instantanea que todavia no cumplio el tiempo de estabilidad.
    _instante_cambio : int
        Marca de tiempo (ticks_ms) en que aparecio _estado_candidato.

    Relaciones con otras clases
    ---------------------------
    Independiente. Es consumida por esclavo/main.py y maestro/main.py.
    """

    def __init__(self, numero_pin, ventana_antirrebote_ms=None):
        """
        Configura el pin como entrada con pull-up y toma la lectura inicial.

        Parametros
        ----------
        numero_pin : int
            Numero de GPIO del ESP32 al que esta conectado el contacto.
        ventana_antirrebote_ms : int, opcional
            Tiempo que el nivel debe mantenerse para aceptarse como valido.
            Si se omite, se usa config.ANTIRREBOTE_MS.

        Retorna
        -------
        None

        Excepciones
        -----------
        ValueError
            Si el GPIO indicado no admite pull-up interno (GPIO 34-39 del ESP32
            son de solo entrada y carecen de resistencias internas).

        Ejemplo de uso
        --------------
        >>> switch = EntradaDigital(config.PIN_SWITCH)
        >>> switch.leer()
        False
        """
        if 34 <= numero_pin <= 39:
            # Falla temprana y con un mensaje util: si se permitiera, el pin
            # quedaria flotando y la entrada leeria ruido de forma erratica.
            raise ValueError(
                "GPIO {} es de solo entrada y no tiene pull-up interno; "
                "elegir otro pin o agregar una resistencia externa".format(numero_pin)
            )

        self._pin = Pin(numero_pin, Pin.IN, Pin.PULL_UP)
        self._ventana_ms = (
            ventana_antirrebote_ms
            if ventana_antirrebote_ms is not None
            else config.ANTIRREBOTE_MS
        )

        # Se invierte porque el circuito es activo en bajo (contacto a GND).
        lectura_inicial = not self._pin.value()
        self._estado_estable = lectura_inicial
        self._estado_candidato = lectura_inicial
        self._instante_cambio = time.ticks_ms()

    def leer(self):
        """
        Devuelve el estado filtrado del contacto y actualiza el antirrebote.

        Debe invocarse periodicamente desde el lazo principal: el filtro avanza
        cada vez que se llama, no en segundo plano.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        bool
            True si el contacto esta accionado (pin en nivel bajo por mas de la
            ventana de antirrebote), False en caso contrario.

        Excepciones
        -----------
        Ninguna.
        """
        lectura = not self._pin.value()

        if lectura != self._estado_candidato:
            # Aparecio un nivel distinto: arranca de cero la ventana de espera.
            self._estado_candidato = lectura
            self._instante_cambio = time.ticks_ms()
        elif lectura != self._estado_estable:
            # El nivel se mantiene y todavia difiere del publicado: se comprueba
            # si ya cumplio el tiempo de estabilidad exigido.
            # ticks_diff maneja correctamente el desbordamiento del contador de
            # milisegundos, cosa que una resta directa no haria.
            transcurrido = time.ticks_diff(time.ticks_ms(), self._instante_cambio)
            if transcurrido >= self._ventana_ms:
                self._estado_estable = lectura

        return self._estado_estable


class EntradaAnalogica:
    """
    Entrada analogica (potenciometro) leida por el ADC del ESP32, con promediado
    para suprimir el ruido de conversion.

    Responsabilidad dentro del sistema
    ----------------------------------
    Entregar un entero estable de 0 a config.ADC_MAXIMO. En un esclavo alimenta
    el Input Register 30001; en el maestro provee el valor que se escribe al
    Holding Register del esclavo.

    Por que se promedia
    -------------------
    El ADC SAR del ESP32 tiene un ruido tipico de varias unidades de LSB. Sin
    promediar, el Input Register cambiaria de valor entre sondeos consecutivos
    aunque nadie toque el potenciometro: el LED PWM del maestro titilaria y el
    bus se llenaria de escrituras innecesarias. Se promedian
    config.MUESTRAS_ADC lecturas, que es potencia de dos y por lo tanto el
    promedio se calcula con un desplazamiento de bits en lugar de una division,
    evitando aritmetica de punto flotante en el lazo principal.

    Atributos principales
    ---------------------
    _adc : machine.ADC
        Canal de conversion configurado a 12 bits y atenuacion de 11 dB.
    _muestras : int
        Cantidad de lecturas que se promedian por invocacion.
    _desplazamiento : int
        log2(_muestras); se precalcula una vez para no repetirlo en cada lectura.

    Relaciones con otras clases
    ---------------------------
    Independiente. Es consumida por esclavo/main.py y maestro/main.py.
    """

    def __init__(self, numero_pin, muestras=None):
        """
        Configura el canal de ADC en su rango completo de entrada.

        La atenuacion de 11 dB extiende el rango de medicion a aproximadamente
        0 a 3,3 V, que es el que cubre un potenciometro alimentado entre 3,3 V y
        masa. Con la atenuacion por defecto (0 dB) el rango util seria de solo
        0 a 1,1 V y el valor saturaria apenas se pasa un tercio del recorrido.

        Parametros
        ----------
        numero_pin : int
            GPIO del ESP32 con capacidad de ADC. Se recomienda 32-39 (ADC1).
        muestras : int, opcional
            Cantidad de lecturas a promediar; debe ser potencia de 2. Si se
            omite, se usa config.MUESTRAS_ADC.

        Retorna
        -------
        None

        Excepciones
        -----------
        ValueError
            Si `muestras` no es una potencia de 2 mayor que cero.

        Ejemplo de uso
        --------------
        >>> pote = EntradaAnalogica(config.PIN_POTENCIOMETRO)
        >>> pote.leer()
        2048
        """
        cantidad = muestras if muestras is not None else config.MUESTRAS_ADC
        if cantidad <= 0 or (cantidad & (cantidad - 1)) != 0:
            raise ValueError(
                "muestras debe ser una potencia de 2 mayor que cero, se recibio {}".format(cantidad)
            )

        # La API del ADC cambio entre versiones de MicroPython. La forma vigente
        # pasa la atenuacion como argumento del CONSTRUCTOR (atten=); es la unica
        # via garantizada en los builds oficiales recientes de ESP32, donde los
        # metodos .atten()/.width() estan marcados "legacy" en el codigo fuente
        # de MicroPython y se compilan condicionados a un flag que los builds
        # oficiales traen DESACTIVADO. Si se llama a .atten() en esa situacion,
        # el metodo ni siquiera existe: la llamada lanza AttributeError.
        #
        # Ese es justamente el bug que tenia esta clase: el intento anterior
        # llamaba solo a .atten()/.width() dentro de un try/except que tragaba
        # el AttributeError en silencio. En un build sin los metodos legacy, la
        # atenuacion nunca se aplicaba y el ADC quedaba en 0 dB (rango util real
        # 0-1,1 V), tal como advierte el parrafo anterior de este docstring. El
        # sintoma en el banco: el potenciometro parece "trabado" o saltar de
        # forma no monotona apenas se supera un tercio del recorrido, y
        # prueba_perifericos.py lo reporta como FALLA aunque el cableado este
        # perfecto — el propio machine.ADC(pin) leido con machine.Pin a mano
        # (sin pasar por esta clase) mostraba el mismo defecto si no se fijaba
        # la atenuacion explicitamente.
        try:
            self._adc = ADC(Pin(numero_pin), atten=ADC.ATTN_11DB)
        except TypeError:
            # Firmware anterior a la introduccion de atten= en el constructor:
            # crear el objeto sin ese argumento y recurrir a los metodos legacy,
            # que en un firmware de esa antiguedad si estan disponibles.
            self._adc = ADC(Pin(numero_pin))
            try:
                self._adc.atten(ADC.ATTN_11DB)
                self._adc.width(ADC.WIDTH_12BIT)
            except AttributeError:
                pass

        self._muestras = cantidad

        # log2 por conteo de desplazamientos: evita importar el modulo math, que
        # en MicroPython arrastra codigo de punto flotante innecesario.
        desplazamiento = 0
        while (1 << desplazamiento) < cantidad:
            desplazamiento += 1
        self._desplazamiento = desplazamiento

    def leer(self):
        """
        Toma N muestras consecutivas del ADC y devuelve su promedio entero.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            Valor promediado en el rango 0 a config.ADC_MAXIMO (0-4095).
            El resultado se acota explicitamente por si una version del firmware
            devolviera un valor fuera de rango: un valor mayor que 0xFFFF
            desbordaria el registro MODBus de 16 bits.

        Excepciones
        -----------
        Ninguna.
        """
        acumulador = 0
        for _ in range(self._muestras):
            acumulador += self._adc.read()

        promedio = acumulador >> self._desplazamiento

        # Saturacion defensiva: un Input Register es un entero sin signo de 16
        # bits, y publicar un valor fuera del rango declarado en el mapa de
        # registros rompe el contrato con el maestro.
        if promedio < 0:
            return 0
        if promedio > config.ADC_MAXIMO:
            return config.ADC_MAXIMO
        return promedio


class SalidaDigital:
    """
    Salida digital simple para gobernar un LED (encendido / apagado).

    Responsabilidad dentro del sistema
    ----------------------------------
    En un esclavo materializa el Coil 00001; en el maestro es el LED replicador
    del Discrete Input remoto y tambien los dos LED indicadores de esclavo
    activo de la Parte 3.

    Por que existe una clase para algo tan simple
    ---------------------------------------------
    Uniformidad de la interfaz (todas las salidas se escriben con escribir()) y
    un unico punto donde definir el estado seguro de arranque. Un actuador que
    arranca en estado indefinido es un defecto de diseno, no un detalle.

    Atributos principales
    ---------------------
    _pin : machine.Pin
        Pin fisico configurado como salida.

    Relaciones con otras clases
    ---------------------------
    Independiente. Es consumida por esclavo/main.py y maestro/main.py.
    """

    def __init__(self, numero_pin, estado_inicial=False):
        """
        Configura el pin como salida y lo lleva a un estado conocido.

        Parametros
        ----------
        numero_pin : int
            GPIO del ESP32 con capacidad de salida (evitar 34-39).
        estado_inicial : bool, opcional
            Estado seguro de arranque. Por defecto False (LED apagado): ante un
            reinicio inesperado, los actuadores quedan en reposo y no en un
            estado activo heredado por casualidad.

        Retorna
        -------
        None

        Excepciones
        -----------
        ValueError
            Si el GPIO indicado es de solo entrada.
        """
        if 34 <= numero_pin <= 39:
            raise ValueError(
                "GPIO {} es de solo entrada y no puede usarse como salida".format(numero_pin)
            )
        self._pin = Pin(numero_pin, Pin.OUT)
        self._pin.value(1 if estado_inicial else 0)

    def escribir(self, encendido):
        """
        Fija el estado de la salida.

        Parametros
        ----------
        encendido : bool
            True enciende el LED, False lo apaga. Se acepta cualquier valor con
            valor de verdad, porque la libreria MODBus puede entregar 0/1 en
            lugar de False/True segun la version.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._pin.value(1 if encendido else 0)


class SalidaPWM:
    """
    Salida de modulacion por ancho de pulso para regular la intensidad de un LED.

    Responsabilidad dentro del sistema
    ----------------------------------
    En un esclavo materializa el Holding Register 40001; en el maestro es el LED
    replicador del Input Register remoto (el potenciometro del esclavo).

    Conversion de rango
    -------------------
    La consigna fija el rango 0-255 para el registro MODBus, mientras que
    MicroPython expone el ciclo de trabajo como un entero de 16 bits sin signo
    (0-65535) mediante duty_u16(). La conversion se hace multiplicando por 257:

        255 x 257 = 65535

    Es exacta en los dos extremos del rango y no requiere punto flotante, a
    diferencia de una regla de tres con division. Se usa duty_u16() y no el
    metodo duty() de 10 bits porque este ultimo esta obsoleto y su resolucion
    (0-1023) obligaria a otra conversion.

    Atributos principales
    ---------------------
    _pwm : machine.PWM
        Canal LEDC del ESP32 configurado a config.PWM_FRECUENCIA_HZ.

    Relaciones con otras clases
    ---------------------------
    Independiente. Es consumida por esclavo/main.py y maestro/main.py.
    """

    #: Factor de conversion del rango MODBus (0-255) al rango de MicroPython
    #: (0-65535). Definido como constante de clase para que el numero magico
    #: tenga nombre y su origen quede documentado.
    _FACTOR_A_U16 = 257

    def __init__(self, numero_pin, frecuencia_hz=None):
        """
        Configura el canal de PWM y lo deja en ciclo de trabajo cero.

        Parametros
        ----------
        numero_pin : int
            GPIO del ESP32 con capacidad de salida.
        frecuencia_hz : int, opcional
            Frecuencia de la portadora. Si se omite, config.PWM_FRECUENCIA_HZ
            (1000 Hz), muy por encima del umbral de fusion de parpadeo del ojo.

        Retorna
        -------
        None

        Excepciones
        -----------
        ValueError
            Si el GPIO indicado es de solo entrada.
        """
        if 34 <= numero_pin <= 39:
            raise ValueError(
                "GPIO {} es de solo entrada y no puede generar PWM".format(numero_pin)
            )
        frecuencia = frecuencia_hz if frecuencia_hz is not None else config.PWM_FRECUENCIA_HZ
        self._pwm = PWM(Pin(numero_pin), freq=frecuencia)
        self._pwm.duty_u16(0)

    def escribir(self, valor_0_255):
        """
        Aplica una intensidad expresada en el rango MODBus de 0 a 255.

        Parametros
        ----------
        valor_0_255 : int
            Intensidad deseada. Los valores fuera de rango se acotan en lugar de
            provocar un error: un Holding Register puede recibir cualquier valor
            de 16 bits desde el bus (por ejemplo, un maestro mal configurado
            escribiendo 5000), y el esclavo debe degradar de forma segura en vez
            de reiniciarse por una excepcion no atrapada.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.

        Ejemplo de uso
        --------------
        >>> led = SalidaPWM(config.PIN_LED_PWM)
        >>> led.escribir(128)   # media intensidad
        """
        valor = int(valor_0_255)
        if valor < 0:
            valor = 0
        elif valor > config.PWM_MAXIMO:
            valor = config.PWM_MAXIMO

        self._pwm.duty_u16(valor * self._FACTOR_A_U16)

    def apagar(self):
        """
        Lleva la salida a ciclo de trabajo cero.

        Se usa como estado seguro ante una falla de comunicacion prolongada, si
        se decide que el maestro apague sus replicadores cuando pierde contacto
        con el esclavo.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._pwm.duty_u16(0)


def adc_a_pwm(valor_adc):
    """
    Convierte una lectura del ADC (0-4095) al rango de PWM de MODBus (0-255).

    Es la unica conversion de escala del sistema y por eso vive en un solo lugar,
    con su factor documentado en docs/mapa-registros.md §5.2. El desplazamiento
    de 4 bits equivale a dividir por 16 y es exacto en ambos extremos del rango
    (4095 >> 4 = 255), sin recurrir a punto flotante.

    Parametros
    ----------
    valor_adc : int
        Lectura cruda del ADC, en el rango 0 a config.ADC_MAXIMO.

    Retorna
    -------
    int
        Valor equivalente en el rango 0 a config.PWM_MAXIMO.

    Excepciones
    -----------
    Ninguna. Los valores fuera de rango se acotan.

    Ejemplo de uso
    --------------
    >>> adc_a_pwm(4095)
    255
    >>> adc_a_pwm(0)
    0
    >>> adc_a_pwm(2048)
    128
    """
    if valor_adc <= 0:
        return 0
    if valor_adc >= config.ADC_MAXIMO:
        return config.PWM_MAXIMO
    return valor_adc >> config.DESPLAZAMIENTO_ADC_A_PWM
