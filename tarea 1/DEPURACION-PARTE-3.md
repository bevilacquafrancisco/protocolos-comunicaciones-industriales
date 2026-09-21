# Depuración de la Parte 3 — Parpadeo de LED y traza de los tres nodos

**Autores: Bevilacqua Francisco, Peralta Agustina**
**Fecha:** 2026-09-17

---

## 1. Diagnóstico del parpadeo

### 1.1. El mecanismo, identificado en el código

El parpadeo **no es** el esclavo cambiando de estado. Es la **política de degradación del maestro** reaccionando a pérdidas aisladas de trama.

El código anterior de `_registrar_fallo()` decía:

```
si fallos_consecutivos >= 3:
    apagar led_replicador_digital
    apagar led_replicador_pwm
```

y `fallos_consecutivos` sólo volvía a cero al completarse un ciclo **entero** sin un solo fallo. La consecuencia, con tres nodos en el bus:

| Instante | Evento | LED replicadores |
|---|---|---|
| t = 0 ms | Ciclo con una trama perdida | encendidos |
| t = 200 ms | Otra trama perdida | encendidos |
| t = 400 ms | Tercera pérdida → umbral alcanzado | **se apagan** |
| t = 600 ms | Ciclo completo correcto | **se encienden** |
| t = 1000 ms | Se repite la secuencia | **se apagan** |

Eso es un parpadeo de aproximadamente 1 Hz, exactamente lo observado en banco.

### 1.2. Por qué aparece recién ahora

Con dos nodos, las pérdidas esporádicas eran lo bastante raras como para que el umbral de tres fallos consecutivos casi nunca se alcanzara. Con tres nodos la tasa de pérdida sube, y un umbral pensado para "el esclavo está desconectado" empieza a dispararse con "se perdió una trama", que es un evento **normal** en RS-485.

> **La causa raíz no es el parpadeo, es la tasa de pérdida.** El parpadeo es el síntoma visible de que el bus, con el tercer nodo, está perdiendo tramas que antes no perdía. Las correcciones de la sección 2 eliminan el síntoma y hacen visible la causa; la sección 5 sirve para atacarla.

---

## 2. Correcciones aplicadas

| # | Corrección | Archivo | Qué resuelve |
|---|---|---|---|
| 1 | Degradación por **ausencia sostenida** (2 s sin ninguna transacción exitosa) en lugar de por fallos contados | `maestro/main.py` | El parpadeo de los LED replicadores del maestro |
| 2 | **Reintento** de cada transacción antes de darla por perdida | `maestro/main.py`, `config.py` | Una pérdida aislada ya no aborta el ciclo |
| 3 | **Selector con confirmación** por 3 muestras coincidentes | `maestro/main.py`, `diagnostico.py` | Un pulso espurio en el selector desviaba las 4 transacciones del ciclo al esclavo equivocado |
| 4 | **Zona muerta** de ±2 en la escritura del PWM | `maestro/main.py`, `config.py` | Titileo fino del LED PWM del esclavo por ruido del conversor, y una transacción gastada por ciclo para reescribir lo mismo |
| 5 | Capa de **diagnóstico** con niveles, marcas de tiempo y detección de cambios | `comun/diagnostico.py` (nuevo) | Hace medible lo que antes se juzgaba mirando LED |

### 2.1. Sobre el reintento

MODBus no numera ni confirma las tramas: el reintento es el **único** mecanismo de recuperación que define la especificación, y es el que usa cualquier maestro industrial. Es seguro aquí porque las cuatro transacciones son **idempotentes** — dos lecturas y dos escrituras de valor absoluto, no incrementos: repetir una escritura deja al esclavo en el mismo estado que ejecutarla una vez.

Costo en el peor caso: un reintento × 300 ms de timeout = 300 ms adicionales sobre un período de 200 ms. El ciclo se estira, pero nunca se bloquea.

### 2.2. Sobre la degradación por tiempo

La intención original sigue intacta: **no mostrar un dato viejo como si fuera actual**. Un operador que ve el LED replicador encendido supone que ésa es la lectura presente del esclavo. Lo que cambia es el criterio: ahora se exige ausencia sostenida de comunicación, que es lo que realmente significa "el esclavo no está".

