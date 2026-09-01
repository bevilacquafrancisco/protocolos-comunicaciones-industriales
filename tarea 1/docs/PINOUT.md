# Conexionado y asignación de pines — Tarea Nº1

Hardware confirmado: 3 × ESP32 DevKit, 3 × módulo MAX485 (TTL↔RS-485), 1 × conversor USB↔RS-485.

---

## 1. PROBLEMA ELÉCTRICO CRÍTICO — leer antes de energizar

El módulo MAX485 y el ESP32 **no son directamente compatibles**. Del datasheet
MAX481/MAX483/MAX485 (Maxim Integrated, rev. 8, 10/03), incluido en `docs/MAX481.PDF`:

| Parámetro | Símbolo | Valor de datasheet |
|---|---|---|
| Tensión de alimentación | VCC | **4,75 V ≤ VCC ≤ 5,25 V** |
| Tensión de entrada alta (DI, DE, RE) | VIH | **2,0 V mín.** |
| Tensión de entrada baja (DI, DE, RE) | VIL | 0,8 V máx. |
| Tensión de salida alta del receptor (RO) | VOH | **3,5 V mín.** (en la práctica ≈ VCC) |
| Umbral diferencial del receptor | VTH | ±200 mV |
| Resistencia de entrada (A, B) | RIN | 12 kΩ mín. (1 carga unitaria) |

El ESP32 tiene lógica de 3,3 V con un **máximo absoluto de 3,6 V** en sus GPIO.
De ahí surgen dos situaciones opuestas, y confundirlas es el error más caro del trabajo.

### 1.1 ESP32 → MAX485 (DI, DE, RE): conexión directa, sin adaptación

El ESP32 entrega 3,3 V y el MAX485 necesita **VIH ≥ 2,0 V** para leer un "1".
Margen de ruido: 3,3 − 2,0 = **1,3 V**. La conexión es directa y no hace falta
level shifter en este sentido — agregarlo es un error frecuente que sólo suma
puntos de falla.

### 1.2 MAX485 → ESP32 (RO → RX): DIVISOR RESISTIVO OBLIGATORIO

El pin RO entrega **VOH ≥ 3,5 V**, y en la práctica ≈ 5 V, contra un máximo
absoluto de 3,6 V del GPIO del ESP32. Conectarlo directo **inyecta corriente en
los diodos de protección del pin y degrada o destruye el ESP32**. Solución:
divisor resistivo en el camino RO → RX.

```
   MAX485 RO ──┬── R1 = 2,2 kΩ ──┬──► ESP32 GPIO16 (UART2 RX)
               │                 │
            (≈5 V)          R2 = 3,3 kΩ
                                 │
                                GND
```

**Verificación del diseño (peor caso, VCC = 5,25 V):**

```
V_RX = VCC × R2/(R1+R2) = 5,25 × 3300/5500 = 3,15 V
```

| Criterio | Valor | Requisito | ¿Cumple? |
|---|---|---|---|
| Nivel máximo en el GPIO | 3,15 V | ≤ 3,6 V (máx. absoluto) | Sí — margen 0,45 V |
| Nivel alto reconocido | 3,15 V | ≥ VIH_ESP32 = 0,75 × 3,3 = 2,48 V | Sí — margen 0,67 V |
| Corriente por el divisor | 5,25/5500 = 0,95 mA | ≪ IOSR del MAX485 (7 mA mín.) | Sí |

**Verificación de que el divisor no arruina el timing** (objeción típica de defensa oral):

```
R_Thévenin = R1 ∥ R2 = 2200 ∥ 3300 = 1,32 kΩ
C_parásita ≈ 50 pF (pin del ESP32 + cableado de protoboard)
tau = R × C = 1,32 kΩ × 50 pF = 66 ns
t_subida (10-90 %) = 2,2 × tau = 145 ns

Tiempo de bit a 9600 baudios = 1/9600 = 104 µs
Distorsión = 145 ns / 104 µs = 0,14 %
```

