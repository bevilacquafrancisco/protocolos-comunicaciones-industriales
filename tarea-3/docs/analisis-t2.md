# Análisis de la Tarea Nº2 — insumo para la Tarea Nº3

Fase F0 · 2026-11-08 · Fuente: `tarea-2/` en la rama `develop` (commit `c7a86fd`) e informe
entregado `tarea-2/Bevilacqua_Peralta_PdCI_T2_26.pdf`.

---

## 0. Qué versión es "el cliente de la TP Nº2"

La T2 tiene tres implementaciones (`tarea-2/versiones/README.md`). La consigna de la T3 §2 dice
*"Utilizar el OPC client creado en TP Nº2"*, así que importa cuál se entregó.

| | v1 — original | **v2 — corrección Python** | v3 — Node-RED |
|---|---|---|---|
| Estado | Base del informe entregado | **"Versión que se presenta"** (`tarea-2/README.md`) | Alternativa, con la teoría en `docs/` |
| Pila | asyncua (sin versión fijada) | **asyncua 2.1.0** (`requirements.txt`) | node-opcua 2.160.0 |
| Probada | PC sin modificar + banco (captura `captura_none.pcapng`) | PC: `prueba_local.py` 50/50 (2026-10-20) | PC: 118 pruebas; banco no medido |

**Conclusión:** el cliente a reutilizar es el de la **v2** (`cliente_base.py` + `cliente_suscripcion.py`).
Coincide con lo que supone `tarea-3/CLAUDE.md` §3 (dispositivo 3 en Python con `asyncua`).

> **Inconsistencia a resolver antes del informe de T3:** el informe PDF entregado describe la
> **v1** (sincronización inicial por Read, dos `CreateMonitoredItems`, captura de 4453 paquetes y
> 70 s), mientras que el README declara que se presenta la **v2**. La captura de 4453 paquetes
> **no está en el repositorio**: la única `.pcapng` versionada es `captura_none.pcapng`
> (1978 tramas, 26,2 s, v1). Al citar números de la T2 hay que citar la captura que existe.

> El `CLAUDE.md` raíz del repositorio está desactualizado respecto de la T2: habla de
> `tarea-2/node-red/` y `tarea-2/agus/`, que hoy están en `tarea-2/versiones/v3-node-red/` y
> `versiones/v1-original-agustina/`.

## 1. Librería OPC UA y versión

| Dispositivo | Librería | Versión | Fuente |
|---|---|---|---|
| Cliente (v2) | `asyncua` (FreeOpcUa, Python) | **2.1.0**, fijada | `v2-correccion-python/requirements.txt` |
| Servidor (v2) | `asyncua` | 2.1.0 | ídem |
| Alternativa (v3) | `node-opcua` | 2.160.0 | `v3-node-red/docs/arquitectura-red.md` ADR-01 |

En esta PC **no está instalado `asyncua`**: `prueba_local.py` no se pudo volver a correr hoy. Sí se
corrieron las pruebas de la v3: `prueba_senales.js` + `prueba_flujos.js` 21/21 y
`prueba_opcua_tramas.py` 0 fallos.

## 2. Código del cliente (v2)

### 2.1 Estructura

| Archivo · bloque | Función | Líneas |
|---|---|---|
| `cliente_base.py` · C1 `conectar()` | `Client(url, timeout=4 s, watchdog_intervall=1 s)`; `GetEndpoints` explícito; `set_security(Basic256Sha256, mode, cert, key, server_cert)`; usuario y clave **desde el entorno** | 92-147 |
| `cliente_base.py` · `nodos_del_modelo()` | 4 NodeIds fijos de la T2 | 150-157 |
| `cliente_base.py` · C2 `tarea_rampa()` | Rampa triangular local | 164-176 |
| `cliente_base.py` · C4 `replicar()` | Lleva el `DataValue` a los LED **solo si `StatusCode.is_good()`** | 183-201 |
| `cliente_base.py` · C5 `Escritor` | `write_value(DataValue con SourceTimestamp)`; un rechazo (`BadUserAccessDenied`) se informa una vez y **no corta la sesión** | 208-261 |
| `cliente_base.py` · C6 | Consola cada 0,5 s | 268-277 |
| `cliente_base.py` · C7 `ejecutar_sesion()` / `main()` | Tareas en paralelo; la primera excepción cancela las demás; `disconnect()` siempre; reintento | 284-374 |
| `cliente_suscripcion.py` · C3 Modo B | `CreateSubscription` + **un** `CreateMonitoredItems` con los dos ítems | 90-128 |
| `cliente.py` · C3 Modo A | Un `ReadRequest` con los dos nodos cada 100 ms | 39-59 |
| `comun.py` | Pines, URL, NodeIds, rampas, **GPIO con `gpiozero`** | 1-273 |

