"""
modbus_tramas.py
Autor: Francisco Bevilacqua
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Herramienta de escritorio para calcular el CRC-16/MODBUS y decodificar tramas
MODBus RTU byte a byte. Corre en CPython (la PC), NO en el ESP32.

Cumple dos requisitos explicitos de la consigna:

  - "Analisis de Tramas MODBus RTU: explicar detalladamente el intercambio de
    mensajes y la estructura de las tramas transmitidas en el bus RS485."
  - Pregunta de evaluacion 2: "Que informacion genera el algoritmo CRC? Su
    calculo es automatico por hardware o requiere implementacion por software?"

Implementar el CRC a mano, en vez de citar la teoria, permite responder esa
pregunta con evidencia propia: el algoritmo esta en las ~15 lineas de
calcular_crc16() y no en ningun periferico del ESP32.

Uso
---
    python modbus_tramas.py                      # autoverificacion + ejemplos
    python modbus_tramas.py "01 04 00 00 00 01 31 CA"   # decodifica una trama

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""

import sys


# =============================================================================
# 1. CRC-16/MODBUS
# =============================================================================

#: Polinomio generador en forma REFLEJADA. El polinomio estandar del CRC-16-IBM
#: es 0x8005 (x^16 + x^15 + x^2 + 1); MODBus procesa los bits del byte menos
#: significativo primero, y para esa direccion de procesamiento el polinomio se
#: escribe invertido bit a bit, quedando 0xA001. Usar 0x8005 con desplazamiento
#: a la derecha es el error clasico al implementar este CRC a mano.
POLINOMIO_REFLEJADO = 0xA001

#: Valor inicial del registro. MODBus arranca con todos los bits en uno, no en
#: cero. Un valor inicial de 0x0000 haria que el CRC no detecte ceros anadidos
#: al principio del mensaje.
VALOR_INICIAL = 0xFFFF


def calcular_crc16(datos):
    """
    Calcula el CRC-16/MODBUS de una secuencia de bytes.

    Que informacion genera
    ----------------------
    NO transporta informacion util del proceso. Genera una firma de 16 bits
    derivada de todos los bytes del mensaje, que permite al receptor detectar si
    la trama se altero en transito (ruido electrico, un byte perdido, una
    colision). Es DETECCION de error, no correccion: el receptor descarta la
    trama y espera que el maestro reintente. Su poder de deteccion cubre todos
    los errores de rafaga de hasta 16 bits y el 99,998 % de las rafagas mas
    largas.

    Es automatico por hardware o por software
    -----------------------------------------
    Por SOFTWARE en este proyecto. El ESP32 no expone un periferico de CRC
    utilizable desde MicroPython para este polinomio, de modo que el calculo lo
    hace la libreria umodbus recorriendo el mensaje byte a byte, exactamente con
    el algoritmo de esta funcion. Algunos microcontroladores (por ejemplo varios
    STM32) si tienen una unidad de CRC por hardware, pero suele estar cableada al
    polinomio de Ethernet (0x04C11DB7) y no al de MODBus, por lo que ni siquiera
    en esos casos se puede usar directamente.

    Algoritmo (procesamiento por bits, sin tabla)
    ---------------------------------------------
    Se elige la version sin tabla de consulta porque hace visible el mecanismo,
    que es lo que se defiende oralmente. La version con tabla de 256 entradas es
    unas 8 veces mas rapida y es la que usan las librerias de produccion, a costa
    de 512 bytes de memoria y de ocultar el algoritmo.

        1. Registro = 0xFFFF
        2. Para cada byte del mensaje:
             registro = registro XOR byte
             repetir 8 veces:
               si el bit menos significativo del registro es 1:
                  registro = (registro >> 1) XOR 0xA001
               si no:
                  registro = registro >> 1
        3. El resultado es el registro final

    Parametros
    ----------
    datos : bytes | bytearray
        Mensaje completo SIN el campo CRC: direccion de esclavo, codigo de
        funcion y datos.

    Retorna
    -------
    int
        Valor del CRC como entero de 16 bits (0x0000 a 0xFFFF).

    Excepciones
    -----------
    TypeError
        Si `datos` no es una secuencia de enteros de 0 a 255.

    Ejemplo de uso
    --------------
    >>> hex(calcular_crc16(b"123456789"))
    '0x4b37'
    """
    registro = VALOR_INICIAL

    for byte in datos:
        registro ^= byte
        for _ in range(8):
            if registro & 0x0001:
                registro = (registro >> 1) ^ POLINOMIO_REFLEJADO
            else:
                registro >>= 1

    return registro & 0xFFFF


def crc16_a_bytes(crc):
    """
    Convierte el CRC a los dos bytes tal como viajan en la trama.

    Punto sutil y muy preguntado en defensa: el CRC es el UNICO campo
    multi-byte de MODBus RTU que se transmite LITTLE-ENDIAN (byte menos
    significativo primero). Todos los demas campos de 16 bits — direccion de
    registro, cantidad, valor de un registro — viajan BIG-ENDIAN. Invertir este
    orden produce un CRC que el receptor rechaza siempre, con el sintoma
    desconcertante de "el esclavo nunca responde aunque el cableado esta bien".

    Parametros
    ----------
    crc : int
        Valor de 16 bits devuelto por calcular_crc16().

    Retorna
    -------
    bytes
        Dos bytes en el orden de transmision: (CRC_lo, CRC_hi).

    Excepciones
    -----------
    Ninguna.

    Ejemplo de uso
    --------------
    >>> crc16_a_bytes(0x4B37).hex(" ")
    '37 4b'
    """
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def agregar_crc(mensaje):
    """
    Devuelve la trama completa: el mensaje con su CRC anexado.

    Parametros
    ----------
    mensaje : bytes | bytearray
        Direccion de esclavo + codigo de funcion + datos.

    Retorna
    -------
    bytes
        Trama lista para transmitir por el bus.

    Excepciones
    -----------
    Ninguna.
    """
    return bytes(mensaje) + crc16_a_bytes(calcular_crc16(mensaje))


def verificar_crc(trama):
    """
    Verifica el CRC de una trama recibida completa.

    Parametros
    ----------
    trama : bytes | bytearray
        Trama completa, incluidos los dos bytes de CRC finales.

    Retorna
    -------
    bool
        True si el CRC calculado sobre el cuerpo coincide con el transmitido.

    Excepciones
    -----------
    ValueError
        Si la trama tiene menos de 4 bytes (el minimo teorico: 1 de direccion,
        1 de funcion y 2 de CRC).
    """
    if len(trama) < 4:
        raise ValueError(
            "Una trama MODBus RTU valida tiene al menos 4 bytes, se recibieron {}".format(len(trama))
        )

    cuerpo = trama[:-2]
    crc_recibido = trama[-2] | (trama[-1] << 8)
    return calcular_crc16(cuerpo) == crc_recibido


# =============================================================================
# 2. DECODIFICACION DE TRAMAS
# =============================================================================

#: Descripcion de los codigos de funcion empleados en este trabajo practico.
FUNCIONES = {
    0x01: ("Read Coils", "Lee salidas digitales (area Coils, Modicon 0xxxx)"),
    0x02: ("Read Discrete Inputs", "Lee entradas digitales (area Discrete Inputs, Modicon 1xxxx)"),
    0x03: ("Read Holding Registers", "Lee registros de retencion (Modicon 4xxxx)"),
    0x04: ("Read Input Registers", "Lee registros de entrada (Modicon 3xxxx)"),
    0x05: ("Write Single Coil", "Escribe una salida digital: 0xFF00 = ON, 0x0000 = OFF"),
    0x06: ("Write Single Register", "Escribe un registro de retencion de 16 bits"),
    0x0F: ("Write Multiple Coils", "Escribe varias salidas digitales de una vez"),
    0x10: ("Write Multiple Registers", "Escribe varios registros de una vez"),
}

#: Codigos de excepcion de la especificacion MODBus. Una respuesta de excepcion
#: se reconoce porque el codigo de funcion vuelve con el bit 7 en uno
#: (por ejemplo, 0x04 se convierte en 0x84).
EXCEPCIONES = {
    0x01: "ILLEGAL FUNCTION — el esclavo no implementa ese codigo de funcion",
    0x02: "ILLEGAL DATA ADDRESS — la direccion solicitada no existe en el esclavo",
    0x03: "ILLEGAL DATA VALUE — el valor esta fuera del rango admitido",
    0x04: "SLAVE DEVICE FAILURE — error irrecuperable durante el procesamiento",
    0x05: "ACKNOWLEDGE — peticion aceptada, en curso, requiere sondeo posterior",
    0x06: "SLAVE DEVICE BUSY — el esclavo esta ocupado, reintentar mas tarde",
}


def parsear_hex(texto):
    """
    Convierte una cadena hexadecimal en bytes, tolerando varios formatos.

    Acepta "01 04 00 00", "01,04,00,00", "0104 0000" y "0x01 0x04".

    Parametros
    ----------
    texto : str
        Representacion hexadecimal de la trama.

    Retorna
    -------
    bytes
        Los bytes de la trama.

    Excepciones
    -----------
    ValueError
        Si el texto contiene caracteres no hexadecimales o un numero impar de
        digitos.
    """
    limpio = (
        texto.replace("0x", "").replace("0X", "")
        .replace(",", "").replace("-", "")
        .replace(" ", "").replace("\t", "").replace("\n", "")
    )
    if len(limpio) % 2 != 0:
        raise ValueError(
            "La trama tiene {} digitos hexadecimales (numero impar); "
            "cada byte necesita exactamente 2".format(len(limpio))
        )
    try:
        return bytes.fromhex(limpio)
    except ValueError:
        raise ValueError("La cadena contiene caracteres que no son hexadecimales: {!r}".format(texto))


def decodificar(trama):
    """
    Produce una explicacion campo por campo de una trama MODBus RTU.

    Pensada para pegar su salida directamente en el informe, junto a la captura
    del analizador logico o de Modbus Poll que dio origen a la trama.

    Parametros
    ----------
    trama : bytes | bytearray
        Trama completa incluyendo el CRC.

    Retorna
    -------
    str
        Texto multilinea con el desglose de la trama.

    Excepciones
    -----------
    ValueError
        Si la trama es demasiado corta para ser valida.
    """
    if len(trama) < 4:
        raise ValueError(
            "Una trama MODBus RTU valida tiene al menos 4 bytes, se recibieron {}".format(len(trama))
        )

    lineas = []
    lineas.append("TRAMA: " + " ".join("{:02X}".format(b) for b in trama))
    lineas.append("Longitud: {} bytes".format(len(trama)))
    lineas.append("-" * 70)

    # --- Campo 1: direccion de esclavo (1 byte) ------------------------------
    direccion = trama[0]
    if direccion == 0:
        nota = "difusion (broadcast): ningun esclavo responde"
    elif 1 <= direccion <= 247:
        nota = "Unit ID del esclavo destinatario"
    else:
        nota = "FUERA DE RANGO — el maximo valido es 247"
    lineas.append("[0]    {:02X}        Direccion de esclavo = {}  ({})".format(
        direccion, direccion, nota))

    # --- Campo 2: codigo de funcion (1 byte) ---------------------------------
    codigo = trama[1]
    es_excepcion = bool(codigo & 0x80)

    if es_excepcion:
        original = codigo & 0x7F
        nombre = FUNCIONES.get(original, ("desconocida", ""))[0]
        lineas.append("[1]    {:02X}        RESPUESTA DE EXCEPCION (bit 7 en uno)".format(codigo))
        lineas.append("                 Funcion original: {:02X} ({})".format(original, nombre))
        if len(trama) >= 3:
            cod_exc = trama[2]
            lineas.append("[2]    {:02X}        Codigo de excepcion = {}".format(cod_exc, cod_exc))
            lineas.append("                 {}".format(
                EXCEPCIONES.get(cod_exc, "codigo de excepcion no estandar")))
    else:
        nombre, detalle = FUNCIONES.get(codigo, ("desconocida", "no usada en este trabajo"))
        lineas.append("[1]    {:02X}        Codigo de funcion = {} ({})".format(codigo, codigo, nombre))
        lineas.append("                 {}".format(detalle))
        lineas.extend(_decodificar_datos(trama, codigo))

    # --- Campo final: CRC (2 bytes, little-endian) ---------------------------
    crc_recibido = trama[-2] | (trama[-1] << 8)
    crc_calculado = calcular_crc16(trama[:-2])
    valido = crc_recibido == crc_calculado

    lineas.append("-" * 70)
    lineas.append("[{:>2}-{:>2}] {:02X} {:02X}     CRC-16 = 0x{:04X}  (transmitido LITTLE-ENDIAN:".format(
        len(trama) - 2, len(trama) - 1, trama[-2], trama[-1], crc_recibido))
    lineas.append("                 byte bajo 0x{:02X} primero, luego el alto 0x{:02X})".format(
        crc_recibido & 0xFF, (crc_recibido >> 8) & 0xFF))
    lineas.append("                 CRC calculado sobre los {} bytes previos = 0x{:04X}".format(
        len(trama) - 2, crc_calculado))
    lineas.append("                 VERIFICACION: {}".format(
        "CORRECTA — la trama es integra" if valido
        else "FALLIDA — la trama se corrompio y debe descartarse"))

    return "\n".join(lineas)


def _decodificar_datos(trama, codigo):
    """
    Decodifica el campo de datos segun el codigo de funcion.

    Funcion auxiliar de decodificar(); no forma parte de la interfaz publica.

    Parametros
    ----------
    trama : bytes
        Trama completa.
    codigo : int
        Codigo de funcion ya extraido.

    Retorna
    -------
    list[str]
        Lineas de explicacion del campo de datos.

    Excepciones
    -----------
    Ninguna. Si la trama es mas corta de lo esperado, se informa en el texto.
    """
    lineas = []
    datos = trama[2:-2]

    # Peticiones de lectura (0x01-0x04) y escrituras simples (0x05, 0x06)
    # comparten el formato "direccion de 16 bits + valor/cantidad de 16 bits".
    if codigo in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06) and len(datos) == 4:
        direccion = (datos[0] << 8) | datos[1]
        segundo = (datos[2] << 8) | datos[3]

        modicon = _a_modicon(codigo, direccion)
        lineas.append("[2-3]  {:02X} {:02X}     Direccion inicial = 0x{:04X} ({})  {}".format(
            datos[0], datos[1], direccion, direccion, modicon))
        lineas.append("                 BIG-ENDIAN: primero el byte alto 0x{:02X}, luego 0x{:02X}".format(
            datos[0], datos[1]))

        if codigo == 0x05:
            estado = "ON (encendido)" if segundo == 0xFF00 else (
                "OFF (apagado)" if segundo == 0x0000 else "VALOR INVALIDO")
            lineas.append("[4-5]  {:02X} {:02X}     Valor = 0x{:04X} -> {}".format(
                datos[2], datos[3], segundo, estado))
            lineas.append("                 La funcion 0x05 solo admite 0xFF00 y 0x0000,")
            lineas.append("                 no 0x0001: cualquier otro valor debe rechazarse")
            lineas.append("                 con excepcion 03 (ILLEGAL DATA VALUE)")
        elif codigo == 0x06:
            lineas.append("[4-5]  {:02X} {:02X}     Valor a escribir = {} (0x{:04X})".format(
                datos[2], datos[3], segundo, segundo))
            lineas.append("                 BIG-ENDIAN dentro del registro (MSB primero)")
        else:
            lineas.append("[4-5]  {:02X} {:02X}     Cantidad a leer = {} elemento(s)".format(
                datos[2], datos[3], segundo))

    # Respuestas de lectura: byte de conteo seguido de los datos.
    elif codigo in (0x01, 0x02, 0x03, 0x04) and len(datos) >= 1:
        conteo = datos[0]
        carga = datos[1:]
        lineas.append("[2]    {:02X}        Cantidad de bytes de datos que siguen = {}".format(
            conteo, conteo))

        if codigo in (0x01, 0x02):
            # Areas de bits: cada byte empaqueta hasta 8 estados, el primer
            # elemento solicitado en el bit menos significativo.
            for i, byte in enumerate(carga):
                bits = " ".join(str((byte >> b) & 1) for b in range(7, -1, -1))
                lineas.append("[{}]    {:02X}        Bits (b7..b0): {}".format(3 + i, byte, bits))
                lineas.append("                 El primer elemento pedido esta en el bit 0 = {}".format(
                    byte & 1))
        else:
            # Areas de registros: pares de bytes big-endian.
            for i in range(0, len(carga) - 1, 2):
                valor = (carga[i] << 8) | carga[i + 1]
                lineas.append("[{}-{}]  {:02X} {:02X}     Registro {} = {} (0x{:04X})".format(
                    3 + i, 4 + i, carga[i], carga[i + 1], i // 2, valor, valor))
                lineas.append("                 MSB=0x{:02X} primero, LSB=0x{:02X} despues (BIG-ENDIAN)".format(
                    carga[i], carga[i + 1]))
    else:
        lineas.append("       {}  Campo de datos ({} bytes)".format(
            " ".join("{:02X}".format(b) for b in datos), len(datos)))

    return lineas


def _a_modicon(codigo, offset):
    """
    Traduce el offset de la trama a la notacion Modicon correspondiente.

    Parametros
    ----------
    codigo : int
        Codigo de funcion, que determina el area de datos.
    offset : int
        Direccion tal como viaja en la trama (base 0).

    Retorna
    -------
    str
        Texto con la direccion Modicon equivalente, o cadena vacia si el codigo
        no corresponde a un area conocida.

    Excepciones
    -----------
    Ninguna.
    """
    if codigo in (0x01, 0x05, 0x0F):
        return "-> Modicon {:05d}  (area Coils)".format(offset + 1)
    if codigo == 0x02:
        return "-> Modicon {:05d}  (area Discrete Inputs)".format(10001 + offset)
    if codigo == 0x04:
        return "-> Modicon {:05d}  (area Input Registers)".format(30001 + offset)
    if codigo in (0x03, 0x06, 0x10):
        return "-> Modicon {:05d}  (area Holding Registers)".format(40001 + offset)
    return ""


# =============================================================================
# 3. AUTOVERIFICACION Y EJEMPLOS
# =============================================================================

def autoverificar():
    """
    Ejecuta los casos de prueba del calculo de CRC.

    Casos cubiertos:
      1. Vector de prueba estandar del CRC-16/MODBUS ("123456789" -> 0x4B37),
         publicado en el catalogo de algoritmos CRC. Es el que valida que la
         implementacion sea realmente CRC-16/MODBUS y no otra variante.
      2. Ida y vuelta: una trama a la que se le agrega el CRC debe verificar bien.
      3. Deteccion de error: alterar un solo bit debe invalidar el CRC.
      4. Trama demasiado corta: debe lanzar ValueError.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True si todos los casos pasaron.

    Excepciones
    -----------
    Ninguna.
    """
    resultados = []

    # Caso 1 — vector de prueba estandar.
    obtenido = calcular_crc16(b"123456789")
    resultados.append((
        "CRC de '123456789' = 0x4B37 (vector estandar)",
        obtenido == 0x4B37,
        "obtenido 0x{:04X}".format(obtenido),
    ))

    # Caso 2 — ida y vuelta sobre una trama real del trabajo.
    peticion = agregar_crc(bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x01]))
    resultados.append((
        "Trama con CRC agregado verifica correctamente",
        verificar_crc(peticion),
        peticion.hex(" ").upper(),
    ))

    # Caso 3 — deteccion de un error de un solo bit.
    corrupta = bytearray(peticion)
    corrupta[3] ^= 0x01          # se invierte el bit menos significativo
    resultados.append((
        "Un bit alterado invalida el CRC",
        not verificar_crc(bytes(corrupta)),
        bytes(corrupta).hex(" ").upper(),
    ))

    # Caso 4 — trama demasiado corta.
    try:
        verificar_crc(b"\x01\x02")
        caso4 = False
        detalle = "no lanzo excepcion"
    except ValueError:
        caso4 = True
        detalle = "ValueError como se esperaba"
    resultados.append(("Trama de menos de 4 bytes es rechazada", caso4, detalle))

    print("AUTOVERIFICACION DEL CALCULO DE CRC-16/MODBUS")
    print("=" * 70)
    todos_ok = True
    for descripcion, ok, detalle in resultados:
        print("  [{}] {}".format("OK  " if ok else "FALLA", descripcion))
        print("         {}".format(detalle))
        todos_ok = todos_ok and ok
    print("=" * 70)
    print("Resultado: {}".format("TODOS LOS CASOS PASARON" if todos_ok else "HAY CASOS FALLIDOS"))
    return todos_ok


#: Tramas de ejemplo del trabajo practico, con su descripcion. Se generan con
#: CRC calculado, de modo que sirven tanto de documentacion como de referencia
#: para comparar contra lo que efectivamente se capture en el bus.
EJEMPLOS = [
    (bytes([0x01, 0x02, 0x00, 0x00, 0x00, 0x01]),
     "Maestro -> Esclavo 1: leer el switch (Discrete Input 10001)"),
    (bytes([0x01, 0x02, 0x01, 0x01]),
     "Esclavo 1 -> Maestro: el switch esta accionado (bit 0 = 1)"),
    (bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x01]),
     "Maestro -> Esclavo 1: leer el potenciometro (Input Register 30001)"),
    (bytes([0x01, 0x04, 0x02, 0x08, 0x00]),
     "Esclavo 1 -> Maestro: el ADC vale 2048 (0x0800), medio recorrido"),
    (bytes([0x02, 0x05, 0x00, 0x00, 0xFF, 0x00]),
     "Maestro -> Esclavo 2: encender el LED 1 (Coil 00001)"),
    (bytes([0x02, 0x06, 0x00, 0x00, 0x00, 0x80]),
     "Maestro -> Esclavo 2: PWM del LED 2 al 50 % (128 = 0x0080, HR 40001)"),
    (bytes([0x01, 0x84, 0x02]),
     "Esclavo 1 -> Maestro: excepcion 02, direccion de dato ilegal"),
]


def mostrar_ejemplos():
    """
    Imprime el desglose de todas las tramas de ejemplo del trabajo.

    Su salida es material directo para la seccion "Analisis de tramas" del
    informe tecnico.

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
    for cuerpo, descripcion in EJEMPLOS:
        trama = agregar_crc(cuerpo)
        print()
        print("#" * 70)
        print("# {}".format(descripcion))
        print("#" * 70)
        print(decodificar(trama))


def main():
    """
    Punto de entrada de la herramienta.

    Sin argumentos ejecuta la autoverificacion y muestra los ejemplos.
    Con un argumento, lo interpreta como una trama en hexadecimal y la decodifica.

    Parametros
    ----------
    Ninguno (lee sys.argv).

    Retorna
    -------
    int
        Codigo de salida del proceso: 0 si todo fue bien, 1 ante un error.

    Excepciones
    -----------
    Ninguna se propaga: los errores se informan y se traducen a codigo de salida.
    """
    if len(sys.argv) > 1:
        try:
            trama = parsear_hex(" ".join(sys.argv[1:]))
            print(decodificar(trama))
            return 0
        except ValueError as error:
            print("Error: {}".format(error))
            return 1

    ok = autoverificar()
    mostrar_ejemplos()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
