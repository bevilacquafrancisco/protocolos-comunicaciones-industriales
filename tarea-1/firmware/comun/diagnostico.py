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
# 0. VERSION DEL MODULO
# =============================================================================
#: Version de la interfaz que expone este modulo. Se incrementa cada vez que se
#: agregan nombres de los que dependen los firmwares de los nodos.
#:
#: Existe porque el despliegue de este proyecto es manual y sobre TRES placas:
#: se copian cinco archivos a cada una desde Thonny, y olvidar uno es un error
#: frecuente y facil de cometer. Su sintoma por defecto es un ImportError o un
#: AttributeError en medio de un traceback que no dice cual es el archivo que
#: falta ni en que placa.
#:
#: Cada firmware declara la version minima que necesita y la comprueba ANTES de
#: importar nombres concretos, usando getattr con valor por defecto para que la
#: comprobacion funcione incluso contra una version tan vieja que ni siquiera
#: tenga esta constante. El resultado es un mensaje que dice exactamente que
#: archivo subir, en lugar de un error que hay que interpretar.
#:
#: Historial:
#:   1  Registrador, DetectorDeCambio, EntradaConfirmada, EstadisticaEsclavo
#:   2  ventana movil en EstadisticaEsclavo, porcentaje(), continuacion()
#:   3  CapturaTramas, UARTObservado, InstrumentacionBus, localizar_interfaz()
#:   4  InstrumentacionBus registra las ordenes de escritura recibidas
VERSION = 4


# =============================================================================
# 1. NIVELES
# =============================================================================

SILENCIO = 0
ERROR = 1
AVISO = 2
INFO = 3
DETALLE = 4
TRAMA = 5


# =============================================================================
# 1.b  LECTURA TOLERANTE DE LA CONFIGURACION
# =============================================================================
# Este modulo se estreno junto con una tanda de constantes nuevas en config.py.
# Subir uno de los dos archivos al ESP32 y olvidar el otro es un error de
# despliegue frecuente cuando hay tres placas, y su sintoma por defecto es un
# AttributeError en medio de un traceback que no dice que hacer.
#
# El criterio adoptado es el de cualquier sistema que lee configuracion externa:
# ante un parametro ausente se aplica un valor por defecto seguro y se INFORMA
# con claridad, en lugar de abortar. Un nodo que arranca con la traza en su
# nivel por defecto es infinitamente mas util que un nodo que no arranca.
#
# Se informa una sola vez por parametro para no repetir el aviso en cada lectura.

_FALTANTES = []


def opcion(nombre, por_defecto):
    """
    Lee una constante de config.py, con valor por defecto si no existe.

    Parametros
    ----------
    nombre : str
        Nombre de la constante en config.py, por ejemplo "NIVEL_LOG".
    por_defecto : objeto
        Valor a usar si la constante no esta definida.

    Retorna
    -------
    objeto
        El valor de config, o por_defecto si falta.

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> opcion("NIVEL_LOG", INFO)
    3
    """
    try:
        return getattr(config, nombre)
    except AttributeError:
        if nombre not in _FALTANTES:
            _FALTANTES.append(nombre)
            print("[DIAGNOSTICO] config.{} no esta definido; se usa {}. "
                  "Falta subir el config.py actualizado a esta placa.".format(
                      nombre, por_defecto))
        return por_defecto


