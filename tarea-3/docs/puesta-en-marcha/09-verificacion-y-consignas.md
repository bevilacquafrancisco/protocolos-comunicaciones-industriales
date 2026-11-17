# 09 · Verificación integral, evidencia y ensayo de la defensa

**Objetivo:** recorrer **cada consigna** del TP con el banco completo y guardar su evidencia en
`docs/capturas/banco/`, con los mismos procedimientos que ya se validaron en el banco virtual (F7).
Así, los números del banco se comparan uno a uno con los de la PC.

**Requisitos:** los criterios de salida de 01 a 08. **Tiempo:** 2-3 h.

**Antes de empezar:**

- Terminal 1: Edge Node (07 §2).
- Terminal 2: observador archivando en `docs/capturas/banco/sparkplug-banco.jsonl` (07 §3.1).
- Túnel SSH al Dashboard (05 §7).
- La web abierta en la notebook (08).
- Wireshark instalado.

Cada resultado se anota en [resultados-pruebas.md](../resultados-pruebas.md) con fecha, commit
(05 §2), resultado y archivo de evidencia. **Las pruebas que fallan también se anotan**, con su causa
y su corrección.

Referencias: [plan-de-pruebas.md](../plan-de-pruebas.md) · [matriz-trazabilidad.md](../matriz-trazabilidad.md) ·
[capturas/README.md](../capturas/README.md) (los pies de figura de las capturas de la PC sirven de
modelo para las del banco).

---

## 1. Convención de la evidencia

| Prefijo del archivo | Contenido |
|---|---|
| `banco-web-*.png` | Capturas de la web (Win+Shift+S) |
| `banco-dashboard-*.png` | Capturas del Dashboard de Node-RED |
| `banco-mqttexplorer-*.png` | Capturas de MQTT Explorer |
| `banco-opcua-*.pcapng` | Capturas de Wireshark en el adaptador Ethernet de la notebook |
| `banco-*.jsonl`, `banco-*.txt`, `banco-*.md` | Registros y reportes generados por las herramientas |

**[SEC]** Antes de subir la evidencia a git, buscar las claves en ella (10 §2).

## 2. Consigna 1: MODBus RTU

| ID | Prueba | Cómo | Criterio | Evidencia |
|---|---|---|---|---|
| 1.a | CRC propio en el maestro y en el esclavo | Dashboard *Tramas* + *Probar conexión*; consola de Thonny (sin `umodbus` en la placa) | CRC válido y calculado por `lib/modbus.js` y `crc16.py` | `banco-dashboard-tramas.png` |
| 1.a | Trama en el bus físico | **Con un segundo adaptador** en la notebook, en paralelo a A/B: `.venv\Scripts\pip install pyserial==3.5` y `.venv\Scripts\python ..\..\tarea-1\herramientas\sniffer_rs485.py COMx --baudrate 9600 --guardar ..\docs\capturas\banco\banco-sniffer-rs485.txt` | Petición y respuesta con CRC válido y silencio ≥ t3,5 entre tramas (B-5) | `banco-sniffer-rs485.txt` + una trama decodificada con `tarea-1/herramientas/modbus_tramas.py` |
| 1.c | Contadores visibles en todas las capas | Dashboard, UaExpert (§3) y web | Los mismos OK, CRC_ERROR, TIMEOUT y EXCEPTION en las tres | `banco-web-contadores.png` |
| B-3 | 750 ciclos sin error | Dejar el sistema 4 minutos y leer el Δ de los contadores | 0 % de error: Δ CRC_ERROR = Δ TIMEOUT = 0 | Anotación en resultados |
| B-4 | Latencia del conversor | 06 §2 (`latency_timer`) | Valor anotado, y `LatenciaMs` antes y después si se ajusta | Anotación |
| 1.d / F-10 | Esclavo desconocido | §5, F-10 | Comunica en **< 3 min** sin recompilar | Cronómetro + `banco-dashboard-descubrimiento.png` |

Sin el segundo adaptador, la captura del bus físico queda pendiente. La trama exacta igual está
documentada desde el transporte de desarrollo (`capturas/f7/modbus-tramas-decodificadas.md`). Se
aclara en el informe.

## 3. Consigna 2: OPC UA

**3.1 Espacio de direcciones con UaExpert (manual).**

1. Agregar un servidor: `opc.tcp://192.168.10.1:4840`.
2. Endpoint `Basic256Sha256 - SignAndEncrypt`, usuario `operador`.
3. UaExpert presenta su certificado: el servidor lo rechaza la primera vez. Confiarlo en el panel del
   Dashboard comparando la huella (07 §2.2).
4. Recorrer `Objects → Dispositivo1 → Inputs / Outputs / Status`.
5. Escribir `Inputs/Pulsador`: tiene que devolver **BadNotWritable**.
6. Capturar pantalla: `banco-uaexpert-*.png`.

**3.2 Reporte reproducible por nodo.** Desde `tarea-3`, la clave se lee del `.env`, sin escribirla en el
comando:

```powershell
PS> $env:PDCI_T3_OPCUA_CLAVE = ((Get-Content .env | Select-String '^OPCUA_CLIENTE_CLAVE=').Line -split '=',2)[1]
PS> node tools\verificar_opcua.js --url opc.tcp://192.168.10.1:4840 --usuario operador --informe docs\capturas\banco\banco-opcua-espacio-direcciones.md
PS> Remove-Item Env:PDCI_T3_OPCUA_CLAVE
```

Es el equivalente en el banco de `docs/opcua-espacio-direcciones.md`, que se generó en la PC.

**3.3 Captura de Wireshark en los tres modos (consigna 2.b).**

1. En Wireshark, el adaptador **Ethernet** de la notebook, con filtro de captura `tcp port 4840`.
2. Iniciar la captura y ejecutar **una sesión** de `tools/verificar_opcua.js` con `--modo None`.
3. Detener la captura y guardar como `banco-opcua-None.pcapng`.
4. Repetir con `--modo Sign` y `--modo SignAndEncrypt`.

En los modos seguros, la primera vez hay que **confiar en el certificado de este verificador** en el
panel. Es otro cliente (`PdCI-T3-verificador`) y se confía igual que en 07 §2.2.

| ✓ | Criterio (comparar con [seguridad-opcua.md §6](../seguridad-opcua.md)) |
|---|---|
| ☐ | Las tres capturas tienen HEL, OPN, MSG y CLO |
| ☐ | En None se leen los NodeIds; en SignAndEncrypt, no |
| ☐ | **En ninguna aparece la contraseña.** Buscarla con *Edit → Find Packet → String*, y cerrar Wireshark sin guardar esa búsqueda |
| ☐ | El tráfico va entre 192.168.10.2 y 192.168.10.1, es decir, por el cable |

## 4. Consigna 3: MQTT y Sparkplug B

| ID | Prueba | Cómo | Evidencia |
|---|---|---|---|
| 3.1 | Broker en internet (I-03) | El host del `.env` es el de EMQX Cloud; `tracert <url-del-broker>` sale de la red local | `banco-tracert-broker.txt` |
| 3.10 / N2.4 | Los **siete tipos**: NBIRTH, DBIRTH, NDATA, DDATA, DCMD, DDEATH, NDEATH | MQTT Explorer con `observador` (07 §3.2) mientras se ejecutan F-01 (DDEATH), F-05 (NDEATH) y un comando desde la web (DCMD) | `banco-mqttexplorer-<tipo>.png` + `sparkplug-banco.jsonl` |
| 3.9 | Payload Protobuf | Un DDATA de `sparkplug-banco.jsonl`: `.venv\Scripts\python tools\volcado_sparkplug.py --jsonl ..\docs\capturas\banco\sparkplug-banco.jsonl --tipo DDATA --markdown` | `banco-volcado-ddata.md` |
| 3.12 | STATE retenido de la Host Application | MQTT Explorer: `spBv1.0/STATE/HA01_WebDashboard`, con la marca de *retained*, `{"online": true, ...}` | `banco-mqttexplorer-state.png` |
| 3.3-3.6 | La web muestra E/S, comandos y los estados MODBus y OPC UA | 08 §3 y §4 | `banco-web-*.png` |

Al terminar la sesión, el observador imprime `violaciones: ...` (Ctrl+C). Tiene que decir **ninguna**.

## 5. Consigna 4: fallas F-01 a F-10

Con el menú en **modo banco**, desde Git Bash en `tarea-3`. Para F-06 hace falta Git Bash **como
administrador**: el script baja la interfaz con `Disable-NetAdapter`.

```bash
GB$ export MODO=banco RPI_SSH=pdci@rpi-pdci-t3.local IFACE="Wi-Fi" T3_ENV="$PWD/.env"
GB$ scripts/inyectar-fallas.sh
```

Cada opción **inyecta** la falla e imprime qué hay que observar. Las físicas, como desenchufar o cerrar
la pestaña, las pide como acción manual. Con **Enter** la **restaura**.

Para cada falla:

1. Cronometrar la detección y la recuperación.
2. Capturar la web en el estado de falla.
3. Anotar el resultado en la tabla de abajo.

Los tiempos esperados son los medidos en la PC ([mediciones.md](../mediciones.md) §4).

