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

El firmware verifica la configuración al arrancar y, si falta algo, **sigue funcionando con valores por defecto seguros e informa cuáles faltan**, en lugar de abortar. Es el criterio habitual para configuración externa: un nodo que arranca degradado y lo declara es más útil que un nodo que no arranca.

Aun así, **las correcciones del §2 no quedan realmente aplicadas hasta subir el `config.py` nuevo**: sin él se usan los valores por defecto del código, no los del proyecto.

### 3.2. Pruebas en la PC, antes de tocar las placas

Ninguna de las dos necesita hardware:

```
python "tarea 1/herramientas/prueba_diagnostico.py"           → FALLAS: 0
python "tarea 1/herramientas/prueba_config_desactualizado.py" → arranca y avisa
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

### 4.4. Procedimiento con tres consolas

Thonny maneja una sola conexión serie por ventana. Para ver los tres nodos a la vez:

1. Abrir **tres instancias de Thonny** (ejecutar el programa tres veces).
2. En cada una, *Herramientas → Opciones → Intérprete* y elegir un puerto COM distinto.
3. Ordenar las ventanas en columnas: Esclavo 1 · Maestro · Esclavo 2.
4. Arrancar los **esclavos primero** y el maestro último: así el maestro no acumula timeouts de arranque que ensucien la traza.

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
| Captura de tramas de una transacción completa | `NIVEL_LOG = 5` en el maestro, 5 segundos, copiar el bloque hexadecimal |
| Evidencia de que el filtrado por dirección funciona | Latido del esclavo mostrando `ajenas` ≈ `propias` |
| Evidencia del parpadeo original | Las líneas `Esclavo N AUSENTE` / `PRESENTE otra vez` con sus marcas de tiempo |
| Medición de resistencia A-B | Valor del téster y la conclusión de la tabla 6.1 |

Esto alimenta la sección 9 del informe técnico (*Resultados y verificación*), que es donde va el contraste entre el modelo temporal calculado y lo medido en banco.
