# Registro de decisiones de arquitectura (ADR)

Formato: contexto → opciones consideradas → decisión → consecuencias.
Cada ADR debe poder defenderse oralmente en treinta segundos.

## Estado tras la Fase F0 (2026-11-08)

Revisión contra el código de las Tareas 1 y 2 ([analisis-t1.md](analisis-t1.md),
[analisis-t2.md](analisis-t2.md)) y el [spike](spike-nodered-opcua.md).

| ADR | Estado | Cambio en F0 |
|---|---|---|
| 001 | **Aceptado con corrección** | Node-RED sí; el servidor OPC UA **no** con `node-red-contrib-opcua` → ADR-011 |
| 002 | **Aceptado; se activó la consecuencia** | La T1 usa `umodbus`: el stack del esclavo se reescribe |
| 003 | Aceptado | Confirmado: es decisión defendida en la T1. `Potenciometro_pct` declarada en el diccionario |
| 004 | Aceptado | Fundamento reforzado con la medición de la T2 (en PC) |
| 005 | Aceptado | Sin cambios |
| 006 | Aceptado | Sin cambios |
| 007 | Aceptado | Sin cambios; depende de ADR-010 |
| 008 | Aceptado | Sin cambios |
| 009 | **Aceptado con corrección** | La T2 **no** tiene capturas de banco en Sign/SignAndEncrypt: hay que medirlas |
| 010 | **Aceptado (2026-11-09)** | MicroPython con Thonny |
| 011 | Propuesto | Servidor OPC UA del dispositivo 2 con `node-opcua` desde function nodes |
| 012 | **Aceptado (F3)** | Delimitación de respuestas en el maestro por longitud esperada |
| 013 | Propuesto | Cliente OPC UA del dispositivo 3 = v2 de la T2, adaptado |
| 014 | **Aceptado (F3)** | Reintento y ausencia sostenida heredados de la T1 como disparador de `DDEATH` |
| 015 | Propuesto (F1) | El Write OPC UA se responde con el eco MODBus, no al encolar |
| 016 | Aceptado (F3) | Dashboard 2.0: el Dashboard original está sin mantenimiento |
| 017 | Aceptado (F3) | Transporte TCP de desarrollo que emula el desajuste de línea |
| 018 | Aceptado (F3) | Descubrimiento en dos fases (menos de 60 s en el caso típico) |

---

## ADR-001 — El dispositivo 2 es una Raspberry Pi con Node-RED, no un ESP32

**Contexto.** La consigna admite microcontrolador o miniPC para el dispositivo 2, que debe cumplir
tres funciones simultáneas: maestro Modbus RTU, servidor OPC UA y entorno de configuración
versátil para un esclavo desconocido (I-04).

**Opciones.**

1. **ESP32 #2** con stack Modbus propio y servidor OPC UA embebido (open62541 portado).
   Continuidad total con la Tarea Nº1, pero el servidor OPC UA en ESP32 consume gran parte de la
   RAM disponible, soporta un subconjunto de los modos de seguridad y reconfigurarlo en vivo exige
   escribir a mano una consola de configuración.
2. **Raspberry Pi con Python** (`asyncua` + maestro Modbus propio sobre `pyserial`).
   Máxima potencia y control, pero toda la interfaz de configuración y el tablero de estadísticas
   hay que construirlos desde cero.
3. **Raspberry Pi con Node-RED.** Flujo de datos declarativo, Dashboard integrado para la
   configuración en runtime y las estadísticas, servidor OPC UA vía `node-red-contrib-opcua`,
   y acceso al puerto serie en modo binario crudo por `node-red-node-serialport`.

**Decisión.** Opción 3: Raspberry Pi con Node-RED.

**Fundamento.**
- **Requisito I-04.** Reconfigurar en vivo un maestro Modbus frente a un esclavo desconocido es
  precisamente lo que un Dashboard resuelve en minutos y un firmware resuelve en horas. El riesgo
  más alto del día de la defensa se mitiga con esta elección.
