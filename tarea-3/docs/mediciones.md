# Mediciones de la cadena completa (F7)

> **Dónde y cómo se midió.** Banco virtual en la PC (`tools/banco_virtual.js`), con todo el software
> del producto: el stack MODBus del firmware (en el simulador), Node-RED con el maestro y el servidor
> OPC UA (SignAndEncrypt + usuario), el Edge Node, un broker MQTT con TLS (amqtt local) y la Host
> Application en Chrome.
>
> **No son del banco real**:
> - el ESP32 y el bus RS-485 (los reemplaza el simulador por TCP, con la misma trama RTU);
> - el broker en la nube (la latencia de internet no está incluida).
>
> Los números de banco con hardware quedan **pendientes**, y se miden con este mismo procedimiento.
> Mediciones del 2026-11-12, sobre el commit `8ada48c` con los cambios de F7 (el commit que agrega
> este archivo). Generado por `tools/analizar_banco.py`.

## 1. Latencia extremo a extremo

### 1.1 Lectura: el pulsador cambia en el esclavo → se ve en la pantalla

Se cambia el pulsador del simulador por su entrada estándar (t₀) y se toma el instante en que la
página lo muestra (MutationObserver en Chrome). El instante intermedio sale del `timestamp` de la
métrica en el DDATA, que es el SourceTimestamp OPC UA, es decir, el momento en que el maestro leyó
el registro. Todos los relojes son de la misma PC, así que las restas son válidas. Entre muestras se
espera un tiempo aleatorio, para no quedar en fase con el ciclo de sondeo.

| Tramo | mín (ms) | mediana | p95 | máx | n |
|---|---|---|---|---|---|
| Campo → servidor OPC UA (espera del sondeo + transacción MODBus) | 49 | 201 | 291 | 315 | 40 |
| Servidor OPC UA → broker (muestreo + publicación de la suscripción + Edge Node + TLS) | 25 | 162 | 223 | 228 | 40 |
| Broker → pantalla (WebSocket + decodificación + dibujo) | 2 | 6 | 12 | 17 | 40 |
| Total | 201 | 360 | 464 | 526 | 40 |

**Lectura.** El cuello de botella son los dos muestreos periódicos y no la red:

- **Campo → OPC UA**, con datos medidos en `trafico-regimen.pcapng`:
  - El ciclo de sondeo real mide 262 ms (250 configurados más la sobrecarga). Esperar el FC 02
    siguiente cuesta ≈ 131 ms en promedio.
  - Cada transacción dura ≈ 31 ms. Las cuatro van seguidas, así que el bus está ocupado 124 de cada
    262 ms.
  - Se suma el refresco de entradas del simulador: cada 50 ms, y solo con el bus libre. En el ESP32
    real cumple ese papel el muestreo del pulsador del firmware.
  - El total da una mediana de ≈ 200 ms, que coincide con lo medido.
- **La suscripción OPC UA** (SamplingInterval y PublishingInterval de 100 ms, ADR-004) suma hasta 200 ms.
- La web aporta un orden de magnitud menos, gracias a que dibuja en el cuadro siguiente al mensaje.
  Antes lo hacía en un ciclo fijo de 250 ms; se corrigió en F7.

Para bajar la latencia habría que acortar el sondeo o la suscripción, a costa de más tráfico (§2).

### 1.2 Comando: clic en la web → LED del esclavo → confirmación en pantalla

| Tramo | mín (ms) | mediana | p95 | máx | n |
|---|---|---|---|---|---|
| Clic → el LED del esclavo cambia (DCMD → Write OPC UA → FC 05) | 19 | 36 | 60 | 69 | 30 |
| Clic → la web muestra CONFIRMADO (la lectura siguiente vuelve por DDATA) | 52 | 192 | 267 | 271 | 30 |

El comando llega rápido porque no espera ningún muestreo: es un Write que el maestro pone delante
de la cola de lecturas. La **confirmación** sí espera la lectura FC 01 siguiente y la publicación
OPC UA. La web solo marca CONFIRMADO cuando ve el valor real (ADR-015), y por eso tarda más.

## 2. Tráfico por capa: régimen y reposo

