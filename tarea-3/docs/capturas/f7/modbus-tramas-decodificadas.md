# MODBus RTU: peticiones y respuestas decodificadas byte a byte

> **Origen**: `modbus-rtu-tcpdev.pcapng`, 5 s capturados con `dumpcap` en el loopback de la PC (banco virtual,
> commit del 2026-11-12), entre el maestro (Node-RED) y el simulador del esclavo, que ejecuta el stack del firmware.
> Los bytes son **exactamente la trama RTU** que va al bus RS-485 (dirección, función, datos y CRC-16): el
> transporte de desarrollo es TCP, así que **no** hay temporización de línea (silencio t3,5, bits de start y
> stop). La captura del bus físico con `tarea-1/herramientas/sniffer_rs485.py` queda **pendiente del banco**.
>
> La decodificación es la salida textual de `tarea-1/herramientas/modbus_tramas.py`, el decodificador de la
> Tarea 1, con el CRC recalculado y verificado.

## FC 01: petición en t = 0.0619 s, respuesta 15.5 ms después

```text
TRAMA: 01 01 00 00 00 01 FD CA
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    01        Codigo de funcion = 1 (Read Coils)
                 Lee salidas digitales (area Coils, Modicon 0xxxx)
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 00001  (area Coils)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 01     Cantidad a leer = 1 elemento(s)
----------------------------------------------------------------------
[ 6- 7] FD CA     CRC-16 = 0xCAFD  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xFD primero, luego el alto 0xCA)
                 CRC calculado sobre los 6 bytes previos = 0xCAFD
                 VERIFICACION: CORRECTA — la trama es integra

TRAMA: 01 01 01 00 51 88
Longitud: 6 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    01        Codigo de funcion = 1 (Read Coils)
                 Lee salidas digitales (area Coils, Modicon 0xxxx)
[2]    01        Cantidad de bytes de datos que siguen = 1
[3]    00        Bits (b7..b0): 0 0 0 0 0 0 0 0
                 El primer elemento pedido esta en el bit 0 = 0
----------------------------------------------------------------------
[ 4- 5] 51 88     CRC-16 = 0x8851  (transmitido LITTLE-ENDIAN:
                 byte bajo 0x51 primero, luego el alto 0x88)
                 CRC calculado sobre los 4 bytes previos = 0x8851
                 VERIFICACION: CORRECTA — la trama es integra
```

## FC 02: petición en t = 0.0000 s, respuesta 15.4 ms después

```text
TRAMA: 01 02 00 00 00 01 B9 CA
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    02        Codigo de funcion = 2 (Read Discrete Inputs)
                 Lee entradas digitales (area Discrete Inputs, Modicon 1xxxx)
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 10001  (area Discrete Inputs)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 01     Cantidad a leer = 1 elemento(s)
----------------------------------------------------------------------
[ 6- 7] B9 CA     CRC-16 = 0xCAB9  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xB9 primero, luego el alto 0xCA)
                 CRC calculado sobre los 6 bytes previos = 0xCAB9
                 VERIFICACION: CORRECTA — la trama es integra

TRAMA: 01 02 01 00 A1 88
Longitud: 6 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    02        Codigo de funcion = 2 (Read Discrete Inputs)
                 Lee entradas digitales (area Discrete Inputs, Modicon 1xxxx)
[2]    01        Cantidad de bytes de datos que siguen = 1
[3]    00        Bits (b7..b0): 0 0 0 0 0 0 0 0
                 El primer elemento pedido esta en el bit 0 = 0
----------------------------------------------------------------------
[ 4- 5] A1 88     CRC-16 = 0x88A1  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xA1 primero, luego el alto 0x88)
                 CRC calculado sobre los 4 bytes previos = 0x88A1
                 VERIFICACION: CORRECTA — la trama es integra
```

## FC 03: petición en t = 0.0933 s, respuesta 14.4 ms después

