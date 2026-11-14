# Dispositivo 3: cliente OPC UA y Edge Node Sparkplug B

Tarea Nº3 · Fase F5 · PC o VM (Python 3.11+)

El dispositivo tiene dos piezas:

- Un **cliente OPC UA**. Es el de la T2, adaptado (ADR-013). Se suscribe a los nodos del
  dispositivo 2 que lista el diccionario de datos.
- Un **Edge Node Sparkplug B 3.0**. Publica esos nodos en un broker MQTT en la nube (I-03) y lleva
  los comandos de la Host Application hasta el LED del ESP32.

**Estado.** Todo lo que sigue se probó en la PC: pasan las 61 pruebas, más una sesión real de punta
a punta contra Node-RED, el servidor OPC UA en SignAndEncrypt y el simulador del esclavo. Quedan
dos cosas pendientes, y son manuales (§8):

- la corrida contra el **broker en la nube** (necesita la cuenta y los usuarios del ADR-005);
- la verificación con **MQTT Explorer**.

---

## 1. Qué hay y dónde

| Ruta | Contenido |
|---|---|
| `src/opcua_client.py` | Cliente de la T2. El encabezado lista qué se reutilizó, qué se adaptó y qué se descartó, con el motivo. Suscripción 100/100/1, reconexión con retroceso 1-30 s y escrituras |
| `src/metrics.py` | Las métricas se **leen** de `docs/diccionario-de-datos.md`: nombre, tipo, alias, origen, NodeId y si es escribible. Ninguna métrica está escrita en el código (I-06) |
| `src/sparkplug.py` | Tópicos, `seq` y codificación Protobuf por tipo (especificación §6.4.16). Sin estado y sin red |
| `src/ciclo_vida.py` | **Máquina de estados del ciclo de vida** (ADR-020): NBIRTH, DBIRTH, NDATA, DDATA, DDEATH, Rebirth y DCMD. Cada regla cita su `tck-id` |
| `src/sparkplug_edge_node.py` | E/S: paho MQTT (TLS, Will), el puente con asyncio, el registro JSONL y el programa |
| `src/sparkplug_b_pb2.py` | **Generado** desde `proto/` (§3). No se edita |
| `proto/sparkplug_b.proto` | Archivo oficial de Eclipse Tahu, **sin modificar**. Su SHA-256 está fijado en una prueba |
| `tools/traer_certificado_servidor.py` | Trae el certificado del servidor OPC UA. Lo guarda solo si la huella coincide con la del panel |
| `tools/observador_sparkplug.py` | Suscriptor de solo lectura. Decodifica, **verifica `seq` y `bdSeq`** y archiva en JSONL |
| `tools/host_comandos.py` | NCMD Rebirth y DCMD, como los envía la web |
| `tools/broker_dev.py` | Broker de **desarrollo** (amqtt) con TLS, usuarios, un WebSocket opcional para la web, y `--acl serverless` o `--acl minimo` para reproducir los permisos del broker real (ADR-026). **Nunca** se usa en la demo (I-03) |
| `tools/fake_edge_node.py` | Edge Node **real** con datos sintéticos, para desarrollar la web (F6). Comandos por teclado: `dnr`, `ok`, `crc`, `opcua off` y `on`, `saltar` (salto de `seq`), `escrituras falla` y `ok`, `matar` |
| `tests/` | pytest: diccionario, codec, máquina de estados, cliente OPC UA y sistema completo |

## 2. Versiones

Todas exactas. Ninguna tenía menos de dos semanas al fijarla (2026-11-12).

| Paquete | Versión | Por qué |
|---|---|---|
| Python | ≥ 3.11 | Probado en 3.11 |
| asyncua | 2.1.0 | La misma versión que la T2 (ADR-013) |
| paho-mqtt | 2.1.0 | MQTT 3.1.1 con TLS y Will. La 2.2.0 salió el 2026-11-04 |
| protobuf | 7.36.2 | Runtime del código generado |
| cryptography | 50.0.2 | Es la que firma y cifra Basic256Sha256 |
| grpcio-tools / grpcio | 1.84.0 (dev) | Trae `protoc`, así que no hay que instalar nada aparte |
| amqtt | 0.12.1 (dev) | Broker solo para las pruebas |
| pytest / pytest-asyncio | 9.2.0 / 1.4.0 (dev) | — |

## 3. Instalación y generación del Protobuf

```bash
cd tarea-3/gateway-sparkplug
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt          # demo
.venv/bin/pip install -r requirements-dev.txt      # desarrollo y pruebas
```

En Windows las rutas son `.venv\Scripts\python`.

El módulo generado está versionado, así que solo hay que regenerarlo si cambia el `.proto`:

```bash
.venv/bin/python -m grpc_tools.protoc -I proto --python_out=src proto/sparkplug_b.proto
```

