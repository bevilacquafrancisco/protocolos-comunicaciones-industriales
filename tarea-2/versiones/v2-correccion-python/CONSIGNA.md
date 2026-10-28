# Cómo cumplir toda la consigna con la versión Python

Recorrido de **Tarea_2_OPC_V26.pdf** en el orden del laboratorio. Supone la puesta en marcha de
[README.md](README.md) hecha (placas, red, programas, certificados, secretos, chrony).

> **Versión lineal con las respuestas teóricas desarrolladas:**
> [../../guia/04_resolucion_consignas.md](../../guia/04_resolucion_consignas.md). Este archivo queda
> como referencia detallada de v2.

- **Hacer:** comandos. `RPi1$` = servidor, `RPi2$` = cliente, `PC>` = PowerShell.
- **Evidencia:** lo que se guarda para el informe (`.png` = captura de pantalla, requerimiento adicional 4).
- **Teoría:** desarrollo con bibliografía ya escrito por el grupo en `../v3-node-red/docs/`. Es
  independiente de la pila salvo los **tamaños de mensaje y nombres de políticas**, que se toman
  de las capturas propias (asyncua ≠ node-opcua).

Plan de banco: **sesión 1** Partes 1 y 2 (2 h) · **sesión 2** Parte 3 (3 h) · **sesión 3** Parte 4 (2-3 h).
Los programas guardan su salida en `~/TP2_OPC/registros/` (con `./iniciar.sh`); al terminar cada
sesión, copiarla a la PC: `PC> scp -r pi@raspberry-cliente.local:~/TP2_OPC/registros evidencia\rpi2`.

---

## Parte 1 — Red Ethernet punto a punto

| # | Hacer | Evidencia |
|---|---|---|
| 1.1 | Cable directo entre las placas, sin switch | Foto del enlace y LED de link |
| 1.2 | README §5 (NetworkManager, `never-default`). Documentar el procedimiento | `nmcli connection show "$PERFIL"` (líneas `ipv4.*`) |
| 1.3 | En cada placa: `ethtool eth0` · `ip -br link` · `ip addr show eth0` · `ping -c 4 <otra IP>` · `ip neigh show dev eth0` | Salidas de texto: velocidad, dúplex, autonegociación, IP, 0 % pérdida, MAC del vecino en estado `REACHABLE` |
| 1.3 (extra) | ARP en acción: `RPi2$ sudo ip neigh flush dev eth0; sudo tcpdump -i eth0 -e -n arp & ping -c1 192.168.10.1` | Request en difusión y Reply unicast |
| 1.4 | **Con la Parte 3 funcionando**, en la RPi 2: `ip route get 192.168.10.1` → `dev eth0` · `ss -tn \| grep 4840` → socket 192.168.10.2 → 192.168.10.1 · `sudo timeout 10 tcpdump -i eth0 -n port 4840 \| wc -l` → cientos · `sudo timeout 10 tcpdump -i wlan0 -n port 4840 \| wc -l` → **0** | Las cuatro salidas |
| 1.5 | Pregunta de análisis | Teoría: `docs/arquitectura-red.md` §2 (física, enlace, red, herramienta por capa). Completar con los valores propios (1000 Mb/s full, perfil, Debian 13) |

**Por qué el tráfico va por `eth0`:** el cliente usa la IP literal 192.168.10.1, que el kernel
rutea por la ruta conectada de `eth0` (prefijo más largo que la ruta por defecto de `wlan0`), y
`never-default` impide que `eth0` compita por la ruta por defecto.

## Parte 2 — Servidor y modelo de información

`RPi1$ ./iniciar.sh servidor.py`

