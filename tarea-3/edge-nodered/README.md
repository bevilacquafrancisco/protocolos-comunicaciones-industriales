# Dispositivo 2 — maestro MODBus RTU en Node-RED

Tarea Nº3 · Fase F3 · Raspberry Pi (en desarrollo, la notebook) + conversor USB-RS485

Maestro MODBus RTU con **stack y CRC propios** (I-01) y Dashboard de **configuración en vivo**
(I-04) y **estadística de las cuatro capas** (I-05). En F4 se le agrega el servidor OPC UA.

**Estado:** probado en la PC contra el simulador, que ejecuta el stack real del firmware
(135 pruebas Jest, Node-RED 4.1.16 corriendo y el Dashboard operado con clics). **Falta el banco**
con el conversor USB-RS485 y el ESP32 (§7).

---

## 1. Qué hay y dónde

| Ruta | Contenido |
|---|---|
| `lib/modbus.js` | Protocolo: `crc16`, `buildRequest`, `parseResponse` (`NONE`/`CRC_ERROR`/`TIMEOUT`/`EXCEPTION`/`MALFORMED`/`WRONG_SLAVE`), `t35ms`, longitudes esperadas |
| `lib/maestro.js` | Máquina de estados del maestro ([DF-2.x]): sondeo, escrituras, reintentos, contadores, estado, mutex del bus, reconfiguración, prueba, trama manual, descubrimiento, exploración |
| `lib/configuracion.js` | Validación (todo lo que llega del Dashboard es no confiable), carga y guardado atómico |
| `lib/tipos.js` | bool, uint16, int16, uint32, int32, float32 y orden de palabras ABCD/CDAB |
| `lib/transportes.js` | Puerto serie de Node-RED o TCP de desarrollo, conmutables en vivo |
| `lib/estadisticas.js` | Registro de las cuatro capas e historial de eventos |
| `config/config.default.json` | Configuración de fábrica (dispositivo 1: 9600 8N1, Unit ID 1, mapa de la T1) |
| `funciones/<flow>/*.js` | Código de cada function node (M1-M4, D1-D2, E1-E2) |
| `plantillas/*.vue`, `estilo.css` | Paneles del Dashboard 2.0 |
| `generar_flujos.js` | Genera `flows/*.json` (uno por flow) y el `flows.json` que carga Node-RED |
| `flows/` | `modbus-master.json`, `dashboard-config.json`, `estadisticas.json`, `dashboard-base.json` |
| `settings.js` | Configuración de Node-RED (módulos propios, contexto en archivo, seguridad) |
| `test/` | Jest: protocolo, maestro, configuración, flows e integración con el simulador |

**Los `flows/*.json` no se editan en el editor de Node-RED**: se cambia el `.js` o el `.vue`
y se regenera (`npm run flows`). `test/flujos.test.js` falla si un flow no coincide con su
generador. Es el mismo criterio de la Tarea 2 (ADR-03): el código del maestro se revisa en un
diff, no dentro de una cadena JSON.

## 2. Versiones

| Paquete | Versión | Por qué |
|---|---|---|
| Node-RED | 4.1.16 | Rama 4.1 mantenida; Node-RED 5 exige Node.js ≥ 22,9 y la imagen de la T2 trae menos |
| Node.js | ≥ 18,5 | Requisito de Node-RED 4.1 |
| `@flowfuse/node-red-dashboard` | 1.33.0 | Dashboard 2.0. `node-red-dashboard` (v1) está marcado **sin mantenimiento** en npm |
| `node-red-node-serialport` | 2.0.3 | Bytes crudos (`bin`) y `serial control` para reconfigurar el puerto en vivo |
| Jest | 30.5.0 | Pruebas (solo desarrollo) |

## 3. Desarrollo sin hardware (Windows o Linux)

```bash
cd tarea-3/edge-nodered
npm install
npm run flows                                   # genera los flows
python ../simuladores/esclavo_modbus_sim.py --tcp 127.0.0.1:5020      # en otra terminal
npm start                                       # Node-RED en http://127.0.0.1:1880
```

Abrir `http://127.0.0.1:1880/dashboard`. En **Configuración MODBus** elegir Medio = *TCP
(simulador)*, `127.0.0.1:5020`, y **Aplicar sin reiniciar**.

