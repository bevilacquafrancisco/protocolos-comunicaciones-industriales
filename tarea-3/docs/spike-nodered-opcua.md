# Spike técnico — Node-RED como maestro MODBus y servidor OPC UA (dispositivo 2)

Fase F0 · 2026-11-08 · Decide la arquitectura del dispositivo 2 (ADR-001, ADR-011, ADR-012).

**Método.** Se leyó el **código fuente** de cada paquete en su repositorio (rama `master`/`develop`
al 2026-11-08), no solo el README, y se contrastó con lo que la Tarea Nº2 ya había encontrado en el
código instalado. Las páginas de npm devolvieron HTTP 403: **las versiones publicadas en npm no se
pudieron confirmar**; se informa la versión del `package.json` del repositorio. Nada de lo que sigue
se ejecutó: es lectura de código. Lo que exige ejecución queda marcado *a verificar*.

---

## Veredicto en una tabla

| Pregunta | Resultado | Consecuencia |
|---|---|---|
| ¿`node-red-contrib-opcua` crea NodeIds `ns=1;s=…` fijos? | ✅ Sí | — |
| ¿Tipos UInt16, Boolean, String? | ✅ Sí | — |
| ¿AccessLevel por variable? | 🟨 Sí, por `msg.accessLevel`, formato no validado | A verificar |
| ¿Propiedad EURange? | ❌ **No existe en el código** | Requisito del diccionario sin cumplir |
| ¿Modos y políticas? | ✅ None / Sign / SignAndEncrypt con Basic128Rsa15, Basic256, Basic256Sha256 | — |
| ¿Usuarios? | ❌ **Contraseñas en texto plano** en `users.json`, comparación directa | Viola la regla de seguridad del repositorio y repite el hallazgo I-03 de la T2 |
| ¿Certificados de clientes? | ⚠ "Auto Accept Unknown Certificates" **activado por defecto** | Anula la trust list si no se desactiva |
| ¿`node-red-node-serialport` lee y escribe bytes crudos? | ✅ Sí (`bin`, `Buffer`) | — |
| ¿Delimitación por silencio t3,5? | ❌ **No es confiable**: resolución de ms, temporizador reiniciado por bloque y no por byte, latencia del conversor USB | El maestro delimita **por longitud esperada** (ADR-012) |
| ¿Reconfigurar el puerto en vivo (I-04)? | ✅ Nodo `serial control` | — |

**Decisión que se propone:** Node-RED se mantiene como dispositivo 2 (ADR-001 confirmado en lo
esencial), pero el servidor OPC UA **no** se arma con los nodos de la paleta: se implementa con
**`node-opcua` desde function nodes**, reutilizando `servidor_opcua.js` de la T2 v3 (plan A′).
El plan B pedido (asyncua en Python con canal local) es viable y se estima en §5, pero cuesta más.

---

## 1. `node-red-contrib-opcua` — nodo OpcUa-Server

Repositorio: `github.com/mikakaraila/node-red-contrib-opcua`. `package.json` de `master`:
versión **0.2.355** (`buildDate 2026-08-26`), dependencia **`node-opcua` 2.160.0** fija.
Archivos leídos: `opcua/104-opcuaserver.js`, `opcua/104-opcuaserver.html`, `opcua/utils.js`.

### 1.1 NodeIds de cadena fijos y namespace

- Comando: `msg.payload.opcuaCommand = "addVariable"` con
  `msg.topic = "ns=1;s=Dispositivo1.Inputs.Pulsador;datatype=Boolean"` (formato de la ayuda:
  `ns=1;s=VariableName;datatype=Double`).
- El NodeId se toma literal del tópico: `name = msg.topic.substring(0, e - 1)` → `nodeId: name`.
- Namespace: `addressSpace.getOwnNamespace()` con `nsindex=1` por defecto → **ns=1**. Existe
  `registerNamespace` para agregar otros.
- La carpeta padre es la última fijada con `addFolder`/`setFolder` (estado global del nodo): la
  jerarquía `Dispositivo1/Inputs/…` se arma con una **secuencia ordenada** de mensajes. Frágil
  ante un redeploy parcial.

