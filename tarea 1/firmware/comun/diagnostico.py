"""
diagnostico.py  (MODULO COMUN A LOS TRES NODOS)
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-17
Version: 1.0

Descripcion general
-------------------
Capa de observabilidad del sistema MODBus RTU. Provee un registrador por niveles
y utilidades de deteccion de cambios, pensado para depurar la comunicacion entre
los tres nodos desde la consola de Thonny.

Por que un modulo y no print() sueltos
--------------------------------------
Tres motivos concretos, y ninguno es estetico:

  1. COSTO CONTROLADO. Un print() por la consola USB de Thonny cuesta del orden
     de 1 a 3 ms. El ciclo de sondeo dura 161 ms y el esclavo debe responder
     dentro de los 300 ms de timeout del maestro: veinte prints por iteracion
     alcanzan para provocar los mismos timeouts que se intentan diagnosticar.
     Instrumentar un sistema de tiempo real y alterar su comportamiento al
     hacerlo es el error clasico de depuracion (efecto sonda). Los niveles
     permiten subir el detalle solo donde hace falta y volver a bajarlo.

  2. CORRELACION ENTRE LOS TRES NODOS. Cada linea lleva marca de tiempo relativa
     al arranque del nodo y un prefijo que lo identifica. Con tres consolas de
     Thonny abiertas en paralelo, eso es lo que permite decir "el maestro emitio
     la peticion en t=12.480 y el esclavo 2 no registro nada", que es una
     afirmacion falsable, en lugar de "a veces no anda".

  3. REGISTRO POR CAMBIO, NO POR ITERACION. El lazo del esclavo gira cientos de
     veces por segundo. Imprimir el estado en cada vuelta produce un torrente
     ilegible; imprimir SOLO cuando el valor cambia produce exactamente la traza
     de un parpadeo, con su instante y su frecuencia. La clase DetectorDeCambio
     existe para eso.

Niveles disponibles
-------------------
    0  SILENCIO   Nada. Operacion normal, maxima velocidad.
    1  ERROR      Solo fallos de transaccion y excepciones.
    2  AVISO      + cambios de estado relevantes (seleccion, degradacion).
    3  INFO       + resumen periodico y cambios de valor en las salidas.
    4  DETALLE    + una linea por transaccion MODBus.
    5  TRAMA      + volcado hexadecimal de las tramas. MUY lento: altera el
                  comportamiento temporal del bus. Usar solo en capturas cortas.

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32 (modulo time).
- Modulo local: config.py.
"""

import time

import config


# =============================================================================
# 1. NIVELES
# =============================================================================

SILENCIO = 0
ERROR = 1
AVISO = 2
INFO = 3
DETALLE = 4
TRAMA = 5

#: Etiqueta de una sola letra por nivel. Se usa una letra y no la palabra
#: completa para que la columna no desplace el resto de la linea: con tres
#: consolas en paralelo, la alineacion vertical es lo que hace legible la traza.
_ETIQUETA = {
    ERROR: "E",
    AVISO: "A",
    INFO: "I",
    DETALLE: "D",
    TRAMA: "T",
}


# =============================================================================
# 2. REGISTRADOR
# =============================================================================