| # | Hacer | Evidencia |
|---|---|---|
| 2.1 | Ver en la salida los tres endpoints y `ss -tlnp \| grep 4840` → `0.0.0.0:4840` | Salida del arranque y de `ss` |
| 2.2 | Modelo en [servidor.py](servidor.py) bloque S2 | Tabla del espacio de direcciones (abajo) |
| 2.3 | Sierra de 4 s cada 50 ms (S3) | Tendencia de UaExpert (2.5) |
| 2.4 | LED digital ← `Cliente.EstadoPulsador`; LED PWM ← `Cliente.Rampa` 0-255 (S5/S6) | Prueba de escritura (2.5) |
| 2.5 a | `PC>` UaExpert → *Add Server* → `opc.tcp://<IP Wi-Fi de la RPi 1>:4840` (`RPi1$ hostname -I`) → **None / None**. Para escribir, *Authentication*: usuario `operador` y su clave; para navegar alcanza *Anonymous*. Si UaExpert es rechazado (`BadCertificateUntrusted`): `RPi1$ mv pki/rechazados/*.der pki/trusted/` y reconectar | `uaexpert_conexion.png` |
| 2.5 b | *Browse* `Objects/Servidor` y `Objects/Cliente`; para cada variable, panel *Attributes* | `uaexpert_atributos_<variable>.png` con NodeId, BrowseName, DataType, AccessLevel, Value, StatusCode, SourceTimestamp, ServerTimestamp; `uaexpert_eurange.png` |
| 2.5 c | Arrastrar `Servidor.Rampa` a *Data Access View* → botón derecho → *Trend*; medir el período | `uaexpert_tendencia_rampa.png` (sierra, 4 s) |
| 2.5 d | Escribir `Cliente.EstadoPulsador` = true/false y `Cliente.Rampa` = 0, 32768, 65535 (como `operador`) | Tabla valor → LED; foto o video |
| 2.5 e | Escribir `Servidor.Rampa` | `uaexpert_solo_lectura.png`: **BadUserAccessDenied** (0x801F0000) |
| 2.6 | Pregunta de análisis | Teoría: `docs/modelo-informacion.md` §7. Argumento propio: UaExpert navegó el servidor y obtuvo tipos, acceso y rango **sin configuración previa** |

**Tabla del espacio de direcciones (para el informe):**

| NodeId | BrowseName | DataType | AccessLevel | Origen | EURange |
|---|---|---|---|---|---|
| `ns=1;s=Servidor.EstadoPulsador` | 1:EstadoPulsador | Boolean (i=1) | 1 (CurrentRead) | Pulsador RPi 1 | — |
| `ns=1;s=Servidor.Rampa` | 1:Rampa | UInt16 (i=5) | 1 | Sierra RPi 1 | 0..65535 |
| `ns=1;s=Cliente.EstadoPulsador` | 1:EstadoPulsador | Boolean | 3 (Read+Write) | Escrita por RPi 2 | — |
| `ns=1;s=Cliente.Rampa` | 1:Rampa | UInt16 | 3 | Escrita por RPi 2 | 0..65535 |

Servicios usados: GetEndpoints, OpenSecureChannel, CreateSession, ActivateSession, Browse (UaExpert),
Read, Write, CreateSubscription, CreateMonitoredItems, Publish, CloseSession, CloseSecureChannel.

**Por qué `BadUserAccessDenied` y no `BadNotWritable` (2.5 e):** la especificación usa
`BadNotWritable` cuando el *AccessLevel* no permite escribir y `BadUserAccessDenied` cuando lo
impide el *UserAccessLevel*. asyncua comprueba los dos juntos y responde siempre el segundo.
Es un comportamiento de la biblioteca: registrarlo y explicarlo.

**Por qué ns=1:** asyncua reserva el índice 1 para el ApplicationUri del servidor; usar
`urn:unraf:pdci:t2` como ApplicationUri deja el modelo en ns=1. Aplicación y modelo son conceptos
distintos (`docs/modelo-informacion.md` §4); el servidor verifica al arrancar que quedó en 1.

## Parte 3 — Cliente e intercambio bidireccional

`RPi1$ ./iniciar.sh servidor.py` · `RPi2$ ./iniciar.sh cliente_suscripcion.py`

