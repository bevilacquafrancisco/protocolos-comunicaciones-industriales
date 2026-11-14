# Sparkplug B: los mensajes decodificados y un payload campo por campo

> **Origen**: el registro del observador (`tools/observador_sparkplug.py`, suscripto a `spBv1.0/#` con el usuario
> de solo lectura) durante el banco virtual. Para cada mensaje se guardan el tópico, el tipo, la QoS, el flag
> de retenido, los bytes crudos (`hex`) y su decodificación con el `sparkplug_b.proto` oficial. Cumple la
> función de MQTT Explorer y además **verifica** `seq` y `bdSeq`: 0 violaciones en las dos corridas. La captura
> de **MQTT Explorer contra el broker en la nube** queda pendiente (P-2 del README del dispositivo 3).

## 1. Un ejemplo de cada tipo

Qué mirar en cada uno:

- **NBIRTH**: es el primero de la sesión, publicado **antes** de que el cliente OPC UA conectara. Por eso
  `Status/MODBUS/*` va con valor `None` (`is_null`, Sparkplug 3.0): no se inventa un valor que todavía no
  existe. `Status/OPCUA/Estado` dice `ERROR` por la misma razón, y el NDATA siguiente lo pasa a `DONE`.
  `bdSeq` y `Node Control/Rebirth` van **sin alias**.
- **DATA y CMD**: solo alias, y `seq` consecutivo. **NCMD y DCMD sin `seq`**.
- **NDEATH**: lo publica el broker como Will, solo con `bdSeq`.
- **La "QoS de entrega" 1** es la que aplicó el broker de desarrollo al entregar (amqtt sube la QoS). La QoS de
  **publicación** del Edge Node es 0 y está verificada en su propio registro (`test_sistema.py`).

### NBIRTH

- Tópico: `spBv1.0/UNRaf_PdCI_2026/NBIRTH/EN01_Gateway`
- QoS de entrega: 1 · retenido: False · payload: 376 bytes · seq: 0
- `timestamp` del payload: 1794527519563 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| bdSeq | — | Int64 | 0 | 1794527519563 |
| Node Control/Rebirth | — | Boolean | False | 1794527519563 |
| Status/MODBUS/Estado | 10 | String | None | 1794527519563 |
| Status/MODBUS/OK | 11 | UInt32 | None | 1794527519563 |
| Status/MODBUS/CRC_ERROR | 12 | UInt32 | None | 1794527519563 |
| Status/MODBUS/TIMEOUT | 13 | UInt32 | None | 1794527519563 |
| Status/MODBUS/EXCEPTION | 14 | UInt32 | None | 1794527519563 |
| Status/OPCUA/Estado | 20 | String | ERROR | 1794527519327 |
| Status/MQTT/Reconexiones | 30 | UInt32 | 0 | 1794527519327 |
| Status/Sparkplug/Rebirths | 40 | UInt32 | 0 | 1794527519327 |

### DBIRTH

- Tópico: `spBv1.0/UNRaf_PdCI_2026/DBIRTH/EN01_Gateway/DEV01_ESP32_Slave`
- QoS de entrega: 1 · retenido: False · payload: 189 bytes · seq: 4
- `timestamp` del payload: 1794527520638 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| Inputs/Pulsador | 101 | Boolean | True | 1794527518309 |
| Inputs/Potenciometro | 102 | UInt16 | 2284 | 1794527520439 |
| Outputs/LedDigital | 103 | Boolean | False | 1794527518350 |
| Outputs/LedPWM | 104 | UInt16 | 0 | 1794527518382 |
| Inputs/Potenciometro_pct | 105 | Float | 55.79999923706055 | 1794527520440 |

### NDATA

- Tópico: `spBv1.0/UNRaf_PdCI_2026/NDATA/EN01_Gateway`
- QoS de entrega: 1 · retenido: False · payload: 28 bytes · seq: 1
- `timestamp` del payload: 1794527520616 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| Status/OPCUA/Estado | 20 | String | DONE | 1794527520616 |

### DDATA

- Tópico: `spBv1.0/UNRaf_PdCI_2026/DDATA/EN01_Gateway/DEV01_ESP32_Slave`
- QoS de entrega: 1 · retenido: False · payload: 43 bytes · seq: 5
- `timestamp` del payload: 1794527520781 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| Inputs/Potenciometro | 102 | UInt16 | 2392 | 1794527520700 |
| Inputs/Potenciometro_pct | 105 | Float | 58.400001525878906 | 1794527520700 |

### NCMD