class Registrador:
    """
    Emisor de lineas de traza con nivel, marca de tiempo y prefijo de nodo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Unico punto por el que sale informacion de depuracion de un nodo. Centralizar
    la salida permite cambiar el formato, el destino o el costo de la traza en un
    solo lugar, y garantiza que las tres consolas produzcan lineas comparables.

    Atributos principales
    ---------------------
    _prefijo : str
        Identificacion del nodo, por ejemplo "MAESTRO" o "ESCLAVO 2".
    _nivel : int
        Umbral activo. Una linea se emite solo si su nivel es menor o igual.
    _origen_ms : int
        Marca de tiempo del arranque, para expresar los instantes en forma
        relativa. Se usa una referencia propia y no ticks_ms() crudo porque el
        contador absoluto de MicroPython no tiene significado para el lector.

    Relaciones con otras clases
    ---------------------------
    Lo consumen maestro/main.py y esclavo/main.py. DetectorDeCambio se usa junto
    a el pero no depende de el.
    """

    def __init__(self, prefijo, nivel=None):
        """
        Parametros
        ----------
        prefijo : str
            Nombre del nodo que aparece en cada linea.
        nivel : int, opcional
            Umbral de detalle. Si es None se toma config.NIVEL_LOG.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._prefijo = prefijo
        self._nivel = config.NIVEL_LOG if nivel is None else nivel
        self._origen_ms = time.ticks_ms()

    # -- Consulta y control ---------------------------------------------------

    def habilitado(self, nivel):
        """
        Indica si una linea de ese nivel se emitiria.

        Sirve para evitar el costo de construir el mensaje cuando no se va a
        imprimir: en MicroPython, format() sobre una cadena larga cuesta mas que
        la comparacion, y en el lazo del esclavo esa diferencia es medible.

        Parametros
        ----------
        nivel : int
            Nivel de la linea que se pretende emitir.

        Retorna
        -------
        bool

        Excepciones
        -----------
        Ninguna.
        """
        return nivel <= self._nivel

    def fijar_nivel(self, nivel):
        """
        Cambia el umbral en caliente, desde el REPL de Thonny.

        Permite arrancar el sistema en nivel bajo, dejarlo estabilizar y subir el
        detalle justo cuando se reproduce la falla, sin reiniciar el nodo y sin
        perder el estado que se estaba investigando.

        Parametros
        ----------
        nivel : int
            Nuevo umbral, de SILENCIO a TRAMA.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._nivel = nivel

    def fijar_prefijo(self, prefijo):
        """
        Cambia la identificacion del nodo en la traza.

        Existe porque el esclavo no conoce su Unit ID hasta haber leido el jumper
        en el arranque, y el registrador debe construirse antes para que la
        subclase del servidor MODBus pueda usarlo. Se expone como metodo en lugar
        de escribir el atributo desde afuera para no acoplar el llamador a la
        representacion interna de la clase.

        Parametros
        ----------
        prefijo : str
            Nueva identificacion, por ejemplo "ESCLAVO 2".

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._prefijo = prefijo

    def marca_ms(self):
        """
        Milisegundos transcurridos desde la construccion del registrador.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int

        Excepciones
        -----------
        Ninguna.
        """
        return time.ticks_diff(time.ticks_ms(), self._origen_ms)

    # -- Emision --------------------------------------------------------------

    def _emitir(self, nivel, mensaje):
        """
        Imprime una linea ya formateada, con marca de tiempo y prefijo.

        Formato: ``[  12.480] E [MAESTRO] texto``

        El tiempo se imprime como segundos con tres decimales y ancho fijo para
        que las columnas queden alineadas y sea posible comparar visualmente dos
        consolas puestas una al lado de la otra.

        Parametros
        ----------
        nivel : int
            Nivel de la linea.
        mensaje : str
            Texto ya construido.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if nivel > self._nivel:
            return
        t = self.marca_ms()
        print("[{:>6}.{:03d}] {} [{}] {}".format(
            t // 1000, t % 1000, _ETIQUETA.get(nivel, "?"), self._prefijo, mensaje,
        ))

    def error(self, mensaje):
        """Emite una linea de nivel ERROR. Ver _emitir()."""
        self._emitir(ERROR, mensaje)

    def aviso(self, mensaje):
        """Emite una linea de nivel AVISO. Ver _emitir()."""
        self._emitir(AVISO, mensaje)

    def info(self, mensaje):
        """Emite una linea de nivel INFO. Ver _emitir()."""
        self._emitir(INFO, mensaje)

    def detalle(self, mensaje):
        """Emite una linea de nivel DETALLE. Ver _emitir()."""
        self._emitir(DETALLE, mensaje)

    def trama(self, sentido, datos):
        """
        Vuelca una trama en hexadecimal, con su sentido y longitud.

        Parametros
        ----------
        sentido : str
            "TX" o "RX", desde el punto de vista del nodo que registra.
        datos : bytes | bytearray | None
            Contenido de la trama. None se representa como ausencia de respuesta,
            que es informacion en si misma: distingue un timeout de una trama
            corrupta.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if TRAMA > self._nivel:
            return
        if not datos:
            self._emitir(TRAMA, "{} (sin datos)".format(sentido))
            return
        self._emitir(TRAMA, "{} {:2d}B  {}".format(
            sentido, len(datos), hexa(datos),
        ))

    def titulo(self, texto):
        """
        Imprime un encabezado enmarcado, sin marca de tiempo.

        Se usa una sola vez por arranque, para separar visualmente las corridas
        en el historial de la consola de Thonny.

        Parametros
        ----------
        texto : str
            Titulo a enmarcar.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        print("=" * 66)
        print(texto)
        print("=" * 66)


