# Mapa de registros MODBus

**Tarea Nº1 — Red MODBus RTU sobre RS-485** · Protocolos de Comunicaciones Industriales · UNRaf

Este documento es el **contrato de datos** del sistema: qué variable vive en qué
dirección, con qué tipo, rango y escala. Es el entregable que hace reproducible y
auditable cualquier integración MODBus — sin él, el próximo que toque el sistema
(incluido uno mismo en seis meses) tiene que adivinar.

Complementa a [arquitectura.md](arquitectura.md) (capa física) y a
[protocolo-comunicacion.md](protocolo-comunicacion.md) (tramas, CRC y parámetros
del puerto serie, que se justifican allí).

**Estado:** v1.0 — pendiente de validar contra el hardware real (Fase 2 del plan).

---

## 1. Identificación de nodos

| Nodo | Rol | Unit ID | Hardware |
|---|---|---|---|
| Maestro | Cliente / iniciador | **ninguno** | ESP32 + MAX485 |
| Esclavo 1 | Servidor | **1** | ESP32 + MAX485 · jumper GPIO13 abierto |
| Esclavo 2 | Servidor | **2** | ESP32 + MAX485 · jumper GPIO13 a GND |
| PC (Modbus Poll) | Cliente, solo Parte 1 | **ninguno** | Conversor USB↔RS-485 |

Direcciones válidas en MODBus serie: **1 a 247**. El 0 se reserva para difusión
(*broadcast*) y no se usa en este trabajo, porque una orden de difusión no genera
respuesta y por lo tanto no permite confirmar que llegó.

Un maestro MODBus **no tiene dirección propia**: nunca es destinatario de una
trama, solo emisor.

## 2. Parámetros del bus

| Parámetro | Valor |
|---|---|
| Modo | RTU (binario) |
| Baudrate | 9600 |
| Bits de datos | 8 |
| Paridad | Ninguna |
| Bits de parada | 1 |