| # | Hacer | Evidencia |
|---|---|---|
| 3.1 | El cliente conecta a la IP de `eth0` (C1) | `[C1] Sesion activa` en el registro; prueba 1.4 |
| 3.2 | Triangular de 8 s (C2). Mirar los dos LED PWM: la RPi 2 muestra la **sierra** y la RPi 1 la **triangular** | Video corto de las dos placas |
| 3.3 | Pulsador ↔ LED digital en los dos sentidos; rampas ↔ LED PWM | Tabla de las 4 pruebas funcionales (README §8) |
| 3.5 | Dejar 60 s ambas placas | `registros/servidor_*.log` (`[S7]`) y `registros/cliente_*.log` (`[C6]`): rampa generada, recibida y SourceTimestamp |

### 3.4 Lectura cíclica frente a suscripción

Capturar **en la RPi 2**, 60 s de régimen cada una (iniciar el cliente, esperar 5 s, recién entonces
capturar):

```bash
RPi2$ ./iniciar.sh cliente.py                  # Modo A; en otra terminal SSH:
RPi2$ sudo timeout 60 tcpdump -i eth0 -w ~/captura_modo_A.pcapng port 4840
RPi2$ ./iniciar.sh cliente_suscripcion.py      # Modo B
RPi2$ sudo timeout 60 tcpdump -i eth0 -w ~/captura_modo_B.pcapng port 4840
# KeepAlive: RPi1$ ./iniciar.sh servidor.py --rampa-detenida, pulsadores en reposo
RPi2$ ./iniciar.sh cliente.py --sin-escritura              -> captura_modo_A_quieto.pcapng
RPi2$ ./iniciar.sh cliente_suscripcion.py --sin-escritura  -> captura_modo_B_quieto.pcapng
```

Conteo en la PC con tshark (comandos en `../v3-node-red/herramientas/estadisticas_captura.md`
§1-3): tramas y bytes totales (`-z io,stat,0`) y por servicio.

**Parámetros (documentar los revisados, de la trama):** `CreateSubscriptionResponse` →
RevisedPublishingInterval, RevisedMaxKeepAliveCount, RevisedLifetimeCount;
`CreateMonitoredItemsResponse` → RevisedSamplingInterval, RevisedQueueSize. El cliente imprime los de
la suscripción en `[C3]`.

| Parámetro | Pedido | Justificación |
|---|---|---|
| PublishingInterval | 100 ms | Lo pide la consigna |
| SamplingInterval | 100 ms | Igual al de publicación: muestrear más rápido no se publicaría |
| QueueSize | 1 | Solo interesa el último valor (LED) |
| MaxKeepAliveCount | 10 | KeepAlive cada 1 s sin cambios: visible en 60 s (el valor por defecto de asyncua da 7,5 min) |
| LifetimeCount | 300 | 30 s sin PublishRequest → el servidor borra la suscripción; IEC 62541-4 pide ≥ 3 × KeepAlive |

**Predicción medida en la PC** (proxy contador, 10 s de régimen, asyncua 2.1.0; el banco debe dar
proporciones parecidas — si no, es un hallazgo a explicar):

| Escenario | Modo A: mensajes / bytes UA | Modo B: mensajes / bytes UA | B / A |
|---|---|---|---|
| Rampa en movimiento, escrituras activas | 418 / 44 811 | 420 / 39 790 | 100 % / 89 % |
| Rampa detenida, sin escrituras | 220 / 27 890 | 38 / 3 091 | **17 % / 11 %** |

Lectura: con la rampa cambiando cada 50 ms, cada publicación de 100 ms trae datos y B no ahorra
mensajes (solo bytes: el PublishResponse lleva únicamente lo que cambió). Con el proceso quieto, B
envía un PublishResponse vacío (KeepAlive) por segundo y A sigue preguntando 10 veces por segundo.
En las dos capturas hay además un **Read de ServerStatus por segundo**: es el *watchdog* del
cliente asyncua (detecta la caída del canal), no parte del Modo A.

