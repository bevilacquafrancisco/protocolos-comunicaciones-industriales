# Plan de verificación y validación

> Principio rector: **ningún requisito se da por cumplido sin una prueba reproducible o una
> evidencia capturada.** La defensa oral es, en el fondo, una ejecución en vivo de este plan.

Niveles: unitario (sin hardware) → integración por enlace → extremo a extremo → inyección de
fallas → ensayo de defensa.

---

## N1 · Pruebas unitarias (sin hardware, automatizables)

### N1.1 CRC-16 Modbus — el test más importante del trabajo

El mismo conjunto de vectores debe pasar en **las dos implementaciones** (MicroPython del ESP32, ejecutado con CPython en la PC, y
JavaScript de Node-RED). Si divergen, la comunicación falla de un modo difícil de diagnosticar.

**Generación de los vectores:** con una implementación independiente y reconocida
(`pymodbus` o una tabla de referencia publicada), producir un archivo
`tests/fixtures/crc_vectors.json` con al menos:

- Las cuatro peticiones del mapa de registros (FC 01, 02, 03, 04) y sus respuestas típicas.
- Las dos escrituras (FC 05 y FC 06) con sus ecos.
- Las cuatro respuestas de excepción (códigos 01 a 04).
- Casos borde: trama de longitud mínima (4 bytes), trama de longitud máxima (256 bytes),
  trama con todos los bytes en `0x00` y con todos en `0xFF`.

**Criterio de aceptación.** 100 % de coincidencia entre MicroPython/CPython, JavaScript y el oráculo.
Además, una propiedad: para toda trama válida, `crc(trama || crc(trama)) == 0`.

```bash
python firmware/esclavo-modbus/test/prueba_crc.py      # CPython, exit 1 si falla (ADR-010: MicroPython)
python firmware/esclavo-modbus/test/prueba_parser.py   # ídem
cd edge-nodered && npm test                        # JS
```

Oráculos (ADR-002): `tarea-1/herramientas/modbus_tramas.py` (ya verificado contra `123456789` →
`0x4B37`) y `pymodbus`. Los vectores se fijan en un JSON común a las dos implementaciones.

**Agregado en F0 — N1.5 Delimitación en el maestro (ADR-012).** Respuestas partidas en bloques
arbitrarios (1 byte, 3 bytes, trama entera, dos tramas pegadas), bytes de más, Unit ID o FC
distinto del pedido, excepción de 5 bytes y longitud incompleta al vencer el timeout. Criterio:
cada caso clasificado como `OK`, `CRC_ERROR` (incluye no recomponible), `EXCEPTION` o `TIMEOUT`.

### N1.2 Parser de tramas del esclavo

Casos: trama correcta · CRC corrupto en un bit · ID de esclavo ajeno (debe ignorarse en silencio,
sin responder) · FC no soportado (excepción 01) · dirección fuera de rango (excepción 02) ·
cantidad fuera de rango (excepción 03) · trama truncada · dos tramas pegadas sin silencio `t3.5`.

### N1.3 Codificación Sparkplug B

Codificar un payload, decodificarlo y comparar campo por campo. Verificar en particular:
`timestamp` en milisegundos desde época Unix, `seq` que envuelve correctamente de 255 a 0,
`datatype` correcto por métrica, y que `bdSeq` del `NDEATH` coincide con el del `NBIRTH`.

### N1.4 Escalado y endianness

ADC 0–4095 → porcentaje y → PWM 0–255, con los extremos y el punto medio.
Intercambio de bytes MSB/LSB en ambos sentidos.

---

## N2 · Pruebas de integración por enlace

### N2.1 Enlace Modbus sin hardware

**Implementado en F3:** `edge-nodered/test/integracion_simulador.test.js` corre el maestro real contra `simuladores/esclavo_modbus_sim.py` (stack del firmware) por TCP, con emulación del desajuste de línea (ADR-017): lee, escribe, inyecta cada falla y descubre al esclavo desconocido. El camino serie real se prueba en Linux con `scripts/dev-serial.sh` (los pty ignoran baud y paridad).

#### Con puertos serie virtuales (Linux)

