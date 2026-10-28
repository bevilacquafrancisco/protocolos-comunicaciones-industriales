# Guion de defensa y banco de preguntas

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Duración estricta: **12 minutos** (2 + 8 + 2), y después preguntas. Ambos
integrantes hablan. Las diapositivas acompañan: no se lee código.

La consigna menciona "canal IR", "secuencia de colores" y "sincronización RGB":
son restos de otra consigna. Este guion usa los contenidos reales de la tarea.

---

## 1. Estructura de 12 minutos

### Apertura y exordio — 2 min · *habla A*

| Tiempo | Contenido | Apoyo |
|---|---|---|
| 0:00-0:45 | **El problema:** dos controladores tienen que mantener **coherencia de estado**: cada uno replica el pulsador y la rampa del otro. En la Tarea 1 lo resolvimos con MODBus maestro-esclavo: un solo maestro, registros sin significado, sin seguridad y un bus de 9600 baudios. ¿Qué cambia si el diálogo es entre pares, con significado y con seguridad? | Diapositiva: T1 frente a T2 |
| 0:45-2:00 | **Objetivos del diseño:** (1) modelo de información autodescriptivo con NodeIds fijos; (2) intercambio bidireccional por un enlace Ethernet dedicado; (3) comparar sondeo frente a suscripción **con números**; (4) recuperarse solo ante la desconexión; (5) seguridad real: no decorativa | Diapositiva: los 5 objetivos |

### Desarrollo y cuerpo técnico — 8 min

| Tiempo | Quién | Contenido | Apoyo |
|---|---|---|---|
| 2:00-3:15 | B | **Arquitectura y flujo de datos:** enlace punto a punto /24 sin gateway; Wi-Fi solo para gestión; por qué el tráfico va por `eth0` (prefijo más largo) y las dos trampas evitadas (nombre de host, URL anunciada) | [red.md](../diagramas/red.md) |
| 3:15-4:15 | B | **Modelo de información:** objetos Servidor/Cliente, AnalogItemType con EURange, AccessLevel 1 y 3, ns=1 resuelto por URI. Diferencia con la tabla de registros | [modelo-informacion.md §2](../docs/modelo-informacion.md) |
| 4:15-5:15 | A | **Bibliotecas y el desafío principal:** Node-RED + node-opcua. **Por qué no** el nodo servidor que muestra la clase: `checkUserLogon()` devolvía siempre `true` (I-03). Lo encontramos leyendo el código | ADR-01 |
| 5:15-6:30 | A | **Demostración en vivo 1:** cada LED PWM muestra la forma de onda **de la otra placa** (sierra / triangular); pulsador → LED remoto; UaExpert conectado leyendo la tendencia | Placas + UaExpert proyectado |
| 6:30-7:30 | B | **Sondeo frente a suscripción, con números:** rampa en movimiento: casi igual tráfico (99 %); rampa detenida: 11 % de los mensajes; KeepAlive cada ~1 s. Latencia: escribir es un evento (~5 ms), leer es un muestreo (~50-100 ms) | Tabla de PARTE-3 §4 con los valores **medidos** |
| 7:30-8:45 | A | **Demostración en vivo 2: desconexión.** Desenchufar el cable ~20 s: los LED se congelan, los generadores siguen, la consola muestra `connection_lost` → `backoff`; reconectar: canal nuevo, **misma sesión**, la suscripción sobrevive | Placas + consola (`journalctl -f`) |
| 8:45-10:00 | B | **Tramas y seguridad:** un WriteRequest byte a byte (0x1234 → `34 12`); eficiencia 0,98 % frente a 25 % de MODBus pero 730 veces menos tiempo en el medio; qué queda legible en None / Sign / SignAndEncrypt; la contraseña viaja cifrada con RSA-OAEP aun en None, pero el nombre de usuario no | Wireshark proyectado |

### Cierre y peroración — 2 min · *habla A, cierra B*

| Tiempo | Contenido |
|---|---|
| 10:00-11:00 | **Síntesis:** coherencia de estado lograda en ambos sentidos (*valores medidos*); la hipótesis de que la suscripción "siempre ahorra" resultó **falsa** para señales rápidas y verdadera para estáticas; la sesión sobrevive al canal; la seguridad se verificó con pruebas, no se supuso |
| 11:00-12:00 | **Mejoras y escalabilidad:** NodeIds numéricos y agrupar valores (un Write con N valores amortiza 78 bytes de cabecera); deshabilitar None y el anónimo; CA propia en lugar de confianza manual; PubSub UADP sobre TSN para muchos consumidores o tiempo real; 10BASE-T1S como sucesor de RS-485. Volver al problema inicial: ya no hay un maestro único; cualquier cliente autorizado puede sumarse |