def verificar_config():
    """
    Comprueba que config.py traiga las constantes que exige esta version.

    Se invoca desde el arranque de cada nodo. Convierte un fallo de despliegue en
    un mensaje accionable emitido en el instante correcto -antes de que el nodo
    empiece a operar- en lugar de una excepcion a mitad de la ejecucion.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    list
        Nombres de las constantes ausentes. Lista vacia si esta todo en orden.

    Excepciones
    -----------
    Ninguna.
    """
    requeridas = (
        "NIVEL_LOG",
        "PERIODO_RESUMEN_MS",
        "REINTENTOS_TRANSACCION",
        "MS_PARA_DECLARAR_AUSENTE",
        "CONFIRMACIONES_SELECTOR",
        "ZONA_MUERTA_PWM",
    )
    ausentes = [n for n in requeridas if not hasattr(config, n)]
    if ausentes:
        print("=" * 66)
        print("AVISO: config.py en esta placa es de una version anterior.")
        print("Faltan: {}".format(", ".join(ausentes)))
        print("Subir firmware/comun/config.py a la raiz del ESP32 y reiniciar")
        print("con Ctrl+D. Mientras tanto se usan valores por defecto.")
        print("=" * 66)
    return ausentes


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
        self._nivel = opcion("NIVEL_LOG", INFO) if nivel is None else nivel
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

    def continuacion(self, nivel, mensaje, sangria=3):
        """
        Emite una linea subordinada a la anterior, alineada y sin encabezado.

        Un reporte de varias lineas que repite marca de tiempo, nivel y nombre
        del nodo en cada una gasta 25 columnas por linea en informacion que ya
        se leyo. Con tres ventanas de Thonny dispuestas en paralelo -que es la
        forma de trabajo recomendada para correlacionar los tres nodos- cada
        ventana ronda las 90 columnas, y esas 25 son la diferencia entre una
        tabla legible y un texto que se envuelve y pierde toda alineacion.

        La sangria es deliberadamente corta y no alineada bajo el encabezado:
        alinear habria consumido las mismas 25 columnas que se quieren ahorrar.
        Tres espacios bastan para que se lea como subordinada a la linea
        anterior.

        Parametros
        ----------
        nivel : int
            Nivel de la linea, para respetar el mismo filtrado que _emitir().
        mensaje : str
            Texto ya construido.
        sangria : int, opcional
            Espacios de indentacion.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if nivel > self._nivel:
            return
        print(" " * sangria + mensaje)

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


def porcentaje(parte, total):
    """
    Formatea una proporcion como porcentaje con un decimal.

    Se calcula con aritmetica entera y un desplazamiento decimal en lugar de
    punto flotante: en MicroPython el flotante es mas caro y aqui no aporta
    precision util.

    Parametros
    ----------
    parte : int
        Numerador.
    total : int
        Denominador. Si es cero se devuelve un guion, porque una proporcion sin
        observaciones no vale cero: es indefinida, y mostrarla como 0.0% seria
        afirmar algo que no se midio.

    Retorna
    -------
    str
        Por ejemplo "11.6%", o "-" si no hubo observaciones.

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> porcentaje(239, 2046)
    '11.6%'
    """
    if not total:
        return "-"
    por_mil = parte * 1000 // total
    return "{}.{}%".format(por_mil // 10, por_mil % 10)


#: Nombre de cada codigo de funcion MODBus. Se listan los ocho de uso corriente
#: sobre linea serie; los seis primeros son los que emplea este trabajo.
NOMBRE_FUNCION = {
    0x01: "Read Coils",
    0x02: "Read Discrete Inputs",
    0x03: "Read Holding Registers",
    0x04: "Read Input Registers",
    0x05: "Write Single Coil",
    0x06: "Write Single Register",
    0x0F: "Write Multiple Coils",
    0x10: "Write Multiple Registers",
}


def nombre_funcion(codigo):
    """
    Traduce un codigo de funcion MODBus a su nombre segun la especificacion.

    Parametros
    ----------
    codigo : int
        Codigo de funcion, con o sin el bit de excepcion.

    Retorna
    -------
    str

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> nombre_funcion(0x04)
    'Read Input Registers'
    """
    return NOMBRE_FUNCION.get(codigo & 0x7F, "funcion 0x{:02X}".format(codigo & 0x7F))


def describir_trama(datos, es_peticion=None):
    """
    Interpreta los campos de una trama MODBus RTU y devuelve una descripcion.

    Es el complemento del volcado hexadecimal: el volcado permite verificar byte
    a byte, y esta descripcion permite leer de un vistazo a quien iba dirigida,
    que funcion solicitaba y con que valor. Detecta ademas las respuestas de
    excepcion, que son las que interesa distinguir de un timeout.

    Sobre el parametro es_peticion
    ------------------------------
    En MODBus RTU, peticion y respuesta **comparten la estructura de cabecera**:
    ambas empiezan con direccion y codigo de funcion. Para una lectura, la
    peticion lleva direccion inicial y cantidad, mientras que la respuesta lleva
    un conteo de bytes y los datos. Sin saber el sentido, distinguirlas exige
    adivinar por la longitud, y esa heuristica falla en los casos de borde.

    Como cada nodo SI conoce el sentido -el maestro pregunta y recibe, el esclavo
    recibe y contesta-, se pasa el dato en lugar de deducirlo. Es la diferencia
    entre una descripcion correcta y una plausible.

    Parametros
    ----------
    datos : bytes | bytearray | None
        Trama completa, incluido el CRC.
    es_peticion : bool | None, opcional
        True si la trama es una peticion maestro -> esclavo, False si es una
        respuesta, None para deducirlo por longitud (menos fiable).

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
    >>> describir_trama(b'\x01\x04\x00\x00\x00\x01\x31\xCA', True)
    'E1 FC=0x04 Read Input Registers  dir=0x0000 n=1'
    """
    if not datos:
        return "sin trama"
    if len(datos) < 4:
        return "trama corta ({} B): {}".format(len(datos), hexa(datos))

    unit = datos[0]
    funcion = datos[1]
    quien = "E{}".format(unit) if unit else "BROADCAST"

    # Bit 7 del codigo de funcion encendido: el esclavo respondio con excepcion.
    # Esta rama va primero porque una excepcion tiene formato propio y no debe
    # interpretarse con el esquema de la funcion original.
    if funcion & 0x80:
        codigo = datos[2] if len(datos) > 2 else 0
        return "{} EXCEPCION a FC=0x{:02X} {}  codigo={} ({})".format(
            quien, funcion & 0x7F, nombre_funcion(funcion), codigo,
            _EXCEPCIONES.get(codigo, "desconocida"),
        )

    etiqueta = "{} FC=0x{:02X} {}".format(quien, funcion, nombre_funcion(funcion))

    # Las funciones de escritura simple tienen eco identico: peticion y respuesta
    # son la misma trama, de modo que el sentido no altera la interpretacion.
    if funcion in (0x05, 0x06) and len(datos) >= 8:
        direccion = (datos[2] << 8) | datos[3]
        valor = (datos[4] << 8) | datos[5]
        if funcion == 0x05:
            legible = "ON" if valor == 0xFF00 else ("OFF" if valor == 0x0000 else "invalido")
            return "{}  dir=0x{:04X} valor=0x{:04X} ({})".format(
                etiqueta, direccion, valor, legible,
            )
        return "{}  dir=0x{:04X} valor={}".format(etiqueta, direccion, valor)

    if funcion in (0x01, 0x02, 0x03, 0x04):
        if es_peticion is None:
            # Sin conocer el sentido: una peticion de lectura mide siempre 8
            # bytes exactos. Es una heuristica, y se la usa solo como respaldo.
            es_peticion = len(datos) == 8

        if es_peticion and len(datos) >= 8:
            direccion = (datos[2] << 8) | datos[3]
            cantidad = (datos[4] << 8) | datos[5]
            return "{}  dir=0x{:04X} n={}".format(etiqueta, direccion, cantidad)

        # Respuesta: [ID][FC][conteo][datos...][CRC]
        conteo = datos[2]
        cuerpo = datos[3:3 + conteo]
        if funcion in (0x03, 0x04) and conteo >= 2:
            valores = [(cuerpo[i] << 8) | cuerpo[i + 1]
                       for i in range(0, conteo - 1, 2)]
            texto = ", ".join(str(v) for v in valores)
        elif funcion in (0x01, 0x02) and conteo >= 1:
            texto = "bits=0b{:08b}".format(cuerpo[0])
        else:
            texto = hexa(cuerpo)
        return "{}  -> {}".format(etiqueta, texto)

    return "{}  {}B: {}".format(etiqueta, len(datos), hexa(datos))


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
            opcion("CONFIRMACIONES_SELECTOR", 3)
            if confirmaciones is None else confirmaciones
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
        """Inicializa todos los contadores, acumulados y de ventana, en cero."""
        # --- Acumulado desde el arranque ------------------------------------
        self.intentos = 0
        self.exitos = 0
        self.timeouts = 0
        self.excepciones = 0
        self.errores_trama = 0
        self.peor_racha = 0
        self._racha = 0

        # --- Ventana: lo ocurrido desde el reporte anterior ------------------
        # El acumulado responde "como se comporto este nodo en toda la corrida";
        # la ventana responde "como se esta comportando AHORA". Son preguntas
        # distintas, y confundirlas induce a error: un nodo que fallo mucho hace
        # cinco minutos y desde entonces funciona bien muestra un acumulado
        # alarmante junto a una ventana impecable, y es la ventana la que
        # describe el estado presente del sistema.
        self.v_intentos = 0
        self.v_exitos = 0
        self.v_peor_racha = 0

    def registrar(self, clase=None):
        """
        Contabiliza una transaccion, en el acumulado y en la ventana.

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
        self.v_intentos += 1

        if clase is None:
            self.exitos += 1
            self.v_exitos += 1
            self._racha = 0
            return

        self._racha += 1
        if self._racha > self.peor_racha:
            self.peor_racha = self._racha
        if self._racha > self.v_peor_racha:
            self.v_peor_racha = self._racha

        if clase == "TIMEOUT":
            self.timeouts += 1
        elif clase == "EXCEPCION":
            self.excepciones += 1
        else:
            self.errores_trama += 1

    def resumen(self):
        """
        Devuelve una linea con el estado ACUMULADO desde el arranque.

        El desglose por clase se abrevia como t/e/c (timeout, excepcion, error
        de trama) para que la linea entre completa en el ancho del Shell de
        Thonny: una linea que se corta o se envuelve deja de ser comparable con
        la de al lado, que es justamente para lo que se la imprime.

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
        linea = "{}tx {}err ({})".format(
            self.intentos, fallos, porcentaje(fallos, self.intentos),
        )

        # El desglose y la peor racha solo se imprimen si hubo algun fallo, y
        # dentro del desglose solo las clases distintas de cero. Un nodo sano
        # produce una linea corta y limpia, y el ojo detecta de inmediato cual
        # de los dos esclavos trae informacion adicional. Una linea que siempre
        # muestra "t/e/c=0/0/0 racha=0" gasta ancho en decir que no hay nada que
        # mirar, y en una consola angosta ese ancho se paga con envolvimiento de
        # linea y perdida de alineacion.
        if fallos:
            clases = []
            if self.timeouts:
                clases.append("{}to".format(self.timeouts))
            if self.excepciones:
                clases.append("{}ex".format(self.excepciones))
            if self.errores_trama:
                clases.append("{}tr".format(self.errores_trama))
            linea += " " + "/".join(clases) + " r={}".format(self.peor_racha)
        return linea

    def resumen_ventana(self):
        """
        Devuelve una linea con lo ocurrido desde el reporte anterior.

        Distingue explicitamente el caso "no se sondeo este nodo" del caso "se
        sondeo y no fallo". Sin esa distincion, un esclavo no seleccionado
        aparece con cero errores y se confunde con un esclavo sano, que es
        exactamente la ambiguedad que esta ventana viene a resolver.

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
        if not self.v_intentos:
            return "sin sondeo"
        fallos = self.v_intentos - self.v_exitos
        return "{}tx {}err ({})".format(
            self.v_intentos, fallos, porcentaje(fallos, self.v_intentos),
        )

    def cerrar_ventana(self):
        """
        Reinicia los contadores de ventana tras emitir el reporte.

        Se invoca desde el maestro inmediatamente despues de imprimir, de modo
        que cada linea de ventana describa exactamente el intervalo transcurrido
        entre dos reportes y no un acumulado parcial.

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
        self.v_intentos = 0
        self.v_exitos = 0
        self.v_peor_racha = 0

    def reiniciar(self):
        """
        Pone a cero todos los contadores, acumulados y de ventana.

        Pensado para invocarse desde el REPL de Thonny al comenzar una medicion:
        permite separar la etapa de puesta a punto -donde los errores son
        esperables- de la corrida que se va a documentar en el informe, sin
        reiniciar el nodo y sin perder el estado del bus.

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
        self.__init__()


