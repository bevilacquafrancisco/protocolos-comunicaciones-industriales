"""
monitor_tramas_maestro.py  (MONITOR DE TRAMAS DEL MAESTRO - se ejecuta desde RAM)
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-29
Version: 1.0

Descripcion general
-------------------
Ejecuta el firmware del maestro TAL COMO ESTA CARGADO en la placa y muestra en
el Shell de Thonny, campo por campo, cada trama MODBus RTU que el maestro envia
y recibe por el bus RS-485: Unit ID, codigo de funcion, area de datos, direccion
con su equivalente Modicon, cantidad o valor, datos de la respuesta, CRC-16
recalculado y verificado, tiempo de ida y vuelta, excepciones y timeouts.

NO SE GUARDA EN LA PLACA. Se abre en Thonny y se ejecuta con F5: Thonny lo manda
a la RAM del ESP32 sin escribir nada en la flash. El main.py, config.py,
diagnostico.py y perifericos.py del maestro quedan intactos, y al desconectar o
reiniciar (Ctrl+D) el maestro vuelve a arrancar solo con su firmware de siempre.
Es el mismo flujo que prueba_perifericos.py (firmware/README.md, seccion 7).

Como se consigue sin modificar la logica
----------------------------------------
Este script NO reimplementa el maestro: importa el main.py de la placa como
modulo (su guarda `if __name__ == "__main__"` evita que arranque solo) y llama
a su propio main(). Antes de hacerlo, en RAM y solo durante esta ejecucion:

  1. Envuelve configurar_maestro_modbus() para colgarle observadores al bus
     recien creado: un proxy del UART (registra TX), una envoltura de
     _uart_read_frame (registra RX o timeout) y una envoltura de cada metodo de
     transaccion de umodbus (registra la llamada, su resultado o su excepcion).
  2. Envuelve MaestroModbus.ejecutar_paso() para detectar el FIN de cada ciclo
     de sondeo (la transicion de un estado activo a ESTADO_ESPERA).

Toda envoltura llama al original con los mismos argumentos y devuelve lo mismo,
o relanza la misma excepcion: el maestro no puede distinguir si esta observado.

Por que se imprime al final del ciclo y no trama por trama
----------------------------------------------------------
Es el efecto sonda documentado en diagnostico.CapturaTramas: cada print() cuesta
1-3 ms, y si se imprime DENTRO de la transaccion ese costo se suma al tiempo de
respuesta y puede provocar timeouts que no existen sin la traza. Aca las tramas
se guardan en memoria (una copia de 8 bytes y un append: microsegundos) y se
imprimen cuando el ciclo ya termino y el bus esta en silencio. Lo unico que se
demora es el COMIENZO del ciclo siguiente, y eso es inocuo porque el maestro es
quien decide cuando sondear.

Consecuencia medible a tener en cuenta: con DETALLADO = True cada ciclo imprime
~40-60 lineas (unos 3 KB). A 115200 baudios por el USB eso son ~260 ms, de modo
que el periodo efectivo de sondeo pasa de 200 ms a ~450 ms mientras el monitor
corre. La tasa de error sigue siendo valida (no se imprime dentro de las
transacciones); el periodo, no. Para medir el periodo, usar el main.py solo.

Uso
---
  1. Maestro conectado por USB, esclavos alimentados y en el bus.
  2. Thonny -> abrir ESTE archivo desde la PC (no desde "Dispositivo").
  3. F5. Thonny reinicia en caliente la placa (sin correr su main.py) y
     ejecuta este script en RAM.
  4. Ctrl+C para detenerlo: imprime un resumen de lo observado.
  5. Ctrl+D (o desconectar y reconectar) para volver al firmware normal.

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32.
- En la placa: main.py, config.py, diagnostico.py, perifericos.py del maestro y
  la libreria umodbus (micropython-modbus, brainelectronics).
- Se prueba en la PC, sin hardware, con herramientas/prueba_monitor_tramas.py.
"""

import time


# =============================================================================
# Opciones del monitor
# =============================================================================
# Van aca y no en config.py a proposito: config.py contiene lo que debe coincidir
# entre los tres nodos, y esto es una preferencia de visualizacion de una sola
# sesion de Thonny. Ademas, ponerlas alla obligaria a modificar el config.py de
# la placa, que es justamente lo que este script evita.

#: True: una linea por campo de cada trama (formato para citar en el informe).
#: False: una linea por trama (hexadecimal + resumen), mucho menos texto.
DETALLADO = True

#: Imprimir uno de cada N ciclos. 1 = todos. Los ciclos con fallo se imprimen
#: siempre, aunque no les toque: son los que explican un problema.
MOSTRAR_CADA_N_CICLOS = 1

#: True: imprimir solo los ciclos en los que alguna transaccion fallo.
MOSTRAR_SOLO_FALLOS = False

#: Tope de transacciones guardadas por ciclo. Un ciclo normal tiene 4 (8 con
#: reintentos). El tope solo existe para acotar la memoria si algo inesperado
#: impidiera cerrar el ciclo.
_MAXIMO_TRANSACCIONES = 16


# =============================================================================
# Tablas del protocolo (MODBus Application Protocol V1.1b3)
# =============================================================================

#: Nombre de cada codigo de funcion.
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

