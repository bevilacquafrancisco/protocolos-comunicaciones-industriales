> **⚠ DISPARA I-01: el esclavo de la Tarea Nº1 usa la librería `umodbus` (micropython-modbus) como stack MODBus, y es esa librería la que genera y verifica el CRC.** `tarea-1/firmware/esclavo/main.py:46` → `from umodbus.serial import ModbusRTU`. La capa de protocolo del esclavo **debe reescribirse**; el resto del firmware se conserva (ver §8).

# Análisis de la Tarea Nº1 — insumo para la Tarea Nº3

Fase F0 · 2026-11-08 · Fuente: código y documentos de `tarea-1/` en la rama `develop`
(último commit que los toca: `9008f55`) e informe entregado
`tarea-1/informe/Bevilacqua_Peralta_PdCI_T3_26-final.docx`.

> Nota de nombre: el informe **de la T1** está guardado como `..._PdCI_T3_26-final.docx`. Es un
> nombre mal puesto (la entrega de la T1 debía decir `T1`); no afecta a la T3, pero hay que evitar
> confundirlo con el informe de la T3 al armar la entrega.

---

## 1. Plataforma real (no la que supone `CLAUDE.md` de la T3)

| Aspecto | Lo que supone `tarea-3/CLAUDE.md` §3 | Lo que hay en la T1 | Fuente |
|---|---|---|---|
| Lenguaje del firmware | C++/Arduino (PlatformIO) | **MicroPython** ≥ 1.19 | `tarea-1/firmware/esclavo/main.py:36` |
| Entorno de desarrollo | PlatformIO, `pio test -e native` | **IDE Thonny** (F5 / Ctrl+C / Ctrl+D) | `tarea-1/firmware/README.md` |
| Stack MODBus | Propio | **Librería `umodbus`** (brainelectronics) | `esclavo/main.py:46`, `maestro/main.py:52` |
| Mapa de registros | Configurable por esclavo | Fijo, 4 variables en offset 0 | `esclavo/main.py:273-307` |
| Maestro de la T1 | — | Otro ESP32 (en la T3 lo reemplaza la Raspberry Pi) | `maestro/main.py` |

La diferencia de lenguaje es una **decisión abierta** (ADR-010 en `decisiones-adr.md`): no se
resuelve en F0.

## 2. Mapa de pines real del esclavo

Fuente única: `tarea-1/firmware/comun/config.py` (las líneas citadas). Coincide con
`tarea-1/docs/arquitectura.md` §8.2.

| Señal | GPIO | Línea en `config.py` | Conexión eléctrica | Observación |
|---|---|---|---|---|
| UART2 TX → DI del MAX485 | **17** | 75 | Directa (VIH ≥ 2,0 V contra 3,3 V: margen 1,3 V) | |
| UART2 RX ← RO del MAX485 | **16** | 80 | **Divisor 2,2 kΩ / 3,3 kΩ + pull-up 680 Ω de RO a 5 V** | Ver §6, incidente 4 |
| DE + RE (unidos) | **4** | 86 | Directa; alto = transmite | |
| Pulsador / switch | **18** | 92 | A GND, pull-up interno, **activo en bajo** | El firmware invierte: 1 = presionado |
| Potenciómetro | **34** (ADC1_CH6) | 96 | Extremos a 3,3 V y GND; atenuación 11 dB | Pin solo-entrada |
| LED digital | **19** | 99 | Ánodo al pin, 330 Ω a GND | |
| LED PWM | **21** | 102 | Ánodo al pin, 330 Ω a GND; 1000 Hz (`config.py:181`) | |
| Jumper de Unit ID | **13** | 112 | Abierto = ID 1 · a GND = ID 2 (leído una vez al arrancar) | |

Pines **descartados a propósito** en la T1 (`arquitectura.md` §8.1): GPIO 0, 2, 5, 12, 15
(*strapping*) y 6-11 (flash SPI). **El diccionario de la T3 proponía GPIO 2 y GPIO 5 para los LED:
son justamente dos de los descartados.** Se corrigió.

## 3. Parámetros serie

