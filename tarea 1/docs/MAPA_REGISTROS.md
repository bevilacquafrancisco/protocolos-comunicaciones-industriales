# Mapa de registros MODBus — Tarea Nº1

**Estado:** borrador v0.1 — pendiente de confirmar rango del ADC y factor de escala.

## 1. Identificación de nodos

| Nodo | Rol | Unit ID | Hardware |
|---|---|---|---|
| Maestro | Cliente / iniciador | — (no tiene) | ESP32 + transceptor RS-485 |
| Esclavo 1 | Servidor | 1 | ESP32 + transceptor RS-485 |
| Esclavo 2 | Servidor | 2 | ESP32 + transceptor RS-485 |
| PC (Modbus Poll) | Cliente, sólo Parte 1 | — | Conversor USB–RS-485 |

Direcciones válidas de esclavo en Modbus serie: 1 a 247. El 0 se reserva
para difusión (broadcast) y no se usa en este trabajo.

## 2. Parámetros de línea serie

| Parámetro | Valor | Justificación |
|---|---|---|
| Baudrate | 9600 | Ver §2.1 — margen de timing frente al intérprete de MicroPython |
| Bits de datos | 8 | Obligatorio en modo RTU (el modo ASCII usa 7) |
| Paridad | Ninguna (N) | Ver §2.2 |
| Bits de parada | 1 | Consecuencia de "sin paridad" según la especificación serie |
| Codificación | RTU (binaria) | Fijado por la consigna |

Todos los nodos del bus **y** la configuración de Modbus Poll deben coincidir
exactamente en estos cuatro parámetros. Un solo nodo desalineado rompe el bus entero.

### 2.1 Por qué 9600 y no 115200

Modbus RTU delimita las tramas por silencio, no por caracteres de inicio/fin:

- Fin de trama: silencio ≥ **3,5 tiempos de carácter** (t3,5)
- Trama descartada: silencio ≥ **1,5 tiempos de carácter** entre bytes (t1,5)

Un carácter RTU 8N1 son 11 bits en la línea (1 start + 8 datos + 1 paridad/relleno + 1 stop).

| Baudrate | t_carácter | t1,5 | t3,5 |
|---|---|---|---|
| 9600 | 1,146 ms | **1,72 ms** | 4,01 ms |
| 19200 | 0,573 ms | 0,86 ms | 2,01 ms |
| 115200 | 0,095 ms | 0,143 ms | 1,750 ms (*) |

(*) La especificación fija t3,5 = 1,750 ms como valor constante para baudrates
superiores a 19200, precisamente porque el cálculo exacto deja de ser practicable.

El firmware corre sobre MicroPython, que es interpretado y ejecuta un recolector
de basura (GC) cuyas pausas están en el orden de las **décimas de milisegundo a
milisegundos**. A 115200 baudios, una sola pausa del GC en medio de la recepción
supera t1,5 = 143 µs y provoca el descarte de una trama válida. A 9600 el
presupuesto es 12 veces mayor (1,72 ms) y el sistema tolera esas pausas.

Trade-off explícito: se pierde ancho de banda (irrelevante — el ciclo de sondeo
de este trabajo es del orden de 100 ms para ~20 bytes por transacción) y se gana
robustez determinista frente al no-determinismo del intérprete. Se descartó
19200 por dejar un margen sólo 1,7 veces mayor que la peor pausa esperada del GC.

### 2.2 Por qué sin paridad (8N1)

La paridad par (8E1) es lo más habitual en instalaciones Modbus históricas, y la
especificación la recomienda como valor por defecto. Se elige **8N1** porque:

1. La trama ya está protegida por **CRC-16**, que detecta todos los errores de
   ráfaga de hasta 16 bits y el 99,998 % de las ráfagas más largas. La paridad
   sólo detecta un número impar de bits erróneos por carácter: es redundante y
   estrictamente más débil que el CRC que ya viaja en la trama.
2. Es el valor por defecto de `machine.UART` en MicroPython y de la mayoría de
   los conversores USB–RS-485 económicos, lo que reduce el riesgo de
   desalineación de configuración entre nodos (causa nº 1 de bus muerto).

Contrapartida asumida: se pierde la detección temprana por carácter, que
permitiría descartar una trama antes de recibirla completa. Irrelevante a 9600
baudios con tramas de 8 bytes.