Despreciable. El divisor es válido a 9600 baudios con enorme margen. (A 1 Mbaud,
con un tiempo de bit de 1 µs, esa distorsión del 14,5 % sí sería un problema:
por eso la verificación se hace con números y no por costumbre.)

### 1.3 Alternativas descartadas

| Alternativa | Por qué se descartó |
|---|---|
| Alimentar el módulo MAX485 a 3,3 V | Queda **fuera de especificación** (VCC mín. = 4,75 V). "Anda en el banco" pero la tensión diferencial de salida cae y el margen de ruido se degrada sin poder cuantificarlo. No es defendible ante la cátedra. |
| Reemplazar por MAX3485 (3,3 V nativo) | Es la solución técnicamente superior, pero implica comprar 3 módulos nuevos. Con el divisor, el hardware ya disponible cumple con margen verificado por cálculo. |
| Level shifter bidireccional (TXS0108E) | Sobredimensionado: de las cuatro líneas, sólo una necesita adaptación. Viola KISS y agrega un componente activo más que puede fallar. |

**Decisión: divisor resistivo 2,2 kΩ / 3,3 kΩ en RO → RX, con el módulo
alimentado a 5 V desde el pin VIN del ESP32.**

---

## 2. Asignación de pines

Criterios de selección de GPIO en el ESP32:

- **Excluidos GPIO 6-11**: conectados a la memoria flash SPI interna. Usarlos cuelga el chip.
- **Excluidos GPIO 0, 2, 12, 15**: pines de *strapping*; su nivel durante el
  arranque determina el modo de booteo. Un LED o un pulsador conectado ahí puede
  impedir que el ESP32 arranque, con un síntoma desconcertante.
- **GPIO 34-39**: sólo entrada, sin pull-up/pull-down interno. Ideales para el
  ADC, inútiles como salida.
- **ADC1 (GPIO 32-39)** preferido sobre ADC2: el ADC2 queda inutilizable mientras
  el WiFi está activo. Aunque este trabajo no usa WiFi, se elige ADC1 para no
  cerrar la puerta a una futura pasarela Modbus↔MQTT (escalabilidad, sección de
  conclusiones del informe).

### 2.1 Esclavo 1 y Esclavo 2 (firmware idéntico)

| Función | GPIO | Dirección Modbus | Conexión |
|---|---|---|---|
| UART2 TX → DI del MAX485 | 17 | — | Directo |
| UART2 RX ← RO del MAX485 | 16 | — | **Vía divisor 2k2/3k3** |
| DE + RE (unidos) | 4 | — | Directo. Alto = transmitir, bajo = recibir |
| Switch / pulsador | 18 | 10001 (Discrete Input 0) | A GND, con pull-up interno → activo en bajo |
| Potenciómetro (cursor) | 34 | 30001 (Input Register 0) | Extremos a 3,3 V y GND |
| LED 1 digital | 19 | 00001 (Coil 0) | Ánodo al pin, R serie 330 Ω a GND |
| LED 2 PWM | 21 | 40001 (Holding Register 0) | Ánodo al pin, R serie 330 Ω a GND |
| **Jumper selector de Unit ID** | 13 | — | Abierto = ID 1 · A GND = ID 2 |

**Sobre el jumper de Unit ID (GPIO 13):** la consigna pide "dirección física
fija". Un jumper es literalmente eso, y es la forma en que los equipos
industriales reales fijan su dirección (las llaves DIP de un variador o de un
módulo de E/S remoto). Se gana además que **ambos esclavos corren exactamente el
mismo firmware**, lo que elimina la clase de error "actualicé un esclavo y me
olvidé del otro" (principio DRY). Se descartó GPIO 5, pese a estar libre, porque
es pin de *strapping* y forzarlo a bajo durante el arranque es riesgoso.

### 2.2 Maestro

