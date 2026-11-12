# Device 3: OPC UA client and Sparkplug B Edge Node

Tarea Nº3 · Fase F5 · PC o VM (Python 3.11+)

The device has two pieces:

- An **OPC UA client**. It is the T2 one, adapted (ADR-013). It subscribes to the device 2 nodes
  that the data dictionary lists.
- A **Sparkplug B 3.0 Edge Node**. It publishes those nodes to an MQTT broker in the cloud (I-03)
  and carries the Host Application's commands down to the ESP32's LED.

**Status.** Everything below was tested on the PC: the 58 tests pass, plus one real end-to-end
session against Node-RED, the OPC UA server in SignAndEncrypt and the simulator of the slave.
Two things are pending and are manual (§8):

- the run against the **cloud broker** (it needs the account and the users of ADR-005);
- the check with **MQTT Explorer**.

---

## 1. Contents

| Path | Contents |
|---|---|
| `src/opcua_client.py` | T2 client. The header lists what was reused, adapted and dropped, with the reason. Subscription with 100/100/1, reconnection with backoff 1-30 s and writes |
| `src/metrics.py` | The metrics are **read from** `docs/diccionario-de-datos.md`: name, type, alias, origin, NodeId and whether it is writable. No metric is written in the code (I-06) |
| `src/sparkplug.py` | Topics, `seq` and Protobuf encoding by type (spec §6.4.16). No state and no network |
| `src/ciclo_vida.py` | **Lifecycle state machine** (ADR-020): NBIRTH, DBIRTH, NDATA, DDATA, DDEATH, Rebirth and DCMD. Each rule cites its `tck-id` |
| `src/sparkplug_edge_node.py` | I/O: paho MQTT (TLS, Will), the bridge with asyncio, the JSONL record and the program |
| `src/sparkplug_b_pb2.py` | **Generated** from `proto/` (§3). Not edited |
| `proto/sparkplug_b.proto` | Official Eclipse Tahu file, **unmodified**. Its SHA-256 is pinned in a test |
| `tools/traer_certificado_servidor.py` | Fetches the OPC UA server certificate. It saves it only if the thumbprint matches the panel's |
| `tools/observador_sparkplug.py` | Read-only subscriber. It decodes, **verifies `seq` and `bdSeq`** and archives as JSONL |
| `tools/host_comandos.py` | NCMD Rebirth and DCMD, as the web will send them in F6 |
| `tools/broker_dev.py` | **Development** broker (amqtt) with TLS and users. **Never** used in the demo (I-03) |
| `tests/` | pytest: dictionary, codec, state machine, OPC UA client and the full system |

## 2. Versions

All are exact. None was less than two weeks old when it was pinned (2026-11-12).

| Package | Version | Why |
|---|---|---|
| Python | ≥ 3.11 | Tested on 3.11 |
| asyncua | 2.1.0 | The same version as the T2 (ADR-013) |
| paho-mqtt | 2.1.0 | MQTT 3.1.1 with TLS and Will. 2.2.0 came out on 2026-11-04 |
| protobuf | 7.36.2 | Runtime of the generated code |
| cryptography | 50.0.2 | It is what signs and encrypts Basic256Sha256 |
| grpcio-tools / grpcio | 1.84.0 (dev) | Ships `protoc`, so there is nothing to install separately |
| amqtt | 0.12.1 (dev) | Broker for the tests only |
| pytest / pytest-asyncio | 9.2.0 / 1.4.0 (dev) | — |

## 3. Installation and Protobuf generation

```bash
cd tarea-3/gateway-sparkplug
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt          # demo
.venv/bin/pip install -r requirements-dev.txt      # development and tests
```

On Windows the paths are `.venv\Scripts\python`.

The generated module is versioned, so you only need to regenerate it if the `.proto` changes:

```bash
.venv/bin/python -m grpc_tools.protoc -I proto --python_out=src proto/sparkplug_b.proto
```