`test_sparkplug.py::test_proto_sin_modificar_y_pb2_al_dia` regenera el módulo en una carpeta
temporal y falla si no coincide con el versionado. También falla si el `.proto` deja de ser el de
Tahu.

## 4. Configuración

Todo se lee de `tarea-3/.env`, que se crea a partir de `.env.example` con permisos 600. Ese archivo
nunca va a git.

| Variable | Uso |
|---|---|
| `OPCUA_URL` | `opc.tcp://<IP literal del dispositivo 2>:4840`. Nunca un nombre de host (T2) |
| `OPCUA_SEGURIDAD` | `SignAndEncrypt` (ADR-009). `None` solo para diagnóstico |
| `OPCUA_CLIENTE_USUARIO` / `OPCUA_CLIENTE_CLAVE` | Usuario con permiso de escritura. Sin él, los DCMD terminan en `BadUserAccessDenied` |
| `MQTT_HOST`, `MQTT_PUERTO_TLS` | Broker en la nube, puerto 8883 con TLS |
| `MQTT_USUARIO_EDGE` / `MQTT_CLAVE_EDGE` | Usuario `edge_node` (ADR-005) |
| `MQTT_CA` | Vacío: las CA del sistema |
| `SPB_GROUP_ID`, `SPB_EDGE_NODE_ID`, `SPB_DEVICE_ID`, `SPB_HOST_ID` | Diccionario §4 |

**Seguridad**

- MQTT sin TLS se rechaza, salvo que el broker sea `127.0.0.1`.
- Los CMD recibidos se validan antes de escribir nada: se descartan si llegan retenidos, si son
  para otro nodo, si superan 16 KiB, si la métrica es desconocida o de solo lectura, o si el tipo
  o el rango no corresponden.
- Una sesión OPC UA anónima es de solo lectura. Lo impone el servidor, no este cliente.

## 5. Certificados OPC UA (confianza mutua)

1. Traer el certificado del servidor. Su huella está en el panel de Node-RED, en
   *Servidor OPC UA · lista de confianza*:

   ```bash
   .venv/bin/python tools/traer_certificado_servidor.py opc.tcp://192.168.10.1:4840 --huella <sha1 del panel>
   ```

   Si la huella no coincide, **no se guarda nada**. En cada conexión el cliente vuelve a verificar
   que el servidor presente ese mismo certificado.
2. Arrancar el Edge Node. La primera vez genera `pki/own/cliente_cert.der` (RSA 2048, URI
   `urn:unraf:pdci:t3:gateway`) e imprime su huella. El servidor lo rechaza, y se reintenta con
   retroceso 1, 2, 4… s.
3. En el panel de Node-RED, comparar la huella y tocar **Confiar**. El intento siguiente abre la
   sesión, sin reiniciar nada (`docs/seguridad-opcua.md` §4).

## 6. Ejecución

```bash
.venv/bin/python src/sparkplug_edge_node.py                 # demo: .env apuntando a la nube
.venv/bin/python src/sparkplug_edge_node.py --opcua-modo lectura   # Modo A de la T2, para comparar (ADR-004)
.venv/bin/python src/sparkplug_edge_node.py --esperar-host  # BIRTH solo con la Host Application en línea
```

**Ctrl+C** publica el NDEATH y desconecta. La especificación 3.0 lo exige en una desconexión
intencional.

**`kill -9` o un cable cortado**: el NDEATH lo publica el broker (el Will).

- Tras un kill, el sistema operativo cierra el socket y el NDEATH sale **enseguida**.
- Tras un corte silencioso, sale a los 1,5 × 10 s de keepalive, es decir, a los **15 s**.

**Registro de evidencia**: `logs/edge-node-<fecha>.jsonl`. Cada mensaje publicado (`tx`) o recibido
(`rx`) ocupa una línea con tópico, tipo, QoS, `seq`, `bdSeq` y las métricas con nombre, alias,
tipo y valor. Cada Write OPC UA ocupa otra línea con su StatusCode.

### Desarrollo sin hardware ni nube

```bash
.venv/bin/python tools/broker_dev.py --carpeta .dev-broker --puerto 18883 --puerto-ws 18884   # CA, claves y WebSocket para la web
.venv/bin/python tools/observador_sparkplug.py --mqtt-ca .dev-broker/ca.pem --puerto 18883 --salida logs/obs.jsonl
.venv/bin/python src/sparkplug_edge_node.py --mqtt-ca .dev-broker/ca.pem      # con MQTT_HOST=127.0.0.1
.venv/bin/python tools/host_comandos.py --mqtt-ca .dev-broker/ca.pem dcmd Outputs/LedDigital true
.venv/bin/python tools/fake_edge_node.py --env <.env> --mqtt-ca .dev-broker/ca.pem   # en lugar del Edge real
```

