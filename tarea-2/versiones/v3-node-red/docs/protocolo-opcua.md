# Protocolo OPC UA: transporte binario, servicios y tramas

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Desarrolla el criterio *"Análisis de tramas"* y las consignas 3.4 (Read frente a
suscripción), 4.3 (conexión TCP, canal seguro y sesión), 4.4 (encapsulamiento),
4.5 (decodificación byte a byte) y 4.6 (eficiencia). Es el equivalente de
`tarea-1/docs/protocolo-comunicacion.md`.

**Procedencia de los bytes.** Todos los volcados de este documento son
**mensajes reales** de la pila node-opcua 2.160.0 intercambiados por el
servidor y el cliente del trabajo (`herramientas/vectores/*.json`, generados
con `capturar_tramas_local.js`), decodificados con `opcua_tramas.py`. En el
banco se repite el análisis sobre la captura `tcpdump` y se reemplazan los
valores que dependen de la sesión (tokens, marcas de tiempo, números de
secuencia).

---

## Índice

1. [Estructura general de un mensaje UA TCP](#1-estructura-general-de-un-mensaje-ua-tcp)
2. [HEL / ACK / ERR](#2-hel--ack--err)
3. [OPN, MSG y CLO](#3-opn-msg-y-clo)
4. [Conexión TCP, canal seguro y sesión](#4-conexión-tcp-canal-seguro-y-sesión)
5. [Codificación UA Binary](#5-codificación-ua-binary)
6. [Decodificación byte a byte: Write sobre las dos variables](#6-decodificación-byte-a-byte-write-sobre-las-dos-variables)
7. [Read periódico frente a suscripción](#7-read-periódico-frente-a-suscripción)
8. [Encapsulamiento completo](#8-encapsulamiento-completo)
9. [Eficiencia de la trama](#9-eficiencia-de-la-trama)
10. [Referencias](#10-referencias)

---

## 1. Estructura general de un mensaje UA TCP

Todo mensaje empieza con una **cabecera fija de 8 bytes**, en little-endian
(IEC 62541-6 §7.1.2):

| Campo | Tamaño | Contenido |
|---|---|---|
| MessageType | 3 bytes ASCII | `HEL`, `ACK`, `ERR`, `RHE`, `OPN`, `MSG` o `CLO` |
| ChunkType | 1 byte ASCII | `F` (final), `C` (intermedio), `A` (abortado) |
| MessageSize | UInt32 | Longitud total del mensaje **incluida la cabecera** |

| Tipo | Nombre | Quién lo envía | Para qué |
|---|---|---|---|
| HEL | Hello | Cliente | Primer mensaje sobre TCP: URL del endpoint y tamaños de buffer |
| ACK | Acknowledge | Servidor | Acepta y fija los buffers |
| ERR | Error | Cualquiera | Error de transporte; luego se cierra el socket |
| RHE | ReverseHello | Servidor | Conexión inversa: el servidor inicia el TCP (útil detrás de un *firewall*). No se usa |
| OPN | OpenSecureChannel | Ambos | Abre o renueva el canal seguro (seguridad **asimétrica**) |
| MSG | Message | Ambos | Todo servicio (Read, Write, Publish…) con seguridad **simétrica** |
| CLO | CloseSecureChannel | Cliente | Cierra el canal (sin respuesta) |

**Delimitación sobre TCP.** TCP entrega un flujo de bytes sin límites de
mensaje. El receptor lee los 8 bytes de cabecera, toma **MessageSize** y sabe
exactamente cuántos bytes más pertenecen a ese mensaje. Es lo que hace el proxy
de `capturar_tramas_local.js`. Contraste con MODBus RTU: allá el límite lo
marcaba un **silencio** de 3,5 caracteres en la línea; acá lo marca un **campo
de longitud**, porque TCP no conserva tiempos.

**Chunks.** Un mensaje que no entra en el buffer negociado en HEL/ACK se parte
en varios chunks (`C`…`C`,`F`), cada uno con su cabecera y su número de
secuencia. En este trabajo nunca ocurre: el mensaje más grande,
GetEndpointsResponse con **14 674 bytes**, viaja como un único chunk `F`
porque el buffer negociado es de 64 KiB. **TCP sí** lo parte en varios
segmentos (MSS ≈ 1448 bytes), y el receptor lo reensambla antes de entregarlo.
Fragmentación de transporte y fragmentación de aplicación son cosas distintas.

## 2. HEL / ACK / ERR

| Campo (HEL) | Tipo | Valor típico |
|---|---|---|
| ProtocolVersion | UInt32 | 0 |
| ReceiveBufferSize / SendBufferSize | UInt32 | 65 535 o mayor |
| MaxMessageSize | UInt32 | 0 = sin límite |
| MaxChunkCount | UInt32 | 0 = sin límite |
| EndpointUrl | String | `opc.tcp://192.168.10.1:4840` |

El ACK repite los cinco UInt32 (sin la URL) con los valores aceptados. En la
diapositiva 38 del material se ve el mismo HEL (59 bytes con otra URL). En los
vectores del trabajo: HEL de 57 bytes, ACK de 28 bytes.

## 3. OPN, MSG y CLO

Después de la cabecera de 8 bytes:

```text
┌──────────┬─────────────────┬──────────────────────┬─────────────────────┬──────────────────────┐
│ Cabecera │ SecureChannelId │ Cabecera de seguridad│ Cabecera de secuencia│ Cuerpo [+ relleno    │
│ 8 bytes  │ UInt32          │ OPN: asimétrica      │ SequenceNumber UInt32│  + firma si Sign o   │
│          │                 │ MSG/CLO: TokenId     │ RequestId UInt32     │  SignAndEncrypt]     │
└──────────┴─────────────────┴──────────────────────┴─────────────────────┴──────────────────────┘
```

| Campo | Qué es |
|---|---|
| **SecureChannelId** | Lo asigna el servidor en la OpenSecureChannelResponse. El primer OPN viaja con 0. En los vectores: 1 |
| Cabecera **asimétrica** (OPN) | `SecurityPolicyUri` (String), `SenderCertificate` (ByteString), `ReceiverCertificateThumbprint` (ByteString). Con política None la URI es `…#None` y los dos ByteString van vacíos (−1) |
| Cabecera **simétrica** (MSG/CLO) | `TokenId`: identifica qué juego de claves simétricas se usa. Cambia cuando el canal se renueva (OPN *Renew*, al 75 % de `RevisedLifetime`, que en los vectores es 600 000 ms) |
| **SequenceNumber** | Crece en 1 por chunk enviado, **con un contador independiente en cada sentido**: en el par Write real del §6, la petición lleva 29 y la respuesta 24. Detecta pérdidas, repeticiones y ataques de *replay* |
| **RequestId** | Empareja la respuesta con su petición: en ese mismo par, ambos llevan **29** |
| Cuerpo | `TypeId` (NodeId del tipo de servicio) + RequestHeader o ResponseHeader + parámetros |
| Relleno + firma | Solo con Sign o SignAndEncrypt. Con Basic256Sha256, la firma es un HMAC-SHA256 de **32 bytes** (verificado en los vectores Sign) |

## 4. Conexión TCP, canal seguro y sesión

> *Consigna 4.3: explicar la función de cada etapa y la diferencia entre
> conexión TCP, canal seguro y sesión.*

Son tres capas apiladas, cada una con su propio ciclo de vida (material de
clase, diapositivas 18-19):

| | Conexión TCP | Canal seguro | Sesión |
|---|---|---|---|
| Asocia | Dos **sockets** (IP + puerto) | Dos **aplicaciones** (certificados X.509 de instancia) | Un **usuario** con el servidor |
| Se establece con | SYN / SYN-ACK / ACK | HEL/ACK + **OPN** | **CreateSession** + **ActivateSession** |
| Se cierra con | FIN / ACK | **CLO** | **CloseSession** |
| Garantiza | Entrega ordenada y sin pérdida de bytes (disponibilidad) | **Integridad** (firma) y **confidencialidad** (cifrado) de cada mensaje; autenticación de la aplicación | **Autenticación y autorización del usuario**; contexto: suscripciones, permisos, NamespaceArray |
| Identificador | 4-tupla de IP y puertos | SecureChannelId + TokenId | SessionId; en cada petición, el **AuthenticationToken** |
| Duración | Mientras el cable y los equipos respondan | `RevisedLifetime` (renovable con OPN *Renew*) | `RevisedSessionTimeout` sin actividad (60 s en el trabajo) |
| Si se pierde… | Se cae el canal | Se puede **reabrir otro canal** y reactivar la **misma** sesión sobre él | Se pierden las suscripciones (salvo transferencia) |

**La clave de la diferencia** está en la última fila. La sesión **no depende**
de un canal particular: al desconectar el cable, TCP y el canal mueren, pero la
sesión y sus suscripciones siguen vivas en el servidor durante su *timeout*. El
cliente abre una conexión y un canal **nuevos** y reactiva la sesión existente
(ActivateSession sobre el nuevo canal). Así se recupera la comunicación en la
Parte 3.6 sin perder la suscripción, si el corte dura menos de 30 s.

Dos evidencias del propio trabajo:

- **I-05**: en el evento de conexión TCP el modo de seguridad todavía vale
  `Invalid`. La conexión existe **antes** que el canal.
- En SignAndEncrypt el cliente abre una **primera conexión** con canal None solo
  para GetEndpoints, la cierra y abre **otra** para la sesión
  ([secuencia_sesion.md §3](../diagramas/secuencia_sesion.md)).

**Función de cada etapa** (consigna 4.2):

| Etapa | Mensajes | Función |
|---|---|---|
| Resolución ARP | ARP Request/Reply | Obtener la MAC de 192.168.10.1 para armar la trama Ethernet |
| Establecimiento TCP | SYN, SYN-ACK, ACK | Sincronizar números de secuencia y abrir un flujo confiable |
| HEL/ACK | HEL, ACK | Acordar tamaños de buffer y de mensaje; declarar el endpoint pedido |
| OPN | OpenSecureChannel Req/Resp | Crear el canal: modo, política, *nonces* para derivar claves, TokenId, vida |
| GetEndpoints | Req/Resp | Conocer los endpoints, sus políticas, el certificado y los tokens de usuario aceptados |
| CreateSession | Req/Resp | Crear la sesión: intercambio de certificados y *nonces*, SessionId, AuthenticationToken, timeout |
| ActivateSession | Req/Resp | Presentar la identidad del usuario (anónimo o usuario/clave) y la firma que prueba la posesión de la clave privada de la aplicación |
| CreateSubscription | Req/Resp | Crear la suscripción: PublishingInterval, KeepAlive, Lifetime |
| CreateMonitoredItems | Req/Resp | Qué nodos vigilar, con qué SamplingInterval y QueueSize |
| Publish | Req/Resp (repetido) | El cliente entrega "sobres" que el servidor devuelve con notificaciones |
| Write | Req/Resp | Escribir `Cliente.*` |
| CloseSession | Req/Resp | Liberar la sesión y sus suscripciones |
| CLO | sin respuesta | Liberar el canal |
| FIN | FIN/ACK | Cerrar la conexión TCP |

## 5. Codificación UA Binary

IEC 62541-6 §5.2. **Todos los números van en little-endian**: primero el byte
menos significativo.

| Tipo | Codificación | Ejemplo real |
|---|---|---|
| Boolean | 1 byte: `00` = false, `01` = true | `true` → `01` |
| UInt16 | 2 bytes LE | 0x1234 = 4660 → `34 12` |
| UInt32 / Int32 | 4 bytes LE | MessageSize 114 → `72 00 00 00` |
| Double | 8 bytes IEEE-754 LE | PublishingInterval 100.0 |
| String | Int32 de longitud + bytes UTF-8; −1 (`ff ff ff ff`) = nulo | `0d 00 00 00` + `Cliente.Rampa` |
| ByteString | Igual que String, con bytes arbitrarios | AuthenticationToken |
| DateTime | Int64 LE, **intervalos de 100 ns desde 1601-01-01 UTC** | `30 28 93 b5 7e 5b dd 01` → 2026-10-14 01:52:46.131 UTC |
| StatusCode | UInt32 LE; bit 31 = Bad, bit 30 = Uncertain | Good = `00 00 00 00`; BadNotWritable = 0x803B0000 |

**NodeId**: el primer byte es una **máscara** que dice cómo sigue:

| Máscara | Formato | Bytes totales | Uso en los vectores |
|---|---|---|---|
| `00` | TwoByte: id < 256 en ns 0 | 2 | AdditionalHeader `00 00` |
| `01` | FourByte: ns (1 byte) + id UInt16 | 4 | TypeId WriteRequest `01 00 a1 02` (i=673) |
| `02` | Numeric: ns UInt16 + id UInt32 | 7 | — |
| `03` | String: ns UInt16 + String | 7 + largo | `03 01 00 0d 00 00 00 43 6c 69…` = ns=1;s=Cliente.Rampa |
| `04` | Guid | 19 | — |
| `05` | ByteString | 7 + largo | AuthenticationToken de node-opcua (16 bytes aleatorios) |

El codificador **elige la forma más corta** que admite el valor: 673 entra en
UInt16 y ns=0 en un byte, así que usa FourByte (4 bytes) en lugar de Numeric
(7).

**Variant**: un byte de máscara cuyos 6 bits bajos son el **tipo integrado**
(1 = Boolean, 5 = UInt16, 11 = Double…) y el bit 0x80 indica arreglo; después
viene el valor.

**DataValue**: un byte de máscara que indica qué campos opcionales siguen, en
orden fijo: `0x01` Value, `0x02` StatusCode, `0x04` SourceTimestamp, `0x10`
SourcePicoseconds, `0x08` ServerTimestamp, `0x20` ServerPicoseconds. **Lo que
no está en la máscara no ocupa ni un byte**: un StatusCode Good no se envía
porque ausente significa Good. En el Write del cliente la máscara es `01`
(solo Value); en las notificaciones es `0d` = Value + SourceTimestamp +
ServerTimestamp.

**Contraste con MODBus (Tarea 1):** MODBus envía los registros de 16 bits en
**big-endian** (0x1234 → `12 34`), salvo el CRC, que va en little-endian
(`tarea-1/docs/protocolo-comunicacion.md` §8). OPC UA es little-endian **en
todo**, igual que los procesadores ARM y x86 que lo ejecutan: decodificar es
copiar bytes, sin invertirlos.

## 6. Decodificación byte a byte: Write sobre las dos variables

Consigna 4.5. Se generan con:

```bash
python herramientas/opcua_tramas.py --markdown "<hex del mensaje>"
python herramientas/opcua_tramas.py --ethernet --markdown "<hex de la trama completa>"
```

### 6.1 WriteRequest `Cliente.Rampa` = 0x1234 (114 bytes)

```text
4d534746 72000000 01000000 01000000 1d000000 1d000000 0100a102 05000010
000000a0 8928f154 50b041bb 0e99f456 e2a3c330 2893b57e 5bdd011d 00000000
00000000 0000983a 00000000 00010000 00030100 0d000000 436c6965 6e74652e
52616d70 610d0000 00ffffff ff010534 12
```

| Offset | Bytes | Campo | Tipo | Valor | Significado |
|---|---|---|---|---|---|
| 0 | `4d 53 47` | MessageType | ASCII[3] | `MSG` | Mensaje de servicio |
| 3 | `46` | ChunkType | ASCII | `F` | Chunk final (único) |
| 4 | `72 00 00 00` | MessageSize | UInt32 | 114 | Bytes totales |
| 8 | `01 00 00 00` | SecureChannelId | UInt32 | 1 | Canal asignado en el OPN |
| 12 | `01 00 00 00` | TokenId | UInt32 | 1 | Cabecera de seguridad simétrica |
| 16 | `1d 00 00 00` | SequenceNumber | UInt32 | 29 | Contador del sentido cliente→servidor |
| 20 | `1d 00 00 00` | RequestId | UInt32 | 29 | Lo repite la respuesta |
| 24 | `01 00 a1 02` | TypeId | NodeId FourByte | ns=0;i=673 | **WriteRequest** (0x02A1 = 673) |
| 28 | `05 00 00 10 00 00 00` + 16 bytes | RequestHeader.AuthenticationToken | NodeId ByteString | b=a08928f1… | Prueba de pertenencia a la sesión |
| 51 | `30 28 93 b5 7e 5b dd 01` | RequestHeader.Timestamp | DateTime | 2026-10-14 01:52:46.131 UTC | Hora del cliente al enviar |
| 59 | `1d 00 00 00` | RequestHeader.RequestHandle | UInt32 | 29 | Lo elige el cliente; vuelve en la respuesta |
| 63 | `00 00 00 00` | ReturnDiagnostics | UInt32 | 0 | Sin diagnósticos |
| 67 | `00 00 00 00` | AuditEntryId | String | "" | Vacío (longitud 0) |
| 71 | `98 3a 00 00` | TimeoutHint | UInt32 | 15 000 | ms que el cliente espera |
| 75 | `00 00` `00` | AdditionalHeader | ExtensionObject | nulo | TypeId i=0, sin cuerpo |
| 78 | `01 00 00 00` | NodesToWrite.Length | Int32 | 1 | Un WriteValue |
| 82 | `03 01 00 0d 00 00 00` + `Cliente.Rampa` | NodeId | NodeId String | ns=1;s=Cliente.Rampa | Máscara 03, ns=1, 13 caracteres: **20 bytes** |
| 102 | `0d 00 00 00` | AttributeId | UInt32 | 13 | **Value** |
| 106 | `ff ff ff ff` | IndexRange | String | nulo | Escalar: sin rango |
| 110 | `01` | DataValue.EncodingMask | Byte | 0x01 | Solo Value (sin estado ni marcas de tiempo) |
| 111 | `05` | Variant.EncodingMask | Byte | 5 | **UInt16** escalar |
| 112 | `34 12` | Variant.Value | UInt16 | **4660 = 0x1234** | **Little-endian:** primero el byte bajo `34`, después el alto `12` |

### 6.2 WriteResponse (64 bytes)

| Offset | Bytes | Campo | Valor | Significado |
|---|---|---|---|---|
| 0-7 | `4d 53 47 46 40 00 00 00` | Cabecera | MSG F 64 | |
| 8 | `01 00 00 00` | SecureChannelId | 1 | |
| 12 | `01 00 00 00` | TokenId | 1 | |
| 16 | `18 00 00 00` | SequenceNumber | **24** | Contador propio del servidor |
| 20 | `1d 00 00 00` | RequestId | **29** | = el de la petición |
| 24 | `01 00 a4 02` | TypeId | i=676 | **WriteResponse** |
| 28 | `80 eb 93 b5 7e 5b dd 01` | ResponseHeader.Timestamp | 01:52:46.136 UTC | 5 ms después de la petición |
| 36 | `1d 00 00 00` | RequestHandle | 29 | Empareja con la petición |
| 40 | `00 00 00 00` | ServiceResult | **Good** | El **servicio** se ejecutó |
| 44 | `00` | ServiceDiagnostics | vacío | |
| 45 | `00 00 00 00` | StringTable | 0 elementos | |
| 49 | `00 00 00` | AdditionalHeader | nulo | |
| 52 | `01 00 00 00` | Results.Length | 1 | Un resultado por WriteValue |
| 56 | `00 00 00 00` | Results[0] | **Good** | La **escritura de ese nodo** se aceptó |
| 60 | `00 00 00 00` | DiagnosticInfos | 0 elementos | |

Hay **dos StatusCode**: `ServiceResult` (si el servicio en sí funcionó) y
`Results[i]` (el resultado de **cada** nodo). Escribir `Servidor.Rampa` da
`ServiceResult = Good` y `Results[0] = BadNotWritable`: el servicio se procesó,
pero ese nodo rechazó la escritura.

### 6.3 WriteRequest `Cliente.EstadoPulsador` = true (122 bytes)

Idéntico al anterior hasta el offset 81, salvo SequenceNumber/RequestId/
RequestHandle = 30 y la marca de tiempo. Cambia el final:

| Offset | Bytes | Campo | Valor | Significado |
|---|---|---|---|---|
| 82 | `03 01 00 16 00 00 00` + `Cliente.EstadoPulsador` | NodeId | ns=1;s=Cliente.EstadoPulsador | 22 caracteres: **29 bytes** |
| 111 | `0d 00 00 00` | AttributeId | 13 | Value |
| 115 | `ff ff ff ff` | IndexRange | nulo | |
| 119 | `01` | DataValue.EncodingMask | 0x01 | Solo Value |
| 120 | `01` | Variant.EncodingMask | 1 | **Boolean** |
| 121 | `01` | Variant.Value | **true** | **Un byte entero** para un bit: `01` = true, `00` = false |

Los 8 bytes de diferencia entre los dos Write (122 − 114) salen **todos del
nombre**: "EstadoPulsador" tiene 9 caracteres más que "Rampa", y el valor
Boolean ocupa 1 byte menos que el UInt16. En MODBus la misma escritura
(FC 0x05, coil) es `01 05 00 00 FF 00` + CRC: el "true" ocupa **2 bytes**
(`FF 00`), y el bit en sí no se transmite como bit.

## 7. Read periódico frente a suscripción

### 7.1 Cómo funciona cada uno

**Modo A — Read periódico (polling).** Cada 100 ms el cliente envía un
ReadRequest con los dos nodos y `MaxAge = 0` (valor actual, no de caché;
diapositiva 22) y el servidor responde. Es el mismo patrón del maestro MODBus
de la Tarea 1: **se pregunta aunque nada haya cambiado**.

**Modo B — Subscription + MonitoredItems.**

| Parámetro | Pedido | Revisado por el servidor | Qué controla |
|---|---|---|---|
| **SamplingInterval** (por ítem) | 100 ms | 100 ms | Cada cuánto el servidor **mira** el valor del nodo. Si se pidiera menos de 50 ms, el servidor lo subiría a `MinimumSamplingInterval` = 50 ms |
| **QueueSize** (por ítem) | 1 | 1 | Cuántos cambios guarda entre dos publicaciones. Con 1 y `DiscardOldest = true` queda solo el último: para un LED interesa el valor actual, no la historia |
| **PublishingInterval** (suscripción) | 100 ms | 100 ms | Cada cuánto el servidor **arma** un NotificationMessage con lo que haya en las colas |
| MaxKeepAliveCount | 10 | 10 | Cuántos ciclos vacíos tolera antes de mandar un KeepAlive: 10 × 100 ms = 1 s |
| LifetimeCount | 300 | 300 | Cuántos ciclos sin PublishRequest antes de **borrar** la suscripción: 30 s |

Los valores revisados salen de las respuestas reales
(`prueba_opcua_tramas.py`, sección 6).

### 7.2 El mecanismo PublishRequest / PublishResponse

OPC UA sobre TCP sigue siendo **petición-respuesta**: el servidor no puede
enviar un mensaje que nadie pidió. La suscripción resuelve esto con un
mecanismo de **sobres** (diapositiva 24):

1. El cliente envía **PublishRequest por adelantado**, sin esperar datos. En
   los vectores, apenas crea la suscripción, encola **5**.
2. El servidor las guarda. Al vencer cada PublishingInterval revisa las colas
   de los MonitoredItems:
   - **hay cambios** → responde una PublishRequest pendiente con un
     **PublishResponse** con `DataChangeNotification` (ClientHandle + DataValue
     de cada ítem que cambió);
   - **no hay cambios** → no responde nada… hasta acumular
     MaxKeepAliveCount ciclos vacíos. Entonces envía un **KeepAlive**: un
     PublishResponse con `NotificationData` vacío (89 bytes en los vectores).
3. Al recibir una respuesta, el cliente envía **otra** PublishRequest. Así
   siempre hay sobres disponibles.
4. Cada PublishRequest **confirma** (*SubscriptionAcknowledgement*) el número
   de secuencia de la notificación anterior. Hasta recibir esa confirmación, el
   servidor la conserva para un eventual **Republish**: si se pierde una
   notificación durante un corte, el cliente la pide de nuevo. Por eso la
   PublishRequest pesa 90 bytes con confirmación y 82 sin ella: los 8 bytes son
   SubscriptionId + SequenceNumber.

**Para qué sirve el KeepAlive:** sin él, un cliente que no recibe nada no puede
distinguir "no hubo cambios" de "el servidor murió". Con él, el silencio máximo
es de 1 s: si pasa más tiempo sin ningún PublishResponse, algo se rompió.
También le confirma al servidor que el cliente sigue vivo, porque la
respuesta genera una nueva PublishRequest; si estas dejan de llegar, el
servidor cuenta hacia el LifetimeCount.

**Para observarlo** (consigna): rampa detenida y pulsador en reposo. Solo
quedan KeepAlive. En los vectores llegan a 3581 ms y 4670 ms: **1,09 s** de
período.

### 7.3 Predicción de tramas y bytes (60 s)

Antes de medir en el banco, la comparación se predijo con el servidor y el
cliente reales en la PC (`python herramientas/comparar_modos.py`; 10 s de
régimen, normalizado a 60 s):

| Modo | Escenario | Mensajes UA | Bytes UA | Bytes en tramas (estimado) | KeepAlive |
|---|---|---|---|---|---|
| A · Read | rampa en movimiento | 1113 | 151 180 | 224 640 | — |
| B · Suscripción | rampa en movimiento | 1107 | 123 994 | 197 076 | 0 |
| A · Read | rampa detenida | 1109 | 150 695 | 223 920 | — |
| B · Suscripción | rampa detenida | **126** | **10 954** | **19 299** | 56 |

**Lectura:**

- **Con la rampa en movimiento la suscripción casi no ahorra:** 99 % de los
  mensajes y 82 % de los bytes del Modo A. La rampa cambia cada 50 ms, más
  rápido que el PublishingInterval de 100 ms, así que **cada ciclo hay un
  cambio que notificar**. La suscripción termina haciendo un intercambio cada
  100 ms, igual que el polling. El ahorro de bytes viene de que la
  PublishRequest (90 B) es más chica que la ReadRequest (173 B), que repite los
  dos NodeIds string en cada pedido.
- **Con la rampa detenida la suscripción usa 11 % de los mensajes y 7 % de los
  bytes:** solo viajan los KeepAlive (~1 por segundo) y sus PublishRequest. El
  Modo A sigue preguntando 10 veces por segundo para recibir siempre lo mismo.
- **Conclusión:** la suscripción no es "más eficiente" en abstracto: es
  eficiente **cuando los datos cambian más despacio que el intervalo de
  publicación**, que es el caso típico de una planta (estados, alarmas,
  temperaturas). Una señal que cambia en cada ciclo de publicación no se
  beneficia. Además, la suscripción **reacciona más rápido** a un cambio
  aislado (el pulsador): el servidor lo detecta en el siguiente muestreo y lo
  envía en la siguiente publicación, sin esperar a que el cliente pregunte.

Diferencias esperables en el banco: la captura `tcpdump` contará también los
ACK puros de TCP y los segmentos de 1500 bytes; la RPi agrega latencia de
procesamiento. Se registran ambos números en [PARTE-3.md](../PARTE-3.md).

## 8. Encapsulamiento completo

Consigna 4.4: una trama que transporta un **PublishResponse** con el valor de
`Servidor.Rampa`. Con un ítem, el mensaje OPC UA mide 134 bytes en los
vectores:

```text
├─ Ethernet II (14) ─┼─ IPv4 (20) ─┼─ TCP (32) ─┼──────────── OPC UA (134) ────────────┤
  MAC dst  MAC src  Type  ...  src 192.168.10.1  sport 4840          MSG F 134 | canal | token | seq | ...
  (RPi 2)  (RPi 1) 0x0800      dst 192.168.10.2  dport efímero       PublishResponse → DataChangeNotification
                                                                      → ClientHandle → DataValue → Variant UInt16
Total visto por Wireshark: 14 + 20 + 32 + 134 = 200 bytes
En el cable: + 8 (preámbulo + SFD) + 4 (FCS) + 12 (IFG) = 224 bytes
```

| Capa | Campo | Qué se ve y qué significa |
|---|---|---|
| **Ethernet II** | MAC destino | La de la **RPi 2**: la trama va al cliente. Se obtuvo por ARP |
| | MAC origen | La de la **RPi 1** |
| | EtherType | `0x0800` = IPv4. Ethernet II no tiene campo de longitud: el EtherType dice qué protocolo lleva adentro |
| **IPv4** | Versión / IHL | `0x45`: versión 4, cabecera de 5 × 4 = 20 bytes (sin opciones) |
| | Total Length | 20 + 32 + 134 = 186 bytes |
| | Flags | `DF` (Don't Fragment): Linux usa *Path MTU Discovery* y nunca fragmenta en IP |
| | TTL | 64 (valor por defecto de Linux); no se decrementa: no hay routers |
| | Protocol | 6 = TCP |
| | Origen / destino | 192.168.10.1 → 192.168.10.2 |
| **TCP** | Puertos | **4840** → puerto efímero del cliente (32768-60999 en Linux) |
| | Número de secuencia | Posición del primer byte de esta carga dentro del flujo servidor→cliente. Wireshark lo muestra **relativo** (empieza en 1); el absoluto es aleatorio (RFC 6528) |
| | Número de acuse | Próximo byte que el servidor espera del cliente: confirma la PublishRequest recibida |
| | Data offset | 8 → **32 bytes**: 20 fijos + 12 de opciones (**TCP Timestamps**, RFC 7323, que Linux activa por defecto) |
| | Flags | `PSH, ACK` |
| **OPC UA** | Cabecera + canal + seguridad + secuencia | `MSG F`, MessageSize, SecureChannelId, TokenId, SequenceNumber, RequestId |
| | TypeId | i=829 PublishResponse |
| | NotificationMessage | SequenceNumber de la notificación; NotificationData = ExtensionObject (TypeId i=811 **DataChangeNotification**) |
| | MonitoredItemNotification | ClientHandle (identifica el ítem: lo eligió el cliente) + DataValue con máscara `0d` (Value + SourceTimestamp + ServerTimestamp) + Variant tipo 5 + **2 bytes de la rampa** |

Decodificación automática de una trama copiada de Wireshark
(*clic derecho → Copy → …as Hex Stream*):
`python herramientas/opcua_tramas.py --ethernet --markdown <hex>`.

Detalle observado en los vectores: node-opcua envía `PublishTime = 0` (nulo) en
el NotificationMessage. Es una particularidad de esta pila; las marcas de
tiempo que importan son las del DataValue.

## 9. Eficiencia de la trama

Consigna 4.6. Resultado de `python herramientas/eficiencia_trama.py`, con el
WriteRequest **real** de `Cliente.Rampa` (114 bytes) y la trama **real** de la
Tarea 1:

| | OPC UA / TCP / Ethernet | MODBus RTU (Tarea 1, FC 0x06) |
|---|---|---|
| Trama | 8 preámbulo + 14 Eth + 20 IP + 32 TCP + **114 UA** + 4 FCS + 12 IFG | `01 06 00 00 00 80 88 6A` |
| Bytes para 1 word | **204** (180 los que muestra Wireshark) | **8** (+ 3,5 caracteres de silencio) |
| Bytes útiles | 2 | 2 |
| **Eficiencia** | **0,98 %** (1,11 % sin preámbulo, FCS ni IFG; 1,75 % contando solo el mensaje UA) | **25 %** por bytes; 20 % por bits (8N1); **13,9 %** con el silencio t3,5 |
| Transacción completa | Write + WriteResponse: 358 bytes → **0,56 %** | Petición + eco: 16 bytes → 12,5 % |
| Tiempo en el medio | **16,3 µs** a 100 Mbit/s | **11,98 ms** a 9600 baudios |

**Discusión.**

1. **OPC UA es unas 26 veces menos eficiente en bytes, pero la trama ocupa el
   medio unas 730 veces menos tiempo**, porque el medio es ~10 400 veces más
   rápido. La eficiencia es una relación entre bytes; lo que limita a un
   sistema de control es el **tiempo** y la **capacidad del medio**. Con
   Ethernet, 200 bytes cada 100 ms ocupan el **0,016 %** de un enlace de
   100 Mbit/s.
2. **¿De dónde salen los 112 bytes de sobrecarga del mensaje UA?**

   | Componente | Bytes | Qué compra |
   |---|---|---|
   | Cabecera + canal + token + secuencia | 24 | Delimitación, canal seguro, detección de pérdidas y repeticiones, emparejamiento |
   | TypeId | 4 | Saber qué servicio es |
   | RequestHeader | 50 | Autenticación de sesión (23 B de token), marca de tiempo, handle, timeout |
   | Longitud del arreglo + NodeId string | 24 | **Identificación autodescriptiva** del destino |
   | AttributeId + IndexRange | 8 | Escribir cualquier atributo o parte de un arreglo |
   | Máscaras de DataValue y Variant | 2 | **Tipo** explícito del dato |
   | **Valor** | **2** | |

   MODBus solo tiene dirección de esclavo, función, registro y CRC: ni sesión,
   ni seguridad, ni tipo, ni nombre.
3. **La sobrecarga es fija por mensaje, no por dato.** Un Write con N valores
   paga los 78 bytes de cabeceras una sola vez, y cada valor adicional cuesta
   unos 32 bytes (NodeId string + atributo + rango + DataValue). Con NodeIds
   **numéricos** (`ns=1;i=1001`, 4 bytes en vez de 20) el costo por valor baja a
   unos 16 bytes. Ese es el motivo por el que los perfiles embebidos y PubSub
   UADP usan identificadores numéricos y mensajes agrupados.
4. **Cuándo gana MODBus RTU:** en un bus serie lento y compartido (RS-485 de
   1 km, decenas de esclavos), cada byte cuesta 1 ms de bus. **Cuándo gana
   OPC UA:** cuando hay ancho de banda (Ethernet) y lo que vale es la semántica,
   la seguridad y el desacople entre equipos de distintos fabricantes.

## 10. Referencias

Gont, F., & Bellovin, S. (2012). *Defending against sequence number attacks*
(RFC 6528). IETF. https://doi.org/10.17487/RFC6528

Borman, D., Braden, B., Jacobson, V., & Scheffenegger, R. (Ed.). (2014). *TCP
extensions for high performance* (RFC 7323). IETF.
https://doi.org/10.17487/RFC7323

International Electrotechnical Commission. (2020). *OPC Unified Architecture
— Part 4: Services* (IEC 62541-4:2020).

International Electrotechnical Commission. (2020). *OPC Unified Architecture
— Part 6: Mappings* (IEC 62541-6:2020).

Mahnke, W., Leitner, S.-H., & Damm, M. (2009). *OPC Unified Architecture*.
Springer. https://doi.org/10.1007/978-3-540-68899-0

Modbus Organization. (2006). *MODBUS over serial line specification and
implementation guide V1.02*. https://modbus.org

node-opcua. (2025). *node-opcua: an implementation of OPC UA for Node.js*
(versión 2.160.0) [Software]. https://github.com/node-opcua/node-opcua