| Función | GPIO | Conexión |
|---|---|---|
| UART2 TX → DI del MAX485 | 17 | Directo |
| UART2 RX ← RO del MAX485 | 16 | **Vía divisor 2k2/3k3** |
| DE + RE (unidos) | 4 | Directo |
| Switch local (se escribe al Coil del esclavo) | 18 | Pull-up interno, activo en bajo |
| Potenciómetro local (se escribe al HR del esclavo) | 34 | ADC1_CH6 |
| LED replicador digital (refleja el DI del esclavo) | 19 | R serie 330 Ω |
| LED replicador PWM (refleja el IR del esclavo) | 21 | R serie 330 Ω |
| Switch selector de esclavo | 13 | Abierto = Esclavo 1 · A GND = Esclavo 2 |
| LED indicador "Esclavo 1 activo" | 22 | R serie 330 Ω |
| LED indicador "Esclavo 2 activo" | 23 | R serie 330 Ω |

Los pines comunes (UART, DE/RE, switch, potenciómetro, LED digital, LED PWM) son
**los mismos en maestro y esclavos**. Reduce errores de cableado en el banco y
permite compartir un único módulo de periféricos entre los tres firmwares.

### 2.3 Cálculo de la resistencia serie de los LEDs

LED rojo típico: Vf ≈ 2,0 V, corriente de trabajo elegida ≈ 4 mA (más que
suficiente para verlo, y deja el GPIO muy por debajo de su límite).

```
R = (V_GPIO − Vf) / I = (3,3 − 2,0) / 0,004 = 325 Ω  →  valor comercial: 330 Ω
I_real = (3,3 − 2,0) / 330 = 3,9 mA
```

El ESP32 admite hasta 40 mA por pin, con un límite agregado por banco de puertos.
Con 4 LEDs a 3,9 mA, el maestro consume 15,6 mA en sus salidas: sin problemas.

---

## 3. Bus RS-485

### 3.1 Topología

```
   [USB-RS485]      [MAESTRO]        [ESCLAVO 1]       [ESCLAVO 2]
    (sólo P1)           │                 │                 │
        │               │                 │                 │
  ══╤═══╧═══════════════╧═════════════════╧═════════════════╧═══╤══  A
    │                                                           │
  ══╧═══════════════════════════════════════════════════════════╧══  B
   120 Ω                                                      120 Ω
  (extremo)                                                 (extremo)

       GND ────────────── GND común a TODOS los nodos ──────────────
```

Reglas de la capa física, y el porqué de cada una:

1. **Bus lineal, nunca estrella.** Las derivaciones (*stubs*) desde el bus hasta
   cada nodo deben ser lo más cortas posible (< 30 cm en protoboard). Una
   topología en estrella crea múltiples reflexiones que ninguna terminación puede
   absorber.
2. **Terminación de 120 Ω sólo en los dos extremos físicos.** El valor iguala la
   impedancia característica del par trenzado: la onda que llega al final se
   disipa en la resistencia en vez de reflejarse hacia atrás e interferir con los
   bits siguientes. Poner terminación también en un nodo intermedio carga el bus
   de más y reduce la amplitud diferencial.
3. **GND común entre todos los nodos.** RS-485 es diferencial, pero el receptor
   sólo tolera una tensión de modo común de −7 V a +12 V respecto de *su propia*
   masa. Sin referencia común esa condición no está garantizada. Es la causa
   número uno de "anda entre dos nodos pero se cae al agregar el tercero".
4. **Polarización de reposo (fail-safe biasing) en un único punto** — ver §3.2.

### 3.2 Polarización de reposo: por qué es obligatoria acá

Cuando ningún nodo transmite (todos los DE en bajo), los drivers quedan en alta
impedancia. Con las dos terminaciones de 120 Ω instaladas, A y B quedan unidas
por 60 Ω y la tensión diferencial cae a ≈ 0 V, es decir, **dentro de la zona
indeterminada de ±200 mV** del receptor (VTH del datasheet). El pin RO oscila
siguiendo el ruido, y el UART del ESP32 interpreta esos flancos como bits de
arranque espurios: se llena de bytes basura y descarta las tramas buenas.

