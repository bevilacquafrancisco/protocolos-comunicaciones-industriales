# Matriz de trazabilidad — consigna → artefacto → evidencia → informe

> Se completa a medida que avanzan las fases. **Ningún requisito queda en "parcial" en la entrega.**
> Antes de entregar, Claude Code debe releer el PDF de la consigna y verificar esta tabla línea por
> línea. Es el control de calidad final del trabajo.

Estados: ⬜ pendiente · 🟨 en curso · ✅ cumplido y con evidencia

> **Nota F1 (2026-11-09).** ADR-010 decidido: el esclavo es MicroPython (fila 1.a, `crc16.py`). El servidor OPC UA de la fila 2.0 ya no es un nodo de la paleta sino `node-opcua` desde
> function nodes (ADR-011). El cliente de la fila 2.2 es la v2 de la T2 (ADR-013).

---

## Consigna 1 — Comunicación Modbus entre dispositivo 1 y dispositivo 2

| # | Requisito literal | Artefacto que lo cumple | Evidencia | Sección del informe | Estado |
|---|---|---|---|---|---|
| 1.0 | Dispositivo 1 = el esclavo de la Tarea Nº1 | `firmware/esclavo-modbus/` (HAL y mapa de la T1, protocolo propio) | Código + foto del montaje | 4.1 Dispositivo de campo | 🟨 código y pruebas en PC; falta banco |
| 1.1 | Dispositivo 2 intercambia datos con las E/S del dispositivo 1 | Flow `modbus-master` + `lib/maestro.js` | Captura del Dashboard con valores vivos | 4.2 Maestro de borde | 🟨 PC ✅ (simulador con el stack del firmware) · banco ⬜ |
| 1.2 | Usar el esquema de la trama Modbus para ubicar los datos | `docs/diccionario-de-datos.md` §1 | Tabla de direcciones | 5.1 Mapa de registros | ⬜ |
| 1.3 | Definir nombre, tipo y dirección Modbus de cada E/S, reutilizables como métricas Sparkplug | `docs/diccionario-de-datos.md` | Tabla única de las tres capas | 5.1 | ⬜ |
| 1.a | Conexión física RS-485 **con CRC generado y verificado en maestro y esclavo** | `firmware/esclavo-modbus/lib/modbus_slave/crc16.py` + `edge-nodered/lib/modbus.js` | Tests *golden* en CPython y JS; captura del sniffer | 6.1 CRC-16 y su implementación | 🟨 los mismos 23 vectores pasan en el esclavo y en el maestro; falta el sniffer en banco |
| 1.b | Explicar intercambio de mensajes, rutinas comentadas y **todos** los campos de la trama | `docs/diagramas/secuencia-modbus.mmd` + informe | Decodificación byte a byte de una trama real | 6.2 Análisis de trama Modbus | ⬜ |
| 1.c | Contador de peticiones aceptadas y con error en el maestro, **visible en todas las capas** | Contadores de `lib/maestro.js`, persistidos; panel de las cuatro capas | Captura de la web con los cuatro contadores | 7.3 Observabilidad | 🟨 MODBus y Dashboard ✅ · OPC UA/MQTT/Sparkplug ⬜ |
| 1.d | Maestro configurable en vivo para un esclavo que trae la cátedra | Dashboard de configuración + asistente de descubrimiento | Video o captura del ensayo contra el ESP32 #2 | 4.2.3 Configuración en runtime | 🟨 PC ✅ (descubrimiento y Aplicar desde el panel) · banco ⬜ |

## Consigna 2 — OPC UA entre dispositivo 2 y dispositivo 3