---

## 3. Carga del firmware en Thonny

**Hay un archivo nuevo.** `comun/diagnostico.py` debe copiarse a la raíz del sistema de archivos de **los tres** ESP32, junto a `config.py` y `perifericos.py`.

Para cada placa:

1. Conectar el ESP32 y seleccionar el intérprete en *Herramientas → Opciones → Intérprete*.
2. Abrir *Ver → Archivos*. El panel inferior muestra el sistema de archivos del dispositivo.
3. Subir, en este orden:

| Archivo del repositorio | Nombre en el ESP32 | Maestro | Esclavo 1 | Esclavo 2 |
|---|---|---|---|---|
| `firmware/comun/config.py` | `config.py` | sí | sí | sí |
| `firmware/comun/perifericos.py` | `perifericos.py` | sí | sí | sí |
| `firmware/comun/diagnostico.py` | `diagnostico.py` | **sí (nuevo)** | **sí (nuevo)** | **sí (nuevo)** |
| `firmware/maestro/main.py` | `main.py` | sí | — | — |
| `firmware/esclavo/main.py` | `main.py` | — | sí | sí |

4. Reiniciar la placa con Ctrl+D en el Shell.

> Los dos esclavos llevan **el mismo** `main.py`. La dirección la determina el jumper de GPIO13 en el arranque: abierto = Unit ID 1, puenteado a GND = Unit ID 2.

### 3.1. Los cinco archivos van juntos

`diagnostico.py` y `config.py` se estrenaron en la misma versión: **subir uno y olvidar el otro deja la placa con constantes que no existen.**

| Síntoma en el Shell de Thonny | Qué significa |
|---|---|
| `AttributeError: 'module' object has no attribute 'NIVEL_LOG'` | Falta el `config.py` actualizado en esa placa |
| `AVISO: config.py en esta placa es de una versión anterior. Faltan: ...` | Lo mismo, ya detectado por el firmware |
| `AttributeError: ... has no attribute '_uart'` | Versión vieja de `main.py`. Instrumentaba por herencia, que no funciona en el esclavo |
| `ImportError: can't import name ...` | `diagnostico.py` viejo en esa placa |
| `ERROR DE DESPLIEGUE ... versión en la placa: N` | Lo mismo, ya detectado: el firmware dice qué subir y se detiene |

El firmware verifica la configuración al arrancar y, si falta algo, **sigue funcionando con valores por defecto seguros e informa cuáles faltan**, en lugar de abortar. Es el criterio habitual para configuración externa: un nodo que arranca degradado y lo declara es más útil que un nodo que no arranca.

Aun así, **las correcciones del §2 no quedan realmente aplicadas hasta subir el `config.py` nuevo**: sin él se usan los valores por defecto del código, no los del proyecto.

Cada firmware declara qué versión de `diagnostico.py` necesita y **lo comprueba antes de importar nada**, de modo que una placa desactualizada se detiene con un mensaje que dice exactamente qué archivo subir, en lugar de un `ImportError` que hay que interpretar:

```
==================================================================
ERROR DE DESPLIEGUE
diagnostico.py en esta placa es de una version anterior.
  version en la placa : 2
  version requerida   : 3

Subir firmware/comun/diagnostico.py a la raiz del ESP32 y
reiniciar con Ctrl+D. Recordar cerrar y reabrir el archivo en
Thonny antes de subirlo: el editor trabaja sobre su propio buffer.
==================================================================
```

### 3.2. Pruebas en la PC, antes de tocar las placas

Ninguna de las dos necesita hardware:

```
python "tarea 1/herramientas/prueba_diagnostico.py"            → FALLAS: 0
python "tarea 1/herramientas/prueba_config_desactualizado.py"  → arranca y avisa
python "tarea 1/herramientas/prueba_version_despliegue.py"     → detiene y explica
```

La primera verifica la lógica del módulo (21 comprobaciones). La segunda reproduce el fallo de despliegue descrito arriba y confirma que degrada bien.

---

## 4. Uso de la traza

### 4.1. Niveles

