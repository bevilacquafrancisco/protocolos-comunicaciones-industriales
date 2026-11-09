# Diccionario de datos — fuente única de verdad

> **Regla:** ninguna capa inventa nombres. Si una métrica cambia aquí, cambia en el firmware,
> en Node-RED, en el Edge Node y en la web, en ese orden, y se actualiza la matriz de trazabilidad.
> Esto materializa el invariante **I-06** (mismo nombre y tipo en las tres capas), que la consigna
> exige explícitamente en §1 y §2.

**Estado de verificación (F0, 2026-11-08).** Todo lo que estaba marcado *(confirmar con T1)* quedó
confirmado o corregido contra el código de la Tarea Nº1. Cada corrección cita su fuente; el análisis
completo está en [analisis-t1.md](analisis-t1.md) y [analisis-t2.md](analisis-t2.md).

| Corrección | Antes | Ahora | Fuente |
|---|---|---|---|
| Pin del pulsador | GPIO 4 | **GPIO 18** (GPIO 4 es DE/RE) | `tarea-1/firmware/comun/config.py:86, :92` |
| Pin del LED digital | GPIO 2 | **GPIO 19** (GPIO 2 es *strapping*, descartado en T1) | `config.py:99`; `tarea-1/docs/arquitectura.md` §8.1 |
| Pin del LED PWM | GPIO 5 | **GPIO 21** (GPIO 5 es *strapping*, descartado en T1) | `config.py:102`; `arquitectura.md` §8.2 |
| Enlace serie del dispositivo 1 | 19200 8E1 | **9600 8N1** (el maestro conserva 19200 8E1 como preajuste para el esclavo de la cátedra) | `config.py:37-55` |
| t3,5 a 9600 bps | ≈ 4,0 ms | **4,010 ms** (11 bits/carácter) | [spike-nodered-opcua.md](spike-nodered-opcua.md) §3.1 |
| Terminación y polarización | Obligatorias | **No instaladas** en la T1 (bus 15-40 cm < 1,5 m crítico); se instalan si el bus de la T3 supera ese largo | Informe T1 §5.5-5.6 |
| Adaptación RO → RX | "Verificar en el módulo" | **Divisor 2,2 kΩ / 3,3 kΩ + pull-up 680 Ω de RO a 5 V**, obligatorio | `tarea-1/evidencia/INCONVENIENTES.md` §4 |

---

## 1. Dispositivo 1 — mapa de E/S y cadena completa de nombres

| Señal física | Pin ESP32 (verificado) | Modbus: tabla y dirección | FC lectura / escritura | Tipo Modbus | NodeId OPC UA (`ns=1`) | Métrica Sparkplug B | Tipo Sparkplug |
|---|---|---|---|---|---|---|---|
| Pulsador | **GPIO 18**, pull-up interno, activo en bajo (el firmware entrega 1 = presionado) | Discrete Input `10001` → offset `0x0000` | FC 02 / — | bit | `s=Dispositivo1.Inputs.Pulsador` | `Inputs/Pulsador` | `Boolean` |
| Potenciómetro | **GPIO 34** (ADC1_CH6), atenuación 11 dB, promedio de 8 muestras | Input Register `30001` → offset `0x0000` | FC 04 / — | word 16 bits, 0–4095 | `s=Dispositivo1.Inputs.Potenciometro` | `Inputs/Potenciometro` | `UInt16` |
| LED digital | **GPIO 19**, 330 Ω a GND | Coil `00001` → offset `0x0000` | FC 01 / FC 05 | bit | `s=Dispositivo1.Outputs.LedDigital` | `Outputs/LedDigital` | `Boolean` |
| LED PWM | **GPIO 21**, 330 Ω a GND, 1000 Hz (`machine.PWM.duty_u16`) | Holding Register `40001` → offset `0x0000` | FC 03 / FC 06 | word 16 bits, rango útil 0–255 (el esclavo satura) | `s=Dispositivo1.Outputs.LedPWM` | `Outputs/LedPWM` | `UInt16` |
| *(derivada, ADR-003)* | — | — (no viaja por MODBus) | — | — | `s=Dispositivo1.Inputs.Potenciometro_pct` | `Inputs/Potenciometro_pct` | `Float` |