**Por qué TCP y no solo pty.** En Windows no hay `socat`, y en Linux un par de pty **ignora
el baud rate y la paridad**: con pty el asistente de descubrimiento "encontraría" al esclavo en
cualquier combinación. Por TCP el maestro anuncia su línea (`PDCI-LINEA 19200 even 8 1`) y el
simulador, si no coincide, se comporta como un UART desajustado: recibe basura y no responde.
Para probar el camino serie real en Linux: `../scripts/dev-serial.sh` y Medio = *Puerto serie*,
`/tmp/pdci-maestro`.

**Simuladores.** Ejecutan el stack REAL del firmware (`firmware/esclavo-modbus/lib`). Fallas
inyectables al arrancar (`--falla crc --prob 0.3`) o en vivo, escribiendo en su consola:
`falla silencio` · `falla crc 0.5` · `falla truncada` · `falla excepcion` · `falla retardo 1 400` ·
`falla ninguna` · `pulsador 1` · `pote 2047` · `auto on` · `estado`.

## 4. Instalación en la Raspberry Pi

1. Node-RED con el script oficial de la Raspberry Pi (instala Node.js LTS y el servicio).
2. En la carpeta de datos de Node-RED (`~/.node-red`):
   `npm install @flowfuse/node-red-dashboard@1.33.0 node-red-node-serialport@2.0.3`
3. Copiar `tarea-3/edge-nodered/` a la placa y generar los flows **en la placa**, apuntando a la
   carpeta de datos: `PDCI_T3_USERDIR=$HOME/.node-red node generar_flujos.js`.
4. Arrancar con este `settings.js`:
   `node-red --settings ~/pdci-t3/edge-nodered/settings.js --userDir ~/.node-red`
   (o editar el servicio). Usuario en el grupo `dialout` para abrir `/dev/ttyUSB0`.
5. Acceso: por defecto Node-RED escucha **solo en 127.0.0.1**. Desde la notebook, por túnel SSH
   (como en la T2): `ssh -L 1880:127.0.0.1:1880 usuario@rpi`. Para exponerlo en la LAN,
   `PDCI_T3_UI_HOST=0.0.0.0` **y** usuarios con hash bcrypt (`npx node-red admin hash-pw`) en
   `PDCI_T3_ADMIN_USUARIO/HASH` y `PDCI_T3_UI_USUARIO/HASH`: sin ellos `settings.js` se niega a
   arrancar. Un maestro MODBus abierto en la red dejaría escribir salidas de campo a cualquiera.

La configuración aplicada desde el Dashboard se guarda en `~/.node-red/pdci-t3-config.json`
(escritura atómica) y los contadores, en el contexto `archivo`: ambos sobreviven a un reinicio.

## 5. Operación (Dashboard)

| Página · panel | Qué hace |
|---|---|
| Estadísticas · Estado de las cuatro capas | MODBus (OK, CRC_ERROR, TIMEOUT, EXCEPTION y estado DONE / CRC ERROR / DEVICE NOT REACHED); OPC UA, MQTT y Sparkplug B se completan en F4-F5. Un dato con más de 10 s se marca |
| Estadísticas · Variables | Valor y calidad de cada variable; ON/OFF y escritura numérica de las salidas. Muestra lo **confirmado** por la lectura posterior, no lo pedido (ADR-015) |
| Estadísticas · Tramas | Última trama TX y RX en hexadecimal, latencia, ciclos y detalle de errores |
| Estadísticas · Historial | Transiciones de estado, reconfiguraciones y descubrimientos |
| Configuración · Enlace | Medio, puerto, baud, bits, paridad, parada, Unit ID, timeout, período, reintentos, ausencia; **Aplicar sin reiniciar**; restaurar de fábrica |
| Configuración · Mapa | Tabla editable: nombre, función, dirección (decimal o `0x…`), tipo, orden, escritura, mín, máx; muestra la notación Modicon |
| Configuración · Probar conexión | Una petición con la trama cruda de ida y vuelta y la validación del CRC; **trama manual** en hexadecimal (el maestro agrega el CRC) |
| Configuración · Descubrimiento | Barrido Unit ID × baud × paridad (FC 03, dirección 0); **Aplicar** el hallazgo; **explorar direcciones** y agregarlas al mapa |

