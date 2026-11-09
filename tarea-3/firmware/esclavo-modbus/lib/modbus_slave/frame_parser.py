"""
frame_parser.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Capa de enlace y de aplicacion del esclavo MODBus RTU, sin dependencias del hardware:

  1. tiempos_us()          -> t_caracter, t1,5 y t3,5 a partir del baud rate.
  2. EnsambladorTramas     -> delimita las tramas por silencio (fin de trama = t3,5).
  3. procesar_trama()      -> valida (longitud, Unit ID, CRC), despacha por codigo de
                              funcion y arma la respuesta o la excepcion, con CRC propio.

El reloj se recibe como parametro (ahora_us y una funcion de diferencia): en el ESP32
es time.ticks_us() / time.ticks_diff(), y en las pruebas de la PC son enteros. Asi toda
la logica se prueba sin placa (CLAUDE.md §6).

Funciones soportadas: 01 Read Coils · 02 Read Discrete Inputs · 03 Read Holding
Registers · 04 Read Input Registers · 05 Write Single Coil · 06 Write Single Register.
Excepciones: 01 funcion ilegal · 02 direccion ilegal · 03 valor ilegal · 04 fallo.

Orden de las validaciones (MODBUS Application Protocol V1.1b3, diagramas de estado
de cada funcion en §6): funcion soportada -> cantidad/valor (03) -> direcciones (02)
-> ejecucion (04 si falla).

Diagrama de flujo: docs/diagramas/flujo-esclavo.mmd, bloques [DF-1.2] y [DF-1.4] a [DF-1.16].

Dependencias externas
---------------------
Ninguna (modulos hermanos crc16 y data_model). MicroPython y CPython.
"""

from . import crc16
from . import data_model
from .data_model import ErrorModbus

# =============================================================================
# Codigos de funcion y limites de la especificacion
# =============================================================================

FC_READ_COILS = 0x01
FC_READ_DISCRETE_INPUTS = 0x02
FC_READ_HOLDING_REGISTERS = 0x03
FC_READ_INPUT_REGISTERS = 0x04
FC_WRITE_SINGLE_COIL = 0x05
FC_WRITE_SINGLE_REGISTER = 0x06

#: Tabla sobre la que opera cada funcion de lectura.
_TABLA_DE_LECTURA = {
    FC_READ_COILS: data_model.COILS,
    FC_READ_DISCRETE_INPUTS: data_model.DISCRETE_INPUTS,
    FC_READ_HOLDING_REGISTERS: data_model.HOLDING_REGISTERS,
    FC_READ_INPUT_REGISTERS: data_model.INPUT_REGISTERS,
}

#: Cantidad maxima por lectura. Sale del limite de 256 bytes de la ADU RTU:
#: 256 - 1 (direccion) - 1 (funcion) - 1 (conteo de bytes) - 2 (CRC) = 251 bytes de
#: datos, que la especificacion redondea a 250: 250 x 8 = 2000 bits; 250 / 2 = 125
#: registros (V1.1b3 §6.1 y §6.3; tarea-1/docs/protocolo-comunicacion.md §9).
MAX_BITS_LECTURA = 2000
MAX_REGISTROS_LECTURA = 125

#: Valores validos de FC 05: 0xFF00 = encendido, 0x0000 = apagado (V1.1b3 §6.5).
COIL_ON = 0xFF00
COIL_OFF = 0x0000

#: Longitudes de trama RTU.
LONGITUD_MINIMA = 4            # direccion + funcion + CRC
LONGITUD_MAXIMA = 256          # limite de la ADU serie
LONGITUD_PETICION_SIMPLE = 8   # FC 01-06: direccion, funcion, 2 + 2 bytes, CRC

#: Unit ID de difusion: todos los esclavos ejecutan, ninguno responde.
DIRECCION_DIFUSION = 0

#: Bits por caracter que la especificacion toma como referencia para los tiempos:
#: 1 de arranque + 8 de datos + 1 de paridad (o un 2.o de parada) + 1 de parada
#: (MODBus over Serial Line V1.02, §2.5.1). Con 8N1 el caracter real es de 10 bits;
#: usar 11 sobreestima los silencios un 10 % y deja del lado seguro (igual que la T1).
BITS_POR_CARACTER = 11