| Parámetro | Valor | Línea en `config.py` | Justificación defendida |
|---|---|---|---|
| Baud rate | **9600** | 37 | t1,5 = 1,72 ms absorbe pausas del GC de MicroPython; a 115200 bps serían 143 µs (`protocolo-comunicacion.md` §3.1) |
| Bits de datos | 8 | 40 | Obligatorio en RTU |
| Paridad | **Ninguna (N)** | 44 | El CRC-16 es más fuerte que la paridad (§3.3) |
| Bits de parada | **1** | 55 | `machine.UART` y los conversores usan 1. **Fuera de la norma**: MODBus serie exige 11 bits por carácter (8N2 sin paridad). Los cálculos de la T1 usan 11 bits, del lado seguro (§3.4) |
| UART | UART2 | 60 | UART0 ocupado por la consola REPL |
| Unit ID | **1** (jumper abierto) / **2** (a GND) | 160-161 | Dirección física por hardware |
| Timeout de respuesta del maestro | 300 ms | 225 | Piso físico de un esclavo MicroPython: 12,1 ms (`maestro/main.py:172-187`) |
| Período de sondeo | 200 ms | 219 | Ciclo medido: 161 ms (§7) |
| Reintentos | 1 | 260 | Las 4 transacciones son idempotentes |

**Consecuencia para la T3.** El esclavo propio queda en **9600 8N1**; el diccionario de la T3 ponía
19200 8E1 por defecto. Se adopta: preajuste "Dispositivo 1" = 9600 8N1 ID 1, y preajuste
"Norma MODBus" = 19200 8E1 para el esclavo de la cátedra (I-04). Ver diccionario §5.

## 4. Mapa MODBus y códigos de función

Fuente: `config.py:138-150`, `esclavo/main.py:273-307`, `docs/mapa-registros.md` §3.

| Variable | Área | Modicon | Offset | FC lectura | FC escritura | Tipo | Rango | Valor inicial |
|---|---|---|---|---|---|---|---|---|
| Pulsador | Discrete Input | 10001 | `0x0000` | 02 | — | bit | 0-1 | `False` |
| Potenciómetro | Input Register | 30001 | `0x0000` | 04 | — | UINT16 | 0-4095 (crudo, promedio de 8 muestras) | 0 |
| LED digital | Coil | 00001 | `0x0000` | 01 | 05 | bit | 0-1 | `False` |
| LED PWM | Holding Register | 40001 | `0x0000` | 03 | 06 | UINT16 | 0-255 (el esclavo satura valores mayores) | 0 |

- **FC soportadas por el esclavo:** 01, 02, 03, 04, 05, 06. Las implementa `umodbus` según las
  áreas dadas de alta; FC 0F/10 no se probaron.
- **Excepciones verificadas en banco** (`mapa-registros.md` §9): prueba 12 (escritura sobre
  Input Register, rechazada) y prueba 13 (dirección inexistente → **excepción 02**). 14/14 pruebas.
- **Maestro de la T1:** usa FC 02, 04, 05 y 06 (4 transacciones por ciclo, `maestro/main.py:727-898`).
- **Endianness:** registros big-endian; CRC little-endian (byte bajo primero)
  (`protocolo-comunicacion.md` §7.3 y §8). Reutilizable tal cual para la pregunta del informe.

## 5. Stack MODBus: librería, no propio

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Librería o propio? | **Librería** `micropython-modbus` (paquete `umodbus`) | `esclavo/main.py:37` (docstring) y `:46` (import) |
| Esclavo | `ModbusRTU(addr, baudrate, data_bits, stop_bits, parity, pins, ctrl_pin, uart_id)` | `esclavo/main.py:262-271` |
| Atención del bus | `cliente.process()` en el lazo | `esclavo/main.py:534` |
| Maestro | `umodbus.serial.Serial`, extendido con `MaestroRTUConTimeout` | `maestro/main.py:52` y `:159` |
| ¿Quién calcula el CRC en el firmware? | La librería: `Serial._calculate_crc16()`, **por tabla** | `umodbus/serial.py` 2.3.7 (develop, consultado 2026-11-08) |
| ¿Hay CRC propio? | Sí, pero **solo en la PC**: `tarea-1/herramientas/modbus_tramas.py`, bit a bit, polinomio 0xA001, verificado contra el vector `123456789` → 0x4B37 | `protocolo-comunicacion.md` §7.3. Se corrió hoy: pasa |
| Versión instalada en las placas | **No registrada.** El README instala la última de PyPI sin fijar versión | `firmware/README.md` §3. Última en PyPI: 2.3.7 (2023-07-19) |

