# Mapa de registros MODBus

**Tarea Nº1 — Red MODBus RTU sobre RS-485** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Este documento es el **contrato de datos** del sistema: qué variable vive en qué
dirección, con qué tipo, rango y escala. Es el entregable que hace reproducible y
auditable cualquier integración MODBus — sin él, el próximo que toque el sistema
(incluido uno mismo en seis meses) tiene que adivinar.

Complementa a [arquitectura.md](arquitectura.md) (capa física) y a
[protocolo-comunicacion.md](protocolo-comunicacion.md) (tramas, CRC y parámetros
del puerto serie).

**Estado: validado sobre hardware.** Las tres partes de la consigna se ejecutaron
y verificaron en banco. Los resultados de cada prueba están en la §9 de este
documento, con el detalle del procedimiento en
[PARTE-1.md](../PARTE-1.md), [PARTE-2.md](../PARTE-2.md) y [PARTE-3.md](../PARTE-3.md).

---

## Índice

1. [Identificación de nodos](#1-identificación-de-nodos)
2. [Parámetros del bus](#2-parámetros-del-bus)
3. [El mapa de registros](#3-el-mapa-de-registros)
4. [Teoría del direccionamiento MODBus](#4-teoría-del-direccionamiento-modbus)
5. [El desfasaje Modicon ↔ offset (off-by-one)](#5-el-desfasaje-modicon--offset-off-by-one)
6. [Las cuatro transacciones, campo por campo](#6-las-cuatro-transacciones-campo-por-campo)
7. [Escala del potenciómetro](#7-escala-del-potenciómetro)
8. [Rango del PWM](#8-rango-del-pwm)
9. [Validación del mapa sobre hardware](#9-validación-del-mapa-sobre-hardware)
10. [Retención de estado](#10-retención-de-estado)
11. [Escalabilidad del mapa](#11-escalabilidad-del-mapa)

---

## 1. Identificación de nodos

| Nodo | Rol | Unit ID | Cómo se determina |
|---|---|---|---|
| Maestro | Cliente / iniciador | **ninguno** | No aplica |
| Esclavo 1 | Servidor | **1** | Jumper de direccionamiento abierto |
| Esclavo 2 | Servidor | **2** | Jumper de direccionamiento a GND |
| PC con herramienta MODBus | Cliente, solo Parte 1 | **ninguno** | No aplica |

Direcciones válidas en MODBus serie: **1 a 247**. El 0 se reserva para difusión
(*broadcast*) y no se usa en este trabajo, porque una orden de difusión no genera
respuesta y por lo tanto **no permite confirmar que llegó** — en un sistema cuyo
único mecanismo de recuperación es el reintento, renunciar a la confirmación es
renunciar a saber si la orden se ejecutó.

Un maestro MODBus **no tiene dirección propia**: nunca es destinatario de una
trama, solo emisor. Es una diferencia conceptual que conviene tener a mano para
la defensa oral, y explica por qué el constructor del maestro en el firmware no
recibe ningún parámetro de dirección mientras que el del esclavo sí.

### 1.1 Direccionamiento por hardware

Ambos esclavos ejecutan **el mismo archivo de firmware**, sin una sola línea
distinta. La dirección se lee de un jumper físico en el arranque.

La decisión tiene dos fundamentos:

1. **Reproduce la práctica industrial.** Un módulo de E/S remoto o un variador de
   frecuencia toman su dirección de llaves DIP, no de su firmware. La dirección
   es una propiedad de la instalación, no del programa.
2. **Elimina por construcción una clase de error.** Con dos archivos distintos,
   actualizar uno y olvidar el otro es cuestión de tiempo, y en un bus de campo
   ese olvido se manifiesta como una falla intermitente dificilísima de atribuir.
   Con un archivo único, ese error no puede ocurrir.

La lectura se hace **una sola vez, en el arranque**. Cambiar la dirección de un
dispositivo MODBus en caliente dejaría al maestro hablándole a un nodo que ya no
existe; en la práctica industrial el redireccionamiento siempre exige reiniciar
el equipo.

## 2. Parámetros del bus

| Parámetro | Valor |
|---|---|
| Modo | RTU (binario) |
| Baudrate | 9600 |
| Bits de datos | 8 |
| Paridad | Ninguna |
| Bits de parada | 1 |

Notación abreviada: **9600 8N1**.

Justificación completa de cada valor en
[protocolo-comunicacion.md §3](protocolo-comunicacion.md#3-configuración-del-puerto-serie).
Deben ser **idénticos en los tres ESP32 y en la herramienta de PC**; están
centralizados en [firmware/comun/config.py](../firmware/comun/config.py), un
único archivo que se copia sin modificar a las tres placas.

> Centralizar estos cinco valores vuelve **imposible por construcción** la
> desalineación de velocidad o paridad entre nodos, que es una de las causas más
> frecuentes de incomunicación total en un bus de campo. No es una comodidad de
> escritura: es una restricción de diseño.

## 3. El mapa de registros

Ambos esclavos implementan **exactamente el mismo mapa**; solo cambia el Unit ID.
Es lo que permite que el maestro conmute de esclavo sin modificar ninguna
dirección, únicamente el destinatario de la trama.

| Dir. Modicon | Offset en trama | Área | Func. lectura | Func. escritura | Tipo | Variable | Rango | L/E |
|---|---|---|---|---|---|---|---|---|
| **10001** | `0x0000` | Discrete Input | 0x02 | — | 1 bit | Pulsador / switch | 0-1 | L |
| **30001** | `0x0000` | Input Register | 0x04 | — | UINT16 | Potenciómetro (ADC crudo) | 0-4095 | L |
| **00001** | `0x0000` | Coil | 0x01 | 0x05 | 1 bit | LED digital | 0-1 | L/E |
| **40001** | `0x0000` | Holding Register | 0x03 | 0x06 | UINT16 | LED PWM | 0-255 | L/E |

### 3.1 Correspondencia con el hardware

| Dirección Modicon | Entrada/salida del ESP32 | Componente | Sentido |
|---|---|---|---|
| 10001 | Entrada digital con pull-up | Pulsador o switch a GND, activo en bajo | Proceso → bus |
| 30001 | Entrada analógica, ADC de 12 bits | Potenciómetro como divisor de tensión | Proceso → bus |
| 00001 | Salida digital | LED con resistencia limitadora | Bus → proceso |
| 40001 | Salida PWM | LED con resistencia limitadora | Bus → proceso |

La asignación concreta de pines está en
[arquitectura.md §8](arquitectura.md#8-asignación-de-pines) y se declara en un
único lugar del código, [firmware/comun/config.py](../firmware/comun/config.py).

### 3.2 Por qué cada variable está en el área que está

La elección de área **no es arbitraria ni intercambiable**: cada área expresa una
propiedad del dato, y equivocarla produce un mapa que funciona pero que miente
sobre la naturaleza de lo que transporta.

| Variable | Área elegida | Por qué esa y no otra |
|---|---|---|
| Pulsador | **Discrete Input** (solo lectura) | Refleja el estado de un contacto físico. Un maestro no puede "escribir" la posición de un pulsador: ponerlo en un Coil permitiría que el bus sobrescriba un estado del proceso, lo que es físicamente absurdo y peligroso |
| Potenciómetro | **Input Register** (solo lectura) | Misma lógica, con dato de 16 bits. Es una medición, y las mediciones no se escriben |
| LED digital | **Coil** (lectura y escritura) | Es un actuador binario gobernado por el maestro. Debe ser escribible, y además legible para poder confirmar el estado sin depender de la memoria del maestro |
| LED PWM | **Holding Register** (lectura y escritura) | Actuador con consigna de 16 bits. Es el equivalente conceptual de una consigna de velocidad a un variador |

> La regla general: **lo que el proceso impone al sistema va en las áreas de solo
> lectura; lo que el sistema impone al proceso va en las áreas escribibles.** Un
> mapa que respeta esa separación hace que el protocolo mismo impida órdenes sin
> sentido, sin necesidad de validación adicional.

Esa separación se verificó explícitamente: la prueba 12 de la §9 intenta escribir
sobre un Input Register y comprueba que el esclavo lo rechaza.

## 4. Teoría del direccionamiento MODBus

Esta sección responde una pregunta que surge de inmediato al mirar el mapa: **si
las cuatro variables usan la dirección `0x0000`, ¿no se pisan entre sí?**

La respuesta es que no, y entender por qué es entender el modelo de datos de
MODBus.

### 4.1 MODBus no tiene un espacio de direcciones, tiene cuatro

El modelo de datos define **cuatro bloques independientes**, separados por dos
criterios ortogonales — el tamaño del dato y la dirección del acceso:

|  | 1 bit | 16 bits |
|---|---|---|
| **Solo lectura** | Discrete Inputs | Input Registers |
| **Lectura y escritura** | Coils | Holding Registers |

Cada bloque tiene **su propio espacio de direcciones, de `0x0000` a `0xFFFF`**.
Son cuatro numeraciones paralelas que arrancan las cuatro en cero y no se
comunican entre sí.

La consecuencia directa es que **la dirección, por sí sola, no identifica nada**.
El identificador único de una variable es el par:

```
(código de función, dirección)
```

### 4.2 El código de función como selector de espacio de nombres

El código de función no dice solamente *qué operación hacer*: dice **en qué área
buscar la dirección**. Actúa como selector de espacio de nombres.

| Código | Operación | Área sobre la que actúa |
|---|---|---|
| 0x01 | Read Coils | Coils |
| 0x02 | Read Discrete Inputs | Discrete Inputs |
| 0x03 | Read Holding Registers | Holding Registers |
| 0x04 | Read Input Registers | Input Registers |
| 0x05 | Write Single Coil | Coils |
| 0x06 | Write Single Register | Holding Registers |
| 0x0F | Write Multiple Coils | Coils |
| 0x10 | Write Multiple Registers | Holding Registers |

Por eso `0x0000` aparece cuatro veces en el mapa sin ambigüedad: son la primera
casilla de cuatro casilleros distintos.

> Es la misma lógica que la de una dirección postal: la calle 25 de Mayo 100
> existe en Rafaela y en Santa Fe. El número se repite y la ciudad desambigua.
> Acá, el código de función es la ciudad.

### 4.3 La evidencia en las tramas reales del sistema

Estas son las cuatro peticiones que emite el maestro de este trabajo, con el CRC
ya calculado. Los bytes de dirección son **idénticos en las cuatro** y sin embargo
alcanzan cuatro periféricos distintos:

```
                                              ID  FC   dirección   dato     CRC
FC02  Read Discrete Inputs   (pulsador)       01  02   00 00       00 01    B9 CA
FC04  Read Input Registers   (potenciómetro)  01  04   00 00       00 01    31 CA
FC05  Write Single Coil      (LED digital)    01  05   00 00       FF 00    8C 3A
FC06  Write Single Register  (LED PWM = 128)  01  06   00 00       00 80    88 6A
                                                  ▲▲   ▲▲ ▲▲
                                                  │    └── idéntico en las cuatro
                                                  └─────── lo único que cambia
```

Lo único que cambia es el segundo byte. Ese byte es el que decide si `00 00`
significa *el pulsador*, *el potenciómetro*, *el LED digital* o *el LED PWM*.

Estas tramas se pueden reproducir y verificar con la herramienta propia del
proyecto:

```
python "tarea 1/herramientas/modbus_tramas.py"
```

### 4.4 Un matiz que conviene conocer

La especificación **permite** que los cuatro bloques estén superpuestos en la
memoria física del dispositivo. Es una decisión del fabricante: existen equipos
donde el Coil 0 y el bit 0 del Holding Register 0 son físicamente el mismo
biestable.

En los esclavos de este trabajo **no lo están**: la biblioteca mantiene las cuatro
áreas en estructuras separadas, cada una con su propia clave. Son genuinamente
independientes.

> La separación de **espacios de direcciones** es una propiedad del protocolo; que
> además sean independientes **en memoria** es una propiedad del dispositivo. Son
> dos afirmaciones distintas y conviene no mezclarlas: al integrar un equipo
> comercial, la segunda hay que verificarla, no suponerla.

## 5. El desfasaje Modicon ↔ offset (off-by-one)

Aquí está la segunda pieza del direccionamiento, y es la que produce más errores
de integración que ninguna otra.

### 5.1 Dos numeraciones para la misma variable

|  | Notación Modicon | Offset del protocolo |
|---|---|---|
| Dónde vive | Documentación, manuales, pantallas de operador, planos | **Dentro de la trama** |
| Base | 1 (empieza en uno) | **0** (empieza en cero) |
| ¿Codifica el área? | Sí, en el dígito inicial | No — eso lo hace el código de función |
| Ejemplo | `30001` | `0x0000` |

La notación Modicon es una convención **de documentación**, heredada de los
autómatas Modicon 984. Empaqueta dos informaciones en un número de cinco dígitos:

```
    3 0001
    ▲ ▲▲▲▲
    │ └──── ordinal dentro del área, empezando en 1
    └────── dígito de área:  0 = Coil            1 = Discrete Input
                             3 = Input Register  4 = Holding Register
```

**Ese número nunca viaja por el cable.** Lo que viaja es el offset base-0.

### 5.2 La fórmula

```
offset = número_Modicon − base_del_área − 1
```

| Variable | Modicon | Base del área | Cálculo | Offset en la trama |
|---|---|---|---|---|
| Pulsador | 10001 | 10000 | 10001 − 10000 − 1 | **0x0000** |
| Potenciómetro | 30001 | 30000 | 30001 − 30000 − 1 | **0x0000** |
| LED digital | 00001 | 0 | 1 − 0 − 1 | **0x0000** |
| LED PWM | 40001 | 40000 | 40001 − 40000 − 1 | **0x0000** |

El `−1` es el off-by-one. No es un error de la especificación ni una rareza de
implementación: **la especificación lo define así explícitamente**. El modelo de
datos numera los elementos de 1 a N para las personas, y la PDU los direcciona de
0 a N−1. Es la misma distinción que entre «el primer elemento» y «el elemento de
índice 0».

### 5.3 Por qué en este sistema las cuatro dan cero

Combinando ambas piezas:

1. Cada área es un espacio independiente → las cuatro arrancan en offset 0.
2. El mapa tiene **exactamente una variable por área** → cada una ocupa la primera
   casilla de su área.
3. La primera casilla, en notación Modicon base-1, es `x0001` → offset `0x0000`.

Que las cuatro coincidan en `0x0000` **no es una decisión de diseño ni una
casualidad**: es la consecuencia aritmética inevitable de tener una sola variable
en cada una de las cuatro áreas. Habría sido imposible que diera otra cosa.

Por eso el archivo de configuración lo declara explícitamente en un comentario:
enunciarlo evita que alguien «corrija» las direcciones a 0, 1, 2 y 3 creyendo que
se pisan — un cambio que rompería las cuatro transacciones de golpe.

### 5.4 Los tres modos de falla, en orden de frecuencia

| Error | Qué ocurre en el bus | Síntoma observable |
|---|---|---|
| Usar `1` donde va el offset `0` | Se pide la segunda casilla, que no existe | **Excepción 02**, o el valor de otra variable |
| Tratar `40001` como offset literal | Se pide el offset 40001 | Excepción 02 |
| Herramienta de PC configurada en otra base | Todo el mapa desplazado un lugar | Todos los valores «corridos en uno» |

El segundo modo es traicionero porque **puede no dar error**: en un equipo con
muchos registros, pedir el offset equivocado devuelve un valor perfectamente
válido, pero de otra variable.

> **Un valor plausible pero incorrecto es más peligroso que una excepción**,
> porque pasa inadvertido. Es la razón por la que la verificación del mapa se hace
> en los extremos del rango y con valores distintos en cada área, nunca con
> valores que puedan confundirse entre sí.

### 5.5 Verificación empírica del direccionamiento

El off-by-one es **falsable en una sola transacción**. Se le pide al esclavo el
offset 1 de un área donde solo existe el offset 0:

```
Petición:   01 04 00 01 00 01 60 0A      ← FC04, dirección 0x0001
Respuesta:  01 84 02 C2 C1
               ▲▲ ▲▲
               │  └── código 02: ILLEGAL DATA ADDRESS
               └───── 0x84 = 0x04 con el bit 7 encendido → es una excepción
```

El esclavo declara **una sola** casilla en el área de Input Registers, de modo que
el offset 1 está fuera del mapa y responde con excepción 02.

Que conteste **rechazando**, en lugar de callarse o de devolver basura, demuestra
dos cosas a la vez: que el direccionamiento base-0 es el correcto, y que la
validación de rango del esclavo funciona. Es la prueba 13 de la §9.

## 6. Las cuatro transacciones, campo por campo

Un ciclo de sondeo completo del maestro contra un esclavo. Las cuatro
transacciones son **idempotentes** —dos lecturas y dos escrituras de valor
absoluto, no incrementos—, propiedad que es la que hace seguro el reintento ante
una trama perdida.

### 6.1 Lectura del pulsador — FC 0x02

```
Petición    01 02 00 00 00 01 B9 CA
            ▲▲ ▲▲ ▲──▲ ▲──▲ ▲──▲
            │  │  │    │    └── CRC-16 (little-endian)
            │  │  │    └─────── cantidad de entradas: 1
            │  │  └──────────── dirección: 0x0000 (Modicon 10001)
            │  └─────────────── función 0x02
            └────────────────── Unit ID del esclavo

Respuesta   01 02 01 01 60 48
            ▲▲ ▲▲ ▲▲ ▲▲ ▲──▲
            │  │  │  │  └────── CRC-16
            │  │  │  └───────── datos: bit 0 = 1 (pulsador accionado)
            │  │  └──────────── conteo de bytes de datos: 1
            │  └─────────────── función 0x02 (eco)
            └────────────────── Unit ID (eco)
```

Los bits se devuelven **empaquetados**: el bit menos significativo del primer byte
corresponde a la primera entrada solicitada. Con una sola entrada, los siete bits
restantes se rellenan con ceros.

### 6.2 Lectura del potenciómetro — FC 0x04

```
Petición    01 04 00 00 00 01 31 CA
Respuesta   01 04 02 08 00 BE F0
                  ▲▲ ▲──▲
                  │  └────────── valor: 0x0800 = 2048 (big-endian)
                  └───────────── conteo: 2 bytes
```

El valor de 16 bits viaja **big-endian** (primero el byte más significativo), a
diferencia del CRC, que viaja little-endian. Ver
[protocolo-comunicacion.md §8](protocolo-comunicacion.md#8-orden-de-bytes-msb-lsb-y-endianness).

### 6.3 Escritura del LED digital — FC 0x05

```
Petición    01 05 00 00 FF 00 8C 3A
                        ▲──▲
                        └──────── 0xFF00 = ON   ·   0x0000 = OFF

Respuesta   01 05 00 00 FF 00 8C 3A     ← eco idéntico a la petición
```

La especificación **no usa 0x0001 para «encendido»** en la función 0x05, sino los
valores `0xFF00` (ON) y `0x0000` (OFF); cualquier otro valor debe rechazarse con
excepción 03. Es un detalle que conviene conocer porque es lo que se ve al
capturar la trama, y porque una implementación que envíe `0x0001` será rechazada
por un esclavo que cumpla la norma.

La respuesta es un **eco idéntico** a la petición. Eso hace que la confirmación
sea inequívoca: si el eco coincide, el esclavo recibió exactamente la orden que se
emitió.

### 6.4 Escritura del PWM — FC 0x06

```
Petición    01 06 00 00 00 80 88 6A
                        ▲──▲
                        └──────── valor: 128, big-endian

Respuesta   01 06 00 00 00 80 88 6A     ← eco idéntico
```

## 7. Escala del potenciómetro

El ADC del ESP32 es de **12 bits (0-4095)**, a diferencia del de un Arduino UNO
(10 bits, 0-1023). El rango es una característica del hardware del esclavo, y por
eso se documenta aquí y no en el código.

### 7.1 Decisión: se transmite el valor crudo

| Opción | Valor en 30001 | A favor | En contra |
|---|---|---|---|
| **A. Crudo (elegida)** | 0-4095 | Sin pérdida de información; el escalado queda en el consumidor | El valor no significa nada sin conocer el hardware del esclavo — se resuelve documentándolo aquí |
| B. Normalizado a 0-255 | 0-255 | Coincide con el rango del PWM; replicación directa | Descarta 4 bits de resolución en el origen, de forma irreversible |

**Principio aplicado:** el esclavo transporta **la medición, no la
interpretación**. El escalado es una decisión de quien consume el dato, y hacerlo
en el origen destruye información que no se puede recuperar. Es el mismo criterio
por el que un transmisor de temperatura industrial envía `235` con factor 0,1 y no
un «caliente/frío».

### 7.2 Conversión aplicada por el maestro

```
pwm = adc >> 4       equivale a  adc ÷ 16

Verificación en los extremos:   4095 >> 4 = 255   exacto
                                   0 >> 4 =   0   exacto
                                2048 >> 4 = 128   punto medio
```

Operación **exacta en todo el rango y sin punto flotante**, lo que importa en un
lazo que se ejecuta cinco veces por segundo sobre un intérprete. Implementada una
sola vez, en la función `adc_a_pwm()` de
[firmware/comun/perifericos.py](../firmware/comun/perifericos.py).

### 7.3 Configuración del ADC

| Parámetro | Valor | Motivo |
|---|---|---|
| Resolución | 12 bits (0-4095) | Valor por defecto del ESP32 |
| Atenuación | 11 dB | Extiende el rango de medición a ≈0-3,3 V. Con la atenuación por defecto el rango útil sería de 0 a 1,1 V, y el valor saturaría al tercio del recorrido del potenciómetro |
| Promediado | 8 muestras | El ADC del ESP32 tiene ruido de varias unidades. Sin promediar, el registro cambiaría entre sondeos con el potenciómetro quieto: el LED PWM titilaría y el bus se llenaría de escrituras que no cambian nada. 8 es potencia de 2, por lo que el promedio se calcula con un desplazamiento en vez de una división |

> **La atenuación fue origen de un defecto real durante la puesta en marcha.** Los
> métodos que la configuran después de construir el objeto están obsoletos en las
> versiones recientes de MicroPython, y el código los invocaba dentro de un bloque
> que capturaba la excepción en silencio: la atenuación nunca se aplicaba. El
> diagnóstico completo está en
> [evidencia/INCONVENIENTES.md](../evidencia/INCONVENIENTES.md).

**Nota de precisión:** el ADC del ESP32 **no es lineal**, sobre todo cerca de los
extremos. Para este trabajo es irrelevante —se regula el brillo de un LED, no se
mide un proceso—, pero en una aplicación de medición real haría falta calibración
por tramos o un conversor externo, y el mapa de registros debería declarar la
incertidumbre asociada.

## 8. Rango del PWM

| Parámetro | Valor | Motivo |
|---|---|---|
| Rango en el registro | 0-255 | **Lo fija la consigna**, no el hardware: el ESP32 admite 16 bits de resolución |
| Frecuencia | 1 kHz | Muy por encima del umbral de fusión de parpadeo del ojo (≈60-90 Hz): la variación se percibe continua |
| Conversión interna | `duty_u16 = valor × 257` | MicroPython expone el ciclo de trabajo como entero de 16 bits. El factor 257 es exacto en los extremos —**255 × 257 = 65535**— y no requiere punto flotante |

**Saturación defensiva:** un Holding Register puede recibir cualquier valor de 16
bits desde el bus; un maestro mal configurado podría escribir 5000. El firmware
del esclavo **acota el valor al rango 0-255 en lugar de lanzar una excepción**.

> El criterio es el de un dispositivo de campo: **degradar de forma segura, no
> reiniciarse ante una orden inválida**. Un nodo que se cae porque recibió un
> valor fuera de rango es un nodo que un solo error de configuración puede sacar
> de servicio.

### 8.1 Zona muerta en la escritura

El maestro **no reescribe el registro si el valor no varió más de ±2** respecto
del último efectivamente escrito.

El fundamento es doble: el ruido residual del conversor, aun promediando ocho
muestras, produce oscilaciones de una o dos unidades tras el escalado a 0-255, lo
que genera un titileo perceptible en el LED; y cada reescritura consume una
transacción del bus para no cambiar nada.

Se aplica **solo a la escritura**: el Input Register sigue publicando el valor
real del conversor, sin filtrar. Filtrar la medición sería falsearla; filtrar la
orden es evitar trabajo inútil.

> La optimización tiene un caso de borde que hubo que resolver: si el esclavo se
> reinicia, sus salidas vuelven al estado seguro, y el maestro —comparando contra
> el valor que creía escrito— decidiría que no hace falta reescribir. El LED
> quedaría apagado hasta que alguien moviera el potenciómetro. Por eso el maestro
> **invalida el valor recordado** cuando un esclavo vuelve de una ausencia. Toda
> optimización basada en «ya lo escribí» es válida solo mientras se pueda sostener
> que el otro extremo no perdió el estado, y una reconexión rompe exactamente esa
> premisa.

## 9. Validación del mapa sobre hardware

Las catorce pruebas se ejecutaron con una herramienta MODBus de PC (QModMaster)
conectada por conversor USB↔RS-485, con el esclavo funcionando de forma
independiente. **Ninguna casilla se marcó por deducción: se marcó por haberlo
visto en pantalla.**

| # | Prueba | Resultado esperado | Resultado |
|---|---|---|---|
| 1 | Leer 10001 con el pulsador suelto | 0 | Correcto |
| 2 | Leer 10001 con el pulsador accionado | 1 | Correcto |
| 3 | Leer 30001 con el potenciómetro al mínimo | ≈ 0 | Correcto |
| 4 | Leer 30001 con el potenciómetro al máximo | ≈ 4095 | Correcto |
| 5 | Leer 30001 en el punto medio | ≈ 2048 | Correcto |
| 6 | Escribir 1 en 00001 | LED digital enciende | Correcto |
| 7 | Escribir 0 en 00001 | LED digital apaga | Correcto |
| 8 | Escribir 255 en 40001 | LED PWM al máximo brillo | Correcto |
| 9 | Escribir 128 en 40001 | LED PWM a brillo medio visible | Correcto |
| 10 | Escribir 0 en 40001 | LED PWM apagado | Correcto |
| 11 | Releer 40001 tras escribir 128 | Devuelve 128 | Correcto |
| 12 | Intentar escribir en 30001 | Rechazo: es de solo lectura | Correcto |
| 13 | Leer una dirección inexistente | Excepción **02** ILLEGAL DATA ADDRESS | Correcto |
| 14 | Repetir el conjunto contra el Esclavo 2 | Comportamiento idéntico | Correcto |

> Las pruebas **12 y 13 son las que más suelen omitirse** y las que más valor
> tienen. Demuestran que el esclavo **rechaza correctamente lo que debe rechazar**,
> no solo que responde a lo que le sale bien. Un sistema que atiende bien el
> camino correcto pero no rechaza lo inválido no está verificado: está probado a
> medias.

### 9.1 Verificación del mapa en operación autónoma

Con el maestro ESP32 sondeando el bus, el sistema sostuvo **750 ciclos de sondeo
consecutivos con una tasa de error del 0,0 %**, medidos por la instrumentación del
propio firmware y no por apreciación visual.

| Métrica | Valor medido |
|---|---|
| Ciclos completados | 750 |
| Ciclos con algún fallo | 0 |
| Tasa de error | 0,0 % |
| Duración útil del ciclo (4 transacciones) | 161 ms |
| Duración útil con zona muerta activa | ≈ 124 ms |

La diferencia entre ambas duraciones es el efecto medible de la zona muerta de la
§8.1: cuando el potenciómetro del maestro está quieto, la cuarta transacción no se
emite y el ciclo se acorta. Es una optimización cuyo beneficio se puede cuantificar
sobre la traza, no una mejora declarada.

### 9.2 Verificación del CRC

El cálculo del CRC-16/MODBUS se validó contra el **vector de prueba estándar**: la
cadena `123456789` debe producir `0x4B37`. Ese vector es precisamente lo que
distingue esta variante de otras que usan el mismo polinomio con distinto valor
inicial o distinta reflexión.

La verificación se ejecuta sin hardware:

```
python "tarea 1/herramientas/modbus_tramas.py"
```

Detalle del algoritmo y de los tres puntos donde se concentran los errores de
implementación —polinomio reflejado, valor inicial y orden de transmisión— en
[protocolo-comunicacion.md §7](protocolo-comunicacion.md#7-el-crc-16).

## 10. Retención de estado

> Requisito de la Parte 3: *«Verificar que el esclavo que no está seleccionado
> mantenga el último estado recibido en sus salidas hasta recibir una nueva
> orden.»*

### 10.1 Cómo se cumple

El comportamiento se cumple **por construcción**, y esto es una propiedad del
modelo de datos de MODBus más que del firmware: el Coil y el Holding Register
**conservan su valor en la memoria del servidor mientras nadie los escriba**. El
lazo del esclavo simplemente refleja ese contenido en el hardware en cada vuelta.

No hay —ni debe haber— lógica de retención explícita. Lo que **sí** depende del
firmware es el requisito complementario: **no reinicializar esos registros dentro
del lazo**. Por eso los valores iniciales se fijan una única vez, en el arranque.

| Qué lo garantiza | Dónde |
|---|---|
| Los registros conservan su valor | Modelo de datos de MODBus |
| Las salidas siguen al registro | `aplicar_salidas()`, en cada vuelta del lazo |
| Los registros no se reinicializan | Configuración del servidor, una sola vez en el arranque |

### 10.2 Cómo se verificó

La consigna pide **verificar**, y una propiedad que no se puede observar no está
verificada. El esclavo emite evidencia con marca de tiempo:

```
[     2.600] A [ESCLAVO 2] RETENCION: sin ordenes hace 1600 ms. Salidas mantenidas en LED=1 PWM=200
[     5.000] I [ESCLAVO 2] latido: tramas=62 propias=24 ajenas=38 errores=0 | DI=0 IR=2047
   salidas: LED=1 PWM=200 | 12 ordenes, ultima hace 4000 ms  <- RETENIENDO
[    10.000] I [ESCLAVO 2] latido: tramas=112 propias=24 ajenas=88 errores=0 | DI=0 IR=2047
   salidas: LED=1 PWM=200 | 12 ordenes, ultima hace 9000 ms  <- RETENIENDO
[    16.400] A [ESCLAVO 2] FIN DE RETENCION: llego una orden. Salidas durante la pausa: SIN CAMBIOS (LED=1 PWM=200)
```

| Observación | Qué demuestra |
|---|---|
| `salidas: LED=1 PWM=200` idéntico en todos los latidos | Las salidas no cambiaron durante la pausa |
| `12 ordenes` no avanza | Ninguna orden de escritura llegó en ese intervalo |
| `ultima hace 4000 → 9000 → 14000 ms` | El intervalo sin órdenes crece: la pausa es real y sostenida |
| `propias` congelado mientras `ajenas` crece | **El nodo está vivo y procesando el bus**, pero no se lo está direccionando |
| `FIN DE RETENCION: SIN CAMBIOS` | El firmware comparó las salidas al entrar y al salir de la retención |

> La cuarta fila es la que cierra el argumento. **Un nodo colgado también
> mantendría sus salidas quietas**: lo que distingue la retención correcta de un
> cuelgue es que el nodo siga procesando el bus mientras retiene, y eso es
> exactamente lo que muestra el contador de tramas ajenas creciendo.

Solo cuentan como «orden» las funciones de escritura (0x05, 0x06, 0x0F, 0x10)
dirigidas a ese nodo. Una lectura no puede modificar una salida, y una escritura
dirigida al *otro* esclavo tampoco — que es justamente el caso central del
requisito.

Procedimiento completo de verificación en
[DEPURACION-PARTE-3.md §5.2](../DEPURACION-PARTE-3.md).

## 11. Escalabilidad del mapa

El mapa actual usa un elemento por área, muy lejos del límite de 125 registros por
transacción. Si el sistema creciera:

| Cambio | Impacto en el mapa | Impacto en el código |
|---|---|---|
| Más variables por esclavo | Direcciones **contiguas** dentro de cada área | Una sola función 0x03/0x04 con `qty=N`, en lugar de N transacciones |
| Más esclavos (ID 3, 4, …) | Ninguno: el mapa es idéntico | Solo cambia el destinatario; el selector pasa a codificar más de dos valores |
| Variables de 32 bits | Ocupan **dos registros consecutivos**; hay que declarar el orden de palabras | Composición explícita de los dos registros |
| Distintas frecuencias de refresco | Agrupar por frecuencia: lo rápido en un bloque, lo lento en otro | Dos ciclos de sondeo con períodos distintos |

Ejemplo concreto del primer caso:

| Variable | Modicon | Offset | Función |
|---|---|---|---|
| Potenciómetro 1 | 30001 | 0x0000 | 0x04 |
| Potenciómetro 2 | 30002 | 0x0001 | 0x04 |

Al quedar **contiguas**, el maestro las lee con **una sola** transacción FC04 con
`cant=2`, en lugar de dos transacciones.

> La regla que sostiene todo esto: **agrupar registros contiguos en una sola
> lectura**. En un maestro MODBus real es la optimización de mayor impacto, porque
> reduce la cantidad de tramas y con ella los silencios entre tramas, que son el
> costo fijo dominante del bus. Un mapa mal ordenado condena al maestro a
> fragmentar lecturas que podrían ser una sola, y esa decisión se toma al escribir
> el mapa de registros, no al programar el maestro.

Sobre las variables de 32 bits corresponde una advertencia: además del orden de
los bytes dentro de cada registro, interviene el **orden de los registros entre
sí**, que **varía según el fabricante y no está normalizado**. No fue necesario en
este trabajo, pero es la causa habitual de valores inconsistentes al integrar
instrumentos comerciales. El criterio profesional es documentar el orden en el
mapa y verificarlo con un valor conocido, nunca asumirlo.

---

## Referencias

- Modbus Organization. (2012). *MODBUS Application Protocol Specification V1.1b3*. Modbus Organization, Inc.
- Modbus Organization. (2006). *MODBUS over Serial Line Specification and Implementation Guide V1.02*. Modbus Organization, Inc.