Se configuran en `config.py`, línea `NIVEL_LOG`. El valor se puede cambiar **en caliente** desde el Shell de Thonny sin reiniciar, lo que permite subir el detalle justo cuando se reproduce la falla:

```python
>>> import diagnostico
>>> LOG.fijar_nivel(diagnostico.TRAMA)
```

| Nivel | Nombre | Qué agrega | Cuándo usarlo |
|---|---|---|---|
| 0 | SILENCIO | nada | Medición de tasa de error y tiempo de ciclo |
| 1 | ERROR | fallos de transacción | Operación normal desatendida |
| 2 | AVISO | cambios de selección, esclavo ausente/presente, transacciones recuperadas | **Primer nivel útil para el parpadeo** |
| 3 | INFO | resumen periódico, transiciones de las salidas | **Valor por defecto. Punto de partida** |
| 4 | DETALLE | una línea por transacción, con tiempo y resultado | Cuando ya se sabe qué transacción falla |
| 5 | TRAMA | volcado hexadecimal de cada trama | Capturas cortas, de a un nodo por vez |

### 4.2. Advertencia sobre el efecto sonda

Cada `print()` por la consola USB de Thonny cuesta entre **1 y 3 ms**. El esclavo debe responder dentro de los 300 ms de timeout del maestro. En nivel 5, un esclavo puede tardar más que ese timeout en volver a atender el bus, **generando timeouts que no existen con la traza apagada**.

Regla práctica:

- Nivel 5 **en un solo nodo por vez**, y en capturas de pocos segundos.
- Nunca medir tasa de error por encima del nivel 3.
- Si al subir el nivel aparecen errores nuevos, **los produjo la traza**, no el bus.

### 4.3. Formato de las líneas

```
[    12.480] A [MAESTRO] Seleccion -> Esclavo 2 (cambios=1 rechazos=0)
 └────┬────┘ │  └───┬──┘
      │      │      └ nodo que emite
      │      └ nivel: E error · A aviso · I info · D detalle · T trama
      └ segundos.milisegundos desde el arranque de ESE nodo
```

El tiempo es **relativo al arranque de cada placa**, así que los tres relojes no coinciden entre sí. Para correlacionar, reiniciar los tres con Ctrl+D lo más junto posible, o usar como referencia común un evento visible en las tres consolas (el cambio de selector aparece en el maestro y se refleja en el tráfico de ambos esclavos).

### 4.4. El reporte periódico del maestro

Cada 5 s el maestro emite tres líneas: una del ciclo y una por esclavo.

```
[   400.544] I [MAESTRO] ciclos=1470 fallos=0 (0.0%) t_ciclo=126ms | ID=1 DI=0 IR=0 -> PWM=0
   -> E1 ACTIVO          78tx 0err (0.0%)  acum: 2954tx 7err (0.2%) 7to r=7
      E2 pausa 210s            sin sondeo  acum: 2046tx 239err (11.6%) 238to/1tr r=239
```

Cada línea de esclavo separa **dos informaciones que antes se confundían**:

| Columna | Qué responde |
|---|---|
| `->` | Cuál es el esclavo **seleccionado ahora** |
| `ACTIVO` / `pausa 210s` | Si se lo está sondeando, o hace cuánto que no |
| **ventana** (columna del medio) | Qué pasó **en los últimos 5 s**. Es el estado ACTUAL |
| `acum:` | Qué pasó **desde el arranque**. Es el HISTORIAL |

> **Por qué importa la distinción.** Con un solo esclavo seleccionado, el otro conserva sus totales congelados. Una línea que repite `err=239 (11.6%)` cada cinco segundos se lee como un nodo que está fallando *ahora*, cuando en realidad **no se lo está sondeando**. La ventana lo dice sin ambigüedad: `sin sondeo` no es lo mismo que `0err`.

Abreviaturas del desglose, que sólo aparecen si hubo algún error:

| Símbolo | Significado |
|---|---|
| `238to` | 238 **t**ime**o**uts — el esclavo no contestó |
| `4ex` | 4 **ex**cepciones MODBus — contestó rechazando la petición |
| `1tr` | 1 error de **tr**ama — CRC inválido o longitud inesperada |
| `r=239` | Peor racha de fallos consecutivos |