# =============================================================================
# 3. UTILIDADES
# =============================================================================

def hexa(datos):
    """
    Convierte una secuencia de bytes a texto hexadecimal separado por espacios.

    Se escribe a mano en lugar de usar ubinascii.hexlify() porque la salida de
    esta ultima viene sin separadores y resulta ilegible para contar campos de
    una trama MODBus, que es justamente para lo que se la necesita.

    Parametros
    ----------
    datos : bytes | bytearray
        Secuencia a formatear.

    Retorna
    -------
    str
        Por ejemplo ``01 04 00 00 00 01 31 CA``.

    Excepciones
    -----------
    TypeError
        Si el argumento no es iterable de enteros.

    Ejemplo de uso
    --------------
    >>> hexa(b'\\x01\\x04')
    '01 04'
    """
    return " ".join("{:02X}".format(b) for b in datos)


def describir_trama(datos):
    """
    Interpreta los campos de una trama MODBus RTU y devuelve una descripcion.

    Es el complemento del volcado hexadecimal: el volcado permite verificar byte
    a byte, y esta descripcion permite leer de un vistazo a quien iba dirigida y
    que pedia. Detecta ademas las respuestas de excepcion, que son las que
    interesa distinguir de un timeout.

    Parametros
    ----------
    datos : bytes | bytearray | None
        Trama completa, incluido el CRC.

    Retorna
    -------
    str
        Descripcion legible, o un texto de diagnostico si la trama es demasiado
        corta para interpretarse.

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> describir_trama(b'\\x01\\x04\\x00\\x00\\x00\\x01\\x31\\xCA')
    'ID=1 FC=0x04 dir=0x0000 cant=1'
    """
    if not datos:
        return "sin trama"
    if len(datos) < 4:
        return "trama corta ({} B): {}".format(len(datos), hexa(datos))

    unit = datos[0]
    funcion = datos[1]

    # Bit 7 del codigo de funcion encendido: el esclavo respondio con excepcion.
    # Esta rama va primero porque una excepcion tiene un formato propio y no debe
    # interpretarse con el esquema de la funcion original.
    if funcion & 0x80:
        codigo = datos[2] if len(datos) > 2 else 0
        return "ID={} EXCEPCION a FC=0x{:02X} codigo={} ({})".format(
            unit, funcion & 0x7F, codigo, _EXCEPCIONES.get(codigo, "desconocida"),
        )

    if funcion in (0x01, 0x02, 0x03, 0x04) and len(datos) >= 8:
        direccion = (datos[2] << 8) | datos[3]
        cantidad = (datos[4] << 8) | datos[5]
        return "ID={} FC=0x{:02X} dir=0x{:04X} cant={}".format(
            unit, funcion, direccion, cantidad,
        )

    if funcion in (0x01, 0x02, 0x03, 0x04):
        # Respuesta: [ID][FC][conteo][datos...][CRC]
        conteo = datos[2]
        cuerpo = datos[3:3 + conteo]
        return "ID={} FC=0x{:02X} respuesta {}B: {}".format(
            unit, funcion, conteo, hexa(cuerpo),
        )

    if funcion in (0x05, 0x06) and len(datos) >= 8:
        direccion = (datos[2] << 8) | datos[3]
        valor = (datos[4] << 8) | datos[5]
        return "ID={} FC=0x{:02X} dir=0x{:04X} valor=0x{:04X} ({})".format(
            unit, funcion, direccion, valor, valor,
        )

    return "ID={} FC=0x{:02X} {}B: {}".format(unit, funcion, len(datos), hexa(datos))