`test_sparkplug.py::test_proto_sin_modificar_y_pb2_al_dia` regenerates the module in a temporary
folder and fails if it doesn't match the versioned one. It also fails if the `.proto` stops
being Tahu's.

## 4. Configuration

Everything is read from `tarea-3/.env`, created from `.env.example` with permissions 600. That
file never goes into git.

| Variable | Use |
|---|---|
| `OPCUA_URL` | `opc.tcp://<literal IP of device 2>:4840`. Never a host name (T2) |
| `OPCUA_SEGURIDAD` | `SignAndEncrypt` (ADR-009). `None` only for diagnostics |
| `OPCUA_CLIENTE_USUARIO` / `OPCUA_CLIENTE_CLAVE` | User with write permission. Without it, the DCMDs end in `BadUserAccessDenied` |
| `MQTT_HOST`, `MQTT_PUERTO_TLS` | Cloud broker, port 8883 with TLS |
| `MQTT_USUARIO_EDGE` / `MQTT_CLAVE_EDGE` | `edge_node` user (ADR-005) |
| `MQTT_CA` | Empty: the system CAs |
| `SPB_GROUP_ID`, `SPB_EDGE_NODE_ID`, `SPB_DEVICE_ID`, `SPB_HOST_ID` | Dictionary §4 |

**Security**

- MQTT without TLS is refused unless the broker is `127.0.0.1`.
- Received CMDs are validated before anything is written: retained, from another node, larger
  than 16 KiB, unknown metric, read-only, wrong type or out of range.
- An anonymous OPC UA session is read-only. The server enforces it, not this client.

## 5. OPC UA certificates (mutual trust)

1. Bring in the server certificate. Its thumbprint is in the Node-RED panel, under
   *Servidor OPC UA · lista de confianza*:

   ```bash
   .venv/bin/python tools/traer_certificado_servidor.py opc.tcp://192.168.10.1:4840 --huella <sha1 del panel>
   ```

   If the thumbprint doesn't match, **nothing is saved**. On each connection the client checks
   again that the server is presenting that same certificate.
2. Start the Edge Node. The first time it generates `pki/own/cliente_cert.der` (RSA 2048, URI
   `urn:unraf:pdci:t3:gateway`) and prints its thumbprint. The server rejects it, and it is
   retried with backoff 1, 2, 4… s.
3. In the Node-RED panel, compare the thumbprint and click **Confiar**. The next attempt opens
   the session; no restart needed (`docs/seguridad-opcua.md` §4).

## 6. Running

```bash
.venv/bin/python src/sparkplug_edge_node.py                 # demo: .env pointing at the cloud
.venv/bin/python src/sparkplug_edge_node.py --opcua-modo lectura   # T2 Mode A, to compare (ADR-004)
.venv/bin/python src/sparkplug_edge_node.py --esperar-host  # BIRTH only with the Host Application online
```

**Ctrl+C** publishes the NDEATH and disconnects. Spec 3.0 requires it on an intentional
disconnect.

**`kill -9` or a cut cable**: the broker publishes the NDEATH (the Will).

- After a kill, the operating system closes the socket and the NDEATH comes out **right away**.
- After a silent cut, it comes out after 1.5 × the 10 s keepalive, that is, **15 s**.

**Evidence record**: `logs/edge-node-<fecha>.jsonl`. Each published (`tx`) or received (`rx`)
message takes one line with topic, type, QoS, `seq`, `bdSeq` and the metrics with name, alias,
type and value. Each OPC UA Write takes another line with its StatusCode.

### Development without hardware or cloud

```bash
.venv/bin/python tools/broker_dev.py --carpeta .dev-broker --puerto 18883   # prints the CA and keys
.venv/bin/python tools/observador_sparkplug.py --mqtt-ca .dev-broker/ca.pem --puerto 18883 --salida logs/obs.jsonl
.venv/bin/python src/sparkplug_edge_node.py --mqtt-ca .dev-broker/ca.pem      # with MQTT_HOST=127.0.0.1
.venv/bin/python tools/host_comandos.py --mqtt-ca .dev-broker/ca.pem dcmd Outputs/LedDigital true
```

