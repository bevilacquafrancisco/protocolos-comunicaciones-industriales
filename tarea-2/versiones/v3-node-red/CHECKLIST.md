# Checklist de la Tarea 2 — de punta a punta

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Recorrido **completo** de la consigna, en el orden en que conviene hacerlo en el
laboratorio. El hardware (dos Raspberry Pi, protoboards, pulsador, LED digital y
LED PWM) **se arma una sola vez y sirve para las cuatro partes**: no hay que
desarmar nada entre una parte y otra.

**Cómo usarlo**

- Tildar cada casilla (`- [ ]` → `- [x]`) recién cuando la **evidencia** está
  guardada: un dato que no quedó registrado no sirve para el informe.
- Cada ítem dice **dónde está explicado** (→) y **qué guardar** (📁).
- La evidencia de las placas se copia a la PC al terminar cada sesión, **antes**
  de restaurar las microSD del laboratorio (§9).
- Los ítems marcados **(consigna X.Y)** son requisitos textuales: no se pueden
  omitir. Los marcados *(recomendado)* no los pide la consigna, pero sostienen
  el informe o la defensa.

**Plan de sesiones sugerido**

| Sesión | Contenido | Duración aproximada |
|---|---|---|
| 0 | En casa, con la PC: §0 | — |
| 1 | Respaldo de las microSD, puesta a punto y Parte 1: §1 y §2 | 3 h |
| 2 | Partes 2 y 3: §3 y §4 | 3 h |
| 3 | Parte 4 y repeticiones: §5 | 2-3 h |

---

## 0. Antes de ir al laboratorio (en la PC)

- [ ] **Pruebas en verde** en la PC: `prueba_senales.js` (9), `prueba_flujos.js` (12), `prueba_opcua_tramas.py` (82) y `prueba_integracion_opcua.js` (15)
      → [README §5](README.md) · 📁 captura de la salida
- [ ] **Software instalado:** Raspberry Pi Imager, Win32 Disk Imager, Wireshark (con tshark), UaExpert, OpenSSH; clave SSH creada
      → [node-red/README.md §3](node-red/README.md)
- [ ] **Hash de la clave del editor** de Node-RED y **clave del usuario OPC UA** decididas (no se escriben en ningún archivo del repo)
      → [node-red/README.md §10.1](node-red/README.md)
- [ ] **Red Wi-Fi** para el banco: punto de acceso del teléfono, WPA2 personal
      → [node-red/README.md §2](node-red/README.md)
- [ ] Espacio libre en la PC para los **respaldos** de las microSD (el tamaño de cada tarjeta)
- [ ] Carpeta `tarea-2/node-red` al día: si se tocó `config.js`, ejecutar `node tarea-2/node-red/generar_flujos.js`
- [ ] **Informe preliminar** entregado, si la cátedra lo pide antes del banco: explicación de la solución, diagrama de flujo, tipo de comunicación y orden de los datos en las tramas *(sección "Fechas" de la consigna)*
      → [diagramas/](diagramas/) · [docs/protocolo-opcua.md §5-6](docs/protocolo-opcua.md)

## 1. Preparar las placas del laboratorio

- [ ] **Autorización** para regrabar las microSD del laboratorio
      → [node-red/README.md §4.1](node-red/README.md)
- [ ] Modelo de cada placa anotado (⚠️ si es una RPi 5, detenerse y decidir)
- [ ] **Respaldo verificado** de las dos microSD (`.img` + SHA256 + *Verify Only*)
      → [node-red/README.md §4.1](node-red/README.md) · 📁 tabla de respaldos completa
- [ ] microSD grabadas con Raspberry Pi OS Lite 64-bit Bookworm (`rpi-servidor` / `rpi-cliente`, usuario `pdci`, SSH con clave)
      → [node-red/README.md §4.2](node-red/README.md)
- [ ] SSH a las dos placas
      → [node-red/README.md §5](node-red/README.md)
