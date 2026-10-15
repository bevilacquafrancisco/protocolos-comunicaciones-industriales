# Diagrama de secuencia — sesión OPC UA completa

**Autores:** Bevilacqua Francisco, Peralta Agustina

Consigna, Parte 4.2: diagrama de secuencia con cada mensaje intercambiado y
quién lo origina, desde la resolución ARP hasta el cierre.

**Origen de los datos.** El orden, los tamaños (MessageSize, en bytes) y los
tiempos de las capas OPC UA **no son teóricos**: salen de una sesión real entre
el servidor y el cliente de este trabajo (pila node-opcua 2.160.0), registrada
con `herramientas/capturar_tramas_local.js` y decodificada con
`opcua_tramas.py` (`herramientas/vectores/sesion_None.json`). Las capas ARP y
TCP, que esa herramienta no ve, siguen el comportamiento estándar de Linux y se
confirman con la captura `tcpdump` del banco (PARTE-4.md). **Al tener la
captura del banco, reemplazar los tamaños y tiempos por los medidos.**

## 1. Secuencia completa (modo None, Modo B)

```mermaid
sequenceDiagram
    autonumber
    participant C as RPi 2 · Cliente<br/>192.168.10.2
    participant S as RPi 1 · Servidor<br/>192.168.10.1:4840

    rect rgb(235,235,235)
    Note over C,S: Capa de enlace: resolución ARP (solo si la entrada no está en caché)
    C->>S: ARP Request (broadcast ff:ff:ff:ff:ff:ff) ¿quién tiene 192.168.10.1?
    S->>C: ARP Reply (unicast) 192.168.10.1 está en <MAC de RPi 1>
    end

    rect rgb(225,235,245)
    Note over C,S: Capa de transporte: conexión TCP (three-way handshake)
    C->>S: SYN (puerto efímero → 4840)
    S->>C: SYN, ACK
    C->>S: ACK
    end

    rect rgb(225,245,230)
    Note over C,S: UA TCP: negociación de buffers y apertura del canal seguro
    C->>S: HEL (57 B) · EndpointUrl, ReceiveBufferSize, SendBufferSize
    S->>C: ACK (28 B) · buffers aceptados
    C->>S: OPN OpenSecureChannelRequest (132 B) · SecureChannelId=0, Issue, None
    S->>C: OPN OpenSecureChannelResponse (135 B) · ChannelId=1, TokenId=1, Lifetime 600 000 ms
    end

    rect rgb(250,240,220)
    Note over C,S: Descubrimiento y sesión (todo como MSG sobre el canal 1)
    C->>S: GetEndpointsRequest (94 B)
    S->>C: GetEndpointsResponse (14 674 B) · endpoints × política × modo + certificado
    C->>S: CreateSessionRequest (1 440 B) · certificado del cliente, nonce
    S->>C: CreateSessionResponse (2 551 B) · SessionId, AuthenticationToken, certificado
    C->>S: ActivateSessionRequest (124 B) · AnonymousIdentityToken
    S->>C: ActivateSessionResponse (96 B) · Good
    C->>S: ReadRequest (112 B) · Server.NamespaceArray (ns=0;i=2255)
    S->>C: ReadResponse (135 B) · [0] OPC UA, [1] urn:unraf:pdci:t2 → ns=1
    end

    rect rgb(240,230,250)
    Note over C,S: Suscripción (Modo B)
    C->>S: CreateSubscriptionRequest (100 B) · 100 ms, KeepAlive 10, Lifetime 300
    S->>C: CreateSubscriptionResponse (72 B) · valores revisados
    C->>S: PublishRequest × 5 (82 B c/u) · el cliente deja peticiones encoladas
    C->>S: CreateMonitoredItemsRequest (217 B) · 2 ítems, Sampling 100 ms, QueueSize 1
    S->>C: CreateMonitoredItemsResponse (106 B) · revisados: 100 ms, 1
    loop cada ~100 ms mientras la rampa cambia
        S->>C: PublishResponse (130-153 B) · DataChangeNotification Servidor.Rampa
        C->>S: PublishRequest (90 B) · confirma (Acknowledgement) la notificación anterior
    end
    end

    rect rgb(250,230,230)
    Note over C,S: Escrituras (Parte 3.3)
    C->>S: WriteRequest (114 B) · Cliente.Rampa = UInt16
    S->>C: WriteResponse (64 B) · Good
    C->>S: WriteRequest (122 B) · Cliente.EstadoPulsador = Boolean
    S->>C: WriteResponse (64 B) · Good
    end

    rect rgb(240,240,240)
    Note over C,S: Sin cambios: KeepAlive
    loop cada ~1,09 s (KeepAliveCount 10 × 100 ms + demora)
        S->>C: PublishResponse KeepAlive (89 B) · NotificationData vacío
        C->>S: PublishRequest (82 B)
    end
    end

    rect rgb(230,230,230)
    Note over C,S: Cierre ordenado
    C->>S: DeleteSubscriptionsRequest (86 B)
    S->>C: ServiceFault × 5 (52 B) · BadNoSubscription a los Publish encolados
    S->>C: DeleteSubscriptionsResponse (64 B)
    C->>S: CloseSessionRequest (79 B)
    S->>C: CloseSessionResponse (52 B)
    C->>S: CLO CloseSecureChannelRequest (57 B) · sin respuesta
    C->>S: FIN, ACK
    S->>C: FIN, ACK
    C->>S: ACK
    end
```

