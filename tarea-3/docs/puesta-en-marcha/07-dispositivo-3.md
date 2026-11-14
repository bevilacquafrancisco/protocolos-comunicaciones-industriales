# 07 · Notebook: cliente OPC UA y Edge Node Sparkplug B (dispositivo 3)

**Objetivo:** el cliente OPC UA de la T2 (adaptado, ADR-013) conectado a la Raspberry Pi en
**SignAndEncrypt + usuario**, y el Edge Node publicando NBIRTH, DBIRTH y DDATA en el broker de la nube.
Cubre las consignas 2 y 3.

**Requisitos:**

- 01: el venv de `gateway-sparkplug`;
- 02: el `tarea-3/.env` con los datos del broker;
- 04: el cable Ethernet, con `ping 192.168.10.1` respondiendo;
- 06: MODBUS = DONE;
- la **huella del servidor** anotada en 05 §7.

**Tiempo:** ~30 min.

Detalle del dispositivo: [gateway-sparkplug/README.md](../../gateway-sparkplug/README.md). Confianza
OPC UA: [seguridad-opcua.md §3-§4](../seguridad-opcua.md).

---

## 1. Completar el `.env` (sección OPC UA)

```powershell
PS> notepad tarea-3\.env
```

| Variable | Valor | Por qué |
|---|---|---|
| `OPCUA_URL` | `opc.tcp://192.168.10.1:4840` | **IP literal**, nunca un nombre de host: el tráfico va por el cable y no por la Wi-Fi (regla de la T2) |
| `OPCUA_SEGURIDAD` | `SignAndEncrypt` | ADR-009 |
| `OPCUA_CLIENTE_USUARIO` / `OPCUA_CLIENTE_CLAVE` | `operador` / la clave **en claro** de 05 §4.1 | Sin usuario, los comandos terminan en `BadUserAccessDenied` |
| `OPCUA_PKI` | vacío (= `gateway-sparkplug/pki`) | Ignorado por git |
| `SPB_GROUP_ID`, `SPB_EDGE_NODE_ID`, `SPB_DEVICE_ID`, `SPB_HOST_ID` | los de `.env.example` | Diccionario §4 |

## 2. Confianza mutua OPC UA

En OPC UA, **cada extremo** valida el certificado del otro contra su propia lista de confianza. Son
dos pasos, uno en cada sentido.

**2.1 La notebook confía en el servidor.** El certificado se trae por la red, pero **solo se guarda si
la huella coincide** con la que se anotó del panel en 05 §7, que llegó por otro canal:

```powershell
PS> cd tarea-3\gateway-sparkplug
PS> .venv\Scripts\python tools\traer_certificado_servidor.py opc.tcp://192.168.10.1:4840 --huella <huella del panel>
Huella SHA-1 del servidor: 9649...
guardado en ...\gateway-sparkplug\pki\servidor_cert.der
```

**[SEC]** Si la huella **no** coincide, no se guarda nada. Es lo que impide que un equipo impostor en
la red se haga pasar por el dispositivo 2.

**2.2 El servidor confía en la notebook.** Arrancar el Edge Node por primera vez:

```powershell
PS> .venv\Scripts\python src\sparkplug_edge_node.py
```

El log muestra la huella del certificado propio de la notebook (se genera solo, RSA 2048, URI
`urn:unraf:pdci:t3:gateway`), y después el rechazo del servidor, con reintentos de 1, 2, 4… s:

```
opcua INFO  [C1] certificado propio ...\pki\own\cliente_cert.der (huella a205...): confiarlo en el panel de Node-RED
opcua WARNING [C7] TRANSPORTE ConnectionError: connection lost
opcua INFO  [C7] reintento 1 en 1 s
```

Mientras tanto, el Edge Node **ya** publicó su NBIRTH con `Status/OPCUA/Estado = ERROR`. El
diagnóstico del nodo no depende del enlace que diagnostica (ADR-006).

En el Dashboard (túnel de 05 §7), *Configuración → Servidor OPC UA · lista de confianza*:

1. Aparece `rechazado · urn:unraf:pdci:t3:gateway · <huella>`.
2. **Comparar** esa huella con la del log de la notebook.
3. **Confiar** y confirmar en el diálogo.

En el siguiente reintento, la sesión se abre **sin reiniciar nada**:

```
opcua INFO  [C1] sesion activa
opcua INFO  [C3] suscripcion: PublishingInterval=100 ms MaxKeepAlive=10 Lifetime=300 | 10 items, SamplingInterval=100 ms QueueSize=1
edge  INFO  Status/OPCUA/Estado = DONE
```

Puede aparecer este aviso, que es **esperado** en HiveMQ Serverless (ADR-026): el permiso de
`edge_node` cubre el grupo, pero no el STATE de la Host Application, que es opcional.

```
edge  WARNING el broker no autoriza spBv1.0/STATE/HA01_WebDashboard: se sigue sin conocer el STATE de la Host Application
```

## 3. Ver los mensajes en el broker

**3.1 Observador** (otra terminal, en `gateway-sparkplug`). Decodifica, **verifica `seq` y `bdSeq`** y
archiva:

```powershell
PS> New-Item -ItemType Directory -Force ..\docs\capturas\banco | Out-Null
PS> .venv\Scripts\python tools\observador_sparkplug.py --salida ..\docs\capturas\banco\sparkplug-banco.jsonl
```

Tienen que aparecer `NBIRTH seq=0`, después `DBIRTH`, y un flujo de `DDATA` (potenciómetro) y `NDATA`
(contadores, una vez por segundo).

**3.2 MQTT Explorer.** Crear una conexión con estos datos:

- host: la URL del broker;
- puerto: 8883;
- *Encryption (tls)*: activado;
- usuario y clave: los de `observador`;
- en *Advanced*, suscripción `spBv1.0/#`.

En el árbol de tópicos aparece `spBv1.0/UNRaf_PdCI_2026/{NBIRTH,NDATA}/EN01_Gateway` y
`.../{DBIRTH,DDATA}/EN01_Gateway/DEV01_ESP32_Slave`.

El payload es **Protobuf** (I-02). Si la versión instalada de MQTT Explorer ofrece un formato *Sparkplug
B* para ver el valor, elegirlo. Si no, se ve en hexadecimal, y la decodificación la da el observador
(3.1) o `tools/volcado_sparkplug.py`, campo por campo.

## 4. Camino de comando hasta el LED

En otra terminal de `gateway-sparkplug`:

```powershell
PS> .venv\Scripts\python tools\host_comandos.py dcmd Outputs/LedDigital true
PS> .venv\Scripts\python tools\host_comandos.py dcmd Outputs/LedPWM 128
```

El camino es DCMD (nube) → Edge Node → Write OPC UA (SignAndEncrypt) → FC 05/06 → ESP32.

| ✓ | Esperado |
|---|---|
| ☐ | El **LED físico** enciende y el PWM toma brillo medio |
| ☐ | Log del Edge Node: `Write Outputs/LedDigital = True -> Good`. `Good` solo si el esclavo devolvió el eco (ADR-015) |
| ☐ | Observador: un `DCMD` y, poco después, un `DDATA` con el valor confirmado |

| Síntoma | Causa | Solución |
|---|---|---|
| `el certificado del servidor (...) NO es el confiado` | La PKI de la Raspberry se regeneró (se borró `~/.pdci-t3`) | Repetir 2.1 con la huella nueva del panel |
| Sigue el rechazo después de "Confiar" | Se confió otra huella, o hay otro cliente rechazado | Revisar que la huella del panel y la del log coincidan |
| `Write ... -> BadUserAccessDenied` | Falta el usuario OPC UA o la clave está mal | §1: `OPCUA_CLIENTE_USUARIO/CLAVE` |
| `Write ... -> BadCommunicationError` | El esclavo no confirmó: está caído o desconectado | 06 §3 |
| `TRANSPORTE ... timed out` sin rechazo | Cable, IP de la notebook o `ufw` | 04 §4; en la Raspberry, `sudo ufw status` debe mostrar 4840 en `eth0` |
| `CONNACK rechazado` (MQTT) | Credenciales de `edge_node` | 02 §4 |

---

## Criterio de salida

- [ ] Sesión OPC UA **SignAndEncrypt** con usuario. La confianza se dio en los dos sentidos, comparando
      las huellas.
- [ ] `Status/OPCUA/Estado = DONE` y la suscripción con 10 ítems.
- [ ] Observador y MQTT Explorer: NBIRTH (`seq` 0), DBIRTH, NDATA y DDATA en el broker de la nube.
- [ ] Un DCMD enciende el LED físico y vuelve un DDATA de confirmación.