El informe de la T1 lo declara explícitamente: *"Stack MODBus: Biblioteca + CRC propio. La biblioteca
asegura la funcionalidad; el CRC propio aporta evidencia para la pregunta 2"* (`tarea-1/README.md` §4).
**Eso alcanzó para la T1 y no alcanza para la T3**, que exige generación y verificación del CRC
*en el esclavo* (consigna T3 §1.a, invariante I-01).

**Lo que se reutiliza para la reescritura:** el algoritmo de `modbus_tramas.py` (ya verificado), los
vectores de prueba de las cuatro tramas del sistema y el decodificador. El CRC de la PC pasa a ser
también el oráculo de los vectores *golden*.

## 6. Control de DE/RE y vaciado del buffer

| Aspecto | Comportamiento en la T1 | Fuente |
|---|---|---|
| Quién maneja DE/RE | La librería, a través de `ctrl_pin` | `config.py:83-86` (comentario), `esclavo/main.py:269` |
| Antes de transmitir | `ctrlPin.on()` y espera fija de **200 µs** | `umodbus/serial.py` `_send()` (2.3.7) |
| Vaciado antes de soltar la línea | **Sí, si el MicroPython lo soporta:** `uart.flush()` + espera de 1 carácter (`t1char`). Si no (MicroPython < 1.20), espera calculada `t1char × len(trama) − tiempo_de_write + 100 µs` | `umodbus/serial.py` `_send()`; `_has_uart_flush = callable(getattr(UART, "flush", None))` |
| Después de transmitir | `ctrlPin.off()` | ídem |
| DE y RE | **Unidos al mismo GPIO**: el nodo no se escucha a sí mismo | `config.py:82-86` |
| Efecto lateral de unirlos | Con RE alto, **RO queda en alta impedancia** y el divisor tira RX a 0 → bytes `0x00` espurios | `evidencia/INCONVENIENTES.md` §4 |
| Corrección de hardware | **Pull-up 680 Ω de RO a 5 V** en las tres placas: nodo en Hi-Z = 2,67 V (umbral ESP32 2,47 V) | `arquitectura.md` §4.3.1, informe T1 §5.3.3 |
| Corrección de software (maestro) | Ventana de descarte de 2000 µs tras transmitir | `maestro/main.py` `_VENTANA_DESCARTE_GLITCH_US` |

**Requisito para el stack propio (no negociable):** reproducir el `flush()` + 1 `t1char` antes de
bajar DE/RE, y verificar al arrancar que `UART.flush` existe (MicroPython ≥ 1.20). Es exactamente
lo que la librería hacía bien y que el stack propio podría perder.

## 7. Mediciones de la T1 citables en la T3

Todas de banco, instrumentación del firmware (`tarea-1/README.md` §1, `INCONVENIENTES.md` §5, informe §9.4.4).

| Medición | Valor | Condición |
|---|---|---|
| Ciclos consecutivos sin fallo | 750, 0,0 % | 2 nodos (Parte 2) |
| Duración del ciclo de 4 transacciones | **161 ms** medido contra 110 ms calculado (+46 %) | 9600 bps |
| Costo de cómputo no modelado | ≈ 12,8 ms por transacción | MicroPython interpretado |
| Tasa de error con 3 nodos — Esclavo 1 | 7 / 2876 = 0,2 % (7 timeouts) | Parte 3 |
| Tasa de error con 3 nodos — **Esclavo 2** | **239 / 2046 = 11,6 %** (238 timeouts, 1 error de trama) | Parte 3, causa física no cerrada |
| Longitud del bus | 15-40 cm | Medición directa |

El 11,6 % del Esclavo 2 **no se explicó** (el informe deriva la causa física a la guía de
depuración). Si en la T3 el ESP32 #2 es la misma placa, es un riesgo (R-07 en `riesgos.md`).

