# Registro de resultados de pruebas

Regla del plan de pruebas: cada ejecución se anota con fecha, commit, resultado y evidencia, y **las
que fallan no se borran**. Se documentan con su causa y su corrección.

Se distinguen dos clases de falla:

- **Defecto del sistema**: el producto no cumplía. Se corrige el producto.
- **Defecto de la prueba**: el procedimiento medía mal. Se corrige la prueba y se vuelve a ejecutar.
  Que el resultado sea "pasa" no autoriza a ocultar que antes no pasaba.

---

## F7 · 2026-11-12/14 · Revisión de la cadena contra N4 y campaña de fallas (banco virtual)

### Revisión de la cadena (punto 1 de la consigna F7)

Se recorrió cada falla F-01 a F-10 contra el código, antes de ejecutar nada.

| # | Hallazgo | Clase | Corrección | Verificación |
|---|---|---|---|---|
| R-1 | **F-04**: con OPC UA caído, la web seguía mostrando el último `Status/MODBUS/Estado = DONE` en verde. Ese dato ya nadie lo verificaba: la falla no se informaba "en la capa correcta" | Defecto del sistema | `hmi-web/app.js`: con OPC UA en ERROR, la tarjeta MODBUS pasa a OBSOLETO con el texto "SIN DATOS (OPC UA en ERROR)" | Paso 5b de `hmi-web/test/ui.test.js`; Figura 4 (`capturas/f7/web-opcua-error.png`) |
| R-2 | **F-09**: el rechazo de credenciales solo quedaba en el registro, y el semáforo decía DESCONECTADO, igual que un corte de red | Defecto del sistema (informe insuficiente) | Banner persistente y semáforo **CREDENCIALES RECHAZADAS** ante un CONNACK 4 o 5 | Campaña F-09; Figura 9 |
| R-3 | La web dibujaba en un ciclo fijo de 250 ms: sumaba 0 a 250 ms a la latencia de lectura | Defecto del sistema (rendimiento) | Dibujo en el cuadro siguiente al mensaje (`requestAnimationFrame`) | Tramo broker → pantalla: mediana 6 ms (`mediciones.md` §1) |

### Campaña de fallas: tres corridas

| Corrida | Commit | Resultado | Causa de las fallas | Corrección |
|---|---|---|---|---|
| 1 | `8ada48c` + cambios de F7 | Latencias, tráfico y eficiencia: **OK**. Fallas: F-02 y F-07 OK; F-01 y F-03 a F-06 **FALLAN** | **Defecto de la prueba.** (a) En F-01 se esperaba la web con un cierre JavaScript, y puppeteer lo serializa al navegador **sin sus variables**, así que la condición no se cumplía nunca. (b) Al fallar la detección no se restauraba la falla: el simulador quedó en silencio y arrastró a F-03 a F-06 | Valor esperado como argumento explícito. Toda falla se restaura aunque su prueba falle |
| 2 | ídem | F-01, F-02 y F-07 OK; F-03 a F-06 **FALLAN** | **Defecto de la prueba.** (a) F-03 escribía el Unit ID **agregando** dígitos (1 → 17 → 171): el triple clic no selecciona en un `input` numérico, y el maestro quedó en ID 171. (b) `matar()` devuelve el código de salida del proceso y se tomó como instante de inyección (detecciones de 1,79·10¹² ms). (c) El lector del JSONL parseaba una línea **a medio escribir**: F-07 "no veía" un NBIRTH que había llegado 2 ms después del NCMD | Selección con Ctrl+A y verificación del valor escrito. Marca de tiempo explícita `{t}`. Solo se leen líneas completas |
| 3 | ídem | **10/10 OK**, 0 violaciones de `seq`/`bdSeq` | — | — |

Ninguna de las fallas de las corridas 1 y 2 fue del sistema. Las capturas de pantalla de la corrida 1
(`error-F-0X.png`, en el scratchpad) muestran la web con el estado correcto en el momento en que la
prueba declaraba la falla.

**Resultado de la corrida 3**: detalle en `mediciones.md` §4 y datos crudos en
`capturas/f7/fallas-resultados.json`.

| ID | Detección | Recuperación | Resultado |
|---|---|---|---|
| F-01 | 2,22 s | 0,5 s | OK |
| F-02 | 2,52 s | 0,5 s | OK |
| F-03 | 1,56 s | 1,4 s | OK |
| F-04 | 0,26 s | 3,8 s | OK |
| F-05 | 0,24 s | 0,8 s | OK |
| F-06 | 17,86 s | 3,1 s | OK |
| F-07 | 0,18 s | 3 ms | OK |
| F-08 | 0,03 s | 0,7 s | OK |
| F-09 | 0,54 s | — (hay que corregir la clave) | OK |
| F-10 | 2,86 s | 4,1 s | OK |

### Menú `scripts/inyectar-fallas.sh` (MODO=pc): 2026-11-14