# =============================================================================
# 7. CAPTURA DE TRAMAS
# =============================================================================

#: Columnas que ocupa el prefijo de una linea de volcado:
#: 7 del salto + 1 + 6 del sentido + 1 + 3 del tamano + 3 del separador " | ".
#: Se define como constante y no como literal para que la segunda linea siga
#: alineada si el formato de la primera cambia.
_SANGRIA_DESCRIPCION = 21


class CapturaTramas:
    """
    Almacena en memoria las ultimas tramas vistas por este nodo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Permitir observar el trafico del bus SIN alterarlo. Es la diferencia entre
    un analizador y una sonda que perturba lo que mide.

    Por que no imprimir directamente
    --------------------------------
    Imprimir cada trama en el momento en que ocurre cuesta entre 1 y 3 ms por
    linea sobre la consola USB. Una transaccion genera dos tramas, el ciclo de
    sondeo tiene cuatro transacciones, y el esclavo debe contestar dentro de los
    300 ms de timeout del maestro: la traza inmediata consume el presupuesto
    temporal del propio protocolo y produce timeouts que no existen sin ella.
    Es el efecto sonda en su forma mas clara.

    Registrar en un buffer circular cuesta, en cambio, una copia de ocho bytes y
    un append: microsegundos. El costo de imprimir se paga una sola vez, cuando
    se pide el volcado, y en ese momento ya no importa perturbar el bus porque
    el dato que interesa ya esta guardado.

    Estrategia de buffer circular
    -----------------------------
    Se conservan las N ultimas tramas y se descartan las viejas. Para diagnostico
    es exactamente lo que se necesita: cuando algo falla, lo que explica el fallo
    es lo que ocurrio inmediatamente antes, no lo que paso hace cinco minutos.
    Ademas acota el uso de memoria, que en un ESP32 con MicroPython no es un
    detalle menor.

    Atributos principales
    ---------------------
    capacidad : int
        Cantidad maxima de tramas conservadas.
    total : int
        Tramas registradas desde el inicio, incluidas las ya descartadas. Sirve
        para saber cuanto trafico paso aunque el buffer solo muestre el final.

    Relaciones con otras clases
    ---------------------------
    La alimentan UARTObservado (transmision) y los metodos _uart_read_frame de
    maestro y esclavo (recepcion). La consume Registrador al volcar.
    """

    def __init__(self, capacidad=24):
        """
        Parametros
        ----------
        capacidad : int, opcional
            Tramas a conservar. Con 24 se cubren tres ciclos de sondeo
            completos, suficiente para ver el contexto de un fallo.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self.capacidad = capacidad
        self.total = 0
        self._tramas = []

    def registrar(self, sentido, datos, es_peticion=None):
        """
        Guarda una trama con su instante, sentido y sentido logico.

        Parametros
        ----------
        sentido : str
            "TX" o "RX", desde el punto de vista de este nodo.
        datos : bytes | bytearray
            Contenido de la trama. Se copia, porque la libreria reutiliza sus
            buffers y guardar la referencia daria lecturas corrompidas al volcar.
        es_peticion : bool | None, opcional
            True si es una peticion maestro -> esclavo, False si es respuesta.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if not self.capacidad or not datos:
            return

        self.total += 1
        self._tramas.append((time.ticks_ms(), sentido, bytes(datos), es_peticion))
        if len(self._tramas) > self.capacidad:
            self._tramas.pop(0)

    def limpiar(self):
        """
        Vacia el buffer sin tocar el contador total.

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
        self._tramas = []

    def volcar(self, log, titulo="CAPTURA DE TRAMAS", limpiar=True):
        """
        Imprime el contenido del buffer en forma legible.

        Cada trama ocupa dos lineas: el volcado hexadecimal, que permite
        verificar byte a byte y contar campos, y la interpretacion, que permite
        leer de un vistazo que ocurrio. Se imprimen las dos porque cumplen
        funciones distintas: el hexadecimal es la evidencia, la interpretacion
        es la lectura, y para un informe hacen falta ambas.

        Se muestra ademas el intervalo respecto de la trama anterior. Ese numero
        es el que revela el comportamiento temporal: el tiempo de respuesta del
        esclavo, el silencio entre tramas y, cuando falta una respuesta, el hueco
        que dejo.

        Parametros
        ----------
        log : Registrador
            Registrador por el que se emite el volcado.
        titulo : str, opcional
            Encabezado del bloque.
        limpiar : bool, opcional
            Si vaciar el buffer despues de volcar. Por defecto si, para que dos
            volcados sucesivos no repitan las mismas tramas.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if not self._tramas:
            log.info("{}: sin tramas capturadas".format(titulo))
            return

        log.info("--- {} ({} de {} vistas) ---".format(
            titulo, len(self._tramas), self.total,
        ))

        # Anchos fijos para que las columnas queden alineadas entre tramas y la
        # segunda linea caiga justo bajo el hexadecimal de la primera. Una tabla
        # desalineada obliga a leer cada linea por separado, que es justo lo que
        # un volcado debe evitar.
        anterior = None
        for instante, sentido, datos, es_peticion in self._tramas:
            if anterior is None:
                salto = " " * 7
            else:
                salto = "{:+5d}ms".format(time.ticks_diff(instante, anterior))
            anterior = instante

            log.continuacion(INFO, "{} {:<6} {:2d}B | {}".format(
                salto, sentido, len(datos), hexa(datos),
            ))
            log.continuacion(INFO, "{}{}".format(
                " " * _SANGRIA_DESCRIPCION, describir_trama(datos, es_peticion),
            ))

        if limpiar:
            self.limpiar()