**Procedimiento frente al esclavo de la cátedra** (ensayado contra el simulador, objetivo
< 3 min): 1) *Descubrir esclavo* → 2) *Aplicar* → 3) si la cátedra da el mapa, cargarlo en la
tabla; si no, *Explorar* con FC 03/04/01/02 y *agregar al mapa* → 4) *Aplicar mapa* →
5) verificar en Estadísticas. Si algo no encaja (otra función, otro formato), *trama manual*.

## 6. Pruebas

```bash
npm test               # 135 pruebas, ~15 s; la integración necesita Python 3 en el PATH
```

| Archivo | Qué prueba |
|---|---|
| `modbus.test.js` | CRC contra los **mismos 23 vectores golden que el firmware**; armado, validación, tiempos |
| `maestro.test.js` | Validación de configuración (entradas maliciosas), persistencia atómica, **mutex del bus** (dos operaciones exclusivas nunca superponen tramas), una escritura pendiente por variable, tipos |
| `integracion_simulador.test.js` | Maestro real contra el simulador (stack del firmware): lee las 4 variables, escribe coil y holding, **cada falla inyectada mueve su contador**, descubrimiento del desconocido en **0,8 s** (ID 17, 19200 8E1) y **8,6 s** (ID 5, 38400 8O1), reconfiguración en vivo al mapa del desconocido |
| `flujos.test.js` | Flows al día, cables y links válidos, código compilable, **sin nodos MODBus de la paleta**, y las tres trampas de Dashboard 2.0 como regresión |

Las pruebas del mutex se validaron con mutación: sin el mutex, la prueba falla.

## 7. Verificación en banco (pendiente)

| # | Prueba | Criterio |
|---|---|---|
| B-1 | Maestro con el conversor USB-RS485 contra el ESP32 (perfil DISPOSITIVO_1) | 750 ciclos, 0,0 % de error |
| B-2 | `serial control`: cambiar baud y paridad desde el Dashboard varias veces seguidas | La lectura se restablece en < 1 s; `serial in` sigue recibiendo después de cada reapertura (R-16) |
| B-3 | Descubrimiento contra el ESP32 #2 (perfil DESCONOCIDO) | Encuentra ID, baud y paridad sin tocar código; tiempo < 60 s |
| B-4 | Latencia del conversor: `cat /sys/bus/usb-serial/devices/ttyUSB0/latency_timer` | Si es 16 ms, bajarlo a 1 ms y medir de nuevo `LatenciaMs` |
| B-5 | Sniffer de la T1 en el bus durante B-1 | Silencio entre tramas ≥ t3,5 (4,01 ms a 9600 bps) |

## 8. Decisiones y limitaciones

| Tema | Decisión | Motivo |
|---|---|---|
| Delimitación de respuestas | Por **longitud esperada**, no por silencio (ADR-012) | Node-RED no mide t3,5 con precisión; el maestro sabe qué preguntó |
| t3,5 al transmitir | Cota inferior: `setTimeout(t3,5 + 1 ms)` | Un temporizador solo puede atrasarse, nunca adelantarse |
| `DEVICE NOT REACHED` | Por **ausencia sostenida** (2000 ms), no por un fallo (ADR-014) | En la T1, contar fallos sueltos hacía parpadear los indicadores |
| CRC_ERROR | Incluye las tramas no recomponibles (MALFORMED, WRONG_SLAVE) | Consigna 1.c; el detalle se ve en el panel de tramas |
| Escritura | Una pendiente por variable; se responde con el eco (ADR-015) | Una orden vieja no tiene sentido; el StatusCode debe reflejar el actuador |
| Descubrimiento | Dos fases: IDs habituales en todas las combinaciones (≈ 8,6 s), luego el resto (peor caso 178 s) | El barrido completo no entra en la defensa; la mayoría de los equipos sale de fábrica con ID 1-10 |
| Tablas del Dashboard | `<table>` nativo, sin etiquetas autocerradas ni atributos camelCase | Dashboard 2.0 parsea la plantilla con el HTML del navegador (regresión en `flujos.test.js`) |
| `serial control` | Espera de asentamiento configurable (`esperaReconfiguracionMs`, 300 ms) | Responde antes de terminar de reabrir el puerto |