## 7. Pruebas

```bash
.venv/bin/python -m pytest              # 61 pruebas, ~18 s
.venv/bin/python -m pytest -m "not red" # sin red: diccionario, codec y máquina de estados (0,5 s)
```

| Archivo | Qué prueba |
|---|---|
| `test_metrics.py` | El diccionario real da las 15 métricas. Se **rechazan** alias repetidos, un tipo no soportado o Rebirth con alias |
| `test_sparkplug.py` | Ida y vuelta por tipo: UInt32 en `int_value`, Int64 en complemento a 2, `is_null`. `seq` vuelve de 255 a 0. `timestamp` en ms. Tópicos. `.proto` sin modificar y `_pb2` al día |
| `test_ciclo_vida.py` | NBIRTH con `seq` = 0, `bdSeq`, Rebirth sin alias y las cuatro capas. DBIRTH. DATA solo ante cambio y solo con alias. Un único `seq` para NDATA y DDATA en 600 mensajes. DDEATH y DBIRTH. Reconexión. `bdSeq` persistido, con 255→0. Rebirth. DCMD por alias y por nombre, más 9 casos de rechazo. STATE |
| `test_opcua_client.py` | Servidor asyncua real: 10 ítems, un Write que vuelve por la suscripción, escritura sobre un nodo de solo lectura, caída del servidor y reconexión con retroceso 1 s → 2 s |
| `test_sistema.py` | **El Edge Node como subproceso** contra un broker TLS y un servidor OPC UA. Recorre el ciclo de vida completo, incluido el **corte del broker** (`bdSeq`+1, `Reconexiones`=1) y el **kill** (NDEATH emitido por el broker con el `bdSeq` que corresponde). Al final verifica que el observador **no registró violaciones** |
| `test_permisos_broker.py` | Los **permisos reales del broker** (ADR-026): con el perfil `serverless`, el Edge Node publica aunque se le rechace la suscripción a STATE (falla sin la corrección, verificado). Además, la clave de la web puede publicar un NBIRTH falso con `serverless` y no con `minimo` |

Las pruebas del núcleo se validaron con mutación: `seq` módulo 257 y `Reconexiones` sin incrementar
se detectan las dos.

**Sesión real de punta a punta (PC, 2026-11-12)**, archivada en
`docs/capturas/sparkplug-pc-observador.jsonl` (observador) y `sparkplug-pc-edge-node.jsonl`:

- **Cadena**: Edge Node, luego OPC UA SignAndEncrypt con usuario, luego Node-RED, luego Modbus,
  luego el simulador, que ejecuta el stack del firmware.
- **Mensajes**: NBIRTH 3, DBIRTH 4, NDATA 262, DDATA 777, DCMD 8, DDEATH 1, NDEATH 1 (emitido por el
  broker al matar el proceso) y NCMD 1.
- **`seq`**: dio la vuelta de 255 a 0 tres veces sin ninguna violación. `bdSeq` 0, 0 y 1 (nacimiento,
  Rebirth y reinicio).
- **Camino de comando**: 8 de 8 DCMD terminaron en `Write … Good`, y el LED del esclavo conmutó cada
  vez. Del DCMD al DDATA de confirmación tardó **149-223 ms** (mediana 203 ms), medido con broker
  local.
- **Agrupamiento** (ADR-021): pasó de 9,3 a 4,9 mensajes por segundo.

## 8. Pendiente

| # | Prueba | Criterio |
|---|---|---|
| P-1 | Crear el broker en la nube y los tres usuarios con permisos por tópico (ADR-005) | `edge_node` no puede suscribirse a `spBv1.0/#` (SUBACK 0x80) |
| P-2 | Edge Node contra la nube, con **MQTT Explorer** suscripto a `spBv1.0/#` con el usuario `observador` | Se ven NBIRTH, DBIRTH, NDATA y DDATA. Al matar el proceso, el NDEATH del broker |
| P-3 | La misma sesión con `tools/observador_sparkplug.py` archivando | Los 7 tipos y `violaciones: ninguna` |
| P-4 | Desde la red del aula: `openssl s_client -connect <broker>:8883` (R-06) | Handshake TLS correcto |
| P-5 | Banco: Raspberry Pi, `eth0`, el ESP32 real | El mismo criterio de salida. Latencia DCMD → LED medida |

**Limitaciones conocidas**

- El ruido del ADC del ESP32 no tiene banda muerta y cada cambio genera un DDATA. Hay que medirlo en
  el banco antes de decidir si agregarla (YAGNI).
- `Status/OPCUA/Estado` informa la sesión del dispositivo 3 con el dispositivo 2, como lo define el
  diccionario.