### 1.2 Tipos

Comparación exacta de cadenas: `Int32, Int16, UInt32, UInt64, UInt16, Double, Float, Byte, SByte,
DateTime, ExtensionObject, ByteString, String, Boolean`. **UInt16, Boolean y String: sí.** Falta
**Int64** (no hace falta en OPC UA: `bdSeq` es solo de Sparkplug).

### 1.3 AccessLevel

```js
var accessLevel = opcua.makeAccessLevelFlag("CurrentRead | CurrentWrite"); // Use as default
if (msg.accessLevel) { accessLevel = msg.accessLevel; }
```

Por defecto **toda variable es escribible**. Se puede pasar `msg.accessLevel` y
`msg.userAccessLevel`, pero el valor llega sin conversión a `namespace.addVariable` y un `0` se
ignora (`if (msg.accessLevel)` es falso). *A verificar:* que el valor numérico de
`makeAccessLevelFlag("CurrentRead")` produzca `BadNotWritable` ante un Write.

### 1.4 EURange

Búsqueda en el archivo completo de `addAnalogItem`, `EURange`, `euRange`, `AnalogItem`: **sin
resultados**. Tampoco en el README ni en la ayuda. Solo hay alarmas (`installDiscreteAlarm`,
`installLimitAlarm`). → **No cumple** el diccionario §3 (`Potenciometro` EURange 0..4095,
`LedPWM` 0..255).

### 1.5 Seguridad

| Aspecto | Código | Evaluación |
|---|---|---|
| Modos | `MessageSecurityMode.None`, `.Sign`, `.SignAndEncrypt` | ✅ |
| Políticas | `SecurityPolicy.None`, `.Basic128Rsa15`, `.Basic256`, `.Basic256Sha256` | ✅ Basic256Sha256. Basic128Rsa15 y Basic256 están **deprecadas** por la OPC Foundation y vienen **habilitadas por defecto** en el editor: hay que desmarcarlas |
| Usuarios | `users.json` con `username`, `password`, `roles`; `if (users[uIndex].password !== password)` | ❌ **Texto plano** y comparación no constante. Es el mismo hallazgo de la T2 (`v3-node-red/evidencia/INCONVENIENTES.md` I-03) |
| Anónimo | `allowAnonymous` configurable, por defecto `true` | ✅ configurable |
| Certificados | PKI en `envPaths("node-red-opcua").config/ServerPKI`; `automaticallyAcceptUnknownCertificate` con valor por defecto **`true`** en el editor | ⚠ Con el valor por defecto, cualquier cliente con cualquier certificado es confiado: SignAndEncrypt cifra, pero no autentica a nadie |
| Espacio de demostración | `constructDefaultAddressSpace` por defecto `true` (crea `ns=1;s=VendorName`, `MyVariable2`, `FreeMemory`, `Counter`, método `Bark`) | ✅ se desactiva con la casilla "Build default AddressSpace" |

### 1.6 Conclusión sobre el nodo de la paleta