| # | Requisito | Artefacto | Evidencia | Informe | Estado |
|---|---|---|---|---|---|
| 2.0 | Dispositivo 2 = servidor; dispositivo 3 = cliente OPC UA | Flow `opcua-server` + `gateway-sparkplug/src/opcua_client.py` | Captura de UaExpert navegando el espacio de direcciones | 4.3 Capa OPC UA | ⬜ |
| 2.1 | Transmitir **el mismo paquete de datos** que en Modbus, incluido el estado de la comunicación Modbus | Nodos `Status.MODBUS.*` en el espacio de direcciones | Tabla de NodeIds | 5.2 Modelo de información | ⬜ |
| 2.2 | Reutilizar el cliente OPC UA de la Tarea Nº2 | `gateway-sparkplug/src/opcua_client.py` | Diff respecto del original con las modificaciones justificadas | 4.3.2 Reutilización | ⬜ |
| 2.3 | Mantener nombre y tipo de cada dato | Diccionario de datos | Tabla de las tres capas | 5.1 | ⬜ |
| 2.a | Desarrollar la conexión física y programar los dispositivos | Diagrama de red + configuración IP | `ip addr`, `ping`, `ethtool` | 3.2 Capa física Ethernet | ⬜ |
| 2.b | Explicar intercambio de mensajes y trama empleada | Diagrama de secuencia OPC UA | Captura de Wireshark con filtro `opcua` | 6.3 Análisis de trama OPC UA | ⬜ |

## Consigna 3 — MQTT con Sparkplug B

| # | Requisito | Artefacto | Evidencia | Informe | Estado |
|---|---|---|---|---|---|
| 3.0 | El cliente OPC UA actúa como Edge Node publicador | `src/sparkplug_edge_node.py` | Captura de MQTT Explorer | 4.4 Edge Node | ⬜ |
| 3.1 | Broker **no local**, el paquete va por internet | Broker en la nube | Captura del panel del broker + `traceroute` | 3.3 Infraestructura MQTT | ⬜ |
| 3.2 | Página web como Host Application suscriptora | `hmi-web/` | Captura de la interfaz | 4.5 Host Application | ⬜ |
| 3.3 | La web muestra el estado de entradas y salidas del dispositivo 1 | `hmi-web/app.js` | Captura con valores vivos | 4.5 | ⬜ |
| 3.4 | La web acciona la salida digital y varía la analógica mediante `DCMD` | Flujo DCMD → OPC UA Write → Modbus FC 05/06 | Video del comando extremo a extremo | 7.2 Camino de comando | ⬜ |
| 3.5 | La web muestra `DEVICE NOT REACHED`, `CRC ERROR`, `DONE` | Métrica `Status/MODBUS/Estado` | Captura de los tres estados provocados | 7.3 | ⬜ |
| 3.6 | La web muestra el estado OPC UA: `ERROR` o `DONE` | Métrica `Status/OPCUA/Estado` | Captura de ambos estados | 7.3 | ⬜ |
| 3.7 | Roles: dispositivo 3 = Edge Node, dispositivo 1 = Device, web = Host Application | Diagrama de roles Sparkplug | Diagrama | 4.4.1 | ⬜ |
| 3.8 | Estructura de tópicos `spBv1.0/{group}/{type}/{node}[/{device}]`, **con identificadores justificados** | Diccionario §4 | Árbol de tópicos en MQTT Explorer | 5.3 Espacio de nombres | ⬜ |
| 3.9 | Payload **Protobuf** según `sparkplug_b.proto`, nunca JSON propio | `proto/sparkplug_b.proto` | Volcado hexadecimal del payload + su decodificación | 6.4 Análisis de payload Sparkplug | ⬜ |
| 3.10 | Ciclo de vida: `NBIRTH` con `seq=0`, `bdSeq`, `Node Control/Rebirth`; `DBIRTH`; `NDEATH` como Will; `NDATA`/`DDATA` ante cambio con `seq` 0–255; `DDEATH` y nuevo `DBIRTH` | `src/sparkplug_edge_node.py` | Capturas de los cinco tipos de mensaje | 7.1 Ciclo de vida | ⬜ |
| 3.11 | Estados de comunicación como métricas del Edge Node | ADR-006 | Captura de `NDATA` con las métricas de estado | 5.3 | ⬜ |
| 3.12 | La web publica `spBv1.0/STATE/{host_id}` retenido, JSON con `online` y `timestamp`, con `offline` como Will | `hmi-web/sparkplug.js` | Captura del mensaje retenido | 7.1.2 | ⬜ |
| 3.13 | Ante salto de `seq` o datos sin BIRTH, la web pide Rebirth con `NCMD` | `hmi-web/sparkplug.js` | Captura del `NCMD` y del `NBIRTH` resultante | 7.1.3 | ⬜ |
| 3.14 | Broker con MQTT 3.1.1/5.0, Last Will, retenidos y WSS; **documentar el nivel de seguridad** | ADR-005 | Tabla de usuarios y permisos por tópico | 8. Seguridad | ⬜ |
| 3.b | Explicar, por cada tipo de mensaje, el tópico y los campos del payload (`timestamp`, `seq`, métricas con `name`, `datatype`, `value`) | Informe §6.4 | Tabla por tipo de mensaje | 6.4 | ⬜ |