### Preparación de la demostración (antes de entrar)

- [ ] Ambas placas encendidas 10 min antes; chrony sincronizado.
- [ ] `config.js`: Modo B, None, anónimo (o el modo que se vaya a mostrar).
- [ ] Túneles SSH abiertos: editores en `localhost:1880` y `localhost:1881`.
- [ ] UaExpert conectado y con la tendencia armada.
- [ ] Una terminal por placa con `journalctl -u nodered -f`.
- [ ] Wireshark con una captura ya filtrada (por si falla la red de la sala).
- [ ] **Plan B:** video de la demostración grabado en el banco.

---

## 2. Banco de preguntas

Respuestas cortas para el oral; el desarrollo está en el documento indicado.

### Red y capa física

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Por qué no hace falta cable cruzado? | Auto MDI-X: el PHY detecta qué par recibe y conmuta internamente | arquitectura-red §2.1 |
| ¿Por qué no hay puerta de enlace? | El destino está en el propio prefijo /24: se resuelve la MAC por ARP y se entrega directo | §2.3 |
| ¿Qué pasa si no se asigna IP fija? | Sin DHCP, link-local 169.254/16 (RFC 3927): impredecible, cambia en cada arranque, no sirve para un endpoint ni para un certificado | §2.3 |
| ¿Cómo demuestran que el OPC UA va por `eth0`? | `ip route get`, `ss -tn`, y `tcpdump` en `wlan0` con 0 paquetes en el puerto 4840 | PARTE-1 §4 |
| ¿Por qué el endpoint del cliente es una IP y no un nombre? | mDNS podría resolver el nombre a la IP de Wi-Fi y el tráfico se desviaría sin ningún error | §4 |
| ¿Por qué `never-default`? | Para que `eth0` no instale una segunda ruta por defecto hacia un enlace sin salida a internet | §4 |
| ¿Qué pasa con la ruta al desconectar el cable? | Hipótesis verificada en el banco: NetworkManager podría quitarla; se mitiga con una ruta `prohibit` | PARTE-3 §6.1 |
| ¿RS-485 o Ethernet? | RS-485: barato, multipunto, 1200 m, lento y half-duplex. Ethernet: punto a punto, full-duplex, 10 000 veces más rápido, 100 m. 10BASE-T1S une los dos mundos | §7 |

### Modelo de información

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Por qué ns=1 y no ns=2? | node-opcua pone el applicationUri en ns=1; con `skipOwnNamespace` se registra `urn:unraf:pdci:t2` en ese índice | modelo-informacion §4 |
| ¿El cliente supone ns=1? | No: lee NamespaceArray (ns=0;i=2255) y busca la URI. El índice es local al servidor | §4 |
| ¿Por qué AnalogItemType y no una variable común? | Es el tipo de Data Access que define EURange | §2.2 |
| ¿Por qué UInt16? | 0-65535 es exactamente su rango; 2 bytes por valor | §2.2 |
| ¿Diferencia entre AccessLevel y UserAccessLevel? | El primero es del nodo; el segundo, para el usuario de la sesión. Anónimo con restricción: 3 y 1 | §2.3 |
| ¿SourceTimestamp o ServerTimestamp? | Source = cuándo lo generó el origen; Server = cuándo lo registró el servidor. Acá coinciden: mismo proceso | §6 |
| ¿Cliente-servidor no es lo mismo que maestro-esclavo? | No: con estado frente a sin estado, objetos frente a registros, y en una suscripción el servidor decide cuándo informar | §7 |

### Protocolo y tramas

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Cómo sabe el receptor dónde termina un mensaje? | Por MessageSize en la cabecera de 8 bytes. En RTU era el silencio t3,5 | protocolo-opcua §1 |
| ¿Conexión TCP, canal seguro y sesión? | Socket / aplicaciones (integridad y confidencialidad) / usuario (estado). La sesión sobrevive a un canal caído | §4 |
| ¿Para qué SequenceNumber si TCP ya ordena? | Seguridad: detecta repeticiones (*replay*) y forma parte de lo firmado. Hay un contador por sentido | §3 |
| ¿Qué empareja petición y respuesta? | RequestId (y RequestHandle en el cuerpo) | §3, §6.2 |
| ¿Cómo se codifica 0x1234? | Little-endian: `34 12`. En MODBus: big-endian, `12 34` | §5 |
| ¿Y un Boolean? | Un byte entero: `00` o `01`. En MODBus FC05, `FF 00` | §6.3 |
| ¿Por qué el WriteRequest mide 114 bytes para 2 útiles? | 24 de transporte y seguridad, 4 de TypeId, 50 de RequestHeader (23 del token), 20 del NodeId string… | §9 |
| ¿Eficiencia? | 0,98 % frente a 25 %; pero 16,3 µs frente a 11,98 ms en el medio | §9 |
| ¿Cómo la mejorarían? | NodeIds numéricos; varios valores por mensaje; PubSub UADP | §9 |
| ¿Por qué hay dos StatusCode en la respuesta? | ServiceResult (el servicio) y Results[i] (cada nodo) | §6.2 |