```text
TRAMA: 01 03 00 00 00 01 84 0A
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    03        Codigo de funcion = 3 (Read Holding Registers)
                 Lee registros de retencion (Modicon 4xxxx)
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 40001  (area Holding Registers)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 01     Cantidad a leer = 1 elemento(s)
----------------------------------------------------------------------
[ 6- 7] 84 0A     CRC-16 = 0x0A84  (transmitido LITTLE-ENDIAN:
                 byte bajo 0x84 primero, luego el alto 0x0A)
                 CRC calculado sobre los 6 bytes previos = 0x0A84
                 VERIFICACION: CORRECTA — la trama es integra

TRAMA: 01 03 02 00 37 F9 92
Longitud: 7 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    03        Codigo de funcion = 3 (Read Holding Registers)
                 Lee registros de retencion (Modicon 4xxxx)
[2]    02        Cantidad de bytes de datos que siguen = 2
[3-4]  00 37     Registro 0 = 55 (0x0037)
                 MSB=0x00 primero, LSB=0x37 despues (BIG-ENDIAN)
----------------------------------------------------------------------
[ 5- 6] F9 92     CRC-16 = 0x92F9  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xF9 primero, luego el alto 0x92)
                 CRC calculado sobre los 5 bytes previos = 0x92F9
                 VERIFICACION: CORRECTA — la trama es integra
```

## FC 04: petición en t = 0.0309 s, respuesta 15.3 ms después

```text
TRAMA: 01 04 00 00 00 01 31 CA
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    04        Codigo de funcion = 4 (Read Input Registers)
                 Lee registros de entrada (Modicon 3xxxx)
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 30001  (area Input Registers)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 01     Cantidad a leer = 1 elemento(s)
----------------------------------------------------------------------
[ 6- 7] 31 CA     CRC-16 = 0xCA31  (transmitido LITTLE-ENDIAN:
                 byte bajo 0x31 primero, luego el alto 0xCA)
                 CRC calculado sobre los 6 bytes previos = 0xCA31
                 VERIFICACION: CORRECTA — la trama es integra

TRAMA: 01 04 02 03 E8 B9 8E
Longitud: 7 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    04        Codigo de funcion = 4 (Read Input Registers)
                 Lee registros de entrada (Modicon 3xxxx)
[2]    02        Cantidad de bytes de datos que siguen = 2
[3-4]  03 E8     Registro 0 = 1000 (0x03E8)
                 MSB=0x03 primero, LSB=0xE8 despues (BIG-ENDIAN)
----------------------------------------------------------------------
[ 5- 6] B9 8E     CRC-16 = 0x8EB9  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xB9 primero, luego el alto 0x8E)
                 CRC calculado sobre los 5 bytes previos = 0x8EB9
                 VERIFICACION: CORRECTA — la trama es integra
```
## FC 06 (escritura): el DCMD `Outputs/LedPWM` llega al bus

De `eficiencia-None.pcapng`: el comando de la web termina en esta trama. El esclavo responde con el **eco**
idéntico 16.5 ms después, y recién entonces el servidor OPC UA responde `Good`
al WriteRequest (ADR-015).

```text
TRAMA: 01 06 00 00 00 0B C8 0D
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    06        Codigo de funcion = 6 (Write Single Register)
                 Escribe un registro de retencion de 16 bits
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 40001  (area Holding Registers)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 0B     Valor a escribir = 11 (0x000B)
                 BIG-ENDIAN dentro del registro (MSB primero)
----------------------------------------------------------------------
[ 6- 7] C8 0D     CRC-16 = 0x0DC8  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xC8 primero, luego el alto 0x0D)
                 CRC calculado sobre los 6 bytes previos = 0x0DC8
                 VERIFICACION: CORRECTA — la trama es integra

(eco del esclavo)
TRAMA: 01 06 00 00 00 0B C8 0D
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    06        Codigo de funcion = 6 (Write Single Register)
                 Escribe un registro de retencion de 16 bits
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 40001  (area Holding Registers)
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 0B     Valor a escribir = 11 (0x000B)
                 BIG-ENDIAN dentro del registro (MSB primero)
----------------------------------------------------------------------
[ 6- 7] C8 0D     CRC-16 = 0x0DC8  (transmitido LITTLE-ENDIAN:
                 byte bajo 0xC8 primero, luego el alto 0x0D)
                 CRC calculado sobre los 6 bytes previos = 0x0DC8
                 VERIFICACION: CORRECTA — la trama es integra
```