- **Representatividad industrial.** Node-RED sobre un gateway de borde es hoy un patrón corriente
  en transformación digital e Industria 4.0: la Raspberry Pi cumple el papel de *edge gateway* del
  nivel 2 del modelo Purdue, exactamente el lugar donde en planta se instala un conversor de
  protocolo. Es un argumento de defensa mucho más fuerte que "pusimos otro microcontrolador".
- **Separación de responsabilidades.** El ESP32 queda confinado al nivel 0/1 (adquisición y
  actuación en tiempo real) y la lógica de integración vive en el nivel 2. La arquitectura se
  explica sola en un diagrama.
- **Reversibilidad.** Los flows son JSON versionado; migrar de la notebook a la Raspberry Pi del
  laboratorio es importar un archivo.

**Consecuencias.**
- Dependencia de la disponibilidad de la Raspberry Pi en el laboratorio → se desarrolla en la
  notebook con el adaptador USB-RS485 y se migra al final (ver riesgo R-02 del plan).
- ~~Hay que validar tempranamente que `node-red-contrib-opcua` cubre NodeIds de cadena fijos,
  `EURange` y modos de seguridad (spike de la Fase F0).~~ **Resuelto en F0:** cubre NodeIds, tipos
  y modos, pero **no** EURange y guarda las contraseñas en texto plano (spike §1). El servidor OPC UA
  se implementa con `node-opcua` desde function nodes (ADR-011). Node-RED sigue siendo el
  dispositivo 2; lo que cambia es *cómo* se arma el servidor dentro de él.
- El acceso serie es `node-red-node-serialport` 2.0.3 en modo binario; su delimitación por silencio
  no alcanza para t3,5 (spike §3), por eso ADR-012.
- La reconfiguración en vivo del enlace (I-04) la cubre el nodo `serial control`
  (`serialport, serialbaud, databits, parity, stopbits`), sin reiniciar Node-RED.
- El CRC se implementa en JavaScript dentro de nodos `function`, lo que **cumple I-01** y, de
  paso, permite mostrar el buffer de la trama en el panel de depuración durante la defensa.

---

## ADR-002 — Stack Modbus propio en ambos extremos, sin librería de protocolo

**Contexto.** La consigna exige, en mayúsculas, generación y verificación del CRC tanto en el
maestro como en el esclavo. La Tarea Nº1 pudo haberse resuelto con una librería de Arduino.

**Opciones.** (a) Librería y explicar el CRC en teoría. (b) Librería en el esclavo y CRC propio en
el maestro. (c) Implementación propia en ambos.

**Decisión.** Opción (c).

**Fundamento.** La lectura literal de la consigna no deja margen: *"incluyendo la GENERACIÓN y
VERIFICACIÓN del código CRC tanto en el MAESTRO MODBUS, cómo en el ESCLAVO MODBUS"*. Además, el
requisito de trazabilidad de código exige referenciar cada fragmento a un bloque del diagrama de
flujo, algo imposible con el interior de una librería. El costo real es bajo: el CRC-16 Modbus son
unas quince líneas y el parser de la trama es una máquina de estados de cuatro estados.

**Consecuencias.**
- ~~Si la Tarea Nº1 usó una librería, **el esclavo debe reescribirse** en la Fase F2.~~
  **Confirmado en F0: la T1 usa `umodbus`** (`tarea-1/firmware/esclavo/main.py:46`), que genera y
  verifica el CRC con `_calculate_crc16()` por tabla. El CRC propio de la T1 existe solo en la PC
  (`tarea-1/herramientas/modbus_tramas.py`). **La capa de protocolo del esclavo se reescribe en F2**;
  configuración, HAL y diagnóstico se conservan (analisis-t1.md §9). El lenguaje se decide en ADR-010.
- Se gana el poder explicar byte a byte cualquier trama que la cátedra señale en la defensa.
- Oráculos para los vectores *golden*: (1) `modbus_tramas.py` de la T1, ya verificado contra el
  vector estándar `123456789` → `0x4B37`; (2) `pymodbus` **sólo como oráculo**, nunca como stack.
  Dos implementaciones independientes que coinciden son la comprobación cruzada que ya usó la T1.