- [ ] Sistema actualizado; `apt policy pigpio` con versión candidata; `pigpio`, `tcpdump`, `ethtool`, `chrony` instalados; `pigpiod` escuchando **solo en 127.0.0.1:8888**
      → [node-red/README.md §6](node-red/README.md) · 📁 salida de `ss -tlnp | grep 8888`
- [ ] Node-RED instalado como servicio; versiones de Node.js y Node-RED anotadas
      → [node-red/README.md §8](node-red/README.md) · 📁 versiones
- [ ] Carpeta copiada a `/home/pdci/pdci-t2` en las dos placas; `node-opcua@2.160.0` y `node-red-node-pi-gpiod@0.5.1` instalados; `npm audit` revisado
      → [node-red/README.md §9](node-red/README.md) · 📁 resumen de `npm audit`
- [ ] Secretos en `/etc/nodered-pdci.env` (permisos 600); `EnvironmentFile` en el servicio; `settings.js` con `...pdci.ajustes` al final; **sin** líneas `[pdci-t2] ATENCION` en el registro
      → [node-red/README.md §10](node-red/README.md)
- [ ] **Conexionado** idéntico en las dos placas, con la placa apagada: pulsador GPIO17 (pin 11) a GND; LED digital GPIO27 (pin 13); LED PWM GPIO18 (pin 12); resistencias en serie
      → [node-red/README.md §11](node-red/README.md) · [diagramas/red.md §2](diagramas/red.md) · 📁 **foto del conexionado de cada placa**

## 2. Parte 1 — Red Ethernet punto a punto

- [ ] **(consigna 1.1)** Cable Ethernet directo entre las placas, sin switch ni router; LED de enlace encendidos
      → [PARTE-1.md §1](PARTE-1.md) · 📁 foto
- [ ] **(consigna 1.2)** IP fija con NetworkManager: RPi 1 = 192.168.10.1/24, RPi 2 = 192.168.10.2/24; perfil `pdci-eth0` con `never-default`; persiste tras `sudo reboot`
      → [PARTE-1.md §2](PARTE-1.md) · [node-red/README.md §7](node-red/README.md) · 📁 `nmcli con show pdci-eth0`
- [ ] **(consigna 1.3)** Estado del enlace, velocidad y dúplex: `ethtool eth0` / `ip link`
      → [PARTE-1.md §3](PARTE-1.md) · 📁 `evidencia/parte1/ethtool_*.txt`
- [ ] **(consigna 1.3)** Direcciones asignadas: `ip addr`
      → 📁 `evidencia/parte1/ipaddr_*.txt`
- [ ] **(consigna 1.3)** Conectividad: `ping` en los dos sentidos
      → 📁 `evidencia/parte1/ping_*.txt`
- [ ] **(consigna 1.3)** Tabla ARP después del ping: `ip neigh`
      → 📁 `evidencia/parte1/ipneigh_*.txt`
- [ ] *(recomendado)* ARP en acción con `tcpdump -e arp`
      → [PARTE-1.md §3.2](PARTE-1.md) · 📁 `arp_tcpdump.txt`
- [ ] Tabla de resultados de [PARTE-1.md §3.1](PARTE-1.md) completa
- [ ] **(consigna 1.4)** Demostración de que el OPC UA va por `eth0` con la Wi-Fi activa (**se hace después de la Parte 3**, con el sistema funcionando): `ip route get`, `ss -tn`, `tcpdump` en `eth0` y en `wlan0`
      → [PARTE-1.md §4](PARTE-1.md) · 📁 salidas de las cuatro pruebas
- [ ] **(consigna 1.5)** Pregunta de análisis: física (cable, auto MDI-X, autonegociación), enlace (MAC, ARP), red (estática, máscara, sin gateway, 169.254/16) y herramienta por capa
      → [docs/arquitectura-red.md §2](docs/arquitectura-red.md)

## 3. Parte 2 — Servidor OPC UA y modelo de información

- [ ] **(consigna 2.1)** Servidor en la RPi 1 con `servidor/flows.json`; `opc.tcp://192.168.10.1:4840`; escucha en todas las interfaces (`LISTEN 0.0.0.0:4840`); seis líneas `Endpoint:` en el registro
      → [PARTE-2.md §2](PARTE-2.md) · 📁 registro y `ss -tlnp`
