# Correcciones a la versión Python/asyncua — Tarea 2 (OPC UA)

**Para:** Agustina · **Revisó:** Francisco · **Fecha:** 2026-10-15

## Cómo se revisó

Además de leer el código, **se ejecutaron tus programas sin modificarlos** en una
PC, con asyncua 2.1.0, gpiozero 2.0.1 y los GPIO simulados (MockFactory de
gpiozero):

- el servidor `servidor_ns1.py`, consultado con un cliente de prueba;
- los dos clientes, conectados a ese servidor a través de un proxy que
  registró cada mensaje OPC UA (786 mensajes en Modo A y 567 en Modo B),
  decodificados después uno por uno.

Todo el código que se propone en este documento **se probó** contra asyncua
2.1.0 antes de escribirlo. No se probó en las Raspberry Pi.

**La base está bien:** servidor, modelo, los dos modos de lectura y la
reconexión funcionan. Lo verificado:

- `ns=1` para `urn:unraf:pdci:t2`;
- los cuatro NodeIds, con sus tipos (Boolean, UInt16);
- AccessLevel 1 en `Servidor.*` y 3 en `Cliente.*`;
- **EURange** presente, con tipo Range (i=884) y valor 0..65 535;
- el servidor rechaza los tipos incorrectos (`BadTypeMismatch`) sin caerse;
- la suscripción notifica solo cuando el valor cambia.

Lo que sigue es lo que falta o hay que corregir, en orden de prioridad.

---

## Índice

