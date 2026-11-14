# Seguridad del servidor OPC UA (dispositivo 2)

> Implementa ADR-009 con node-opcua 2.160.0 (ADR-011, ADR-019). Código:
> `edge-nodered/lib/servidor_opcua.js` (bloques DF-5.1, DF-5.2 y DF-5.7 de
> [flujo-servidor-opcua.mmd](diagramas/flujo-servidor-opcua.mmd)) y `lib/credenciales.js`.
> **Todo lo medido es en la PC** (Node-RED + simulador del esclavo, loopback). En el banco con la
> Raspberry Pi queda **pendiente**.

## 1. Endpoints y política de identidad

| Endpoint | SecurityPolicy | MessageSecurityMode | Qué protege |
|---|---|---|---|
| 1 | `None` | `None` | Nada: integridad y confidencialidad nulas. Se mantiene para diagnóstico y para el GetEndpoints |
| 2 | `Basic256Sha256` | `Sign` | Integridad y autenticación del canal (firma RSA-SHA256 + HMAC-SHA256) |
| 3 | `Basic256Sha256` | `SignAndEncrypt` | Integridad + confidencialidad (AES-256-CBC) |

`Basic256Sha256` es la política mínima vigente: `Basic128Rsa15` y `Basic256` están deprecadas por
usar SHA-1 (OPC UA Part 7, perfiles de seguridad; OPC 10000-2 §6).

| Identidad | Cómo se valida | Rol | Puede |
|---|---|---|---|
| Anónimo | — | `Anonymous` | Browse + Read + suscripciones |
| Usuario y contraseña | hash **scrypt** (N = 2¹⁷, r = 8, p = 1, sal de 16 B), comparación en tiempo constante | `AuthenticatedUser` | además, **Write** sobre `Outputs/*` |

- La contraseña **nunca** se guarda: solo el hash, en la variable de entorno
  `PDCI_T3_OPCUA_HASH` de la placa. Se genera con `node tools/generar_hash_opcua.js`, que la
  pide sin eco y exige al menos 12 caracteres.
- El servidor publica la `UserTokenPolicy` de usuario con `Basic256Sha256` **también en el
  endpoint None**: el cliente cifra la contraseña con la clave pública del servidor. Esto se
  verificó en la captura del §6, donde la contraseña no aparece en ninguno de los tres modos.
- Un usuario o una clave incorrecta da `BadUserAccessDenied` y suma `usuariosRechazados` en el
  panel de las cuatro capas. El log registra el usuario, nunca la clave.

## 2. Certificado X.509 de aplicación

### 2.1 Generación automática (camino por defecto)

En el primer arranque, `iniciarServidor()` crea la PKI en `PDCI_T3_OPCUA_PKI` (por defecto
`<userDir>/opcua-pki`, **fuera del repositorio** y cubierta por el `.gitignore`):

```
opcua-pki/
├── own/certs/servidor_pdci_t3.pem     certificado de aplicación (público)
├── own/private/private_key.pem        clave privada RSA 2048 — no sale de la placa
├── trusted/certs/                     certificados de clientes en los que se confía
├── rejected/                          clientes desconocidos (esperan decisión)
└── issuers/                           CAs, si se usaran (no es el caso: autofirmados)
```

| Campo | Valor | Por qué |
|---|---|---|
| Sujeto | `CN=PdCI-T3 Dispositivo 2, O=UNRaf, OU=PdCI T3, L=Rafaela, ST=Santa Fe, C=AR` | Sin él, node-opcua usa su sujeto de ejemplo (`C=FR, L=Orleans, O=Sterfive`) y trunca el CN a 64 caracteres (observado en la PC) |
| `subjectAltName` URI | `urn:<hostname>:unraf:pdci:t3:servidor` | Debe coincidir con la `ApplicationUri` del servidor (OPC 10000-4 §5.5.2): un cliente estricto rechaza la diferencia |
| `subjectAltName` DNS / IP | hostname e IPv4 de la placa | El cliente verifica que el host del endpoint figure en el certificado |
| Clave | RSA 2048, firma `sha256WithRSAEncryption` | Mínimo que exige `Basic256Sha256` |
| Validez | **730 días** | NIST SP 800-57 Parte 1 (tabla 1) sugiere 1 a 3 años para claves privadas de firma, y 2 años cubren la cursada y la defensa. node-opcua usa 10 años por defecto |