Un nodo sano produce una línea corta: `78tx 0err (0.0%)`, sin desglose.

### 4.5. Comandos desde el Shell de Thonny

Tras interrumpir con Ctrl+C, el maestro queda accesible como `MAESTRO`:

```python
>>> MAESTRO.reiniciar_estadisticas()      # antes de una medición para el informe
>>> LOG.fijar_nivel(diagnostico.TRAMA)    # capturar tramas en vivo
>>> LOG.fijar_nivel(diagnostico.INFO)     # volver al nivel normal
```

`reiniciar_estadisticas()` separa la puesta a punto —donde los errores son esperables y no dicen nada del sistema terminado— de la corrida que se va a documentar, **sin reiniciar la placa**: un reinicio obligaría a rehacer la puesta en marcha del bus.

### 4.6. Procedimiento con tres consolas

Thonny maneja una sola conexión serie por ventana. Para ver los tres nodos a la vez:

1. Abrir **tres instancias de Thonny** (ejecutar el programa tres veces).
2. En cada una, *Herramientas → Opciones → Intérprete* y elegir un puerto COM distinto.
3. Ordenar las ventanas en columnas: Esclavo 1 · Maestro · Esclavo 2.
4. Arrancar los **esclavos primero** y el maestro último: así el maestro no acumula timeouts de arranque que ensucien la traza.

---

### 4.7. Captura de tramas

Los tres nodos registran **todas las tramas que ven**, en ambos sentidos, en un buffer circular en memoria. Está activo siempre y no hay que encender nada.

#### Por qué en memoria y no impreso al vuelo

Imprimir cada trama en el momento cuesta 1-3 ms. Una transacción son dos tramas, el ciclo tiene cuatro transacciones, y el esclavo debe contestar dentro de los 300 ms de timeout: **la traza inmediata consume el presupuesto temporal del propio protocolo y genera timeouts que no existen sin ella.**

Registrar en un buffer cuesta una copia de ocho bytes: microsegundos. El costo de imprimir se paga una sola vez, al pedir el volcado, cuando ya no importa perturbar el bus porque el dato ya está guardado.

#### Volcado a pedido

Ctrl+C y después:

```python
>>> MAESTRO.volcar_tramas()     # en el maestro
>>> VOLCAR()                    # en cualquiera de los dos esclavos
```

```
[    40.132] I [MAESTRO] --- CAPTURA A PEDIDO (8 de 1204 vistas) ---
           TX      8B | 01 02 00 00 00 01 B9 CA
                        E1 FC=0x02 Read Discrete Inputs  dir=0x0000 n=1
     +31ms RX      6B | 01 02 01 00 A1 88
                        E1 FC=0x02 Read Discrete Inputs  -> bits=0b00000000
      +2ms TX      8B | 01 04 00 00 00 01 31 CA
                        E1 FC=0x04 Read Input Registers  dir=0x0000 n=1
     +33ms RX      7B | 01 04 02 08 00 BE F0
                        E1 FC=0x04 Read Input Registers  -> 2048
      +2ms TX      8B | 01 05 00 00 FF 00 8C 3A
                        E1 FC=0x05 Write Single Coil  dir=0x0000 valor=0xFF00 (ON)
     +30ms RX      8B | 01 05 00 00 FF 00 8C 3A
                        E1 FC=0x05 Write Single Coil  dir=0x0000 valor=0xFF00 (ON)
```

Cada trama ocupa dos líneas porque cumplen funciones distintas: el **hexadecimal es la evidencia** —permite contar campos y verificar el CRC byte a byte— y la **interpretación es la lectura**. Para un informe hacen falta las dos.

| Columna | Qué es |
|---|---|
| `+33ms` | Intervalo desde la trama anterior. Es el que revela el tiempo de respuesta del esclavo y, cuando falta una respuesta, el hueco que dejó |
| `TX` / `RX` / `RX(aj)` | Transmitida · recibida · recibida pero dirigida a otro nodo |
| `8B` | Longitud en bytes, CRC incluido |
| `E1` / `E2` | Unit ID del esclavo involucrado |
| `FC=0x04 ...` | Código y nombre de función según la especificación |