- [ ] **(consigna 2.2)** Namespace `urn:unraf:pdci:t2` en **ns=1**; objetos `Servidor` y `Cliente`; las cuatro variables con NodeId, tipo y acceso de la tabla
      → [docs/modelo-informacion.md §2](docs/modelo-informacion.md)
- [ ] **(consigna 2.2)** Propiedad **EURange** (0 a 65535) en las dos `Rampa`
- [ ] **(consigna 2.3)** Rampa diente de sierra 0-65535, período 4 s, actualizada cada 50 ms
      → [diagramas/flujo_servidor.md](diagramas/flujo_servidor.md) bloque S3
- [ ] **(consigna 2.4)** LED digital ← `Cliente.EstadoPulsador`; LED PWM ← `Cliente.Rampa` escalada a 0-255
      → bloque S6
- [ ] **(consigna 2.5)** UaExpert conectado desde la PC por la IP **Wi-Fi** de la RPi 1, en modo **None** / Anonymous
      → [PARTE-2.md §3.1](PARTE-2.md) · 📁 `uaexpert_conexion.png`
- [ ] **(consigna 2.5)** Browse y atributos de cada variable: NodeId, BrowseName, DataType, AccessLevel, Value, StatusCode, SourceTimestamp, ServerTimestamp
      → [PARTE-2.md §3.2](PARTE-2.md) · 📁 `uaexpert_browse.png`, `uaexpert_atributos_*.png`, `uaexpert_eurange.png`
- [ ] **(consigna 2.5)** `Servidor.Rampa` en la **vista de tendencia**: forma de onda y período medidos
      → [PARTE-2.md §3.3](PARTE-2.md) · 📁 `uaexpert_tendencia_rampa.png`
- [ ] **(consigna 2.5)** Escribir `Cliente.EstadoPulsador` y `Cliente.Rampa` desde UaExpert y ver la respuesta de los LED
      → [PARTE-2.md §3.4](PARTE-2.md) · 📁 tabla completa
- [ ] **(consigna 2.5)** Escribir una variable de solo lectura y registrar el **StatusCode** (se espera `BadNotWritable`)
      → [PARTE-2.md §3.5](PARTE-2.md) · 📁 `uaexpert_bad_not_writable.png`
- [ ] **(consigna 2.6)** Pregunta de análisis: cliente-servidor frente a maestro-esclavo; navegar frente a tabla de registros
      → [docs/modelo-informacion.md §7](docs/modelo-informacion.md)

## 4. Parte 3 — Cliente e intercambio bidireccional

**Antes de medir:** relojes sincronizados con chrony (RPi 1 como servidor NTP
por `eth0`) → [node-red/README.md §14](node-red/README.md). 📁 `chronyc tracking`

- [ ] **(consigna 3.1)** Cliente en la RPi 2 con `cliente/flows.json`, conectado por `eth0`; nodo C1 en verde
      → [PARTE-3.md §1](PARTE-3.md)
- [ ] **(consigna 3.2)** Rampa triangular 0-65535, 8 s (4 + 4), cada 50 ms
      → bloque C2
- [ ] **(consigna 3.2)** Prueba visual: cada LED PWM muestra la forma de onda **de la otra placa** (sierra en la RPi 2, triangular en la RPi 1)
      → [PARTE-3.md §2](PARTE-3.md) · 📁 video corto de las dos placas
- [ ] **(consigna 3.3)** Lectura y replicación: `Servidor.EstadoPulsador` → LED digital de la RPi 2; `Servidor.Rampa` → LED PWM de la RPi 2
- [ ] **(consigna 3.3)** Escritura: `Cliente.EstadoPulsador` solo **al cambiar**; `Cliente.Rampa` cada **100 ms**; verificado en la captura
      → [PARTE-3.md §5](PARTE-3.md) · 📁 tabla completa
