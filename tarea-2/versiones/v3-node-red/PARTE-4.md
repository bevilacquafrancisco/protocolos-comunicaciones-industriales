# Parte 4 — Análisis de tramas y seguridad

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Guía de banco de la Parte 4: captura de una sesión completa, secuencia de
mensajes, encapsulamiento, decodificación byte a byte, eficiencia, modos y
políticas de seguridad y autenticación de usuario.

**Requisitos previos:** Partes 1 a 3 funcionando. En la PC: Wireshark y Python
3. Teoría en [docs/protocolo-opcua.md](docs/protocolo-opcua.md) y
[docs/seguridad.md](docs/seguridad.md).

**Antes del banco ya está resuelto:** el decodificador
[`opcua_tramas.py`](herramientas/opcua_tramas.py) se validó contra 334
mensajes reales de la misma pila (82 verificaciones,
`prueba_opcua_tramas.py`). En el banco solo se aplica a las capturas reales.

---

## 1. Captura de una sesión completa en modo None (consigna 4.1)

La PC no ve el tráfico del enlace directo: la captura se hace **en la RPi 2**.

Con `config.seguridad.modoCliente = 'None'`, `config.lectura.modo = 'B'` y todo
en marcha:

```bash
# en AMBAS placas: vaciar la tabla ARP para que la captura incluya la resolución
$ sudo ip neigh flush dev eth0

# en la RPi 2:
$ sudo systemctl stop nodered                      # 1. cliente detenido
$ sudo tcpdump -i eth0 -w ~/captura_none.pcapng &   # 2. empezar a capturar (todo eth0, incluido ARP)
$ sudo systemctl start nodered                     # 3. el cliente conecta: ARP, TCP, HEL, OPN, sesión…
#  ... esperar ~15 s; presionar los pulsadores un par de veces (Write del pulsador) ...
$ sudo systemctl stop nodered                      # 4. cierre ordenado: CloseSession, CLO, FIN
$ sudo pkill tcpdump                               # 5. terminar la captura
```