Hay dos ventanas de 60 s capturadas con `dumpcap` en el loopback:

- **Régimen**: el simulador en modo automático mueve el potenciómetro (rampa triangular de 20 s) y
  cambia el pulsador cada 3 s (`simuladores/esclavo_modbus_sim.py`, `actualizar_entradas`).
- **Reposo**: los valores quedan fijos.

En las columnas, *Carga* son los bytes de la aplicación (payload TCP) y *Ethernet* es lo mismo
encapsulado en Ethernet II + IPv4 + TCP con timestamps. Esto último se calcula con `trama_ethernet`
de la T2.

| Ventana | Capa | Tramas/s | Carga (B/s) | Ethernet (B/s) | Nota |
|---|---|---|---|---|---|
| regimen | MODBus RTU (TCP de desarrollo) | 30.2 | 219 | — (RS-485 en el producto) | 34 % del bus a 9600 bps |
| regimen | OPC UA (SignAndEncrypt) | 11.6 | 1974 | 3014 |  |
| regimen | MQTT/TLS Edge Node ↔ broker | 4.9 | 590 | 1035 |  |
| regimen | MQTT/WebSocket web ↔ broker | 9.7 | 196 | 1065 |  |
| reposo | MODBus RTU (TCP de desarrollo) | 30.6 | 222 | — (RS-485 en el producto) | 34 % del bus a 9600 bps |
| reposo | OPC UA (SignAndEncrypt) | 5.9 | 925 | 1454 |  |
| reposo | MQTT/TLS Edge Node ↔ broker | 1.1 | 94 | 197 |  |
| reposo | MQTT/WebSocket web ↔ broker | 2.1 | 34 | 219 |  |

Mensajes Sparkplug B por tipo (registro del observador), con tasa y tamaño mediano del payload Protobuf:

| Ventana | Mensajes |
|---|---|
| regimen | DDATA: 3.88/s (44 B) · NDATA: 0.95/s (27 B) |
| reposo | NDATA: 0.96/s (26 B) |

**Lectura**

- **MODBus no se entera del reposo**: el maestro sondea igual. Es el costo de un protocolo de
  sondeo frente a uno por excepción.
- **OPC UA y Sparkplug sí bajan en reposo**, pero no a cero. Los contadores `Status/MODBUS/OK`
  cambian con cada respuesta: en OPC UA viajan en cada PublishResponse, y en Sparkplug en un
  NDATA por segundo (ADR-021).
- **Hay además un piso fijo en OPC UA**: el watchdog del cliente asyncua lee `ServerState` una vez
  por segundo (T2), y se suman los KeepAlive de la suscripción.

## 3. Eficiencia de trama: una word, en las tres capas

Es la misma pregunta de la T2 (consigna 4.6), extendida a la T3: cuántos bytes útiles hay sobre los
bytes totales al transmitir **una word**. Se toma el comando `Outputs/LedPWM` (UInt16), porque es
el único dato que atraviesa las tres capas como un mensaje de un solo valor: DCMD → WriteRequest →
FC 06. Útiles = 2 bytes.

Todos los tamaños de mensaje están **medidos**: `eficiencia-*.pcapng` para MODBus, OPC UA y MQTT/TLS,
y el registro del observador para el payload Protobuf. El encapsulado Ethernet (preámbulo, cabeceras
con timestamps TCP, FCS e IFG) se calcula con `trama_ethernet` de la T2.

| Capa | Mensaje | Bytes del mensaje | Eficiencia | Bytes en el cable Ethernet | Eficiencia en el cable | Nota |
|---|---|---|---|---|---|---|
| MODBus RTU | FC 06 `01 06 00 00 00 0b c8 0d` | 8 | 25.0 % | — (RS-485: 115 bits con t3,5 = 11.98 ms) | 13.9 % de los bits | 9600 8N1 |
| OPC UA None | WriteRequest | 132 | 1.5 % | 222 | 0.90 % | respuesta 64 B |
| OPC UA SignAndEncrypt | WriteRequest (identificado por tamaño) | 176 | 1.1 % | 266 | 0.75 % | respuesta 112 B |
| Sparkplug B (MQTT) | DCMD: PUBLISH 85 B = 2 + 2 + tópico 59 + Protobuf 22 | 85 | 2.4 % | 175 | 1.14 % | sin TLS |
| Sparkplug B (MQTT/TLS 1.3) | el mismo PUBLISH en un registro TLS (medido, broker → Edge) | 109 | 1.8 % | 199 | 1.01 % | +22 B de TLS (cabecera 5, tipo 1, tag AEAD 16) +2 B de Packet Id (amqtt entrega con QoS 1) |