- [ ] **(consigna 3.5)** Consola de las dos placas: rampa generada, valor recibido y SourceTimestamp (60 s de cada una)
      → [PARTE-3.md §3](PARTE-3.md) · 📁 `evidencia/consola/consola_rpi1.txt`, `consola_rpi2.txt`
- [ ] **(consigna 3.4)** Captura de **60 s en Modo A** (Read cada 100 ms)
      → [PARTE-3.md §4.2](PARTE-3.md) · 📁 `captura_modo_A.pcapng`
- [ ] **(consigna 3.4)** Captura de **60 s en Modo B** (suscripción de 100 ms)
      → 📁 `captura_modo_B.pcapng`
- [ ] **(consigna 3.4)** SamplingInterval, PublishingInterval y QueueSize **revisados**, leídos de la trama
      → [PARTE-3.md §4.4](PARTE-3.md) · 📁 captura de pantalla de CreateMonitoredItemsResponse
- [ ] **(consigna 3.4)** Comparación de **cantidad de tramas y de bytes** en los dos modos; contraste con la predicción (99 % / 11 %)
      → [PARTE-3.md §4.3](PARTE-3.md) · [herramientas/estadisticas_captura.md](herramientas/estadisticas_captura.md) · 📁 tabla completa
- [ ] **(consigna 3.4)** Mecanismo **Publish/KeepAlive**: repetir las capturas con el pulsador en reposo y la **rampa detenida** (botones *S3 · Detener rampa* y *C5 · Detener rampa*); período medido entre KeepAlive (~1 s)
      → [PARTE-3.md §4.4](PARTE-3.md) · [docs/protocolo-opcua.md §7.2](docs/protocolo-opcua.md) · 📁 `captura_modo_A_quieto.pcapng`, `captura_modo_B_quieto.pcapng`
- [ ] **(consigna 3.4)** **Latencia** pulsador → LED en los dos sentidos y los dos modos (20 pulsaciones cada caso); `medir_latencia.py`; desvío de chrony anotado
      → [PARTE-3.md §4.5](PARTE-3.md) · 📁 `lat_rpi1.log`, `lat_rpi2.log`, tabla completa
- [ ] *(recomendado)* Validar la latencia con un video en cámara lenta (240 fps)
- [ ] **(consigna 3.6)** Comprobación previa: con el cable desconectado, `ip route get 192.168.10.1` sigue por `eth0` (si no, aplicar la ruta *prohibit* y registrarlo en INCONVENIENTES)
      → [PARTE-3.md §6.1](PARTE-3.md)
- [ ] **(consigna 3.6)** Desconexión: LED PWM **congelado** en las dos placas mientras el generador local sigue
      → [PARTE-3.md §6.2](PARTE-3.md) · 📁 video
- [ ] **(consigna 3.6)** **StatusCode** informado por el cliente y comportamiento de la sesión; cortes de ~5 s, ~20 s y ~45 s
      → 📁 `evidencia/consola/desconexion_*.txt`, tabla completa
- [ ] **(consigna 3.6)** Recuperación al reconectar: secuencia de eventos y tiempo hasta los datos nuevos
- [ ] *(consigna 3.7, opcional)* Corrección **gamma** 2,2: activar `usarGamma`, comparar la percepción y justificar por qué una rampa lineal en PWM no se ve lineal
      → [PARTE-3.md §7](PARTE-3.md)
- [ ] **(consigna 1.4, pendiente de la Parte 1)** Demostración `eth0` frente a `wlan0` → ver §2

## 5. Parte 4 — Análisis de tramas y seguridad

- [ ] **(consigna 4.1)** Captura en la RPi 2 (`tcpdump -i eth0`) de una **sesión completa en modo None**, desde antes de conectar hasta la desconexión; tabla ARP vaciada antes, para que aparezca el ARP
      → [PARTE-4.md §1](PARTE-4.md) · 📁 `captura_none.pcapng`
- [ ] **(consigna 4.2)** **Diagrama de secuencia** con cada mensaje y su origen: ARP y TCP; HEL/ACK y OPN; GetEndpoints, CreateSession y ActivateSession; CreateSubscription, CreateMonitoredItems, Publish y Write; CloseSession y CLO. Ajustado a la captura real
      → [diagramas/secuencia_sesion.md](diagramas/secuencia_sesion.md) · [PARTE-4.md §2](PARTE-4.md) · 📁 tabla de números de trama