Interfaz RS-485 del dispositivo 1 (no son métricas, se documentan para el conexionado):
UART2 **TX = GPIO 17** → DI · **RX = GPIO 16** ← RO (vía divisor + pull-up) · **DE+RE = GPIO 4** ·
jumper de Unit ID en **GPIO 13** (abierto = 1, a GND = 2). Fuente: `config.py:60-112`.

**Justificaciones que deben aparecer en el informe:**

- **ADC1 y no ADC2.** En el ESP32, el ADC2 queda inutilizable mientras el radio Wi-Fi está activo,
  porque el driver de Wi-Fi se apropia del periférico. Aunque este TP no use Wi-Fi en el esclavo,
  elegir ADC1 (GPIO 32–39) evita un acoplamiento latente (T1, `arquitectura.md` §8.1).
- **Pines de *strapping* evitados.** GPIO 0, 2, 5, 12 y 15 definen el modo de arranque; un LED o un
  pulsador ahí puede impedir el booteo (T1, `arquitectura.md` §8.1).
- **Direccionamiento y el desfasaje de uno.** `10001`, `30001`, `00001` y `40001` son direcciones
  del *modelo de datos* de Modbus (notación Modicon de 5 dígitos). En la trama viaja el **offset**
  `0x0000`. Confundir ambos es el error clásico del protocolo (T1, `mapa-registros.md` §5).
- **Escalado del ADC.** El ADC del ESP32 es de 12 bits (0–4095) y no lineal en los extremos.
  Se transporta el valor **crudo** en el Input Register y el escalado ocurre en el borde
  (ADR-003; decisión ya defendida en T1, `mapa-registros.md` §7.1).
- **Endianness.** Modbus transmite cada word en *big-endian* (MSB primero) y el CRC en
  *little-endian*; OPC UA Binary es *little-endian* en todo. Ambos procesadores son
  *little-endian*. Es la pregunta 3 de la Tarea Nº1 (`protocolo-comunicacion.md` §8) y la T2 lo
  mostró sobre una trama real (`10965 = 0x2AD5` → `d5 2a` en OPC UA, `2a d5` en MODBus).

### 1.1 Esclavo de prueba (ESP32 #2, ADR-007)

Mismo firmware, distinto Unit ID, baud rate, paridad y **mapa de registros**. El mapa se declara en
`config.py` del esclavo de prueba, **nunca** en el maestro (I-04). Se define en F2 y no se comunica
a quien opere el maestro durante el ensayo.

---

## 2. Métricas de estado (se publican como métricas del **Edge Node**, no del Device)