- Lo que la librería hacía bien y el stack propio no debe perder: `uart.flush()` + un carácter de
  espera antes de bajar DE/RE (`umodbus/serial.py` `_send()`), y 200 µs tras subir DE.

---

## ADR-003 — El escalado y la lógica de interpretación viven en el nivel 2, no en el campo

**Contexto.** El potenciómetro entrega 0–4095 (ADC de 12 bits) y el LED PWM acepta 0–255.
Alguien tiene que escalar.

**Decisión.** El esclavo transporta valores crudos; el maestro de nivel 2 realiza el escalado y
publica tanto el valor crudo como el valor de ingeniería.

**Fundamento.** Es el principio de *dumb field device, smart edge*: el dispositivo de campo mide y
actúa, el borde interpreta. Cambiar la escala o la curva de corrección no debería exigir reflashear
una placa en planta. Además permite mostrar en la web el crudo y el porcentaje, lo que evidencia
comprensión del escalado de señal, que es materia de la asignatura.

**Consecuencias.** Una métrica adicional (`Inputs/Potenciometro_pct`, `Float`) que conviene declarar
en el diccionario de datos antes de implementarla.

---

## ADR-004 — Suscripción OPC UA en lugar de lectura cíclica

**Contexto.** La Tarea Nº2 comparó explícitamente `Read` periódico contra
`CreateSubscription` + `CreateMonitoredItems`.

**Decisión.** La cadena productiva usa suscripción. El modo `Read` cíclico se conserva como
alternativa conmutable, para poder mostrar la comparación en la defensa.

**Fundamento.** Sparkplug B publica por excepción (`DATA` sólo ante cambio de valor). Si la capa
OPC UA hiciera *polling*, el Edge Node tendría que filtrar cambios por su cuenta y la latencia se
sumaría dos veces. Usar suscripción hace que el modelo *report by exception* sea coherente de punta
a punta, y permite citar la medición de tramas y bytes ya realizada en la Tarea Nº2.

**Evidencia ya disponible (F0).** Con el servidor y el cliente reales en loopback, normalizado a
60 s: con la señal quieta la suscripción usa **126 mensajes / 10 954 B** contra **1109 / 150 695 B**
del Read cada 100 ms; con la señal cambiando cada 50 ms la diferencia casi desaparece (1107 frente a
1113 mensajes). Fuente: `tarea-2/versiones/v3-node-red/docs/protocolo-opcua.md` §7.3. **Es medición
en PC**: se cita como tal y se repite en banco en la T3. Las E/S del dispositivo 1 cambian por
acción humana, que es el caso donde la suscripción gana.

**Consecuencias.** Hay que documentar `SamplingInterval`, `PublishingInterval` y `QueueSize`, y
explicar el mecanismo `PublishRequest`/`PublishResponse` con sus `KeepAlive`. Se heredan los valores
de la T2 v2: 100 ms / 100 ms / 1, KeepAlive 10, Lifetime 300.

---

## ADR-005 — Broker MQTT gestionado en la nube

**Contexto.** I-03 prohíbe un broker local. Hay que elegir servicio.

**Opciones.**

| Opción | A favor | En contra |
|---|---|---|
| **HiveMQ Cloud Serverless** | Gratuito y sin tarjeta; TLS en 8883 y WebSockets seguros en 8884; reglas de autorización por tópico; 100 conexiones y 10 GB mensuales, holgadísimo para este TP | Puerto WSS fijo en 8884, no configurable; sin SLA |
| **EMQX Cloud Serverless** | Capa gratuita, TLS y WSS, panel de métricas detallado | Límites por cuota de sesiones/tráfico que conviene revisar |
| **Mosquitto en VPS propio** | Control total, certificados propios, ACL por archivo, se puede mostrar la configuración en el informe | Hay que administrarlo, exponerlo y asegurarlo; más superficie de ataque y más trabajo |

**Decisión.** HiveMQ Cloud Serverless como opción principal; EMQX Serverless como respaldo
contrastado y documentado. Si el grupo quiere maximizar la nota en la discusión de seguridad, el
VPS con Mosquitto permite mostrar `acl_file` y certificados propios: es la opción más vistosa y la
más cara en tiempo.

