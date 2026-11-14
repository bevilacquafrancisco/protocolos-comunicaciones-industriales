"""
data_model.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Modelo de datos MODBus del esclavo: las cuatro tablas de la especificacion
(MODBUS Application Protocol V1.1b3, §4.3), cada una con su propio espacio de
direcciones de 0x0000 a 0xFFFF.

    Tabla               Tipo     Acceso desde el bus   Funciones
    discrete_inputs     bit      solo lectura          02
    coils               bit      lectura / escritura   01, 05
    input_registers     UInt16   solo lectura          04
    holding_registers   UInt16   lectura / escritura   03, 06

El mapa NO esta escrito aca: se recibe de config.py como una lista de entradas.
Asi el mismo modulo sirve para el dispositivo 1 y para el "esclavo desconocido"
(ADR-007), y el mapa vive en un unico lugar (I-04, I-06).

Hay dos interfaces, a proposito separadas:
  - la del BUS (leer_bits, leer_registros, escribir_coil, escribir_holding): aplica
    las reglas MODBus y lanza ErrorModbus con el codigo de excepcion;
  - la del HARDWARE (fijar_entrada, valor_de_senal): la usa main.py para publicar
    las entradas fisicas y leer las salidas; no pasa por las reglas de acceso,
    porque un sensor SI escribe su propio Input Register.

Diagrama de flujo: bloques [DF-1.11] (validacion de direcciones y valores) y
[DF-1.12] (ejecucion).

Dependencias externas
---------------------
Ninguna. Corre igual en MicroPython y en CPython.
"""

# =============================================================================
# Tablas y codigos de excepcion
# =============================================================================

COILS = "coils"
DISCRETE_INPUTS = "discrete_inputs"
HOLDING_REGISTERS = "holding_registers"
INPUT_REGISTERS = "input_registers"

#: Tablas de 1 bit y de 16 bits (determina rango de valores y empaquetado).
TABLAS_BIT = (COILS, DISCRETE_INPUTS)
TABLAS_REGISTRO = (HOLDING_REGISTERS, INPUT_REGISTERS)
TABLAS = TABLAS_BIT + TABLAS_REGISTRO

#: Codigos de excepcion (MODBUS Application Protocol V1.1b3, §7).
EXC_FUNCION_ILEGAL = 0x01      # la funcion no esta implementada
EXC_DIRECCION_ILEGAL = 0x02    # alguna direccion pedida no existe en el mapa
EXC_VALOR_ILEGAL = 0x03        # cantidad o valor fuera de lo admitido
EXC_FALLO_DISPOSITIVO = 0x04   # error irrecuperable al ejecutar la orden

#: Ultima direccion valida de cualquier tabla.
DIRECCION_MAXIMA = 0xFFFF


class ErrorModbus(Exception):
    """
    Error que el esclavo debe responder como excepcion MODBus.

    Atributos:
        codigo (int): 1 a 4, ver EXC_*.
    Relaciones:
        La lanza ModeloDatos y la atrapa frame_parser.procesar_trama(), que la
        convierte en una respuesta con el bit 7 del codigo de funcion en 1.
    """

    def __init__(self, codigo, detalle=""):
        Exception.__init__(self, detalle)
        self.codigo = codigo


# =============================================================================
# Variable del mapa
# =============================================================================

class Variable:
    """
    Una entrada del mapa de registros.

    Responsabilidad:
        Guardar el valor actual y los limites que valen para una direccion de una tabla.
    Atributos:
        tabla (str): una de TABLAS.
        direccion (int): offset 0x0000-0xFFFF que viaja en la trama (no la notacion
            Modicon de 5 digitos: 40001 es la direccion 0x0000 de holding_registers).
        nombre (str): nombre del diccionario de datos (I-06), p. ej. "Outputs/LedPWM".
        senal (str | None): senal fisica asociada en main.py, o None si es solo memoria.
        minimo, maximo (int): rango admitido. Una escritura fuera de rango desde el bus
            se rechaza con la excepcion 03.
        valor (int): valor actual; en las tablas de bits es 0 o 1.
    """

    def __init__(self, tabla, direccion, nombre, senal, minimo, maximo, valor):
        self.tabla = tabla
        self.direccion = direccion
        self.nombre = nombre
        self.senal = senal
        self.minimo = minimo
        self.maximo = maximo
        self.valor = valor


# =============================================================================
# Modelo de datos
# =============================================================================