#: Por encima de 19200 bps la especificacion fija valores constantes (§2.5.1.1), porque
#: t1,5 y t3,5 calculados serian demasiado cortos para los temporizadores reales.
BAUD_LIMITE_TIEMPOS_FIJOS = 19200
T15_FIJO_US = 750
T35_FIJO_US = 1750


# =============================================================================
# [DF-1.2] Tiempos del enlace
# =============================================================================

def tiempos_us(baud):
    """
    [DF-1.2] Calcula los tiempos de la delimitacion RTU a partir del baud rate.

    Formula (MODBus over Serial Line V1.02, §2.5.1.1):

        t_car = BITS_POR_CARACTER / baud            [s]   (11 bits por caracter)
        t1,5  = 1,5 * t_car   -> hueco maximo DENTRO de una trama
        t3,5  = 3,5 * t_car   -> silencio minimo que marca el FIN de una trama
        si baud > 19200:  t1,5 = 750 us  y  t3,5 = 1750 us  (valores fijos)

    Valores (exacto -> devuelto, redondeado hacia arriba):
             9600 bps   -> t_car 1145,8 -> 1146 us · t1,5 1718,8 -> 1719 us · t3,5 4010,4 -> 4011 us
             19200 bps  -> t_car  572,9 ->  573 us · t1,5  859,4 ->  860 us · t3,5 2005,2 -> 2006 us
             115200 bps -> t_car   95,5 ->   96 us · t1,5 750 us (fijo)   · t3,5 1750 us (fijo)

    Se usa aritmetica entera (MicroPython del ESP32 evita asi el punto flotante) con
    redondeo hacia arriba: un silencio levemente mas largo es seguro; uno mas corto
    podria cortar una trama legitima.

    Parametros:
        baud (int): velocidad del enlace, > 0.
    Retorna:
        tuple[int, int, int]: (t_caracter_us, t15_us, t35_us).
    Excepciones:
        ValueError: baud <= 0.
    """
    if baud <= 0:
        raise ValueError("baud rate invalido: {}".format(baud))
    # ceil(a / b) con enteros = (a + b - 1) // b
    t_car = (BITS_POR_CARACTER * 1000000 + baud - 1) // baud
    if baud > BAUD_LIMITE_TIEMPOS_FIJOS:
        return t_car, T15_FIJO_US, T35_FIJO_US
    t15 = (15 * BITS_POR_CARACTER * 1000000 + 10 * baud - 1) // (10 * baud)
    t35 = (35 * BITS_POR_CARACTER * 1000000 + 10 * baud - 1) // (10 * baud)
    return t_car, t15, t35


def _diferencia_entera(a, b):
    """Diferencia de tiempos para las pruebas en la PC (sin desborde de ticks)."""
    return a - b


# =============================================================================
# [DF-1.4] a [DF-1.7] Delimitacion de tramas por silencio
# =============================================================================

