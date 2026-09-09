"""
sniffer_rs485.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-07
Version: 1.0

Descripcion general
-------------------
Analizador pasivo del bus RS-485. Escucha con el conversor USB-RS485 SIN
transmitir nada, separa las tramas por el silencio de 3,5 caracteres que define
MODBus RTU, y las decodifica campo por campo.

Por que hace falta esta herramienta en la Parte 2
--------------------------------------------------
En la Parte 1 el maestro era la PC, asi que el monitor de tramas de QModMaster
mostraba todo el dialogo. En la Parte 2 el maestro pasa a ser un ESP32 y
QModMaster deja de ver nada: su monitor solo muestra lo que el propio QModMaster
transmite y recibe, no el trafico ajeno.

Peor todavia: QModMaster **no puede** quedar conectado al bus mientras el ESP32
maestro sondea. MODBus RTU admite un unico maestro; dos iniciadores producen
colisiones y errores de CRC en ambos. Ver PARTE-2.md §4.

Este script resuelve el problema poniendo el conversor USB-RS485 en modo
puramente receptor: RS-485 es un medio compartido, de modo que el adaptador
recibe electricamente todas las tramas aunque no participe del dialogo. Es el
equivalente en software de un analizador de protocolo.

Uso
---
    python sniffer_rs485.py COM5
    python sniffer_rs485.py COM5 --guardar captura.txt
    python sniffer_rs485.py /dev/ttyUSB0 --baudrate 9600

Ctrl+C para terminar; al salir imprime un resumen con el conteo por funcion y
la tasa de error de CRC.

Dependencias externas
---------------------
- Python 3 en la PC (no corre en el ESP32).
- pyserial:  pip install pyserial
- Modulo local modbus_tramas.py, en la misma carpeta.
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    print("Falta pyserial. Instalarlo con:\n\n    pip install pyserial\n")
    sys.exit(1)

import modbus_tramas


#: Bits que ocupa un caracter RTU 8N1 en la linea: 1 de arranque + 8 de datos +
#: 1 de relleno de paridad + 1 de parada. Se usa el valor conservador de 11 (y no
#: 10) por coherencia con el resto del proyecto: sobreestima levemente los
#: tiempos y por lo tanto deja del lado seguro al separar tramas.
BITS_POR_CARACTER = 11

#: Multiplo de tiempo de caracter que MODBus RTU define como fin de trama.
CARACTERES_SILENCIO_FIN_TRAMA = 3.5

#: Piso del silencio de fin de trama, en segundos. La especificacion fija
#: t3,5 = 1,750 ms como constante para baudrates superiores a 19200, porque el
#: calculo exacto deja de ser practicable. Se aplica el mismo piso aca.
SILENCIO_MINIMO_S = 0.00175

#: Tiempo de espera de lectura del puerto serie. Debe ser MENOR que el silencio
#: de fin de trama para poder detectarlo; se usa una fraccion holgada.
TIMEOUT_LECTURA_S = 0.0005


def calcular_silencio_fin_trama(baudrate):
    """
    Calcula la duracion del silencio que marca el fin de una trama RTU.

    En modo RTU no hay caracteres de inicio ni de fin: la trama se delimita
    exclusivamente por el tiempo que la linea permanece inactiva. Un silencio de
    3,5 tiempos de caracter indica que la trama termino.

    Parametros
    ----------
    baudrate : int
        Velocidad del bus en baudios.

    Retorna
    -------
    float
        Duracion del silencio de fin de trama, en segundos.

    Excepciones
    -----------
    ValueError
        Si el baudrate no es un entero positivo.

    Ejemplo de uso
    --------------
    >>> round(calcular_silencio_fin_trama(9600) * 1000, 2)
    4.01
    """
    if not isinstance(baudrate, int) or baudrate <= 0:
        raise ValueError("El baudrate debe ser un entero positivo, se recibio {!r}".format(baudrate))

    tiempo_caracter = BITS_POR_CARACTER / baudrate
    return max(tiempo_caracter * CARACTERES_SILENCIO_FIN_TRAMA, SILENCIO_MINIMO_S)


def clasificar_trama(trama):
    """
    Determina si una trama es una peticion del maestro o una respuesta de esclavo.

    Heuristica y su fundamento
    --------------------------
    MODBus RTU no marca en la trama quien la emitio: el mismo formato sirve para
    los dos sentidos. La distincion se hace por la LONGITUD y la estructura,
    porque las peticiones de las funciones 0x01 a 0x06 miden siempre 8 bytes,
    mientras que las respuestas de lectura llevan un byte de conteo y una carga
    de tamano variable.

    Caso ambiguo conocido: las respuestas a 0x05 y 0x06 son un eco identico a la
    peticion, tambien de 8 bytes. Es indistinguible por contenido, y se resuelve
    por el orden de aparicion: la primera es la peticion y la segunda el eco.

    Parametros
    ----------
    trama : bytes
        Trama completa, con CRC.

    Retorna
    -------
    str
        'PETICION', 'RESPUESTA', 'EXCEPCION' o 'INDETERMINADA'.

    Excepciones
    -----------
    Ninguna.
    """
    if len(trama) < 4:
        return "INDETERMINADA"

    codigo = trama[1]

    if codigo & 0x80:
        return "EXCEPCION"

    # Peticiones de lectura y escritura simple: exactamente 8 bytes.
    if codigo in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06) and len(trama) == 8:
        return "PETICION"

    # Respuestas de lectura: byte de conteo coherente con la longitud restante.
    if codigo in (0x01, 0x02, 0x03, 0x04) and len(trama) >= 5:
        if trama[2] == len(trama) - 5:
            return "RESPUESTA"

    return "INDETERMINADA"


def escuchar(puerto, baudrate, archivo_salida=None, decodificar=True):
    """
    Escucha el bus y muestra cada trama detectada hasta que se interrumpa.

    El adaptador NUNCA transmite: se abre el puerto solo para lectura y no se
    escribe un solo byte. Esto es lo que permite dejarlo conectado mientras el
    ESP32 maestro sondea, sin convertirse en un segundo maestro.

    Parametros
    ----------
    puerto : str
        Nombre del puerto serie del conversor USB-RS485 ('COM5', '/dev/ttyUSB0').
    baudrate : int
        Velocidad del bus. Debe coincidir con la de todos los nodos.
    archivo_salida : str, opcional
        Ruta donde guardar la captura en texto. Si se omite, solo se muestra.
    decodificar : bool, opcional
        Si es True (por defecto), agrega el desglose campo por campo de cada
        trama. Con False solo lista los bytes, mas compacto para capturas largas.

    Retorna
    -------
    dict
        Estadisticas de la sesion: total de tramas, cuantas por codigo de
        funcion y cuantas fallaron la verificacion de CRC.

    Excepciones
    -----------
    serial.SerialException
        Si el puerto no existe o esta ocupado por otro programa (tipicamente,
        QModMaster con la conexion abierta).
    """
    silencio_fin_trama = calcular_silencio_fin_trama(baudrate)

    estadisticas = {"total": 0, "crc_invalido": 0, "por_funcion": {}}
    salida = open(archivo_salida, "w", encoding="utf-8") if archivo_salida else None

    def emitir(texto):
        """Escribe una linea por pantalla y, si corresponde, al archivo."""
        print(texto)
        if salida:
            salida.write(texto + "\n")

    emitir("=" * 70)
    emitir("SNIFFER PASIVO RS-485 / MODBus RTU")
    emitir("Puerto: {}  |  {} baudios 8N1".format(puerto, baudrate))
    emitir("Silencio de fin de trama (t3,5): {:.2f} ms".format(silencio_fin_trama * 1000))
    emitir("El adaptador NO transmite: es seguro dejarlo mientras el maestro sondea.")
    emitir("Ctrl+C para terminar.")
    emitir("=" * 70)

    conexion = serial.Serial(
        port=puerto,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=TIMEOUT_LECTURA_S,
    )

    buffer = bytearray()
    instante_ultimo_byte = time.monotonic()

    try:
        while True:
            datos = conexion.read(256)

            if datos:
                buffer.extend(datos)
                instante_ultimo_byte = time.monotonic()
                continue

            # No llego nada en esta vuelta: se evalua si el silencio acumulado
            # ya alcanza t3,5, en cuyo caso el buffer contiene una trama completa.
            hay_silencio = (time.monotonic() - instante_ultimo_byte) >= silencio_fin_trama
            if buffer and hay_silencio:
                _procesar_trama(bytes(buffer), estadisticas, emitir, decodificar)
                buffer = bytearray()

    except KeyboardInterrupt:
        # Salida limpia: es la forma normal de terminar la captura.
        if buffer:
            _procesar_trama(bytes(buffer), estadisticas, emitir, decodificar)
        emitir("")
        emitir(_formatear_resumen(estadisticas))

    finally:
        conexion.close()
        if salida:
            salida.close()

    return estadisticas


def _procesar_trama(trama, estadisticas, emitir, decodificar):
    """
    Muestra una trama detectada y actualiza las estadisticas.

    Funcion auxiliar de escuchar(); no forma parte de la interfaz publica.

    Parametros
    ----------
    trama : bytes
        Trama completa detectada entre dos silencios.
    estadisticas : dict
        Acumulador que se actualiza en el lugar.
    emitir : callable
        Funcion que recibe una cadena y la vuelca a pantalla y archivo.
    decodificar : bool
        Si se agrega el desglose campo por campo.

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna.
    """
    marca = time.strftime("%H:%M:%S")
    hexadecimal = " ".join("{:02X}".format(b) for b in trama)

    # Una trama de menos de 4 bytes no puede ser MODBus valida (1 de direccion,
    # 1 de funcion, 2 de CRC). Suele ser ruido de la conmutacion de DE/RE.
    if len(trama) < 4:
        emitir("{} | {:<12} | {}".format(marca, "RUIDO", hexadecimal))
        return

    estadisticas["total"] += 1

    crc_ok = modbus_tramas.verificar_crc(trama)
    if not crc_ok:
        estadisticas["crc_invalido"] += 1

    codigo = trama[1] & 0x7F
    estadisticas["por_funcion"][codigo] = estadisticas["por_funcion"].get(codigo, 0) + 1

    tipo = clasificar_trama(trama)
    marca_crc = "" if crc_ok else "  <-- CRC INVALIDO"

    emitir("{} | {:<12} | ID={} FC=0x{:02X} | {}{}".format(
        marca, tipo, trama[0], trama[1], hexadecimal, marca_crc))

    if decodificar:
        for linea in modbus_tramas.decodificar(trama).splitlines()[3:]:
            emitir("             {}".format(linea))
        emitir("")


def _formatear_resumen(estadisticas):
    """
    Arma el resumen final de la captura.

    Parametros
    ----------
    estadisticas : dict
        Acumulador devuelto por escuchar().

    Retorna
    -------
    str
        Texto multilinea con el resumen.

    Excepciones
    -----------
    Ninguna.
    """
    lineas = ["=" * 70, "RESUMEN DE LA CAPTURA", "=" * 70]
    lineas.append("Tramas detectadas: {}".format(estadisticas["total"]))

    if estadisticas["total"]:
        porcentaje = estadisticas["crc_invalido"] * 100.0 / estadisticas["total"]
        lineas.append("Tramas con CRC invalido: {} ({:.2f} %)".format(
            estadisticas["crc_invalido"], porcentaje))
        lineas.append("")
        lineas.append("Por codigo de funcion:")
        for codigo in sorted(estadisticas["por_funcion"]):
            nombre = modbus_tramas.FUNCIONES.get(codigo, ("desconocida", ""))[0]
            lineas.append("  0x{:02X}  {:<28} {} tramas".format(
                codigo, nombre, estadisticas["por_funcion"][codigo]))

    lineas.append("=" * 70)
    return "\n".join(lineas)


def main():
    """
    Punto de entrada de la herramienta.

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
    analizador = argparse.ArgumentParser(
        description="Analizador pasivo de un bus RS-485 con MODBus RTU.",
    )
    analizador.add_argument(
        "puerto",
        help="Puerto serie del conversor USB-RS485 (por ejemplo COM5 o /dev/ttyUSB0)",
    )
    analizador.add_argument(
        "--baudrate", type=int, default=9600,
        help="Velocidad del bus (por defecto 9600, igual que el resto del proyecto)",
    )
    analizador.add_argument(
        "--guardar", metavar="ARCHIVO", default=None,
        help="Guardar la captura en un archivo de texto para adjuntar al informe",
    )
    analizador.add_argument(
        "--compacto", action="store_true",
        help="Listar solo los bytes, sin el desglose campo por campo",
    )
    argumentos = analizador.parse_args()

    try:
        escuchar(
            puerto=argumentos.puerto,
            baudrate=argumentos.baudrate,
            archivo_salida=argumentos.guardar,
            decodificar=not argumentos.compacto,
        )
        return 0

    except serial.SerialException as error:
        print("No se pudo abrir el puerto {}: {}".format(argumentos.puerto, error))
        print()
        print("Causas habituales:")
        print("  - El puerto esta ocupado por otro programa (cerrar la conexion")
        print("    de QModMaster: Commands -> Disconnect).")
        print("  - Es el COM del ESP32 y no el del conversor USB-RS485.")
        return 1

    except ValueError as error:
        print("Parametro invalido: {}".format(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