```bash
socat -d -d pty,raw,echo=0 pty,raw,echo=0     # devuelve /dev/pts/N y /dev/pts/M
python3 simuladores/esclavo_modbus_sim.py --port /dev/pts/N --id 1 --baud 19200 --parity E
# Node-RED apunta su nodo serie a /dev/pts/M
```

Verificar: lectura de las cuatro variables, escritura de coil y de holding register, incremento
correcto de los contadores, y comportamiento ante un esclavo que no responde.

### N2.2 Enlace Modbus real sobre RS-485

Con las dos placas en el bus, terminación y polarización colocadas:
medir con osciloscopio o analizador lógico la señal diferencial A–B, verificar los tiempos de
conmutación de `DE`/`RE` y comprobar que el silencio entre tramas supera `t3.5`.
Capturar una trama completa y decodificarla byte a byte para el informe.

### N2.3 Enlace OPC UA

Cliente y servidor en loopback primero, luego sobre la red real.
Navegar el espacio de direcciones con UaExpert y verificar, por cada nodo:
`NodeId`, `BrowseName`, `DataType`, `AccessLevel`, `Value`, `StatusCode`, `SourceTimestamp` y
`ServerTimestamp`. Intentar escribir un nodo de sólo lectura y registrar el `StatusCode` devuelto
(`BadNotWritable`). Capturar con Wireshark una sesión completa, de `HEL` a `CLO`.

### N2.4 Enlace MQTT y Sparkplug B

Contra el broker en la nube, con MQTT Explorer suscripto a `spBv1.0/#`:
capturar y archivar `NBIRTH`, `DBIRTH`, `NDATA`, `DDATA`, `DCMD`, `DDEATH` y `NDEATH`.
Verificar que `NDEATH` llega **sin** que el Edge Node lo publique (lo emite el broker como Will).

---

## N3 · Pruebas extremo a extremo

| ID | Escenario | Criterio de aceptación |
|---|---|---|
| E2E-01 | Pulsar el botón del dispositivo 1 | El indicador cambia en la web; latencia total medida y registrada |
| E2E-02 | Girar el potenciómetro | El valor varía en la web de forma continua, sin saltos ni valores imposibles |
| E2E-03 | Accionar la salida digital desde la web | El LED del dispositivo 1 enciende; `DCMD` → `Write` OPC UA → FC 05 verificado en el sniffer |
| E2E-04 | Variar la salida analógica desde la web | El brillo del LED PWM cambia de forma monótona en todo el recorrido |
| E2E-05 | Operación sostenida 30 minutos | Sin fugas de memoria, sin crecimiento del contador de errores, `seq` envolviendo correctamente |
| E2E-06 | Dos pestañas del navegador abiertas | Ambas muestran el mismo estado; los comandos de una se reflejan en la otra |

**Medición de latencia.** Instrumentar con marcas de tiempo en los cuatro puntos de la cadena
(campo, borde, gateway, navegador) y reportar la distribución, no sólo el promedio: en sistemas
industriales lo que importa es el peor caso. Distinguir la latencia de la rama de lectura de la de
la rama de comando, que recorre la cadena en sentido inverso.

---

## N4 · Inyección de fallas — consigna 4

Cada fila es una prueba que debe ejecutarse, capturarse y, en la defensa, poder reproducirse en vivo.