| ID | En el banco se provoca con | Esperado (detección / recuperación en la PC) | Evidencia | Detección | Recuperación |
|---|---|---|---|---|---|
| F-01 | Desenchufar el ESP32 | DEVICE NOT REACHED + DDEATH (2,2 s / 0,5 s) | `banco-web-f01.png` | | |
| F-02 | Ruido en A/B (puede dar TIMEOUT en vez de CRC) | CRC ERROR (2,5 s / 0,5 s). La reproducción exacta es la de la PC | `banco-web-f02.png` | | |
| F-03 | Unit ID 7 en el Dashboard | DDEATH (1,6 s / 1,4 s) | `banco-web-f03.png` | | |
| F-04 | `systemctl stop pdci-t3-nodered` (por SSH) | OPC UA ERROR, MODBUS SIN DATOS (0,3 s / 3,8 s) | `banco-web-f04.png` | | |
| F-05 | `kill -9` del Edge Node | NDEATH del broker (0,2 s / 0,8 s) | `banco-web-f05.png` | | |
| F-06 | Bajar la Wi-Fi de la notebook | NDEATH por keepalive (~15-18 s / 3,1 s) | `banco-web-f06-corte.png`, `banco-web-f06-recuperado.png` | | |
| F-07 | Edge de prueba que salta un `seq` | Aviso + NCMD Rebirth (0,2 s / ms) | `banco-web-f07.png` | | |
| F-08 | Cerrar la pestaña | STATE offline **retenido** en MQTT Explorer | `banco-mqttexplorer-state-offline.png` | | |
| F-09 | Clave equivocada en `config.js` | CREDENCIALES RECHAZADAS | `banco-web-f09.png` | | |
| F-10 | ESP32 #2 (perfil DESCONOCIDO) en lugar del #1 | Descubrimiento + Aplicar (< 3 min) | `banco-dashboard-descubrimiento.png` | | |

En F-06, la notebook pierde internet **y** la sesión SSH, si va por la misma Wi-Fi. El enlace OPC UA
sigue, porque va por el cable. Hay que tenerlo en cuenta si se está mirando el Dashboard.

## 6. Mediciones en el banco

| Medición | Cómo | Comparar con |
|---|---|---|
| **Latencia de comando** (clic → CONFIRMADO, con la nube) | 20 clics en el conmutador. El registro de la web dice `CONFIRMADO (NNN ms)` en cada uno. Calcular mín, mediana, p95 y máx | `mediciones.md` §1.2 (PC: mediana 192 ms) |
| **Latencia de lectura** (lectura MODBus → observador) | `timestamp` de la métrica en el DDATA (reloj de la Raspberry) contra la llegada al observador (reloj de la notebook). Antes, verificar el desvío: `timedatectl timesync-status` en la Raspberry y `w32tm /stripchart /computer:pool.ntp.org /samples:3` en la notebook. Ese desvío es la cota de error | `mediciones.md` §1.1 |
| **Tráfico OPC UA** en régimen y reposo | Wireshark 60 s en el Ethernet de la notebook, *Statistics → Conversations* | `mediciones.md` §2 |
| **Ocupación del bus RS-485** | Con el sniffer (§2) o calculada de la tasa de transacciones | `mediciones.md` §2 (34 %) |
| **Resistencia, 30 min** (E2E-05) | Todo corriendo. En la Raspberry, el lazo de abajo. Al final: Δ de los contadores de error, `violaciones` del observador, Rebirths | `mediciones.md` §5 |

Lazo de memoria de la Raspberry (RSS y PSS reales, que en la PC quedó pendiente):

```bash
$ PID=$(systemctl show -p MainPID --value pdci-t3-nodered)
$ timeout 1800 bash -c "while true; do echo \$(date +%T) \$(grep -E '^(Rss|Pss):' /proc/$PID/smaps_rollup | tr -s ' ' | tr '\n' ' '); sleep 30; done" > ~/banco-memoria-nodered.txt
```

Criterio: sin crecimiento sostenido de `Pss` en 30 minutos.

## 7. Ensayo de la defensa

Del plan de pruebas, N5:

| ✓ | Punto |
|---|---|
| ☐ | Guion cronometrado: apertura 2 min, cuerpo 8 min, cierre 2 min. **Tres ensayos completos** |
| ☐ | Reparto por capa: cada integrante domina un tramo de la cadena y sus preguntas del banco (N5) |
| ☐ | **Video de respaldo** de la secuencia completa, grabado en el banco (Win+Alt+R o OBS): comando, pulsador, F-05 y su recuperación, F-07 |
| ☐ | **Plan B de conectividad** probado en el aula: 02 §5.4 con el punto de acceso del celular |
| ☐ | Cronometrar F-10 con el ESP32 #2 preparado por la otra persona, a ciegas |

**Secuencia sugerida para la demo:**

1. Semáforo en verde.
2. Pulsador y potenciómetro en vivo.
3. Comando del LED (ENVIADO → CONFIRMADO).
4. F-05: matar el Edge Node, NDEATH, todo OBSOLETO; reiniciarlo y ver la recuperación sola.
5. F-07: salto de `seq` y Rebirth.
6. Mostrar `bdSeq` y `seq` en MQTT Explorer.

---

## Criterio de salida

- [ ] Cada fila de §2 a §5 con su evidencia en `docs/capturas/banco/` y su anotación en
      `resultados-pruebas.md`.
- [ ] Observador: `violaciones: ninguna` en la sesión del banco.
- [ ] Mediciones del §6 anotadas y comparadas con las de la PC en `mediciones.md`, en una sección
      "Banco".
- [ ] Ensayo del §7 hecho al menos una vez completo con el banco.