- Tópico: `spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway`
- QoS de entrega: 1 · retenido: False · payload: 42 bytes · seq: None
- `timestamp` del payload: 1794527520330 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| Node Control/Rebirth | — | Boolean | True | 1794527520330 |

### DCMD

- Tópico: `spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/DEV01_ESP32_Slave`
- QoS de entrega: 1 · retenido: False · payload: 22 bytes · seq: None
- `timestamp` del payload: 1794527577068 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| Outputs/LedDigital | 103 | Boolean | True | 1794527577068 |

### DDEATH

- Tópico: `spBv1.0/UNRaf_PdCI_2026/DDEATH/EN01_Gateway/DEV01_ESP32_Slave`
- QoS de entrega: 1 · retenido: False · payload: 9 bytes · seq: 23
- `timestamp` del payload: 1794527780642 ms UTC
- Sin métricas: solo `timestamp` y `seq` (9 bytes). El `seq` sigue la cuenta del nodo, así la Host Application
  sabe que no se perdió nada antes de la muerte del dispositivo.

### NDEATH

- Tópico: `spBv1.0/UNRaf_PdCI_2026/NDEATH/EN01_Gateway`
- QoS de entrega: 1 · retenido: False · payload: 27 bytes · seq: None
- `timestamp` del payload: 1794527519330 ms UTC

| Métrica | Alias | Tipo | Valor | timestamp |
|---|---|---|---|---|
| bdSeq | — | Int64 | 0 | 1794527519330 |

### STATE

- Tópico: `spBv1.0/STATE/HA01_WebDashboard`
- QoS de entrega: 1 · retenido: False · payload: 41 bytes
- JSON (única excepción a Protobuf en Sparkplug 3.0): online = True, timestamp = 1794527519955

## 2. Volcado de un DDATA, campo por campo

Formato de cable de Protocol Buffers: cada campo empieza con una clave varint, `(número << 3) | tipo de cable`.
Los nombres salen del descriptor del `.proto` (`tools/volcado_sparkplug.py`).

```text
payload de 43 bytes
Hex: 08 8d d0 b3 91 9d 34 12 0e 10 66 18 bc cf b3 91 9d 34 20 06 50 d8 12 12 10 10 69 18 bc cf b3 91 9d 34 20 09 65 9a 99 69 42 18 05
```

| Offset | Bytes | Campo | Nº:tipo de cable | Valor | Nota |
|---|---|---|---|---|---|
| 0 | `08 8d d0 b3 91 9d 34` | `timestamp` | 1:varint | 1794527520781 | ms desde 1970-01-01 UTC |
| 7 | `12 0e` | `metrics` | 2:longitud | submensaje de 14 bytes | Metric |
| 9 | `10 66` | `metrics.alias` | 2:varint | 102 |  |
| 11 | `18 bc cf b3 91 9d 34` | `metrics.timestamp` | 3:varint | 1794527520700 | ms desde 1970-01-01 UTC |
| 18 | `20 06` | `metrics.datatype` | 4:varint | 6 | UInt16 |
| 20 | `50 d8 12` | `metrics.int_value` | 10:varint | 2392 |  |
| 23 | `12 10` | `metrics` | 2:longitud | submensaje de 16 bytes | Metric |
| 25 | `10 69` | `metrics.alias` | 2:varint | 105 |  |
| 27 | `18 bc cf b3 91 9d 34` | `metrics.timestamp` | 3:varint | 1794527520700 | ms desde 1970-01-01 UTC |
| 34 | `20 09` | `metrics.datatype` | 4:varint | 9 | Float |
| 36 | `65 9a 99 69 42` | `metrics.float_value` | 12:32 bits | 58.400002 | IEEE 754, little-endian |
| 41 | `18 05` | `seq` | 3:varint | 5 |  |


**Lectura del volcado**

- **Las métricas viajan solo con `alias`, sin `name`**: es lo que exige Sparkplug 3.0 en los DATA. El nombre
  se resuelve con el DBIRTH.
- **`int_value` es un varint, no una palabra big-endian como en MODBus**: el valor 0x0C8A viaja como `8a 19`,
  en grupos de 7 bits con el menos significativo primero. **`float_value` es IEEE 754 little-endian.**
  Las tres capas usan tres órdenes de bytes distintos, que es la pregunta de *endianness* de la T1.
- **Cada métrica lleva su propio `timestamp`**: es el instante de la lectura MODBus (SourceTimestamp OPC UA),
  no el de la publicación. Así la Host Application sabe qué tan viejo es el dato.