Cumple lo mínimo de NodeIds, tipos y modos. Falla en **EURange** y en **gestión de credenciales**,
y tiene dos valores por defecto inseguros. La T2 ya había descartado este nodo por el mismo motivo
y lo dejó escrito como ADR-01 de la v3: usarlo en la T3 sería **retroceder sobre una decisión
defendida** y abriría una pregunta incómoda en la defensa (*"¿por qué en la T2 lo descartaron por
inseguro y ahora lo usan?"*).

---

## 2. `node-red-node-serialport` — bytes crudos y separación de tramas

Repositorio: `github.com/node-red/node-red-nodes`, `io/serialport/`. `package.json`: versión
**2.0.3**, `serialport ^12.0.0`, Node-RED ≥ 3.0.0, Node ≥ 16. Archivos leídos: `25-serial.js`,
`25-serial.html`, `locales/en-US/25-serial.{html,json}`.

### 2.1 Bytes crudos

| Sentido | Cómo | Detalle |
|---|---|---|
| Lectura | Configuración `bin = "bin"` → `msg.payload` es `Buffer` | Con `"false"` hace `m.toString()` (UTF-8): **corrompe** bytes ≥ 0x80. Siempre `bin` |
| Escritura | `msg.payload` de tipo `Buffer` se escribe tal cual | Campo `addchar` **vacío** (si se pone `"false"` agrega el texto literal "false") |

### 2.2 Estrategias de separación (`out`)

| Opción | Código | ¿Sirve para MODBus RTU? |
|---|---|---|
| `char` — por carácter | Emite al ver `splitc[0]` | ❌ RTU no tiene delimitador; `0x0A` aparece dentro de los datos |
| `time` — "after a timeout of" | `setTimeout` que arranca **con el primer byte** (`spliton === "time" && i === 1`) | ❌ Es duración fija desde el inicio, no silencio |
| `interbyte` — "after a silence of" | `setTimeout` reiniciado cuando `z === d.length-1`, es decir **una vez por bloque `data`**, no por byte | 🟨 Se parece a t3,5, pero ver §3 |
| `count` — longitud fija | Emite al llegar a N bytes | 🟨 Sirve si se conoce la longitud; es fija por nodo |

Otros nodos: **`serial request`** (petición-respuesta con `responsetimeout`, 10 000 ms por defecto,
`msg.timeout`) — empareja respuestas por FIFO y **comparte el temporizador** con el de separación; en
*timeout* puede entregar bytes parciales. **`serial control`**: acepta en `msg.payload`
`serialport, serialbaud, databits, parity, stopbits, dtr, rts, cts, dsr, enabled` → cambia puerto y
parámetros **en vivo** (I-04 ✅). No cambia `bin`/`out`/`newline`.
Parámetros admitidos: paridad `none, even, odd, mark, space`; datos `5-8`; parada `1, 2`.

## 3. Resolución temporal y t3,5

### 3.1 Cálculo de t1,5 y t3,5

MODBus serie usa **11 bits por carácter** (1 inicio + 8 datos + paridad + 1 parada, o 2 de parada
sin paridad). Por encima de 19 200 bps la norma fija valores constantes (Modbus Organization, 2006,
*MODBUS over Serial Line V1.02*, §2.5.1.1; la misma regla está codificada en `umodbus`:
`if baudrate <= 19200 … else: self._inter_frame_delay = 1750`).

| Baud rate | t_carácter = 11 / baud | t1,5 | t3,5 | t3,5 con 8N1 real (10 bits) |
|---|---|---|---|---|
| 9600 | 1,146 ms | **1,719 ms** | **4,010 ms** | 3,646 ms |
| 19 200 | 0,573 ms | **0,859 ms** | **2,005 ms** | 1,823 ms |
| 115 200 | 0,095 ms | 0,143 ms → **fijo 0,750 ms** | 0,334 ms → **fijo 1,750 ms** | 1,750 ms (fijo) |

Corrección al diccionario: a 9600 bps el valor es **4,01 ms** (el diccionario decía "≈ 4,0"), y a
19 200 bps **2,005 ms**.

### 3.2 ¿Alcanza la resolución de Node-RED?

| Fuente de incertidumbre | Magnitud | Fuente |
|---|---|---|
| `setTimeout` de Node.js | Granularidad 1 ms; garantiza un **mínimo**, no un máximo; se atrasa con la carga del *event loop* | Documentación de Node.js (`timers`) |
| `interbyte` reinicia por bloque `data` | Un bloque puede traer la trama entera o una parte | `25-serial.js` |
| Agrupamiento del conversor USB-serie | 1 a 16 ms típico (temporizador de latencia del driver) | `tarea-1/docs/protocolo-comunicacion.md` §4, punto 3. *A medir* en el adaptador real: `cat /sys/bus/usb-serial/devices/ttyUSB0/latency_timer` |
| Unidad mínima configurable en el nodo | 1 ms (entero en ms); "0" no está validado y el código no lo trata como caso especial | `25-serial.js` |

**Conclusión:** el *jitter* de la cadena (USB + *event loop*) es del **mismo orden o mayor** que t3,5
a 9600 bps (4 ms) y claramente mayor a 19 200 y 115 200 bps (≤ 2 ms). **Delimitar por silencio en
el maestro de Node-RED no es confiable a ningún baud rate de la tabla.**

### 3.3 Estrategia que sí funciona (ADR-012)

El **maestro** no necesita detectar t3,5 para delimitar: **sabe cuántos bytes debe recibir**, porque
él mismo hizo la pregunta. Es lo que hace `umodbus` en su `_uart_read()` del lado cliente
(`expected_len = RESPONSE_HDR_LENGTH + 1 + response[2] + CRC_LENGTH`).

| Respuesta esperada | Longitud |
|---|---|
| FC 01/02/03/04 normal | 3 + `byte_count` (byte 3) + 2 = 5 + N |
| FC 05/06 normal (eco) | 8 |
| Excepción (FC con bit 7 en 1) | 5 |

Algoritmo (function node, máquina de estados):

1. Nodo serie en `bin`, separación `interbyte` con 1-2 ms (solo para no recibir byte a byte; la
   delimitación real no depende de ese valor).
2. El function node acumula bloques en un buffer y, apenas tiene 2 bytes, calcula la longitud
   esperada (3 si necesita `byte_count`).
3. Completa la longitud → verifica CRC propio → `OK` o `CRC_ERROR`.
4. Vence el **timeout de respuesta** (configurable, 50-3000 ms; en la T1, 300 ms) → `TIMEOUT`.
5. Llegan bytes de más, o un Unit ID / FC distinto del pedido → descarta y cuenta como trama no
   recomponible (consigna §1.c: *"no se pudo recomponer la trama"*) → `CRC_ERROR` con subcausa.
6. **t3,5 como cota inferior al transmitir:** antes de la próxima petición se espera
   `ceil(t3,5) + 1 ms` después de la última respuesta. Como `setTimeout` solo puede atrasarse,
   **una cota inferior siempre se cumple**: la tolerancia del temporizador juega a favor.

El **esclavo** (ESP32) sí debe delimitar por silencio, porque recibe peticiones que no sabe de
antemano. Ahí la resolución es de microsegundos (`time.ticks_us()` en MicroPython; el ESP32 además
tiene timeout de RX por hardware) y la T1 ya lo sostuvo a 9600 bps con 0,0 % de error.

**Control de dirección del lado maestro:** el adaptador USB-RS485 debe conmutar DE/RE
**automáticamente** (la Raspberry Pi no tiene GPIO de DE en este esquema). *A verificar* con el
modelo concreto (R-04).

---

## 4. Plan A′ (recomendado): `node-opcua` desde function nodes

Reutiliza `tarea-2/versiones/v3-node-red/node-red/servidor/servidor_opcua.js` (342 líneas) y
`comun/credenciales.js`, ya escritos y probados en la PC (15 pruebas de integración de la T2 v3).

| Requisito | Cómo lo cubre `servidor_opcua.js` | Línea |
|---|---|---|
| NodeIds fijos en ns=1 | `nodeId('…')` con el namespace propio | 194-230 |
| Boolean / UInt16 | `dataType: 'Boolean'`, `'UInt16'` | 211, 217 |
| AccessLevel por variable | `makeAccessLevelFlag('CurrentRead')` / `'CurrentRead | CurrentWrite'` | 183-184 |
| EURange | Variables de tipo AnalogItem con `config.opcua.euRange` | 159-164, 206 |
| Modos y políticas | `securityPolicies` / `securityModes` desde `config.js` | 101-102 |
| Anónimo configurable | `allowAnonymous: config.seguridad.permitirAnonimo` | 103 |
| Trust list | `automaticallyAcceptUnknownCertificate` desde `config.js` | 280 |
| Usuario con hash scrypt | `comun/credenciales.js` | — |

**Costo estimado:** 1 a 1,5 días-persona: cambiar el modelo (de 4 variables de la T2 a las ~12 del
diccionario, generadas desde una tabla), agregar String/UInt32, y conectar los Write entrantes con la
cola de escritura del maestro MODBus. Requiere `functionGlobalContext` en `settings.js` y reiniciar
Node-RED ante cambios del módulo (lección de la T2).

**Se gana:** un solo proceso en la Raspberry Pi, cero IPC, decisión coherente con la T2, código ya
defendible. **Se pierde:** no se "arrastra" el servidor desde la paleta; hay más código propio que
explicar.

## 5. Plan B (pedido): servidor OPC UA en Python (`asyncua`) + Node-RED por canal local

```
ESP32 ──RS-485──► Node-RED (maestro MODBus, HMI) ──127.0.0.1──► Python asyncua (servidor OPC UA :4840) ──► dispositivo 3
```

| Ítem | Detalle | Estimación |
|---|---|---|
| Servidor | Reutiliza `tarea-2/versiones/v2-correccion-python/servidor.py` (448 líneas: EURange, 3 endpoints, scrypt, trust list, roles). Quitar GPIO y rampas; modelo desde el diccionario | 0,5-1 día |
| Canal local | TCP en `127.0.0.1` con JSON por línea (nodos `tcp in`/`tcp out` de Node-RED; `asyncio.start_server` en Python). Descartado MQTT local: confunde con I-03 en la defensa | 0,5 día |
| Contrato del canal | Mensajes `valor`, `estado`, `write`, `ack`; versionado; reconexión en ambos lados | 0,5 día |
| Operación | Segundo servicio `systemd`, orden de arranque, logs separados | 0,5 día |
| Pruebas | Integración Node-RED ↔ Python ↔ cliente en loopback | 0,5-1 día |
| **Total** | | **2,5-3,5 días-persona** |

**Riesgos propios del plan B:** un punto de falla más (si el puente se cae, el servidor OPC UA
publica datos viejos con `StatusCode` Good, salvo que se marque `BadCommunicationError`
explícitamente); latencia del puente < 1 ms en loopback (despreciable frente a 100 ms de
PublishingInterval, *a medir*); la consigna §8 pide diagramas de flujo del servidor: habría dos.

**Cuándo pasar al plan B:** si `node-opcua` 2.160.0 no instala o no corre en el sistema operativo de
la Raspberry Pi del laboratorio (la T2 v3 necesitó Bookworm Legacy por `pigpio`, no por `node-opcua`),
o si la prueba de integración del plan A′ no cierra en F4.

## 6. Qué queda a verificar con ejecución (antes de F3)

| # | Verificación | Cómo |
|---|---|---|
| V-1 | `node-opcua` 2.160.0 instala en la Raspberry Pi del laboratorio | `npm i node-opcua@2.160.0` en la placa (o imagen igual) |
| V-2 | Delimitación por longitud con `serial in` en `bin` + `interbyte` 1 ms | `socat` + `simuladores/esclavo_modbus_sim.py`, 10 000 transacciones, 0 tramas mal delimitadas |
| V-3 | Cota inferior de t3,5 al transmitir | Sniffer RS-485 de la T1 midiendo el silencio entre respuesta y petición siguiente |
| V-4 | Latencia del adaptador USB-RS485 y conmutación automática de dirección | `latency_timer`, prueba de eco, osciloscopio si hay |
| V-5 | `serial control` cambia baud y paridad sin reiniciar Node-RED | Flow de prueba con dos preajustes |

## Referencias

- Modbus Organization. (2006). *MODBUS over serial line specification and implementation guide V1.02*. https://www.modbus.org
- Karaila, M. (2026). *node-red-contrib-opcua* (versión 0.2.355) [Software]. GitHub. https://github.com/mikakaraila/node-red-contrib-opcua
- OpenJS Foundation. (2026). *node-red-node-serialport* (versión 2.0.3) [Software]. GitHub. https://github.com/node-red/node-red-nodes/tree/master/io/serialport
- brainelectronics. (2023). *micropython-modbus* (versión 2.3.7) [Software]. GitHub. https://github.com/brainelectronics/micropython-modbus
- Bevilacqua, F., y Peralta, A. (2026). *Tarea Nº2 — OPC UA*, `evidencia/INCONVENIENTES.md` I-03 y `docs/arquitectura-red.md` ADR-01 (v3). Repositorio del grupo.