#### Volcado automático ante un fallo

Es la función más útil. Cuando una transacción falla, el maestro imprime **lo que estaba pasando en el bus justo antes**:

```
[   594.201] E [MAESTRO] Fallo 0x04 Read Input Registers con Esclavo 2 [TIMEOUT] (1 consecutivos): ...
[   594.203] I [MAESTRO] --- CONTEXTO DEL FALLO (3 de 2841 vistas) ---
           TX      8B | 02 04 00 00 00 01 31 F9
                        E2 FC=0x04 Read Input Registers  dir=0x0000 n=1
    +300ms TX      8B | 02 04 00 00 00 01 31 F9
                        E2 FC=0x04 Read Input Registers  dir=0x0000 n=1
     +12ms RX      5B | 02 84 02 32 C1
                        E2 EXCEPCION a FC=0x04 Read Input Registers  codigo=2 (direccion invalida)
```

Esa información es imposible de conseguir a mano: para cuando el operador reacciona al fallo, ya se perdió. Se limita a un volcado cada 8 s para que una ráfaga de fallos no inunde la consola ni agrave el problema que se está diagnosticando.

#### Lo que ve cada nodo

| Nodo | Qué captura |
|---|---|
| Maestro | Sus peticiones (`TX`) y las respuestas que recibe (`RX`) |
| Esclavo | Las peticiones dirigidas a él (`RX`), **las dirigidas al otro esclavo** (`RX(aj)`), y sus propias respuestas (`TX`) |

La captura del esclavo es la más completa de las tres: en un bus multipunto **todos los nodos oyen todo**. Sirve para dos cosas que desde el maestro no se pueden verificar:

- Que el **filtrado por dirección funciona**: aparecen tramas `RX(aj)` y el nodo no responde a ninguna.
- Distinguir **quién perdió la trama**: si el maestro reporta timeout y en el esclavo la petición aparece como `RX` con su `TX` de respuesta, el esclavo contestó y el problema está en el camino de vuelta.

#### Ajustes

En `config.py`:

| Constante | Por defecto | Qué hace |
|---|---|---|
| `CAPTURA_TRAMAS` | 24 | Tramas conservadas. Cubre 3 ciclos completos. `0` desactiva |
| `VOLCAR_TRAMAS_AL_FALLAR` | `True` | Volcado automático de contexto ante un fallo |
| `MS_ENTRE_VOLCADOS` | 8000 | Intervalo mínimo entre volcados automáticos |

#### Cómo se instrumenta, y por qué así

La librería organiza sus dos clases de forma distinta, y eso condiciona el diseño:

| Clase | Rol | Relación con el UART |
|---|---|---|
| `Serial` | Interfaz serie | **Tiene** el UART. El **maestro** la extiende |
| `ModbusRTU` | Servidor esclavo | **Contiene** una `Serial` en un atributo interno. Composición, no herencia |

Por eso la instrumentación se aplica **por envoltura en tiempo de ejecución** y no extendiendo la clase: `InstrumentacionBus` localiza la interfaz real en lugar de suponerla, y funciona igual en los tres nodos.

> Extender `ModbusRTU` y sobrescribir su método de lectura de trama **no instrumenta nada**: ese método vive en el objeto contenido y nunca llega a invocarse. El síntoma es silencioso — contadores en cero para siempre, sin ningún error.

Al arrancar, cada nodo confirma qué instrumentó:

```
[     0.312] I [ESCLAVO 2] Bus instrumentado (atributo _itf): TX y RX bajo observacion
```

Si esa línea no aparece, o aparece un error, el nodo **sigue operando sin captura**. Para averiguar dónde guarda el UART esa versión de la librería:

```python
>>> import diagnostico
>>> diagnostico.explorar(cliente)
```

#### Traza inmediata (nivel 5)

`NIVEL_LOG = 5` imprime cada trama en el instante en que ocurre, sin buffer. Sirve para mirar el bus en vivo, pero **altera el timing**. Para documentar el informe usar siempre la captura, no el nivel 5.

---

## 5. Árbol de decisión