Justificación completa de cada valor en
[protocolo-comunicacion.md §3](protocolo-comunicacion.md#3-configuración-del-puerto-serie).
Deben ser **idénticos en los tres ESP32 y en Modbus Poll**; están centralizados
en [firmware/comun/config.py](../firmware/comun/config.py) para garantizarlo por
construcción.

## 3. Mapa de registros — idéntico en Esclavo 1 y Esclavo 2

Ambos esclavos implementan **exactamente el mismo mapa**; solo cambia el Unit ID.
Es un requisito de la Parte 3: permite que el maestro conmute de esclavo sin
cambiar ninguna dirección, únicamente el destinatario.

| Dir. Modicon | Offset en trama | Área | Función L | Función E | Tipo | Variable | Rango | Escala | L/E |
|---|---|---|---|---|---|---|---|---|---|
| **10001** | `0x0000` | Discrete Input | 0x02 | — | 1 bit | Switch / pulsador | 0-1 | — | L |
| **30001** | `0x0000` | Input Register | 0x04 | — | UINT16 | Potenciómetro (ADC) | 0-4095 | ×1 (crudo) | L |
| **00001** | `0x0000` | Coil | 0x01 | 0x05 | 1 bit | LED 1 digital | 0-1 (0xFF00/0x0000) | — | L/E |
| **40001** | `0x0000` | Holding Register | 0x03 | 0x06 | UINT16 | LED 2 PWM | 0-255 | ×1 | L/E |

### 3.1 Correspondencia con los pines físicos

| Dirección Modicon | GPIO del ESP32 | Componente |
|---|---|---|
| 10001 | GPIO18 | Pulsador a GND, pull-up interno, activo en bajo |
| 30001 | GPIO34 | Potenciómetro 10 kΩ, ADC1, 12 bits |
| 00001 | GPIO19 | LED + resistencia 330 Ω |
| 40001 | GPIO21 | LED + resistencia 330 Ω, PWM a 1 kHz |

Detalle del conexionado en [arquitectura.md §8](arquitectura.md#8-asignación-de-pines).

## 4. Desfasaje de direccionamiento (off-by-one)

La numeración `1xxxx / 3xxxx / 0xxxx / 4xxxx` es la **notación Modicon**: el
primer dígito identifica el área de datos y los cuatro siguientes numeran la
posición **desde 1**. En la trama real, en cambio, la dirección viaja como un
**offset desde 0** dentro de esa área.

```
40001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x03 / 0x06
30001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x04
10001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x02
00001 (Modicon)  →  0x0000 en el campo de dirección de una función 0x05
```

> **Que las cuatro variables compartan el offset `0x0000` no es una colisión.**
> Cada área de MODBus tiene su propio espacio de direcciones independiente, y es
> el **código de función** el que determina en qué área se busca ese offset. Una
> función 0x02 con dirección 0x0000 y una función 0x04 con dirección 0x0000
> acceden a variables completamente distintas.

**Este desfasaje es el error más común al integrar MODBus.** Verificación
obligatoria antes de dar por buena la implementación: escribir un valor conocido
y **distinto en cada área** (por ejemplo Coil 0 = 1 y HR 0 = 200) y comprobar que
Modbus Poll lo lee donde corresponde.

Modbus Poll y otras herramientas permiten configurar si direccionan con base 0 o
base 1. Si el valor aparece corrido en uno, **el problema es de configuración de
la herramienta, no del firmware**. El síntoma típico del error es la excepción
**02 (ILLEGAL DATA ADDRESS)**.

## 5. Escala del potenciómetro

El ADC del ESP32 es de **12 bits (0-4095)**, a diferencia del de un Arduino UNO
(10 bits, 0-1023). El rango es una característica del hardware del esclavo, y por
eso se documenta acá y no en el código.

### 5.1 Decisión: se transmite el valor crudo

| Opción | Valor en 30001 | A favor | En contra |
|---|---|---|---|
| **A. Crudo (elegida)** | 0-4095 | Sin pérdida de información; el escalado queda en el consumidor del dato | El valor no significa nada sin conocer el hardware del esclavo — se resuelve documentándolo acá |
| B. Normalizado a 0-255 | 0-255 | Coincide con el rango del PWM; replicación directa | Se descartan 4 bits de resolución en el origen, de forma irreversible |

**Principio aplicado:** el esclavo transporta **la medición, no la
interpretación**. El escalado es una decisión de quien consume el dato, y hacerlo
en el origen destruye información que no se puede recuperar. Es el mismo criterio
por el que un transmisor de temperatura envía `235` con factor 0,1 y no un
"caliente/frío".

### 5.2 Conversión aplicada por el maestro

El maestro convierte de ADC a PWM con un **desplazamiento de 4 bits**:

```
pwm = adc >> 4       equivale a  adc ÷ 16

Verificación en los extremos:   4095 >> 4 = 255   ✔ exacto
                                   0 >> 4 =   0   ✔ exacto
                                2048 >> 4 = 128   ✔ punto medio
```

Operación exacta en todo el rango y **sin punto flotante**, lo que importa en un
lazo que se ejecuta cinco veces por segundo sobre un intérprete. Implementada una
sola vez en `adc_a_pwm()` de
[firmware/comun/perifericos.py](../firmware/comun/perifericos.py).

### 5.3 Configuración del ADC

| Parámetro | Valor | Motivo |
|---|---|---|
| Resolución | 12 bits (0-4095) | Valor por defecto del ESP32 |
| Atenuación | 11 dB | Extiende el rango de medición a ≈0-3,3 V. Con la atenuación por defecto (0 dB) el rango útil sería 0-1,1 V y el valor saturaría al tercio del recorrido del potenciómetro |
| Promediado | 8 muestras | El ADC SAR del ESP32 tiene ruido de varias unidades de LSB. Sin promediar, el registro cambiaría entre sondeos con el potenciómetro quieto: el LED PWM del maestro titilaría y el bus se llenaría de escrituras innecesarias. 8 es potencia de 2, por lo que el promedio se calcula con un desplazamiento en vez de una división |

> **Nota de precisión:** el ADC del ESP32 **no es lineal**, sobre todo cerca de
> los extremos del rango. Para este trabajo es irrelevante (se regula el brillo de
> un LED, no se mide un proceso). En una aplicación de medición real haría falta
> calibración por tramos o un ADC externo, y el mapa de registros debería declarar
> la incertidumbre.

## 6. Rango del PWM

| Parámetro | Valor | Motivo |
|---|---|---|
| Rango en el registro | 0-255 | **Lo fija la consigna**, no el hardware: el ESP32 admite 16 bits de resolución de PWM |
| Frecuencia | 1 kHz | Muy por encima del umbral de fusión de parpadeo del ojo (~60-90 Hz): la variación se percibe continua |
| Conversión interna | `duty_u16 = valor × 257` | MicroPython expone el ciclo de trabajo como entero de 16 bits (0-65535). El factor 257 es exacto en los extremos: **255 × 257 = 65535**, y no requiere punto flotante |

**Saturación defensiva:** un Holding Register puede recibir cualquier valor de 16
bits desde el bus (un maestro mal configurado podría escribir 5000). El firmware
del esclavo **acota el valor al rango 0-255 en lugar de lanzar una excepción**: un
dispositivo de campo debe degradar de forma segura, no reiniciarse ante una orden
inválida.

## 7. Transacciones del maestro por ciclo

| # | Sentido | Función | Dirección | Datos | Propósito |
|---|---|---|---|---|---|
| 1 | Maestro → Esclavo N | 0x02 | `0x0000`, qty=1 | — | Leer switch remoto |
| 2 | Maestro → Esclavo N | 0x04 | `0x0000`, qty=1 | — | Leer potenciómetro remoto |
| 3 | Maestro → Esclavo N | 0x05 | `0x0000` | `0xFF00` / `0x0000` | Escribir LED 1 del esclavo |
| 4 | Maestro → Esclavo N | 0x06 | `0x0000` | `0x0000`-`0x00FF` | Escribir PWM del esclavo |

Cuatro transacciones por ciclo, cada una con su petición y su respuesta. El bus
es half-duplex: nunca hay dos nodos transmitiendo a la vez.

Período de sondeo: **200 ms** (51 % de ocupación del bus). Cálculo completo en
[protocolo-comunicacion.md §11.2](protocolo-comunicacion.md#112-cálculo-del-período-de-sondeo).

## 8. Validación del mapa (Fase 2 del plan)

Checklist a completar con Modbus Poll antes de programar el maestro. **Ninguna
casilla se marca por deducción: se marca por haberlo visto en pantalla.**

| # | Prueba | Resultado esperado | ✔ |
|---|---|---|---|
| 1 | Leer 10001 con el switch suelto | 0 | ⬜ |
| 2 | Leer 10001 con el switch accionado | 1 | ⬜ |
| 3 | Leer 30001 con el potenciómetro al mínimo | ≈ 0 | ⬜ |
| 4 | Leer 30001 con el potenciómetro al máximo | ≈ 4095 | ⬜ |
| 5 | Leer 30001 en el punto medio | ≈ 2048 | ⬜ |
| 6 | Escribir 1 en 00001 | LED 1 enciende | ⬜ |
| 7 | Escribir 0 en 00001 | LED 1 apaga | ⬜ |
| 8 | Escribir 255 en 40001 | LED 2 al máximo brillo | ⬜ |
| 9 | Escribir 128 en 40001 | LED 2 a brillo medio visible | ⬜ |
| 10 | Escribir 0 en 40001 | LED 2 apagado | ⬜ |
| 11 | Releer 40001 después de escribir 128 | Devuelve 128 (retención) | ⬜ |
| 12 | Intentar escribir en 30001 | Excepción 01 o 02 (es de solo lectura) | ⬜ |
| 13 | Leer una dirección inexistente (p. ej. 40010) | Excepción **02** ILLEGAL DATA ADDRESS | ⬜ |
| 14 | Repetir todo contra el Esclavo 2 (Unit ID 2) | Idéntico comportamiento | ⬜ |

> Las pruebas **12 y 13 son las que más suelen omitirse** y las que más valor
> tienen en el informe: demuestran que el esclavo rechaza correctamente lo que
> debe rechazar, no solo que responde a lo que le sale bien. Un informe que solo
> muestra el camino feliz se lee como un informe sin trabajo de banco real.

## 9. Escalabilidad del mapa

Punto para la sección de conclusiones del informe. El mapa actual usa 1 elemento
por área, muy lejos del límite de 125 registros por transacción. Si el sistema
creciera:

| Cambio | Impacto en el mapa | Impacto en el código |
|---|---|---|
| Más variables por esclavo | Direcciones **contiguas** dentro de cada área | Una sola función 0x03/0x04 con `qty=N` en vez de N transacciones |
| Más esclavos (ID 3, 4, …) | Ninguno: el mapa es idéntico | Solo cambia el destinatario; el selector pasa a codificar más de 2 valores |
| Variables de 32 bits (float, contadores) | Ocupan **2 registros consecutivos**; hay que declarar el orden de palabras (*word swap*) | Composición explícita de los dos registros |
| Distintas frecuencias de refresco | Agrupar por frecuencia: lo rápido junto, lo lento en otro bloque | Dos ciclos de sondeo con períodos distintos |

La regla que sostiene todo esto: **agrupar registros contiguos en una sola
lectura**. En un maestro MODBus real es la optimización más importante, porque
reduce el número de tramas y con él los silencios t3,5, que son el costo fijo
dominante del bus.

---

## Referencias

- Modbus Organization. (2012). *MODBUS Application Protocol Specification V1.1b3*. Modbus.org.
- Modbus Organization. (2006). *MODBUS over Serial Line Specification and Implementation Guide V1.02*. Modbus.org.