**Fundamento.** Cumple los cuatro requisitos del enunciado (MQTT 3.1.1/5.0, Last Will, retenidos y
WebSockets) sin costo, y la autorización por tópico permite demostrar privilegio mínimo real, no
declarado.

**Consecuencias y nota de seguridad importante.** Las credenciales MQTT de la página web **viajan
en el JavaScript del navegador y son públicas de hecho**. Mitigación obligatoria, y excelente
material de informe: crear **tres usuarios distintos** con permisos por tópico diferenciados.

| Usuario | Publica en | Se suscribe a |
|---|---|---|
| `edge_node` | `spBv1.0/UNRaf_PdCI_2026/N*/EN01_Gateway` y `.../D*/EN01_Gateway/#` | `spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway`, `.../DCMD/#`, `spBv1.0/STATE/#` |
| `host_app` | `spBv1.0/STATE/HA01_WebDashboard`, `.../NCMD/EN01_Gateway`, `.../DCMD/#` | `spBv1.0/UNRaf_PdCI_2026/#` |
| `observador` | nada | `spBv1.0/#` (sólo lectura, para MQTT Explorer) |

Discutir en el informe, con referencia a IEC 62443, por qué la alternativa correcta en producción
sería un backend intermedio que custodie las credenciales y emita tokens de corta vida, y por qué
en un TP de laboratorio el usuario restringido es una mitigación proporcional al riesgo.

---

## ADR-006 — Las métricas de estado son del Edge Node, no del Device

**Decisión.** `Status/MODBUS/*`, `Status/OPCUA/*`, `Status/MQTT/*` y `Status/Sparkplug/*` se
publican en `NBIRTH`/`NDATA`.

**Fundamento.** Si fueran métricas del Device, un `DDEATH` —que es justamente lo que ocurre cuando
el esclavo Modbus deja de responder— marcaría toda esa información como obsoleta en el momento
exacto en que el operador la necesita para diagnosticar. La consigna lo pide de forma expresa y la
razón de ingeniería es sólida: **el diagnóstico de un enlace no puede depender de que el enlace
funcione.**

---

## ADR-007 — El ESP32 #2 se usa como simulador del esclavo desconocido

**Contexto.** I-04 exige configurar el maestro en vivo para un esclavo que trae la cátedra. Es el
riesgo más alto del día de la defensa y no se puede ensayar contra el esclavo real.

**Decisión.** El segundo ESP32 se programa con el mismo firmware pero con un `slaveId`, un baud
rate, una paridad y un mapa de registros **deliberadamente distintos**, desconocidos para quien
opere el maestro durante el ensayo.

**Fundamento.** Convierte un requisito incierto en un caso de prueba repetible. Un integrante
configura el simulador y no se lo dice a los demás; los otros dos deben descubrir los parámetros y
establecer la comunicación contra reloj. Se ensaya hasta bajar el tiempo a menos de tres minutos.

**Consecuencias.** El Dashboard debe incluir un asistente de descubrimiento: barrido de IDs
1–247 con FC 03 y detección de respuesta, y prueba de las combinaciones habituales de baud rate y
paridad. Esto no lo pide la consigna, y es exactamente el tipo de agregado que distingue un trabajo
de nota alta.

---

## ADR-008 — Node-RED Dashboard como HMI de configuración, no como entrega final

**Decisión.** El Dashboard de Node-RED es la herramienta de ingeniería y puesta en marcha
(configuración del maestro, estadísticas crudas, trazas de tramas). La **página web Sparkplug es la
interfaz de usuario entregable** exigida por la consigna. No se confunden ni se sustituyen.

**Fundamento.** Separa el rol de operador de planta del rol de técnico de puesta en marcha, que es
la separación real en una instalación industrial. También evita la tentación de resolver la
consigna 3 con el Dashboard, lo que dejaría a la Host Application sin su razón de ser.

---

## ADR-009 — Seguridad por capas y su declaración explícita

**Decisión y objetivos de cumplimiento mínimos:**