class EnsambladorTramas:
    """
    Junta los bytes recibidos y decide cuando termino una trama.

    Responsabilidad:
        Implementar la delimitacion por tiempo de MODBus RTU: no hay bytes de inicio ni
        de fin, la trama termina cuando el bus queda en silencio t3,5.
    Atributos principales:
        t15_us, t35_us (int): umbrales calculados con tiempos_us().
        verificar_t15 (bool): si es True, un hueco > t1,5 dentro de la trama la marca
            como fragmentada (la especificacion manda descartarla).
        _buffer (bytearray): bytes de la trama en curso.
        _ultimo_us (int | None): instante del ultimo byte recibido.
        _fragmentada, _desbordada (bool): defectos de la trama en curso.
    Relaciones:
        main.py le pasa los bytes del UART; procesar_trama() recibe lo que devuelve.

    Limitacion de la medicion (documentada en firmware/README.md): el UART del ESP32
    tiene FIFO, de modo que el software ve los bytes en bloques. Un hueco solo se mide
    entre bloques; si el lazo se demora (p. ej. una pausa del recolector de basura) con
    bytes en vuelo, el hueco medido es mayor que el real. Por eso verificar_t15 se puede
    desactivar en config.py, y el contador tramas_fragmentadas permite medir su efecto.
    """

    def __init__(self, t15_us, t35_us, verificar_t15=True, diferencia=None):
        """
        Parametros:
            t15_us, t35_us (int): umbrales en microsegundos.
            verificar_t15 (bool): aplicar la regla de t1,5.
            diferencia (callable | None): f(a, b) -> a - b con desborde de ticks;
                None = resta entera (pruebas). En el ESP32: time.ticks_diff.
        """
        self.t15_us = t15_us
        self.t35_us = t35_us
        self.verificar_t15 = verificar_t15
        self._diferencia = diferencia if diferencia is not None else _diferencia_entera
        self._buffer = bytearray()
        self._ultimo_us = None
        self._fragmentada = False
        self._desbordada = False

    def en_curso(self):
        """Retorna True si hay una trama a medio recibir (el lazo no debe demorarse)."""
        return len(self._buffer) > 0

    def alimentar(self, datos, ahora_us):
        """
        [DF-1.5] Agrega un bloque de bytes recibido en el instante ahora_us.

        Si el silencio desde el bloque anterior ya alcanzaba t3,5, la trama anterior
        estaba terminada: se la deja disponible y estos bytes inician una nueva. (En el
        uso normal main.py llama a trama_completa() antes y esto no ocurre; es la red de
        seguridad si el lazo se demoro.)

        Parametros:
            datos (bytes | bytearray): bytes leidos del UART, al menos uno.
            ahora_us (int): instante de la lectura.
        Retorna:
            tuple | None: la trama anterior, en el formato de trama_completa(), si
            quedo cerrada por este bloque; None en otro caso.
        """
        cerrada = None
        if self._buffer and self._ultimo_us is not None:
            hueco = self._diferencia(ahora_us, self._ultimo_us)
            if hueco >= self.t35_us:
                cerrada = self._cerrar()
            elif hueco > self.t15_us and self.verificar_t15:
                # [DF-1.7] hueco entre t1,5 y t3,5: trama incompleta segun §2.5.1.1
                self._fragmentada = True
        # Mas de 256 bytes no es una trama RTU valida: se sigue recibiendo para no
        # partir la basura en varias "tramas", pero se marca para descartarla.
        if len(self._buffer) + len(datos) > LONGITUD_MAXIMA:
            self._desbordada = True
        else:
            self._buffer.extend(datos)
        self._ultimo_us = ahora_us
        return cerrada

    def trama_completa(self, ahora_us):
        """
        [DF-1.6] Devuelve la trama si el bus lleva un silencio >= t3,5.

        Parametros:
            ahora_us (int): instante actual.
        Retorna:
            tuple[bytes, bool] | None: (trama, defectuosa). defectuosa = True si hubo un
            hueco > t1,5 dentro o si supero 256 bytes. None si no hay trama terminada.
        """
        if not self._buffer and not self._desbordada:
            return None
        if self._diferencia(ahora_us, self._ultimo_us) < self.t35_us:
            return None
        return self._cerrar()

    def _cerrar(self):
        """Entrega la trama en curso y deja el ensamblador vacio."""
        resultado = (bytes(self._buffer), self._fragmentada or self._desbordada)
        self._buffer = bytearray()
        self._fragmentada = False
        self._desbordada = False
        return resultado


# =============================================================================
# [DF-1.7] a [DF-1.15] Procesamiento de una trama completa
# =============================================================================

#: Motivos que devuelve procesar_trama(); main.py los usa como claves de contadores.
MOTIVO_RESPONDIDA = "respondida"        # respuesta normal
MOTIVO_EXCEPCION = "excepcion"          # respuesta de excepcion
MOTIVO_DIFUSION = "difusion"            # Unit ID 0: ejecutada (si es escritura), sin respuesta
MOTIVO_AJENA = "ajena"                  # dirigida a otro esclavo
MOTIVO_CRC = "crc_error"                # CRC invalido
MOTIVO_INVALIDA = "invalida"            # longitud < 4, hueco > t1,5 o > 256 bytes