**Publish / KeepAlive:** el cliente mantiene PublishRequest pendientes en el servidor; el servidor
responde uno por cada intervalo con datos, o uno vacío (`NotificationMessage` sin notificaciones)
cada MaxKeepAliveCount intervalos. Teoría: `docs/protocolo-opcua.md` §7.2. Evidencia: en
`captura_modo_B_quieto` el período entre PublishResponse ≈ 1 s (estadisticas_captura.md §3).

**Latencia pulsador → LED (relojes con chrony, README §7):** las dos placas imprimen
`LATENCIA pulsador_local=…` en el flanco y `LATENCIA led_digital=…` al cambiar el LED.
20 pulsaciones por caso, en los dos sentidos y en los dos modos:

```powershell
PC> python ..\v3-node-red\herramientas\medir_latencia.py evidencia\rpi1\servidor_X.log evidencia\rpi2\cliente_Y.log   # RPi 1 → RPi 2
PC> python ..\v3-node-red\herramientas\medir_latencia.py evidencia\rpi2\cliente_Y.log evidencia\rpi1\servidor_X.log   # RPi 2 → RPi 1
```

Informar mínimo, mediana, p95 y máximo, con el `System time` de `chronyc tracking` como cota de
error. Hipótesis a contrastar: RPi 1 → RPi 2 entre unos pocos ms y ~100 ms, uniforme (en Modo B se
espera el próximo ciclo de publicación; en Modo A, el próximo Read); RPi 2 → RPi 1, pocos ms (el
Write sale en el flanco y el servidor enciende el LED al aceptarlo, sin sondeo).

### 3.6 Prueba de desconexión

Previo: con el cable desconectado, `RPi2$ ip route get 192.168.10.1` debe seguir por `eth0`. Si sale
por `wlan0`, NetworkManager quitó la ruta: agregar en las dos placas
`sudo nmcli connection modify "$PERFIL" +ipv4.routes "192.168.10.0/24 type=prohibit metric=4000"`
y registrarlo como inconveniente (`../v3-node-red/PARTE-3.md` §6.1).

Con Modo B en marcha, tres cortes: **~5 s**, **~20 s** y **~45 s**.

| Qué observar | Dónde |
|---|---|
| LED PWM de cada placa congelado; generador local sigue | Video; `[C6] generada=` cambia y la línea termina en `SIN CONEXION (LED congelados)`; en el servidor `[S7] generada=` cambia y `recibida` queda fija |
| StatusCode / error informado y hora | `[C3] Estado de la suscripcion: BadShutdown` y `[C7] TRANSPORTE TimeoutError` (con el cable cortado no llega ningún StatusCode del servidor: vence el *watchdog* de 1 s) |
| Recuperación | `[C1] Conectando…` cada 2 s; al reconectar: `[C1] Sesion activa`, `[C3]` suscripción nueva |

Comportamiento de la sesión, para el informe: el cliente **abre canal y sesión nuevos** y crea una
suscripción nueva; no reactiva la sesión anterior. La sesión vieja queda en el servidor hasta su
timeout (60 s, pedido por el cliente) y su suscripción hasta el Lifetime (30 s). El corte corto puede
no producir ningún error si TCP retransmite antes de que venza el watchdog: es un resultado válido.
Verificado en la PC con un proxy que retiene el tráfico: detección en 1-2 s, cierre local 4 s
después (CloseSession sin respuesta) y nueva sesión ~2 s después de volver el enlace.

**3.7 (opcional):** `--gamma` en las dos placas; comparar a simple vista. Teoría: el ojo responde de
forma aproximadamente logarítmica (ley de Stevens), por eso una rampa lineal de ciclo de trabajo
parece subir rápido al principio y quedarse plana arriba; `255·(v/65535)^2,2` compensa.

## Parte 4 — Tramas y seguridad

### 4.1-4.3 Sesión completa en modo None y secuencia

