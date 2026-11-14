# Capturas: índice y pies de figura

Cada figura dice **qué se ve**, **dónde está el dato** y **de dónde sale**.

Salvo que se indique otra cosa, todo es del **banco virtual en la PC**: la cadena completa con el
software del producto, el simulador del esclavo en lugar del ESP32 y un broker MQTT local con TLS en
lugar del de la nube (`tools/banco_virtual.js`, ver `docs/mediciones.md`). Lo que necesita hardware
o la nube figura como **pendiente** al final.

## 1. Host Application: estados de cada capa (F7, `f7/`)

| Archivo | Pie de figura |
|---|---|
| `f7/web-modbus-done-opcua-done.png` | **Figura 1. Operación normal.** Las cuatro capas en ✔ verde: MODBUS DONE con sus cuatro contadores, OPC UA DONE, MQTT CONECTADO y SPARKPLUG NODO EN LÍNEA. El estado se lee por el ícono y el texto, no solo por el color. El dispositivo 1 está EN LÍNEA y cada valor indica su antigüedad ("hace 0 s"). |
| `f7/web-modbus-crc-error.png` | **Figura 2. MODBUS = CRC ERROR (F-02).** El simulador corrompe el CRC del 30 % de las respuestas. La tarjeta MODBUS pasa a ▲ amarillo con el contador `CRC_ERROR` en aumento. El dispositivo sigue **EN LÍNEA**, porque un error de CRC no es ausencia y el sondeo continúa (ADR-014). |
| `f7/web-modbus-device-not-reached.png` | **Figura 3. MODBUS = DEVICE NOT REACHED (F-01).** El esclavo no responde. Después de 2 s de ausencia sostenida, la tarjeta MODBUS pasa a ✖ rojo y llega un DDEATH. El dispositivo queda OBSOLETO, con los últimos valores **tachados**, y el registro de eventos muestra el DDEATH con su `seq`. |
| `f7/web-opcua-error.png` | **Figura 4. OPC UA = ERROR (F-04).** Se detuvo Node-RED. La tarjeta OPC UA está en ✖ ERROR. La de MODBUS dice **"SIN DATOS (OPC UA en ERROR)"** y no el último DONE: la falla se informa en la capa donde ocurrió, y la capa de abajo, como desconocida (corrección de F7). |
| `f7/web-opcua-done-recuperado.png` | **Figura 5. OPC UA = DONE otra vez.** El cliente reconectó solo, con retroceso exponencial, después de reiniciar Node-RED. Llegó un DBIRTH nuevo y todo volvió a EN LÍNEA sin tocar la web. |
| `f7/web-ndeath-nodo-obsoleto.png` | **Figura 6. NDEATH (F-05).** Se mató el proceso del Edge Node. El **broker** publicó el Will. SPARKPLUG pasa a ✖ NODO OBSOLETO y todas las métricas quedan tachadas. El registro muestra `NDEATH bdSeq=N`. |
| `f7/web-recuperacion-1-corte.png` | **Figura 7a. Recuperación tras un corte, momento 1 (F-06).** Corte silencioso de la red del dispositivo 3. A los ≈ 18 s el broker detectó la pérdida por keepalive y publicó el NDEATH. SPARKPLUG ✖ NODO OBSOLETO; MODBUS y OPC UA figuran como "DONE (OBSOLETO)": ya no se sabe nada de esas capas. |
| `f7/web-recuperacion-2-restablecido.png` | **Figura 7b. Recuperación tras un corte, momento 2.** Volvió la red. Sin intervención: `bdSeq` 2 (antes 1), **Reconexiones Edge = 1**, NBIRTH con `seq` = 0 y DBIRTH. El registro muestra la secuencia completa NDEATH → NBIRTH → DBIRTH (invariante I-10). |
| `f7/web-rebirth-por-salto-de-seq.png` | **Figura 8. Salto de `seq` (F-07).** Un Edge de prueba omitió un `seq`. La web lo detecta y lo avisa en el banner con el dato exacto: "Salto de seq: esperado 31, llegó 32 → NCMD Rebirth solicitado (#2)". El #1 es el pedido normal que la web hizo al conectarse, contra el Edge real. El contador "Rebirths pedidos (web)" queda en 2. "Rebirths (Edge)" vale 1 porque el Edge de prueba cuenta solo el suyo, y ya llega contado en su NBIRTH. El registro muestra NBIRTH `seq`=0 y DBIRTH `seq`=1. |
| `f7/web-credenciales-rechazadas.png` | **Figura 9. Credenciales inválidas (F-09).** La tarjeta MQTT dice ✖ **CREDENCIALES RECHAZADAS** y el banner explica qué revisar. No es un fallo silencioso. Las demás capas figuran DESCONOCIDAS porque, sin conexión, nunca llegó un BIRTH. |
| `f7/web-resistencia-30min.png` | **Figura 10. Después de 30 minutos (E2E-05).** Las cuatro capas siguen en ✔. El registro de eventos no tiene entradas nuevas desde el arranque: ninguna caída ni Rebirth. Los contadores de error que se ven (TIMEOUT 2411, CRC_ERROR 63) son **históricos**, porque persisten entre reinicios; durante la prueba crecieron en **+0**, sobre 28 001 transacciones correctas (`mediciones.md` §5). |
| `hmi-escritorio.png`, `hmi-celular.png`, `hmi-ddeath.png` | **Figuras 11 a 13 (F6).** La misma pantalla en un proyector (1366 × 900) y en un celular (390 px, una columna, sin desplazamiento horizontal). La última muestra el dispositivo OBSOLETO tras un DDEATH. |