Con `NIVEL_LOG = 3` en los tres nodos, **sondear cada esclavo durante un rato** —conmutando el selector— y leer el reporte periódico del maestro:

```
   -> E1 ACTIVO          78tx 0err (0.0%)  acum: 2954tx 7err (0.2%) 7to r=7
      E2 pausa 210s            sin sondeo  acum: 2046tx 239err (11.6%) 238to/1tr r=239
```

> Comparar siempre la columna **ventana** entre ambos esclavos, no los acumulados: un esclavo que estuvo en pausa tiene el acumulado congelado y no dice nada del estado presente. Para comparar en igualdad de condiciones hay que darle tiempo de sondeo a cada uno.

| Lo que muestra la traza | Causa probable | Qué hacer |
|---|---|---|
| **Ambos** esclavos con tasa parecida y distinta de cero **en ventana** | El medio compartido: terminación, polarización o masas | Sección 6 |
| **Un solo** esclavo con error; el otro en 0,0 % | Ese nodo: su transceptor, su cableado, su alimentación | Cambiar ese MAX485 por el del otro esclavo. Si el error se muda con el módulo, es el módulo; si se queda, es el cableado |
| Muchos `to` y ningún `tr` | El esclavo no recibe o no alcanza a contestar | Mirar el latido de ese esclavo (abajo) |
| Aparece `tr` en el desglose | Ruido o **colisión**: dos nodos transmitiendo a la vez | Verificar que ningún esclavo tenga el mismo Unit ID. Nivel 5 en un esclavo y observar `RX descartado en la ventana de guarda` |
| Aparece `ex` en el desglose | El esclavo responde rechazando: está vivo y el problema es la petición | El mapa de direcciones no coincide entre maestro y esclavo |
| `r=` alta con tasa **baja** | Falla en ráfagas: interferencia externa | Alejar el bus de fuentes conmutadas; trenzar A y B |
| `r=` baja con tasa **alta** | Pérdida uniforme: problema estructural del bus | Sección 6 |
| `Seleccion -> Esclavo N` aparece sin que nadie toque el switch | Ruido en el selector. `rechazos=` cuantifica cuánto | Pull-up externo de 10 kΩ en GPIO13; alejar ese cable del bus; subir `CONFIRMACIONES_SELECTOR` |
| `Coil 00001 ->` / `HR 40001 ->` con transiciones que nadie provocó, en la consola del esclavo | El registro **sí** está cambiando: el origen está en el maestro | Comparar con la traza del maestro en el mismo instante |
| El LED titila pero en el esclavo **no** aparece ninguna transición | El registro no cambia: el problema es eléctrico, no de protocolo | Revisar el LED, su resistencia y la masa de ese nodo |

### 5.1. El latido del esclavo

Cada 5 s, cada esclavo emite:

```
[    35.010] I [ESCLAVO 2] latido: tramas=418 propias=209 ajenas=209 errores=0 | DI=0 IR=2047
```

Su valor está en las tres lecturas que permite:

| Observación | Significado |
|---|---|
| El latido sale y `propias` **crece** | El esclavo recibe y contesta. El problema está en el camino de vuelta hacia el maestro |
| El latido sale pero `propias` **no crece** | El esclavo no está recibiendo sus peticiones. Problema en el sentido maestro → esclavo, o Unit ID equivocado |
| El latido **deja de salir** | El nodo se colgó o se reinició. Revisar alimentación |
| `ajenas` ≈ `propias` | Correcto: el otro esclavo habla y este nodo descarta bien esas tramas por dirección |

---

## 5.2. Verificar la retención de estado (Parte 3, requisito 3)

> *"Verificar que el esclavo que no está seleccionado mantenga el último estado recibido en sus salidas hasta recibir una nueva orden."*

El comportamiento se cumple **por construcción**: los registros MODBus conservan su valor mientras nadie los escriba, y `aplicar_salidas()` los refleja en el hardware en cada vuelta del lazo. No hay lógica de retención explícita porque no hace falta — la retención es una propiedad del modelo de datos de MODBus.

Lo que sí depende del firmware es el requisito complementario: **no reinicializar esos registros dentro del lazo**. Los valores iniciales se fijan una única vez, en `configurar_servidor_modbus()`.