```bash
RPi1$ sudo ip neigh flush dev eth0
RPi2$ sudo ip neigh flush dev eth0
RPi2$ sudo tcpdump -i eth0 -w ~/captura_none.pcapng &      # todo eth0: incluye ARP
RPi2$ ./iniciar.sh cliente_suscripcion.py                    # ~15 s, presionar los pulsadores
#     Ctrl+C (cierre ordenado)
RPi2$ sudo pkill tcpdump
PC>   scp pi@raspberry-cliente.local:~/captura_none.pcapng evidencia\
```

Wireshark, filtro `opcua || arp || tcp.flags.syn==1 || tcp.flags.fin==1`. Secuencia verificada en la
PC con este código:

| Conexión | Mensajes | Origen |
|---|---|---|
| — | ARP request (difusión) / reply | RPi 2 / RPi 1 |
| TCP 1 (descubrimiento) | SYN, SYN-ACK, ACK · **HEL / ACK** · **OPN** · **GetEndpoints** · **CLO** · FIN | cliente / servidor alternados |
| TCP 2 (sesión) | SYN… · HEL / ACK · OPN · **CreateSession** · **ActivateSession** · **CreateSubscription** · **CreateMonitoredItems** · **Publish** y **Write** intercalados · Read de ServerStatus (1/s) · **CloseSession** · **CLO** · FIN | — |

Diagrama: adaptar `../v3-node-red/diagramas/secuencia_sesion.md` a esta tabla (dos conexiones
TCP). Diferencia entre conexión TCP, canal seguro y sesión: `docs/protocolo-opcua.md` §4.

### 4.4-4.6 Encapsulamiento, byte a byte y eficiencia

| # | Hacer | Herramienta |
|---|---|---|
| 4.4 | Elegir un PublishResponse con `Servidor.Rampa`; *Copy → …as Hex Stream* | `python ..\v3-node-red\herramientas\opcua_tramas.py --ethernet "<hex>"` decodifica Ethernet II, IPv4, TCP y OPC UA |
| 4.5 | Un WriteRequest/WriteResponse sobre `Cliente.Rampa` y otro sobre `Cliente.EstadoPulsador` | `opcua_tramas.py --markdown "<hex>"`: tabla campo a campo (cabecera, SecureChannelId, TokenId, SequenceNumber, RequestId, NodeId de servicio, RequestHeader, NodeId, AttributeId, máscara del DataValue, Variant) |
| 4.6 | MessageSize del WriteRequest de `Cliente.Rampa` medido | `python ..\v3-node-red\herramientas\eficiencia_trama.py --ua-bytes <MessageSize>` (compara con MODBus RTU de la Tarea 1) |

Detalle propio de esta versión (medido en la PC): el cliente escribe un **DataValue con
SourceTimestamp**, así el servidor sabe cuándo se generó el dato. asyncua lo codifica con máscara
`0x07` (valor + StatusCode Good + SourceTimestamp): el WriteRequest de `Cliente.Rampa` mide
**107 bytes** y el de `Cliente.EstadoPulsador` 115; la WriteResponse, 64. Escribir solo el valor
(máscara `0x01`) ahorraría 12 bytes (4 de StatusCode + 8 de DateTime): mencionarlo en 4.5 y 4.6.
La word viaja little-endian (15586 = `0x3CE2` → `e2 3c`) y el Boolean ocupa 1 byte (`00`/`01`).
Teoría de la codificación: `docs/protocolo-opcua.md` §5-6 y §8-9 (los tamaños de ese documento son
de node-opcua; usar los propios).

### 4.7-4.8 Tres endpoints, certificados y confianza

El servidor ya ofrece None, Sign y SignAndEncrypt con Basic256Sha256. Procedimiento de confianza:

1. `RPi2$ ./iniciar.sh cliente_suscripcion.py --seguridad Sign` → **rechazado**:
   `[C7] StatusCode=BadCertificateUntrusted`; en el servidor `[S1] Certificado NO confiable … SHA256=…`
   y el archivo en `pki/rechazados/`. 📁 ambas salidas.