Si el archivo ya existe, se reutiliza: regenerarlo cambia la huella y obliga a reconfiar en
todos los clientes. Para renovarlo, se borra `own/certs/servidor_pdci_t3.pem` y se reinicia
Node-RED.

### 2.2 Generación manual con OpenSSL (alternativa)

Sirve si se quiere el certificado antes del primer arranque, o firmado por una CA propia.

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 730 -nodes \
  -keyout private_key.pem -out servidor_pdci_t3.pem \
  -subj "/CN=PdCI-T3 Dispositivo 2/O=UNRaf/OU=PdCI T3/L=Rafaela/ST=Santa Fe/C=AR" \
  -addext "subjectAltName=URI:urn:$(hostname):unraf:pdci:t3:servidor,DNS:$(hostname),IP:192.168.10.1" \
  -addext "keyUsage=critical,digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment" \
  -addext "extendedKeyUsage=serverAuth,clientAuth"
# copiar a <pki>/own/certs/ y <pki>/own/private/ ; chmod 600 private_key.pem
```

La IP `192.168.10.1` es la de `eth0` en la topología de la T2. Hay que ajustarla a la del banco.

## 3. La confianza es mutua

En `Sign` y `SignAndEncrypt`, el `OpenSecureChannel` intercambia los dos certificados, y **cada
lado** valida el del otro contra su propia lista:

| Dirección | Quién decide | Si no confía |
|---|---|---|
| Cliente → servidor | Lista de confianza del **servidor** (`opcua-pki/trusted/`) | `BadSecurityChecksFailed`; el certificado del cliente queda en `rejected/` |
| Servidor → cliente | Lista de confianza del **cliente** (UaExpert, dispositivo 3) | El cliente corta antes de enviar el `OpenSecureChannel` |

**No hay aceptación automática** (`automaticallyAcceptUnknownCertificate: false`). Aceptar
cualquier certificado reduciría `Sign` y `SignAndEncrypt` a cifrar con un desconocido: un
atacante en la red podría presentarse como cliente (STRIDE: *Spoofing*; IEC 62443-3-3 SR 1.2).

## 4. Cómo se agrega un cliente a la lista de confianza

**Paso 0 — comparar huellas.** Antes de confiar se compara la huella SHA-1 del certificado
rechazado con la que muestra el cliente por un canal **distinto** de la red: la pantalla de
UaExpert o la consola del dispositivo 3. Es lo único que distingue al cliente legítimo de un
impostor con el mismo nombre.

1. El cliente intenta conectar en `Sign` o `SignAndEncrypt`. El servidor lo rechaza y guarda el
   certificado en `rejected/`.
2. Se confía en él por **uno** de estos dos caminos:

| Camino | Pasos | Aplica | Verificado en la PC |
|---|---|---|---|
| **A. Panel (en vivo)** | Dashboard → *Configuración* → *Servidor OPC UA · lista de confianza* → **Confiar** en la fila del cliente. Pide confirmar la huella | Inmediatamente, sin reiniciar | Sí, desde la UI real ([captura](capturas/panel-lista-confianza.png)); prueba `confiar en vivo por huella` |
| **B. Archivo + reinicio** | `mv <pki>/rejected/<cliente>.pem <pki>/trusted/certs/` y `sudo systemctl restart nodered` | Tras el reinicio | Sí (el `Sign` se aceptó después del reinicio) |

⚠ **Mover el archivo sin reiniciar NO alcanza.** El gestor de certificados de node-opcua indexa
las carpetas al arrancar y mantiene el estado en memoria: con el archivo ya en `trusted/` el
servidor siguió rechazando durante 15 s (medido). La prueba `mover el archivo a trusted/ con el
servidor corriendo NO alcanza` fija ese comportamiento: si una versión futura de node-opcua lo
cambia, la prueba avisa.

3. Del lado del cliente se confía en el servidor:
   - **UaExpert:** al conectar muestra el certificado del servidor. Se compara la huella con la
     del panel (*Huella del servidor*) y se elige **Trust Server Certificate**.
   - **Dispositivo 3** (F5): se copia `own/certs/servidor_pdci_t3.pem` a la carpeta de confianza
     del cliente asyncua.
   - **`tools/verificar_opcua.js`:** lee el certificado del `GetEndpoints` e imprime la huella para
     compararla.

**Revocar.** El botón **Revocar** del panel mueve el certificado a `rejected/`, y la sesión
segura siguiente se rechaza (prueba `revocar`). El certificado propio del servidor no aparece en
el panel, para que no se lo pueda revocar por error.

## 5. Autorización por nodo

| Situación | StatusCode | Medido |
|---|---|---|
| Write sobre `Inputs/*` o `Status/*` (AccessLevel sin `CurrentWrite`) | `BadNotWritable` | ✅ |
| Write anónimo sobre `Outputs/*` | `BadUserAccessDenied` | ✅ |
| Write con tipo incorrecto | `BadTypeMismatch` | ✅ (prueba) |
| Write fuera de EURange (`LedPWM` = 300) | `BadOutOfRange`, sin tocar el bus | ✅ |
| Write de usuario, esclavo no responde | `BadCommunicationError`; el valor **no cambia** | ✅ (prueba) |
| Write de usuario, esclavo confirma con el eco FC 05/06 | `Good`, en 20-62 ms | ✅ |

Tabla completa por nodo: [opcua-espacio-direcciones.md](opcua-espacio-direcciones.md).

## 6. Comparación de los modos de seguridad (capturas)

Las capturas son `capturas/opcua-{None,Sign,SignAndEncrypt}.pcapng`, tomadas con `dumpcap` sobre
el loopback de la PC (`\Device\NPF_Loopback`, filtro `tcp port 4840`). Cada una es una sesión
completa de `tools/verificar_opcua.js` con usuario: HEL → OPN → CreateSession → ActivateSession
→ Browse/Read/Write → CloseSession → CLO.

| Modo | Conexiones TCP | Mensajes OPC UA (HEL / OPN / MSG / CLO) | Bytes del archivo | NodeIds legibles | Usuario legible | Contraseña legible |
|---|---|---|---|---|---|---|
| None | 1 | 1 / 2 / 100 / 1 | 53 032 | Sí | Sí | **No** (cifrada por la UserTokenPolicy) |
| Sign | 3 (2 GetEndpoints en None + 1 segura) | 3 / 6 / 108 / 3 | 128 584 | Sí | Sí | **No** |
| SignAndEncrypt | 3 (2 GetEndpoints en None + 1 segura) | 3 / 6 / 108 / 3 | 129 332 | **No** | **No** | **No** |

La columna "legible" se midió buscando el texto (`Outputs.LedPWM`, el nombre de usuario, la
contraseña) en los bytes del archivo. Contados con `tshark -d tcp.port==4840,opcua -Y opcua`.
Las dos conexiones extra de los modos seguros son el `GetEndpoints` en `None` que hace el cliente
antes de abrir el canal seguro. Una la hace el verificador, para mostrar la huella, y la otra
node-opcua. Ninguna lleva datos del proceso.

**Lectura para la defensa.** `Sign` impide modificar la trama, pero cualquiera en la red ve qué
variables se leen y escriben. Solo `SignAndEncrypt` oculta el contenido. El dispositivo 3 debe
usar `SignAndEncrypt` con usuario, que es lo que fija ADR-009.

## 7. STRIDE resumido del servidor

| Amenaza | Control | Residual |
|---|---|---|
| **S**poofing de cliente | Lista de confianza sin autoaceptación; usuario con hash scrypt | Cualquiera puede conectar **anónimo en None** y leer (decisión de ADR-009 para diagnóstico) |
| **T**ampering en tránsito | `Sign` / `SignAndEncrypt` | El endpoint `None` existe: un cliente mal configurado puede usarlo |
| **R**epudiation | Log de CreateSession, ActivateSession y de cada Write (usuario, valor, StatusCode) en el historial | El historial es en memoria (200 eventos) |
| **I**nformation disclosure | `SignAndEncrypt`; la clave privada queda en la placa; la PKI no se versiona | El anónimo lee todo el espacio |
| **D**enial of service | `maxSessions: 6`; un Write pendiente por variable en el maestro | Sin límite de tasa por cliente |
| **E**levation of privilege | Roles: solo `AuthenticatedUser` escribe; AccessLevel por nodo | Un solo usuario con escritura (sin roles finos) |

## 8. Pendiente (banco)

- [ ] Instalar node-opcua 2.160.0 en la Raspberry Pi del laboratorio (R-03).
- [ ] Conectar **UaExpert** a los tres endpoints, recorrer el espacio y escribir un nodo de solo
      lectura. Hay que hacerlo **a mano**: es una aplicación gráfica y no puede automatizarse desde acá.
      `tools/verificar_opcua.js` ejecuta la misma verificación de forma reproducible.
- [ ] Repetir las capturas del §6 en `eth0` de la placa, entre el dispositivo 2 y el dispositivo 3.
