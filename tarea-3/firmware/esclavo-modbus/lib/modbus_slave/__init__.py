"""
modbus_slave — stack MODBus RTU propio del esclavo (Tarea 3, invariante I-01).

Modulos:
    crc16         generacion y verificacion del CRC-16/MODBUS
    data_model    las cuatro tablas de datos y sus reglas de acceso
    frame_parser  tiempos t1,5/t3,5, delimitacion por silencio y procesamiento de peticiones

Sin dependencias del hardware: se importa igual en MicroPython (ESP32, carpeta /lib)
y en CPython (pruebas en la PC). La capa de hardware esta en src/main.py.
"""

#: Version de la interfaz del paquete. main.py la verifica al arrancar: el despliegue
#: es manual con Thonny y olvidar un archivo debe detectarse con un mensaje claro
#: (mismo mecanismo que diagnostico.VERSION en la Tarea 1).
VERSION = 1