2. Comparar huellas: `RPi1$ openssl x509 -inform DER -in pki/rechazados/<archivo>.der -noout -fingerprint -sha256`
   y `RPi2$ openssl x509 -inform DER -in pki/own/cliente_cert.der -noout -fingerprint -sha256`. 📁
3. Iguales → `RPi1$ mv pki/rechazados/<archivo>.der pki/trusted/cliente_cert.der`.
4. Reintentar: conecta (no hace falta reiniciar el servidor). Repetir con `--seguridad SignAndEncrypt`.

Capturas por modo (Modo A, `RPi1$ … --rampa-detenida`, 60 s): `captura_none`, `captura_sign`,
`captura_signandencrypt`.

| Qué mostrar en Wireshark | None | Sign | SignAndEncrypt |
|---|---|---|---|
| MessageType, MessageSize, SecureChannelId, TokenId | legibles | legibles | legibles |
| SequenceNumber, RequestId, servicio, NodeId, valor | legibles | legibles | **cifrados** |
| Firma (32 bytes HMAC-SHA256) al final | — | sí | sí |
| OPN | en claro | firmado/cifrado con RSA | firmado/cifrado con RSA |

Latencia por modo: `../v3-node-red/herramientas/latencia_captura.py` sobre cada captura
(estadisticas_captura.md §5). Hipótesis: diferencia < 1 ms en régimen (HMAC y AES sobre ~100 bytes),
notoria en el establecimiento (RSA 2048). Teoría de certificados X.509 y trust list:
`docs/seguridad.md` §2-4.

### 4.9 Usuario y contraseña además del anónimo

| Prueba | Comando | Resultado esperado (verificado en la PC) |
|---|---|---|
| Anónimo | `./iniciar.sh cliente.py --anonimo` | Lee; `Write … rechazado: BadUserAccessDenied` (una vez); la sesión sigue |
| Usuario correcto | `./iniciar.sh cliente.py` | Lee y escribe |
| Clave incorrecta | editar temporalmente `OPCUA_CLIENTE_CLAVE` | `[C7] StatusCode=BadUserAccessDenied` en ActivateSession; el servidor registra el usuario, nunca la clave |

**Dónde viaja el token:** en el **ActivateSessionRequest**, campo `UserIdentityToken`
(`UserNameIdentityToken`, i=324). El nombre de usuario va legible; la contraseña va **cifrada con
RSA-OAEP con la clave pública del certificado del servidor**, junto con el `ServerNonce` de la
CreateSessionResponse (impide reenviarla en otra sesión). En el endpoint None asyncua anuncia para el
token la política Basic256Sha256, así que la clave tampoco viaja en claro en modo None; en
SignAndEncrypt la protege el canal. Verificarlo en `captura_none` (campo `EncryptionAlgorithm`).
Teoría: `docs/seguridad.md` §5.

**Diseño de autorización:** anónimo = leer, navegar y suscribirse; `operador` = además escribir
(mínimo privilegio, IEC 62443-3-3 SR 2.1). Sin esta regla autenticar no cambiaría nada. La clave se
guarda como hash scrypt (N = 2¹⁷, OWASP) y se compara en tiempo constante.

## Requerimientos adicionales

| # | Dónde |
|---|---|
| 1. Diagrama de red y conexionado | [diagramas/red.md](diagramas/red.md) + foto de cada placa |
| 2. Diagramas de flujo | [diagramas/flujo_servidor.md](diagramas/flujo_servidor.md) (S1-S7) · [diagramas/flujo_cliente.md](diagramas/flujo_cliente.md) (C1-C7) |
| 3. Trazabilidad de código | Cada sección del código está marcada `BLOQUE Sx` / `BLOQUE Cx`; tabla de trazabilidad al pie de cada diagrama |
| 4. Capturas `.png` | Carpeta `evidencia/` junto al informe |
| Librerías: parámetros, funciones con tipos y retorno (*Aclaraciones*) | Tabla siguiente + docstrings del código |

