# Arquitectura de red, capa física y decisiones de diseño

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Desarrolla el criterio de evaluación *"Arquitectura de red y capa física"*,
la **pregunta de análisis 5 de la Parte 1**, el objetivo específico sobre
*transportes, codificaciones y medios físicos* y las decisiones de arquitectura
del trabajo (ADR).

---

## Índice

1. [Ubicación del sistema en el modelo de Purdue](#1-ubicación-del-sistema-en-el-modelo-de-purdue)
2. [Pregunta 5: red Ethernet punto a punto sin equipos intermedios](#2-pregunta-5-red-ethernet-punto-a-punto-sin-equipos-intermedios)
3. [Direccionamiento del trabajo](#3-direccionamiento-del-trabajo)
4. [Convivencia de eth0 y wlan0](#4-convivencia-de-eth0-y-wlan0)
5. [OPC UA no tiene capa física: modelo en capas](#5-opc-ua-no-tiene-capa-física-modelo-en-capas)
6. [Transportes y medios físicos de OPC UA](#6-transportes-y-medios-físicos-de-opc-ua)
7. [Contraste con la capa física RS-485 de la Tarea 1](#7-contraste-con-la-capa-física-rs-485-de-la-tarea-1)
8. [Registro de decisiones de arquitectura (ADR)](#8-registro-de-decisiones-de-arquitectura-adr)
9. [Referencias](#9-referencias)

---

## 1. Ubicación del sistema en el modelo de Purdue

| Nivel (ISA-95 / Purdue) | En una planta | En este trabajo |
|---|---|---|
| 3 · Operaciones | MES, historiador | — |
| 2 · Supervisión | SCADA, HMI | **UaExpert** en la PC (cliente genérico) |
| 1 · Control | PLC, controladores | **RPi 1**: servidor OPC UA que expone sus E/S |
| 1 · Control | Panel o controlador par | **RPi 2**: cliente OPC UA que lee y escribe |
| 0 · Campo | Sensores, actuadores | Pulsadores y LED de cada placa |

En la Tarea 1, MODBus RTU vivía entre los niveles 0 y 1, en un bus de campo.
OPC UA nació para el borde entre los niveles 1-2 y 3: conecta controladores con
supervisión y con sistemas de información. El material de clase lo ubica así
(diapositivas 1 y 9: "OPC server" entre *controller* y *edge*). En este trabajo
se lo usa también para un intercambio par a par entre dos controladores, que
es el caso de uso de los perfiles *embedded* de IEC 62541-7.

## 2. Pregunta 5: red Ethernet punto a punto sin equipos intermedios

> *Explicar teóricamente qué se debe realizar para montar una red Ethernet
> punto a punto entre dos equipos sin dispositivos intermedios.*

### 2.1 Capa física

**Tipo de cable.** Par trenzado no blindado (UTP) categoría 5e o superior, con
conectores RJ-45. 100BASE-TX usa dos de los cuatro pares (uno para transmitir y
otro para recibir); 1000BASE-T usa los cuatro, en ambos sentidos a la vez, con
cancelación de eco (IEEE 802.3, cláusulas 25 y 40). Categoría 5e (100 MHz) es
el mínimo especificado para 1000BASE-T.

**El problema del cruce y el auto MDI-X.** En 10/100BASE-T, el par que una
interfaz usa para transmitir tiene que llegar al par que la otra usa para
recibir. Las interfaces se dividían en **MDI** (equipos terminales: PC, placa)
y **MDI-X** (switches, con el cruce hecho por dentro). Entre un equipo MDI y
un switch MDI-X alcanza con un cable **directo**; entre dos equipos MDI, como
dos Raspberry Pi, hacía falta un cable **cruzado**.

**Auto MDI-X** (*automatic MDI/MDI-X configuration*; IEEE 802.3 lo define
como opcional, cláusula 40.4.4, pero está en prácticamente todos los PHY
Gigabit actuales) resuelve esto en el PHY: cada extremo prueba durante el
arranque del enlace qué par recibe los pulsos de enlace (*link pulses*) del
otro y, si hace falta, intercambia internamente transmisión y recepción. Los
PHY de la Raspberry Pi 3B+ y 4 lo implementan, así que **cualquier cable sirve**,
directo o cruzado. (Con 1000BASE-T el cruce en sí deja de ser un problema,
porque los cuatro pares son bidireccionales; lo que el PHY resuelve es qué par
lógico es cuál.)

**Autonegociación** (IEEE 802.3, cláusula 28). Antes de transmitir datos, cada
PHY envía ráfagas de *Fast Link Pulses* que codifican sus capacidades (10/100/
1000, half/full-duplex, pausa). Los dos eligen el **mejor modo común** según un
orden de prioridad fijo. Entre una RPi 3B+ (Gigabit sobre USB 2.0, limitado en
la práctica a ~300 Mbit/s) y una RPi 4 (Gigabit nativo), el resultado esperado
es **1000 Mbit/s full-duplex**. Entre dos 3B+, también 1000/full a nivel de
enlace.

Riesgo clásico: si un extremo tiene la velocidad **fijada a mano** y el otro
negocia, el que negocia no puede detectar el modo dúplex y asume
**half-duplex**. Ese desacuerdo de dúplex (*duplex mismatch*) produce colisiones
tardías y pérdida de rendimiento sin errores visibles. Por eso se deja la
autonegociación activa en ambos extremos.

**Verificación:** `ethtool eth0` (*Speed*, *Duplex*, *Auto-negotiation*,
*Link detected*, *MDI-X*) o `ip link` (`state UP`, `LOWER_UP` = portadora
física presente).

### 2.2 Capa de enlace

**Direcciones MAC.** Cada interfaz Ethernet tiene una dirección de 48 bits
grabada de fábrica (las Raspberry Pi usan los OUI `b8:27:eb`, `dc:a6:32`,
`e4:5f:01` o `d8:3a:dd`, según el modelo). Toda trama Ethernet II lleva
**MAC de destino, MAC de origen y EtherType** (0x0800 = IPv4, 0x0806 = ARP).
Un enlace punto a punto es el dominio de difusión más chico posible: dos
equipos, sin conmutación. Cada trama que sale de una interfaz llega a la otra.

**Ethernet full-duplex no usa CSMA/CD.** Con un medio dedicado en cada sentido
no hay colisiones posibles: en modo full-duplex el MAC desactiva la detección
de portadora y de colisiones del Ethernet original. Lo que queda es, como
mucho, el control de flujo por tramas PAUSE (IEEE 802.3, cláusula 31 y anexo
31B), que se negocia en la autonegociación.

**ARP** (RFC 826) traduce una dirección IP en una MAC. Para enviar el primer
paquete a 192.168.10.1, la RPi 2 necesita la MAC de destino de la trama. Para
obtenerla:

1. Envía un **ARP Request** a la MAC de difusión `ff:ff:ff:ff:ff:ff`: *"¿quién
   tiene 192.168.10.1? Responder a 192.168.10.2"*.
2. La RPi 1 reconoce su IP y responde con un **ARP Reply** *unicast* con su MAC.
3. Ambas guardan la asociación en su tabla ARP (la RPi 1 también aprende la de
   la RPi 2 a partir del pedido). Linux la mantiene en estado `REACHABLE`
   mientras haya tráfico y la vuelve a confirmar cuando caduca.

**Verificación:** `ip neigh` después de un `ping`: debe mostrar
`192.168.10.1 dev eth0 lladdr <MAC> REACHABLE`.

### 2.3 Capa de red

**Direccionamiento estático.** En el enlace no hay servidor DHCP: si cada
interfaz quedara en modo automático, nadie le asignaría dirección. Se fija a
mano una IP de la misma subred en cada extremo.

**Máscara de subred.** `/24` (255.255.255.0) significa que los primeros 24 bits
identifican la red y los 8 restantes el equipo. Con 192.168.10.1/24 y
192.168.10.2/24 los dos equipos comparten el prefijo **192.168.10.0/24**, y el
kernel crea automáticamente una ruta *directly connected*
(`192.168.10.0/24 dev eth0 proto kernel scope link`). El rango 192.168.0.0/16
es privado (RFC 1918): nunca colisiona con direcciones públicas. Bastaría un
/30 (2 equipos útiles), pero se usa el /24 que fija la consigna.

**Por qué no hace falta puerta de enlace.** La puerta de enlace es el router al
que se envía lo que **no** pertenece a ninguna red conectada. Como el destino
(192.168.10.1) está dentro del prefijo propio, el emisor resuelve la MAC del
destino **directamente** por ARP y le entrega la trama. No hay ningún salto
intermedio. Agregar una puerta de enlace en `eth0` sería además
contraproducente: competiría con la ruta por defecto de `wlan0` y el tráfico a
internet podría intentar salir por un enlace que no lleva a ningún lado (§4).

**Qué pasaría sin IP fija: direcciones de enlace local.** Si `eth0` queda en
modo DHCP y nadie responde, después de unos segundos el sistema puede
autoasignarse una dirección **169.254.x.y/16** (IPv4 Link-Local, RFC 3927). El
equipo elige una dirección al azar en el rango, comprueba con *ARP probes* que
nadie la use y la anuncia. Si ambos extremos lo hacen, **podrían comunicarse**,
porque quedan en el mismo /16. Pero:

- la dirección **no es predecible**: cambia en cada arranque, así que no puede
  figurar en el endpoint `opc.tcp://…` de la consigna ni en un certificado;
- el RFC 3927 la limita al enlace local (no se enruta), lo cual no molesta
  aquí, pero confirma que es un mecanismo de emergencia y no de diseño;
- en Raspberry Pi OS con NetworkManager el comportamiento depende del perfil:
  el perfil por defecto `Wired connection 1` reintenta DHCP y puede **no**
  configurar link-local, y la interfaz queda sin IPv4.

Conclusión: en una red de control las direcciones se asignan de forma estática
y se documentan, igual que los Unit ID de MODBus en la Tarea 1.

**Verificación:** `ip addr show eth0` (dirección y prefijo), `ip route`
(ruta *link* sin `via`), `ping -c 5 192.168.10.1` (ida y vuelta de capa 3).

### 2.4 Qué herramienta verifica cada capa

| Capa | Qué se verifica | Herramienta | Resultado esperado |
|---|---|---|---|
| 1 · Física | Portadora, velocidad, dúplex, MDI-X | `ethtool eth0`, `ip link` | `Link detected: yes`, `Speed: 1000Mb/s`, `Duplex: Full`, `LOWER_UP` |
| 2 · Enlace | MAC propia, resolución ARP | `ip link` (MAC), `ip neigh` | `lladdr` del vecino, `REACHABLE` |
| 3 · Red | Dirección, prefijo, ruta, alcance | `ip addr`, `ip route`, `ip route get`, `ping` | 0 % de pérdida, RTT < 1 ms |
| 4 · Transporte | Puerto OPC UA escuchando, conexión establecida | `ss -tlnp`, `ss -tn` | `LISTEN 0.0.0.0:4840`; `ESTAB 192.168.10.2:x → 192.168.10.1:4840` |
| 7 · Aplicación | Intercambio OPC UA | Wireshark (filtro `opcua`), UaExpert | HEL/ACK/OPN/MSG |

Los valores medidos se registran en [PARTE-1.md](../PARTE-1.md).

## 3. Direccionamiento del trabajo

| Equipo | Rol | `eth0` | `wlan0` | Nombre |
|---|---|---|---|---|
| Raspberry Pi 1 | Servidor OPC UA | 192.168.10.1/24 | DHCP | `rpi-servidor` |
| Raspberry Pi 2 | Cliente OPC UA | 192.168.10.2/24 | DHCP | `rpi-cliente` |
| PC | UaExpert, Wireshark, SSH | — | DHCP | — |

Configuración con NetworkManager (`nmcli`), con el procedimiento completo en
[node-red/README.md §7](../node-red/README.md).

## 4. Convivencia de eth0 y wlan0

La consigna (Parte 1.4) permite mantener la Wi-Fi para internet y SSH, pero
exige que **todo el tráfico OPC UA entre las placas circule por `eth0`** y que
se demuestre.

**Por qué ocurre así.** Linux elige la ruta por **coincidencia de prefijo más
largo** (*longest prefix match*). Hacia 192.168.10.1 compiten:

| Ruta | Prefijo | Interfaz |
|---|---|---|
| `192.168.10.0/24` (conectada) | 24 bits | `eth0` |
| `default` (0.0.0.0/0) | 0 bits | `wlan0` |

Gana la de 24 bits. El perfil de `eth0` se crea con `ipv4.never-default yes`
para que NetworkManager no instale una segunda ruta por defecto a través de un
enlace que no lleva a internet.

**Dos trampas que el diseño evita:**

1. **Nombre de host en lugar de IP.** Si el cliente usara
   `opc.tcp://rpi-servidor.local:4840`, mDNS podría devolver la IP de **Wi-Fi**
   del servidor, y el tráfico iría por `wlan0` cumpliendo todo en apariencia.
   Por eso `config.opcua.endpointCliente` es la IP literal 192.168.10.1, y
   `prueba_senales.js` (prueba 8) lo verifica.
2. **La URL que anuncia el servidor.** En GetEndpoints el servidor devuelve sus
   URL con su nombre de host. Si el cliente **reconectara usando esa URL**,
   caería en la trampa 1. El cliente usa `endpointMustExist: false`: abre el
   canal siempre contra la URL configurada. El servidor anuncia además cada
   una de sus IP (`alternateHostname`), para que UaExpert pueda usar la de
   Wi-Fi.

**Demostración** (detalle en PARTE-1.md §4): `ip route get 192.168.10.1` →
`dev eth0`; `ss -tn` en el cliente → conexión desde 192.168.10.2; y
`tcpdump -i wlan0 port 4840` sin paquetes mientras `tcpdump -i eth0 port 4840`
sí muestra tráfico.

## 5. OPC UA no tiene capa física: modelo en capas

OPC UA (IEC 62541) es una **arquitectura orientada a servicios** que separa tres
cosas (IEC 62541-1 §5; material de clase, diapositiva 10):

| Capa de OPC UA | Qué define | Parte de IEC 62541 | En este trabajo |
|---|---|---|---|
| **Modelo de información** | Espacio de direcciones: nodos, atributos, referencias, tipos | Partes 3, 5, 8 | 2 objetos y 4 variables con NodeIds fijos ([modelo-informacion.md](modelo-informacion.md)) |
| **Servicios abstractos** | Qué se puede pedir: Read, Write, Browse, CreateSubscription, Publish… | Parte 4 | Read, Write, Browse, CreateSubscription, CreateMonitoredItems, Publish |
| **Mapeos de transporte** | Cómo se codifica y viaja un servicio | Parte 6 | UA Binary + UA SecureConversation + UA TCP sobre TCP/IP sobre Ethernet |

La consecuencia práctica es que **el mismo modelo de información y los mismos
servicios** pueden viajar por UA TCP binario, por HTTPS con JSON o por
WebSockets, sin cambiar una línea de la lógica de la aplicación. En MODBus, en
cambio, el formato de la trama (RTU, ASCII, TCP) está atado al servicio.

```text
 ┌────────────────────────────────────────────┐
 │ Aplicación: servidor_opcua.js / cliente    │ ← modelo de información
 ├────────────────────────────────────────────┤
 │ Servicios: Read, Write, Publish…           │ ← IEC 62541-4
 ├────────────────────────────────────────────┤
 │ Codificación: UA Binary                    │ ← IEC 62541-6 §5
 │ Seguridad: UA SecureConversation           │ ← IEC 62541-6 §6.7
 │ Transporte: UA TCP (HEL/ACK/OPN/MSG/CLO)   │ ← IEC 62541-6 §7
 ├────────────────────────────────────────────┤
 │ TCP (RFC 9293) · IPv4 (RFC 791)            │
 ├────────────────────────────────────────────┤
 │ Ethernet II (IEEE 802.3) · 1000BASE-T      │ ← la capa física la pone Ethernet
 └────────────────────────────────────────────┘
```

## 6. Transportes y medios físicos de OPC UA

### 6.1 Mapeos de transporte

| Mapeo | URL / puerto | Codificación | Modelo | Comentario |
|---|---|---|---|---|
| **UA TCP** (el de este trabajo) | `opc.tcp://` — 4840 | UA Binary | Cliente-servidor | El más eficiente y el más soportado; seguridad propia (SecureConversation) |
| HTTPS | `https://` — 443 | Binaria o JSON | Cliente-servidor | La seguridad la da TLS; atraviesa *firewalls* y proxies corporativos |
| WebSockets seguros | `opc.wss://` — 443 | Binaria o JSON | Cliente-servidor | Permite clientes en el navegador; conexión persistente (a diferencia de HTTPS) |
| PubSub sobre UDP | `opc.udp://` — 4840 multicast | UADP | Publicador-suscriptor sin *broker* | Un publicador, N suscriptores, sin sesión ni confirmaciones; seguridad por grupo de claves (SKS) |
| PubSub sobre Ethernet capa 2 | `opc.eth://` — EtherType **0xB62C** | UADP | Publicador-suscriptor determinista | Sin IP: con TSN logra latencia acotada; base de OPC UA FX (*field exchange*) |

PubSub sobre *brokers* (MQTT, AMQP) existe en IEC 62541-14, pero la consigna lo
deja fuera del alcance.

**Por qué este trabajo usa UA TCP y no PubSub:** la consigna pide analizar
sesión, canal seguro, Read frente a Subscription y Write: todos son conceptos
del modelo cliente-servidor. PubSub no tiene sesión, y el suscriptor no escribe
en el publicador.

### 6.2 Medios físicos por debajo de IP

OPC UA corre sobre cualquier medio que transporte Ethernet o IP:

| Medio | Norma | Velocidad / alcance típico | Uso industrial |
|---|---|---|---|
| Ethernet de cobre (el de este trabajo) | IEEE 802.3 100BASE-TX, 1000BASE-T | 100 m por segmento | Tableros, salas de control |
| Fibra óptica | 100BASE-FX, 1000BASE-SX/LX | 550 m (multimodo) a 10+ km (monomodo) | Distancias largas, inmunidad electromagnética total, aislación galvánica entre edificios |
| Wi-Fi | IEEE 802.11 | Decenas de metros | Equipos móviles (AGV), puesta en marcha. Latencia no determinista |
| Celular 5G | 3GPP (URLLC, 5G-LAN) | Kilómetros | Activos dispersos; 5G industrial promete latencias de ~1 ms |
| **SPE: 10BASE-T1L** / **Ethernet-APL** | IEEE 802.3cg-2019 | 10 Mbit/s, **1000 m**, **un solo par**, alimentación por el mismo par | Instrumentación de campo y zonas con riesgo de explosión (APL agrega seguridad intrínseca, IEC TS 60079-47): lleva Ethernet hasta el transmisor, donde antes había 4-20 mA + HART |
| **SPE: 10BASE-T1S** | IEEE 802.3cg-2019 | 10 Mbit/s, ~25 m, **multipunto** (PLCA) | Buses cortos entre sensores y actuadores: el reemplazo Ethernet de los buses de campo tipo RS-485/CAN |
| Ethernet con **TSN** | IEEE 802.1 (Qbv, AS, CB…) | Igual que el medio subyacente | Tiempo real determinista: planificación por ventanas de tiempo y reloj sincronizado (gPTP) |

## 7. Contraste con la capa física RS-485 de la Tarea 1

| Aspecto | RS-485 (Tarea 1, MODBus RTU) | Ethernet (Tarea 2, OPC UA) |
|---|---|---|
| Señal | Diferencial balanceada en un par: ±1,5 V mínimo en el receptor (TIA-485-A) | Diferencial en 2 o 4 pares, codificación multinivel (MLT-3 en 100BASE-TX; PAM-5 en 1000BASE-T) |
| Topología | **Bus multipunto** (hasta 32 cargas unitarias) | **Punto a punto**; varios equipos requieren un switch (estrella) |
| Dúplex | Half-duplex en 2 hilos: un solo transmisor a la vez, con conmutación DE/RE | **Full-duplex**: transmisión y recepción simultáneas, sin colisiones |
| Acceso al medio | Lo resuelve el protocolo: maestro único, sondeo por turnos | Medio dedicado por sentido; no hay arbitraje |
| Velocidad | 9600 baudios en el trabajo (hasta ~10 Mbit/s a pocos metros) | 100 Mbit/s o 1 Gbit/s: **~10 400 a ~104 000 veces más rápido** |
| Distancia | Hasta 1200 m a baja velocidad | 100 m por segmento de cobre |
| Terminación | Externa, **120 Ω en ambos extremos** del bus; polarización *fail-safe* (analizadas en T1, `arquitectura.md` §5) | Integrada en el PHY (100 Ω diferencial); el usuario no la configura |
| Niveles lógicos | El transceptor MAX485 a 5 V obligó a un divisor 2,2 k/3,3 k hacia el ESP32 | El PHY está integrado en la placa: no hay adaptación externa |
| Aislación | No incluida en el MAX485 | Transformadores de acoplamiento (*magnetics*) en cada puerto: IEEE 802.3 exige que la MDI soporte 1500 Vrms de aislación |
| Delimitación de trama | Silencio de 3,5 caracteres (t3,5) | Preámbulo + SFD, y la longitud de cada capa |
| Detección de errores | CRC-16 del protocolo MODBus | CRC-32 (FCS) de Ethernet + checksum de IP y de TCP |
| Costo por nodo | Mínimo (un transceptor de centavos de dólar) | Mayor (PHY + magnetics + switch si hay más de dos equipos) |

**Síntesis:** RS-485 es un medio barato, robusto y de larga distancia, pero
lento y compartido: obliga a un protocolo de turnos (maestro-esclavo).
Ethernet ofrece un canal dedicado y full-duplex miles de veces más rápido, lo
que permite el modelo cliente-servidor con suscripciones de OPC UA y su
sobrecarga de cabeceras, cuantificada en
[protocolo-opcua.md §9](protocolo-opcua.md). La tecnología que acerca los dos
mundos es **10BASE-T1S**: Ethernet multipunto en un par, el mismo nicho que hoy
ocupa RS-485.

## 8. Registro de decisiones de arquitectura (ADR)

### ADR-01 — Pila OPC UA: node-opcua desde function nodes, no los nodos de la paleta

| | |
|---|---|
| **Estado** | Aceptada (2026-10-13). Reemplaza la decisión del plan inicial, que proponía el Compact-Server |
| **Contexto** | El material de clase muestra `node-red-contrib-opcua-server` (Compact-Server) y `node-red-contrib-opcua`. La consigna exige NodeIds fijos en `ns=1`, EURange, tres endpoints (None, Sign y SignAndEncrypt con Basic256Sha256), autenticación por usuario, y documentar SamplingInterval, QueueSize y el StatusCode ante una desconexión |
| **Hallazgos** | Compact-Server 1.1.1: `checkUserLogon()` **devuelve siempre `true`** (acepta cualquier usuario y contraseña), depende de node-opcua 2.64 (2022) y de **vm2**, con vulnerabilidades críticas de escape del sandbox y sin mantenimiento ([INCONVENIENTES.md](../evidencia/INCONVENIENTES.md), I-03). OpcUa-Server de `node-red-contrib-opcua`: contraseñas en **texto plano** en `users.json` y un espacio de direcciones de demostración propio. OpcUa-Client: no expone los eventos de reconexión ni los valores revisados de la suscripción |
| **Decisión** | Node-RED sigue siendo el entorno de ejecución (temporizadores, GPIO, consola, editor gráfico). La pila OPC UA es **node-opcua 2.160.0** (la misma biblioteca de los nodos de la paleta, versión actual), usada desde function nodes a través de dos módulos propios: `servidor_opcua.js` y `cliente_opcua.js` |
| **Se gana** | Control explícito de cada parámetro que la consigna pide documentar; autenticación real con hash scrypt; módulos verificables en la PC (15 pruebas de integración); la API es la de la diapositiva 32 del material |
| **Se pierde** | No se arma el servidor arrastrando nodos: hay más código propio que mantener y entender para la defensa |
| **Descartado** | open62541 en C: más eficiente, pero exige compilar con mbedTLS y un ciclo de desarrollo mucho más lento; además se pidió Node-RED. python-asyncua: viable, pero fuera de Node-RED |

### ADR-02 — GPIO con pigpiod y no con `rpi-gpio`

| | |
|---|---|
| **Decisión** | Nodos `node-red-node-pi-gpiod` y demonio `pigpiod` |
| **Por qué** | PWM temporizado por **DMA**: el ciclo de trabajo no depende de la carga del CPU ni del *event loop* de Node.js. El nodo `rpi-gpio` usa RPi.GPIO, con PWM por software y jitter visible en el LED. pigpio además ofrece filtro de rebote por hardware (`set_glitch_filter`) |
| **Costo** | No soporta la Raspberry Pi 5 (chip RP1). El demonio no tiene autenticación: se lo restringe a loopback (`pigpiod -l`) |

### ADR-03 — Un único `config.js` y flujos generados

| | |
|---|---|
| **Decisión** | `config.js` es la única fuente de verdad; los `flows.json` se **generan** con `generar_flujos.js` a partir de él y del código en `*/funciones/*.js` |
| **Por qué** | Es el invariante de la Tarea 1 (`config.py`). Si los pines y períodos se tipearan en el editor, quedarían duplicados sin que nada detecte una divergencia. `prueba_flujos.js` falla si un `flows.json` no coincide con su regeneración |
| **Costo** | Un cambio hecho a mano en el editor de Node-RED se pierde en la próxima importación. Se documenta en [node-red/README.md §12](../node-red/README.md) |

## 9. Referencias

IEEE. (2022). *IEEE Standard for Ethernet* (IEEE Std 802.3-2022). IEEE.

IEEE. (2019). *Amendment 5: Physical layers specifications and management
parameters for 10 Mb/s operation and associated power delivery over a single
balanced pair of conductors* (IEEE Std 802.3cg-2019). IEEE.

Cheshire, S., Aboba, B., & Guttman, E. (2005). *Dynamic configuration of IPv4
link-local addresses* (RFC 3927). IETF. https://doi.org/10.17487/RFC3927

Eddy, W. (Ed.). (2022). *Transmission Control Protocol (TCP)* (RFC 9293).
IETF. https://doi.org/10.17487/RFC9293

International Electrotechnical Commission. (2020). *OPC Unified Architecture
— Part 6: Mappings* (IEC 62541-6:2020).

Mahnke, W., Leitner, S.-H., & Damm, M. (2009). *OPC Unified Architecture*.
Springer. https://doi.org/10.1007/978-3-540-68899-0

Plummer, D. C. (1982). *An Ethernet address resolution protocol* (RFC 826).
IETF. https://doi.org/10.17487/RFC0826

Postel, J. (1981). *Internet Protocol* (RFC 791). IETF.
https://doi.org/10.17487/RFC0791

Rekhter, Y., Moskowitz, B., Karrenberg, D., de Groot, G. J., & Lear, E.
(1996). *Address allocation for private internets* (RFC 1918). IETF.
https://doi.org/10.17487/RFC1918

Tanenbaum, A. S., & Wetherall, D. J. (2011). *Computer networks* (5.ª ed.).
Pearson.