## Consigna 4 — Verificación del estado funcional y recuperación

| # | Requisito | Artefacto | Evidencia | Informe | Estado |
|---|---|---|---|---|---|
| 4.1 | Informar la falla **y en qué parte se generó**, en tiempo real | Semáforo por capa en la web | Capturas de cada falla inyectada | 7.3 | ⬜ |
| 4.2 | Aprovechar `NDEATH`/Last Will, `DDEATH` y los saltos de `seq` | `src/sparkplug_edge_node.py` + `hmi-web/` | Capturas de los tres mecanismos | 7.1 | ⬜ |
| 4.3 | Reconexión automática: nueva sesión MQTT con `bdSeq` incrementado, `NBIRTH` con `seq=0`, `DBIRTH`, y la web se actualiza sola | Lógica de reconexión | Video de la secuencia completa | 7.4 Recuperación | ⬜ |
| 4.4 | Verificar el tráfico con una herramienta externa que decodifique Sparkplug B e incluir capturas de BIRTH, DATA, CMD y DEATH | MQTT Explorer | Cuatro capturas en `docs/capturas/` | Anexo B | ⬜ |

## Requisitos transversales

| # | Requisito | Dónde | Estado |
|---|---|---|---|
| T.1 | Diagramas de flujo del maestro y de los esclavos | `docs/diagramas/flujo-*.mmd` + `.png` (F1) | 🟨 |
| T.2 | Trazabilidad de código: cada fragmento referenciado a un bloque del diagrama | Etiquetas `[DF-1.x]` esclavo, `[DF-2.x]` maestro, `[DF-3.x]` Edge Node, `[DF-4.x]` Host App, definidas en F1 | 🟨 |
| T.3 | Código comentado para que otro programador lo entienda | Todo el código | ⬜ |
| T.4 | Librerías usadas: parámetros de configuración, funciones, tipos de argumentos y valores de retorno | Informe, anexo de librerías | ⬜ |
| T.5 | Conexionado de **cada** bloque del circuito | Esquemáticos + fotos | ⬜ |
| T.6 | Formato: PDF, Arial 11, interlineado 1,5, márgenes 3/2,5, justificado, APA 7 | `informe/` | ⬜ |
| T.7 | Nombre `Apellido1_Apellido2_Apellido3_PdCI_T3_26.pdf` | Entrega | ⬜ |
| T.8 | Se adjuntan códigos, simulaciones y diagramas | Paquete de entrega | ⬜ |
| T.9 | Informe preliminar: explicación de la solución + diagrama de flujo + tipo de comunicación y orden de los datos en las tramas | `informe/Bevilacqua_Peralta_PdCI_T3_26_preliminar.pdf` (fuentes en el commit 658fa3a) | 🟨 generado, falta subirlo |
| T.10 | Defensa de 12 minutos con los tres integrantes hablando | `defensa/guion-12min.md` | ⬜ |

---

## Verificación final (ejecutar antes de entregar)

1. Releer el PDF de la consigna completo y marcar cada línea de esta matriz.
2. Abrir el PDF generado y comprobar tipografía, márgenes, interlineado y justificado reales.
3. Comprobar que cada captura del informe existe en `docs/capturas/` y está referenciada.
4. Comprobar que cada referencia bibliográfica citada aparece en la lista y viceversa.
5. Correr la suite de pruebas completa y pegar la salida en el anexo.
6. Ensayar la demo de principio a fin, incluido el ensayo del esclavo desconocido (ADR-007).