| Biblioteca · función | Parámetros (tipo) | Retorna |
|---|---|---|
| `asyncua.Server.set_endpoint(url)` | `str` | `None` |
| `Server.set_application_uri(uri)` | `str` | `None` (async) |
| `Server.get_namespace_index(uri)` | `str` | `int` |
| `Server.set_security_policy(policies, permission_ruleset)` | `list[SecurityPolicyType]`, `PermissionRuleset` | `None` |
| `Server.load_certificate(path)` / `load_private_key(path)` | `str` | `None` (async) |
| `Server.set_certificate_validator(fn)` | `async (x509.Certificate, ApplicationDescription) -> None` | `None` |
| `Server.subscribe_server_callback(CallbackType.PostWrite, fn)` | `fn(ServerItemCallback, CallbackService)` | `None` |
| `Node.add_object(nodeid, bname)` / `add_variable(nodeid, bname, val)` | `NodeId`, `QualifiedName`, `Variant` | `Node` |
| `Node.add_property(nodeid, bname, val, datatype=)` | ídem + `NodeId` | `Node` |
| `Node.set_writable()` | — | `None` (AccessLevel = 3) |
| `Node.write_value(value)` | `Variant` o `DataValue` | `None`; lanza `UaStatusCodeError` si el servidor rechaza |
| `asyncua.Client(url, timeout, watchdog_intervall)` | `str`, `float` s, `float` s | `Client` |
| `Client.connect_and_get_server_endpoints()` | — | `list[EndpointDescription]` |
| `Client.set_security(policy, certificate, private_key, server_certificate, mode)` | clase de política, rutas `str`, `MessageSecurityMode` | `None` |
| `Client.set_user(str)` / `set_password(str)` / `connect()` / `disconnect()` | — | `None` |
| `Client.read_attributes(nodes)` | `list[Node]` | `list[DataValue]` (Value, StatusCode, SourceTimestamp, ServerTimestamp) |
| `Client.create_subscription(params, handler)` | `CreateSubscriptionParameters`, objeto con `datachange_notification(node, val, data)` | `Subscription` |
| `Subscription.subscribe_data_change(nodes, sampling_interval, queuesize)` | `list[Node]`, `float` ms, `int` | `list[int]` (handles) |
| `gpiozero.Button(pin, pull_up, bounce_time)` | `int`, `bool`, `float` s | `Button` (`is_pressed`, `when_pressed`, `when_released`) |
| `gpiozero.LED(pin)` · `PWMLED(pin)` | `int` | `.value`: `bool` / `float` 0.0-1.0 |

## Informe y defensa

| Requisito | Cómo |
|---|---|
| PDF `Apellido1_Apellido2_PdCI_T2_26.pdf`, Arial 11, justificado, márgenes 3 / 2,5 cm, interlineado 1,5, APA 7 | Plantilla del informe |
| Arquitectura de red y capa física · modelo de información · análisis de tramas · diseño lógico | Partes 1, 2 y 4 + diagramas de esta carpeta |
| Códigos y diagramas junto al informe | Esta carpeta (sin `pki/` ni `~/.pdci-t2.env`) |
| Defensa de 12 min (2 + 8 + 2) | Guion y banco de preguntas: `../v3-node-red/defensa/guion.md`. La consigna menciona "canal IR", "RGB" y "secuencia de colores": son restos de otra consigna; se defiende con el contenido real (pulsador/rampa ↔ LED, latencias, desconexión) |
| Declaración de uso de IA | Si la cátedra lo pide |

Demostración en vivo sugerida (3 min): servidor + Modo B → pulsadores y rampas cruzadas → cortar el
cable 20 s (LED congelados, consola `SIN CONEXION`, generador sigue) → reconectar (sesión nueva) →
`--seguridad SignAndEncrypt` mostrando en Wireshark una captura preparada.