Pero la consigna no pide implementarlo, pide **verificarlo**, y una propiedad que no se puede observar no está verificada. Por eso el esclavo emite evidencia con marca de tiempo.

### Procedimiento

1. Con el selector en el **Esclavo 2**, mover el potenciómetro y el switch del maestro hasta dejar las salidas del esclavo en un estado reconocible (por ejemplo LED encendido y PWM a media intensidad).
2. Conmutar el selector al **Esclavo 1**.
3. Observar la consola del Esclavo 2 durante al menos 15 s.
4. Volver a conmutar al Esclavo 2.

### Lo que debe aparecer en la consola del Esclavo 2

```
[     2.600] A [ESCLAVO 2] RETENCION: sin ordenes hace 1600 ms. Salidas mantenidas en LED=1 PWM=200
[     5.000] I [ESCLAVO 2] latido: tramas=62 propias=24 ajenas=38 errores=0 | DI=0 IR=2047
   salidas: LED=1 PWM=200 | 12 ordenes, ultima hace 4000 ms  <- RETENIENDO
[    10.000] I [ESCLAVO 2] latido: tramas=112 propias=24 ajenas=88 errores=0 | DI=0 IR=2047
   salidas: LED=1 PWM=200 | 12 ordenes, ultima hace 9000 ms  <- RETENIENDO
[    15.000] I [ESCLAVO 2] latido: tramas=162 propias=24 ajenas=138 errores=0 | DI=0 IR=2047
   salidas: LED=1 PWM=200 | 12 ordenes, ultima hace 14000 ms  <- RETENIENDO
[    16.400] A [ESCLAVO 2] FIN DE RETENCION: llego una orden. Salidas durante la pausa: SIN CAMBIOS (LED=1 PWM=200)
```

### Por qué esto constituye una verificación

| Observación | Qué demuestra |
|---|---|
| `salidas: LED=1 PWM=200` idéntico en los tres latidos | Las salidas **no cambiaron** durante la pausa |
| `12 ordenes` no avanza | **Ninguna orden** llegó durante ese intervalo |
| `ultima hace 4000 → 9000 → 14000 ms` | El intervalo sin órdenes crece: la pausa es real y sostenida |
| `propias=24` congelado mientras `ajenas` crece | El nodo **está vivo y escuchando**, pero no se lo está direccionando. Descarta que las salidas se mantengan porque el esclavo se colgó |
| `FIN DE RETENCION: ... SIN CAMBIOS` | El firmware comparó las salidas al entrar y al salir de la retención, y coinciden |

La cuarta fila es la que cierra el argumento. Un nodo colgado también mantendría sus salidas quietas: lo que distingue la retención correcta de un cuelgue es que el nodo **siga procesando el bus** mientras retiene, y eso es exactamente lo que muestra `ajenas` creciendo.

La última línea es la comparación que hace el propio firmware, no el autor del informe: registra los valores al entrar en retención y los contrasta al salir. Si algo hubiera modificado las salidas sin mediar una orden, diría `MODIFICADAS, revisar`.

### Umbral

`MS_PARA_DECLARAR_RETENCION = 1500` en `config.py`: más de siete períodos de sondeo. No se alcanza por una pérdida de tramas aislada, sólo porque el maestro dejó efectivamente de dirigirse a ese nodo. No cambia ningún comportamiento — la retención ocurre siempre; el umbral sólo decide cuándo registrarla.

### Ensayo previo en la PC

```
python "tarea 1/herramientas/demo_retencion_estado.py"
```

Corre la misma lógica contra un servidor simulado y produce la salida de arriba. Sirve para saber qué esperar antes de ir al banco; **la verificación que vale para el informe es la del hardware**.

---

## 6. Verificaciones de hardware

Si la traza indica un problema del medio compartido, tres mediciones en este orden. Las tres son rápidas y falsables.

### 6.1. Terminación oculta en los módulos — hacer esta primero

Muchos módulos MAX485 traen una resistencia de **120 Ω soldada entre A y B**. Con tres módulos, eso son tres resistencias en paralelo: **40 Ω**, que cargan el bus mucho más de lo previsto y hunden la amplitud diferencial.