**Lectura**

- **MODBus RTU es la más eficiente en bytes** (25 %) **y la más lenta en el medio**
  (9600 bps).
- **OPC UA ocupa 16 veces más bytes** que MODBus para la misma word. El cifrado lo lleva
  a 22 veces, por la firma HMAC de 32 B y el relleno AES.
- **El DCMD Sparkplug está en el medio en tamaño**: lo que más pesa es el **tópico** (59 de
  85 B), no el Protobuf. Es la misma razón por la que Sparkplug 3.0 manda los DATA solo con
  alias: si cada métrica llevara su nombre (`Inputs/Potenciometro_pct`, 24 B), el payload pesaría tanto
  como el tópico.
- **En el cable Ethernet las tres variantes TCP quedan por debajo del 2 %.** La sobrecarga es fija
  por mensaje. Se amortiza agrupando valores: un DDATA con potenciómetro y porcentaje (ADR-021), o
  un PublishResponse con varias notificaciones.
- **Con SignAndEncrypt, el tamaño ya no revela el servicio**: el Write y el Read del watchdog miden
  igual. Es un efecto del relleno a bloques que también protege contra el análisis de tráfico.

## 4. Detección y recuperación de cada falla (plan de pruebas N4)

*Detección* se mide desde que se inyecta la falla hasta el primer síntoma en la capa que
corresponde, visto por el observador o por la web. *Recuperación* se mide desde que se quita la
causa hasta que todo vuelve EN LÍNEA. Campaña del 2026-11-13, commit `8ada48c`.
El observador registró **0 violaciones** de `seq`/`bdSeq` en toda la campaña.

| ID | Falla | Resultado | Detección | Recuperación |
|---|---|---|---|---|
| F-01 | el esclavo no responde (simulador en silencio = sin alimentacion) | OK | 2.22 s · DDEATH seq=32 (web: dispositivo OBSOLETO) | 0.5 s · DBIRTH seq=36 a los 471 ms; web EN LÍNEA |
| F-02 | error de CRC (el simulador corrompe el CRC del 30 % de las respuestas) | OK | 2.52 s · NDATA Estado=CRC ERROR, CRC_ERROR=(otro NDATA) | 0.5 s · NDATA Estado=DONE (el contador CRC_ERROR queda como historico) |
| F-03 | Unit ID equivocado desde el Dashboard (1 -> 7) y correccion (7 -> 1) | OK | 1.56 s · DEVICE NOT REACHED -> DDEATH | 1.4 s · DBIRTH sin reiniciar nada |
| F-04 | cae el servidor OPC UA (se detiene Node-RED) | OK | 0.26 s · NDATA Status/OPCUA/Estado=ERROR + DDEATH; web: OPC UA en ERROR, MODBUS SIN DATOS | 3.8 s · reconexion del cliente con retroceso, OPC UA DONE, DBIRTH |
| F-05 | cae el Edge Node (kill del proceso) | OK | 0.24 s · NDEATH del broker (Will), bdSeq=0, coincide=true | 0.8 s · NBIRTH seq=0 bdSeq=1, DBIRTH, web EN LINEA |
| F-06 | se corta internet en el dispositivo 3 (corte silencioso en el proxy) | OK | 17.86 s · NDEATH por keepalive del broker a los 17861 ms (esperado ~15 s) | 3.1 s · NBIRTH bdSeq=2 Reconexiones=1 |
| F-07 | mensajes perdidos (Edge de prueba que salta un seq) | OK | 0.18 s · la web detecto el salto y publico NCMD Rebirth | 0.0 s · NBIRTH seq=0 tras el NCMD (Rebirths=1) |
| F-08 | se cae la Host Application (se mata el navegador) | OK | 0.03 s · STATE offline (Will) retenido=false | 0.7 s · STATE online, Rebirth pedido al conectar, web EN LINEA |
| F-09 | credenciales MQTT invalidas en la web | OK | 0.54 s · semaforo MQTT: CREDENCIALES RECHAZADAS + aviso | — · sin recuperación automática: hay que corregir la causa |
| F-10 | esclavo desconocido (ID 17, 19200 8E1, otro mapa): descubrimiento desde el Dashboard | OK | 2.86 s · el maestro no comunica: DDEATH | 4.1 s · descubrimiento + Aplicar: Status/MODBUS/Estado=DONE con el esclavo nuevo, sin recompilar |