#: Codigos de excepcion MODBus relevantes para este sistema. Se listan solo los
#: cuatro que la especificacion define como basicos, que son los unicos que puede
#: emitir un esclavo con este mapa de registros.
_EXCEPCIONES = {
    1: "funcion no soportada",
    2: "direccion invalida",
    3: "valor invalido",
    4: "fallo del dispositivo",
}


def clasificar_error(error):
    """
    Separa un fallo de transaccion en TIMEOUT, EXCEPCION o ERROR DE TRAMA.

    Es la distincion mas importante del diagnostico y la que orienta hacia donde
    mirar, porque cada clase apunta a una capa distinta del sistema:

      TIMEOUT   El esclavo no contesto. Problema de capa fisica, de direccion o
                de alimentacion: el nodo no escucho, no esta, o no pudo hablar.
      EXCEPCION El esclavo contesto rechazando la peticion. El nodo esta vivo y
                entiende el protocolo: el problema esta en la peticion (funcion
                o direccion), es decir, en la capa de aplicacion.
      TRAMA     Llego algo que no es una respuesta valida (CRC malo, longitud
                inesperada). Apunta a ruido en el bus o a colision de dos nodos
                transmitiendo a la vez.

    La libreria senaliza los tres casos como excepcion de Python, por lo que la
    clasificacion se hace sobre el texto del error. Es una heuristica, y se la
    documenta como tal: ante un texto no reconocido devuelve el original en vez
    de forzarlo dentro de una categoria.

    Parametros
    ----------
    error : Exception
        Excepcion capturada al ejecutar la transaccion.

    Retorna
    -------
    str
        "TIMEOUT", "EXCEPCION", "TRAMA" o el texto original del error.

    Excepciones
    -----------
    Ninguna.
    """
    texto = str(error).lower()
    if "timeout" in texto or "no data" in texto or "no response" in texto:
        return "TIMEOUT"
    if "exception" in texto or "error code" in texto or "illegal" in texto:
        return "EXCEPCION"
    if "crc" in texto or "invalid" in texto or "length" in texto:
        return "TRAMA"
    return str(error) if str(error) else type(error).__name__


# =============================================================================
# 4. DETECTOR DE CAMBIO
# =============================================================================