- [ ] **(consigna 4.3)** Función de cada etapa; diferencia entre **conexión TCP, canal seguro y sesión**
      → [docs/protocolo-opcua.md §4](docs/protocolo-opcua.md)
- [ ] **(consigna 4.4)** **Encapsulamiento** de un PublishResponse con `Servidor.Rampa`: Ethernet II (MAC, EtherType), IPv4, TCP (puertos, números de secuencia) y OPC UA
      → [PARTE-4.md §4](PARTE-4.md) · `opcua_tramas.py --ethernet --markdown` · 📁 `evidencia/tramas/publish_encapsulamiento.md`
- [ ] **(consigna 4.5)** **Byte a byte:** WriteRequest/WriteResponse de `Cliente.Rampa` **y** de `Cliente.EstadoPulsador` (cabecera, SecureChannelId, TokenId, SequenceNumber, RequestId, NodeId del servicio, RequestHeader, NodeId de la variable, AttributeId, DataValue y su máscara, Variant; UInt16 en little-endian y Boolean)
      → [PARTE-4.md §5](PARTE-4.md) · [docs/protocolo-opcua.md §6](docs/protocolo-opcua.md) · 📁 cuatro tablas en `evidencia/tramas/`
- [ ] **(consigna 4.6)** **Eficiencia** para una word (Ethernet, IP, TCP, OPC UA) con el tamaño **medido**; comparación con la trama MODBus RTU de la Tarea 1 y discusión
      → `eficiencia_trama.py --ua-bytes <medido>` · [docs/protocolo-opcua.md §9](docs/protocolo-opcua.md)
- [ ] **(consigna 4.7)** Servidor con **tres endpoints**: None, Sign/Basic256Sha256 y SignAndEncrypt/Basic256Sha256; conexión del cliente repetida con cada uno
      → [PARTE-4.md §7.1](PARTE-4.md)
- [ ] **(consigna 4.8)** **Certificados X.509 y trust list:** rechazo inicial, comparación de huellas por SSH, paso de `rejected/` a `trusted/`; StatusCode del rechazo anotado
      → [PARTE-4.md §7.2](PARTE-4.md) · [docs/seguridad.md §3](docs/seguridad.md) · 📁 `pki_rejected.png`, `pki_huellas.png`
- [ ] **(consigna 4.8)** **Legibilidad en Wireshark** en cada modo (qué campos quedan legibles y cuáles cifrados)
      → [PARTE-4.md §7.3](PARTE-4.md) · 📁 `wireshark_write_none.png`, `_sign.png`, `_signandencrypt.png`
- [ ] **(consigna 4.8)** **Latencia** del intercambio en cada modo (`latencia_captura.py`) y tiempo de establecimiento
      → [PARTE-4.md §7.4](PARTE-4.md) · 📁 tabla completa
- [ ] **(consigna 4.9)** **Usuario y contraseña** además del anónimo; en qué mensaje viaja el token (ActivateSession) y cómo se protege (RSA-OAEP + ServerNonce)
      → [PARTE-4.md §8](PARTE-4.md) · [docs/seguridad.md §5](docs/seguridad.md) · 📁 `wireshark_activatesession_token.png`
- [ ] *(recomendado)* Pruebas de rechazo: clave incorrecta; anónimo sin permiso de escritura (`soloAutenticadosEscriben`) → `BadUserAccessDenied`
      → [PARTE-4.md §8.3](PARTE-4.md)
- [ ] Volver `config.js` al modo que se va a mostrar en la defensa

## 6. Requerimientos adicionales del trabajo

- [ ] **(req. 1)** Diagrama de red: enlace, interfaces, IP y conexionado de los periféricos de cada placa
      → [diagramas/red.md](diagramas/red.md) (ajustar si el conexionado real difiere)