### 2.2 Cómo se conecta

1. `connect_and_get_server_endpoints()`: canal temporal None → `GetEndpoints` → `CLO`
   (`cliente_base.py:113`). Comprueba que el modo pedido se ofrece **antes** de abrir sesión.
2. Si el modo no es None: certificados de `pki/own/` y del servidor en `pki/` (`:120-131`).
3. `set_user`/`set_password` desde `OPCUA_CLIENTE_USUARIO` / `OPCUA_CLIENTE_CLAVE` (`:134-138`).
4. `client.connect()` → HEL, OPN, CreateSession (timeout 60 s, `:42`), ActivateSession.

### 2.3 Cómo se suscribe (Modo B)

| Parámetro | Pedido | Fuente |
|---|---|---|
| PublishingInterval | 100 ms | `cliente_suscripcion.py:32` |
| SamplingInterval | 100 ms | `:33` |
| QueueSize | 1 | `:34` |
| MaxKeepAliveCount | 10 (KeepAlive cada 1 s) | `:38` |
| LifetimeCount | 300 (30 s) | `:41` |

Las notificaciones llegan a `ManejadorSuscripcion.datachange_notification(node, val, data)` y se
distribuyen por NodeId (`:63-77`). `status_change_notification` registra `BadTimeout`/`BadShutdown`.

### 2.4 Cómo reconecta

- **Detección:** `watchdog_intervall=1.0` (asyncua lee `ServerState` cada 1 s) →
  `connection_lost_callback` completa un *future* que corta la sesión (`cliente_base.py:310-318`).
- **Clasificación:** `UaStatusCodeError` (el servidor respondió con error) frente a
  `TimeoutError`/`ConnectionError`/`OSError` (no hubo respuesta) (`:359-367`).
- **Política:** reintento **fijo cada 2 s**, sin *backoff*, canal y sesión nuevos; la sesión vieja
  muere sola a los 60 s (`:38`, `:368-369`).
- **Verificado en banco** (informe T2 §7): con el cable cortado el LED remoto queda congelado y el
  generador local sigue; al reconectar, se recrea la suscripción sin intervención.

### 2.5 Reutilizable tal cual frente a adaptar

| Pieza | Veredicto | Motivo |
|---|---|---|
| C1 `conectar()` (descubrimiento, seguridad, usuario por entorno) | **Tal cual** | Independiente del modelo |
| `Escritor` (C5) | **Tal cual** | Es el camino `DCMD → Write`; ya distingue rechazo de error de transporte |
| `correr_hasta_falla()` | **Tal cual** | Genérico |
| Lazo de reconexión de `main()` (C7) | **Adaptar** | Debe publicar `Status/OPCUA/Estado` (DONE/ERROR) y disparar `DDEATH` al perder el canal y `DBIRTH` al recuperarlo (consigna T3 §4: *"DDEATH (pérdida del esclavo MODBUS o de la comunicación con el dispositivo 2)"*). Conviene *backoff* exponencial con tope |
| `ManejadorSuscripcion` (C3 Modo B) | **Adaptar** | De 2 NodeIds fijos a la lista del diccionario; entregar cada cambio al Edge Node con `SourceTimestamp` (será el `timestamp` de la métrica) |
| Parámetros de suscripción | **Adaptar** | 100 ms vale; revisar QueueSize = 1 con los contadores (un contador que salta 2 veces en 100 ms pierde el intermedio, aceptable) |
| `nodos_del_modelo()` | **Reescribir** | Pasa a leerse del diccionario de datos |
| C2 rampa, C4 LED, C6 consola, `Pulsador`/`Salidas` | **Descartar** | El dispositivo 3 es una PC: no tiene GPIO |
| `comun.py` | **Partir** | Importa `gpiozero` a nivel de módulo (`comun.py:32`): en la PC del dispositivo 3 sobra. Quedan URL, URIs y utilidades de tiempo |
| `cliente.py` (Modo A) | **Conservar** como alternativa conmutable (ADR-004) | Para mostrar la comparación en la defensa |
| `generar_certificados.py` | **Tal cual** | X.509 con URI = ApplicationUri |