| ID | Falla inyectada | Cómo se provoca | Detección esperada | Recuperación esperada |
|---|---|---|---|---|
| F-01 | El esclavo Modbus no responde | Desconectar su alimentación | `Status/MODBUS/Estado = DEVICE NOT REACHED`, contador `TIMEOUT` sube, `DDEATH` publicado | Al reconectar: `DBIRTH` nuevo y la web se repuebla sola |
| F-02 | Error de CRC | Inyectar ruido en el par A/B, o un modo de prueba del simulador que corrompa un bit | `Status/MODBUS/Estado = CRC ERROR`, contador `CRC_ERROR` sube | El sondeo continúa; el contador queda como registro histórico |
| F-03 | Esclavo con ID equivocado | Cambiar el ID en el Dashboard a uno inexistente | `DEVICE NOT REACHED` | Corregir el ID en el Dashboard restablece la comunicación sin reiniciar nada |
| F-04 | Se cae el servidor OPC UA | Detener el flow o desenchufar la Ethernet | `Status/OPCUA/Estado = ERROR`; el `StatusCode` del cliente lo refleja | Reconexión automática del cliente, estado vuelve a `DONE` |
| F-05 | Se cae el Edge Node | Matar el proceso del dispositivo 3 | El broker publica el `NDEATH` (Will); la web marca el nodo fuera de línea y todas sus métricas como obsoletas | Al reiniciar: `bdSeq` incrementado, `NBIRTH` con `seq = 0`, `DBIRTH`, web actualizada sin intervención |
| F-06 | Se corta internet en el dispositivo 3 | Desactivar su interfaz de red | Igual que F-05, por tiempo de espera de MQTT (`keepalive`) | Reconexión automática con nueva sesión |
| F-07 | Mensajes perdidos | Forzar un salto de `seq` desde un cliente de prueba | La web detecta el salto | La web publica `NCMD` con `Node Control/Rebirth = true` y el nodo republica sus BIRTH |
| F-08 | Se cae la Host Application | Cerrar la pestaña del navegador | El broker publica `STATE` con `offline` (Will) retenido | Al reabrir, `STATE` pasa a `online` y la web reconstruye su estado desde los BIRTH retenidos o pidiendo Rebirth |
| F-09 | Credenciales MQTT inválidas | Alterar la contraseña | Error de conexión informado al usuario, no un fallo silencioso | — |
| F-10 | Esclavo desconocido de la cátedra | ESP32 #2 con ID, baud, paridad y mapa distintos (ADR-007) | El maestro no comunica inicialmente | Descubrimiento y configuración desde el Dashboard en **menos de 3 minutos**, sin recompilar |

**Nota sobre F-07.** Es la prueba que más luce en la defensa y la que mejor explica por qué
Sparkplug B existe. Vale la pena dedicarle treinta segundos del guion.

---

## N5 · Ensayo de la defensa

- **Cronometrar** las tres secciones: apertura 2 min, cuerpo técnico 8 min, cierre 2 min.
  Ensayar al menos tres veces completas. La consigna dice "duración estricta".
- Los tres integrantes hablan. Repartir por capa, no por sección, para que cada uno domine un
  tramo completo de la cadena y pueda responder preguntas sobre él.
- **Demo con red de seguridad:** tener grabado un video de la secuencia completa por si falla el
  hardware o la conectividad del aula. Mostrar en vivo y usar el video sólo como respaldo.
- **Plan B de conectividad:** si el aula no tiene internet, usar la conexión compartida de un
  celular. Probarlo antes, no el mismo día.
- **Banco de preguntas probables** (preparar respuesta de 30 segundos para cada una):
  1. ¿Cuántos registros se pueden leer en un solo mensaje Modbus RTU y por qué?
     (Límite de 256 bytes de ADU → 253 de PDU; 125 registros de 16 bits en FC 03/04,
     2000 bits en FC 01/02. Hay que poder derivarlo, no recitarlo.)
  2. ¿El CRC es por hardware o por software? ¿Qué detecta y qué no detecta?
  3. ¿Por qué `bdSeq` y no simplemente `seq`?
  4. ¿Qué pasa si el broker se reinicia y pierde los mensajes retenidos?
  5. ¿Por qué Sparkplug B y no MQTT con JSON? ¿Qué se pierde y qué se gana?
  6. ¿Qué diferencia conceptual hay entre cliente-servidor de OPC UA y maestro-esclavo de Modbus?
  7. ¿Cuánto tarda un comando desde el clic hasta el LED, y dónde está el cuello de botella?
  8. ¿Cómo asegurarían esto en una planta real? ¿Qué falta para IEC 62443?
  9. ¿Por qué las métricas de estado son del nodo y no del dispositivo?
  10. ¿Qué pasa si dos Host Applications se conectan a la vez?

---

## Registro de resultados

Cada ejecución se anota en `docs/resultados-pruebas.md` con fecha, versión del commit, resultado y
enlace a la evidencia. Las pruebas que fallan **no se borran**: se documentan con su causa y su
corrección. Un informe que muestra un error encontrado y resuelto es más creíble que uno donde
todo salió bien a la primera, y el tribunal lo sabe.