def _u16(trama, indice):
    """Lee un entero de 16 bits big-endian (MSB primero) en trama[indice]."""
    return (trama[indice] << 8) | trama[indice + 1]


def _empaquetar_bits(bits):
    """
    Empaqueta bits como manda FC 01/02: el primer bit pedido va en el bit 0 (LSB) del
    primer byte; los bits sobrantes del ultimo byte quedan en 0 (V1.1b3 §6.1).

    Parametros:
        bits (list[int]): 0 o 1.
    Retorna:
        bytearray: ceil(len(bits) / 8) bytes.
    """
    salida = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            salida[i >> 3] |= 1 << (i & 7)
    return salida


def _respuesta_excepcion(unit_id, funcion, codigo):
    """
    [DF-1.13] Arma la respuesta de excepcion: ID, funcion | 0x80, codigo, CRC.

    Parametros:
        unit_id (int), funcion (int), codigo (int 1-4).
    Retorna:
        bytearray: 5 bytes.
    """
    return crc16.agregar_crc(bytes([unit_id, (funcion | 0x80) & 0xFF, codigo]))


def _ejecutar(trama, modelo):
    """
    [DF-1.10] a [DF-1.12] Despacha por codigo de funcion, valida y ejecuta.

    Parametros:
        trama (bytes): trama completa con CRC ya verificado.
        modelo (data_model.ModeloDatos).
    Retorna:
        bytearray: PDU de respuesta (funcion + datos), sin direccion ni CRC.
    Excepciones:
        ErrorModbus: con el codigo de excepcion que corresponde.
    """
    funcion = trama[1]

    # [DF-1.10] Despacho: funcion no implementada -> excepcion 01
    if funcion not in _TABLA_DE_LECTURA and funcion not in (FC_WRITE_SINGLE_COIL,
                                                            FC_WRITE_SINGLE_REGISTER):
        raise ErrorModbus(data_model.EXC_FUNCION_ILEGAL, "funcion 0x{:02X}".format(funcion))

    # Todas las funciones soportadas tienen peticion de 8 bytes. Otra longitud es una
    # PDU mal formada: se responde 03, el mismo criterio que la especificacion usa
    # para un campo con valor incoherente.
    if len(trama) != LONGITUD_PETICION_SIMPLE:
        raise ErrorModbus(data_model.EXC_VALOR_ILEGAL, "longitud {}".format(len(trama)))

    direccion = _u16(trama, 2)
    argumento = _u16(trama, 4)      # cantidad (lecturas) o valor (escrituras)

    if funcion in _TABLA_DE_LECTURA:
        tabla = _TABLA_DE_LECTURA[funcion]
        es_bit = tabla in data_model.TABLAS_BIT
        # [DF-1.11] Cantidad: 03 si esta fuera de 1..2000 (bits) o 1..125 (registros)
        maximo = MAX_BITS_LECTURA if es_bit else MAX_REGISTROS_LECTURA
        if not 1 <= argumento <= maximo:
            raise ErrorModbus(data_model.EXC_VALOR_ILEGAL, "cantidad {}".format(argumento))
        # [DF-1.11] Direcciones (02) y [DF-1.12] lectura
        if es_bit:
            datos = _empaquetar_bits(modelo.leer_bits(tabla, direccion, argumento))
        else:
            datos = bytearray()
            for valor in modelo.leer_registros(tabla, direccion, argumento):
                datos.append((valor >> 8) & 0xFF)   # MSB primero (big-endian)
                datos.append(valor & 0xFF)
        pdu = bytearray([funcion, len(datos)])
        pdu.extend(datos)
        return pdu

    if funcion == FC_WRITE_SINGLE_COIL:
        # [DF-1.11] Solo 0xFF00 o 0x0000 son validos -> si no, excepcion 03
        if argumento not in (COIL_ON, COIL_OFF):
            raise ErrorModbus(data_model.EXC_VALOR_ILEGAL, "coil 0x{:04X}".format(argumento))
        modelo.escribir_coil(direccion, argumento == COIL_ON)       # [DF-1.12]
    else:  # FC_WRITE_SINGLE_REGISTER
        modelo.escribir_holding(direccion, argumento)               # [DF-1.11]/[DF-1.12]

    # La respuesta normal de FC 05 y 06 es el eco de la peticion (sin el CRC, que se
    # vuelve a generar al armar la trama).
    return bytearray(trama[1:6])