`levantar`, después cada falla con `F-0X` y `F-0X restaurar` en modo no interactivo, y al final `bajar`.
El efecto se verificó en el observador, no en lo que imprime el menú.

| Falla | Inyección | Restauración |
|---|---|---|
| F-01 | DDEATH | DBIRTH |
| F-05 | NDEATH a 1,0 s | DBIRTH |
| F-06 | NDEATH a 19,9 s | DBIRTH; último `bdSeq` = 3 |
| F-07 | NCMD a 9,2 s (incluye los 8 s de arranque del Edge de prueba) | DBIRTH |

- `bajar` no dejó procesos huérfanos ni puertos tomados.
- **Defecto encontrado y corregido**: el proceso en segundo plano heredaba la salida del script, y
  `inyectar-fallas.sh levantar | tail` no terminaba nunca. Ahora se desacopla con `< /dev/null > /dev/null`.
- F-03, F-08, F-09 y F-10 son **manuales por diseño** (Dashboard, cerrar la pestaña, clave, asistente de
  descubrimiento), porque en la demo los hace el operador. En el banco virtual quedaron cubiertos por la
  campaña automática.

### Suites automáticas al cierre de F7

| Suite | Resultado |
|---|---|
| `edge-nodered`: `npx jest` | 179/179 |
| `gateway-sparkplug`: `pytest` | 58/58 |
| `hmi-web`: `npm test` (incluye la página en Chrome) | 16/16 |

### Resistencia (E2E-05): 2026-11-14, 30 minutos, **OK**

| Criterio de E2E-05 | Resultado |
|---|---|
| Sin fugas de memoria | Ningún proceso crece de forma sostenida. El heap JS de la página varía +0,7 MiB en 30 min. Medido con el working set de Windows: la confirmación con RSS/PSS en la Raspberry Pi queda **pendiente** |
| Sin crecimiento del contador de errores | CRC_ERROR +0, TIMEOUT +0 y EXCEPTION +0, sobre 28 001 transacciones correctas |
| `seq` envolviendo correctamente | 34 vueltas de 255 a 0, 0 violaciones, sin NDEATH ni DDEATH, 1 solo Rebirth (el de la conexión inicial) |

Detalle en `mediciones.md` §5. Evidencia en `capturas/f7/resistencia-resultados.json` (las 59 muestras) y
en la Figura 10.

---

## Puesta en marcha · 2026-11-14 · Revisión del despliegue antes del banco

Al escribir el procedimiento de puesta en marcha (`docs/puesta-en-marcha/`), se recorrió cada paso
contra el código y contra la documentación oficial del broker. Aparecieron cuatro defectos que **no**
se habían visto en la PC, porque solo se manifiestan en el despliegue real:

| # | Hallazgo | Clase | Corrección | Verificación |
|---|---|---|---|---|
| D-1 | **El broker gratuito no admite permisos por tópico.** HiveMQ Cloud Serverless da un permiso por credencial y no tiene roles (documentación oficial). El Edge Node abortaba ante **cualquier** SUBACK rechazado, y con el permiso limitado al grupo, el rechazo de `STATE` impedía que arrancara en el banco | Defecto del sistema (latente) | STATE pasa a ser opcional, salvo con `--esperar-host`; ADR-026 | `test_permisos_broker.py` con el perfil `serverless` del broker de desarrollo: **falla sin la corrección y pasa con ella** (verificado con `git stash`) |
| D-2 | `edge-nodered/README.md` §4 proponía Node-RED global con los módulos en `~/.node-red`. **No arrancaba**: `settings.js` resuelve `node-opcua` desde su carpeta | Defecto de documentación | `node-red` pasa a `dependencies`; Node-RED se ejecuta desde `edge-nodered/node_modules` (el camino del banco virtual); unidad systemd versionada | Lockfile: solo cambian las marcas `dev` (sin versiones distintas). 179/179 en Jest |
| D-3 | `inyectar-fallas.sh` en `MODO=banco` detenía un servicio `nodered` (el de la T3 es `pdci-t3-nodered`), ejecutaba `sudo` por SSH sin terminal, y usaba `pkill` e `ip link`, que no existen en Git Bash de Windows | Defecto de la herramienta | Nombre del servicio, `ssh -t`, `matar_proc` e `interfaz` según el sistema operativo | `matar_proc` probado en Windows: termina solo el proceso señuelo |
| D-4 | Las unidades systemd y las plantillas de entorno podían llegar a la placa con CRLF: un `\r` final en `EnvironmentFile` cambia el hash OPC UA | Riesgo de despliegue | `.gitattributes`: `*.service` y `*.ejemplo` con LF | `git check-attr eol`: `lf` |

Suites al cierre: firmware TODO OK · `edge-nodered` 179/179 · `gateway-sparkplug` **61/61** (+3 de
permisos) · `hmi-web` 16/16.

---