class DetectorDeCambio:
    """
    Emite una senal unicamente cuando el valor observado cambia.

    Responsabilidad dentro del sistema
    ----------------------------------
    Convertir un valor muestreado a alta frecuencia en una secuencia de eventos.
    Es la herramienta central para diagnosticar un parpadeo: un LED que titila no
    se ve en un volcado periodico del estado, pero si se ve como una sucesion de
    transiciones con su instante y su intervalo.

    Atributos principales
    ---------------------
    _anterior : objeto
        Ultimo valor observado. El centinela _SIN_VALOR distingue "todavia no
        observe nada" de "observe None", que son situaciones distintas.
    _umbral : int | float
        Variacion minima para considerar que un valor numerico cambio. Evita que
        el ruido de un conversor analogico genere un evento por muestra.
    transiciones : int
        Cantidad de cambios detectados desde la construccion. Es la metrica que
        cuantifica el parpadeo.

    Relaciones con otras clases
    ---------------------------
    Independiente. Se usa junto a Registrador pero no lo requiere.
    """

    _SIN_VALOR = object()

    def __init__(self, umbral=0):
        """
        Parametros
        ----------
        umbral : int | float, opcional
            Variacion minima para valores numericos. Con 0, cualquier diferencia
            cuenta como cambio.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._anterior = self._SIN_VALOR
        self._umbral = umbral
        self.transiciones = 0

    def cambio(self, valor):
        """
        Registra el valor y responde si constituye un cambio.

        Parametros
        ----------
        valor : objeto
            Valor observado en este instante.

        Retorna
        -------
        bool
            True si difiere del anterior mas alla del umbral, o si es la primera
            observacion.

        Excepciones
        -----------
        Ninguna.

        Ejemplo de uso
        --------------
        >>> d = DetectorDeCambio()
        >>> d.cambio(1), d.cambio(1), d.cambio(0)
        (True, False, True)
        """
        if self._anterior is self._SIN_VALOR:
            self._anterior = valor
            self.transiciones += 1
            return True

        if self._umbral and isinstance(valor, int) and isinstance(self._anterior, int):
            distinto = abs(valor - self._anterior) > self._umbral
        else:
            distinto = valor != self._anterior

        if distinto:
            self._anterior = valor
            self.transiciones += 1
        return distinto

    @property
    def valor(self):
        """
        Ultimo valor observado, o None si todavia no se observo ninguno.

        Retorna
        -------
        objeto
        """
        return None if self._anterior is self._SIN_VALOR else self._anterior


# =============================================================================
# 5. ENTRADA DIGITAL CONFIRMADA
# =============================================================================

class EntradaConfirmada:
    """
    Lector de una entrada digital que solo acepta un estado tras confirmarlo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Eliminar los glitches de una entrada digital muestreada de forma esporadica,
    sin recurrir a una espera bloqueante.

    Por que hace falta
    ------------------
    El selector de esclavo del maestro se muestrea UNA vez por ciclo de sondeo.
    Un unico pulso espurio en el instante exacto del muestreo desvia las cuatro
    transacciones de ese ciclo al esclavo equivocado. El pull-up interno del
    ESP32 es de unos 45 kOhm, valor alto: un cable dupont de 20 o 30 cm tendido
    en paralelo al bus RS-485 acopla capacitivamente lo suficiente como para que
    eso ocurra. Exigir N lecturas consecutivas iguales antes de aceptar un cambio
    convierte ese pulso aislado en un evento descartado.

    El criterio es el mismo de un filtro de entradas de PLC: el estado no se
    toma de una muestra sino de una ventana de muestras coincidentes.

    Atributos principales
    ---------------------
    _pin : machine.Pin
        Entrada fisica, configurada con pull-up.
    _confirmaciones : int
        Muestras consecutivas iguales necesarias para aceptar un cambio.
    _estable : int
        Estado aceptado actualmente. Es el que devuelve leer().
    _candidato : int
        Estado distinto observado, todavia sin confirmar.
    _repeticiones : int
        Veces consecutivas que se observo el candidato.
    rechazos : int
        Cantidad de cambios candidatos que no llegaron a confirmarse. Es la
        medida directa del ruido presente en la entrada: si crece, el problema
        esta en el cableado del selector y no en el bus.

    Relaciones con otras clases
    ---------------------------
    Envuelve un machine.Pin ya construido.
    """

    def __init__(self, pin, confirmaciones=None):
        """
        Parametros
        ----------
        pin : machine.Pin
            Entrada ya configurada como IN con PULL_UP.
        confirmaciones : int, opcional
            Muestras coincidentes exigidas. Si es None se toma
            config.CONFIRMACIONES_SELECTOR.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._pin = pin
        self._confirmaciones = (
            config.CONFIRMACIONES_SELECTOR if confirmaciones is None else confirmaciones
        )
        self._estable = pin.value()
        self._candidato = self._estable
        self._repeticiones = 0
        self.rechazos = 0

    def leer(self):
        """
        Muestrea la entrada y devuelve el estado confirmado.

        Toma varias muestras seguidas separadas por un milisegundo en lugar de
        una sola. El costo es de pocos milisegundos por ciclo de sondeo, frente a
        un periodo de 200 ms, y elimina la clase entera de fallos por pulso
        aislado sin necesidad de interrupciones ni de temporizadores.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            0 o 1, el estado confirmado.

        Excepciones
        -----------
        Ninguna.
        """
        for _ in range(self._confirmaciones):
            muestra = self._pin.value()
            if muestra == self._estable:
                # Coincide con lo aceptado: cualquier candidato pendiente era un
                # glitch, y se descarta.
                if self._repeticiones:
                    self.rechazos += 1
                self._candidato = self._estable
                self._repeticiones = 0
            elif muestra == self._candidato:
                self._repeticiones += 1
                if self._repeticiones >= self._confirmaciones:
                    self._estable = self._candidato
                    self._repeticiones = 0
            else:
                self._candidato = muestra
                self._repeticiones = 1
            time.sleep_ms(1)

        return self._estable