class UARTObservado:
    """
    Envoltorio de un UART que registra en una captura todo lo que transmite.

    Responsabilidad dentro del sistema
    ----------------------------------
    Observar el lado de la TRANSMISION, que de otro modo queda ciego.

    Por que hace falta
    ------------------
    La instrumentacion de recepcion se implementa extendiendo _uart_read_frame(),
    porque la libreria expone ese punto. Para la transmision no existe un punto
    equivalente estable: el nombre y la firma del metodo que escribe varian entre
    versiones de la libreria, y depender de ellos haria que la instrumentacion se
    rompiera con cualquier actualizacion.

    Interponerse en el objeto UART, en cambio, funciona con cualquier version,
    porque el UART es una interfaz de MicroPython y no de la libreria. Es el
    patron Proxy aplicado al punto de acoplamiento mas estable disponible.

    Todo lo que no sea write() se delega al UART real mediante __getattr__, de
    modo que la libreria no percibe diferencia alguna.

    Atributos principales
    ---------------------
    _uart : machine.UART
        Objeto real, al que se delega todo.
    _captura : CapturaTramas
        Destino de las tramas transmitidas.

    Relaciones con otras clases
    ---------------------------
    Sustituye al atributo _uart de las subclases del transceptor, tras la
    construccion de la clase base.
    """

    def __init__(self, uart, captura, es_peticion=None):
        """
        Parametros
        ----------
        uart : machine.UART
            UART real ya inicializado por la libreria.
        captura : CapturaTramas
            Buffer donde registrar lo transmitido.
        es_peticion : bool | None, opcional
            Sentido logico de lo que transmite este nodo: True en el maestro,
            que emite peticiones; False en el esclavo, que emite respuestas.
            Se fija por nodo y no por trama porque un maestro nunca responde y
            un esclavo nunca pregunta: es una propiedad del rol.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._uart = uart
        self._captura = captura
        self._es_peticion = es_peticion

    def write(self, datos):
        """
        Registra la trama y la entrega al UART real.

        Parametros
        ----------
        datos : bytes | bytearray
            Trama completa a transmitir.

        Retorna
        -------
        int
            Lo que devuelva el UART real: bytes escritos.

        Excepciones
        -----------
        Las que propague el UART real.
        """
        self._captura.registrar("TX", datos, self._es_peticion)
        return self._uart.write(datos)

    def __getattr__(self, nombre):
        """
        Delega en el UART real cualquier atributo no definido aqui.

        Se invoca solo cuando la busqueda normal falla, de modo que write() y los
        atributos propios no pasan por aca. read(), any() y flush() si.

        Parametros
        ----------
        nombre : str
            Atributo solicitado.

        Retorna
        -------
        objeto
            El atributo del UART real.

        Excepciones
        -----------
        AttributeError
            Si el UART real tampoco lo define.
        """
        return getattr(self._uart, nombre)


# =============================================================================
# 8. INSTRUMENTACION DE LA INTERFAZ SERIE
# =============================================================================

def localizar_interfaz(objeto):
    """
    Encuentra, dentro de un objeto de la libreria, el que realmente tiene el UART.

    Por que hace falta
    ------------------
    La libreria expone dos clases con roles distintos y jerarquia distinta:

      Serial      es la interfaz serie: tiene el UART y los metodos que leen y
                  escriben tramas. La usa el MAESTRO, que la extiende
                  directamente.
      ModbusRTU   es el servidor esclavo. NO extiende a Serial: la CONTIENE, en
                  un atributo interno. Es composicion, no herencia.

    La consecuencia practica es que extender ModbusRTU y sobrescribir sus metodos
    de lectura de trama no instrumenta nada: esos metodos viven en el objeto
    contenido, no en el que se extendio, y nunca llegan a invocarse. El sintoma es
    silencioso y enganoso -contadores que quedan en cero para siempre, sin ningun
    error- salvo que ademas se acceda a un atributo inexistente, que es lo que
    produce el AttributeError sobre _uart.

    Esta funcion resuelve el problema buscando el objeto correcto en lugar de
    suponerlo, y tolerando que el nombre del atributo cambie entre versiones de
    la libreria.

    Parametros
    ----------
    objeto : objeto
        Instancia de la libreria: Serial, ModbusRTU o una subclase de cualquiera.

    Retorna
    -------
    tuple(objeto, str)
        La interfaz que posee el UART y una descripcion de donde se la encontro,
        o (None, motivo) si no se la pudo ubicar.

    Excepciones
    -----------
    Ninguna.
    """
    if hasattr(objeto, "_uart"):
        return objeto, "el objeto mismo"

    # Nombres con los que las distintas versiones guardan la interfaz contenida.
    for nombre in ("_itf", "itf", "_serial", "serial"):
        contenido = getattr(objeto, nombre, None)
        if contenido is not None and hasattr(contenido, "_uart"):
            return contenido, "atributo {}".format(nombre)

    return None, "no se encontro ningun atributo con _uart"


def explorar(objeto):
    """
    Imprime los atributos de un objeto, para inspeccionarlo desde el REPL.

    Utilidad de ultimo recurso: si localizar_interfaz() falla porque una version
    de la libreria guarda el UART con otro nombre, esto permite averiguar cual es
    sin leer el codigo fuente de la libreria en la placa.

    Parametros
    ----------
    objeto : objeto
        Instancia a inspeccionar.

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> import diagnostico
    >>> diagnostico.explorar(cliente)
    """
    print("Tipo:", type(objeto))
    try:
        atributos = sorted(dir(objeto))
    except Exception:
        atributos = []
    print("Atributos:")
    for nombre in atributos:
        if nombre.startswith("__"):
            continue
        try:
            valor = getattr(objeto, nombre)
        except Exception:
            valor = "<no accesible>"
        if callable(valor):
            print("   {}()".format(nombre))
        else:
            print("   {} = {}".format(nombre, valor))


class InstrumentacionBus:
    """
    Observa el trafico de un nodo sin modificar la logica del protocolo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Conectar la captura de tramas a la interfaz serie real de un nodo,
    cualquiera sea la clase de la libreria que ese nodo utilice.

    Como funciona
    -------------
    Se aplica DESPUES de construir el objeto de la libreria, y actua por
    envoltura y no por herencia:

      - Reemplaza el UART por un UARTObservado, que registra la transmision.
      - Envuelve el metodo de lectura de trama, que registra la recepcion.

    Envolver en tiempo de ejecucion, en lugar de extender la clase, tiene una
    ventaja concreta en este caso: funciona igual sea cual sea la clase concreta
    y sin importar si el nodo hereda de la interfaz serie o la contiene. Es la
    diferencia entre una instrumentacion que anda en los tres nodos y una que
    anda solo en el maestro.

    Si no logra ubicar la interfaz, lo informa con claridad y el nodo sigue
    funcionando sin captura: la observabilidad es deseable, pero no al precio de
    impedir que el dispositivo opere.

    Atributos principales
    ---------------------
    tramas_recibidas, tramas_propias : int
        Contadores de recepcion. La diferencia entre ambos es el trafico dirigido
        a otros nodos, cuya presencia confirma que el filtrado por direccion
        funciona.
    activa : bool
        Si la instrumentacion llego a aplicarse.

    Relaciones con otras clases
    ---------------------------
    Usa CapturaTramas y UARTObservado. La aplican maestro/main.py y
    esclavo/main.py tras construir su objeto de la libreria.
    """

    def __init__(self, captura, log, unit_id=None, tx_es_peticion=None):
        """
        Parametros
        ----------
        captura : CapturaTramas
            Buffer donde registrar las tramas.
        log : Registrador
            Registrador del nodo, para informar el resultado.
        unit_id : int | None, opcional
            Direccion propia, para distinguir el trafico propio del ajeno. None
            en el maestro, que no tiene direccion.
        tx_es_peticion : bool | None, opcional
            True en el maestro (transmite peticiones), False en el esclavo
            (transmite respuestas).

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._captura = captura
        self._log = log
        self._unit_id = unit_id
        self._tx_es_peticion = tx_es_peticion
        self.tramas_recibidas = 0
        self.tramas_propias = 0
        self.activa = False

        #: Cantidad de ordenes de ESCRITURA dirigidas a este nodo, y el instante
        #: de la ultima. Se cuentan aparte de las lecturas porque son las unicas
        #: que pueden modificar las salidas.
        #:
        #: Sirven para evidenciar el tercer requisito de la Parte 3: que el
        #: esclavo no seleccionado mantenga su ultimo estado hasta recibir una
        #: nueva orden. Ese requisito se cumple por construccion -los registros
        #: MODBus conservan su valor mientras nadie los escriba- pero la consigna
        #: pide VERIFICARLO, y una propiedad que no se puede observar no esta
        #: verificada. Con estos contadores, la evidencia es directa: las salidas
        #: permanecen constantes mientras este contador no avanza.
        self.ordenes_escritura = 0
        self.ultima_orden_ms = time.ticks_ms()

    def aplicar(self, objeto):
        """
        Instrumenta el objeto de la libreria e informa el resultado.

        Parametros
        ----------
        objeto : objeto
            Instancia de Serial, ModbusRTU o subclase.

        Retorna
        -------
        bool
            True si se instrumento la transmision y la recepcion.

        Excepciones
        -----------
        Ninguna: cualquier fallo se informa y se devuelve False.
        """
        interfaz, donde = localizar_interfaz(objeto)
        if interfaz is None:
            self._log.error(
                "No se pudo instrumentar el bus ({}). El nodo funciona, pero sin "
                "captura de tramas. Ejecutar diagnostico.explorar(objeto) para "
                "averiguar donde guarda el UART esta version de la libreria."
                .format(donde)
            )
            return False

        try:
            interfaz._uart = UARTObservado(
                interfaz._uart, self._captura, self._tx_es_peticion,
            )
        except Exception as error:
            self._log.error("No se pudo envolver el UART: {}".format(error))
            return False

        if not hasattr(interfaz, "_uart_read_frame"):
            self._log.aviso(
                "Transmision instrumentada ({}), pero la interfaz no expone "
                "_uart_read_frame: no se registrara la recepcion.".format(donde)
            )
            self.activa = True
            return False

        original = interfaz._uart_read_frame

        def leer_trama(timeout=None):
            """Lee la trama con el metodo original y la registra."""
            trama = original(timeout)
            self._registrar_recepcion(trama)
            return trama

        interfaz._uart_read_frame = leer_trama
        self.activa = True
        self._log.info("Bus instrumentado ({}): TX y RX bajo observacion".format(donde))
        return True

    def ms_sin_ordenes(self):
        """
        Milisegundos transcurridos desde la ultima orden de escritura recibida.

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
        return time.ticks_diff(time.ticks_ms(), self.ultima_orden_ms)

    def _registrar_recepcion(self, trama):
        """
        Contabiliza y captura una trama recibida.

        Parametros
        ----------
        trama : bytes | bytearray | None
            Trama devuelta por la libreria.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if not trama:
            return

        self.tramas_recibidas += 1

        if self._unit_id is None:
            # Maestro: no tiene direccion propia, y todo lo que recibe es una
            # respuesta a una peticion que el mismo emitio.
            self._captura.registrar("RX", trama, es_peticion=False)
            return

        propia = trama[0] == self._unit_id
        if propia:
            self.tramas_propias += 1

            # Funciones de escritura: 0x05 y 0x06 simples, 0x0F y 0x10 multiples.
            # Solo estas pueden alterar una salida; las de lectura no tocan el
            # estado del dispositivo, de modo que contarlas aqui desdibujaria la
            # evidencia de retencion.
            if len(trama) > 1 and trama[1] in (0x05, 0x06, 0x0F, 0x10):
                self.ordenes_escritura += 1
                self.ultima_orden_ms = time.ticks_ms()

        # Sentido logico de lo recibido por un esclavo, que no es uniforme:
        #
        #   propia -> siempre una peticion del maestro. Nadie mas inicia
        #             transacciones en el bus.
        #   ajena  -> puede ser una peticion al otro esclavo, o la RESPUESTA de
        #             ese otro esclavo. En un bus multipunto todos los nodos oyen
        #             todo, de modo que el sentido es genuinamente desconocido y
        #             se deja que lo deduzca la heuristica de longitud. Forzarlo
        #             describiria mal las respuestas ajenas, y un volcado que
        #             miente es peor que no tener volcado.
        self._captura.registrar(
            "RX" if propia else "RX(aj)", trama,
            es_peticion=True if propia else None,
        )
