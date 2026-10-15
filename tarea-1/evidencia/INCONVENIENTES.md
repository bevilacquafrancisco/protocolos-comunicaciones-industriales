# Inconvenientes encontrados durante el desarrollo y su resolución

**Tarea Nº1 — Red MODBus RTU sobre RS-485** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Este documento registra, en orden cronológico, los problemas reales de banco
encontrados durante la implementación de las Partes 1 y 2, el proceso de
diagnóstico seguido para cada uno (incluidas las hipótesis descartadas) y la
justificación técnica de la solución aplicada.

No es un registro cosmético: cada problema descrito acá detuvo el avance del
proyecto en algún momento, y la resolución de cada uno está verificada contra
evidencia real de banco (logs, capturas de tramas, mediciones), no contra una
suposición. Se incluyen las hipótesis que se descartaron, porque el camino para
llegar a la causa raíz es tan relevante para la defensa oral como la causa raíz
misma — la mitad de las preguntas típicas de cátedra son justamente "¿y cómo se
dieron cuenta de que era eso y no otra cosa?".

---

## Índice

1. [Prueba de LED sin verificación real](#1-prueba-de-led-sin-verificación-real)
2. [Atenuación del ADC no aplicada — potenciómetro con rango comprimido](#2-atenuación-del-adc-no-aplicada--potenciómetro-con-rango-comprimido)
3. [Timeout de recepción insuficiente para un esclavo MicroPython](#3-timeout-de-recepción-insuficiente-para-un-esclavo-micropython)
4. [RO en alta impedancia genera bytes espurios — la causa raíz de los "invalid response CRC"](#4-ro-en-alta-impedancia-genera-bytes-espurios--la-causa-raíz-de-los-invalid-response-crc)
5. [Hallazgo: diferencia entre el tiempo de ciclo teórico y el medido](#5-hallazgo-diferencia-entre-el-tiempo-de-ciclo-teórico-y-el-medido)

---

## 1. Prueba de LED sin verificación real

### Contexto

Durante la Fase 1 (bring-up eléctrico), al revisar el código de
`firmware/prueba_perifericos.py` para depurar un problema distinto (§2), se
detectó una inconsistencia entre lo que el propio código documentaba y lo que
efectivamente hacía.

### Diagnóstico

El docstring de `prueba_led_digital()` afirmaba explícitamente:

```
Retorna
-------
bool
    True si el operador confirma que vio parpadear el LED.
```

Pero el cuerpo de la función hacía parpadear el LED cinco veces y retornaba
`True` **sin condición alguna**, sin pedir ninguna confirmación:

```python
for i in range(1, 6):
    led.escribir(True)
    ...
led.escribir(False)
print("  Resultado esperado: 5 parpadeos visibles.")
return True   # incondicional — el docstring prometía otra cosa
```

`prueba_led_pwm()` tenía el mismo patrón. En la práctica, esto significa que el
checklist de banco podía mostrar **"OK" en ambos LEDs sin que hubiera prueba
alguna de que efectivamente encendieran** — un LED con la polaridad invertida,
sin resistencia, o con el retorno a GND cortado habría dado exactamente el mismo
resultado en pantalla que uno funcionando correctamente.

### Por qué importa

Este tipo de falso positivo es particularmente peligroso en un checklist de
puesta en marcha: el objetivo de `prueba_perifericos.py` es **aislar** el
hardware antes de sumarle la complejidad de MODBus (documentado explícitamente
en su propio encabezado). Un test que no verifica nada rompe esa garantía sin
avisar, y el error se descubre recién más adelante, mezclado con otras posibles
causas — exactamente el escenario que la herramienta existe para evitar.

### Solución aplicada

Se modificaron ambas funciones para pedir confirmación explícita del operador
mediante `input()`, disponible en el REPL de Thonny durante la ejecución con F5:

```python
respuesta = input("  ¿Viste parpadear el LED 5 veces? (s/n): ")
ok = respuesta.strip().lower().startswith("s")

if not ok:
    print("  FALLA: revisar polaridad del LED, resistencia de 330 ohm,")
    print("  el cable al GPIO{}, y que su retorno llegue realmente".format(...))
return ok
```

El mismo patrón se aplicó a `prueba_led_pwm()`. El resultado del test ahora
coincide con lo que el docstring siempre dijo que debía ser: el "OK" es una
afirmación verificada por un humano, no una suposición del código.

### Verificación

Se re-ejecutó `prueba_perifericos.py` completo en ambos nodos (maestro y
esclavo). Las pruebas de LED pasaron a requerir la tecla `s`/`n` antes de
continuar, sin afectar el resto del flujo del script.

---

## 2. Atenuación del ADC no aplicada — potenciómetro con rango comprimido

### Contexto y síntoma

Durante la Fase 1, `prueba_perifericos.py` reportó:

```
RESUMEN
==========================================================
  [OK   ] LED digital
  [OK   ] LED PWM
  [FALLA] Switch
  [FALLA] Potenciometro
  [OK   ] Selector
```

### Hipótesis descartadas

1. **Cableado del potenciómetro o del switch.** Se pidió ejecutar directamente
   en el REPL, sin pasar por las clases del proyecto:

   ```python
   from machine import Pin
   p = Pin(18, Pin.IN, Pin.PULL_UP)
   p.value()          # switch: alternaba correctamente entre 0 y 1

   from machine import ADC, Pin
   a = ADC(Pin(34))
   a.atten(ADC.ATTN_11DB)
   a.read()            # potenciometro: recorria ampliamente 0-4095
   ```

   Ambas pruebas crudas funcionaron perfectamente. **Esto descartó el hardware
   por completo**: los pines físicos, las resistencias del divisor de tensión
   del potenciómetro y el pulsador estaban bien conectados. El defecto tenía
   que estar en la capa de software del proyecto (`perifericos.py`), no en el
   circuito.

2. **Riel de GND partido o sin puentear** (hipótesis descartada antes de la
   prueba anterior, mencionada por completitud del proceso de descarte): se
   consideró porque switch y potenciómetro son las dos únicas pruebas de
   *entrada* del script, mientras que las de LED son de salida y podrían
   "pasar" sin verificar realmente el retorno a masa (ver problema §1). Se
   descartó en cuanto la prueba cruda del switch confirmó una GND funcional.

### Diagnóstico confirmado

El defecto estaba específicamente en `EntradaAnalogica.__init__()` de
`perifericos.py`. La versión original:

```python
self._adc = ADC(Pin(numero_pin))
try:
    self._adc.atten(ADC.ATTN_11DB)
    self._adc.width(ADC.WIDTH_12BIT)
except AttributeError:
    pass
```

Se verificó contra el código fuente de MicroPython
(`extmod/machine_adc.c`, tabla `machine_adc_locals_dict_table`) que los métodos
`.atten()` y `.width()` están marcados explícitamente como **"Legacy methods"**
y se compilan condicionados al flag `MICROPY_PY_MACHINE_ADC_ATTEN_WIDTH`. Los
builds oficiales recientes de MicroPython para ESP32 **traen ese flag
desactivado**: en ese firmware, `.atten()` directamente no existe como método
del objeto `ADC`, y la llamada lanza `AttributeError`.

Como el código atrapaba ese `AttributeError` con un `except ... pass`
silencioso, el ADC quedaba configurado con la atenuación **por defecto (0 dB)**,
cuyo rango útil de entrada es de solo **0 a 1,1 V** — muy por debajo del rango
real del potenciómetro (0 a 3,3 V). Esto es exactamente lo que el propio
docstring de la clase ya advertía, sin que el código lo evitara:

```
Con la atenuacion por defecto (0 dB) el rango util seria de solo
0 a 1,1 V y el valor saturaria apenas se pasa un tercio del recorrido.
```

Con 0 dB, al girar el potenciómetro más allá de aproximadamente un tercio de su
recorrido, la lectura del ADC deja de ser lineal y puede saturar o comportarse
de forma no monótona (comportamiento documentado del ADC del ESP32 fuera de su
rango de atenuación configurado), lo que hace que el recorrido efectivo medido
por la prueba (`prueba_perifericos.py` exige ≥ 80 % del rango 0-4095) nunca
llegue al umbral — de ahí la `FALLA` reportada pese a que el hardware físico
estaba intacto.

### Por qué la prueba manual en el REPL sí funcionó

La prueba cruda ejecutada durante el descarte de hipótesis incluía
explícitamente `a.atten(ADC.ATTN_11DB)` **antes de leer**. En el firmware
específico de esta placa esa llamada síncrona no lanzó excepción en el momento
de la prueba manual con el orden de llamadas usado ahí — lo cual, sumado a que
la clase del proyecto SÍ dependía exclusivamente del bloque `try/except`
silencioso para aplicar la atenuación, confirma que el problema estaba
acotado al mecanismo de configuración de la clase, no al hardware ni al ADC en
sí.

### Solución aplicada

Se reescribió el constructor para usar la **API vigente**: pasar la atenuación
como argumento del **constructor** (`atten=`), que es la única vía garantizada
en los builds oficiales recientes, con una rama de compatibilidad hacia atrás
para firmware antiguo que todavía no acepta ese argumento:

```python
try:
    self._adc = ADC(Pin(numero_pin), atten=ADC.ATTN_11DB)
except TypeError:
    # Firmware anterior a la introduccion de atten= en el constructor:
    # crear el objeto sin ese argumento y recurrir a los metodos legacy,
    # que en un firmware de esa antiguedad si estan disponibles.
    self._adc = ADC(Pin(numero_pin))
    try:
        self._adc.atten(ADC.ATTN_11DB)
        self._adc.width(ADC.WIDTH_12BIT)
    except AttributeError:
        pass
```

Se invierte la prioridad: se intenta primero el método moderno (constructor),
y solo si falla con `TypeError` (argumento de palabra clave no reconocido, lo
que indica un firmware realmente antiguo) se recurre al método legacy. Esto
hace que el mismo archivo funcione correctamente en ambas generaciones de
firmware, en lugar de depender silenciosamente de la que ya no es la vigente.

### Verificación

Se volvió a ejecutar `prueba_perifericos.py`: la prueba del potenciómetro pasó
a recorrer correctamente el rango completo (0 a 4095, > 80 % del recorrido)
tanto en el nodo maestro como en el esclavo.

---

## 3. Timeout de recepción insuficiente para un esclavo MicroPython

### Contexto y síntoma

Al poner en marcha el maestro de la Parte 2 por primera vez, la consola de
Thonny mostró:

```
[MAESTRO] Fallo 0x02 Read Discrete Inputs con Esclavo 1 (1 consecutivos): no data received from slave
[MAESTRO] Fallo 0x02 Read Discrete Inputs con Esclavo 1 (2 consecutivos): no data received from slave
...
```

repitiéndose en el 100 % de los intentos, mientras que el mismo Esclavo 1 había
respondido correctamente durante toda la Parte 1 a las consultas manuales desde
QModMaster.

### Diagnóstico

`no data received from slave` es la excepción que `umodbus` lanza cuando su
función interna `_uart_read_frame()` agota su tiempo de espera sin haber
detectado ni un solo byte en el UART. Se calculó ese tiempo de espera por
defecto a partir del código fuente de la librería:

```
t1char              = 1000000 x (8 datos + 1 parada + 2) / 9600  =  1145 us
inter_frame_delay   = t1char x 3,5                                =  4007 us
timeout por defecto = 2 x inter_frame_delay                       =  8014 us   (8,0 ms)
```

Y se calculó, de forma independiente, el tiempo **mínimo físico** que un
esclavo puede tardar en responder, contando desde que el maestro termina de
transmitir:

| Etapa | Tiempo | Origen |
|---|---|---|
| Detección del fin de la petición (t3,5, obligatorio por especificación) | 4007 µs | El esclavo no puede empezar a procesar antes de esto |
| Procesamiento en el intérprete (estimación optimista) | ~1000 µs | Tiempo de MicroPython, no de hardware dedicado |
| Activación de DE en el transceptor | 200 µs | Retardo fijo del driver del proyecto |
| Transmisión de la respuesta (6 bytes × t1char) | 6870 µs | Física del bus a 9600 baudios |
| **Mínimo teórico absoluto** | **12 077 µs (12,1 ms)** | |

El presupuesto de la librería (8,0 ms) es **menor** que el piso físico que
cualquier esclavo necesita (12,1 ms), incluso en el caso optimista. El maestro
abandonaba la espera de la respuesta antes de que el esclavo hubiera terminado
siquiera de procesar la petición, y mucho antes de que pudiera empezar a
transmitir.

### Por qué la Parte 1 no mostró este problema

QModMaster (el maestro utilizado en la Parte 1) usa un timeout configurable de
1000 ms por defecto, muy por encima del piso físico de 12,1 ms. El problema es
específico de reemplazar el maestro por un segundo ESP32 corriendo la misma
librería con su timeout por defecto, que fue diseñado asumiendo un esclavo
mucho más rápido (típicamente un dispositivo con stack de comunicación en
hardware o firmware compilado, no un intérprete).

### Alternativa descartada

Se consideró aumentar directamente el atributo `_inter_frame_delay` de la
librería (que ya interviene en el cálculo del timeout por defecto), pero se
descartó: ese atributo cumple **dos** funciones a la vez — define el timeout
(×2) y también el silencio necesario para dar por completa una trama ya en
curso. Subirlo a, por ejemplo, 150 ms resolvería el timeout, pero agregaría
150 ms de espera **a cada una de las cuatro transacciones del ciclo**, llevando
el ciclo de ~102 ms a más de 600 ms — muy por encima del período de sondeo de
200 ms, rompiendo por completo el presupuesto temporal del sistema.

### Solución aplicada

Se creó una subclase de `umodbus.serial.Serial` (`MaestroRTUConTimeout` en
`firmware/maestro/main.py`) que sobrescribe únicamente `_uart_read_frame()`
para imponer un **piso** de timeout, sin tocar `_inter_frame_delay`:

```python
def _uart_read_frame(self, timeout=None):
    timeout_minimo_us = config.TIMEOUT_RESPUESTA_MS * 1000  # 300 ms
    if timeout is None or timeout < timeout_minimo_us:
        timeout = timeout_minimo_us
    ...
    return super()._uart_read_frame(timeout)
```

Se eligió un piso (no un reemplazo incondicional) para que un timeout explícito
mayor, si una versión futura de la librería lo pasara, siga respetándose. El
valor elegido (300 ms, ya presente en `config.TIMEOUT_RESPUESTA_MS`) deja un
margen de **24,8×** sobre el mínimo físico de 12,1 ms, sin afectar la
delimitación de tramas (que sigue gobernada por los 4007 µs de
`_inter_frame_delay`, tal como exige la especificación).

### Verificación

Tras la corrección, el error `no data received from slave` dejó de aparecer en
el arranque; se pasó a observar un problema distinto y más específico (§4), lo
que en sí mismo confirmó que el timeout ya no era la causa limitante.

---

## 4. RO en alta impedancia genera bytes espurios — la causa raíz de los "invalid response CRC"

Este fue el problema más costoso de diagnosticar del proyecto, y el que más
vueltas de hipótesis-experimento-descarte llevó. Se documenta con el proceso
completo porque el camino recorrido es en sí mismo evidencia de método.

### Contexto y síntoma inicial

Resuelto el problema de timeout (§3), la consola pasó a mostrar, de forma
consistente:

```
[MAESTRO] Fallo 0x02 Read Discrete Inputs con Esclavo 1 (1 consecutivos): invalid response CRC
[MAESTRO] Fallo 0x02 Read Discrete Inputs con Esclavo 1 (2 consecutivos): invalid response CRC
...
[MAESTRO] Fallo 0x02 Read Discrete Inputs con Esclavo 1 (196 consecutivos): invalid response CRC
```

En el 100 % de los intentos, de forma indefinida.

### Hipótesis 1 (descartada): glitch de conmutación DE/RE

**Razonamiento.** Se capturó el tráfico del bus con un analizador pasivo
(`herramientas/sniffer_rs485.py`, construido para este propósito) conectado al
conversor USB-RS485 como tercer nodo, sin transmitir. El resultado:

```
Tramas detectadas: 46
Tramas con CRC invalido: 1 (2.17 %)

Por codigo de funcion:
  0x02  Read Discrete Inputs         45 tramas
  0x4A  desconocida                  1 tramas
```

Un observador externo, que nunca transmite ni conmuta su propio transceptor,
veía el bus **limpio** (45 de 46 tramas válidas), mientras el maestro fallaba
el 100 % de sus propias lecturas. Esa divergencia llevó a la primera hipótesis:
un ruido de conmutación momentáneo, generado únicamente por el propio maestro
al pasar de transmisión a recepción, que el maestro captura como "primer byte
de respuesta" y que dispara prematuramente su lógica de fin de trama (basada en
4007 µs de silencio) mucho antes de que la respuesta real —que tarda ~12 ms en
llegar— siquiera empiece a transmitirse.

**Corrección aplicada bajo esta hipótesis.** Se agregó a
`MaestroRTUConTimeout._uart_read_frame()` una espera fija de 2000 µs tras cada
transmisión, seguida de un descarte explícito (`self._uart.read()`) de
cualquier byte acumulado en ese margen, antes de delegar a la lectura real.

**Resultado de la prueba.** El error **persistió sin cambios**. Más
concluyente todavía: **el mismo error apareció incluso con el firmware del
esclavo completamente detenido** (interrumpido en el REPL, sin `main.py`
corriendo). Esto es la prueba decisiva de que la hipótesis 1 era incorrecta: si
no hay absolutamente nadie del otro lado del bus, no puede haber una
"respuesta" que interpretar mal — y sin embargo el maestro seguía reportando
`invalid response CRC`, no un timeout. La única fuente posible de esos bytes
era **el propio maestro escuchándose a sí mismo**.

### Hipótesis 2 (descartada): puente RE↔DE sin continuidad

Se sospechó que el puente entre los pines RE y DE del módulo MAX485 del
maestro no estuviera haciendo contacto, dejando RE flotante y el receptor
permanentemente habilitado (lo que también explicaría una autoescucha). Como
el grupo no dispone de multímetro, se diseñó una prueba alternativa por
software: forzar una transmisión conocida (`AA 55 AA 55`) y leer de vuelta el
UART.

**Resultado de la prueba:**

```
b'\x00\x00\x00\x00'
```

Se recibieron **4 bytes**, la misma cantidad que se transmitió, pero con
contenido completamente distinto (`0x00` en vez de `0xAA`/`0x55`). Este dato
descartó también la hipótesis 2: un RE flotante que produjera autoescucha real
debería devolver el mismo contenido transmitido (o una versión con bits
alterados de forma más errática), no un patrón tan limpio y constante de ceros.
Un patrón de ceros perfectamente uniforme, del mismo largo que la transmisión,
apuntaba a algo más sistemático relacionado con el propio período de
transmisión, no con un eco del contenido.

### Diagnóstico confirmado

El dato de los `0x00` señaló directamente al comportamiento documentado del
MAX485 en su datasheet:

> *"RO is high impedance when RE is high."*

Como el diseño del proyecto ata **RE y DE al mismo GPIO** (para que un único
pin controle de forma coherente ambas mitades del transceptor y sea imposible
dejarlo transmitiendo y escuchando a la vez), esto tiene una consecuencia no
prevista: **mientras el nodo transmite (DE = RE = 1), su propio RO queda en
alta impedancia**, es decir, no conduce nada.

El divisor resistivo instalado entre RO y el GPIO de recepción (2,2 kΩ en serie
y 3,3 kΩ a GND, dimensionado para adaptar los ~5 V de RO a los 3,3 V del ESP32)
se convierte, en ese instante, en un problema:

```
   RO (Hi-Z, sin conducir)  ──[2,2 kΩ]──┬──[3,3 kΩ]── GND
                                        │
                                     GPIO16
```

Sin nada que sostenga RO en alto, la resistencia de 3,3 kΩ tira el nodo del
GPIO **a masa**. Para un UART, la línea RX en bajo es un bit de arranque; si se
sostiene en bajo, genera **bytes `0x00` de forma continua** durante toda la
duración de la transmisión — exactamente el patrón observado.

Esto explica, de una sola causa, **todas** las observaciones registradas:

| Observación | Explicación |
|---|---|
| Maestro falla el 100 % de las veces, con o sin esclavo | Se escucha transmitir sus propios `0x00`, generados localmente, sin depender de nada externo |
| Prueba de UART: `b'\x00\x00\x00\x00'` | Coincide exactamente con el mecanismo: 4 bytes de duración similar a la ventana de transmisión de la prueba |
| Sniffer externo ve el bus limpio | El sniffer nunca transmite ni conmuta su propio transceptor: es inmune a este efecto, que es local a cada nodo transmisor |
| En el esclavo, 0x02 funciona pero 0x04 falla (observado más adelante, ver nota) | Los `0x00` residuales de la propia transmisión del esclavo se concatenan con la siguiente petición si esta llega dentro de los 4 ms de silencio permitido, corrompiendo el CRC de la trama unida — pero solo cuando dos peticiones llegan muy seguidas, lo que depende del orden dentro del ciclo del maestro |

> **Nota:** este mismo defecto existía también en el esclavo desde la Parte 1,
> pero no se había manifestado como error explícito allí porque los fragmentos
> de `0x00` (menos de 8 bytes) eran descartados en silencio por la librería
> (`if len(req) < 8: return None`), sin lanzar ninguna excepción visible.

### Por qué los tutoriales genéricos de MAX485 + ESP32 no mencionan esto

La mayoría de los ejemplos publicados conectan RO **directamente** al GPIO,
sin divisor resistivo (una práctica fuera de especificación, dado que RO puede
entregar hasta ~5 V contra un máximo absoluto de 3,6 V del GPIO del ESP32, ver
`docs/arquitectura.md` §4). En ese esquema, **el pull-up interno del ESP32**
sostiene la línea en alto cuando RO queda flotando, y el problema nunca se
manifiesta. El divisor resistivo de este proyecto, necesario para proteger el
pin, elimina esa protección incidental sin que nada la reemplace — de ahí que
el defecto sea propio de este diseño y no algo documentado en fuentes
genéricas.

### Solución aplicada

Se agregó una resistencia de **pull-up de 680 Ω desde RO hacia 5 V**, en las
tres placas del proyecto (maestro y ambos esclavos, dado que las tres
transmiten):

```
                     5 V
                      │
                   [ 680 Ω ]
                      │
   MAX485 RO ─────────┴──[2,2 kΩ]──┬──[3,3 kΩ]── GND
                                   │
                                GPIO16
```

**Justificación del valor.** El pull-up debe sostener el nodo del divisor por
encima del umbral de entrada alta del ESP32 (0,75 × 3,3 V = 2,47 V) cuando RO
está en alta impedancia, sin comprometer los otros dos estados de RO:

| Pull-up | V en el nodo con RO en Hi-Z | Corriente con RO en bajo | Veredicto |
|---|---|---|---|
| 470 Ω | 2,76 V | 9,8 mA | Sirve |
| **680 Ω** | **2,67 V** | **6,8 mA** | **Elegido** |
| 1 kΩ | 2,54 V | 4,6 mA | Margen ajustado |
| 1,5 kΩ | 2,36 V | — | Insuficiente (< 2,47 V) |

Con 680 Ω, los otros dos estados de RO se verifican correctos: RO conduciendo
en bajo deja el nodo en 0,24 V (BAJO); RO conduciendo en alto lo deja en
2,70 V (ALTO). El pull-up no interfiere con la operación normal del divisor,
solo resuelve el estado Hi-Z que antes quedaba sin definir.

### Verificación

1. Con el pull-up instalado, se repitió la prueba de UART: la respuesta pasó
   de `b'\x00\x00\x00\x00'` a `None` (nada recibido, como corresponde a un
   canal en reposo sin transmisión real).
2. Se corrigió inicialmente solo el maestro y se corrió el sistema completo:
   apareció un segundo síntoma relacionado (0x02 funcionaba, 0x04 fallaba con
   timeout), que el análisis de la Nota anterior explicó como el mismo defecto
   pendiente de corregir en el esclavo.
3. Se agregó el pull-up también en el esclavo. Resultado, sostenido durante
   750 ciclos consecutivos de sondeo:

   ```
   [MAESTRO] ciclos=750 fallos=0 (0.0%) t_ciclo=161ms | ID=1 DI=0 IR=0 -> PWM=0
   ```

   0 % de fallos, con los cuatro caminos de datos (switch↔LED digital y
   potenciómetro↔LED PWM, en ambos sentidos) verificados funcionando en vivo.

### Corrección adicional de documentación

Se actualizaron todos los documentos del proyecto que mostraban el divisor sin
el pull-up (`docs/arquitectura.md` §4.3.1, `PARTE-1.md` §5.3, `PARTE-2.md`
§6.4) y las tres listas de materiales, para que el error no se repita al armar
el tercer nodo (Esclavo 2, Parte 3).

---

## 5. Hallazgo: diferencia entre el tiempo de ciclo teórico y el medido

No es un problema que haya bloqueado el avance —el sistema funciona
correctamente—, pero es un dato de ingeniería real obtenido por medición, que
vale la pena dejar registrado junto a los problemas anteriores.

### Contexto

El período de sondeo del maestro (`config.PERIODO_SONDEO_MS = 200`) se había
calculado en la Fase 0, antes de tener hardware, sumando el tiempo de
transmisión de los 61 bytes de las cuatro transacciones del ciclo más los 8
silencios de t3,5 correspondientes, dando una duración útil teórica de
**102 ms** (más 8 ms adicionales tras la corrección de §4, si se instrumentara
una espera equivalente — el valor de referencia usado para la comparación es
110 ms, sumando esa corrección).

### Medición real

Con la instrumentación agregada al maestro (contador de ciclos, fallos y
duración por ciclo), se midió en banco, de forma estable a lo largo de 750
ciclos:

```
t_ciclo = 161 ms
```

### Análisis de la diferencia

| Concepto | Tiempo | Origen |
|---|---|---|
| Transmisión de 61 bytes a 9600 baudios | 69,9 ms | Calculado, Fase 0 |
| 8 silencios de t3,5 | 32,1 ms | Calculado, Fase 0 |
| **Predicción** | **~110 ms** | |
| **Medido** | **161 ms** | Instrumentación del maestro |
| **Diferencia no modelada** | **~51 ms (+46 %)** | ~12,8 ms por transacción |

El modelo original solo contabilizaba el tiempo que los bits ocupan
físicamente el cable — un componente determinista que depende únicamente del
baudrate. No contabilizaba el **costo de cómputo** de ejecutar el protocolo
sobre un intérprete: el cálculo del CRC-16 en Python puro (sin tabla de
consulta, son 8 iteraciones de bucle por byte, ejecutado varias veces por
transacción entre emisor y receptor), el resto del lazo del esclavo entre
peticiones (incluidas 8 lecturas de ADC para el promediado), y el despacho de
la máquina de estados del maestro.

### Conclusión

El modelo teórico predijo correctamente el **componente físico** del tiempo de
ciclo y subestimó el **componente de cómputo**, que depende de la plataforma de
ejecución elegida (MicroPython interpretado) y no del protocolo en sí. La
diferencia no invalida el diseño: con 161 ms de ocupación sobre un período de
200 ms, el sistema opera al 80,5 % de ocupación del bus (contra el 51 %
previsto), y sostiene una tasa de error del 0,0 % sobre cientos de ciclos, lo
que confirma que el margen restante es suficiente. Se documenta como ejemplo de
que un cálculo teórico de Fase 0 debe contrastarse con medición real antes de
darse por válido — que es precisamente el objetivo de haber instrumentado el
sistema.

---

## Resumen ejecutivo

| # | Problema | Capa afectada | Tiempo de diagnóstico | Causa raíz |
|---|---|---|---|---|
| 1 | Prueba de LED sin verificación | Herramienta de testing | Bajo | Inconsistencia entre docstring y código |
| 2 | Potenciómetro con rango comprimido | Software (driver de ADC) | Medio | API legacy de MicroPython deshabilitada en firmware reciente |
| 3 | Timeout insuficiente del maestro | Software (parámetro de librería) | Medio | Timeout por defecto de la librería menor al piso físico de respuesta |
| 4 | `invalid response CRC` persistente | Hardware (diseño del divisor) | Alto | RO en alta impedancia durante transmisión, sin pull-up, genera bytes `0x00` |
| 5 | t_ciclo medido > teórico | Medición / modelado | — (no es un fallo) | Costo de cómputo del intérprete no incluido en el modelo de Fase 0 |

El problema 4 es el que más tiempo insumió porque las dos primeras hipótesis
(glitch de conmutación, puente RE↔DE) eran técnicamente plausibles y
consistentes con parte de la evidencia disponible en su momento; cada una se
descartó únicamente después de una prueba diseñada para falsificarla — la
prueba con el esclavo detenido y la prueba directa de eco por UART— y no por
intuición. Ese proceso de descarte metódico, más que la solución final en sí,
es el argumento más sólido de que el trabajo de banco fue real.