# =============================================================================
# 6. CONTADOR DE TRANSACCIONES POR ESCLAVO
# =============================================================================

class EstadisticaEsclavo:
    """
    Acumula el resultado de las transacciones dirigidas a un esclavo concreto.

    Responsabilidad dentro del sistema
    ----------------------------------
    Permitir afirmaciones del tipo "el Esclavo 2 pierde el 18 % de las tramas y
    el Esclavo 1 ninguna". Un contador global no distingue esos casos, y esa
    distincion es la que separa un problema de un nodo de un problema del bus:
    si ambos esclavos fallan por igual, el sospechoso es el medio compartido; si
    falla uno solo, el sospechoso es ese nodo.

    Atributos principales
    ---------------------
    intentos, exitos : int
        Transacciones emitidas y completadas.
    timeouts, excepciones, errores_trama : int
        Fallos desglosados segun clasificar_error().
    peor_racha : int
        Maxima cantidad de fallos consecutivos observada. Un valor alto con una
        tasa de error baja indica una falla en rafagas, tipica de interferencia;
        una tasa alta con racha baja indica una perdida uniforme.

    Relaciones con otras clases
    ---------------------------
    La usa el maestro, una instancia por Unit ID.
    """

    def __init__(self):
        """Inicializa todos los contadores en cero."""
        self.intentos = 0
        self.exitos = 0
        self.timeouts = 0
        self.excepciones = 0
        self.errores_trama = 0
        self.peor_racha = 0
        self._racha = 0

    def registrar(self, clase=None):
        """
        Contabiliza una transaccion.

        Parametros
        ----------
        clase : str | None
            None si fue exitosa; en caso contrario, la salida de
            clasificar_error().

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self.intentos += 1
        if clase is None:
            self.exitos += 1
            self._racha = 0
            return

        self._racha += 1
        if self._racha > self.peor_racha:
            self.peor_racha = self._racha

        if clase == "TIMEOUT":
            self.timeouts += 1
        elif clase == "EXCEPCION":
            self.excepciones += 1
        else:
            self.errores_trama += 1

    def resumen(self):
        """
        Devuelve una linea con el estado acumulado.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        str

        Excepciones
        -----------
        Ninguna.
        """
        if not self.intentos:
            return "sin transacciones"
        fallos = self.intentos - self.exitos
        # Se calcula con enteros y un desplazamiento decimal para no arrastrar
        # punto flotante, que en MicroPython es mas caro y aqui no aporta nada.
        por_mil = fallos * 1000 // self.intentos
        return "tx={} err={} ({}.{}%) timeout={} excep={} trama={} racha={}".format(
            self.intentos, fallos, por_mil // 10, por_mil % 10,
            self.timeouts, self.excepciones, self.errores_trama, self.peor_racha,
        )