**Lectura de los tiempos**

- **F-01 y F-03 detectan en ≈ 2 s** por diseño: es la ausencia sostenida de 2000 ms (ADR-014). Un
  timeout aislado no mata al dispositivo.
- **F-06 detecta en ≈ 15-18 s**: es el keepalive MQTT (10 s × 1,5), el único mecanismo posible
  cuando un cable se corta sin FIN ni RST.
- **F-05 (kill) detecta en milisegundos**, porque el sistema operativo cierra el socket.
- **Los tiempos de recuperación incluyen el retroceso exponencial (ADR-023)**. Una caída larga puede
  tardar hasta 30 s más en recuperarse.

## 5. Resistencia: 30 minutos (plan de pruebas E2E-05)

La cadena completa funcionó con el simulador en modo automático. Se tomó una muestra de memoria
cada 30 s (59 muestras): working set del árbol de procesos y heap JS de la página. Commit
`8ada48c` con los cambios de F7.

| Proceso | Primer 20 % (MiB) | Último 20 % (MiB) | Diferencia | Máximo |
|---|---|---|---|---|
| broker | 43.8 | 28.0 | -15.8 | 44.2 |
| proxy | 25.7 | 16.0 | -9.7 | 25.9 |
| obs | 57.4 | 39.8 | -17.6 | 61.6 |
| sim | 19.3 | 13.1 | -6.2 | 19.5 |
| nodered | 186.0 | 171.5 | -14.5 | 297.4 |
| edge | 62.3 | 35.5 | -26.8 | 63.0 |
| chrome | 491.8 | 444.8 | -47.0 | 565.3 |
| web (heap JS) | 11.2 | 11.9 | +0.7 | 12.2 |

**Cómo leer la memoria.**

- En Windows, el *working set* lo recorta el propio sistema operativo cuando un proceso está
  estable. Por eso que baje **no** prueba que se liberó memoria.
- Lo que sí indica es que **ningún proceso crece de forma sostenida** en 30 minutos.
- El dato más limpio es el heap JS de la página, que lo mide el propio motor de JavaScript, sin
  intervención del sistema operativo. Varía menos de 1 MiB.
- Los picos de Node-RED son ciclos del recolector de basura, no una tendencia.
- Para afirmar que no hay fugas en el producto, hay que repetir la prueba en la Raspberry Pi midiendo
  RSS o PSS (`/proc/<pid>/smaps_rollup`). Queda **pendiente del banco**.

- **Mensajes Sparkplug**: DBIRTH 1, DDATA 7143, NBIRTH 2, NCMD 1, NDATA 1712, STATE 2.
- **`seq`**: dio **34 vueltas de 255 a 0**, con **0 violaciones**.
- **MODBus durante la prueba**: 28001 transacciones correctas; los errores crecieron en
  CRC_ERROR +0, TIMEOUT +0 y EXCEPTION +0.
  Los valores absolutos de la web son históricos, porque los contadores persisten entre reinicios y
  arrastran las campañas de fallas. El criterio E2E-05 es que no crezcan.
- **Sin NDEATH ni DDEATH** en toda la prueba: 0 y 0.
- **Rebirths pedidos por la web al final**: 1. Uno es el de la conexión inicial;
  uno más indicaría mensajes perdidos.
- **Registro de eventos de la web**: 7 entradas, acotado a 300 por diseño.
