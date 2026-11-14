"""
crc16.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
CRC-16/MODBUS propio: generacion (al transmitir) y verificacion (al recibir).
Cumple el invariante I-01 de la Tarea 3: ninguna biblioteca de protocolo calcula
el CRC por nosotros.

Parametros del algoritmo (MODBus over Serial Line V1.02, §6.2.2):
  polinomio 0x8005 en forma REFLEJADA = 0xA001 (los bits se procesan del menos
  significativo al mas significativo) · valor inicial 0xFFFF · sin XOR final.
  En la trama el CRC viaja con el BYTE BAJO PRIMERO: es la unica excepcion al
  big-endian de MODBus.

Dos implementaciones con el mismo resultado:
  crc16_bit_a_bit() -> la definicion del algoritmo, ocho iteraciones por byte.
                       Es la que se explica en la defensa.
  crc16()           -> por tabla de 256 entradas, una iteracion por byte. Es la que
                       usa el firmware: en la T1 el costo de computo del interprete fue
                       de ~12,8 ms por transaccion (ADR-010, salvaguarda b).
Las pruebas (test/prueba_crc.py) exigen que las dos coincidan con los vectores
golden de tests/fixtures/crc_vectors.json, generados con oraculos independientes.

Diagrama de flujo: bloques [DF-1.9] (verificacion) y [DF-1.15] (generacion).

Dependencias externas
---------------------
Ninguna. Corre igual en MicroPython (ESP32) y en CPython (pruebas en la PC).
"""

from array import array

#: Polinomio generador 0x8005 escrito en forma reflejada.
POLINOMIO_REFLEJADO = 0xA001

#: Valor inicial del registro. Con 0x0000 el CRC no detectaria ceros agregados al
#: comienzo del mensaje (tarea-1/docs/protocolo-comunicacion.md §7.3).
VALOR_INICIAL = 0xFFFF


def crc16_bit_a_bit(datos, inicio=0, fin=None):
    """
    Calcula el CRC-16/MODBUS procesando bit por bit (definicion del algoritmo).

    Parametros:
        datos (bytes | bytearray | memoryview): mensaje.
        inicio (int): primer indice incluido.
        fin (int | None): indice final excluido; None = hasta el final.
    Retorna:
        int: valor del registro CRC, 0x0000-0xFFFF.
    Excepciones:
        Ninguna.
    Ejemplo:
        >>> hex(crc16_bit_a_bit(b"123456789"))
        '0x4b37'
    """
    if fin is None:
        fin = len(datos)
    registro = VALOR_INICIAL
    for i in range(inicio, fin):
        registro ^= datos[i]
        for _ in range(8):
            # Si el bit que sale por la derecha es 1, se "resta" (XOR) el polinomio.
            if registro & 0x0001:
                registro = (registro >> 1) ^ POLINOMIO_REFLEJADO
            else:
                registro >>= 1
    return registro & 0xFFFF


def _construir_tabla():
    """
    Precalcula el efecto de los 8 desplazamientos para cada valor posible de un byte.

    Retorna:
        array('H'): 256 enteros de 16 bits (512 bytes de RAM; una lista de int
        ocuparia varias veces mas en MicroPython).
    """
    tabla = array("H", [0] * 256)
    for valor in range(256):
        registro = valor
        for _ in range(8):
            if registro & 0x0001:
                registro = (registro >> 1) ^ POLINOMIO_REFLEJADO
            else:
                registro >>= 1
        tabla[valor] = registro
    return tabla


#: Tabla construida una sola vez, al importar el modulo.
_TABLA = _construir_tabla()


def crc16(datos, inicio=0, fin=None):
    """
    Calcula el CRC-16/MODBUS por tabla (version que usa el firmware).

    Equivalencia con la version bit a bit: XOR del byte en la parte baja del registro,
    y los 8 desplazamientos con sus XOR condicionales se reemplazan por una consulta.

    Parametros:
        datos (bytes | bytearray | memoryview): mensaje.
        inicio (int): primer indice incluido.
        fin (int | None): indice final excluido; None = hasta el final.
    Retorna:
        int: valor del registro CRC, 0x0000-0xFFFF.
    Excepciones:
        Ninguna.
    """
    if fin is None:
        fin = len(datos)
    registro = VALOR_INICIAL
    tabla = _TABLA
    for i in range(inicio, fin):
        registro = (registro >> 8) ^ tabla[(registro ^ datos[i]) & 0xFF]
    return registro


def agregar_crc(mensaje):
    """
    [DF-1.15] Genera el CRC del mensaje y lo agrega al final, byte bajo primero.

    Parametros:
        mensaje (bytes | bytearray): direccion + PDU, sin CRC.
    Retorna:
        bytearray: mensaje + CRC (2 bytes mas).
    Excepciones:
        Ninguna.
    Ejemplo:
        >>> bytes(agregar_crc(bytes([1, 4, 0, 0, 0, 1])))  # 01 04 00 00 00 01 31 CA
        b'\\x01\\x04\\x00\\x00\\x00\\x011\\xca'
    """
    trama = bytearray(mensaje)
    valor = crc16(trama)
    trama.append(valor & 0xFF)          # byte bajo primero
    trama.append((valor >> 8) & 0xFF)   # luego el alto
    return trama


def verificar_crc(trama):
    """
    [DF-1.9] Verifica el CRC de una trama recibida completa.

    Se recalcula sobre los n-2 primeros bytes y se compara con los dos ultimos,
    reconstruidos como (alto << 8) | bajo.

    Parametros:
        trama (bytes | bytearray | memoryview): trama completa con CRC.
    Retorna:
        bool: True si el CRC coincide. False si no coincide o si la trama tiene
        menos de 4 bytes (direccion + funcion + CRC es el minimo posible).
    Excepciones:
        Ninguna.
    """
    n = len(trama)
    if n < 4:
        return False
    recibido = trama[n - 2] | (trama[n - 1] << 8)
    return crc16(trama, 0, n - 2) == recibido
