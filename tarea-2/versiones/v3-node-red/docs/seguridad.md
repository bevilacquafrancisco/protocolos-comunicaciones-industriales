# Seguridad en OPC UA y modelo de amenazas del sistema

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Desarrolla las consignas 4.7 (modos y políticas), 4.8 (certificados, trust
list, qué queda legible, latencia) y 4.9 (autenticación de usuario), y el
análisis de amenazas del sistema completo. El procedimiento de banco está en
[PARTE-4.md](../PARTE-4.md).

---

## Índice

1. [Las tres capas de seguridad de OPC UA](#1-las-tres-capas-de-seguridad-de-opc-ua)
2. [Modos y políticas de seguridad](#2-modos-y-políticas-de-seguridad)
3. [Certificados X.509 de aplicación y trust list](#3-certificados-x509-de-aplicación-y-trust-list)
4. [Qué queda legible en cada modo](#4-qué-queda-legible-en-cada-modo)
5. [Autenticación de usuario](#5-autenticación-de-usuario)
6. [Por qué se descartaron los nodos servidor de la paleta](#6-por-qué-se-descartaron-los-nodos-servidor-de-la-paleta)
7. [Modelo de amenazas (STRIDE)](#7-modelo-de-amenazas-stride)
8. [Encuadre IEC 62443](#8-encuadre-iec-62443)
9. [Referencias](#9-referencias)

---

## 1. Las tres capas de seguridad de OPC UA

| Capa | Mecanismo | Protege | Diapositiva |
|---|---|---|---|
| **Aplicación** | Certificado X.509 de instancia de aplicación + trust list | Que el **programa** del otro lado sea el autorizado | 19, 21 |
| **Comunicación** | Canal seguro: firma (HMAC) y cifrado (AES) de cada mensaje con claves derivadas en el OPN | **Integridad** y **confidencialidad** de los mensajes | 18, 19 |
| **Usuario** | Token de identidad en ActivateSession: anónimo, usuario/contraseña, certificado de usuario o token emitido | Que la **persona o rol** esté autorizado | 21 (pasos 3 y 4) |

La diferencia con MODBus es de fondo: MODBus no tiene ninguna de las tres.
Cualquier equipo con acceso al bus RS-485 puede leer y escribir cualquier
registro, y la única defensa es la **arquitectura** (segmentación).

## 2. Modos y políticas de seguridad

Un **endpoint** combina un **modo** de seguridad (qué se protege) con una
**política** (con qué algoritmos):

| SecurityMode | Firma | Cifrado | Uso |
|---|---|---|---|
| **None** | No | No | Diagnóstico, laboratorio aislado. Lo que pide la consigna para UaExpert y para la captura de la Parte 4.1 |
| **Sign** | Sí | No | Integridad y autenticación de origen; el contenido queda legible (útil si un analizador tiene que verlo) |
| **SignAndEncrypt** | Sí | Sí | Integridad + confidencialidad. Recomendado en producción |

**Política Basic256Sha256** (IEC 62541-7, perfil de seguridad):

| Uso | Algoritmo |
|---|---|
| Firma asimétrica (OPN, CreateSession, ActivateSession) | RSA-PKCS#1 v1.5 con SHA-256 |
| Cifrado asimétrico (OPN, contraseña del usuario) | RSA-OAEP (SHA-1) |
| Derivación de claves simétricas | P_SHA256 sobre los *nonces* de cliente y servidor |
| Firma simétrica (cada MSG) | **HMAC-SHA256** → 32 bytes por mensaje |
| Cifrado simétrico (cada MSG) | **AES-256-CBC** |
| Tamaño de clave RSA | 2048 a 4096 bits |

Las políticas Basic128Rsa15 y Basic256 (SHA-1) están **deprecadas** por la OPC
Foundation; el servidor del trabajo **no las ofrece** (`politicasServidor` en
`config.js`).

**Endpoints del servidor del trabajo** (prueba de integración 7 y registro del
nodo S2): por cada IP anunciada, exactamente tres:

```text
opc.tcp://192.168.10.1:4840  None            None
opc.tcp://192.168.10.1:4840  Sign            Basic256Sha256
opc.tcp://192.168.10.1:4840  SignAndEncrypt  Basic256Sha256
(+ los mismos tres con la IP de wlan0, para UaExpert)
```

**Cómo se establecen las claves (OPN).** En Sign/SignAndEncrypt, el OPN viaja
**cifrado con la clave pública del receptor y firmado con la privada del
emisor** (RSA). Dentro van los *nonces* aleatorios de cada lado. Ambos derivan
de esos nonces las mismas claves simétricas (firma, cifrado, vector
inicial), sin que las claves viajen nunca. Después todos los MSG usan esas
claves simétricas, mucho más rápidas que RSA. El TokenId identifica qué juego
de claves está vigente; al renovar el canal (OPN *Renew*) cambia.

## 3. Certificados X.509 de aplicación y trust list

**Rol del certificado.** Cada aplicación OPC UA (no cada persona) tiene un
certificado X.509 v3 con:

- la **clave pública** (la privada nunca sale del equipo: `own/private/`);
- el **ApplicationUri** en el campo *SubjectAltName* (URI), que debe coincidir
  con el que declara la aplicación: así un certificado robado no sirve para
  hacerse pasar por otra aplicación;
- los nombres de host o IP en *SubjectAltName* (DNS/IP);
- la vigencia y el uso de clave permitido.

**Trust list (lista de confianza).** Cada aplicación mantiene una PKI en disco
(node-opcua: `~/.node-red/opcua-pki/{servidor,cliente}/`):

| Carpeta | Contenido |
|---|---|
| `own/` | Certificado y clave privada **propios** |
| `trusted/certs/` | Certificados de las aplicaciones en las que se **confía** |
| `rejected/` | Certificados presentados por aplicaciones desconocidas |
| `issuers/` | Certificados de autoridades certificantes (CA) si se usan |

**Proceso de confianza** (cuando `aceptarCertificadosDesconocidos = false`,
como en el trabajo):

1. El cliente intenta conectarse con Sign o SignAndEncrypt. El servidor recibe
   el certificado del cliente en el OPN, no lo encuentra en `trusted/` y lo
   copia a `rejected/`. La conexión falla con **BadSecurityChecksFailed** (el
   servidor no da detalles a propósito, para no informar a un atacante).
2. Un **administrador** verifica que el certificado sea el esperado (huella
   SHA-1 o SHA-256, que se compara con la que muestra el cliente) y lo mueve
   de `rejected/` a `trusted/certs/`.
3. Lo mismo del lado del cliente con el certificado del servidor (UaExpert
   muestra un diálogo con la opción de confiar).
4. Se reintenta: la conexión segura se establece.

Es una confianza **explícita y manual**, sin una CA. En una planta con muchos
equipos se usa una CA propia y un *Global Discovery Server* (IEC 62541-12) que
distribuye certificados y listas de revocación.

**Por qué no se aceptan certificados automáticamente:** con
`automaticallyAcceptUnknownCertificate = true` cualquiera que genere un
certificado entra, y el canal "seguro" quedaría cifrado **con un desconocido**.
Esa opción solo se usa en las pruebas en la PC (`prueba_integracion_opcua.js`),
con PKI temporales que se borran al terminar.

## 4. Qué queda legible en cada modo

Verificado sobre los mensajes reales (`prueba_opcua_tramas.py`, sección 7):

| Parte del mensaje | None | Sign | SignAndEncrypt |
|---|---|---|---|
| MessageType, ChunkType, MessageSize | legible | legible | legible |
| SecureChannelId, TokenId | legible | legible | legible |
| SequenceNumber, RequestId | legible | legible | **cifrado** |
| TypeId (qué servicio es) | legible | legible | **cifrado** |
| RequestHeader (token de sesión, hora) | legible | legible | **cifrado** |
| NodeId, valor escrito | legible | legible | **cifrado** |
| Firma al final | no hay | 32 bytes HMAC-SHA256 | 32 bytes, dentro de lo cifrado |
| OPN | legible | **cifrado con RSA** (salvo la cabecera asimétrica) | **cifrado con RSA** |
| GetEndpoints (descubrimiento) | legible | legible (canal None aparte) | legible (canal None aparte) |

En Wireshark: con None y Sign el disector `opcua` muestra el árbol completo. Con
SignAndEncrypt muestra la cabecera y *Encrypted data*, y no puede saber si un
MSG es un Write o un Publish. Lo único que se infiere es el **tamaño** y el
**ritmo** (análisis de tráfico): un MSG de ~130 bytes cada 100 ms sigue
pareciendo una suscripción.

**Sign protege contra modificación, no contra lectura.** Un atacante en el
enlace puede leer el valor de la rampa, pero si lo modifica la firma no
coincide y el receptor descarta el mensaje (y cierra el canal). En control
industrial esto suele ser lo prioritario: **integridad antes que
confidencialidad** (IEC 62443).

**Latencia** (consigna 4.8, a medir en el banco, [PARTE-4.md §7](../PARTE-4.md)).
Lo esperable: RSA solo se usa al abrir el canal y la sesión (cientos de ms en
una RPi); cada MSG agrega HMAC-SHA256 (Sign) y AES-256-CBC (SignAndEncrypt)
sobre ~100 bytes, que en un Cortex-A72 cuestan microsegundos. La diferencia en
la latencia del intercambio en régimen debería ser **inferior al milisegundo**,
y la de **establecimiento** de la conexión, notoria.

## 5. Autenticación de usuario

### 5.1 En qué mensaje viaja el token

El token de identidad viaja en el **ActivateSessionRequest**, dentro del campo
`UserIdentityToken` (un ExtensionObject). Verificado en los vectores reales
(`sesion_None_usuario.json`):

| Campo | Valor real | Qué significa |
|---|---|---|
| UserIdentityToken.TypeId | `ns=0;i=324` | **UserNameIdentityToken** (el anónimo es i=321) |
| PolicyId | `username_basic256Sha256` | La política de token que el servidor anunció en GetEndpoints para ese endpoint |
| UserName | `operador` | **Legible** (sin cifrar) dentro del token |
| Password | ByteString de 256 bytes | **Cifrada** |
| EncryptionAlgorithm | `http://www.w3.org/2001/04/xmlenc#rsa-oaep` | Cómo se cifró la contraseña |

### 5.2 Cómo se protege

La contraseña **no** se protege con el canal sino **por sí misma**:

1. En la respuesta a CreateSession el servidor envía un **ServerNonce**
   aleatorio y su certificado.
2. El cliente arma `longitud + contraseña + ServerNonce` y lo cifra con
   **RSA-OAEP usando la clave pública del certificado del servidor**.
3. Solo el servidor, con su clave privada, puede descifrarlo. Comprueba que el
   nonce sea el que él generó: así una contraseña capturada **no puede
   reenviarse** en otra sesión (protección contra *replay*).

Por eso, **aun con el canal en modo None**, la contraseña viaja cifrada: el
endpoint None del servidor anuncia la política de token `username_basic256Sha256`.
El **nombre de usuario**, en cambio, sí queda legible en modo None. Es un hallazgo
concreto para mostrar en Wireshark.

Un servidor que anunciara la política de token `None` para usuario/contraseña
recibiría la contraseña **en claro** (la herramienta lo marca como
"EN CLARO"). node-opcua lo advierte al arrancar.

### 5.3 Del lado del servidor

- **Verificación:** `credenciales.verificarClave()` compara contra un hash
  **scrypt** (N = 2¹⁷, r = 8, p = 1: los mínimos de OWASP), con comparación de
  tiempo constante (`timingSafeEqual`). La contraseña nunca se almacena.
- **Fallo:** una clave incorrecta produce el rechazo de ActivateSession
  (prueba de integración 13); el servidor registra el intento **sin** la clave.
- **Autorización por rol:** con `soloAutenticadosEscriben = true`, el anónimo
  puede leer pero no escribir: `UserAccessLevel = 1`, Write →
  **BadUserAccessDenied**; el usuario autenticado escribe normalmente (prueba
  15). Es la demostración de **para qué** sirve la autenticación: sin
  autorización, autenticar no cambia nada.

## 6. Por qué se descartaron los nodos servidor de la paleta

Ver ADR-01 en [arquitectura-red.md §8](arquitectura-red.md) e I-03 en
[INCONVENIENTES.md](../evidencia/INCONVENIENTES.md). Resumen:

| Paquete | Hallazgo | Consecuencia para la Parte 4.9 |
|---|---|---|
| `node-red-contrib-opcua-server` 1.1.1 (Compact-Server) | `checkUserLogon()` devuelve siempre `true`; depende de `vm2` (escape de sandbox, crítico, sin mantenimiento) y de node-opcua 2.64 (2022) | La autenticación sería **decorativa**: cualquier clave entra |
| `node-red-contrib-opcua` (OpcUa-Server) | Usuarios en `users.json` con contraseña en **texto plano** | Quien lea el archivo obtiene todas las claves |

## 7. Modelo de amenazas (STRIDE)

Diagrama de flujo de datos y límites de confianza:

```text
           límite: Wi-Fi (red compartida)                límite: enlace eth0
 ┌──────┐   SSH / túnel   ┌──────────────────────┐   OPC UA 4840   ┌──────────────────────┐
 │  PC  │ ───────────────►│ RPi 1 (servidor)     │◄───────────────►│ RPi 2 (cliente)      │
 │      │   UaExpert 4840 │ Node-RED · pigpiod   │                 │ Node-RED · pigpiod   │
 └──────┘ ───────────────►│ PKI · /etc/*.env     │                 │ PKI · /etc/*.env     │
                          └──────────────────────┘                 └──────────────────────┘
                                 │ GPIO                                     │ GPIO
                            pulsador, LEDs                            pulsador, LEDs
```

| # | Elemento | STRIDE | Amenaza concreta | Control aplicado | Cómo se verifica |
|---|---|---|---|---|---|
| 1 | Endpoint 4840 | **S**poofing | Un equipo en la Wi-Fi se hace pasar por la RPi 2 y escribe `Cliente.*` | Sign/SignAndEncrypt + trust list manual; usuario/clave; `soloAutenticadosEscriben` | Pruebas 11-15; PARTE-4 §7-9 |
| 2 | Mensajes en el enlace | **T**ampering | Modificar el valor de un Write en tránsito | Firma HMAC-SHA256 en Sign y SignAndEncrypt | Vectores Sign: firma de 32 B |
| 3 | Mensajes en el enlace | **I**nformation disclosure | Leer valores y nombres de usuario | SignAndEncrypt; la contraseña siempre va cifrada con RSA-OAEP | `prueba_opcua_tramas.py` §7-8 |
| 4 | Editor de Node-RED (1880) | **E**levation of privilege | Quien accede al editor ejecuta código arbitrario en la placa | `uiHost` 127.0.0.1 + túnel SSH; `adminAuth` con bcrypt | `ss -tlnp` muestra 127.0.0.1:1880 |
| 5 | `pigpiod` (8888) | **E**levation / **T**ampering | Controlar los GPIO sin pasar por OPC UA | `pigpiod -l` (solo loopback) | `ss -tlnp` muestra 127.0.0.1:8888 |
| 6 | Credenciales | **I**nformation disclosure | Robo de contraseñas desde el repositorio o el editor | Hash scrypt; secretos en `/etc/nodered-pdci.env` (600); nada en git (`.gitignore`); el hash se lee con una función, no se guarda en el contexto | Revisión de `git status`; `ls -l /etc/nodered-pdci.env` |
| 7 | Servidor OPC UA | **D**enial of service | Abrir sesiones hasta agotar memoria | `maxSessions = 5`; timeout de sesión de 60 s | — |
| 8 | Escrituras | **R**epudiation | No saber quién escribió | Registro de CreateSession/ActivateSession con origen, modo y usuario (journalctl) | `journalctl -u nodered` |
| 9 | Cadena de suministro | **T**ampering | Dependencia vulnerable o abandonada | Versiones fijas (`node-opcua@2.160.0`), `npm audit`, descarte de vm2 (I-03) | `npm audit --omit=dev` |
| 10 | SSH | **S**poofing | Fuerza bruta de contraseñas | Solo clave pública (Imager); usuario no estándar | `sudo sshd -T \| grep passwordauthentication` |

**Riesgos aceptados (laboratorio académico):** el endpoint None sigue
habilitado porque la consigna lo exige para UaExpert y para la captura; el
acceso anónimo está permitido en las Partes 2 y 3; la Wi-Fi comparte red con
la PC. En una instalación real: deshabilitar None, quitar el anónimo o dejarlo
solo de lectura, y sacar 4840 de la red de oficina (§8).

## 8. Encuadre IEC 62443

| Concepto IEC 62443 | En este trabajo | En una planta real |
|---|---|---|
| **Zona** de control | Las dos RPi y sus E/S | Celda o línea de producción |
| **Conducto** de control | El enlace `eth0` directo, sin otros equipos | Switch gestionado dedicado, VLAN de control |
| Conducto de gestión | `wlan0` (SSH, UaExpert) | No existiría: se accedería desde una DMZ industrial con un *jump server* |
| Nivel de seguridad (SL) | SL 1 (errores casuales) con None; SL 2 (atacante con medios simples) con SignAndEncrypt + autenticación | SL objetivo por análisis de riesgo |
| Prioridad | **Disponibilidad → integridad → confidencialidad**: por eso el cliente reconecta solo y los LED se congelan en el último valor bueno en lugar de apagarse | Igual |

OPC UA aporta los requisitos de componente que IEC 62443-4-2 pide (autenticación
de usuarios y de dispositivos, integridad y confidencialidad de la
comunicación), pero **no reemplaza la segmentación**: un servidor OPC UA con
SignAndEncrypt expuesto a internet sigue siendo una superficie de ataque.

## 9. Referencias

International Electrotechnical Commission. (2016). *OPC Unified Architecture
— Part 2: Security model* (IEC TR 62541-2:2016).

International Electrotechnical Commission. (2020). *OPC Unified Architecture
— Part 4: Services* (IEC 62541-4:2020).

International Electrotechnical Commission. (2020). *OPC Unified Architecture
— Part 7: Profiles* (IEC 62541-7:2020).

International Electrotechnical Commission. (2019). *Security for industrial
automation and control systems — Part 4-2: Technical security requirements
for IACS components* (IEC 62443-4-2:2019).

OWASP Foundation. (2024). *Password storage cheat sheet*. OWASP Cheat Sheet
Series. https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

Shostack, A. (2014). *Threat modeling: Designing for security*. Wiley.
