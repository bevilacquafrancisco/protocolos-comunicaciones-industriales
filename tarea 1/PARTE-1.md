# PARTE 1 — Implementación del Esclavo MODBus RTU y validación desde PC

**Tarea Nº1** · Protocolos de Comunicaciones Industriales · UNRaf

Guía de ejecución de banco: qué construir, en qué orden, qué medir y cómo
interpretar lo que se ve. Es el documento operativo; la fundamentación teórica
está en [docs/arquitectura.md](docs/arquitectura.md),
[docs/protocolo-comunicacion.md](docs/protocolo-comunicacion.md) y
[docs/mapa-registros.md](docs/mapa-registros.md).

---

## Índice

1. [Objetivo y criterio de terminado](#1-objetivo-y-criterio-de-terminado)
2. [Supuestos e inventario](#2-supuestos-e-inventario)
3. [Decisiones de banco propias de la Parte 1](#3-decisiones-de-banco-propias-de-la-parte-1)
4. [Lista de materiales](#4-lista-de-materiales)
5. [Conexiones de hardware](#5-conexiones-de-hardware)
6. [Archivos involucrados](#6-archivos-involucrados)
7. [Paso a paso de resolución](#7-paso-a-paso-de-resolución)
8. [Software maestro en la PC](#8-software-maestro-en-la-pc)
9. [Cómo obtener e interpretar los datos](#9-cómo-obtener-e-interpretar-los-datos)
10. [Checklist de validación](#10-checklist-de-validación)
11. [Evidencia a capturar para el informe](#11-evidencia-a-capturar-para-el-informe)
12. [Diagnóstico de fallas](#12-diagnóstico-de-fallas)
13. [Pregunta de análisis de la Parte 1](#13-pregunta-de-análisis-de-la-parte-1)

---

## 1. Objetivo y criterio de terminado

La consigna pide tres cosas:

| # | Consigna | Cómo se cumple acá |
|---|---|---|
| 1 | Esclavo MODBus RTU con ID fijo = 1 sobre ESP32 + MAX485 | [firmware/esclavo/main.py](firmware/esclavo/main.py), Unit ID por jumper (§5.6) |
| 2 | Cuatro periféricos mapeados a direcciones fijas | §5 y [docs/mapa-registros.md](docs/mapa-registros.md) |
| 3 | Validación desde PC con conversor USB-RS485 y Modbus Poll | §8, §9 y §10 |

**Definition of Done de la Parte 1** — no se pasa a la Parte 2 sin esto:

- [ ] Las 16 pruebas del checklist de §10 pasan y están anotadas.
- [ ] Hay capturas de pantalla de la lectura y la escritura de las 4 direcciones.
- [ ] Hay al menos una trama real capturada y decodificada byte a byte.
- [ ] Está medida y anotada la tensión del divisor RO→RX.
- [ ] Está redactada la respuesta a la pregunta de análisis (§13).

## 2. Supuestos e inventario

### SUPUESTOS

> **S1 — Transceptores.** La lista de hardware que pasaste no menciona el
> **módulo MAX485** ni el **conversor USB-RS485**, pero al inicio del proyecto
> confirmaste tener 3 y 1 respectivamente. Esta guía asume que están
> disponibles. **Sin ellos la Parte 1 no puede completarse**, porque la consigna
> exige validar desde la PC a través de un conversor USB-RS485. Si no están a
> mano, los pasos 0 a 3 (hardware local) igual se pueden hacer con
> `prueba_perifericos.py`, y la parte de bus queda pendiente.
>
> **S2 — Alimentación.** Todo se alimenta desde el USB de la PC. Consumo total
> estimado: ESP32 ≈ 60 mA + MAX485 ≈ 1 mA + LEDs ≈ 8 mA. Sin problemas para un
> puerto USB.
>
> **S3 — Longitud del bus.** Menos de 1 metro de cable dupont entre el ESP32 y
> el conversor USB-RS485. Esto determina las decisiones de §3.

### Inventario declarado y suficiencia

| Componente | Disponible | Necesario Parte 1 | ¿Alcanza? |
|---|---|---|---|
| ESP32 | 3 | 1 | ✅ |
| Módulo MAX485 | 3 *(supuesto S1)* | 1 | ✅ |
| Conversor USB-RS485 | 1 *(supuesto S1)* | 1 | ✅ |
| Botones (pulsadores) | varios | 1 | ✅ |
| LEDs | varios | 2 | ✅ |
| Potenciómetros | 2 (2,2 kΩ y 10 kΩ) | 1 | ✅ |
| Resistencias | varias | ver §4 | ⚠️ verificar valores |
| Cables dupont | sí | ~15 | ✅ |

### ⚠️ Faltantes para las Partes 2 y 3 (no bloquean la Parte 1)

| Componente | Tenés | Necesitás | Falta |
|---|---|---|---|
| Potenciómetros | 2 | 3 (maestro + 2 esclavos) | **1** |
| Botones | varios | 5 (1 switch × 3 nodos + selector + jumper ID) | verificar |
| Par trenzado | no | recomendable para el bus de 3 nodos | — |

Conviene conseguir el tercer potenciómetro antes de la Parte 3. Cualquier valor
entre 1 kΩ y 10 kΩ sirve.

## 3. Decisiones de banco propias de la Parte 1

Esta sección documenta **tres puntos donde la Parte 1 se aparta a propósito de lo
prescrito en [docs/arquitectura.md](docs/arquitectura.md)**, y por qué. Cada
desvío tiene justificación numérica; no son atajos.

### 3.1 Sin resistencias de terminación

`arquitectura.md` §5 establece 120 Ω en los dos extremos del bus. **En la Parte 1
no se instalan.** Fundamento:

El criterio para decidir si una línea necesita terminación compara el tiempo de
ida y vuelta de la señal con el tiempo de subida del driver:

```
Terminar si:   2 × L / v  >  t_subida

t_subida (tR) del MAX485 = 15 ns típico          ← datasheet MAX481/MAX485
v ≈ 0,66 c ≈ 2 × 10⁸ m/s                          (≈ 5 ns por metro)

Longitud crítica:  L_c = tR × v / 2 = 15 ns × 2×10⁸ / 2 = 1,5 m
Longitud real del bus de la Parte 1:              ≈ 0,3 a 0,6 m
```

Con 2 nodos y menos de 60 cm de cable, **el bus es eléctricamente corto**: la
onda reflejada vuelve antes de que el flanco haya terminado de formarse, se funde
con él y no produce oscilación separada. Terminar no aporta nada.

> **Y además haría daño.** Instalar 120 Ω en ambos extremos **sin** la red de
> polarización deja A y B unidas por 60 Ω. En reposo la tensión diferencial cae a
> ≈0 V, dentro de la zona indeterminada de ±200 mV del receptor, y el UART se
> llena de bytes espurios. Terminación y polarización van juntas o no van
> ninguna de las dos.

**Cuándo revisar esta decisión:** en la Parte 3, con 3 nodos y un bus más largo,
volver a `arquitectura.md` §5 y §6 e instalar los 120 Ω **junto con** la
polarización de 680 Ω.

### 3.2 Sin red de polarización (se usa el fail-safe interno del MAX485)

Consecuencia directa de 3.1. El datasheet del MAX481/MAX485 dice:

> *"The receiver input has a fail-safe feature that guarantees a logic-high output
> if the input is open circuit."*

En `arquitectura.md` §6 se aclara que esa función **no** aplica con el bus
terminado, porque ahí la entrada no está abierta sino cargada por 60 Ω. **Sin
terminación, sí aplica**: las únicas cargas son las impedancias de entrada de los
dos receptores (RIN ≥ 12 kΩ cada uno). El fail-safe interno mantiene RO en alto
en reposo, que es el estado de marca que el UART espera.

**Plan B si aparecen bytes basura en reposo:** agregar una polarización *ligera*,
dimensionada para bus **sin terminar**:

```
   +5 V ── 10 kΩ ──── línea A
   GND  ── 10 kΩ ──── línea B

Carga diferencial = 12 kΩ ∥ 12 kΩ = 6 kΩ  (los dos receptores)
V_AB(reposo) = 5 × 6000 / (10000 + 6000 + 10000) = 1,15 V   ≫ 200 mV  ✔
Corriente = 5 / 26000 = 0,19 mA                              despreciable
```

> **No usar los 680 Ω de `arquitectura.md` acá.** Ese valor está calculado para
> un bus **terminado** (carga de 60 Ω). Sobre un bus sin terminar daría
> 5 × 6000/7360 = **4,1 V** de polarización de reposo: una carga innecesaria que
> el driver tiene que vencer en cada transición. El valor de una resistencia
> depende del resto del circuito, no del componente.

### 3.3 Cable dupont en lugar de par trenzado

Es la limitación más importante de este banco y hay que documentarla, no
disimularla.

| Lo que aporta el par trenzado | Qué pasa sin él |
|---|---|
| Rechazo de ruido de modo común: al trenzarse, el ruido se induce por igual en A y B y la resta A−B lo cancela | Se pierde ese rechazo. El ruido puede inducirse distinto en cada conductor y aparecer como señal |
| Impedancia característica controlada (≈120 Ω) | Z₀ queda indefinida (≈100-200 Ω según cómo queden los cables). Ninguna terminación sería exacta |
| Apantallado en cables industriales | Sin protección frente a fuentes de EMI cercanas |

**Por qué es aceptable en la Parte 1:** a 9600 baudios el tiempo de bit es de
104 µs. Una perturbación tendría que durar decenas de microsegundos y superar los
±200 mV diferenciales para corromper un bit. En un escritorio, sin motores ni
variadores cerca y con 40 cm de cable, eso no ocurre. **Y el CRC-16 detecta
cualquier trama que sí se corrompa**, así que el modo de falla es "trama
descartada y reintento", no "dato erróneo aceptado".

**Dos mitigaciones que cuestan cero:**

1. **Trenzar a mano los dos dupont de A y B.** Tomar los dos cables y retorcerlos
   entre sí, unas 3 a 5 vueltas por cada 10 cm. Recupera buena parte del efecto
   de cancelación. Es la mitigación de mejor relación costo-beneficio del banco.
2. **Cables lo más cortos posible** y alejados de la fuente del monitor, del
   cargador del celular y de cualquier motor.

Anotar esta limitación en el informe, en la sección de resultados: es
exactamente el tipo de observación que distingue un trabajo de banco real de uno
copiado.

### 3.4 Potenciómetro: se usa el de 10 kΩ

| Criterio | 10 kΩ (elegido) | 2,2 kΩ |
|---|---|---|
| Corriente que consume | 3,3 V / 10 kΩ = **0,33 mA** | 3,3 V / 2,2 kΩ = 1,5 mA |
| Impedancia de fuente vista por el ADC (peor caso, cursor al medio: R/4) | **2,5 kΩ** | 550 Ω |
| ¿Compatible con el ADC del ESP32? | Sí — 2,5 kΩ está dentro de lo que el ADC carga sin error apreciable | Sí, mejor aún |

Se elige el de **10 kΩ** porque consume 4,5 veces menos y su impedancia de fuente
sigue siendo perfectamente tolerable. El de 2,2 kΩ queda reservado para el nodo
maestro de la Parte 2.

**Mejora opcional** (si tenés un capacitor de 100 nF): entre GPIO34 y GND, forma
un filtro pasa bajos con la impedancia del cursor:

```
f_corte = 1 / (2π × 2500 Ω × 100 nF) = 637 Hz
```

Sobra para un potenciómetro que se gira a mano y suprime ruido de alta
frecuencia. **No es necesario**: el promediado de 8 muestras por software
(`config.MUESTRAS_ADC`) ya resuelve el problema.

## 4. Lista de materiales

| Componente | Cantidad | Valor | Función |
|---|---|---|---|
| ESP32 DevKit | 1 | — | Nodo esclavo |
| Módulo MAX485 | 1 | — | Transceptor TTL↔RS-485 |
| Conversor USB-RS485 | 1 | — | Maestro en la PC |
| Potenciómetro | 1 | **10 kΩ** | Entrada analógica → IR 30001 |
| Pulsador | 1 | — | Entrada digital → DI 10001 |
| LED | 2 | — | Coil 00001 y HR 40001 |
| Resistencia | 2 | **330 Ω** (ver tabla) | Limitadora de los LEDs |
| Resistencia | 1 | **2,2 kΩ** (ver tabla) | R1 del divisor RO→RX |
| Resistencia | 1 | **3,3 kΩ** (ver tabla) | R2 del divisor RO→RX |
| Protoboard | 1 | — | Montaje |
| Cables dupont | ~15 | — | Interconexión |

### 4.1 Si no tenés exactamente 2,2 kΩ y 3,3 kΩ (divisor RO→RX)

Lo que importa es la **relación**, no los valores absolutos. Se necesita
`R2/(R1+R2) ≈ 0,60`, lo que da ≈3,15 V en el peor caso de VCC = 5,25 V.

| R1 (serie) | R2 (a GND) | V_RX @ 5,25 V | Corriente | ¿Sirve? |
|---|---|---|---|---|
| 1 kΩ | 1,5 kΩ | 3,15 V | 2,1 mA | ✅ |
| 1,5 kΩ | 2,2 kΩ | 3,12 V | 1,4 mA | ✅ |
| **2,2 kΩ** | **3,3 kΩ** | **3,15 V** | **0,95 mA** | ✅ **preferido** |
| 3,3 kΩ | 4,7 kΩ | 3,08 V | 0,66 mA | ✅ |
| 4,7 kΩ | 6,8 kΩ | 3,10 V | 0,46 mA | ✅ |
| 10 kΩ | 15 kΩ | 3,15 V | 0,21 mA | ✅ |
| 1 kΩ | 2 kΩ | 3,50 V | 1,8 mA | ⚠️ poco margen contra los 3,6 V |
| 2,2 kΩ | 4,7 kΩ | 3,58 V | 0,76 mA | ❌ demasiado cerca del máximo absoluto |
| 1 kΩ | 1 kΩ | 2,63 V | 2,6 mA | ⚠️ funciona, pero solo 0,15 V sobre VIH |

Todas las opciones marcadas ✅ tienen una constante de tiempo despreciable frente
al bit de 104 µs (la peor, 10 k/15 k, distorsiona un 0,63 %).

### 4.2 Si no tenés exactamente 330 Ω (LEDs)

| Valor | Corriente (LED rojo, Vf ≈ 2 V) | Observación |
|---|---|---|
| 220 Ω | 5,9 mA | Más brillante |
| **330 Ω** | **3,9 mA** | Preferido |
| 470 Ω | 2,8 mA | Bien visible |
| 1 kΩ | 1,3 mA | Tenue pero se ve; puede costar apreciar el PWM bajo |

Cualquiera entre 220 Ω y 1 kΩ funciona. **Nunca conectar un LED sin resistencia**:
el GPIO admite 40 mA y un LED directo pediría mucho más.

## 5. Conexiones de hardware

> ⚠️ **Armar todo con la alimentación desconectada.** Conectar el USB recién al
> terminar el paso 1 del §7.

### 5.1 Tabla completa de conexiones

| # | Desde | Hacia | Componente intermedio |
|---|---|---|---|
| 1 | ESP32 **GPIO17** | MAX485 **DI** | — (directo) |
| 2 | MAX485 **RO** | ESP32 **GPIO16** | **Divisor 2,2 k / 3,3 k** ⚠️ |
| 3 | ESP32 **GPIO4** | MAX485 **DE** *y* **RE** (unidos) | — (directo) |
| 4 | ESP32 **VIN (5 V)** | MAX485 **VCC** | — |
| 5 | ESP32 **GND** | MAX485 **GND** | — |
| 6 | MAX485 **A** | USB-RS485 **A** (o **D+**) | cable dupont trenzado a mano |
| 7 | MAX485 **B** | USB-RS485 **B** (o **D−**) | cable dupont trenzado a mano |
| 8 | ESP32 **GND** | USB-RS485 **GND** | ⚠️ **imprescindible** |
| 9 | ESP32 **GPIO18** | Pulsador → GND | — (pull-up interno) |
| 10 | ESP32 **3V3** | Potenciómetro extremo 1 | — |
| 11 | ESP32 **GND** | Potenciómetro extremo 2 | — |
| 12 | Potenciómetro **cursor** | ESP32 **GPIO34** | — |
| 13 | ESP32 **GPIO19** | LED 1 ánodo | 330 Ω hacia GND |
| 14 | ESP32 **GPIO21** | LED 2 ánodo | 330 Ω hacia GND |
| 15 | ESP32 **GPIO13** | *sin conectar* | fija Unit ID = 1 |

### 5.2 Interfaz ESP32 ↔ MAX485

**El único punto donde se puede romper la placa.** Tres de las cuatro líneas van
directas; solo RO necesita adaptación.

```
        ESP32                                    MAX485
  ┌───────────────┐                        ┌──────────────┐
  │               │                        │              │
  │  GPIO17 (TX)  ├───────────────────────►│ DI    (4)    │
  │               │        directo         │              │
  │               │                        │              │
  │  GPIO4        ├────────────┬──────────►│ DE    (3)    │        A (6) ──► al bus
  │               │  directo   └──────────►│ RE    (2)    │        B (7) ──► al bus
  │               │                        │              │
  │  GPIO16 (RX)  │◄────┬──────────────────┤ RO    (1)    │
  │               │     │      2,2 kΩ      │              │
  │               │  3,3 kΩ                │              │
  │               │     │                  │              │
  │      GND      ├─────┴──────────────────┤ GND   (5)    │
  │               │                        │              │
  │      VIN      ├───────────────────────►│ VCC   (8)    │
  └───────────────┘                        └──────────────┘
```

**Por qué DI, DE y RE van directos:** el MAX485 necesita **VIH ≥ 2,0 V** y el
ESP32 entrega 3,3 V. Margen de 1,3 V, de sobra. Agregar un level shifter acá es
un error común que solo suma un punto de falla.

**Por qué RO necesita divisor:** RO entrega **VOH ≥ 3,5 V** y en la práctica casi
VCC (≈5 V), contra un **máximo absoluto de 3,6 V** en el GPIO del ESP32.
Conectarlo directo hace conducir los diodos de protección del pin y degrada o
destruye el chip.

**Por qué DE y RE se unen:** RE es activo en bajo y DE en alto. Uniéndolos, un
solo GPIO controla las dos funciones de forma coherente y es imposible dejar el
nodo transmitiendo y escuchando a la vez. La librería `umodbus` conmuta ese pin
automáticamente (parámetro `ctrl_pin`).

### 5.3 Detalle del divisor en protoboard

```
   MAX485 RO ────[ 2,2 kΩ ]────┬──── ESP32 GPIO16
                               │
                          [ 3,3 kΩ ]
                               │
                              GND
```

El punto de unión de las dos resistencias es el que va al GPIO16. Es el nodo que
se mide en el paso 2 del §7.

### 5.4 Pulsador → Discrete Input 10001

```
   ESP32 GPIO18 ──────┬──────  pin 1 del pulsador
                      │
              (pull-up interno,
               activado por software)
                      
                pin 2 del pulsador ────── GND
```

**Lógica activa en bajo:** con el pull-up interno, el pin lee **1 en reposo** y
**0 al presionar**. La clase `EntradaDigital` invierte esa lectura, de modo que
el registro MODBus reporta `1 = presionado`, que es la convención natural.

> **Es un pulsador, no una llave con enclavamiento.** Para validar la lectura hay
> que **mantenerlo presionado** mientras Modbus Poll sondea. Es válido según la
> consigna, que admite "Switch / Botón": el Discrete Input refleja el estado
> instantáneo del contacto, que es exactamente lo que hace un sensor de campo.

No hace falta resistencia externa: el pull-up del ESP32 (≈45 kΩ) ya lo resuelve.

### 5.5 Potenciómetro → Input Register 30001

```
   ESP32 3V3 ──────── extremo 1
                          │
                        ┌─┴─┐
                        │   │◄──── cursor ──── ESP32 GPIO34
                        └─┬─┘
                          │
   ESP32 GND ──────── extremo 2
```

⚠️ **Alimentar con 3V3, nunca con 5 V ni con VIN.** El GPIO34 admite hasta 3,3 V;
con 5 V en el extremo del potenciómetro se dañaría la entrada.

GPIO34 es de **solo entrada** y pertenece al ADC1. Esa característica es una
ventaja: es imposible configurarlo como salida por error.

### 5.6 LEDs → Coil 00001 y Holding Register 40001

```
   ESP32 GPIO19 ────►│──── [ 330 Ω ] ──── GND      LED 1 · digital · Coil 00001
                    LED

   ESP32 GPIO21 ────►│──── [ 330 Ω ] ──── GND      LED 2 · PWM · HR 40001
                    LED
```

El triángulo apunta en el sentido de la corriente: **el ánodo (pata larga) va al
GPIO** y el cátodo (pata corta, lado achatado del encapsulado) al lado de la
resistencia. Si el LED no enciende nunca, invertirlo es lo primero a probar.

### 5.7 Jumper de Unit ID — no se conecta nada

`GPIO13` se lee al arrancar con pull-up interno:

| Estado de GPIO13 | Lectura | Unit ID |
|---|---|---|
| **Sin conectar (abierto)** | 1 | **1** ← lo que necesita la Parte 1 |
| Puenteado a GND | 0 | 2 |

**Para la Parte 1 no se conecta ningún componente a GPIO13.** El pull-up interno
lo deja en alto y el firmware asigna Unit ID = 1, que es lo que pide la consigna.

Es la implementación de la "dirección física fija": exactamente como las llaves
DIP de direccionamiento de un módulo de E/S remoto industrial.

### 5.8 Bus hacia el conversor USB-RS485

```
   MAX485 A ──────┐  (trenzar estos dos    ┌────── USB-RS485  A  (o D+, o "485+")
                  ├───  cables a mano)  ───┤
   MAX485 B ──────┘                        └────── USB-RS485  B  (o D−, o "485−")

   ESP32 GND ─────────────────────────────────────  USB-RS485 GND
```

Tres advertencias:

1. **La masa común no es opcional.** RS-485 es diferencial, pero el receptor solo
   tolera una tensión de modo común de −7 V a +12 V **respecto de su propia masa**.
   Sin referencia común esa condición no está garantizada. Es la causa número uno
   de fallas raras en RS-485.
2. **A con A, B con B.** Si están cruzadas, el receptor interpreta todos los bits
   invertidos y no responde nada. Los rótulos varían: algunos conversores dicen
   `D+`/`D−`, otros `485+`/`485−`, otros `A`/`B`. Si no funciona, **probar
   intercambiándolas**: no rompe nada y es la prueba más rápida.
3. **Sin terminación ni polarización** — ver §3.1 y §3.2. Si tu conversor
   USB-RS485 trae un jumper de terminación de 120 Ω, **dejarlo desactivado**.

## 6. Archivos involucrados

### 6.1 Se cargan en el ESP32 (a la raíz `/`, no en subcarpetas)

| Archivo de origen | Nombre en el ESP32 | Qué aporta |
|---|---|---|
| [firmware/comun/config.py](firmware/comun/config.py) | `config.py` | Pines, parámetros del bus, direcciones MODBus. **Única fuente de verdad** |
| [firmware/comun/perifericos.py](firmware/comun/perifericos.py) | `perifericos.py` | Capa de abstracción: antirrebote, promediado del ADC, conversión de PWM |
| [firmware/esclavo/main.py](firmware/esclavo/main.py) | `main.py` | Servidor MODBus RTU. Se ejecuta solo al arrancar |
| librería `umodbus` | `lib/umodbus/` | Stack MODBus (se instala con el gestor de paquetes de Thonny) |

### 6.2 Se ejecutan pero no se instalan

| Archivo | Dónde corre | Para qué |
|---|---|---|
| [firmware/prueba_perifericos.py](firmware/prueba_perifericos.py) | ESP32, con **F5** desde Thonny | Verifica el hardware local antes de meter MODBus en la ecuación |
| [herramientas/modbus_tramas.py](herramientas/modbus_tramas.py) | PC, Python 3 | Calcula CRC-16 y decodifica tramas capturadas |

### 6.3 Documentación de consulta

| Documento | Cuándo mirarlo |
|---|---|
| [firmware/README.md](firmware/README.md) | Instalación de Thonny, MicroPython y `umodbus`, paso a paso |
| [docs/arquitectura.md](docs/arquitectura.md) | Fundamentos eléctricos, criterios de selección de GPIO |
| [docs/protocolo-comunicacion.md](docs/protocolo-comunicacion.md) | Tramas, CRC, endianness, excepciones |
| [docs/mapa-registros.md](docs/mapa-registros.md) | Contrato de datos y checklist de validación |
| [diagramas/flujo_esclavo.md](diagramas/flujo_esclavo.md) | Lógica del firmware, bloque por bloque |
| [docs/modbusprotocolspecification.pdf](docs/modbusprotocolspecification.pdf) | Especificación oficial V1.1b3 — fuente para citar en APA |

### 6.4 Trazabilidad código ↔ diagrama de flujo

Requerimiento adicional 2 de la consigna. Cada función del firmware declara a qué
bloque del diagrama pertenece:

| Bloque | Función en `esclavo/main.py` | Qué hace |
|---|---|---|
| E1 | `configurar_perifericos()` · `configurar_servidor_modbus()` | Inicializa hardware y da de alta las 4 áreas |
| E2 | `leer_unit_id()` | Lee GPIO13 y fija la dirección física |
| E3 | `publicar_entradas()` | Vuelca switch y ADC a las áreas de solo lectura |
| E4 | `cliente.process()` | Escucha el bus y responde si la trama es para este ID |
| E5 | `aplicar_salidas()` | Vuelca Coil y HR a los LEDs |
| E6 | `main()` | Lazo infinito |

## 7. Paso a paso de resolución

Cada paso tiene un **criterio de aceptación**. No avanzar sin cumplirlo: saltear
uno convierte un problema simple en varios superpuestos.

### Paso 0 — Preparar el entorno (una vez)

1. Instalar [Thonny](https://thonny.org).
2. *Herramientas → Opciones → Intérprete* → **MicroPython (ESP32)** → puerto COM →
   **Instalar o actualizar MicroPython**.
3. *Herramientas → Administrar paquetes* → `micropython-modbus` → **Instalar**.

Detalle completo en [firmware/README.md](firmware/README.md).

> ✅ **Criterio:** en el Shell de Thonny, `from umodbus.serial import ModbusRTU`
> no da error.

### Paso 1 — Montar el hardware sin alimentar

Armar todo lo de §5 con el USB desconectado. Al terminar, verificar con
multímetro en modo continuidad:

- No hay continuidad entre **VIN y GND**, ni entre **3V3 y GND**.
- No hay continuidad entre **A y B**.
- Sí hay continuidad entre la GND del ESP32 y la del MAX485 y la del USB-RS485.

> ✅ **Criterio:** ningún cortocircuito. Recién ahora se puede alimentar.

### Paso 2 — Medir el divisor ⚠️ paso crítico

**Antes de conectar el cable del divisor al GPIO16**, dejarlo suelto y medir.

1. Conectar el USB del ESP32 (alimenta al MAX485 por VIN).
2. Medir primero **VIN contra GND**. Anotarlo.
3. Con el bus en reposo, RO queda en alto por el fail-safe interno. Medir el
   **punto medio del divisor** (la unión de las dos resistencias) contra GND.

| Medición | Valor esperado | Si no da eso |
|---|---|---|
| VIN | 4,6 a 5,1 V | Ver la nota de abajo |
| Punto medio del divisor | **2,6 a 3,4 V** | ❌ **No conectar al GPIO16** |
| Si midiera ≈ VIN (4,6-5 V) | — | El divisor está mal armado o una resistencia está suelta |

> **Nota sobre VIN.** En la mayoría de los DevKit, VIN llega desde el USB a
> través de un diodo, por lo que suele medir **4,6-4,8 V**, algo por debajo del
> mínimo de 4,75 V que especifica el MAX485. En la práctica funciona
> perfectamente a 9600 baudios con un bus corto, pero **hay que medirlo y
> anotarlo en el informe** — es una desviación real de la especificación, y
> reconocerla vale más que ignorarla. Si el punto medio del divisor queda por
> debajo de 2,6 V, alimentar el MAX485 con 5 V desde el conversor USB-RS485 o
> desde una fuente externa, siempre con GND común.

> ✅ **Criterio:** punto medio entre 2,6 V y 3,4 V. Recién entonces conectar ese
> nodo al GPIO16.

### Paso 3 — Verificar los periféricos locales sin MODBus

1. Cargar `config.py` y `perifericos.py` en el ESP32
   (*Archivo → Guardar como → Dispositivo MicroPython*).
2. Abrir [firmware/prueba_perifericos.py](firmware/prueba_perifericos.py) y
   pulsar **F5**. No hace falta guardarlo en la placa.
3. Seguir las 5 pruebas guiadas.

> ✅ **Criterio:** las 5 pruebas dan OK. En particular, el potenciómetro debe
> recorrer más del 80 % del rango del ADC.

### Paso 4 — Cargar el firmware del esclavo

1. Abrir [firmware/esclavo/main.py](firmware/esclavo/main.py) en Thonny.
2. *Archivo → Guardar como → Dispositivo MicroPython* → nombre exacto: **`main.py`**.
3. Reiniciar con **Ctrl+F2**.

Salida esperada en el Shell:

```
==========================================================
ESCLAVO MODBus RTU  |  Unit ID = 1
Bus: 9600 baudios, 8N1
UART2  TX=GPIO17  RX=GPIO16  DE/RE=GPIO4
Registros: DI 10001 | IR 30001 | Coil 00001 | HR 40001
==========================================================
```

> ✅ **Criterio:** dice **Unit ID = 1**. Si dijera 2, GPIO13 está tocando GND.

### Paso 5 — Conectar el conversor USB-RS485

1. Conectar el conversor USB-RS485 a la PC.
2. Anotar en qué COM aparece (Administrador de dispositivos → *Puertos*).

> 💡 **Dejá Thonny conectado al COM del ESP32.** Son **dos puertos distintos** —
> uno es el USB del ESP32 y el otro el del conversor— así que Thonny y
> QModMaster conviven sin conflicto. Mantener el Shell a la vista es la mejor
> herramienta de diagnóstico que tenés: si el firmware lanza una excepción
> atendiendo el bus, la vas a ver ahí en el momento. Lo único que no hay que
> hacer es pulsar **Ctrl+C**, que interrumpiría `main.py`.
>
> Solo hay conflicto si intentaras abrir el **mismo** COM desde dos programas.

> ✅ **Criterio:** dos puertos COM distintos, uno para el ESP32 y otro para el
> conversor. Anotar cuál es cuál.

### Paso 6 — Configurar el software maestro

Ver §8. Los parámetros deben coincidir **exactamente** con los del esclavo.

> ✅ **Criterio:** el software abre el puerto sin error.

### Paso 7 — Primera lectura

Leer el **Input Register 30001** (función 0x04, dirección 0, cantidad 1).

> ✅ **Criterio:** aparece un número que **cambia al girar el potenciómetro**.
> Si aparece un error, ir directo a §12.

### Paso 8 — Checklist completo y evidencia

Ejecutar las 16 pruebas de §10 y capturar la evidencia de §11.

> ✅ **Criterio:** el Definition of Done de §1 está completo.

## 8. Software maestro en la PC

### 8.1 Modbus Poll y alternativas libres

La consigna dice "Modbus Pull (o equivalente)", así que las alternativas están
explícitamente admitidas.

| Herramienta | Licencia | Costo | Observaciones |
|---|---|---|---|
| **Modbus Poll** | Comercial | **≈ US$ 135** licencia única · demo limitada a 10 min por sesión | Es el que nombra la consigna. La demo alcanza para las pruebas si se reinicia |
| **QModMaster** | GPL (libre) | **$0** | ⭐ **Recomendado.** GUI similar, basado en libmodbus, con ventana de tramas en crudo. Windows y Linux |
| **mbpoll** | Libre | **$0** | Línea de comandos. Ideal para automatizar pruebas y pegar la salida en el informe |
| **Radzio Modbus Master Simulator** | Freeware | **$0** | Muy simple, solo Windows |

**Recomendación:** usar **QModMaster** para todo el trabajo y, si querés cumplir
al pie de la letra con el enunciado, repetir una o dos pruebas con la demo de
Modbus Poll para la captura del informe. La demo de 10 minutos alcanza de sobra.

### 8.2 Parámetros de conexión (idénticos en cualquier herramienta)

| Parámetro | Valor | De dónde sale |
|---|---|---|
| Modo | **RTU** | Fijado por la consigna |
| Puerto serie | COM del **conversor USB-RS485** | Paso 5 |
| Baudrate | **9600** | `config.BAUDRATE` |
| Bits de datos | **8** | `config.BITS_DATOS` |
| Paridad | **None** | `config.PARIDAD` |
| Bits de parada | **1** | `config.BITS_PARADA` |
| Slave / Unit ID | **1** | `config.ID_ESCLAVO_1` |
| Timeout de respuesta | 1000 ms | Holgado para la primera puesta en marcha |
| Base de direccionamiento | **0** (ver §9.1) | Determina si se escribe `0` o `1` |

> **Un solo parámetro distinto y no funciona nada.** No hay degradación parcial:
> con el baudrate o la paridad mal, el esclavo recibe bits mal encuadrados, el
> CRC falla y descarta todo en silencio.

### 8.3 QModMaster paso a paso

QModMaster es **portable**: se descomprime el ZIP y se ejecuta `qmodmaster.exe`
directamente. No hay instalación ni configuración previa. Que se abra la interfaz
es todo lo que hace falta.

#### A. Configurar el puerto serie — antes de conectar

**`Options → Modbus RTU Settings`** (en algunas versiones, el ícono de llave
inglesa o `Settings` en la barra de herramientas):

| Campo | Valor |
|---|---|
| Serial Port | El COM del **conversor USB-RS485**, no el del ESP32 |
| Baud | **9600** |
| Data Bits | **8** |
| Stop Bits | **1** |
| Parity | **None** |
| RTS / DTR | Dejar en el valor por defecto |

> ⚠️ **El error más común es elegir el COM equivocado.** Con el ESP32 y el
> conversor enchufados hay dos puertos. Para saber cuál es cuál: desenchufar el
> conversor, mirar qué COM desaparece del Administrador de dispositivos, y
> volver a enchufarlo.

#### B. Configurar la base de direccionamiento

**`Options → Base Addr`** → elegir **0**.

Con base 0, el campo *Start Address* se escribe tal como viaja en la trama, que
es como está documentado el mapa de registros de este trabajo. Si tu versión no
tiene ese menú, probá primero con `0` y, si da excepción 02, usá `1`.

#### C. Configurar la petición en la ventana principal

| Campo | Valor para la primera prueba |
|---|---|
| Modbus Mode | **RTU** |
| Slave Addr | **1** |
| Scan Rate (ms) | 1000 |
| Function Code | **Read Input Registers (0x04)** |
| Start Address | **0** |
| Number of Registers | **1** |
| Data Format | Dec (decimal) |

#### D. Conectar y leer

1. **`Commands → Connect`** (o el ícono del enchufe). El estado abajo debe pasar
   a conectado.
2. **`Commands → Read/Write`** para una lectura única, o activar **`Scan`** para
   que sondee de forma continua al ritmo del *Scan Rate*.
3. Girar el potenciómetro: el número de la tabla debe cambiar.

#### E. Abrir el monitor de tramas — no es opcional

**`View → Bus Monitor`**. Es la única forma de saber qué está pasando de verdad.

| Qué muestra | Qué significa |
|---|---|
| Hay línea **Tx** y hay **Rx** | Todo bien |
| Hay **Tx** pero **no hay Rx** | La PC transmite y el esclavo no contesta → problema del lado del ESP32 o del cableado |
| **No hay ni Tx** | QModMaster no está enviando → no está conectado, o el Function Code es inválido |

#### F. Escribir en las salidas

Para mover los LEDs (ver §9.0: no responden al pulsador ni al potenciómetro
locales):

| Objetivo | Function Code | Start Address | Valor |
|---|---|---|---|
| LED 1 encendido | **Write Single Coil (0x05)** | 0 | 1 |
| LED 1 apagado | **Write Single Coil (0x05)** | 0 | 0 |
| LED 2 al máximo | **Write Single Register (0x06)** | 0 | 255 |
| LED 2 a medias | **Write Single Register (0x06)** | 0 | 128 |

Al elegir una función de escritura, la tabla de datos se vuelve editable: se
escribe el valor en la celda y se ejecuta con **`Commands → Read/Write`**.

> **Desactivar `Scan` antes de escribir.** Con el sondeo continuo activo, la
> escritura se repite una vez por segundo y cuesta interpretar el monitor.

#### G. Menús que NO sirven en este trabajo

**`Commands → Modbus Diagnostics`** y **`Report Slave ID`** usan las funciones
0x08 y 0x11, que este esclavo no implementa. **Siempre dan timeout** y no aportan
información de diagnóstico. Ver §12.8.

### 8.4 Equivalencia con `mbpoll` (línea de comandos)

Útil porque la salida se copia y pega directo al informe:

```bash
# Leer el Input Register 30001 (función 0x04)
mbpoll -m rtu -a 1 -b 9600 -P none -d 8 -s 1 -t 3 -r 1 -c 1 COM5

# Leer el Discrete Input 10001 (función 0x02)
mbpoll -m rtu -a 1 -b 9600 -P none -t 1 -r 1 -c 1 COM5

# Escribir el Coil 00001 en ON (función 0x05)
mbpoll -m rtu -a 1 -b 9600 -P none -t 0 -r 1 COM5 1

# Escribir 128 en el Holding Register 40001 (función 0x06)
mbpoll -m rtu -a 1 -b 9600 -P none -t 4 -r 1 COM5 128
```

`-t` selecciona el área: `0`=coil, `1`=discrete input, `3`=input register,
`4`=holding register. `mbpoll` usa base 1 por defecto, de ahí el `-r 1`.

## 9. Cómo obtener e interpretar los datos

### 9.0 ⚠️ Antes de nada: el esclavo NO acopla sus entradas con sus salidas

**El pulsador no enciende el LED 1, y el potenciómetro no regula el LED 2.** No
es una falla: es el diseño, y confundirlo cuesta horas de diagnóstico sobre un
sistema que ya funciona.

En el esclavo hay **cuatro variables independientes**, sin ninguna relación entre
ellas dentro del firmware:

```
   PULSADOR ──────► Discrete Input 10001 ──────► el maestro lo LEE
   POTENCIÓMETRO ─► Input Register 30001 ──────► el maestro lo LEE

   LED 1 ◄───────── Coil 00001 ◄─────────────── el maestro lo ESCRIBE
   LED 2 ◄───────── Holding Reg. 40001 ◄─────── el maestro lo ESCRIBE
```

No hay ninguna flecha que cruce de arriba abajo. `publicar_entradas()` solo
escribe en las áreas de **solo lectura**; `aplicar_salidas()` solo lee de las
áreas **escribibles**. Son dos caminos que nunca se tocan.

**El acoplamiento existe, pero vive en otro lado y llega en la Parte 2:** es el
*maestro* el que lee el switch remoto por el bus y replica su valor, y el que lee
su potenciómetro local y lo escribe en el registro del esclavo. Ese cruce ocurre
**a través del bus RS-485**, no dentro del esclavo.

| Etapa | Quién mueve los LEDs del esclavo |
|---|---|
| **Parte 1** | La **PC**, escribiendo a mano con las funciones 0x05 y 0x06 desde QModMaster |
| Partes 2 y 3 | El **maestro ESP32**, escribiendo automáticamente en cada ciclo de sondeo |

> **Por qué el diseño es así y no de otra forma:** un dispositivo de campo
> publica lo que mide y obedece lo que le ordenan. La lógica —qué hacer con esa
> medición— vive en el controlador, no en el sensor. Si el esclavo decidiera solo
> encender su LED al presionar el pulsador, el maestro perdería el control de esa
> salida y el requisito de retención de estado de la Parte 3 sería imposible de
> cumplir: habría dos escritores peleando por el mismo actuador.

**Entonces, para ver moverse los LEDs en la Parte 1 hay que ESCRIBIR desde
QModMaster** — ver §9.4 y §9.5.

### 9.1 Lo primero: base 0 o base 1

**Es el error más común de toda la integración MODBus.** La notación Modicon
(`10001`, `30001`, `00001`, `40001`) numera **desde 1**, pero en la trama la
dirección viaja como un offset **desde 0**.

```
40001 (Modicon)  →  se transmite como dirección 0x0000
30001 (Modicon)  →  se transmite como dirección 0x0000
10001 (Modicon)  →  se transmite como dirección 0x0000
00001 (Modicon)  →  se transmite como dirección 0x0000
```

Que las cuatro compartan el offset `0x0000` **no es una colisión**: cada área
tiene su propio espacio de direcciones, y es el **código de función** el que
determina en cuál se busca.

| Si tu herramienta direcciona en... | Escribir en el campo "Address" |
|---|---|
| **Base 0** (QModMaster por defecto, Modbus Poll con *PLC addresses* desmarcado) | **0** |
| **Base 1** (Modbus Poll con *PLC addresses* marcado, `mbpoll`) | **1** |

**Cómo saber en cuál estás:** si al pedir la dirección `0` recibís
**excepción 02 (ILLEGAL DATA ADDRESS)** y al pedir `1` funciona, estás en base 1.
Y al revés. No es un error del firmware.

### 9.2 Discrete Input 10001 — el pulsador

| Concepto | Valor |
|---|---|
| Función | **0x02** Read Discrete Inputs |
| Dirección | `0` (base 0) |
| Cantidad | 1 |
| Tipo | 1 bit |

**Qué hacer:** poner la herramienta a sondear en forma continua y presionar el
pulsador.

| Estado físico | Valor leído | Qué significa |
|---|---|---|
| Pulsador suelto | **0** | Contacto abierto, pull-up mantiene el pin en alto, el firmware invierte → 0 |
| Pulsador presionado | **1** | Contacto a GND, el firmware invierte → 1 |

**Cómo interpretarlo:** el cambio debe ser **inmediato y limpio**, sin valores
intermedios ni parpadeos. Si vieras el valor oscilando con el pulsador quieto,
el antirrebote no está funcionando (`config.ANTIRREBOTE_MS`).

> Recordá que es un **pulsador momentáneo**: hay que mantenerlo presionado para
> ver el 1 en pantalla.

### 9.3 Input Register 30001 — el potenciómetro

| Concepto | Valor |
|---|---|
| Función | **0x04** Read Input Registers |
| Dirección | `0` (base 0) |
| Cantidad | 1 |
| Tipo | UINT16, **sin signo** |
| Rango declarado | 0 a 4095 (ADC de 12 bits, valor **crudo**) |

**Configurar el formato como `Unsigned` / `UInt16`**, no como `Signed`. Con 12
bits nunca superaría 32767, pero declararlo bien documenta la intención.

| Posición del potenciómetro | Valor esperado | Nota |
|---|---|---|
| Tope mínimo | **0 a 150** | El ADC del ESP32 tiene un offset: **es normal que no llegue a 0 exacto** |
| Un cuarto | ≈ 1000 | |
| Medio | ≈ 2048 | |
| Tres cuartos | ≈ 3100 | |
| Tope máximo | **4095** | **Satura antes del tope mecánico**: es normal |

> **Dos comportamientos que parecen fallas y no lo son.** El ADC del ESP32 **no
> es lineal**, sobre todo en los extremos: no baja a 0 exacto y satura en 4095
> un poco antes de llegar al final del recorrido. Para regular el brillo de un
> LED es irrelevante; en una aplicación de medición real haría falta calibración
> por tramos o un ADC externo. Vale la pena mencionarlo en el informe.

**Verificación de endianness (pregunta 3 de evaluación):** girar el
potenciómetro al máximo debe dar un número **cercano a 4095**.

| Interpretación | Bytes `0F FF` | Resultado |
|---|---|---|
| Correcta (big-endian) | MSB=0x0F, LSB=0xFF | **4095** ✅ |
| Invertida (little-endian) | leído al revés | 65295 ❌ absurdo |

Por eso se prueba en los **extremos** y no en el medio: ahí el error es obvio.

### 9.4 Coil 00001 — el LED digital

| Concepto | Valor |
|---|---|
| Función lectura / escritura | **0x01** / **0x05** Write Single Coil |
| Dirección | `0` (base 0) |
| Tipo | 1 bit |

**Qué hacer:** escribir el valor y mirar el LED de GPIO19.

| Valor escrito | Qué viaja en la trama | LED 1 |
|---|---|---|
| ON / 1 / True | **`FF 00`** | Enciende |
| OFF / 0 / False | **`00 00`** | Apaga |

> **Detalle que sorprende:** la función 0x05 **no usa `00 01`** para encender.
> La especificación define únicamente `0xFF00` = ON y `0x0000` = OFF; cualquier
> otro valor debe rechazarse con excepción 03. La razón es la distancia de
> Hamming: ambos valores difieren en 8 bits, así que **ningún error de un solo
> bit puede convertir un "apagar" en un "encender"**. Es seguridad funcional, no
> un capricho. La herramienta hace la traducción sola, pero esto es lo que vas a
> ver en la captura de la trama.

**Verificar la retención:** después de escribir ON, **leer** el Coil con la
función 0x01. Debe devolver 1. El valor persiste en la memoria del servidor
mientras nadie lo escriba — esa es la base del requisito de la Parte 3.

### 9.5 Holding Register 40001 — el LED PWM

| Concepto | Valor |
|---|---|
| Función lectura / escritura | **0x03** / **0x06** Write Single Register |
| Dirección | `0` (base 0) |
| Tipo | UINT16 |
| Rango declarado | **0 a 255** (lo fija la consigna) |

| Valor escrito | Brillo del LED 2 |
|---|---|
| 0 | Apagado |
| 25 | Apenas visible |
| 64 | Bajo |
| 128 | Medio, claramente distinguible |
| 255 | Máximo |

**Cómo interpretarlo:** el brillo **no es lineal con el número**. El ojo tiene
respuesta logarítmica, así que el salto de 0 a 64 se percibe mucho mayor que el
de 191 a 255. No es un defecto del PWM.

**Probar la saturación defensiva:** escribir **5000**. El firmware lo acota a 255
y el LED queda al máximo, sin reiniciarse ni lanzar excepción. Es el
comportamiento correcto de un dispositivo de campo: **degradar de forma segura
ante una orden inválida**, no caerse.

### 9.6 Leer las tramas en crudo

Acá se cumple el requerimiento adicional 3 de la consigna.

| Herramienta | Dónde ver las tramas |
|---|---|
| Modbus Poll | *Display → Communication Traffic* (Ctrl+T) |
| QModMaster | Panel inferior de *Raw Data* / *Bus Monitor* |
| mbpoll | Agregar `-v` (verbose) |

Copiar una trama y decodificarla con la herramienta del proyecto:

```bash
python herramientas/modbus_tramas.py "01 04 00 00 00 01 31 CA"
```

Salida:

```
TRAMA: 01 04 00 00 00 01 31 CA
Longitud: 8 bytes
----------------------------------------------------------------------
[0]    01        Direccion de esclavo = 1  (Unit ID del esclavo destinatario)
[1]    04        Codigo de funcion = 4 (Read Input Registers)
[2-3]  00 00     Direccion inicial = 0x0000 (0)  -> Modicon 30001
                 BIG-ENDIAN: primero el byte alto 0x00, luego 0x00
[4-5]  00 01     Cantidad a leer = 1 elemento(s)
----------------------------------------------------------------------
[ 6- 7] 31 CA     CRC-16 = 0xCA31  (transmitido LITTLE-ENDIAN)
                 VERIFICACION: CORRECTA — la trama es integra
```

**Qué mirar en la captura, y qué demuestra cada cosa:**

| Campo | Qué demuestra |
|---|---|
| Byte 0 = `01` | El direccionamiento por Unit ID funciona |
| Byte 1 = `04` | La función pedida. Si volviera `84`, es una **excepción** |
| Bytes 2-3 | La dirección viaja como offset **desde 0**, no como 30001 |
| Bytes 2-3 en ese orden | Los campos de 16 bits son **big-endian** (MSB primero) |
| Últimos 2 bytes | El CRC viaja **little-endian**: es la única excepción del protocolo |

Capturar **una trama por cada función usada (02, 04, 05, 06)** con su respuesta.
Son 8 tramas y cubren por completo el requerimiento de análisis del informe.

### 9.7 Provocar una excepción a propósito

Vale mucho en el informe: demuestra que el esclavo rechaza correctamente lo que
debe rechazar, no solo que responde a lo que le sale bien.

**Cómo:** leer el Input Register en la dirección `10` (que no existe en el mapa).

```
Petición:  01 04 00 0A 00 01 [CRC]
Respuesta: 01 84 02 [CRC]
              │  └── código de excepción 02 = ILLEGAL DATA ADDRESS
              └── 0x84 = 0x04 | 0x80 → bit 7 en 1 = respuesta de excepción
```

**Interpretación:** el esclavo está vivo, escuchó, verificó el CRC y decidió
rechazar. Es diagnósticamente **opuesto** a un timeout, que significaría que no
llegó nada. Confundir ambos hace perder horas revisando cables cuando el
problema está en el mapa de registros.

## 10. Checklist de validación

Marcar cada casilla **solo por haberlo visto en pantalla**, nunca por deducción.

| # | Prueba | Función | Resultado esperado | Valor obtenido | ✔ |
|---|---|---|---|---|---|
| 1 | Leer 10001, pulsador suelto | 0x02 | 0 | | ⬜ |
| 2 | Leer 10001, pulsador presionado | 0x02 | 1 | | ⬜ |
| 3 | Leer 30001, potenciómetro al mínimo | 0x04 | 0 a 150 | | ⬜ |
| 4 | Leer 30001, potenciómetro al medio | 0x04 | ≈ 2048 | | ⬜ |
| 5 | Leer 30001, potenciómetro al máximo | 0x04 | ≈ 4095 | | ⬜ |
| 6 | Escribir ON en 00001 | 0x05 | LED 1 enciende | | ⬜ |
| 7 | Escribir OFF en 00001 | 0x05 | LED 1 apaga | | ⬜ |
| 8 | Leer 00001 tras escribir ON | 0x01 | Devuelve 1 (retención) | | ⬜ |
| 9 | Escribir 255 en 40001 | 0x06 | LED 2 al máximo | | ⬜ |
| 10 | Escribir 128 en 40001 | 0x06 | LED 2 a brillo medio | | ⬜ |
| 11 | Escribir 0 en 40001 | 0x06 | LED 2 apagado | | ⬜ |
| 12 | Leer 40001 tras escribir 128 | 0x03 | Devuelve 128 (retención) | | ⬜ |
| 13 | Escribir 5000 en 40001 | 0x06 | Se acota a 255, sin reinicio | | ⬜ |
| 14 | Leer dirección inexistente (offset 10) | 0x04 | **Excepción 02** | | ⬜ |
| 15 | Consultar con Unit ID = 2 | 0x04 | **Timeout** (no hay tal esclavo) | | ⬜ |
| 16 | Sondeo continuo 3 min sin errores | 0x04 | 0 fallos de CRC ni timeouts | | ⬜ |

> Las pruebas **13, 14 y 15 son las que más suelen omitirse** y las que más valor
> aportan. La 15 en particular demuestra el **filtrado por Unit ID**: el esclavo
> recibe eléctricamente esa trama y la descarta en silencio porque no es para él.
> Un informe que solo muestra el camino feliz se lee como un informe sin trabajo
> de banco real.

**Anotar además:**

| Medición | Valor | Dónde se usa |
|---|---|---|
| VIN medido | ____ V | Paso 2 · informe |
| Punto medio del divisor | ____ V | Paso 2 · informe |
| Longitud del bus | ____ cm | Justificación de §3.1 |
| Errores en 3 min de sondeo | ____ | Prueba 16 |

## 11. Evidencia a capturar para el informe

El informe se redacta al final, pero **la evidencia hay que sacarla ahora**,
con el banco armado. Guardar todo en `evidencia/`.

| # | Qué capturar | Formato | Para qué sección |
|---|---|---|---|
| 1 | Foto del montaje completo, con el divisor visible | JPG | Arquitectura y capa física |
| 2 | Detalle del divisor RO→RX | JPG | Adaptación de niveles |
| 3 | Multímetro midiendo el punto medio del divisor | JPG | Verificación del diseño |
| 4 | Shell de Thonny con la cabecera de arranque (Unit ID = 1) | PNG | Implementación |
| 5 | Salida de `prueba_perifericos.py` con las 5 pruebas OK | PNG | Pruebas y resultados |
| 6 | Lectura del DI 10001 con el pulsador en ambos estados | PNG | Validación |
| 7 | Lectura del IR 30001 en los 3 extremos del potenciómetro | PNG | Validación |
| 8 | Escritura del Coil + foto del LED encendido | PNG + JPG | Validación |
| 9 | Escritura del HR con 3 valores + fotos del brillo | PNG + JPG | Validación |
| 10 | **Ventana de tráfico con las 8 tramas (petición y respuesta × 4 funciones)** | PNG | **Análisis de tramas** |
| 11 | Respuesta de excepción 02 | PNG | Manejo de errores |
| 12 | Salida de `modbus_tramas.py` decodificando una trama real capturada | TXT | Análisis de tramas |
| 13 | Checklist de §10 completo con los valores anotados | — | Pruebas y resultados |

> **La captura 10 es la más importante y la que más se olvida.** Sin la ventana
> de tráfico no hay forma de escribir el análisis de tramas, y ese es un ítem
> puntuado explícitamente. Sacarla antes de desarmar el banco.

## 12. Diagnóstico de fallas

Regla: **una hipótesis, un experimento, una variable por vez.** Y la pregunta que
resuelve la mitad de los casos: ¿el problema es de hardware (la señal no existe)
o de software (existe pero se interpreta mal)?

### 12.1 El ESP32 no arranca o se reinicia solo

| Causa | Verificación |
|---|---|
| **RO conectado directo al GPIO16 sin divisor** | Medir GPIO16: debe dar ≈3,1 V, **nunca 5 V**. Es la causa más grave |
| Cortocircuito en la protoboard | Continuidad entre 3V3/VIN y GND |
| Algo conectado a un pin de strapping | Revisar que nada toque GPIO 0, 2, 12 ni 15 |

### 12.2 El esclavo nunca responde (timeout siempre)

En orden de probabilidad:

| # | Causa | Cómo descartarla |
|---|---|---|
| 1 | **A y B intercambiadas** | Intercambiarlas. No rompe nada y es la prueba más rápida |
| 2 | **Falta la masa común** | Continuidad entre GND del ESP32 y GND del USB-RS485 |
| 3 | Parámetros serie distintos | Comparar la cabecera del Shell contra la config de la herramienta |
| 4 | Unit ID equivocado | La cabecera debe decir `Unit ID = 1` |
| 5 | COM equivocado | ¿Estás usando el COM del conversor o el del ESP32? |
| 6 | Thonny sigue ocupando el puerto | Cerrar Thonny o desconectar el intérprete |
| 7 | `main.py` no está corriendo | Reconectar Thonny: la cabecera debe aparecer al resetear |
| 8 | DE/RE mal conectados | Ambos al mismo GPIO4. Si RE quedó a GND fijo, el nodo nunca transmite |

### 12.3 Responde a veces sí y a veces no

| Causa | Solución |
|---|---|
| Latencia del buffer del conversor USB | Administrador de dispositivos → propiedades del COM → *Latency Timer* a **1 ms**. Es la causa más frecuente |
| Ruido en el bus por cables sin trenzar | Trenzar A y B a mano; acortar los cables |
| Timeout de la herramienta muy corto | Subirlo a 1000 ms |
| Cables dupont flojos en la protoboard | Reasentarlos: es más común de lo que parece |

### 12.4 Excepción 02 (ILLEGAL DATA ADDRESS) en todo

**No es un error del firmware.** Es el desfasaje base 0 / base 1: la herramienta
está pidiendo la dirección 1 cuando el firmware expone la 0. Ver §9.1 y cambiar
la base de direccionamiento.

### 12.5 Los valores se leen pero son absurdos

| Síntoma | Causa |
|---|---|
| El potenciómetro da ~65000 en vez de ~4095 | Endianness: la herramienta interpreta al revés. Ver §9.3 |
| El potenciómetro da un número negativo | Formato configurado como `Signed`. Cambiarlo a `Unsigned` |
| El valor no cambia al girar | El cursor no está en GPIO34, o el potenciómetro está mal alimentado |
| El valor satura enseguida en 4095 | El potenciómetro está alimentado con 5 V en vez de 3V3 ⚠️ |

### 12.6 "Leo bien el potenciómetro pero los LEDs no hacen nada"

**Causa nº 1, y con diferencia:** se está esperando que el pulsador y el
potenciómetro **locales** muevan los LEDs. No lo hacen, por diseño — ver §9.0.
Los LEDs solo se mueven **escribiendo** desde QModMaster con las funciones 0x05 y
0x06.

Que la lectura del potenciómetro funcione es una **excelente noticia**: prueba
que ya están validados el cableado A/B, la masa común, el divisor RO→RX, el
baudrate, la paridad, el Unit ID, el cálculo de CRC y la conmutación de DE/RE. Lo
único que falta ejercitar es el sentido de escritura.

Si ya estás escribiendo y aun así no pasa nada, seguir este orden:

| # | Verificación | Cómo |
|---|---|---|
| 1 | ¿La trama sale realmente al bus? | Abrir el **Bus Monitor** de QModMaster y comparar byte a byte con la tabla de abajo |
| 2 | ¿El esclavo respondió? | Las funciones 0x05 y 0x06 responden con un **eco idéntico**. Sin eco es timeout, no rechazo |
| 3 | ¿Volvió una excepción? | Si el byte 1 vuelve como `85` u `86`, es excepción: el bit 7 está en 1. El byte siguiente dice la causa |
| 4 | ¿Misma base de direccionamiento que en la lectura? | Si leíste el potenciómetro con dirección `0`, escribí también en `0` |
| 5 | ¿El Shell de Thonny muestra excepciones? | Dejalo conectado al COM del ESP32 mientras usás QModMaster: son puertos distintos |
| 6 | ¿Escribiste en el área correcta? | El Coil es 0x05, **no** 0x06. El PWM es 0x06, **no** 0x05 |

**Tramas exactas hacia el Esclavo 1** (verificadas con `modbus_tramas.py`):

| Acción | Trama que debe aparecer en el Bus Monitor |
|---|---|
| Coil 00001 = ON | `01 05 00 00 FF 00 8C 3A` |
| Coil 00001 = OFF | `01 05 00 00 00 00 CD CA` |
| HR 40001 = 255 | `01 06 00 00 00 FF C9 8A` |
| HR 40001 = 128 | `01 06 00 00 00 80 88 6A` |
| HR 40001 = 0 | `01 06 00 00 00 00 89 CA` |
| Leer Coil 00001 | `01 01 00 00 00 01 FD CA` |
| Leer HR 40001 | `01 03 00 00 00 01 84 0A` |

La respuesta a `0x05` y `0x06` es un **eco idéntico** a la petición.

Cualquier trama capturada se puede desglosar con:

```bash
python herramientas/modbus_tramas.py "01 05 00 00 FF 00 8C 3A"
```

### 12.7 El LED no responde

| Síntoma | Causa |
|---|---|
| Nunca enciende | LED al revés (ánodo al GPIO), o falta la resistencia, o pin equivocado |
| El PWM solo enciende o apaga | El pin no admite PWM, o la conversión de rango está mal |
| El PWM titila | `config.PWM_FRECUENCIA_HZ` demasiado baja |

### 12.8 El menú *Modbus Diagnostics* de QModMaster siempre da timeout

**Es esperable y no indica ninguna falla.** Ese menú usa funciones MODBus que
este esclavo no implementa, y que además la consigna no pide.

```
------- Modbus Diagnotics : Report Slave ID 1 -------
Read diagnostics data failed.
Error : Timeout
```

*Report Slave ID* es la **función 0x11 (17 decimal)**, y *Diagnostics* es la
**0x08**. Ninguna de las dos forma parte de las cuatro del trabajo.

**Hay dos motivos independientes por los que la trama se descarta**, y basta con
el primero:

| # | Motivo | Detalle |
|---|---|---|
| 1 | **La trama es demasiado corta** | `get_request()` de `umodbus` empieza con `if len(req) < 8: return None`. La petición de *Report Slave ID* es `01 11 C0 2C`: **4 bytes**. Se descarta antes de mirar siquiera el código de función |
| 2 | **La función no está implementada** | La librería solo maneja 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F y 0x10 |

#### Qué funciones responde este esclavo

| Código | Función | ¿Responde? | ¿La usa el TP? |
|---|---|---|---|
| 0x01 | Read Coils | ✅ | Sí — verificar retención |
| 0x02 | Read Discrete Inputs | ✅ | **Sí** |
| 0x03 | Read Holding Registers | ✅ | Sí — verificar retención |
| 0x04 | Read Input Registers | ✅ | **Sí** |
| 0x05 | Write Single Coil | ✅ | **Sí** |
| 0x06 | Write Single Register | ✅ | **Sí** |
| 0x0F | Write Multiple Coils | ✅ | No |
| 0x10 | Write Multiple Registers | ✅ | No |
| **0x08** | **Diagnostics** | ❌ timeout | No |
| **0x11** | **Report Slave ID** | ❌ timeout | No |
| 0x07, 0x14-0x18, 0x2B | Otras | ❌ timeout | No |

> **Observación de conformidad, buena para el informe.** Según la especificación
> (sección 7, *MODBUS Exception Responses*), un servidor que recibe un código de
> función que no implementa **debería responder con la excepción 01 (ILLEGAL
> FUNCTION)**, no quedarse callado. `umodbus` descarta la trama en silencio, de
> modo que el maestro no puede distinguir "función no soportada" de "dispositivo
> ausente". Es una **desviación real de la especificación por parte de la
> librería**, detectada en el banco. Mencionarla suma: demuestra lectura crítica
> de la herramienta, no uso ciego.

#### Cómo comprobar de verdad que el esclavo está vivo

No uses el menú de diagnóstico. Usá una función que sí implementa:

```
Function Code: Read Input Registers (0x04)
Start Address: 0        (o 1, según tu base de direccionamiento)
Number of Registers: 1
```

Trama: `01 04 00 00 00 01 31 CA`. Si devuelve un número que cambia al girar el
potenciómetro, **el esclavo está perfectamente vivo** y el bus completo está
validado en el sentido de lectura.

### 12.9 QModMaster dice "values written correctly" pero el LED no cambia

**El mensaje es cierto: la escritura se ejecutó bien. Lo que está mal es el
valor.** QModMaster confirma que hubo eco del esclavo, no que hayas escrito lo
que querías.

Caso real de este banco, tomado del monitor de tramas:

```
Tx > 01  05  00  00  00  00  CD  CA
Rx > 01  05  00  00  00  00  CD  CA
Sys > values written correctly.
                └──┬──┘
                   └── bytes 4-5 = 0x0000 = OFF
```

Se escribió **apagar**, tres veces seguidas. El LED nunca se encendió porque
nunca se pidió que se encendiera.

**Cómo leer el valor en la trama de escritura, sin depender de la interfaz:**

| Función | Bytes 4-5 | Significado |
|---|---|---|
| 0x05 Write Single Coil | `FF 00` | **ON** |
| 0x05 Write Single Coil | `00 00` | OFF |
| 0x06 Write Single Register | `00 FF` | 255 (PWM al máximo) |
| 0x06 Write Single Register | `00 80` | 128 (PWM medio) |
| 0x06 Write Single Register | `00 00` | 0 (PWM apagado) |

**Causa en la interfaz:** el valor se ingresa en la **tabla de datos**, no en un
campo aparte, y **hay que confirmar la celda con Enter antes de ejecutar**. Si se
tipea el valor y se hace clic directamente en el botón de ejecutar, la celda
queda en modo edición, el valor no se confirma y se envía el que tenía antes
—habitualmente 0—.

**Procedimiento correcto:**

1. `Function Code` → **Write Single Coil (0x05)**
2. `Start Address` → 0 · `Number of Coils` → 1
3. **Doble clic en la celda de la tabla**, escribir `1`, **pulsar Enter**
4. `Commands → Read/Write`
5. Verificar en el Bus Monitor que los bytes 4-5 digan `FF 00`

**Trama que confirma que salió bien:**

```
Tx > 01  05  00  00  FF  00  8C  3A     ← encender LED 1
Rx > 01  05  00  00  FF  00  8C  3A     ← eco idéntico
```

**Verificación cruzada, que no depende de mirar el LED:** después de escribir,
leer con `Read Coils (0x01)`. Si el LED está encendido, la respuesta debe ser
`01 01 01 01 ...` (dato `01`), no `01 01 01 00 ...` (dato `00`).

## 13. Pregunta de análisis de la Parte 1

> *"¿Qué elemento funciona como maestro y qué elemento funciona como esclavo en
> esta instancia? Justificar la configuración de parámetros serie empleada."*

### 13.1 Roles

**La PC (con Modbus Poll y el conversor USB-RS485) es el MAESTRO. El ESP32 es el
ESCLAVO.**

El criterio no es quién tiene más capacidad de cómputo —el ESP32 y la PC podrían
intercambiarse— sino **quién inicia la transacción**:

| Rol | Comportamiento | En esta instancia |
|---|---|---|
| **Maestro** | Es el único que inicia. No tiene dirección propia, porque nunca es destinatario de una trama | La PC: emite cada petición y espera la respuesta |
| **Esclavo** | Es pasivo. Solo habla cuando lo interrogan con su Unit ID, y descarta en silencio lo que no le corresponde | El ESP32: Unit ID = 1, nunca inicia nada |

Esa asimetría —**un único iniciador, varios que solo responden**— es la
definición del modelo maestro-esclavo por sondeo, y es lo que hace innecesario
cualquier mecanismo de arbitraje en un bus half-duplex: **el turno de palabra lo
otorga el maestro al dirigir la petición**.

En términos del modelo de Purdue, la PC cumple acá un rol de **nivel 2**
(supervisión, equivalente a un SCADA/HMI simplificado) y el ESP32 uno de
**nivel 0-1** (dispositivo de campo). En la Parte 2 ese rol de maestro pasará a
un segundo ESP32, que actuará como controlador de nivel 1.

### 13.2 Justificación de los parámetros serie

**Configuración: 9600 baudios, 8 bits de datos, sin paridad, 1 bit de parada (8N1).**

| Parámetro | Valor | Justificación |
|---|---|---|
| **Baudrate** | 9600 | En RTU la trama se delimita por **silencio**: una pausa mayor a **t1,5** dentro de una trama la invalida. A 9600 ese margen es de **1,72 ms**; a 115200 caería a **143 µs**. El firmware corre sobre **MicroPython**, que es interpretado y ejecuta un recolector de basura con pausas impredecibles de décimas de milisegundo. A 115200 una sola pausa del GC corrompería la recepción. Se resigna ancho de banda —irrelevante: un ciclo mueve 61 bytes— a cambio de **robustez determinista frente al no-determinismo del intérprete** |
| **Bits de datos** | 8 | **Obligatorio en modo RTU**: cada byte del mensaje viaja como un byte binario íntegro. El modo ASCII usa 7 porque codifica cada byte como dos caracteres hexadecimales |
| **Paridad** | Ninguna | La trama ya está protegida por **CRC-16**, que detecta todas las ráfagas de hasta 16 bits sobre el mensaje completo. La paridad solo detecta un número **impar** de bits erróneos por carácter: es redundante y **estrictamente más débil**. Además, `None` es el valor por defecto de `machine.UART` y de los conversores USB-RS485 comunes, lo que reduce el riesgo de desalineación entre nodos — la causa número uno de bus muerto |
| **Bits de parada** | 1 | Consecuencia de no usar paridad. La especificación pide 11 bits por carácter (lo que implicaría 2 bits de parada sin paridad), pero MicroPython y la mayoría de los conversores usan 1, dando 10 bits. La diferencia afecta el cálculo de t1,5/t3,5 en un 10 %, muy por debajo del margen que da haber elegido 9600 baudios. **Los cálculos de este trabajo usan el valor conservador de 11 bits**, que sobreestima los tiempos y deja del lado seguro |

**Trade-off explícito:** la elección de baudrate **no es una propiedad del
protocolo sino de la plataforma de ejecución**. Un firmware en C sobre el mismo
ESP32, con recepción por DMA e interrupciones, operaría sin problemas a 115200.
Así hay que defenderlo.

Desarrollo completo en
[docs/protocolo-comunicacion.md §3](docs/protocolo-comunicacion.md#3-configuración-del-puerto-serie).

---

## Qué queda listo para la Parte 2

Al terminar la Parte 1 quedan validados, y ya no vuelven a ser sospechosos:

- El **mapa de registros** y el direccionamiento base 0.
- Los **parámetros serie** de todo el bus.
- La **adaptación de niveles** y el conexionado ESP32↔MAX485.
- El **firmware del esclavo**, que en la Parte 3 se reutiliza sin un solo cambio:
  solo hay que puentear GPIO13 a GND para que el segundo nodo tome Unit ID = 2.

La Parte 2 consiste en reemplazar a la PC por un segundo ESP32 como maestro.
Todo lo verificado acá se da por bueno, y cualquier problema nuevo se atribuye al
nodo nuevo — que es exactamente el valor de haber aislado esta etapa.

---

## Referencias

- Modbus Organization. (2012). *MODBUS Application Protocol Specification V1.1b3*. [docs/modbusprotocolspecification.pdf](docs/modbusprotocolspecification.pdf)
- Modbus Organization. (2006). *MODBUS over Serial Line Specification and Implementation Guide V1.02*.
- Maxim Integrated. (2003). *MAX481/MAX483/MAX485/MAX487–MAX491/MAX1487 datasheet* (Rev. 8). [docs/MAX481.PDF](docs/MAX481.PDF)
- Texas Instruments. (2014). *TIA/EIA-485 (RS-485) Design Guide* (Application Report SLLA272).