## 3. Mapa de registros — idéntico en Esclavo 1 y Esclavo 2

Sólo cambia el Unit ID. El mapa idéntico es un requisito de la Parte 3: permite
que el maestro conmute de esclavo sin cambiar ninguna dirección, sólo el ID.

| Dir. Modicon | Offset en trama | Área | Función L | Función E | Tipo | Variable | Rango | Escala | L/E |
|---|---|---|---|---|---|---|---|---|---|
| 10001 | 0x0000 | Discrete Input | 0x02 | — | 1 bit | Switch / pulsador | 0-1 | — | L |
| 30001 | 0x0000 | Input Register | 0x04 | — | UINT16 | Potenciómetro (ADC) | 0-4095 | ×1 (crudo) | L |
| 00001 | 0x0000 | Coil | 0x01 | 0x05 | 1 bit | LED 1 (digital) | 0-1 | — | L/E |
| 40001 | 0x0000 | Holding Register | 0x03 | 0x06 | UINT16 | LED 2 (PWM) | 0-255 | ×1 | L/E |

### 3.1 Desfasaje de direccionamiento (off-by-one)

La numeración `1xxxx / 3xxxx / 0xxxx / 4xxxx` es la **notación Modicon**: el
primer dígito identifica el área y los cuatro siguientes numeran la posición
**desde 1**. En la trama real, la dirección viaja como offset **desde 0** dentro
de esa área. Por lo tanto:

```
40001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x03 / 0x06
30001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x04
10001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x02
00001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x05
```

Que las cuatro variables compartan el offset 0x0000 **no es una colisión**: cada
área de Modbus tiene su propio espacio de direcciones independiente, y la función
usada es la que determina en qué área se busca ese offset.

Verificación obligatoria antes de dar por buena la implementación: escribir un
valor conocido y distinto en cada área (por ejemplo Coil 0 = 1, HR 0 = 200) y
comprobar que Modbus Poll lo lee en la dirección esperada. Modbus Poll y otras
herramientas permiten configurar si direccionan con base 0 o base 1 — si el
valor aparece corrido en uno, el problema es de configuración de la herramienta,
no del firmware.

### 3.2 Escala del potenciómetro (decisión abierta — ver TODO)

El ADC del ESP32 es de **12 bits (0-4095)**, a diferencia del de un Arduino UNO
(10 bits, 0-1023). Dos opciones:

| Opción | Valor en 30001 | A favor | En contra |
|---|---|---|---|
| A. Crudo | 0-4095 | Sin pérdida de información; el escalado queda en el maestro | El valor no significa nada sin conocer el hardware del esclavo |
| B. Normalizado a 0-255 | 0-255 | Coincide con el rango del PWM; replicación directa | Se descartan 4 bits de resolución en el origen |

**Elegida: opción A (crudo, 0-4095).** Principio aplicado: el esclavo transporta
la medición, no la interpretación; el escalado es una decisión del consumidor del
dato. El maestro convierte a PWM con un desplazamiento de 4 bits
(`pwm = adc >> 4`, equivalente a dividir por 16), operación exacta y sin punto
flotante. Se documenta el factor de escala aquí, que es donde corresponde: el
mapa de registros, no el código.

## 4. Transacciones del maestro por ciclo de sondeo

| # | Sentido | Función | Dirección | Datos | Propósito |
|---|---|---|---|---|---|
| 1 | Maestro → Esclavo N | 0x02 | 0x0000, qty=1 | — | Leer switch remoto |
| 2 | Maestro → Esclavo N | 0x04 | 0x0000, qty=1 | — | Leer potenciómetro remoto |
| 3 | Maestro → Esclavo N | 0x05 | 0x0000 | 0xFF00 / 0x0000 | Escribir LED 1 del esclavo |
| 4 | Maestro → Esclavo N | 0x06 | 0x0000 | 0x0000-0x00FF | Escribir PWM del esclavo |

Cuatro transacciones por ciclo. Cada una es una petición y su respuesta: el bus
RS-485 es half-duplex, nunca hay dos nodos transmitiendo a la vez.

## TODO antes de la entrega

- [ ] Confirmar atenuación del ADC elegida y el rango de tensión real que cubre
- [ ] Medir el tiempo real de ciclo de sondeo completo y registrarlo acá
- [ ] Adjuntar captura de Modbus Poll validando cada una de las 4 direcciones