**Estimación:** ≈ 60 % del código del cliente se reutiliza sin cambios; el resto es adaptación al
modelo nuevo, no reescritura del protocolo.

## 3. Espacio de direcciones del servidor (v2)

`servidor.py:244-287`, namespace `urn:unraf:pdci:t2` forzado a **ns=1** usando la URI del modelo
como ApplicationUri (`:412`, verificado en `:257-259`).

| NodeId | Tipo | AccessLevel | EURange | Escribe |
|---|---|---|---|---|
| `ns=1;s=Servidor` | Object | — | — | — |
| `ns=1;s=Servidor.EstadoPulsador` | Boolean | 1 = CurrentRead | — | servidor |
| `ns=1;s=Servidor.Rampa` | UInt16 | 1 = CurrentRead | 0..65535 (`Servidor.Rampa.EURange`, ns=0 BrowseName) | servidor |
| `ns=1;s=Cliente` | Object | — | — | — |
| `ns=1;s=Cliente.EstadoPulsador` | Boolean | 3 = Read\|Write | — | cliente |
| `ns=1;s=Cliente.Rampa` | UInt16 | 3 = Read\|Write | 0..65535 | cliente |

**Autorización** (`servidor.py:125-147`): anónimo = leer, navegar, suscribirse, **no** escribir;
usuario autenticado = además `Write`. Contraseña verificada contra hash **scrypt**
(`OPCUA_CLAVE_HASH`). Trust list con `pki/trusted/` y `pki/rechazados/` (`:150-179`).

Este patrón (objeto + variables `Objeto.Variable`, EURange como propiedad con NodeId fijo,
AccessLevel por variable) es el que replica el diccionario de la T3 §3.

## 4. Modos de seguridad probados

| Modo | En el banco (Raspberry Pi) | En la PC | Fuente |
|---|---|---|---|
| None + anónimo | ✅ **Único modo de banco documentado** | ✅ | Informe T2 §9: *"Las pruebas funcionales documentadas en este informe se realizaron con SecurityMode None y autenticación Anonymous."* |
| None + usuario | ⬜ No documentado | ✅ `prueba_local.py`; vector `sesion_None_usuario.json` (v3) | |
| Sign (Basic256Sha256) | ⬜ No documentado | ✅ conexión, `BadCertificateUntrusted` sin confianza (`prueba_local.py:230-235`); vector `sesion_Sign.json` | |
| SignAndEncrypt (Basic256Sha256) | ⬜ No documentado | ✅ Modo A y B (`prueba_local.py:254`); vector `sesion_SignAndEncrypt.json` | |
| Escritura anónima rechazada | ✅ con UaExpert, **sin captura de pantalla** | ✅ `BadUserAccessDenied` | Informe T2 §4.4 |

**Lo que se puede afirmar con evidencia** (`v3-node-red/docs/seguridad.md` §4, verificado sobre
vectores reales en la PC): en Sign el contenido queda legible y la firma HMAC-SHA256 ocupa 32 bytes;
en SignAndEncrypt quedan legibles solo cabecera, SecureChannelId y TokenId.

**Lo que NO se puede citar como medido:** latencia por modo de seguridad y tiempo de
establecimiento. `seguridad.md` §4 los deja como *"a medir en el banco"*. → La comparación de modos
que pide el informe de la T3 (§8 de `CLAUDE.md`) **hay que medirla en la T3**.

## 5. Mediciones citables sin repetir el experimento