def procesar_trama(trama, unit_id, modelo, defectuosa=False):
    """
    Procesa una trama completa y decide la respuesta.

    Secuencia (docs/diagramas/flujo-esclavo.mmd):
        [DF-1.7]  longitud >= 4 y sin defectos de delimitacion, si no: descartar
        [DF-1.8]  Unit ID propio o 0, si no: descartar en silencio
        [DF-1.9]  CRC correcto, si no: descartar sin responder
        [DF-1.10] a [DF-1.13] despacho, validacion, ejecucion o excepcion
        [DF-1.14] difusion: se ejecuta la escritura pero NO se responde
        [DF-1.15] respuesta con CRC propio

    Por que el CRC invalido no se responde (ni siquiera con excepcion): responder
    implicaria confiar en un Unit ID que pudo llegar alterado, y podria contestar el
    esclavo equivocado. El maestro lo vera como timeout y reintentara.

    Parametros:
        trama (bytes): trama completa entregada por EnsambladorTramas.
        unit_id (int): direccion propia, 1-247.
        modelo (data_model.ModeloDatos).
        defectuosa (bool): marca del ensamblador (hueco > t1,5 o desborde).
    Retorna:
        tuple[bytearray | None, str]: (respuesta a transmitir o None, motivo MOTIVO_*).
    Excepciones:
        Ninguna: todo error se traduce en un motivo o en una excepcion MODBus.
    """
    # [DF-1.7] Validacion de longitud y de delimitacion
    if defectuosa or len(trama) < LONGITUD_MINIMA:
        return None, MOTIVO_INVALIDA

    # [DF-1.8] Filtrado por Unit ID: si la trama no es para este esclavo, silencio
    destino = trama[0]
    if destino != unit_id and destino != DIRECCION_DIFUSION:
        return None, MOTIVO_AJENA

    # [DF-1.9] Validacion de CRC de la trama recibida
    if not crc16.verificar_crc(trama):
        return None, MOTIVO_CRC

    difusion = destino == DIRECCION_DIFUSION
    funcion = trama[1]

    # [DF-1.14] En difusion solo tienen sentido las escrituras (V1.1b3 §4.1: "no
    # response is returned to broadcast requests"); una lectura se ignora.
    if difusion and funcion not in (FC_WRITE_SINGLE_COIL, FC_WRITE_SINGLE_REGISTER):
        return None, MOTIVO_DIFUSION

    try:
        pdu = _ejecutar(trama, modelo)                       # [DF-1.10] a [DF-1.12]
        motivo = MOTIVO_RESPONDIDA
    except ErrorModbus as error:
        pdu = None                                           # [DF-1.13]
        codigo = error.codigo
        motivo = MOTIVO_EXCEPCION
    except Exception:
        # Cualquier otra falla al ejecutar es un error interno del esclavo: excepcion 04.
        # Se atrapa para que una trama no pueda detener el dispositivo de campo.
        pdu = None
        codigo = data_model.EXC_FALLO_DISPOSITIVO
        motivo = MOTIVO_EXCEPCION

    if difusion:                                             # [DF-1.14]
        return None, MOTIVO_DIFUSION

    # [DF-1.15] Armado de la respuesta con CRC propio
    if pdu is None:
        return _respuesta_excepcion(unit_id, funcion, codigo), motivo
    mensaje = bytearray([unit_id])
    mensaje.extend(pdu)
    return crc16.agregar_crc(mensaje), motivo