## 2. Sparkplug B (F5 y F7)

| Archivo | Pie de figura |
|---|---|
| `f7/sparkplug-mensajes-decodificados.md` | **Tabla 1. Un mensaje real de cada tipo**: NBIRTH, DBIRTH, NDATA, DDATA, NCMD, DCMD, DDEATH, NDEATH y STATE, con tópico, `seq`, `timestamp` y métricas (nombre, alias, tipo, valor). Incluye el **volcado hexadecimal de un DDATA campo por campo**, con clave Protobuf, tipo de cable y valor; ahí se ve el varint de `int_value` y el float little-endian. |
| `f7/sparkplug-medicion-observador.jsonl`, `f7/sparkplug-fallas-observador.jsonl` | Registro completo del observador en las dos corridas: cada mensaje con sus bytes crudos (`hex`) y su decodificación. **0 violaciones** de `seq` y `bdSeq`. |
| `sparkplug-pc-observador.jsonl`, `sparkplug-pc-edge-node.jsonl` | Sesión de F5 contra Node-RED y OPC UA reales. `seq` dio 3 vueltas de 255 a 0, hubo 8 DCMD hasta el LED y un NDEATH al matar el proceso. |

## 3. OPC UA (F4 y F7)

| Archivo | Pie de figura |
|---|---|
| `opcua-None.pcapng`, `opcua-Sign.pcapng`, `opcua-SignAndEncrypt.pcapng` | **Figura 14. Sesión OPC UA completa en los tres modos**, de HEL a CLO, con filtro `opcua` en Wireshark. En **None** se leen los NodeIds y el nombre de usuario. En **Sign** también se leen, pero el mensaje va firmado. En **SignAndEncrypt** no se lee nada. En ninguno aparece la contraseña. El detalle está en `docs/seguridad-opcua.md` §6. |
| `f7/eficiencia-None.pcapng`, `f7/eficiencia-SignAndEncrypt.pcapng` | Sesión del **Edge Node** (asyncua) con suscripción y cinco WriteRequest de `LedPWM`. En None, el WriteRequest mide 132 B. En SignAndEncrypt mide 176 B y ya no se distingue del Read del watchdog: el relleno AES oculta el servicio. Es la base de la tabla de eficiencia de `docs/mediciones.md` §3. |
| `panel-lista-confianza.png` | **Figura 15.** Lista de confianza del servidor OPC UA en el Dashboard: certificados de cliente con su huella SHA-1 y los botones Confiar y Revocar en vivo (F4). |

## 4. MODBus RTU (F7)

| Archivo | Pie de figura |
|---|---|
| `f7/modbus-tramas-decodificadas.md` | **Tabla 2. Una petición y su respuesta por cada función usada** (FC 01, 02, 03, 04 y la escritura FC 06 con su eco), **byte a byte**: dirección, función, dirección y cantidad en big-endian, datos, y CRC-16 en little-endian recalculado y verificado. Lo genera el decodificador de la T1. Son los bytes exactos que van al RS-485, capturados en el transporte TCP de desarrollo, **sin** la temporización de línea. |
| `f7/modbus-rtu-tcpdev.pcapng` | Los 5 s de captura de los que salen esas tramas. |

## 5. Tráfico

| Archivo | Pie de figura |
|---|---|
| `f7/trafico-regimen.pcapng`, `f7/trafico-reposo.pcapng` | Ventanas de 60 s de las cuatro capas: MODBus en 5020, OPC UA en 4840, MQTT/TLS del Edge en 28893 y WebSocket de la web en 28884. Son la base de `docs/mediciones.md` §2. |
| `f7/medicion-resultados.json`, `f7/fallas-resultados.json` | Datos crudos de las mediciones: cada muestra de latencia y cada falla, con sus marcas de tiempo. |

## 6. Pendientes (necesitan hardware o la nube)

| Captura | Cómo se obtiene |
|---|---|
| **MQTT Explorer** con los 7 tipos de mensaje | Broker en la nube con el usuario `observador` suscripto a `spBv1.0/#` (P-2 del README del dispositivo 3) |
| **Sniffer del bus RS-485** con la temporización real | `tarea-1/herramientas/sniffer_rs485.py` en el bus del banco, en paralelo al maestro |
| **Wireshark OPC UA en `eth0`** entre la Raspberry Pi y el dispositivo 3 | Los mismos tres modos, en la red real (B-8 del README de `edge-nodered`) |
| La web con el ESP32 real y la nube | Las mismas figuras, con la cadena del banco (W-3) |