| Medición | Valor | Dónde se midió | Fuente |
|---|---|---|---|
| Enlace Ethernet | 1000 Mb/s Full Duplex, 0 % pérdida en ping | Banco | Informe T2 §11.1 |
| Sesión completa HEL → CLO | 1978 tramas, 240 265 bytes en 26,2 s | Banco, v1, None | `evidencia/ANALISIS_captura_none.md` §4.1 |
| Mensajes por servicio (26 s) | Write 275/275 · Publish 263/262 · Read 28/28 (26 del watchdog) | Banco, v1 | ídem |
| Parámetros revisados de la suscripción | PI 100 ms, Lifetime 10 000, KeepAlive 4500 (v1) | Banco, v1 | ídem §3.4 |
| Canal y sesión | RevisedLifetime 3 600 000 ms; SessionTimeout 600 000 ms | Banco, v1 | ídem §4.3 |
| PublishResponse con un UInt16 | 204 B = 14 + 20 + 32 + **138** OPC UA | Banco | ídem §4.4 |
| WriteRequest `Cliente.Rampa` | **173 B** de trama, 107 B OPC UA | Banco | ídem §4.5 |
| WriteResponse | 130 B de trama, 64 B OPC UA | Banco | ídem |
| WriteRequest Boolean | 181 B, 115 B OPC UA | Banco | ídem |
| Eficiencia Write UInt16 | OPC UA 1,16 % (pedido) / 0,66 % (ida y vuelta) frente a MODBus RTU 25 % / 12,5 % | Banco + T1 | ídem §4.6, informe T2 §8.7 |
| Tiempo de un pedido en el medio | OPC UA ≈ 1,4 µs a 1 Gb/s; MODBus FC 06 ≈ 8,3 ms a 9600 bps | Calculado sobre tamaños medidos | ídem §4.6 |
| Read frente a suscripción, 60 s, rampa en movimiento | A: 1113 msj / 151 180 B · B: 1107 msj / 123 994 B | **PC** (`comparar_modos.py`) | `v3-node-red/docs/protocolo-opcua.md` §7.3 |
| Read frente a suscripción, rampa detenida | A: 1109 msj / 150 695 B · B: **126 msj / 10 954 B** (56 KeepAlive) | **PC** | ídem |
| Período de KeepAlive | 1,09 s (con MaxKeepAliveCount 10) | PC (vectores) | ídem §7.2 |
| Firma Sign | HMAC-SHA256 de 32 bytes | PC (vectores) | ídem §3 |
| Latencia pulsador → LED | **No medida** | — | `v3-node-red/CHECKLIST.md` 3.4 sin marcar |
| Latencia por modo de seguridad | **No medida** | — | `CHECKLIST.md` 4.8 sin marcar |

**Regla de cita:** lo medido en la PC se cita como *predicción o medición en loopback*, nunca como
banco (convención del repositorio: "los números medidos son evidencia, no adorno").

**El argumento clave para ADR-004 ya está medido:** la suscripción ahorra cuando el dato cambia más
lento que el PublishingInterval (11 % de los mensajes con la rampa detenida). En la T3 las E/S del
dispositivo 1 cambian por acción humana: es exactamente ese caso.

## 6. Decisiones de la T2 que la T3 debe respetar

| Decisión | Fuente | Implicancia en la T3 |
|---|---|---|
| **No usar los nodos servidor de la paleta de Node-RED**: Compact-Server acepta cualquier contraseña y depende de `vm2` vulnerable; OpcUa-Server guarda claves en texto plano | `v3-node-red/evidencia/INCONVENIENTES.md` I-03; ADR-01 | **Choca con ADR-001 de la T3**, que asume `node-red-contrib-opcua`. Ver `spike-nodered-opcua.md` |
| NodeIds fijos en ns=1 forzando la ApplicationUri | `servidor.py:248-259` | Se reutiliza con `urn:unraf:pdci:t3` |
| Contraseña OPC UA solo como hash scrypt, fuera del repositorio | `servidor.py:71-90`, `.env` | Igual en la T3 |
| IP literal del enlace, nunca nombre de host | `comun.py:44-46` | El dispositivo 3 apunta a la IP de la Raspberry Pi |
| Cliente que falla después de conectar **desconecta** (evita cliente zombi) | v3 I-04 | Se conserva en C7 |
| Conexión en segundo plano, sin acumular mensajes si el servidor no está | v3 I-07 | El Edge Node debe arrancar aunque OPC UA no esté |

## 7. Gaps de información

| Gap | Impacto | Cómo se cierra |
|---|---|---|
| Captura de 4453 paquetes citada en el informe T2, ausente del repositorio | Medio: no se puede re-verificar | Buscarla en la PC de Agustina o en las placas |
| Sign/SignAndEncrypt nunca probados en banco | Alto para el informe de T3 (comparación de modos) | Medir en la T3 (plan de pruebas N2.3) |
| Retroalimentación de la cátedra sobre la T2 | Medio | Pedirla |
| `asyncua` no instalado en esta PC | Bajo | `pip install asyncua==2.1.0` en el entorno del dispositivo 3 |