## 8. Decisiones defendidas que conviene conservar

| Decisión | Por qué conservarla en la T3 | Fuente |
|---|---|---|
| `config.py` como única fuente de verdad, importable desde CPython | Permite probar el stack nuevo en la PC sin placa | `config.py:13-25` |
| Un solo firmware para todos los esclavos; Unit ID por jumper | Base de ADR-007 (esclavo de prueba con otros parámetros) | `esclavo/main.py:139-183` |
| Valor crudo del ADC (0-4095) en el registro; escalado en quien consume | Ya era ADR-003 de la T3 | `mapa-registros.md` §7.1 |
| ADC1, atenuación 11 dB, promedio de 8 muestras | Defecto real resuelto (incidente 2) | `mapa-registros.md` §7.3 |
| Pull-up 680 Ω en RO + divisor 2,2/3,3 kΩ | Causa raíz del incidente más caro de la T1 | `INCONVENIENTES.md` §4 |
| Sin terminación ni polarización (bus < 1,5 m) | Calculado y validado; si el bus de la T3 crece, revisar | Informe T1 §5.5-5.6 |
| Separación timeout / excepción / CRC inválido | Coincide con los contadores que pide la T3 §1.c | `protocolo-comunicacion.md` §10.1 |
| CRC bit a bit, sin tabla | "Hace visible el mecanismo" para la defensa | `protocolo-comunicacion.md` §7.4 |
| Capa de diagnóstico (`CapturaTramas`, versión entre módulos, efecto sonda) | Conserva la observabilidad sin alterar el timing | `diagnostico.py` (VERSION 4) |
| HAL `perifericos.py` | Independiente del stack MODBus | `perifericos.py` |
| Trazabilidad bloque ↔ función (`E1`…`E6`) | Exigida también por la T3 (I-09) | `diagramas/flujo_esclavo.md` |
| Reintento único e idempotencia | El maestro de la T3 debe heredar el criterio | `config.py:248-260` |
| Degradación por ausencia sostenida (2000 ms), no por fallos contados | Es la base natural del `DDEATH` (I-07): un fallo aislado no debe producir `DDEATH` | `config.py:262-274` |

## 9. Qué se reutiliza y qué se reescribe

| Pieza | Destino en la T3 |
|---|---|
| `comun/config.py` | **Reutilizar**, agregando el mapa de registros configurable para el esclavo de prueba |
| `comun/perifericos.py` | **Reutilizar tal cual** |
| `comun/diagnostico.py` | **Reutilizar**; `InstrumentacionBus` se rehace porque envuelve a `umodbus` |
| `esclavo/main.py`, bloques E1-E3, E5, E6 | **Adaptar**: reemplazar `ModbusRTU` por el stack propio |
| `esclavo/main.py`, bloque E4 (`cliente.process()`) | **Reescribir**: recepción por silencio t3,5, verificación de CRC, despacho de FC, excepciones 01-03, armado de respuesta con CRC propio |
| `maestro/main.py` | **No se usa** (el maestro pasa a la Raspberry Pi); su lógica de reintento y degradación se traslada al flow de Node-RED |
| `herramientas/modbus_tramas.py` | **Reutilizar** como oráculo de vectores y decodificador |
| `herramientas/sniffer_rs485.py` | **Reutilizar** para capturas del informe |
| `docs/protocolo-comunicacion.md` §5-§10, `mapa-registros.md`, `arquitectura.md` | **Citar** en el informe de la T3 |

## 10. Gaps de información

| Gap | Impacto | Cómo se cierra |
|---|---|---|
| Versión exacta de `umodbus` y de MicroPython en las placas | Bajo (se reemplaza) | `import umodbus.version; print(umodbus.version.__version__)` y `os.uname()` en Thonny |
| ¿La placa del Esclavo 2 de la T1 es la que se usará como ESP32 #2? | Medio (R-07) | Preguntar al grupo |
| ¿El adaptador USB-RS485 tiene control de dirección automático? | Alto para el maestro (R-04) | Modelo del adaptador; prueba de eco |
| Retroalimentación de la cátedra sobre la T1 (nota y observaciones) | Medio | Pedirla: dice qué no tocar |