## 7. Tests

```bash
.venv/bin/python -m pytest              # 58 tests, ~16 s
.venv/bin/python -m pytest -m "not red" # without network: dictionary, codec and state machine (0.5 s)
```

| File | What it tests |
|---|---|
| `test_metrics.py` | The real dictionary yields the 15 metrics. Duplicate aliases, an unsupported type or Rebirth with an alias are **rejected** |
| `test_sparkplug.py` | Round trip for each type: UInt32 in `int_value`, Int64 in two's complement, `is_null`. `seq` wraps from 255 to 0. `timestamp` in ms. Topics. Unmodified `.proto` and up-to-date `_pb2` |
| `test_ciclo_vida.py` | NBIRTH with `seq` = 0, `bdSeq`, Rebirth with no alias and the four layers. DBIRTH. DATA only on change and only with alias. One `seq` for NDATA and DDATA across 600 messages. DDEATH and DBIRTH. Reconnection. Persisted `bdSeq` with 255→0. Rebirth. DCMD by alias and by name, plus 9 rejection cases. STATE |
| `test_opcua_client.py` | Real asyncua server: 10 items, a Write that comes back through the subscription, a write to a read-only node, the server dropping and reconnecting with backoff 1 s → 2 s |
| `test_sistema.py` | **The Edge Node as a subprocess** against a TLS broker and an OPC UA server. It runs through the whole lifecycle, including the **broker cut** (`bdSeq`+1, `Reconexiones`=1) and the **kill** (NDEATH emitted by the broker with the matching `bdSeq`). It ends by checking that the observer recorded **no violations** |

The core's tests were validated with mutation: `seq` modulo 257 and `Reconexiones` without
incrementing are both detected.

**Real end-to-end session (PC, 2026-11-12)**, archived in
`docs/capturas/sparkplug-pc-observador.jsonl` (observer) and `sparkplug-pc-edge-node.jsonl`:

- **Chain**: Edge Node, then OPC UA SignAndEncrypt with a user, then Node-RED, then Modbus, then
  the simulator, which runs the firmware's stack.
- **Messages**: NBIRTH 3, DBIRTH 4, NDATA 262, DDATA 777, DCMD 8, DDEATH 1, NDEATH 1 (emitted by
  the broker on the kill) and NCMD 1.
- **`seq`**: wrapped from 255 to 0 three times with no violation. `bdSeq` 0, 0 and 1 (birth,
  Rebirth and restart).
- **Command path**: 8 of 8 DCMDs ended in `Write … Good`, and the slave's LED switched each time.
  From DCMD to the confirmation DDATA it took **149-223 ms** (median 203 ms), measured with a
  local broker.
- **Grouping** (ADR-021): it went from 9.3 to 4.9 messages per second.

## 8. Pending

| # | Test | Criterion |
|---|---|---|
| P-1 | Create the cloud broker and the three users with per-topic permissions (ADR-005) | `edge_node` cannot subscribe to `spBv1.0/#` (SUBACK 0x80) |
| P-2 | Edge Node against the cloud, with **MQTT Explorer** subscribed to `spBv1.0/#` with the `observador` user | NBIRTH, DBIRTH, NDATA and DDATA visible. On killing the process, the broker's NDEATH |
| P-3 | Same session with `tools/observador_sparkplug.py` archiving | The 7 types and `violaciones: ninguna` |
| P-4 | From the classroom network: `openssl s_client -connect <broker>:8883` (R-06) | TLS handshake OK |
| P-5 | Bench: Raspberry Pi, `eth0`, the real ESP32 | Same exit criterion. Latency DCMD → LED measured |

**Known limitations**

- The ESP32's ADC noise has no deadband and each change produces a DDATA. Measure it on the
  bench before deciding whether to add one (YAGNI).
- `Status/OPCUA/Estado` reports the session from device 3 to device 2, as the dictionary
  defines it.