class ModeloDatos:
    """
    Las cuatro tablas MODBus del esclavo, construidas a partir del mapa de config.py.

    Responsabilidad:
        Responder lecturas y escrituras del bus con las reglas de la especificacion, y
        ofrecer a la capa de hardware el acceso directo a las senales.
    Atributos principales:
        _tablas (dict[str, dict[int, Variable]]): direccion -> variable, por tabla.
        _por_senal (dict[str, Variable]): para que main.py encuentre cada senal fisica.
        escrituras (int): ordenes de escritura aceptadas desde el bus (diagnostico).
    Relaciones:
        Lo usa frame_parser.procesar_trama() (interfaz del bus) y main.py (interfaz
        del hardware).
    """

    def __init__(self, mapa):
        """
        Construye y VALIDA el modelo. Un mapa mal escrito debe impedir el arranque: un
        esclavo que arranca con un mapa inconsistente responde datos falsos en planta.

        Parametros:
            mapa (list[dict]): entradas con las claves
                tabla (str), direccion (int), nombre (str),
                y opcionales senal (str|None), minimo (int), maximo (int), inicial (int).
        Excepciones:
            ValueError: tabla desconocida, direccion fuera de 0-0xFFFF, direccion o
                senal repetida, limites incoherentes o valor inicial fuera de rango.
        """
        self._tablas = {}
        for tabla in TABLAS:
            self._tablas[tabla] = {}
        self._por_senal = {}
        self.escrituras = 0

        for entrada in mapa:
            tabla = entrada.get("tabla")
            if tabla not in TABLAS:
                raise ValueError("tabla desconocida: {}".format(tabla))
            direccion = entrada.get("direccion")
            if not isinstance(direccion, int) or not 0 <= direccion <= DIRECCION_MAXIMA:
                raise ValueError("direccion invalida en {}: {}".format(tabla, direccion))
            if direccion in self._tablas[tabla]:
                raise ValueError("direccion repetida en {}: 0x{:04X}".format(tabla, direccion))

            tope = 1 if tabla in TABLAS_BIT else 0xFFFF
            minimo = entrada.get("minimo", 0)
            maximo = entrada.get("maximo", tope)
            if not 0 <= minimo <= maximo <= tope:
                raise ValueError("limites invalidos en {} 0x{:04X}: {}..{}".format(
                    tabla, direccion, minimo, maximo))
            inicial = int(entrada.get("inicial", minimo))
            if not minimo <= inicial <= maximo:
                raise ValueError("valor inicial fuera de rango en {} 0x{:04X}".format(
                    tabla, direccion))

            senal = entrada.get("senal")
            variable = Variable(tabla, direccion, entrada.get("nombre", ""), senal,
                                minimo, maximo, inicial)
            self._tablas[tabla][direccion] = variable
            if senal is not None:
                if senal in self._por_senal:
                    raise ValueError("senal asignada dos veces: {}".format(senal))
                self._por_senal[senal] = variable

    # -------------------------------------------------------------------------
    # Interfaz del BUS — [DF-1.11] validacion y [DF-1.12] ejecucion
    # -------------------------------------------------------------------------

    def _rango(self, tabla, inicio, cantidad):
        """
        [DF-1.11] Comprueba que TODAS las direcciones del rango existan en el mapa.

        Parametros:
            tabla (str), inicio (int), cantidad (int >= 1).
        Retorna:
            list[Variable]: en orden de direccion.
        Excepciones:
            ErrorModbus(02): el rango se sale de 0xFFFF o alguna direccion no existe.
        """
        if inicio + cantidad - 1 > DIRECCION_MAXIMA:
            raise ErrorModbus(EXC_DIRECCION_ILEGAL, "rango fuera de 0xFFFF")
        tabla_dict = self._tablas[tabla]
        variables = []
        for direccion in range(inicio, inicio + cantidad):
            variable = tabla_dict.get(direccion)
            if variable is None:
                raise ErrorModbus(EXC_DIRECCION_ILEGAL,
                                  "{} 0x{:04X} no existe".format(tabla, direccion))
            variables.append(variable)
        return variables

    def leer_bits(self, tabla, inicio, cantidad):
        """
        [DF-1.12] Lee un rango contiguo de coils o de discrete inputs (FC 01 / 02).

        Parametros:
            tabla (str): COILS o DISCRETE_INPUTS.
            inicio (int): primera direccion.
            cantidad (int): cantidad de bits (el limite 1-2000 lo valida el parser).
        Retorna:
            list[int]: 0 o 1 por direccion.
        Excepciones:
            ErrorModbus(02): alguna direccion no existe.
        """
        return [v.valor for v in self._rango(tabla, inicio, cantidad)]

    def leer_registros(self, tabla, inicio, cantidad):
        """
        [DF-1.12] Lee un rango contiguo de holding o input registers (FC 03 / 04).

        Parametros:
            tabla (str): HOLDING_REGISTERS o INPUT_REGISTERS.
            inicio (int), cantidad (int): el limite 1-125 lo valida el parser.
        Retorna:
            list[int]: valores 0-0xFFFF.
        Excepciones:
            ErrorModbus(02): alguna direccion no existe.
        """
        return [v.valor for v in self._rango(tabla, inicio, cantidad)]

    def escribir_coil(self, direccion, encendido):
        """
        [DF-1.12] Escribe un coil (FC 05).

        Parametros:
            direccion (int).
            encendido (bool): el parser ya tradujo 0xFF00 / 0x0000.
        Excepciones:
            ErrorModbus(02): la direccion no existe.
            ErrorModbus(03): el valor no esta en el rango del coil (p. ej. un coil
                fijo en 0 por configuracion).
        """
        variable = self._rango(COILS, direccion, 1)[0]
        valor = 1 if encendido else 0
        if not variable.minimo <= valor <= variable.maximo:
            raise ErrorModbus(EXC_VALOR_ILEGAL, "coil fuera de rango")
        variable.valor = valor
        self.escrituras += 1

    def escribir_holding(self, direccion, valor):
        """
        [DF-1.12] Escribe un holding register (FC 06).

        Decision respecto de la T1: alli un PWM de 5000 se SATURABA en 255. Aca se
        RECHAZA con la excepcion 03, para que el maestro lo cuente (Status/MODBUS/
        EXCEPTION) y el operador vea que la orden no se cumplio tal como la dio.

        Parametros:
            direccion (int), valor (int): 0-0xFFFF (garantizado por el formato de la trama).
        Excepciones:
            ErrorModbus(02): la direccion no existe.
            ErrorModbus(03): valor fuera de [minimo, maximo] de esa variable.
        """
        variable = self._rango(HOLDING_REGISTERS, direccion, 1)[0]
        if not variable.minimo <= valor <= variable.maximo:
            raise ErrorModbus(EXC_VALOR_ILEGAL, "{} fuera de {}..{}".format(
                valor, variable.minimo, variable.maximo))
        variable.valor = valor
        self.escrituras += 1

    # -------------------------------------------------------------------------
    # Interfaz del HARDWARE (main.py)
    # -------------------------------------------------------------------------

    def fijar_entrada(self, senal, valor):
        """
        [DF-1.3] Publica el valor de una senal fisica en su variable.

        A diferencia del bus, no rechaza: SATURA al rango declarado. Un sensor que
        entrega un valor imposible (ruido del ADC por encima del maximo) no debe
        detener el esclavo; el valor saturado es la mejor estimacion disponible.

        Parametros:
            senal (str): nombre de la senal en el mapa.
            valor (int | bool).
        Retorna:
            bool: True si la senal existe en el mapa activo, False si no (el perfil no
            la expone y la lectura del hardware simplemente se descarta).
        Excepciones:
            Ninguna.
        """
        variable = self._por_senal.get(senal)
        if variable is None:
            return False
        valor = int(valor)
        if valor < variable.minimo:
            valor = variable.minimo
        elif valor > variable.maximo:
            valor = variable.maximo
        variable.valor = valor
        return True

    def valor_de_senal(self, senal):
        """
        [DF-1.17] Devuelve el valor actual de una senal (para llevarlo a una salida).

        Parametros:
            senal (str).
        Retorna:
            int | None: None si el perfil activo no tiene esa senal.
        """
        variable = self._por_senal.get(senal)
        return None if variable is None else variable.valor

    def senales(self):
        """Retorna list[str] con las senales fisicas del mapa activo."""
        return list(self._por_senal)

    def variables(self, tabla):
        """
        Retorna list[Variable] de una tabla, ordenadas por direccion (para el listado
        del mapa en la consola de arranque y para las pruebas).
        """
        tabla_dict = self._tablas[tabla]
        return [tabla_dict[d] for d in sorted(tabla_dict)]