> El datasheet menciona una función *fail-safe* que garantiza RO en alto con la
> entrada **en circuito abierto**. No aplica en este caso: con las terminaciones
> instaladas la entrada no está abierta, está cargada por 60 Ω.

Red de polarización, en **un solo punto del bus** (se instala en el nodo maestro):

```
   +5 V ── R_up = 680 Ω ──── línea A

   GND  ── R_dn = 680 Ω ──── línea B
```

Verificación del valor elegido:

```
Terminaciones en paralelo:  120 ∥ 120 = 60 Ω
Malla:  R_up + 60 + R_dn = 680 + 60 + 680 = 1420 Ω
I = 5 V / 1420 Ω = 3,52 mA
V_AB(reposo) = 3,52 mA × 60 Ω = 211 mV  ≥  200 mV requeridos
```

Con 211 mV el receptor ve un "1" lógico estable (línea en reposo = marca), que es
exactamente lo que el UART necesita para no dispararse. Si se usaran 1 kΩ, la
tensión caería a 145 mV y quedaría **dentro** de la zona indeterminada: el bus
seguiría sin funcionar y la causa sería dificilísima de encontrar sin osciloscopio.

### 3.3 Carga del bus

Cada MAX485 presenta 1 carga unitaria (RIN ≥ 12 kΩ). Con 4 nodos (3 ESP32 más el
conversor USB) se usan 4 de las 32 cargas unitarias admitidas por el estándar.
Sin problemas de capacidad de bus.

---

## 4. Lista de materiales adicional

| Componente | Cantidad | Uso |
|---|---|---|
| Resistencia 2,2 kΩ | 3 | Divisor RO→RX (una por nodo) |
| Resistencia 3,3 kΩ | 3 | Divisor RO→RX (una por nodo) |
| Resistencia 330 Ω | 8 | LEDs (2 por esclavo + 4 en el maestro) |
| Resistencia 120 Ω | 2 | Terminación del bus (sólo en los extremos) |
| Resistencia 680 Ω | 2 | Polarización de reposo (un solo punto del bus) |
| LED 5 mm | 8 | 2 por esclavo, 4 en el maestro |
| Potenciómetro 10 kΩ | 3 | Entrada analógica de cada nodo |
| Pulsador / llave | 6 | 1 switch + 1 jumper de ID o selector por nodo |

---

## 5. Procedimiento de puesta en marcha (bring-up)

No saltear pasos: cada uno aísla una clase de falla distinta, y saltearlos
convierte un problema simple en tres problemas superpuestos.

| # | Paso | Criterio de aceptación |
|---|---|---|
| 1 | Inspección visual y continuidad **sin alimentar** | Sin cortos entre 5 V/3,3 V y GND; A y B no cortocircuitadas entre sí |
| 2 | Alimentar el MAX485 y forzar RO alto; medir el divisor | Tensión en el nodo del divisor entre 2,9 y 3,2 V. **Si mide ≈5 V, NO conectar al ESP32** |
| 3 | Alimentar los ESP32 y correr un *blink* | Confirma alimentación, reloj y toolchain de MicroPython |
| 4 | Probar los periféricos locales uno por vez (switch, ADC, LED, PWM), sin Modbus | Cada uno responde de forma aislada |
| 5 | Armar el bus completo y medir la polarización de reposo, con todos los nodos callados | V(A) − V(B) ≈ 200-220 mV, estable |
| 6 | Modbus Poll ↔ Esclavo 1, con el resto de los nodos apagados | Lectura y escritura correctas en las 4 direcciones |
| 7 | Agregar el maestro (Parte 2) | Sondeo estable, sin timeouts durante 5 minutos continuos |
| 8 | Agregar el Esclavo 2 (Parte 3) | Conmutación en vivo; el esclavo no seleccionado retiene su estado |