| Capa | Mecanismo | Qué documentar |
|---|---|---|
| Modbus RTU | Ninguno por diseño: sin autenticación, sin cifrado, sin integridad criptográfica (el CRC detecta errores de transmisión, no manipulación) | Controles compensatorios: segmentación física del bus, acceso físico restringido, el borde como punto único de cruce OT/IT |
| OPC UA | `SecurityMode = SignAndEncrypt`, política `Basic256Sha256`, certificados X.509 de aplicación y lista de confianza (auto-aceptación **desactivada**), más autenticación de usuario con hash scrypt | Comparar con `None` y con `Sign`. **Corrección F0:** la T2 solo tiene captura de banco en `None` (informe T2 §9); `Sign` y `SignAndEncrypt` existen como vectores en PC (`v3-node-red/herramientas/vectores/sesion_Sign*.json`) y la tabla de campos legibles está verificada sobre ellos (`v3-node-red/docs/seguridad.md` §4). Latencia por modo: **nunca medida**, se mide en la T3 |
| MQTT | TLS 1.2 o superior, usuario y contraseña, autorización por tópico, tres usuarios con privilegio mínimo | Tabla de permisos del ADR-005 y análisis del riesgo de credenciales en el navegador |
| Sparkplug B | No aporta seguridad propia: hereda la de MQTT | Señalarlo explícitamente; es una pregunta probable del tribunal |

**Fundamento.** La consigna pide "conocer y probar las ventajas y desventajas de los distintos
niveles de seguridad". Responderlo con una tabla de modos medidos, y no con una afirmación
genérica, es lo que separa una respuesta de examen de un informe de ingeniería.

---

## ADR-010 — Lenguaje del firmware del esclavo reescrito: MicroPython con Thonny *(Aceptado 2026-11-09)*

**Decisión (Francisco Bevilacqua, 2026-11-09):** opción 1, MicroPython en IDE Thonny. Se aplican las
dos salvaguardas de la recomendación y el disparador de reapertura (> 1 % de error a 19200 bps).

**Contexto.** ADR-002 obliga a reescribir la capa de protocolo del esclavo. `CLAUDE.md` §3 y §4 de la
T3 suponen C++/Arduino con PlatformIO, pero la T1 es MicroPython en Thonny, con `config.py`,
`perifericos.py` y `diagnostico.py` ya verificados (70 pruebas en PC, 750 ciclos en banco), y el
flujo de trabajo con Thonny está documentado como decisión (`tarea-1/firmware/README.md`). La
consigna dice *"El dispositivo 1 será el esclavo creado en la Tarea Nº1"*.

**Opciones.**

| | 1. MicroPython: reescribir solo el bloque E4 | 2. C++/Arduino con PlatformIO |
|---|---|---|
| Reuso de la T1 | `config.py`, HAL, diagnóstico, bloques E1-E3/E5/E6, diagramas | Solo el mapa y las decisiones; todo el código es nuevo |
| Continuidad con "el esclavo de la Tarea Nº1" | Alta: mismo firmware con otra capa de protocolo | Baja: es otro firmware |
| Pruebas sin hardware | CPython puro sobre la lógica del parser y el CRC (el patrón de la T1: `config.py` importable desde CPython) | `pio test -e native` (Unity) |
| Delimitación por silencio | `ticks_us()` + `uart.any()` en el intérprete; la T1 lo sostuvo a 9600 bps con 0,0 % | `micros()` o el timeout de RX del UART por hardware; holgado a 19200 y más |
| Velocidad del esclavo | ≈ 12,8 ms de cómputo por transacción medidos en la T1 | Submilisegundo esperado (*sin medir*) |
| Riesgo con el esclavo de prueba a 19200 8E1 (ADR-007) | t1,5 = 0,86 ms frente a pausas del GC: **riesgo real** (es el argumento por el que la T1 eligió 9600) | Bajo |
| Herramientas | Thonny (ya instalado y documentado) | PlatformIO nuevo para el grupo |
| Costo estimado | 1,5-2 días | 3-4 días, más la curva de PlatformIO |