### Read frente a suscripción

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿La suscripción siempre ahorra tráfico? | **No.** Con la rampa cambiando cada 50 ms: 99 % de los mensajes del Read. Con la rampa quieta: 11 % | protocolo-opcua §7.3 |
| ¿Para qué el KeepAlive? | Distinguir "no hubo cambios" de "el servidor murió"; mantener viva la suscripción | §7.2 |
| ¿Por qué el cliente encola 5 PublishRequest? | El servidor solo puede responder si tiene una petición pendiente; con varias nunca se queda sin "sobres" | §7.2 |
| ¿SamplingInterval o PublishingInterval? | Cada cuánto se **mira** el nodo frente a cada cuánto se **envía** lo acumulado | §7.1 |
| ¿Por qué QueueSize 1? | Para un LED importa el último valor, no la historia | §7.1 |
| ¿Por qué el pulsador no llega más rápido con la suscripción? | Igual hay que esperar al muestreo y a la publicación; la ventaja es el tráfico, no la latencia | PARTE-3 §4.5 |
| ¿Por qué escribir es más rápido que leer? | Escribir es un evento (al cambiar); leer depende del período de sondeo o muestreo | PARTE-3 §4.5 |
| ¿Cómo midieron la latencia? | Marcas de tiempo en cada placa con relojes sincronizados por chrony sobre el propio enlace, y validación con video a 240 fps | PARTE-3 §4.5 |

### Desconexión

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Por qué los LED se congelan y no se apagan? | Sin datos, C4 no actúa: se mantiene el último valor bueno (disponibilidad primero en OT) | PARTE-3 §6 |
| ¿Por qué un corte corto puede no verse? | TCP retransmite: la conexión no se entera | §6.2 |
| ¿Qué pasa si el corte supera 30 s? | La suscripción expira (LifetimeCount 300 × 100 ms); la sesión (60 s) todavía no | §6.2 |
| ¿Por qué no se acumulan escrituras durante el corte? | Una pendiente por variable; las demás se omiten. Al volver se escribe el valor vigente | cliente_opcua.js |

### Seguridad

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Sign o SignAndEncrypt? | Sign: integridad (nadie modifica), contenido legible. SignAndEncrypt: además confidencialidad | seguridad §2, §4 |
| ¿Qué se ve en SignAndEncrypt? | MessageType, MessageSize, SecureChannelId y TokenId; nada más | §4 |
| ¿Para qué el certificado de aplicación? | Autenticar el **programa**: solo aplicaciones confiadas abren un canal seguro | §3 |
| ¿Por qué no aceptan certificados automáticamente? | Sería cifrar con un desconocido | §3 |
| ¿Dónde viaja el usuario y la clave? | En ActivateSession, UserNameIdentityToken; clave cifrada con RSA-OAEP + ServerNonce, aun en None. El nombre, legible | §5 |
| ¿Cómo guardan la clave? | Hash scrypt N = 2¹⁷ en una variable de entorno; nunca en claro ni en git | §5.3 |
| ¿Por qué no el nodo servidor de la clase? | `checkUserLogon()` devolvía siempre `true` y dependía de vm2 vulnerable | ADR-01, I-03 |
| ¿Para qué autenticar si el anónimo puede escribir? | Para nada: por eso existe `soloAutenticadosEscriben` (anónimo → BadUserAccessDenied) | §5.3 |
| ¿Cómo encaja con IEC 62443? | Zona = las placas; conducto = `eth0`; la Wi-Fi sería un conducto de gestión a separar; disponibilidad primero | §8 |

### Implementación

| Pregunta | Respuesta | Fuente |
|---|---|---|
| ¿Por qué las rampas se calculan desde el reloj? | El *event loop* no garantiza 50 ms exactos; un contador acumularía la deriva | senales.js |
| ¿Por qué pigpiod? | PWM por DMA, sin jitter; filtro de rebote por hardware | ADR-02 |
| ¿El "debounce" de 25 ms? | ¡Son µs en pigpio! Se configuró 25 000 | I-01 |
| ¿Por qué generan los `flows.json`? | Para que ningún número de `config.js` quede duplicado a mano | ADR-03 |
| ¿Cómo probaron sin las placas? | Servidor y cliente reales en la PC: 15 pruebas de integración; decodificador contra 334 mensajes reales; Node-RED real | README §1 |