**Con todo desconectado de la alimentación**, medir con el téster en ohmios entre A y B:

| Lectura | Interpretación |
|---|---|
| Circuito abierto / muy alta | Ningún módulo tiene terminación. Es lo que asume el diseño actual |
| ≈ 120 Ω | Un solo módulo la trae. Aceptable |
| ≈ 60 Ω | Dos módulos la traen. Agregar la polarización de 6.2 |
| ≈ 40 Ω | **Los tres la traen.** Desoldar dos, o agregar la polarización de 6.2 |

Esta medición decide todo lo demás, y además confirma o corrige lo que afirma el informe sobre la terminación del bus.

### 6.2. Polarización, si hay terminación

Con el bus cargado por terminaciones y ningún nodo transmitiendo, la tensión diferencial cae a ~0 V, dentro de la zona indeterminada de ±200 mV del receptor: la salida oscila con el ruido y el UART interpreta esos flancos como bits de arranque.

Red de polarización, **en un solo punto del bus**:

```
        5 V
         │
      [ 680 Ω ]
         │
    A ───┴──────────────  (línea A del bus)

    B ───┬──────────────  (línea B del bus)
         │
      [ 680 Ω ]
         │
        GND
```

Con 60 Ω de terminación equivalente: I = 5 / (680 + 60 + 680) = 3,52 mA → V_AB = 211 mV ✓ supera el umbral.
Con 1 kΩ en lugar de 680 Ω: V_AB = 145 mV ✗ queda dentro de la zona muerta y el bus sigue sin funcionar.

> Una sola red. Cada red adicional carga el bus en paralelo y reduce la amplitud disponible.

### 6.3. Masa común entre los tres nodos

RS-485 es diferencial, pero el receptor sólo tolera una tensión de modo común acotada **respecto de su propia masa**. Sin referencia común esa condición no se garantiza.

Es la causa principal de la falla característica *"funcionaba con dos nodos y se degrada al agregar el tercero"*, que es exactamente la situación de este banco.

Verificar que los tres GND estén unidos con un conductor propio, y no solamente a través de los USB de la notebook. **Medir la continuidad**: téster en continuidad entre el GND del maestro y el GND de cada esclavo.

### 6.4. Pull-up de RO en el tercer nodo

El Esclavo 2 es el nodo agregado más recientemente. Confirmar que lleva la resistencia de **680 Ω entre RO y 5 V**, igual que los otros dos. Sin ella, el divisor conecta la entrada del UART a masa mientras ese nodo transmite y genera bytes espurios (es el defecto documentado en el informe, §5.3.3 y §9.4.3).

---

## 7. Qué registrar para el informe

| Evidencia | Cómo obtenerla |
|---|---|
| Resumen por esclavo, antes y después de la corrección | `MAESTRO.reiniciar_estadisticas()`, dejar correr, copiar las líneas `E1` / `E2` |
| Tiempo de ciclo con reintentos activos | Línea `t_ciclo=` del maestro |
| Captura de tramas de una transacción completa | Ctrl+C y `MAESTRO.volcar_tramas()` — no altera el timing del bus |
| Contexto de un fallo real | Se vuelca solo. Copiar el bloque `CONTEXTO DEL FALLO` |
| Evidencia de que un esclavo oye el tráfico ajeno | `VOLCAR()` en un esclavo: aparecen líneas `RX(aj)` |
| **Retención de estado del esclavo no seleccionado** | Procedimiento §5.2. Copiar el bloque `RETENCION` → latidos → `FIN DE RETENCION` |
| Evidencia de que el filtrado por dirección funciona | Latido del esclavo mostrando `ajenas` ≈ `propias` |
| Evidencia del parpadeo original | Las líneas `Esclavo N AUSENTE` / `PRESENTE otra vez` con sus marcas de tiempo |
| Medición de resistencia A-B | Valor del téster y la conclusión de la tabla 6.1 |

Esto alimenta la sección 9 del informe técnico (*Resultados y verificación*), que es donde va el contraste entre el modelo temporal calculado y lo medido en banco.