**Recomendación.** Opción 1, con dos salvaguardas: (a) el esclavo de prueba (ESP32 #2) se configura a
9600 o 19200 bps, nunca más alto, y se mide su tasa de error antes de F5; (b) CRC por tabla de 256
entradas en el firmware (≈ 8 veces menos iteraciones) y bit a bit en las herramientas de la PC, con
los mismos vectores *golden* en ambos. Si la medición (a) supera 1 % de error a 19200 bps, se
reabre este ADR.

**Consecuencias.** Si se elige la opción 1, `CLAUDE.md` §3 y §4 de la T3 y el plan de pruebas N1.1
(`pio test -e native`) deben actualizarse: la carpeta `firmware/esclavo-modbus/` pasa a contener los
`.py` de MicroPython, y los tests nativos pasan a ser scripts CPython con exit code, como en la T1.
**Aplicado el 2026-11-09:** `CLAUDE.md` §3, §4 y §6, plan de pruebas N1.1 y matriz 1.a actualizados.

---

## ADR-011 — Servidor OPC UA del dispositivo 2 con `node-opcua` desde function nodes

**Contexto.** ADR-001 asumía el nodo OpcUa-Server de `node-red-contrib-opcua`. El spike (§1) leyó su
código (0.2.355): crea NodeIds `ns=1;s=…`, tipos UInt16/Boolean/String y modos
None/Sign/SignAndEncrypt, pero **no** puede crear EURange, compara **contraseñas en texto plano**
desde `users.json` y trae **auto-aceptación de certificados** activada por defecto. La T2 ya lo había
descartado por lo mismo (ADR-01 de la v3, I-03).

**Opciones.** 1. Nodo de la paleta, desactivando defaults inseguros y renunciando a EURange.
2. **`node-opcua` 2.160.0 desde function nodes**, reutilizando `servidor_opcua.js` de la T2 v3.
3. Servidor `asyncua` en Python en la misma Raspberry Pi con canal local a Node-RED (plan B del spike).

**Decisión.** Opción 2. Opción 3 como contingencia (disparador en `riesgos.md`, R-03).

**Fundamento.** Cumple los cuatro requisitos del modelo de información (NodeIds fijos, tipos,
AccessLevel, EURange) y los de seguridad (trust list, scrypt) con código **ya probado en la T2**
(15 pruebas de integración). Es la misma biblioteca que usa el nodo de la paleta (node-opcua 2.160.0):
no se agrega dependencia, se quita una capa. Mantiene un solo proceso, sin IPC. Y es coherente con lo
que el grupo ya defendió.

**Consecuencias.** Más código propio que explicar en la defensa (se compensa con la trazabilidad
bloque ↔ código). Los módulos en `functionGlobalContext` solo se cargan al arrancar Node-RED: un
cambio exige reiniciar el servicio. Costo estimado: 1 a 1,5 días-persona (opción 3: 2,5 a 3,5).

---

## ADR-012 — El maestro delimita las respuestas por longitud esperada, no por silencio t3,5

**Contexto.** `node-red-node-serialport` ofrece separación por silencio (`interbyte`), pero con
resolución de 1 ms, temporizador reiniciado por bloque y no por byte, y detrás de un conversor USB
que agrupa bytes durante 1-16 ms. t3,5 vale 4,01 ms a 9600 bps y 2,0 o 1,75 ms por encima
(spike §3).

**Opciones.** 1. Separación `interbyte` del nodo como delimitador. 2. Nodo `serial request`.
3. **Function node con máquina de estados que conoce la longitud de la respuesta** a partir del FC
y del `byte_count`, con timeout de respuesta propio.

**Decisión.** Opción 3. t3,5 se aplica solo como **cota inferior** del silencio antes de transmitir.

**Fundamento.** El maestro siempre sabe qué preguntó: la longitud de la respuesta es determinista
(5 + N para FC 01-04, 8 para FC 05/06, 5 para una excepción). Es la misma estrategia del cliente de
`umodbus` (`_uart_read` termina por `expected_len`). Una cota inferior es exactamente lo que
`setTimeout` garantiza. `serial request` se descarta porque comparte el temporizador con la
separación y entrega bytes parciales en el timeout.

**Consecuencias.** La detección de "trama no recomponible" (consigna §1.c) queda explícita: bytes
de más, Unit ID o FC distinto del pedido, o longitud incompleta al vencer el timeout. El esclavo, que
no sabe qué le van a pedir, **sí** delimita por silencio con resolución de microsegundos.

---

## ADR-013 — El cliente OPC UA del dispositivo 3 es la v2 de la Tarea Nº2, adaptada

**Contexto.** La consigna §2 exige *"Utilizar el OPC client creado en TP Nº2"*. Hay tres versiones;
la que se presentó es la v2 (Python, `asyncua` 2.1.0).

**Decisión.** Se parte de `cliente_base.py` + `cliente_suscripcion.py` de la v2. Se conservan sin
cambios C1 (conexión y seguridad), `Escritor` (C5) y `correr_hasta_falla`; se adaptan C3 (ítems desde
el diccionario) y C7 (estado OPC UA, `DDEATH`/`DBIRTH`); se descartan rampa, LED y GPIO
(analisis-t2.md §2.5). `cliente.py` (Modo A) queda como alternativa conmutable (ADR-004).

**Fundamento.** Requisito literal; además el código ya resuelve descubrimiento, seguridad,
reconexión y distinción entre rechazo y error de transporte, con 50 pruebas en PC.

**Consecuencias.** `comun.py` importa `gpiozero` a nivel de módulo: se parte en una parte sin GPIO.
El informe debe mostrar el *diff* respecto del original (matriz 2.2). `Status/OPCUA/Estado` lo
calcula este cliente: un servidor caído no puede publicar su propia caída. La pérdida de la sesión
OPC UA dispara `DDEATH` (consigna §4).

---

## ADR-014 — Reintento y ausencia sostenida heredados de la Tarea Nº1

**Contexto.** La T1 midió que una política de "3 fallos consecutivos" hacía parpadear los
indicadores a ≈ 1 Hz con tres nodos en el bus, y la reemplazó por 1 reintento + ausencia sostenida
de 2000 ms (informe T1 §9.4.4). En la T3 el equivalente del parpadeo es un **ciclo DDEATH/DBIRTH**,
mucho más caro: cada uno es un mensaje MQTT a internet y un repoblado de la web.

**Decisión.** Cada transacción admite 1 reintento (idempotente). `Status/MODBUS/Estado` refleja la
última transacción (puede pasar a `CRC ERROR` aislado), pero `DEVICE NOT REACHED` y `DDEATH` se
declaran solo tras **ausencia sostenida** (2000 ms por defecto, configurable).

**Fundamento.** Separar *evento* (un fallo, que se cuenta) de *estado* (el dispositivo no está, que
cambia el ciclo de vida). Es la lección medida de la T1 trasladada a la capa Sparkplug.

**Consecuencias.** La detección de la caída del esclavo tarda hasta ≈ 2,3 s (ausencia + un timeout).
Se documenta como latencia de detección en el plan de pruebas F-01.

---

## ADR-015 — El Write OPC UA se responde recién con el eco MODBus *(Propuesto, F1)*

**Contexto.** Un `DCMD` de la web termina en un `WriteRequest` OPC UA sobre `Outputs/*`, que el
dispositivo 2 traduce a FC 05/06. Hay que decidir cuándo responder el `WriteResponse`.

**Opciones.** 1. Responder `Good` apenas el valor entra en la cola del maestro. 2. **Responder cuando
llega el eco MODBus** (`Good`) o se agotan los reintentos (`BadCommunicationError`).

**Decisión.** Opción 2, con el setter asíncrono de `node-opcua`.

**Fundamento.** El `StatusCode` debe decir la verdad sobre el actuador, no sobre una cola: con la
opción 1 una orden a un esclavo caído devolvería `Good`. El peor caso cabe holgado en el
`TimeoutHint` de 4000 ms del cliente de la T2 (`cliente_base.py:39`): espera de la transacción en
curso (≤ 300 ms) + 2 intentos × 300 ms ≈ 0,9 s.

**Consecuencias.** La web no muestra el valor pedido sino el confirmado: el `DDATA` posterior al
sondeo de lectura (FC 01/03) es la confirmación visible. Se mide la latencia del camino de comando
(plan de pruebas E2E-03/04).

---

## ADR-016 — Dashboard 2.0 (`@flowfuse/node-red-dashboard`) y no el Dashboard original *(Aceptado, F3)*

**Contexto.** ADR-001 y ADR-008 suponen "Node-RED Dashboard" para la configuración en vivo (I-04).

**Opciones.** 1. `node-red-dashboard` 3.6.6 (AngularJS). 2. **`@flowfuse/node-red-dashboard` 1.33.0**
(Vue 3 + Vuetify). 3. `node-red-contrib-uibuilder`.

**Decisión.** Opción 2.

**Fundamento.** npm marca a `node-red-dashboard` como *"No longer maintained - please look at alternatives
such as @flowfuse/node-red-dashboard"* (consultado 2026-11-09), y AngularJS no recibe correcciones de
seguridad. La opción 2 es la sucesora recomendada por el proyecto Node-RED; uibuilder obliga a escribir
el front-end completo. Se fija la 1.33.0 (2026-10-06) y no la última (1.36.0, de hace 3 días).

**Consecuencias.** Los paneles complejos son `ui-template` en Vue. Se encontraron tres trampas del
parseo con el HTML del navegador (`<v-table>` con filas, etiquetas autocerradas y atributos camelCase),
que quedaron como regresión en `edge-nodered/test/flujos.test.js`.

---

## ADR-017 — Transporte TCP de desarrollo que emula el desajuste de línea *(Aceptado, F3)*

**Contexto.** El maestro debe probarse sin hardware (CLAUDE.md §6), pero en Windows no hay `socat`, y en
Linux un par de pty **ignora baud y paridad**: el asistente de descubrimiento "encontraría" al esclavo
en cualquier combinación y la prueba del criterio de salida no probaría nada.

**Decisión.** El maestro tiene un transporte compuesto: el puerto serie de `node-red-node-serialport`
(producción) o TCP contra el simulador (desarrollo), conmutables en vivo. Por TCP, al conectar se envía
`PDCI-LINEA <baud> <paridad> <bits> <parada>` y el simulador, si no coincide con la suya, se comporta
como un UART desajustado: recibe basura y no responde.

**Fundamento.** Hace reproducible y automatizable el ensayo de I-04 (ADR-007) en cualquier PC. El
simulador ejecuta el stack REAL del firmware, así que cada prueba es además cruzada maestro JS y
esclavo MicroPython.

**Consecuencias.** El camino serie de Node-RED (`serial in`/`out`/`control`) queda probado solo en banco
(R-16). `scripts/dev-serial.sh` cubre el camino serie en Linux, con la limitación de los pty documentada.

---

## ADR-018 — Descubrimiento en dos fases *(Aceptado, F3)*

**Contexto.** El barrido completo cuesta combinaciones x IDs x timeout = 12 x 247 x 60 ms = **178 s**:
no entra en la defensa, y el criterio de salida pide menos de 60 s.

**Decisión.** Fase 1: los Unit ID habituales (1-10, 17, 247) en **todas** las combinaciones
(12 x 12 x 60 ms = 8,6 s). Fase 2: el resto. Las combinaciones empiezan por 19200 8E1, el valor por
defecto que fija la norma (MODBus over Serial Line §2.5.1). Una respuesta de excepción también cuenta
como hallazgo: demuestra que hay un esclavo escuchando en esa configuración.

**Fundamento.** Medido contra el simulador: ID 17 a 19200 8E1 en **0,8 s**; ID 5 a 38400 8O1 (combinación
tardía) en **8,6 s**. El peor caso sigue siendo 178 s y el panel lo informa.

**Consecuencias.** Un esclavo con un ID atípico en una combinación tardía puede tardar más de 60 s;
mitigación: el panel permite acotar el rango de IDs y desmarcar combinaciones.

---

## Plantilla para ADRs nuevos

```markdown
## ADR-0NN — <decisión en una línea>
**Contexto.**
**Opciones.** 1. … 2. … 3. …
**Decisión.**
**Fundamento.** (principio de ingeniería + requisito de la consigna que lo obliga)
**Consecuencias.** (incluido lo que se pierde)
```