#: Area de datos sobre la que opera cada funcion: (nombre, base Modicon, clave).
#: La clave corta es la que indexa el mapa de registros de construir_mapa().
#: Hace falta porque en este sistema las cuatro variables estan en el offset
#: 0x0000: lo unico que distingue al pulsador del potenciometro, del LED o del
#: PWM es el codigo de funcion, no la direccion.
AREA_DE_FUNCION = {
    0x01: ("Coils", 1, "CO"),
    0x02: ("Discrete Inputs", 10001, "DI"),
    0x03: ("Holding Registers", 40001, "HR"),
    0x04: ("Input Registers", 30001, "IR"),
    0x05: ("Coils", 1, "CO"),
    0x06: ("Holding Registers", 40001, "HR"),
    0x0F: ("Coils", 1, "CO"),
    0x10: ("Holding Registers", 40001, "HR"),
}

#: Codigos de excepcion (seccion 7 de la especificacion).
NOMBRE_EXCEPCION = {
    0x01: "Illegal Function",
    0x02: "Illegal Data Address",
    0x03: "Illegal Data Value",
    0x04: "Server Device Failure",
    0x05: "Acknowledge",
    0x06: "Server Device Busy",
}

#: Metodos de transaccion de umodbus que se observan -> codigo de funcion. El
#: maestro usa los cuatro primeros; el resto se envuelve igual por si se usaran
#: desde el REPL, y si la version de la libreria no los tiene se ignoran.
METODOS_TRANSACCION = (
    ("read_discrete_inputs", 0x02),
    ("read_input_registers", 0x04),
    ("write_single_coil", 0x05),
    ("write_single_register", 0x06),
    ("read_coils", 0x01),
    ("read_holding_registers", 0x03),
    ("write_multiple_coils", 0x0F),
    ("write_multiple_registers", 0x10),
)

#: Ancho de la columna de nombres de campo en el modo detallado.
_ANCHO_CAMPO = 13


# =============================================================================
# Funciones puras de decodificacion (no dependen de la placa)
# =============================================================================

def crc16(datos):
    """
    Calcula el CRC-16/MODBUS de una secuencia de bytes.

    Polinomio 0xA001 (forma reflejada de 0x8005), valor inicial 0xFFFF. El
    resultado se TRANSMITE con el byte menos significativo primero, al reves que
    el resto de los campos. Vector de prueba estandar: "123456789" -> 0x4B37.
    Desarrollo completo en docs/protocolo-comunicacion.md.

    Parametros
    ----------
    datos : bytes | bytearray
        Trama SIN los dos bytes de CRC.

    Retorna
    -------
    int
        CRC de 16 bits.

    Excepciones
    -----------
    Ninguna.
    """
    crc = 0xFFFF
    for byte in datos:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def hexa(datos):
    """
    Formatea bytes como hexadecimal en mayusculas separado por espacios.

    Se arma a mano y no con bytes.hex() porque el separador de hex() no existe
    en todas las versiones de MicroPython.

    Parametros
    ----------
    datos : bytes | bytearray

    Retorna
    -------
    str
        Por ejemplo "01 04 00 00 00 01 31 CA".

    Excepciones
    -----------
    Ninguna.
    """
    return " ".join("{:02X}".format(byte) for byte in datos)


def construir_mapa(modulo_config):
    """
    Arma el mapa (area, offset) -> descripcion a partir del config.py de la placa.

    Se leen los offsets del config.py cargado, y no se escriben aca, para que el
    monitor describa lo que el maestro REALMENTE usa: si un offset cambiara en
    config.py, la descripcion lo seguiria sin tocar este archivo.

    Parametros
    ----------
    modulo_config : modulo
        El config.py importado. Se lee con getattr para tolerar una version que
        no tenga alguna constante: en ese caso el registro queda sin nombre.

    Retorna
    -------
    dict
        {(clave_area, offset): descripcion}.

    Excepciones
    -----------
    Ninguna.
    """
    entradas = (
        ("DI", "DIR_DISCRETE_INPUT_SWITCH", "pulsador/switch del esclavo"),
        ("IR", "DIR_INPUT_REGISTER_POTE", "potenciometro del esclavo, ADC 0-4095"),
        ("CO", "DIR_COIL_LED_DIGITAL", "LED digital del esclavo"),
        ("HR", "DIR_HOLDING_REGISTER_PWM", "PWM del LED del esclavo, 0-255"),
    )
    mapa = {}
    for clave, constante, descripcion in entradas:
        offset = getattr(modulo_config, constante, None)
        if offset is not None:
            mapa[(clave, offset)] = "{} [{}]".format(descripcion, constante)
    return mapa


def _u16(alto, bajo):
    """Compone un entero de 16 bits big-endian (orden de los campos MODBus)."""
    return (alto << 8) | bajo


def _direccion(codigo, offset, mapa):
    """
    Describe una direccion: offset crudo, equivalente Modicon y nombre.

    Parametros
    ----------
    codigo : int
        Codigo de funcion, que determina el area.
    offset : int
        Direccion tal como viaja en la trama (base 0).
    mapa : dict
        Mapa de construir_mapa().

    Retorna
    -------
    str
        Por ejemplo "0x0000 -> 30001 Input Registers (potenciometro ... [DIR_...])".

    Excepciones
    -----------
    Ninguna.
    """
    area = AREA_DE_FUNCION.get(codigo)
    if area is None:
        return "0x{:04X}".format(offset)
    nombre_area, base, clave = area
    texto = "0x{:04X} -> {:05d} {}".format(offset, base + offset, nombre_area)
    descripcion = mapa.get((clave, offset))
    if descripcion:
        texto += " ({})".format(descripcion)
    return texto