## Puesta en marcha · 2026-11-16 · Alta del broker

| # | Hallazgo | Clase | Corrección | Verificación |
|---|---|---|---|---|
| D-5 | **No se podía crear el broker del ADR-005.** La consola de HiveMQ solo ofrecía brokers *self-managed*: HiveMQ Cloud Serverless dejó de venderse el 2026-09-30 y se apaga el 2026-12-31 (docs.hivemq.com, "Serverless End of Life"). El ADR-005 y el ADR-026 se habían verificado contra páginas del plan que no mencionaban el retiro | Defecto de documentación (fuente no revisada: se verificaron las características del servicio, pero no su ciclo de vida) | ADR-027: EMQX Cloud Serverless con *Spend Limit* en USD 0 y la tabla de permisos del ADR-005 completa. WSS pasa de 8884 a 8084. El perfil `serverless` del broker de desarrollo se renombra `un_filtro`, y `minimo` pasa a ser el del banco | El código no tenía nada atado al proveedor: solo cambian la configuración, los comentarios y la documentación. `gateway-sparkplug` 61/61 y `hmi-web` 16/16 después del cambio. Las pruebas de mínimo privilegio contra la nube son las de 02 §5.3, **pendientes** del alta |

---

## Host Application v2 · 2026-11-16 · ADR-028

| Suite | Resultado |
|---|---|
| `gateway-sparkplug` (pytest) | **62/62** (+1: tramas de diagnóstico agrupadas en el NDATA) |
| `hmi-web` (`node:test`) | **24/24**: núcleo 12, decodificación y modelo 9, entrega 2, página en Chrome 1 |

- **CRC-16 de `tramas.js`** contra cuatro tramas reales del sistema: `84 0A` y `B8 44` (banco,
  2026-11-16), `31 CA` (diccionario) y `B9 E4` (verificación OPC UA). Las cuatro coinciden byte a byte.
- **`modelo.js` contra la fuente de verdad**: la primera corrida falló porque el lector de la prueba
  partía `\|` dentro de una celda del diccionario. Fue un **defecto de la prueba**, y se corrigió.
- **Página en Chrome**: la primera corrida falló en la vista de celular (conmutador de 0 px). Al
  pasar a modo celular, Puppeteer recarga la página y la clave, que solo vive en memoria, se pierde.
  Es el **comportamiento buscado** (ADR-028). La prueba ahora vuelve a ingresar, y además verifica
  que ninguna de las cinco pestañas desborde en 390 px.
- **Revisión visual** de las capturas de cada pestaña: se corrigieron una columna FC que partía el
  número, palabras cortadas en tablas angostas, la abreviatura del broker y los Float con 14 decimales.

---

## Preparación para la defensa · 2026-11-16 · ADR-029

| Suite | Resultado |
|---|---|
| Firmware (CPython) | `TODO OK`: `prueba_config.py` 38 verificaciones (+9: registro de perfil, eco antes del cambio, excepción 03) |
| `edge-nodered` (Jest) | 179/179, con los flujos regenerados |
| `gateway-sparkplug` (pytest) | 62/62 (retroceso OPC UA 1, 2, 4, 5, 5…) |
| `hmi-web` (`node:test`) | **25/25**: + sitio de GitHub Pages sin claves; la página en Chrome ahora verifica la alarma del bus, la del cable (sin acusar al bus) y las dos recuperaciones |

- **Defecto de la prueba:** el chequeo "sin claves" del sitio fallaba con el comentario del propio
  `config.js` ("SIN claves"). Ahora busca un **campo** de clave, no la palabra.
- **Defecto del script:** `banco.ps1 verificar` no detectaba la falla de SSH, porque PowerShell no
  convierte el código de salida de un programa externo en excepción, y calculaba un desfase de
  −1,79·10¹² ms. Ahora revisa `$LASTEXITCODE`.
- **Hallazgo de la prueba en seco, con el banco desconectado:** `ping 192.168.10.1` respondía. La
  placa Ethernet de la notebook había perdido la IP fija (10 §4 de la versión anterior la borraba),
  así que el paquete salía por la Wi-Fi de casa y contestaba otro equipo con esa dirección. Por eso
  `verificar` comprueba primero que la ruta a la Raspberry salga **por Ethernet**, y la IP fija pasa
  a ser permanente (ADR-029).

**Pendiente con hardware:** desenchufar y volver a enchufar el cable Ethernet y el bus RS-485,
cronometrando la alarma y la recuperación (11 §5); el cambio de perfil del ESP32 desde el Dashboard
seguido del descubrimiento; el sitio publicado en GitHub Pages, abierto desde un celular en otra red.

---

## Pendiente con hardware

El banco real (ESP32, RS-485, Raspberry Pi, broker en la nube) repite **las mismas** pruebas con
`scripts/inyectar-fallas.sh` en `MODO=banco`. Los resultados se anotan acá con el mismo formato.