Copiar a la PC (`scp pdci@rpi-cliente.local:~/captura_none.pcapng .\tarea-2\evidencia\capturas\`)
y abrir en Wireshark con el filtro `opcua || arp || tcp.flags.syn==1 || tcp.flags.fin==1`.

## 2. Secuencia de mensajes (consigna 4.2)

El diagrama ya está hecho con los mensajes reales de la pila:
[diagramas/secuencia_sesion.md](diagramas/secuencia_sesion.md). En el banco,
**completar la tabla** con los números de trama de Wireshark y **corregir el
diagrama** si algo difiere (por ejemplo, los tamaños):

| Etapa | Mensaje | Origen | N.º de trama | Tamaño UA (bytes) |
|---|---|---|---|---|
| ARP | Request / Reply | RPi 2 / RPi 1 | *pend.* | — |
| TCP | SYN, SYN-ACK, ACK | RPi 2 / RPi 1 / RPi 2 | *pend.* | — |
| Canal | HEL / ACK | RPi 2 / RPi 1 | *pend.* | 57 / 28 en la PC |
| Canal | OPN Req / Resp | RPi 2 / RPi 1 | *pend.* | 132 / 135 |
| Sesión | GetEndpoints Req / Resp | RPi 2 / RPi 1 | *pend.* | 94 / ~14 700 |
| Sesión | CreateSession Req / Resp | RPi 2 / RPi 1 | *pend.* | ~1 440 / ~2 550 |
| Sesión | ActivateSession Req / Resp | RPi 2 / RPi 1 | *pend.* | 124 / 96 |
| Datos | CreateSubscription Req / Resp | RPi 2 / RPi 1 | *pend.* | 100 / 72 |
| Datos | CreateMonitoredItems Req / Resp | RPi 2 / RPi 1 | *pend.* | 217 / 106 |
| Datos | Publish Req / Resp | RPi 2 / RPi 1 | *pend.* | 90 / 130-153 |
| Datos | Write Req / Resp | RPi 2 / RPi 1 | *pend.* | 114-122 / 64 |
| Cierre | CloseSession Req / Resp | RPi 2 / RPi 1 | *pend.* | 79 / 52 |
| Cierre | CLO | RPi 2 | *pend.* | 57 |
| Cierre | FIN, ACK | ambos | *pend.* | — |

Los tamaños de sesión dependen de los certificados (el nombre de host está
adentro) y van a diferir algo de los de la PC.

## 3. Función de cada etapa y diferencia entre conexión, canal y sesión (consigna 4.3)

Desarrollada en [protocolo-opcua.md §4](docs/protocolo-opcua.md), con dos
evidencias propias: el canal "Invalid" en el evento de conexión
([INCONVENIENTES.md I-05](evidencia/INCONVENIENTES.md)) y la doble conexión TCP
de SignAndEncrypt (§7 de esta guía).

## 4. Encapsulamiento completo (consigna 4.4)

1. En `captura_none.pcapng`, filtro `opcua.servicenodeid.numeric == 829`
   (PublishResponse). Elegir uno que tenga `Servidor.Rampa` en la
   DataChangeNotification (desplegar el árbol).
2. *Copy → …as a Hex Stream* y:

   ```powershell
   python tarea-2\herramientas\opcua_tramas.py --ethernet --markdown "<hex>" > tarea-2\evidencia\tramas\publish_encapsulamiento.md
   ```

3. Completar con los valores reales, explicando cada campo según
   [protocolo-opcua.md §8](docs/protocolo-opcua.md):

| Capa | Campo | Valor medido |
|---|---|---|
| Ethernet II | MAC destino (RPi 2) | *pendiente* |
| | MAC origen (RPi 1) | *pendiente* |
| | EtherType | `0x0800` |
| IPv4 | Origen / destino | 192.168.10.1 → 192.168.10.2 |
| | Total Length / TTL / Protocol / Flags | *pendiente* |
| TCP | Puerto origen / destino | 4840 → *pendiente* |
| | Número de secuencia (relativo y absoluto) | *pendiente* |
| | Número de acuse | *pendiente* |
| | Longitud de cabecera (¿32 con Timestamps?) | *pendiente* |
| OPC UA | MessageType / MessageSize / SecureChannelId / TokenId / SequenceNumber / RequestId | *pendiente* |
| | Valor de `Servidor.Rampa` y su SourceTimestamp | *pendiente* |
| Total | Bytes por capa (lo imprime la herramienta) | *pendiente* |

## 5. Decodificación byte a byte (consigna 4.5)

Cuatro mensajes: WriteRequest/WriteResponse de `Cliente.Rampa` y de
`Cliente.EstadoPulsador`.

1. Filtro `opcua.servicenodeid.numeric == 673` (WriteRequest). El de
   `Cliente.Rampa` mide 8 bytes menos que el de `Cliente.EstadoPulsador`.
2. Para cada uno, copiar **solo los bytes OPC UA** (en el panel de detalle,
   clic derecho sobre *OpcUa Binary Protocol* → *Copy → …as a Hex Stream*) y
   ejecutar `opcua_tramas.py --markdown`.
3. Para las respuestas, filtro `opcua.servicenodeid.numeric == 676` y
   `opcua.security.rqid` igual al RequestId de la petición.
4. Guardar las cuatro tablas en `evidencia/tramas/` y redactar el análisis
   siguiendo [protocolo-opcua.md §6](docs/protocolo-opcua.md), que ya tiene las
   cuatro tablas comentadas con los mensajes de la PC. Lo que cambia en el
   banco son el AuthenticationToken, las marcas de tiempo, los números de
   secuencia y el valor escrito.

Puntos que la consigna pide explicar explícitamente, todos en esas tablas:

| Pedido | Dónde está |
|---|---|
| MessageType, ChunkType, MessageSize, SecureChannelId | offsets 0-11 |
| TokenId, SequenceNumber, RequestId | offsets 12-23 |
| NodeId del servicio y RequestHeader (AuthenticationToken, Timestamp, RequestHandle, TimeoutHint) | offsets 24-77 |
| NodeId de la variable, AttributeId, DataValue con su máscara | offsets 78-110 |
| Variant: byte de tipo y valor; word en little-endian; Boolean | últimos 2-3 bytes |

## 6. Eficiencia de la trama (consigna 4.6)

Con el MessageSize del WriteRequest de `Cliente.Rampa` **medido** en la
captura:

```powershell
python tarea-2\herramientas\eficiencia_trama.py --ua-bytes <MessageSize medido>
```

Si la cabecera TCP de la captura no mide 32 bytes, agregar
`--tcp-opciones <largo - 20>`. Resultado con los valores de la PC y discusión:
[protocolo-opcua.md §9](docs/protocolo-opcua.md) (0,98 % frente a 25 % de
MODBus RTU; 16,3 µs frente a 11,98 ms).

## 7. Modos y políticas de seguridad (consignas 4.7 y 4.8)

### 7.1 Los tres endpoints

El servidor ya ofrece los tres (Parte 2, §2). Se repite la conexión del cliente
con cada uno cambiando `config.js` → `seguridad`:

| Ensayo | `modoCliente` | `politicaCliente` |
|---|---|---|
| 1 | `'None'` | `'None'` |
| 2 | `'Sign'` | `'Basic256Sha256'` |
| 3 | `'SignAndEncrypt'` | `'Basic256Sha256'` |

Después de cada cambio: copiar a la RPi 2 y reiniciar Node-RED.

### 7.2 Establecer la confianza (primera conexión con Sign)

La primera vez **falla a propósito**: ninguna de las dos aplicaciones conoce el
certificado de la otra.

1. Pasar a Sign y reiniciar el cliente. C1 queda en rojo con un error de
   seguridad (`BadSecurityChecksFailed` o `BadCertificateUntrusted`). Anotar el
   StatusCode exacto: *pendiente*.
2. **En la RPi 1** (el servidor rechazó el certificado del cliente):

   ```bash
   $ ls ~/.node-red/opcua-pki/servidor/rejected/
   $ openssl x509 -in ~/.node-red/opcua-pki/servidor/rejected/<archivo> -noout -subject -fingerprint -sha256
   ```

   Comparar la huella con la del certificado del cliente **en la RPi 2**:

   ```bash
   $ openssl x509 -in ~/.node-red/opcua-pki/cliente/own/certs/*.pem -noout -subject -fingerprint -sha256
   ```

   (Si `openssl` no lee el archivo, agregar `-inform DER`.) Si coinciden:

   ```bash
   $ mv ~/.node-red/opcua-pki/servidor/rejected/<archivo> ~/.node-red/opcua-pki/servidor/trusted/certs/
   ```

3. **En la RPi 2**, lo mismo con el certificado del servidor, si quedó en
   `~/.node-red/opcua-pki/cliente/rejected/`.
4. `sudo systemctl restart nodered` en ambas placas. C1 pasa a verde con
   `Modo B Sign/Basic256Sha256`.

Esta comparación de huellas por un **canal independiente** (dos sesiones SSH)
es el paso que da sentido a la confianza: aceptar sin comparar equivaldría a
`automaticallyAcceptUnknownCertificate = true`.

**Capturas:** `pki_rejected.png`, `pki_huellas.png`.

### 7.3 Capturar cada modo y comparar

Para cada ensayo: Modo A, rampa del **servidor** detenida (botón **S3 · Detener
rampa**), 60 s:

```bash
$ sudo timeout 60 tcpdump -i eth0 -w ~/captura_<modo>.pcapng port 4840
```

Abrir las tres en Wireshark con el filtro `opcua` y completar (la columna "PC"
es lo verificado con los vectores reales, `prueba_opcua_tramas.py` §7):

| Campo | None | Sign | SignAndEncrypt | PC |
|---|---|---|---|---|
| MessageType, MessageSize, SecureChannelId, TokenId | *pend.* | *pend.* | *pend.* | legibles en los tres |
| SequenceNumber, RequestId | *pend.* | *pend.* | *pend.* | cifrados en SignAndEncrypt |
| Tipo de servicio (Write, Read…) | *pend.* | *pend.* | *pend.* | cifrado en SignAndEncrypt |
| NodeId y valor escrito | *pend.* | *pend.* | *pend.* | legibles en None y Sign |
| Firma al final del mensaje | *pend.* | *pend.* | *pend.* | 32 bytes en Sign y SignAndEncrypt |
| OPN | *pend.* | *pend.* | *pend.* | cifrado con RSA en Sign y SignAndEncrypt |
| Cantidad de conexiones TCP al inicio | *pend.* | *pend.* | *pend.* | 2 en Sign y SignAndEncrypt (descubrimiento + sesión) |
| Tamaño del WriteRequest de `Cliente.Rampa` | *pend.* | *pend.* | *pend.* | 114 / 146 / cifrado (relleno a bloques de 16) |

**Capturas** en `evidencia/capturas/`: `wireshark_write_none.png`,
`wireshark_write_sign.png` (árbol legible + firma),
`wireshark_write_signandencrypt.png` (*Encrypted data*).

### 7.4 Latencia por modo

Con las mismas tres capturas (comandos en
[estadisticas_captura.md §5](herramientas/estadisticas_captura.md)):

| Modo | n | mediana (ms) | p95 (ms) | máx (ms) | Tiempo de establecimiento (de SYN a ActivateSessionResponse) |
|---|---|---|---|---|---|
| None | *pend.* | | | | *pend.* |
| Sign | *pend.* | | | | *pend.* |
| SignAndEncrypt | *pend.* | | | | *pend.* |

**Hipótesis** ([seguridad.md §4](docs/seguridad.md)): en régimen, la diferencia
es menor que 1 ms (HMAC y AES sobre ~100 bytes); en el **establecimiento** es
notoria (RSA de 2048 bits en el OPN, CreateSession y ActivateSession, más la
conexión adicional de descubrimiento).

### 7.5 Rol de los certificados y trust list (consigna 4.8)

Desarrollado en [seguridad.md §3](docs/seguridad.md). La evidencia de banco es
§7.2: el rechazo inicial, la carpeta `rejected/`, la comparación de huellas y
el movimiento a `trusted/`.

## 8. Autenticación de usuario (consigna 4.9)

### 8.1 Habilitar

1. En la **RPi 1**: usuario y hash en `/etc/nodered-pdci.env`
   ([README §10](node-red/README.md)). El servidor ya acepta usuario/clave
   **además** del anónimo (`permitirAnonimo: true`).
2. En la **RPi 2**: `OPCUA_CLIENTE_USUARIO` y `OPCUA_CLIENTE_CLAVE` en
   `/etc/nodered-pdci.env`, y en `config.js`
   `seguridad.autenticacionCliente: 'usuario'`.
3. Reiniciar ambas. En el registro de la RPi 1:
   `ActivateSession usuario "operador": aceptado`.

### 8.2 Dónde viaja el token y cómo se protege

Capturar una conexión en **modo None** con usuario (procedimiento §1). En
Wireshark, filtro `opcua.servicenodeid.numeric == 467` (ActivateSessionRequest)
→ desplegar *UserIdentityToken*:

| Campo | Esperado (vectores de la PC) | Medido |
|---|---|---|
| TypeId del token | i=324 UserNameIdentityToken | *pend.* |
| PolicyId | `username_basic256Sha256` | *pend.* |
| UserName | `operador` **legible** | *pend.* |
| Password | 256 bytes **cifrados** | *pend.* |
| EncryptionAlgorithm | `…xmlenc#rsa-oaep` | *pend.* |

Explicación (RSA-OAEP con la clave pública del servidor + ServerNonce contra
*replay*): [seguridad.md §5.2](docs/seguridad.md). **Captura:**
`wireshark_activatesession_token.png`.

### 8.3 Pruebas de rechazo y de autorización

| Prueba | Cómo | Esperado | Medido |
|---|---|---|---|
| Clave incorrecta | UaExpert, Authentication *Username/Password* con clave errónea | Conexión rechazada (`BadUserAccessDenied` o `BadIdentityTokenRejected`); en la RPi 1, `clave incorrecta` sin la clave en el registro | *pend.* |
| Anónimo puede escribir (`soloAutenticadosEscriben: false`) | UaExpert anónimo escribe `Cliente.Rampa` | Good | *pend.* |
| Anónimo **no** puede escribir (`soloAutenticadosEscriben: true`, reiniciar la RPi 1) | ídem | **BadUserAccessDenied**; UserAccessLevel de `Cliente.Rampa` = 1 en *Attributes* | *pend.* |
| Usuario autenticado escribe | UaExpert con usuario y clave correctos | Good | *pend.* |

Las cuatro pasaron en la PC (pruebas de integración 13 y 15).

## 9. Lista de verificación de la Parte 4

- [ ] `captura_none.pcapng` con ARP, TCP, sesión completa y cierre.
- [ ] Tabla de secuencia (§2) y diagrama ajustado a lo medido.
- [ ] Encapsulamiento de un PublishResponse (§4).
- [ ] Cuatro tablas byte a byte (§5).
- [ ] Eficiencia recalculada con el tamaño medido (§6).
- [ ] Confianza de certificados documentada (§7.2).
- [ ] Tres capturas por modo de seguridad, tabla de legibilidad y latencias (§7.3-7.4).
- [ ] Token de identidad en Wireshark y pruebas de rechazo/autorización (§8).
- [ ] Al terminar: volver `config.js` a `None`/anónimo/Modo B si se va a usar
      así en la defensa, y dejar `soloAutenticadosEscriben` como se vaya a
      demostrar.