0. [Urgente: la contraseña está escrita en la guía](#0-urgente-la-contraseña-está-escrita-en-la-guía)
1. [Un solo servidor y una sola guía](#1-un-solo-servidor-y-una-sola-guía)
2. [Parámetros de la suscripción](#2-parámetros-de-la-suscripción)
3. [Poder detener la rampa del servidor](#3-poder-detener-la-rampa-del-servidor)
4. [Leer los dos nodos en un solo Read](#4-leer-los-dos-nodos-en-un-solo-read)
5. [StatusCode en la desconexión](#5-statuscode-en-la-desconexión)
6. [Medir la latencia](#6-medir-la-latencia)
7. [Parte 4: certificados, Sign/SignAndEncrypt, usuario y contraseña](#7-parte-4-certificados-signsignandencrypt-usuario-y-contraseña)
8. [Diagramas de flujo y trazabilidad del código](#8-diagramas-de-flujo-y-trazabilidad-del-código)
9. [Preguntas de análisis 1.5 y 2.6](#9-preguntas-de-análisis-15-y-26)
10. [Correcciones menores](#10-correcciones-menores)
11. [Lista de verificación](#11-lista-de-verificación)

---

## 0. Urgente: la contraseña está escrita en la guía

`Puesta_en_marcha_TP_OPC_UA_Raspberry_Pi.docx`, sección 6, dice
*"Nota: contraseña: …"* con la contraseña real de las placas, que además sirve
para SSH y `sudo`.

**Todavía no se filtró** (la carpeta no está en git ni en GitHub). Antes de
subir nada:

1. Borrar esa línea del `.docx`.
2. Cambiar la contraseña en las dos placas: `passwd`.
3. Recomendado: pasar SSH a **clave pública**. En Windows,
   `ssh-keygen -t ed25519`, y luego copiar el contenido de `id_ed25519.pub`
   a `~/.ssh/authorized_keys` en cada placa.

La consigna pide justamente evaluar la seguridad (Parte 4): una contraseña en
el informe es lo primero que miraría la cátedra.

## 1. Un solo servidor y una sola guía

**Problema.** Hay dos servidores, y las guías se contradicen:

| | `puesta_en_marcha.txt` | `Puesta_en_marcha_…docx` |
|---|---|---|
| Servidor que se copia | `servidor.py` (deja el namespace en **ns=2**) | `servidor_ns1.py` (**ns=1**, el correcto) |
| Perfil de red | `"Wired connection 1"` | `netplan-eth0` (el que existe en Debian 13) |

Los clientes buscan `ns=1` fijo. Con `servidor.py`, **nada funciona**: el cliente
recibe `BadNodeIdUnknown`. Si el día de la defensa se copia el archivo
equivocado, la demostración falla.

**Corrección.**

1. Borrar `servidor.py` y renombrar `servidor_ns1.py` → `servidor.py`.
2. Borrar `cliente_suscripcion.py` (la v1) si quedó en alguna placa, y la
   función sin uso `crear_item_monitoreado` de la v2 (ver §10).
3. Mantener **una sola guía**: la `.docx` es la más completa. Borrar el
   `.txt` o actualizarlo.

## 2. Parámetros de la suscripción

**Problema.** [cliente_suscripcion_v2.py:209](cliente_suscripcion_v2.py#L209)
crea la suscripción con `create_subscription(100, manejador)` y nada más. En
la trama capturada, asyncua pide sus valores por defecto:

| Parámetro | Lo que se envía hoy | Consecuencia |
|---|---|---|
| RequestedMaxKeepAliveCount | **4500** | KeepAlive cada 4500 × 100 ms = **450 s (7,5 min)**. En una captura de 60 s con la rampa quieta **no aparece ningún KeepAlive**, y la consigna (3.4) pide explicarlos y observarlos |
| RequestedLifetimeCount | **10 000** | Si el cliente muere, la suscripción sigue viva en el servidor **16 min** |

**Corrección** (probada; el servidor devuelve como revisados KeepAlive 10 y
Lifetime 300):

```python
params = ua.CreateSubscriptionParameters(
    RequestedPublishingInterval=PUBLISHING_INTERVAL_MS,  # 100 ms
    RequestedLifetimeCount=300,       # 300 x 100 ms = 30 s sin Publish -> se borra
    RequestedMaxKeepAliveCount=10,    # 10 x 100 ms = 1 s sin cambios -> KeepAlive
    MaxNotificationsPerPublish=0,     # sin limite
    PublishingEnabled=True,
    Priority=0,
)
subscription = await client.create_subscription(params, manejador)

# Valores REVISADOS por el servidor (los que rigen): asyncua los copia en
# subscription.parameters despues de crearla.
print("Revisados: PublishingInterval =", subscription.parameters.RequestedPublishingInterval,
      "| KeepAlive =", subscription.parameters.RequestedMaxKeepAliveCount,
      "| Lifetime =", subscription.parameters.RequestedLifetimeCount)
```

Justificación de los valores, para el informe:
- KeepAlive de 1 s, porque es lo que se quiere observar en la captura.
- Lifetime de 30 s, que debe ser al menos 3 veces el KeepAlive (IEC 62541-4).
- Un corte de cable de menos de 30 s conserva la suscripción; uno más largo la
  hace expirar. Son las dos ramas que conviene mostrar en la prueba de
  desconexión.

Los valores **revisados** también se ven en Wireshark, en la
`CreateSubscriptionResponse`.

## 3. Poder detener la rampa del servidor

**Problema.** La consigna (3.4) pide repetir la captura del Modo B *"con el
pulsador en reposo y la rampa detenida"* para ver los KeepAlive. Hoy el
servidor siempre genera la rampa.

**Corrección.** Un argumento de línea de comandos, en `servidor.py`:

```python
import argparse

parser = argparse.ArgumentParser(description="Servidor OPC UA - TP2")
parser.add_argument("--rampa-detenida", action="store_true",
                    help="no actualiza Servidor.Rampa (captura de KeepAlive, consigna 3.4)")
ARGS = parser.parse_args()

# ... dentro del while, en lugar de escribir siempre la rampa:
if not ARGS.rampa_detenida:
    await rampa_servidor.write_value(ua.Variant(valor_rampa_local, ua.VariantType.UInt16))
```

Uso: `python servidor.py --rampa-detenida`. Hacer lo mismo en el cliente
(`--sin-escritura`), para que la captura de KeepAlive no tenga Writes
intercalados.

**Verificado:** asyncua solo notifica cuando el valor **cambia**. Aunque el
servidor reescribe `Servidor.EstadoPulsador` cada 50 ms con el mismo valor, el
cliente recibió **una sola** notificación de ese nodo en 13 s. Con la rampa
detenida, solo quedan los KeepAlive.

## 4. Leer los dos nodos en un solo Read

**Problema.** [cliente.py:109-110](cliente.py#L109-L110) hace dos
`read_data_value()` seguidos: son **dos** ReadRequest de un nodo cada uno. En
la medición fueron 263 ReadRequest, todos de 1 nodo. Eso duplica el tráfico de
lectura del Modo A y **sesga la comparación** A frente a B.

Tráfico medido en régimen (PC, 13,4 s):

| | Modo A (hoy) | Modo B (hoy) |
|---|---|---|
| Mensajes por segundo | 57,9 | 40,8 |
| Bytes UA por segundo | 5462 | 3873 |

**Corrección** (probada; devuelve las dos DataValue con su SourceTimestamp):

```python
# Un unico ReadRequest con los dos nodos (2 ReadValueId dentro del mismo pedido)
data_estado, data_rampa = await client.read_attributes([estado_servidor, rampa_servidor])
```

**Ojo con la cuenta de tramas:** el cliente de asyncua lee además
`ServerStatus` **una vez por segundo** para detectar caídas (parámetro
`watchdog_intervall=1.0` de `Client`). Aparece en las dos capturas y hay que
mencionarlo al comparar.

## 5. StatusCode en la desconexión

**Problema.** La consigna (3.6) pide *"registrar el StatusCode informado por el
cliente y el comportamiento de la sesión"*. Hoy solo se imprime el tipo de
excepción (`TimeoutError`).

**Corrección.** Distinguir los dos casos e imprimir la hora:

```python
from datetime import datetime, timezone

def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

async def main():
    while True:
        try:
            await ejecutar_sesion()
        except asyncio.CancelledError:
            raise
        except ua.UaStatusCodeError as exc:
            # El SERVIDOR respondio con un error OPC UA (sesion invalida, etc.)
            print(f"{ahora()} [OPC UA] StatusCode={ua.StatusCode(exc.code).name} (0x{exc.code:08X})")
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            # No hubo respuesta: con el cable desconectado no llega ningun
            # StatusCode, se agota el tiempo de espera (timeout del Client = 4 s).
            print(f"{ahora()} [TRANSPORTE] {type(exc).__name__}: sin respuesta del servidor")
        print(f"{ahora()} Reintentando en {INTERVALO_RECONEXION:.0f} s...")
        await asyncio.sleep(INTERVALO_RECONEXION)
```

Y además:

- En [cliente.py:151](cliente.py#L151), envolver el `disconnect()` del
  `finally` en `try/except`, como ya hace la v2. Con el cable desconectado
  falla y **tapa** la excepción original.
- **Para el informe:** cada reconexión abre una sesión **nueva**; no reactiva la
  anterior. La sesión vieja queda en el servidor hasta su timeout, que el
  servidor revisó a **600 000 ms (10 min)** (asyncua pide 1 h por defecto). Es
  válido, pero hay que explicarlo.
- Probar dos cortes: uno de **menos de 5 s**, en el que probablemente TCP
  retransmite y no se ve ningún error, y uno de **más de 10 s**, que dispara el
  timeout y la reconexión.

## 6. Medir la latencia

La consigna (3.4) pide la latencia entre presionar el pulsador en una placa y
el encendido del LED en la otra. Hoy no se mide.

**Corrección.** Imprimir una línea con la hora en el flanco del pulsador y en
cada cambio del LED, **con este formato exacto**. Así sirve la herramienta del
grupo `tarea-2/herramientas/medir_latencia.py`, que empareja los eventos y
calcula mínimo, media, mediana, percentil 95 y máximo:

```python
# donde se detecta el cambio del pulsador local:
print(f"LATENCIA pulsador_local={'ON' if estado_local else 'OFF'} t={ahora()}")

# donde cambia el LED digital (solo si cambio respecto del valor anterior):
print(f"LATENCIA led_digital={'ON' if estado_remoto else 'OFF'} t={ahora()}")
```

Requisitos:

1. **Relojes sincronizados** entre las placas: `chrony`, con la RPi 1 como
   servidor NTP por `eth0`. Procedimiento en `tarea-2/node-red/README.md` §14.
2. Guardar la salida de cada placa (`python cliente.py | tee cliente.log`) y en
   la PC correr:
   `python medir_latencia.py servidor.log cliente.log`.
3. Medir en Modo A y en Modo B, en los dos sentidos.

**Mejor todavía:** usar los eventos de gpiozero en lugar de sondear el pulsador
(`pulsador.when_pressed = ...`). Hoy se lee cada 50 ms en el servidor y cada
100 ms en el cliente: una pulsación breve se puede perder, y eso suma hasta
100 ms de latencia que no son del protocolo.

## 7. Parte 4: certificados, Sign/SignAndEncrypt, usuario y contraseña

### 7.1 Problema de seguridad actual (importante)

El servidor ya **anuncia** login con usuario y contraseña (tokens `Anonymous`,
`Certificate` y `UserName`), pero **no configura un gestor de usuarios**. Por
defecto asyncua usa `PermissiveUserManager`, que **acepta cualquier usuario con
cualquier contraseña**. Además, como solo existe el endpoint None, el propio
asyncua avisa al arrancar:
*"No encrypting policy available, password may get transferred in plaintext"*.

### 7.2 Generar los certificados (una vez, en cada placa)

asyncua trae el generador. En la RPi 1, `generar_certificados.py`:

```python
import asyncio, socket
from pathlib import Path
from cryptography.x509.oid import ExtendedKeyUsageOID
from asyncua.crypto.cert_gen import setup_self_signed_certificate

async def main():
    Path("pki/own").mkdir(parents=True, exist_ok=True)
    Path("pki/trusted").mkdir(parents=True, exist_ok=True)
    await setup_self_signed_certificate(
        Path("pki/own/servidor_key.pem"), Path("pki/own/servidor_cert.der"),
        "urn:unraf:pdci:t2", socket.gethostname(),
        [ExtendedKeyUsageOID.SERVER_AUTH], {"commonName": "TP2 Servidor"})

asyncio.run(main())
```

En la RPi 2, lo mismo con `cliente_key.pem` / `cliente_cert.der`, la URI
`urn:unraf:pdci:t2:cliente` y `ExtendedKeyUsageOID.CLIENT_AUTH`.

**[SEC]** La carpeta `pki/own/` contiene la **clave privada**: no va al
informe, ni al repositorio, ni por mail.

### 7.3 Servidor: tres endpoints, lista de confianza y usuarios

```python
import hashlib, hmac, os
from pathlib import Path
from asyncua import Server, ua
from asyncua.crypto.permission_rules import User, UserRole
from asyncua.crypto.truststore import TrustStore
from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
from asyncua.server.user_managers import UserManager

# [SEC] Nunca la clave en el codigo: el HASH viene de una variable de entorno
# (se genera con generar_hash.py, ver abajo).
HASH_CLAVE = os.environ.get("OPCUA_CLAVE_HASH", "")

def clave_valida(clave: str) -> bool:
    if "$" not in HASH_CLAVE:
        return False
    sal, h = HASH_CLAVE.split("$")
    calculado = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal), n=2**14, r=8, p=1)
    return hmac.compare_digest(calculado.hex(), h)   # comparacion de tiempo constante

class GestorUsuarios(UserManager):
    def get_user(self, iserver, username=None, password=None, certificate=None):
        if username is None:                                   # sesion anonima
            return User(role=UserRole.Anonymous)
        if username == "operador" and password and clave_valida(password):
            return User(role=UserRole.User, name=username)
        return None                                            # -> BadUserAccessDenied

async def main():
    server = Server(user_manager=GestorUsuarios())             # <- reemplaza al permisivo
    await server.init()
    await server.set_application_uri(NAMESPACE_URI)
    server.set_endpoint(ENDPOINT)

    await server.load_certificate("pki/own/servidor_cert.der")
    await server.load_private_key("pki/own/servidor_key.pem")
    server.set_security_policy([
        ua.SecurityPolicyType.NoSecurity,                      # lo pide la consigna (UaExpert)
        ua.SecurityPolicyType.Basic256Sha256_Sign,
        ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
    ])
    server.set_identity_tokens([ua.AnonymousIdentityToken, ua.UserNameIdentityToken])

    # Lista de confianza: solo los certificados de pki/trusted/ pueden abrir un
    # canal Sign o SignAndEncrypt.
    almacen = TrustStore([Path("pki/trusted")], [])
    await almacen.load()
    server.set_certificate_validator(CertificateValidator(
        CertificateValidatorOptions.TRUSTED_VALIDATION | CertificateValidatorOptions.PEER_CLIENT,
        almacen))
    # ... resto igual (namespace, objetos, variables, bucle)
```

Para generar el hash, en la RPi 1, `generar_hash.py`:

```python
import getpass, hashlib, secrets

clave = getpass.getpass("Clave del usuario OPC UA: ").encode()  # no queda en el historial
sal = secrets.token_bytes(16)
print(sal.hex() + "$" + hashlib.scrypt(clave, salt=sal, n=2**14, r=8, p=1).hex())
```

La salida va a una variable de entorno, por ejemplo al final de
`~/opcua-env/bin/activate`: `export OPCUA_CLAVE_HASH='<salida>'`. Las
**comillas simples** son obligatorias: el hash tiene un `$`, y con comillas
dobles o sin comillas la shell lo interpretaría como una variable.

Dos trampas encontradas al probarlo:

| Síntoma | Causa | Solución |
|---|---|---|
| `ValueError: can't create an empty store` al arrancar | `pki/trusted/` está vacía | Copiar ahí el propio certificado del servidor, o el del cliente, antes de arrancar |
| El cliente es rechazado con **`BadCertificateUriInvalid`** aunque el certificado esté confiado | El cliente se presenta con la URI por defecto de asyncua (`urn:freeopcua:client`), distinta de la del certificado | En el cliente: `client.application_uri = "urn:unraf:pdci:t2:cliente"` |

### 7.4 Cliente: modo de seguridad y usuario

```python
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

client = Client(url=URL_SERVIDOR)
client.application_uri = "urn:unraf:pdci:t2:cliente"           # = URI del certificado
await client.set_security(
    SecurityPolicyBasic256Sha256,
    certificate="pki/own/cliente_cert.der",
    private_key="pki/own/cliente_key.pem",
    server_certificate="pki/servidor_cert.der",                # copiado de la RPi 1
    mode=ua.MessageSecurityMode.SignAndEncrypt,                # o ua.MessageSecurityMode.Sign
)
client.set_user(os.environ["OPCUA_CLIENTE_USUARIO"])           # [SEC] desde el entorno
client.set_password(os.environ["OPCUA_CLIENTE_CLAVE"])
await client.connect()
```

Conviene que el modo (None, Sign o SignAndEncrypt) sea un **argumento** del
programa, para repetir la prueba con los tres sin editar el código.

### 7.5 Lo que se verificó (y lo que hay que mostrar en el banco)

| Prueba | Resultado en la PC |
|---|---|
| Endpoints anunciados | None/None, Sign/Basic256Sha256 y SignAndEncrypt/Basic256Sha256 |
| Cliente cuyo certificado **no** está en `pki/trusted/` | Rechazado: **`BadCertificateUntrusted`** |
| Después de copiar `cliente_cert.der` a `pki/trusted/` en la RPi 1 | Conecta |
| SignAndEncrypt + usuario y clave correctos | Conecta |
| Clave incorrecta | **`BadUserAccessDenied`** |
| Usuario inexistente | **`BadUserAccessDenied`** |

**Procedimiento de confianza para el informe (4.8).**

1. Primer intento: rechazado.
2. Comparar la huella del certificado en las dos placas:
   `openssl x509 -inform DER -in cliente_cert.der -noout -fingerprint -sha256`.
3. Copiar `cliente_cert.der` a `pki/trusted/` de la RPi 1 con `scp`.
4. Reintentar: conecta.

Para Wireshark (4.8) hacen falta tres capturas, una por modo, comparando qué
campos quedan legibles:
- **None:** todo legible.
- **Sign:** todo legible, más 32 bytes de firma al final de cada mensaje.
- **SignAndEncrypt:** solo MessageType, MessageSize, SecureChannelId y TokenId.

También medir la latencia de cada modo.

**Token de identidad (4.9):** en Wireshark, el `ActivateSessionRequest` lleva
un `UserNameIdentityToken`. El nombre de usuario viaja legible y la contraseña
cifrada con RSA-OAEP usando el certificado del servidor. Explicación completa
en `tarea-2/docs/seguridad.md` §5.

## 8. Diagramas de flujo y trazabilidad del código

**Problema.** La consigna (requerimientos adicionales 2 y 3) pide:

- **diagramas de flujo del servidor** (inicialización, creación del espacio de
  direcciones, generación de la rampa, lectura del pulsador, atención de
  escrituras y manejo de LEDs) **y del cliente** (conexión, suscripción, manejo
  de notificaciones, escrituras y reconexión);
- que el código se explique **referenciando el bloque del diagrama** al que
  pertenece.

Las figuras actuales de la guía son de **conexionado**, de **flujo de datos
entre placas** y de **pasos de instalación**: no son diagramas de flujo del
programa.

**Corrección.**

1. Dibujar los dos diagramas con bloques numerados: **S1…S7** para el servidor
   y **C1…C7** para el cliente. Hay un modelo en
   `tarea-2/diagramas/flujo_servidor.md` y `flujo_cliente.md`. Los bloques
   tienen que reflejar **tu** código: por ejemplo, tu servidor lee las escrituras
   del cliente por sondeo en el mismo bucle, no por evento.
2. En el código, marcar cada sección con su bloque:

   ```python
   # ==================================================================
   # BLOQUE S3 · Rampa diente de sierra (consigna 2.3)
   # ==================================================================
   ```

3. **Documentar las funciones de las bibliotecas** con parámetros, tipos y
   retorno. La consigna lo exige textualmente en *Aclaraciones*: *"especificar
   qué parámetros requiere la configuración, qué funciones se emplean y qué
   parámetros (con tipo) requieren, qué y cómo devuelven"*. Ejemplo:

   ```python
   def generar_rampa_triangular(t: float) -> int:
       """
       Rampa triangular 0..65535, periodo 8 s (4 s subida + 4 s bajada).

       Parametros:
           t (float): segundos desde el inicio de la rampa.
       Retorna:
           int: valor en [0, 65535].
       Biblioteca: no usa ninguna.
       """
   ```

   Y en el informe, una tabla con las funciones de asyncua y gpiozero usadas:
   `Server.register_namespace(uri: str) -> int`,
   `Node.add_variable(nodeid, bname, val) -> Node`,
   `Node.write_value(value: Variant | DataValue) -> None`,
   `Client.read_attributes(nodes, attr) -> list[DataValue]`,
   `Client.create_subscription(params, handler) -> Subscription`,
   `Subscription.subscribe_data_change(node, sampling_interval: float, queuesize: int) -> int`,
   `Button(pin: int, pull_up: bool, bounce_time: float)`,
   `PWMLED.value: float [0..1]`.

## 9. Preguntas de análisis 1.5 y 2.6

No están respondidas. Somos el mismo grupo, así que se puede usar el desarrollo
que ya está hecho, adaptándolo a lo que vos implementaste:

| Pregunta | Desarrollo | Qué adaptar a tu versión |
|---|---|---|
| 1.5 — Red Ethernet punto a punto (física, enlace, red, herramientas) | `tarea-2/docs/arquitectura-red.md` §2 | Tus valores reales: 1000 Mb/s full, `netplan-eth0`, Debian 13 |
| 2.6 — Cliente-servidor frente a maestro-esclavo; navegar frente a tabla de registros | `tarea-2/docs/modelo-informacion.md` §7 | Que UaExpert navegó tu servidor sin configuración previa |

Falta también **demostrar** que el OPC UA va por `eth0` con la Wi-Fi activa
(consigna 1.4): `ip route get 192.168.10.1`, `ss -tn | grep 4840` y
`sudo tcpdump -i wlan0 port 4840`, que no debe mostrar paquetes. Ver
`tarea-2/PARTE-1.md` §4.

## 10. Correcciones menores

| # | Dónde | Qué | Corrección |
|---|---|---|---|
| a | [cliente_suscripcion_v2.py:130](cliente_suscripcion_v2.py#L130) | `crear_item_monitoreado()` no se usa y tiene `ClientHandle = 0`: fue el error de la v1 (los dos ítems con el mismo identificador) | Borrarla |
| b | La guía, sección 17, y el comentario de la v2 | Se dice que la v2 corrige el LED **con la "sincronización inicial"**. La causa real era el `ClientHandle` repetido: el servidor **siempre** envía la notificación inicial (verificado: llegó una del pulsador al suscribirse) | Corregir la explicación; la lectura inicial puede quedar, pero no es la solución. En la defensa, dar la causa correcta |
| c | [servidor_ns1.py:184](servidor_ns1.py#L184) | `sleep(0.05)` sin descontar el tiempo de trabajo: el ciclo dura algo más de 50 ms | `await asyncio.sleep(max(0, 0.05 - (time.monotonic() - ahora)))`, como ya hace el cliente |
| d | [servidor_ns1.py:171](servidor_ns1.py#L171) y clientes | La consigna pide escalar a **0-255**; se escala a 0..1 | Calcular `duty = round(valor * 255 / 65535)` y luego `led_pwm.value = duty / 255`, y mostrar el 0-255 en la consola |
| e | [servidor_ns1.py:31](servidor_ns1.py#L31) | El comentario dice "pull-down **externa** de 10 kΩ"; la guía y el código usan la **interna** | Corregir el comentario |
| f | [cliente.py:90](cliente.py#L90) | La rampa del cliente se genera cada 100 ms; la consigna dice "actualizada cada 50 ms" (y escrita cada 100 ms) | Generar a 50 ms y escribir a 100 ms, o justificarlo en el informe |
| g | Consola | Escribir `Servidor.Rampa` devuelve **`BadUserAccessDenied`**, no `BadNotWritable`: asyncua controla primero el UserAccessLevel | Registrarlo así en el informe (2.5) y explicar por qué |
| h | Guías | `pip install asyncua gpiozero` sin versión | Fijar las versiones probadas: `pip install asyncua==X gpiozero==Y lgpio==Z` (las que muestra `pip freeze` en las placas) |
| i | `servidor_ns1.py` | `set_application_uri(NAMESPACE_URI)` usa la misma URI para la **aplicación** y para el **modelo**. Funciona, pero son conceptos distintos | Dejarlo y explicarlo en el informe: es la forma de obtener `ns=1` en asyncua |
| j | Modelo | EURange como propiedad de una variable común; el tipo estándar que la define es `AnalogItemType` | Opcional; si no, justificarlo |

## 11. Lista de verificación

- [ ] §0 Contraseña borrada de la guía y cambiada en las placas.
- [ ] §1 Un solo `servidor.py` (el de ns=1) y una sola guía.
- [ ] §2 Suscripción con KeepAlive 10 y Lifetime 300; valores revisados impresos.
- [ ] §3 `--rampa-detenida` en el servidor y captura de KeepAlive (~1 por segundo).
- [ ] §4 Un solo Read con dos nodos; capturas de 60 s del Modo A y el Modo B; tabla de tramas y bytes.
- [ ] §5 StatusCode y hora en cada evento de desconexión; cortes corto y largo documentados.
- [ ] §6 Líneas `LATENCIA` y medición con chrony en los dos sentidos y los dos modos.
- [ ] §7 Certificados, tres endpoints, confianza documentada, usuario con hash; capturas None/Sign/SignAndEncrypt.
- [ ] §8 Diagramas de flujo S1-S7 y C1-C7, bloques marcados en el código, tabla de funciones de las bibliotecas.
- [ ] §9 Preguntas 1.5 y 2.6; demostración de `eth0` frente a `wlan0`.
- [ ] §10 Correcciones menores.