def _bits(datos, cantidad, primera, base):
    """
    Desempaqueta los bits de una respuesta 0x01/0x02.

    MODBus empaqueta los bits LSB primero: el bit 0 del primer byte de datos es
    la primera entrada pedida. Se devuelven solo las `cantidad` pedidas; el
    resto del ultimo byte es relleno en cero.

    Parametros
    ----------
    datos : bytes
        Bytes de datos de la respuesta (sin byte count).
    cantidad : int
        Entradas pedidas en la peticion.
    primera : int
        Offset de la primera entrada pedida.
    base : int
        Base Modicon del area.

    Retorna
    -------
    list[str]
        Una descripcion por bit, por ejemplo "10001 = 1 (ON)".

    Excepciones
    -----------
    Ninguna.
    """
    salida = []
    for indice in range(cantidad):
        byte = indice // 8
        if byte >= len(datos):
            break
        valor = (datos[byte] >> (indice % 8)) & 1
        salida.append("{:05d} = {} ({})".format(
            base + primera + indice, valor, "ON" if valor else "OFF",
        ))
    return salida


def desglosar_trama(trama, es_peticion, peticion=None, mapa=None, escalar=None):
    """
    Decodifica una trama MODBus RTU campo por campo y verifica su CRC.

    Parametros
    ----------
    trama : bytes | bytearray
        Trama completa, CRC incluido.
    es_peticion : bool
        True si la emitio el maestro, False si es la respuesta del esclavo. El
        mismo codigo de funcion tiene formatos distintos en cada sentido (una
        peticion 0x04 lleva direccion y cantidad; su respuesta, byte count y
        datos), y la trama sola no alcanza para distinguirlos.
    peticion : bytes | None, opcional
        Para una respuesta, la peticion que la origino. Permite nombrar cada
        dato devuelto con su direccion y comprobar el eco de 0x05/0x06.
    mapa : dict | None, opcional
        Mapa de construir_mapa(), para nombrar los registros.
    escalar : callable | None, opcional
        Conversion ADC -> PWM del maestro (perifericos.adc_a_pwm), para mostrar
        que PWM local produce un valor leido del potenciometro remoto.

    Retorna
    -------
    tuple(str, list[tuple(str, str)], bool)
        (resumen de una linea, [(campo, valor), ...], crc_correcto).

    Excepciones
    -----------
    Ninguna: una trama malformada se describe, no se rechaza.
    """
    mapa = mapa or {}
    campos = []
    largo = len(trama)

    if largo < 4:
        return (
            "trama truncada: {} bytes, el minimo es 4 (ID + funcion + CRC)".format(largo),
            [("Bytes", hexa(trama) or "(ninguno)")],
            False,
        )

    unit_id = trama[0]
    codigo = trama[1]
    pdu = trama[2:-2]
    crc_en_linea = trama[-2] | (trama[-1] << 8)
    crc_calculado = crc16(trama[:-2])
    crc_ok = crc_en_linea == crc_calculado

    # --- Direccion y funcion ------------------------------------------------
    if unit_id == 0:
        destino = "broadcast"
    else:
        destino = "Esclavo {}".format(unit_id)
    campos.append(("Unit ID", "0x{:02X} = {}".format(unit_id, destino)))

    codigo_base = codigo & 0x7F
    nombre = NOMBRE_FUNCION.get(codigo_base, "funcion desconocida")
    es_excepcion = bool(codigo & 0x80) and not es_peticion
    if es_excepcion:
        campos.append(("Funcion", "0x{:02X} = 0x{:02X} {} + bit 7 de EXCEPCION".format(
            codigo, codigo_base, nombre,
        )))
    else:
        area = AREA_DE_FUNCION.get(codigo_base)
        acceso = ""
        if area:
            acceso = " [{} sobre {}]".format(
                "escritura" if codigo_base in (0x05, 0x06, 0x0F, 0x10) else "lectura",
                area[0],
            )
        campos.append(("Funcion", "0x{:02X} {}{}".format(codigo, nombre, acceso)))

    resumen = "{} 0x{:02X} {} | ID {}".format(
        "Peticion" if es_peticion else "Respuesta", codigo, nombre, unit_id,
    )

    # --- PDU segun funcion y sentido -----------------------------------------
    esperado = None  # largo total esperado de la trama, cuando se puede saber

    if es_excepcion:
        esperado = 5
        if pdu:
            excepcion = pdu[0]
            texto = NOMBRE_EXCEPCION.get(excepcion, "codigo no estandar")
            campos.append(("Excepcion", "0x{:02X} {}".format(excepcion, texto)))
            resumen += " | EXCEPCION 0x{:02X} {}".format(excepcion, texto)

    elif es_peticion and codigo in (0x01, 0x02, 0x03, 0x04) and len(pdu) >= 4:
        esperado = 8
        offset = _u16(pdu[0], pdu[1])
        cantidad = _u16(pdu[2], pdu[3])
        campos.append(("Direccion", _direccion(codigo, offset, mapa)))
        campos.append(("Cantidad", "0x{:04X} = {}".format(cantidad, cantidad)))
        resumen += " | {:05d} x{}".format(AREA_DE_FUNCION[codigo][1] + offset, cantidad)

    elif codigo == 0x05 and len(pdu) >= 4:
        esperado = 8
        offset = _u16(pdu[0], pdu[1])
        valor = _u16(pdu[2], pdu[3])
        if valor == 0xFF00:
            estado = "ON (0xFF00 = encender)"
        elif valor == 0x0000:
            estado = "OFF (0x0000 = apagar)"
        else:
            estado = "INVALIDO: solo se admiten 0xFF00 y 0x0000 (excepcion 03)"
        campos.append(("Direccion", _direccion(codigo, offset, mapa)))
        campos.append(("Valor", "{:02X} {:02X} -> {}".format(pdu[2], pdu[3], estado)))
        resumen += " | {:05d} <- {}".format(1 + offset, estado.split(" ")[0])

    elif codigo == 0x06 and len(pdu) >= 4:
        esperado = 8
        offset = _u16(pdu[0], pdu[1])
        valor = _u16(pdu[2], pdu[3])
        campos.append(("Direccion", _direccion(codigo, offset, mapa)))
        campos.append(("Valor", "MSB {:02X} LSB {:02X} -> {} (0x{:04X})".format(
            pdu[2], pdu[3], valor, valor,
        )))
        resumen += " | {} <- {}".format(40001 + offset, valor)

    elif not es_peticion and codigo in (0x01, 0x02) and len(pdu) >= 1:
        cuenta = pdu[0]
        datos = pdu[1:]
        esperado = 5 + cuenta
        campos.append(("Byte count", "{} byte(s) de datos".format(cuenta)))
        campos.append(("Datos", "{} (bits empaquetados LSB primero)".format(hexa(datos))))
        if peticion is not None and len(peticion) >= 8:
            primera = _u16(peticion[2], peticion[3])
            cantidad = _u16(peticion[4], peticion[5])
            base = AREA_DE_FUNCION[codigo][1]
            for descripcion in _bits(datos, cantidad, primera, base):
                campos.append(("", descripcion))
            if cantidad == 1 and datos:
                resumen += " | {:05d} = {}".format(base + primera, datos[0] & 1)

    elif not es_peticion and codigo in (0x03, 0x04) and len(pdu) >= 1:
        cuenta = pdu[0]
        datos = pdu[1:]
        esperado = 5 + cuenta
        campos.append(("Byte count", "{} byte(s) = {} registro(s) de 16 bits".format(
            cuenta, cuenta // 2,
        )))
        primera = None
        if peticion is not None and len(peticion) >= 8:
            primera = _u16(peticion[2], peticion[3])
        base, clave = AREA_DE_FUNCION[codigo][1], AREA_DE_FUNCION[codigo][2]
        for indice in range(len(datos) // 2):
            valor = _u16(datos[2 * indice], datos[2 * indice + 1])
            if primera is None:
                donde = "registro {}".format(indice)
            else:
                donde = "{:05d}".format(base + primera + indice)
            texto = "{} = MSB {:02X} LSB {:02X} -> {} (big-endian)".format(
                donde, datos[2 * indice], datos[2 * indice + 1], valor,
            )
            if primera is not None:
                descripcion = mapa.get((clave, primera + indice))
                if descripcion:
                    texto += " ({})".format(descripcion.split(" [")[0])
            if escalar is not None and codigo == 0x04:
                try:
                    texto += " => PWM local {}".format(escalar(valor))
                except Exception:
                    pass
            campos.append(("Dato" if indice == 0 else "", texto))
            if indice == 0:
                resumen += " | {} = {}".format(donde, valor)

    elif codigo in (0x0F, 0x10) and len(pdu) >= 4:
        offset = _u16(pdu[0], pdu[1])
        cantidad = _u16(pdu[2], pdu[3])
        campos.append(("Direccion", _direccion(codigo, offset, mapa)))
        campos.append(("Cantidad", "{}".format(cantidad)))
        if es_peticion and len(pdu) >= 5:
            campos.append(("Byte count", "{}".format(pdu[4])))
            campos.append(("Datos", hexa(pdu[5:])))
            esperado = 9 + pdu[4]
        else:
            esperado = 8

    else:
        campos.append(("Datos", hexa(pdu) or "(sin datos)"))

    # --- Eco de las escrituras simples ---------------------------------------
    # La respuesta correcta a 0x05/0x06 es la peticion repetida byte a byte. Es
    # la unica confirmacion de escritura que da el protocolo.
    if not es_peticion and codigo in (0x05, 0x06) and peticion is not None:
        if bytes(trama) == bytes(peticion):
            campos.append(("Eco", "identico a la peticion: escritura confirmada"))
        else:
            campos.append(("Eco", "DISTINTO de la peticion ({})".format(hexa(peticion))))
            resumen += " | ECO DISTINTO"

    # --- Coherencia de la respuesta con su peticion ---------------------------
    if not es_peticion and peticion is not None and len(peticion) >= 2:
        if unit_id != peticion[0]:
            campos.append(("Aviso", "responde el ID {} y se pregunto al ID {}".format(
                unit_id, peticion[0],
            )))
        if codigo_base != peticion[1]:
            campos.append(("Aviso", "funcion 0x{:02X} y se pidio 0x{:02X}".format(
                codigo_base, peticion[1],
            )))

    if esperado is not None and esperado != largo:
        campos.append(("Longitud", "{} bytes, se esperaban {}: trama MAL FORMADA".format(
            largo, esperado,
        )))
        resumen += " | LARGO {} != {}".format(largo, esperado)

    # --- CRC ------------------------------------------------------------------
    campos.append(("CRC", "en linea {:02X} {:02X} (LSB primero) = 0x{:04X} | "
                          "calculado 0x{:04X} -> {}".format(
                              trama[-2], trama[-1], crc_en_linea, crc_calculado,
                              "OK" if crc_ok else "ERROR",
                          )))
    resumen += " | CRC {}".format("OK" if crc_ok else "ERROR")

    return resumen, campos, crc_ok


# =============================================================================
# Captura sobre el bus del maestro
# =============================================================================

class _UARTEspia:
    """
    Proxy del UART que registra lo que el maestro transmite.

    Responsabilidad dentro del sistema
    ----------------------------------
    Capturar la trama TX con su instante en microsegundos y detectar los bytes
    que el maestro descarta en su ventana de guarda posterior a la transmision
    (MaestroRTUConTimeout._uart_read_frame, "glitch de conmutacion DE/RE").

    Por que any() y read() no pasan por un metodo propio
    ----------------------------------------------------
    La libreria llama a any() y read() en un lazo de sondeo mientras espera la
    respuesta. Interponer una funcion en ese lazo le sumaria microsegundos a
    cada vuelta. Por eso se copian como atributos de instancia apuntando al
    metodo REAL: la busqueda los encuentra directamente, sin capa extra.

    La unica excepcion es la PRIMERA lectura despues de cada write(): en el
    firmware cargado esa lectura es el drenaje de la ventana de guarda, y se
    intercepta una sola vez para ver si descarto algo. Enseguida read vuelve a
    apuntar al metodo real.

    Atributos principales
    ---------------------
    _uart : objeto
        UART que tenia el bus (el UARTObservado de diagnostico.py).
    _registrar : callable
        Funcion del monitor que recibe (tipo, datos).

    Relaciones con otras clases
    ---------------------------
    Lo instala MonitorBus.instrumentar() sobre el bus del maestro.
    """

    def __init__(self, uart, registrar):
        self._uart = uart
        self._registrar = registrar
        self._read_real = uart.read
        self.any = uart.any
        self.read = self._read_real

    def write(self, datos):
        """
        Registra la trama y la entrega al UART original.

        Parametros
        ----------
        datos : bytes | bytearray
            Trama a transmitir.

        Retorna
        -------
        int
            Lo que devuelva el UART original.

        Excepciones
        -----------
        Las que propague el UART original.
        """
        self._registrar("TX", datos)
        self.read = self._read_primera
        return self._uart.write(datos)

    def _read_primera(self, *args):
        """Primera lectura tras transmitir: registra lo descartado, si hubo."""
        self.read = self._read_real
        datos = self._read_real(*args)
        if datos:
            self._registrar("DESCARTE", datos)
        return datos

    def __getattr__(self, nombre):
        """Delega en el UART original todo lo que no se define aca."""
        return getattr(self._uart, nombre)


class MonitorBus:
    """
    Registra las transacciones del maestro y las imprime al cerrar cada ciclo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Observar sin intervenir. Todo lo que hace durante una transaccion es copiar
    bytes y tomar un instante; decodificar e imprimir ocurre en cerrar_ciclo(),
    cuando el bus ya esta en silencio. Cualquier error interno del monitor se
    atrapa y se informa: el maestro nunca debe fallar por culpa del monitor.

    Atributos principales
    ---------------------
    ciclos : int
        Ciclos de sondeo observados.
    estadistica : dict
        Contadores globales (tramas, timeouts, CRC, excepciones, fallos).
    _transacciones : list[dict]
        Transacciones del ciclo en curso.
    _actual : dict | None
        Transaccion abierta en este momento.
    _rtt : dict
        Por metodo: [cantidad, suma_us, minimo_us, maximo_us] del tiempo entre
        el inicio de la TX y el fin de la RX.

    Relaciones con otras clases
    ---------------------------
    Instala un _UARTEspia en el bus. Lo usa ejecutar().
    """

    def __init__(self, mapa=None, escalar=None, detallado=True, cada_n=1,
                 solo_fallos=False, reloj=None, imprimir=print):
        """
        Parametros
        ----------
        mapa : dict | None
            Mapa de construir_mapa().
        escalar : callable | None
            Conversion ADC -> PWM del maestro, para anotar las lecturas 0x04.
        detallado : bool
            Formato por campo (True) o una linea por trama (False).
        cada_n : int
            Imprimir uno de cada N ciclos; los fallidos se imprimen siempre.
        solo_fallos : bool
            Imprimir solo ciclos con fallo.
        reloj : objeto | None
            Provee ticks_us(), ticks_ms() y ticks_diff(). Por defecto el modulo
            time de MicroPython; la prueba de PC inyecta uno simulado.
        imprimir : callable
            Salida de texto. Por defecto print().

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._mapa = mapa or {}
        self._escalar = escalar
        self._detallado = detallado
        self._cada_n = max(1, cada_n)
        self._solo_fallos = solo_fallos
        self._reloj = reloj or time
        self._imprimir = imprimir

        self._transacciones = []
        self._actual = None
        self._inicio_ms = self._reloj.ticks_ms()

        self.ciclos = 0
        self.estadistica = {
            "tx": 0, "rx": 0, "timeouts": 0, "crc_error": 0,
            "excepciones": 0, "fallidas": 0, "descartes": 0,
            "ciclos_con_fallo": 0,
        }
        self._rtt = {}

    # -------------------------------------------------------------------------
    # Instalacion sobre el bus
    # -------------------------------------------------------------------------
    def instrumentar(self, bus):
        """
        Cuelga los observadores del objeto Serial de umodbus ya construido.

        Parametros
        ----------
        bus : umodbus.serial.Serial (o subclase)
            El bus que devolvio configurar_maestro_modbus().

        Retorna
        -------
        list[str]
            Metodos de transaccion que quedaron observados.

        Excepciones
        -----------
        AttributeError
            Si el objeto no tiene _uart o _uart_read_frame: sin ellos no hay
            nada que observar, y es preferible avisarlo al arrancar que correr
            un monitor que no muestra nada.
        """
        bus._uart = _UARTEspia(bus._uart, self._registrar_evento)

        # _uart_read_frame ya es un atributo de INSTANCIA (lo puso
        # InstrumentacionBus de diagnostico.py). Se envuelve esa funcion, de modo
        # que la cadena completa sigue intacta: monitor -> diagnostico ->
        # MaestroRTUConTimeout -> umodbus.
        leer_original = bus._uart_read_frame
        monitor = self

        def leer_trama(timeout=None):
            trama = leer_original(timeout)
            monitor._registrar_evento("RX", trama)
            return trama

        bus._uart_read_frame = leer_trama

        observados = []
        for nombre, codigo in METODOS_TRANSACCION:
            metodo = getattr(bus, nombre, None)
            if metodo is not None:
                setattr(bus, nombre, self._envolver(metodo, nombre, codigo))
                observados.append(nombre)
        return observados

    def _envolver(self, metodo, nombre, codigo):
        """
        Envuelve un metodo de transaccion para delimitar sus tramas.

        La envoltura llama al original con los mismos argumentos y devuelve su
        resultado, o relanza su excepcion, sin alterarlos.

        Parametros
        ----------
        metodo : callable
            Metodo ligado original del bus.
        nombre : str
            Nombre del metodo, para el volcado.
        codigo : int
            Codigo de funcion MODBus que emite.

        Retorna
        -------
        callable

        Excepciones
        -----------
        Ninguna al envolver. La envoltura propaga las del original.
        """
        monitor = self

        def envoltura(*args, **kwargs):
            monitor._abrir(nombre, codigo, kwargs)
            try:
                resultado = metodo(*args, **kwargs)
            except Exception as error:
                monitor._cerrar(None, error)
                raise
            monitor._cerrar(resultado, None)
            return resultado

        return envoltura

    # -------------------------------------------------------------------------
    # Registro (camino caliente: solo copias y marcas de tiempo)
    # -------------------------------------------------------------------------
    def _abrir(self, nombre, codigo, argumentos):
        try:
            self._actual = {
                "metodo": nombre, "codigo": codigo, "args": argumentos,
                "t0": self._reloj.ticks_us(), "eventos": [],
                "resultado": None, "error": None, "t1": None,
            }
        except Exception:
            self._actual = None

    def _cerrar(self, resultado, error):
        try:
            transaccion = self._actual
            self._actual = None
            if transaccion is None:
                return
            transaccion["t1"] = self._reloj.ticks_us()
            transaccion["resultado"] = resultado
            transaccion["error"] = error
            if len(self._transacciones) < _MAXIMO_TRANSACCIONES:
                self._transacciones.append(transaccion)
        except Exception:
            pass

    def _registrar_evento(self, tipo, datos):
        try:
            evento = (tipo, self._reloj.ticks_us(), bytes(datos) if datos else b"")
            if self._actual is not None:
                self._actual["eventos"].append(evento)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Cierre del ciclo: aca si se decodifica e imprime
    # -------------------------------------------------------------------------
    def cerrar_ciclo(self, id_activo):
        """
        Contabiliza e imprime las transacciones del ciclo que acaba de terminar.

        Se invoca cuando la maquina de estados entra en ESTADO_ESPERA, ya sea
        porque el ciclo se completo o porque una transaccion fallo y lo corto.

        Parametros
        ----------
        id_activo : int
            Esclavo al que se dirigio el ciclo.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna: un error del monitor se informa y se descarta el ciclo.
        """
        transacciones = self._transacciones
        self._transacciones = []
        if not transacciones:
            return
        self.ciclos += 1

        try:
            hubo_fallo = self._contabilizar(transacciones)
            if hubo_fallo:
                self.estadistica["ciclos_con_fallo"] += 1

            if self._solo_fallos and not hubo_fallo:
                return
            if not hubo_fallo and (self.ciclos - 1) % self._cada_n:
                return
            self._imprimir_ciclo(id_activo, transacciones, hubo_fallo)
        except Exception as error:
            self._imprimir("[MONITOR] error interno al volcar el ciclo {}: {!r}".format(
                self.ciclos, error,
            ))

    def _contabilizar(self, transacciones):
        """Actualiza la estadistica global. Devuelve True si algo fallo."""
        hubo_fallo = False
        for transaccion in transacciones:
            if transaccion["error"] is not None:
                hubo_fallo = True
                self.estadistica["fallidas"] += 1
            peticion = None
            t_tx = None
            for tipo, instante, datos in transaccion["eventos"]:
                if tipo == "TX":
                    self.estadistica["tx"] += 1
                    peticion, t_tx = datos, instante
                elif tipo == "DESCARTE":
                    self.estadistica["descartes"] += 1
                elif tipo == "RX":
                    if not datos:
                        self.estadistica["timeouts"] += 1
                        continue
                    self.estadistica["rx"] += 1
                    if len(datos) >= 4 and crc16(datos[:-2]) != (datos[-2] | (datos[-1] << 8)):
                        self.estadistica["crc_error"] += 1
                    if len(datos) >= 2 and datos[1] & 0x80:
                        self.estadistica["excepciones"] += 1
                    if t_tx is not None and transaccion["error"] is None:
                        self._acumular_rtt(transaccion["metodo"],
                                           self._reloj.ticks_diff(instante, t_tx))
        return hubo_fallo

    def _acumular_rtt(self, metodo, rtt_us):
        registro = self._rtt.get(metodo)
        if registro is None:
            self._rtt[metodo] = [1, rtt_us, rtt_us, rtt_us]
            return
        registro[0] += 1
        registro[1] += rtt_us
        if rtt_us < registro[2]:
            registro[2] = rtt_us
        if rtt_us > registro[3]:
            registro[3] = rtt_us

    def _imprimir_ciclo(self, id_activo, transacciones, hubo_fallo):
        """Imprime el encabezado del ciclo y cada una de sus transacciones."""
        reloj = self._reloj
        segundos = reloj.ticks_diff(reloj.ticks_ms(), self._inicio_ms) / 1000
        ocupado_ms = reloj.ticks_diff(transacciones[-1]["t1"], transacciones[0]["t0"]) / 1000
        codigos = [t["codigo"] for t in transacciones]

        self._imprimir("")
        self._imprimir("=" * 78)
        self._imprimir("[{:10.3f}] CICLO {} | Esclavo {} | {} transaccion(es) | "
                       "bus {:.1f} ms | {}".format(
                           segundos, self.ciclos, id_activo, len(transacciones),
                           ocupado_ms, "CON FALLO" if hubo_fallo else "OK",
                       ))
        self._imprimir("=" * 78)

        anterior = None
        for numero, transaccion in enumerate(transacciones, 1):
            reintento = (
                anterior is not None
                and anterior["metodo"] == transaccion["metodo"]
                and anterior["error"] is not None
            )
            self._imprimir_transaccion(numero, transaccion, reintento)
            anterior = transaccion

        # La zona muerta del maestro omite la 0x06 cuando el potenciometro local
        # no se movio. Sin esta nota, un ciclo de tres transacciones parece un
        # ciclo incompleto.
        if not hubo_fallo and 0x05 in codigos and 0x06 not in codigos:
            self._imprimir("  (0x06 no emitida: PWM local dentro de la zona muerta, "
                           "el esclavo ya tiene ese valor)")

    def _imprimir_transaccion(self, numero, transaccion, reintento):
        """Imprime una transaccion: la llamada, su resultado y sus tramas."""
        reloj = self._reloj
        argumentos = ", ".join(
            "{}={}".format(clave, transaccion["args"][clave])
            for clave in sorted(transaccion["args"])
        )
        duracion_ms = reloj.ticks_diff(transaccion["t1"], transaccion["t0"]) / 1000
        if transaccion["error"] is None:
            desenlace = "OK -> {}".format(transaccion["resultado"])
        else:
            error = transaccion["error"]
            desenlace = "FALLO {}: {}".format(type(error).__name__, error)

        self._imprimir("")
        self._imprimir("[{}] {}({}){}".format(
            numero, transaccion["metodo"], argumentos,
            "  <- REINTENTO" if reintento else "",
        ))
        self._imprimir("    {}  ({:.1f} ms en la libreria)".format(desenlace, duracion_ms))

        peticion = None
        t_tx = None
        for tipo, instante, datos in transaccion["eventos"]:
            relativo = "{:+7.1f}ms".format(
                reloj.ticks_diff(instante, t_tx if t_tx is not None else transaccion["t0"]) / 1000
            )

            if tipo == "TX":
                peticion, t_tx = datos, instante
                relativo = "  +0.0ms"
                self._imprimir_trama("TX", relativo, datos, True, None)

            elif tipo == "DESCARTE":
                self._imprimir("  {} {} DESCARTADO en la ventana de guarda: {} "
                               "(ruido de conmutacion DE/RE o cola de la TX)".format(
                                   "--", relativo, hexa(datos)))

            elif tipo == "RX" and not datos:
                self._imprimir("  RX {} SIN RESPUESTA: vencio el timeout de "
                               "recepcion sin recibir ningun byte".format(relativo))

            elif tipo == "RX":
                self._imprimir_trama("RX", relativo, datos, False, peticion)

    def _imprimir_trama(self, sentido, relativo, trama, es_peticion, peticion):
        """Imprime una trama: linea hexadecimal y, segun el modo, sus campos."""
        resumen, campos, _ = desglosar_trama(
            trama, es_peticion, peticion, self._mapa, self._escalar,
        )
        self._imprimir("  {} {} {:2d}B | {}".format(
            sentido, relativo, len(trama), hexa(trama),
        ))
        if not self._detallado:
            self._imprimir("  {}   {}".format(" " * len(relativo), resumen))
            return
        for campo, valor in campos:
            if campo:
                etiqueta = "{} ".format(campo) + "." * (_ANCHO_CAMPO - len(campo))
            else:
                etiqueta = " " * (_ANCHO_CAMPO + 1)
            self._imprimir("      {} {}".format(etiqueta, valor))

    def imprimir_resumen(self):
        """
        Imprime lo observado desde el arranque del monitor.

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
        e = self.estadistica
        self._imprimir("")
        self._imprimir("=" * 78)
        self._imprimir("RESUMEN DEL MONITOR ({} ciclos observados)".format(self.ciclos))
        self._imprimir("=" * 78)
        self._imprimir("  Tramas TX: {}   RX: {}   sin respuesta: {}   CRC erroneo: {}".format(
            e["tx"], e["rx"], e["timeouts"], e["crc_error"],
        ))
        self._imprimir("  Excepciones MODBus: {}   transacciones fallidas: {}   "
                       "descartes de guarda: {}".format(
                           e["excepciones"], e["fallidas"], e["descartes"],
                       ))
        self._imprimir("  Ciclos con fallo: {} de {}".format(e["ciclos_con_fallo"], self.ciclos))
        if self._rtt:
            self._imprimir("  Ida y vuelta (inicio TX -> fin de RX detectado, incluye t3,5):")
            for metodo in sorted(self._rtt):
                cantidad, suma, minimo, maximo = self._rtt[metodo]
                self._imprimir("    {:<24} n={:<5} min {:6.1f}  prom {:6.1f}  max {:6.1f} ms".format(
                    metodo, cantidad, minimo / 1000, suma / cantidad / 1000, maximo / 1000,
                ))
        self._imprimir("=" * 78)


# =============================================================================
# Arranque sobre el firmware real de la placa
# =============================================================================

def ejecutar():
    """
    Arranca el main() del maestro de la placa con el monitor colgado del bus.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    MonitorBus
        El monitor, cuando se interrumpe con Ctrl+C (queda publicado como
        MONITOR para inspeccionarlo desde el Shell).

    Excepciones
    -----------
    ImportError
        Si falta en la placa alguno de los archivos del maestro.
    """
    global MONITOR

    # Importar el main.py de la placa NO lo ejecuta: su main() esta protegido
    # por `if __name__ == "__main__"`, y al importarlo __name__ vale "main".
    import main as firmware
    import config

    try:
        from perifericos import adc_a_pwm as escalar
    except ImportError:
        escalar = None

    monitor = MonitorBus(
        mapa=construir_mapa(config),
        escalar=escalar,
        detallado=DETALLADO,
        cada_n=MOSTRAR_CADA_N_CICLOS,
        solo_fallos=MOSTRAR_SOLO_FALLOS,
    )
    MONITOR = monitor

    # --- 1. Observadores del bus, instalados apenas se construye -------------
    # main() busca configurar_maestro_modbus en los globales de SU modulo en el
    # momento de llamarla, de modo que reemplazarla ahi alcanza para intervenir
    # la construccion sin tocar main().
    configurar_original = firmware.configurar_maestro_modbus

    def configurar_con_monitor():
        bus = configurar_original()
        observados = monitor.instrumentar(bus)
        print("[MONITOR] Bus observado. Metodos: {}".format(", ".join(observados)))
        return bus

    firmware.configurar_maestro_modbus = configurar_con_monitor

    # --- 2. Deteccion del fin de cada ciclo ----------------------------------
    paso_original = firmware.MaestroModbus.ejecutar_paso
    espera = firmware.ESTADO_ESPERA

    def paso_con_monitor(maestro):
        previo = maestro._estado
        paso_original(maestro)
        if maestro._estado == espera and previo != espera:
            monitor.cerrar_ciclo(maestro._id_activo)

    firmware.MaestroModbus.ejecutar_paso = paso_con_monitor

    print("=" * 78)
    print("MONITOR DE TRAMAS - maestro MODBus RTU (ejecucion en RAM, flash intacta)")
    print("Modo: {} | cada {} ciclo(s){}".format(
        "detallado" if DETALLADO else "compacto",
        MOSTRAR_CADA_N_CICLOS,
        " | solo fallos" if MOSTRAR_SOLO_FALLOS else "",
    ))
    print("Ctrl+C: detener y ver resumen | Ctrl+D: volver al firmware normal")
    print("=" * 78)

    try:
        firmware.main()
    except KeyboardInterrupt:
        monitor.imprimir_resumen()
    return monitor


#: Monitor en ejecucion, para inspeccionarlo desde el Shell tras Ctrl+C.
MONITOR = None

if __name__ == "__main__":
    ejecutar()