- [ ] **(req. 2)** Diagrama de flujo del **servidor**: inicialización, espacio de direcciones, rampa, pulsador, escrituras, LED
      → [diagramas/flujo_servidor.md](diagramas/flujo_servidor.md)
- [ ] **(req. 2)** Diagrama de flujo del **cliente**: conexión, suscripción, notificaciones, escrituras, reconexión
      → [diagramas/flujo_cliente.md](diagramas/flujo_cliente.md)
- [ ] **(req. 3)** **Trazabilidad:** cada fragmento de código del informe referencia su bloque (S1…S7, C0…C7)
      → tablas de trazabilidad de cada diagrama · `prueba_flujos.js` en verde
- [ ] **(req. 4)** Todos los `.png` usados en el informe guardados junto a él
      → 📁 `evidencia/capturas/`
- [ ] Problemas del banco registrados (I-08 en adelante), con la hipótesis descartada
      → [evidencia/INCONVENIENTES.md](evidencia/INCONVENIENTES.md)

## 7. Informe técnico

Contenido que evalúa la cátedra:

- [ ] **Arquitectura de red y capa física:** enlace punto a punto, direccionamiento, verificación por capas, conexionado de cada placa
- [ ] **Modelo de información:** tabla del espacio de direcciones con NodeIds, tipos, niveles de acceso y servicios usados
- [ ] **Análisis de tramas:** diagrama de secuencia, encapsulamiento, byte a byte, comparación de modos de seguridad
- [ ] **Diseño lógico y diagramas de flujo** del servidor y del cliente
- [ ] Respuestas a las preguntas de análisis **1.5** y **2.6**
- [ ] **Bibliotecas:** parámetros de configuración, funciones usadas con sus parámetros **y tipos**, y qué devuelven (node-opcua, pigpio/pi-gpiod, Node-RED) *(Aclaraciones de la consigna)*
- [ ] **Conexionado de cada bloque** del circuito *(Aclaraciones)*
- [ ] Justificación teórica **con bibliografía** (las referencias de `docs/`)
- [ ] Declaración del uso de IA, si la cátedra la pide

Formato *(sección "Entrega")*:

- [ ] **PDF**, nombre `Bevilacqua_Peralta_PdCI_T2_26.pdf`
- [ ] Texto **justificado**; márgenes **3 cm** laterales y **2,5 cm** superior e inferior
- [ ] **Arial 11**; interlineado **1,5**; espaciado **posterior 6**, anterior 0
- [ ] Citas y referencias en **APA 7.ª edición**
- [ ] Junto al informe: **código, diagramas y capturas** usados (carpeta `tarea-2/`)
- [ ] Revisado que **no** contenga contraseñas, hashes ni claves privadas

## 8. Defensa (12 minutos estrictos + preguntas)

- [ ] Guion ensayado con tiempo: apertura (2 min), desarrollo (8 min), cierre (2 min); **ambos** integrantes hablan
      → [defensa/guion.md](defensa/guion.md)
- [ ] Diapositivas de apoyo (esquemas, no lectura de código)
- [ ] Demostración en vivo: formas de onda cruzadas, pulsador → LED remoto, UaExpert, **desconexión y recuperación**
- [ ] Plan B: video de la demostración grabado en el banco y una captura de Wireshark ya filtrada
- [ ] Banco de preguntas repasado por los dos integrantes
      → [defensa/guion.md §2](defensa/guion.md)
- [ ] Acceso al informe entregado (papel o digital) el día de la defensa

## 9. Al cerrar cada sesión de laboratorio

- [ ] Evidencia copiada a la PC: capturas `.pcapng`, registros, `~/evidencia`, fotos
- [ ] Evidencia copiada al repositorio (`tarea-2/evidencia/`) y commit con Conventional Commits
- [ ] Placas apagadas con `sudo poweroff`
- [ ] **microSD del laboratorio restauradas** desde su `.img` y verificadas; cada una en **su** placa
      → [node-red/README.md §18](node-red/README.md)
- [ ] *(opcional)* Imagen de **nuestra** tarjeta configurada guardada, para no repetir la puesta a punto