## 2. Lo que muestra la secuencia

| Observación | Dato | Explicación |
|---|---|---|
| El canal se abre **antes** de la sesión | OPN (pasos 6-7) antes de CreateSession (10-11) | El canal seguro protege la comunicación entre **aplicaciones**; la sesión la asocia a un **usuario** y lleva el estado (suscripciones). Ver [docs/protocolo-opcua.md §4](../docs/protocolo-opcua.md) |
| GetEndpoints es el mensaje más grande | 14 674 B | Lista cada combinación IP × modo × política e incluye el certificado del servidor **en cada entrada**. Ocupa varios segmentos TCP, pero un solo mensaje UA (ChunkType F): TCP lo fragmenta y lo reensambla |
| El índice del namespace se **lee**, no se supone | Read de ns=0;i=2255 justo después de activar la sesión | IEC 62541-3 §8.2.2: el índice depende del servidor; la URI es la identidad estable |
| El cliente encola **5 PublishRequest** antes de que haya datos | Pasos 18-22 | El servidor solo puede notificar si tiene una petición pendiente para responder. Con varias en cola nunca se queda sin "sobres" por la latencia de ida y vuelta |
| Período de las notificaciones | ~105 ms entre PublishResponse | PublishingInterval revisado = 100 ms más la latencia de procesamiento |
| KeepAlive | 3581 ms → 4670 ms: **1,09 s** | MaxKeepAliveCount 10 × 100 ms: el servidor avisa que la suscripción sigue viva |
| Cada Publish **confirma** el anterior | PublishRequest de 90 B (con Acknowledgement) vs. 82 B (sin) | Los 8 B extra son SubscriptionId + SequenceNumber de la notificación recibida: hasta confirmarla, el servidor la guarda para un eventual Republish |
| Al borrar la suscripción, 5 ServiceFault | BadNoSubscription | Son las 5 PublishRequest que estaban encoladas sin respuesta |
| CLO no tiene respuesta | Paso final de UA | Después del CLO el servidor solo cierra el socket (FIN de TCP) |

## 3. Diferencia en SignAndEncrypt

Con Basic256Sha256 el cliente abre **dos** conexiones TCP:

1. **Descubrimiento:** HEL/ACK → OPN con política **None** → GetEndpoints →
   CLO. Así obtiene el certificado del servidor, que necesita para cifrar.
2. **Sesión:** HEL/ACK → OPN **cifrado con RSA** (Basic256Sha256) → el resto
   igual que arriba, pero cada MSG va cifrado desde la cabecera de secuencia en
   adelante.

En Wireshark se ven **dos** HEL y **dos** OPN. Ver
`herramientas/vectores/sesion_SignAndEncrypt.json` y
[PARTE-4.md §7](../PARTE-4.md).