Van en el nodo y no en el dispositivo para que **sigan disponibles cuando el esclavo Modbus no
responda** — si estuvieran en el Device, un `DDEATH` las dejaría obsoletas justo cuando más se
necesitan. Es un requisito literal de la consigna (T3, Requisitos Sparkplug B, "Estados de
comunicación").

| Métrica Sparkplug | Tipo | NodeId OPC UA (`ns=1`) | Valores / semántica |
|---|---|---|---|
| `bdSeq` | `Int64` | — (sólo capa Sparkplug) | Número de sesión; idéntico en `NBIRTH` y en el `NDEATH` registrado como Will |
| `Node Control/Rebirth` | `Boolean` | — | En `true` el nodo republica sus BIRTH |
| `Status/MODBUS/Estado` | `String` | `s=Status.MODBUS.Estado` | `DONE` \| `CRC ERROR` \| `DEVICE NOT REACHED` |
| `Status/MODBUS/OK` | `UInt32` | `s=Status.MODBUS.OK` | Peticiones respondidas y validadas |
| `Status/MODBUS/CRC_ERROR` | `UInt32` | `s=Status.MODBUS.CRC_ERROR` | Respuestas con CRC inválido **o trama no recomponible** (longitud, Unit ID o FC inesperados; consigna §1.c) |
| `Status/MODBUS/TIMEOUT` | `UInt32` | `s=Status.MODBUS.TIMEOUT` | Peticiones sin respuesta dentro del tiempo de espera |
| `Status/MODBUS/EXCEPTION` | `UInt32` | `s=Status.MODBUS.EXCEPTION` | Respuestas de excepción (FC con bit 7, códigos 01–04) — *añadido propio*: la T1 distingue timeout, excepción y CRC (`protocolo-comunicacion.md` §10.1) |
| `Status/OPCUA/Estado` | `String` | `s=Status.OPCUA.Estado` | `DONE` \| `ERROR` — lo **calcula el dispositivo 3** según el estado de su sesión y suscripción; el nodo del servidor solo informa que el servidor vive |
| `Status/MQTT/Reconexiones` | `UInt32` | — | Reconexiones del cliente MQTT del Edge Node |
| `Status/Sparkplug/Rebirths` | `UInt32` | — | Rebirths solicitados por la Host Application |

> Nota sobre `Status/OPCUA/Estado`: un servidor OPC UA caído no puede publicar su propia caída. El
> valor que ve la web es el que deduce el **cliente** (dispositivo 3): `ERROR` si el *watchdog* o la
> suscripción fallan (T2 v2, bloque C7), `DONE` con la sesión activa. El NodeId se conserva para que
> UaExpert lo muestre, pero la métrica Sparkplug **no** se lee de ese nodo.

**Diagnóstico adicional recomendado** (no exigido, pero vale mucho en la defensa y en el análisis
de tramas del informe):

| NodeId OPC UA | Tipo | Contenido |
|---|---|---|
| `ns=1;s=Status.MODBUS.UltimaTramaTx` | `String` | Última petición en hexadecimal, p. ej. `01 04 00 00 00 01 31 CA` (trama verificada con `tarea-1/herramientas/modbus_tramas.py`) |
| `ns=1;s=Status.MODBUS.UltimaTramaRx` | `String` | Última respuesta en hexadecimal |
| `ns=1;s=Status.MODBUS.LatenciaMs` | `UInt16` | Tiempo entre fin de transmisión y respuesta completa. **Incluye la latencia del conversor USB** (1-16 ms, T1 `protocolo-comunicacion.md` §4): documentarlo al citar el número |

---

## 3. Espacio de nombres OPC UA

- **URI del namespace:** `urn:unraf:pdci:t3`  → índice `ns=1`
  (la Tarea Nº2 usó `urn:unraf:pdci:t2` y forzó `ns=1` usando la URI como ApplicationUri,
  `tarea-2/versiones/v2-correccion-python/servidor.py:248-259`; se mantiene el patrón).
- **Endpoint:** `opc.tcp://<ip-raspberry>:4840` — IP literal, nunca nombre de host (T2, `comun.py:44-46`).
- **Jerarquía bajo `Objects`:**

```
Objects
└── Dispositivo1              (Object)
    ├── Inputs                (Object)
    │   ├── Pulsador          Boolean, AccessLevel = CurrentRead
    │   ├── Potenciometro     UInt16,  CurrentRead,  EURange 0..4095
    │   └── Potenciometro_pct Float,   CurrentRead,  EURange 0..100 (ADR-003)
    ├── Outputs               (Object)
    │   ├── LedDigital        Boolean, CurrentRead | CurrentWrite
    │   └── LedPWM            UInt16,  CurrentRead | CurrentWrite, EURange 0..255
    └── Status                (Object)
        ├── MODBUS            (Object) → Estado, OK, CRC_ERROR, TIMEOUT, EXCEPTION
        │                                (+ UltimaTramaTx, UltimaTramaRx, LatenciaMs)
        └── OPCUA             (Object) → Estado
```

- **EURange** como propiedad con NodeId fijo `<variable>.EURange` y BrowseName estándar en ns=0,
  como en la T2 (`servidor.py:225-241`). El nodo OpcUa-Server de la paleta **no** puede crearla:
  ver [spike-nodered-opcua.md](spike-nodered-opcua.md) §1.4.
- **Escrituras:** solo usuario autenticado; el anónimo lee, navega y se suscribe
  (T2, `servidor.py:125-147`). Un Write sobre `Inputs/*` debe devolver `BadNotWritable`.
- **Servicios usados** (documentar en el informe con sus parámetros):
  `GetEndpoints`, `OpenSecureChannel`, `CreateSession`, `ActivateSession`, `Browse`,
  `Read`, `Write`, `CreateSubscription`, `CreateMonitoredItems`, `Publish`, `CloseSession`.
- **Acceso a datos:** suscripción (`CreateSubscription` + `CreateMonitoredItems`) y no *polling*
  (ADR-004). Parámetros heredados de la T2 v2: PublishingInterval 100 ms, SamplingInterval 100 ms,
  QueueSize 1, MaxKeepAliveCount 10, LifetimeCount 300 (`cliente_suscripcion.py:32-41`). El
  `PublishingInterval` fija el peor caso de latencia de esta capa y debe medirse.

---

## 4. Espacio de nombres Sparkplug B

| Elemento | Valor propuesto | Justificación para el informe |
|---|---|---|
| `namespace` | `spBv1.0` | Fijo por especificación Sparkplug 3.0 (ISO/IEC 20237) |
| `group_id` | `UNRaf_PdCI_2026` | Agrupa el "sitio". En planta sería la planta o el área. Sin `/`, sin `+`, sin `#`, sin espacios |
| `edge_node_id` | `EN01_Gateway` | Identifica al dispositivo 3. Estable entre reinicios: un id volátil rompe la correlación `NBIRTH`/`NDEATH` |
| `device_id` | `DEV01_ESP32_Slave` | El esclavo Modbus publicado como Device de ese nodo |
| `host_id` | `HA01_WebDashboard` | Host Application (la página web) |

**Tópicos resultantes:**

```
spBv1.0/UNRaf_PdCI_2026/NBIRTH/EN01_Gateway
spBv1.0/UNRaf_PdCI_2026/NDATA/EN01_Gateway
spBv1.0/UNRaf_PdCI_2026/NDEATH/EN01_Gateway                     ← Last Will del Edge Node
spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway                       ← Rebirth desde la web
spBv1.0/UNRaf_PdCI_2026/DBIRTH/EN01_Gateway/DEV01_ESP32_Slave
spBv1.0/UNRaf_PdCI_2026/DDATA/EN01_Gateway/DEV01_ESP32_Slave
spBv1.0/UNRaf_PdCI_2026/DDEATH/EN01_Gateway/DEV01_ESP32_Slave
spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/DEV01_ESP32_Slave     ← comandos desde la web
spBv1.0/STATE/HA01_WebDashboard                                 ← retenido, JSON
```

(Corregido: la versión anterior tenía espacios dentro de los tópicos `NDATA /` y `NCMD  /`, que
MQTT trataría como parte del nombre.)

La Host Application se suscribe a `spBv1.0/UNRaf_PdCI_2026/#`.

**Cuándo se publica `DDEATH`.** Por cualquiera de dos causas, ambas literales de la consigna §4:
(a) el maestro declara `DEVICE NOT REACHED` por **ausencia sostenida** (criterio heredado de la T1:
2000 ms sin ninguna transacción exitosa, `config.py:262-274`; no por un fallo aislado), o (b) el
dispositivo 3 pierde la sesión OPC UA con el dispositivo 2.

**Regla de oro del ciclo de vida** (a explicar en la defensa): una métrica sólo es válida si llegó
en un BIRTH o si es un DATA posterior a un BIRTH de la misma sesión. Sin BIRTH previo, o con un
salto en `seq`, los datos son sospechosos y corresponde pedir Rebirth. Ese mecanismo es lo que
distingue Sparkplug B de "MQTT con JSON", y es el argumento central de la defensa.

---

## 5. Parámetros del enlace serie

### 5.1 Preajustes del maestro

| Preajuste | Baud | Formato | Unit ID | Uso | Fuente |
|---|---|---|---|---|---|
| **Dispositivo 1** (por defecto) | **9600** | **8N1** | 1 | El esclavo propio, tal como se defendió en la T1 | `config.py:37-55, :160` |
| Norma MODBus | 19200 | 8E1 | 1 | Primer intento contra el esclavo de la cátedra | MODBus over Serial Line V1.02: 19200 y paridad par son el valor por defecto obligatorio |
| Barrido | 9600, 19200, 38400, 57600, 115200 × N/E/O | 8 bits | 1…247 | Asistente de descubrimiento (ADR-007) | — |

### 5.2 Rangos configurables en runtime (I-04)

| Parámetro | Valor por defecto | Rango configurable en runtime (I-04) |
|---|---|---|
| Baud rate | 9600 | 1200 … 115200 |
| Bits de datos | 8 | 8 (RTU exige 8; 7 solo sirve para ASCII, no se ofrece) |
| Paridad | None (N) | None, Even, Odd |
| Bits de parada | 1 | 1, 2 |
| ID de esclavo | 1 | 1 … 247 |
| Tiempo de espera de respuesta | 300 ms | 50 … 3000 ms |
| Período de sondeo | 250 ms | 100 … 5000 ms |
| Reintentos por transacción | 1 | 0 … 10 |
| Ausencia sostenida antes de `DEVICE NOT REACHED` | 2000 ms | 500 … 30 000 ms |
| Mapa de registros (área, offset, cantidad, tipo, nombre) | el de §1 | Tabla editable desde el Dashboard |

**Cambios respecto de la versión anterior y su motivo:**

- *Por defecto 9600 8N1 y no 19200 8E1*: el dispositivo 1 está fijado así en la T1, con un
  argumento medido (t1,5 = 1,72 ms frente a las pausas del GC de MicroPython). 19200 8E1 pasa a ser
  el preajuste "Norma MODBus" para el esclavo desconocido.
- *Bits de datos 7 eliminado*: MODBus RTU usa 8 bits obligatoriamente (`config.py:39`).
- *Reintentos 1 y no 3, y ausencia sostenida separada*: la T1 midió que contar fallos hacía
  parpadear los indicadores (informe T1 §9.4.4). El reintento recupera una trama perdida; la
  ausencia sostenida decide `DEVICE NOT REACHED` / `DDEATH`.
- *Período 250 ms*: el ciclo de 4 transacciones midió 161 ms en la T1 contra un esclavo MicroPython;
  200 ms dejaba 80,5 % de ocupación. 250 ms da margen para el reintento.

### 5.3 Tiempos de silencio

MODBus serie usa 11 bits por carácter. Por encima de 19200 bps la norma fija valores constantes.

| Baud | t_carácter | t1,5 | t3,5 |
|---|---|---|---|
| 9600 | 1,146 ms | 1,719 ms | **4,010 ms** |
| 19200 | 0,573 ms | 0,859 ms | **2,005 ms** |
| > 19200 | — | 0,750 ms (fijo) | **1,750 ms** (fijo) |

El dispositivo 1 usa 8N1, es decir 10 bits por carácter (fuera de la norma, documentado en la T1
`config.py:46-54`); los cálculos usan 11 bits, que sobreestiman los tiempos y quedan del lado
seguro. **El maestro de Node-RED no delimita por t3,5** sino por longitud esperada, y aplica t3,5
solo como cota inferior antes de transmitir (ADR-012, spike §3).

---

## 6. Capa física RS-485 (checklist de montaje)

- Par trenzado para A/B, **más una referencia de masa común** entre todos los nodos.
- **Terminación de 120 Ω**: solo si el bus supera la longitud crítica, ≈ 1,5 m con el MAX485
  (L_c = t_subida × v / 2 = 15 ns × 2·10⁸ m/s / 2). La T1 operó sin terminación con bus de
  15-40 cm y 0,0 % de error en 750 ciclos (informe T1 §5.5). Si se instala, **solo en los dos
  extremos físicos**.
- **Polarización *fail-safe*** (680 Ω a +5 V en A y 680 Ω a masa en B, un único punto): solo junto
  con la terminación; con 120 Ω ∥ 120 Ω da V_AB = 211 mV > 200 mV. Con 1 kΩ quedaría en 145 mV,
  dentro de la zona indeterminada (informe T1 §5.6).
- Control de dirección del MAX485 del dispositivo 1: `DE` y `RE` unidos a **GPIO 4**. **Vaciar el
  buffer de transmisión antes de liberar la línea**: `uart.flush()` (MicroPython ≥ 1.20) y una
  espera de un carácter, que es lo que hacía `umodbus` (`serial.py` `_send()`, 2.3.7). El stack
  propio debe reproducirlo y verificar al arrancar que `UART.flush` existe.
- **Niveles lógicos**: el MAX485 es de 5 V y el ESP32 de 3,3 V (máximo absoluto 3,6 V).
  - ESP32 → DI/DE/RE: conexión directa (VIH ≥ 2,0 V; margen 1,3 V).
  - **RO → RX (GPIO 16): divisor 2,2 kΩ / 3,3 kΩ obligatorio y pull-up de 680 Ω de RO a 5 V.**
    Sin el pull-up, con DE = RE = 1 el RO queda en alta impedancia, el divisor tira RX a masa y el
    UART lee `0x00` continuos: fue el incidente más caro de la T1 (`INCONVENIENTES.md` §4).
  - Alternativa: MAX3485 (3,3 V), que elimina el divisor. **Esto debe documentarse: la consigna lo
    pregunta de forma explícita en la Tarea Nº1.**
- **Lado maestro (dispositivo 2):** adaptador USB-RS485. Debe conmutar la dirección
  **automáticamente**; verificar modelo y latencia del driver antes de F3 (spike V-4, riesgo R-04).
