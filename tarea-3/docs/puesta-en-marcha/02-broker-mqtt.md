# 02 · Broker MQTT en la nube

**Objetivo:** un broker en internet (invariante I-03) con TLS, tres credenciales separadas y
**permisos por tópico** (mínimo privilegio). El criterio de salida se comprueba con las herramientas
del repositorio.

**Dónde:** en casa, con internet. **Tiempo:** ~30 min.

**Decisiones:**

- [ADR-027](../decisiones-adr.md): EMQX Cloud Serverless, gratuito. Reemplaza a HiveMQ Cloud
  Serverless (ADR-005), que dejó de venderse el 2026-09-30 y se apaga el 2026-12-31.
- ADR-005: los tres usuarios y su tabla de permisos, que con EMQX **sí** se pueden configurar.

---

## 1. Lo que da el plan gratuito

Según la consola de EMQX al crear el broker (2026-11-16) y la documentación oficial
(docs.emqx.com, "Serverless Connection Guide" y "Default Authorization"):

| Característica | EMQX Cloud Serverless |
|---|---|
| Cuota gratuita mensual | 1 millón de minutos de sesión · **1 GB de tráfico** · 1 millón de acciones de reglas |
| Límite de gasto (*Spend Limit*) | **USD 0,00**: si se agota la cuota, el broker se detiene; **no cobra** |
| Capacidad | Hasta 1000 sesiones y 1000 mensajes/s |
| Puertos | **Solo con TLS**: MQTT **8883** · WebSocket **8084** (1883 y 8083 no existen en este plan) |
| Autenticación | Usuario y contraseña. **No admite anónimos.** Exige SNI en el saludo TLS |
| Autorización | Reglas por usuario: tópico, acción (publicar, suscribirse o ambas) y permiso (permitir o denegar) |
| Fijo al crearlo (\*) | Proyecto, plan, región, versión (v5) y puertos |

**¿Alcanza la cuota?** Es una estimación hecha con el tráfico medido en el banco virtual
(`mediciones.md` §2, régimen):

| Cliente | B/s |
|---|---|
| Edge Node | 590 |
| Web en la notebook y en el celular | 2 × 196 |
| Observador (recibe lo mismo que una web) | ≈ 196 |
| **Total** | **≈ 1180 B/s ≈ 4,2 MB/h** |

- **Tráfico.** 1 GB alcanza para unas **230 h de régimen por mes**, de sobra para el banco y la
  defensa. Pero **no** para dejar la cadena encendida las 24 h durante un mes, que serían unos 3 GB.
- **Sesiones.** Cuatro clientes durante una hora gastan 240 minutos de sesión: el millón no es el
  límite.

**Consecuencia:** al terminar cada sesión de trabajo, se detienen el Edge Node y el observador (10 §1).

## 2. Alta de la cuenta y del broker

1. Entrar a la consola de EMQX Cloud y crear una cuenta. **[SEC]** Activar la verificación en dos
   pasos si la consola la ofrece: quien entra a la consola puede crear credenciales y cambiar permisos.
2. Crear un **proyecto** (por ejemplo `TP-PdCI`) y, dentro, un *deployment* con:

   | Campo | Valor | Por qué |
   |---|---|---|
   | Plan | **Serverless** | Gratuito |
   | Region | La que ofrezca, por ejemplo North America | Fija para siempre. La latencia de la nube se mide en el banco (09 §6) y se informa con la región |
   | Tier | 1,000 Sessions / 1,000 TPS | El único |
   | EMQX Version | v5 | |
   | **Spend Limit** | **USD 0,00** | Que nunca cobre: al agotar la cuota se detiene |

3. En el **Overview** del deployment, anotar:
   - la **dirección del broker** (*Address*, algo como `<id>.ala.<región>.emqxsl.com`);
   - los puertos **8883** (MQTT sobre TLS) y **8084** (WebSocket sobre TLS);
   - si la consola ofrece descargar el **certificado de la CA**, bajarlo a
     `tarea-3/gateway-sparkplug/pki/emqx-ca.crt`. Esa carpeta ya está en `.gitignore`. Solo se usa si
     5.1 falla (§4, `MQTT_CA`).

**[SEC]** El certificado de la CA es público y no es un secreto. Lo que **no** se guarda en el repositorio es la
dirección del broker junto con las claves: las dos van al `.env`.

## 3. Credenciales y permisos

Ir a **Access Control** del deployment.

### 3.1 Credenciales (*Authentication*)

Primero generar tres claves aleatorias, una por usuario, y guardarlas en el gestor de contraseñas:

```powershell
PS> py -3.11 -c "import secrets; [print(secrets.token_urlsafe(18)) for _ in range(3)]"
```

Después, en *Authentication*, botón **Add**, una vez por fila:

| Username | Password | Lo usa |
|---|---|---|
| `edge_node` | la primera clave | Edge Node (dispositivo 3) |
| `host_app` | la segunda | La web y `tools/host_comandos.py`. **Es pública de hecho**: va en el navegador |
| `observador` | la tercera | `tools/observador_sparkplug.py` y MQTT Explorer |

### 3.2 Permisos (*Authorization*)

EMQX evalúa primero las reglas **por usuario** (pestaña *Username*) y después las de **todos los
usuarios** (pestaña *All Users*). Gana la **primera** regla que coincide.

Sin reglas, EMQX **permite todo** (modo lista negra): cualquier usuario podría publicar un NBIRTH
falso. Por eso el orden es:

**1. Lista blanca.** En la pestaña *All Users*, una sola regla:

| Topic | Action | Permission |
|---|---|---|
| `#` | Publish & Subscribe | **Deny** |

Desde ahí, lo que no está permitido explícitamente queda prohibido. En el plan Serverless este cambio
de modo no se hace con un botón: se hace con esa regla (documentación de EMQX).

**2. Permisos por usuario.** En la pestaña *Username*, estas reglas, todas con **Allow**. Es la tabla del ADR-005
y el mismo perfil `minimo` que reproduce `tools/broker_dev.py --acl minimo` y que prueba
`test_permisos_broker.py`:

| Username | Topic | Action |
|---|---|---|
| `edge_node` | `spBv1.0/UNRaf_PdCI_2026/+/EN01_Gateway` | Publish |
| `edge_node` | `spBv1.0/UNRaf_PdCI_2026/+/EN01_Gateway/#` | Publish |
| `edge_node` | `spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway` | Subscribe |
| `edge_node` | `spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/#` | Subscribe |
| `edge_node` | `spBv1.0/STATE/#` | Subscribe |
| `host_app` | `spBv1.0/STATE/HA01_WebDashboard` | Publish & Subscribe |
| `host_app` | `spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway` | Publish |
| `host_app` | `spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/#` | Publish |
| `host_app` | `spBv1.0/UNRaf_PdCI_2026/#` | Subscribe |
| `observador` | `spBv1.0/#` | Subscribe |

Qué impide cada fila, para la defensa:

- `edge_node` publica solo tópicos de **su** nodo (`N*` y `D*` de `EN01_Gateway`), y se suscribe
  solo a sus comandos y al STATE.
- `host_app` **no** puede publicar NBIRTH, NDATA ni DDATA: con su clave, que es pública, no se puede
  hacer pasar por el Edge Node. Solo publica su STATE y los comandos.
- `observador` no puede publicar nada.

Si la consola no deja elegir *Publish & Subscribe* en una regla, se cargan dos reglas para ese tópico,
una de cada tipo.

EMQX guarda en caché, por conexión, el resultado de cada autorización. **Después de cambiar una
regla hay que reconectar** el cliente afectado.

## 4. Cargar los datos en la notebook

Desde `tarea-3/`:

```powershell
PS> Copy-Item .env.example .env
PS> notepad .env
```

Completar la sección del dispositivo 3, la del observador y la de la web:

| Variable | Valor |
|---|---|
| `MQTT_HOST` | la dirección del broker (§2), sin `mqtts://` |
| `MQTT_PUERTO_TLS` | `8883` |
| `MQTT_PUERTO_WSS` | `8084` |
| `MQTT_USUARIO_EDGE` / `MQTT_CLAVE_EDGE` | `edge_node` / su clave |
| `MQTT_USUARIO_HOST` / `MQTT_CLAVE_HOST` | `host_app` / su clave (la usa `tools/host_comandos.py`) |
| `MQTT_USUARIO_OBSERVADOR` / `MQTT_CLAVE_OBSERVADOR` | `observador` / su clave |
| `MQTT_CA` | **vacío**: el certificado del broker lo firma una CA pública, y Python usa las del sistema. Solo si 5.2 da `CERTIFICATE_VERIFY_FAILED`: la ruta absoluta de `emqx-ca.crt` (§2) |

**[SEC]**

- `.env` está en `.gitignore`. Confirmarlo con `git status`: el archivo **no** debe aparecer.
- No guardar el repositorio en una carpeta sincronizada (OneDrive, Google Drive), porque el `.env` se
  subiría a la nube.

## 5. Verificación

**5.1 TLS de punta a punta.** Git Bash trae `openssl`. `-servername` envía el SNI, que EMQX exige:

```bash
GB$ openssl s_client -connect <direccion-del-broker>:8883 -servername <direccion-del-broker> -brief < /dev/null
GB$ openssl s_client -connect <direccion-del-broker>:8084 -servername <direccion-del-broker> -brief < /dev/null
```

Esperado en las dos: `Verification: OK` y el protocolo (TLSv1.2 o TLSv1.3). Si falla, ver la tabla.

**5.2 Publicar y recibir por la nube**, con dos terminales en `tarea-3/gateway-sparkplug`:

```powershell
PS> .venv\Scripts\python tools\observador_sparkplug.py          # terminal 1: usuario observador
PS> .venv\Scripts\python tools\host_comandos.py rebirth          # terminal 2: usuario host_app
```

El observador tiene que mostrar una línea `NCMD ... Node Control/Rebirth=True`. Eso prueba TLS, las
dos credenciales y los permisos de `host_app` para NCMD y de `observador` para `spBv1.0/#`.

**5.3 El mínimo privilegio funciona.** Con el observador de 5.2 todavía abierto, se usa MQTT Explorer:

- *Encryption (tls)* activado;
- puerto 8883;
- en *Advanced*, borrar las suscripciones por defecto (`#` y `$SYS/#`) y dejar solo `spBv1.0/#`.

| Conexión | Acción en el panel *Publish* | Esperado |
|---|---|---|
| `observador` | Publicar en `spBv1.0/prueba` | El observador de 5.2 **no** recibe nada |
| `host_app` | Publicar `00` en `spBv1.0/UNRaf_PdCI_2026/NBIRTH/EN01_Gateway` | El observador **no** recibe nada: con la clave de la web no se puede imitar al Edge Node |
| `edge_node` | — (solo conectar, suscripto a `spBv1.0/#`) | El árbol de tópicos queda **vacío**: `edge_node` no puede leer más que sus comandos |

Si alguna de las tres pasa, falta la regla *Deny* de *All Users* (§3.2, paso 1), o no se reconectó el
cliente después de cargarla.

**5.4 Desde la red del aula (riesgo R-06).** Repetir 5.1 el día del laboratorio, conectados a la red
donde se va a defender:

- si 8883 u 8084 no responden, usar el punto de acceso del celular;
- si tampoco responden por el celular, revisar la dirección del broker y que el deployment esté en
  marcha (§5.5).

**5.5 El día anterior al banco.** Entrar a la consola y confirmar que el deployment está **en
marcha**, y cuánto queda de la cuota del mes. Según una fuente no oficial, un deployment Serverless
sin conexiones durante 30 días se detiene. Si está detenido, iniciarlo desde la consola.

| Síntoma | Causa probable | Solución |
|---|---|---|
| `connect: Connection timed out` | La red filtra el puerto | Usar el punto de acceso del celular |
| `Verification error` | Se conectó a otro equipo (portal cautivo), o la hora de la notebook está mal | Verificar la hora; salir del portal cautivo |
| La conexión se corta en el saludo TLS | Falta el SNI (en `openssl`, `-servername`) | Agregarlo. paho, mqtt.js y MQTT Explorer lo envían solos |
| `CERTIFICATE_VERIFY_FAILED` en Python y `openssl` da OK | El almacén de Windows no tiene esa raíz instalada | `MQTT_CA` = ruta de `emqx-ca.crt` (§2) |
| `CONNACK ... Not authorized` o `Bad user name or password` | Usuario o clave mal copiados | Volver a copiarlos desde el gestor |
| `SUBACK rechazado para NCMD/DCMD` en el Edge Node | Falta una regla de `edge_node`, o hay un error de tipeo en el tópico | Comparar con la tabla de §3.2 y reconectar |
| El NCMD de 5.2 no llega al observador | Falta la regla de `host_app` para NCMD o la de `observador` | Ídem |

## 6. Referencia: el mismo perfil en un broker propio

Si el sistema pasara a producción, o el broker tuviera que ser propio, el perfil de §3.2 se escribe
igual en un `acl_file` de Mosquitto. Mosquitto se puede instalar en una VM en la nube: gratis en una
capa *always free*, o unos USD 4-6/mes en un VPS básico, con TLS de Let's Encrypt (ADR-027, opción B):

```text
# /etc/mosquitto/acl  (password_file y acl_file en mosquitto.conf; allow_anonymous false)
user edge_node
topic write spBv1.0/UNRaf_PdCI_2026/+/EN01_Gateway
topic write spBv1.0/UNRaf_PdCI_2026/+/EN01_Gateway/#
topic read  spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway
topic read  spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/#
topic read  spBv1.0/STATE/#

user host_app
topic write spBv1.0/STATE/HA01_WebDashboard
topic write spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway
topic write spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/#
topic read  spBv1.0/UNRaf_PdCI_2026/#
topic read  spBv1.0/STATE/HA01_WebDashboard

user observador
topic read  spBv1.0/#
```

Mosquitto deniega todo lo que no figura en el archivo, así que **no** hace falta la regla *Deny*
global que EMQX sí necesita.

---

## Criterio de salida

- [ ] Deployment Serverless creado con *Spend Limit* en USD 0. Dirección y puertos anotados.
- [ ] Tres credenciales. Las claves están en el gestor y en `tarea-3/.env`, que no figura en
      `git status`.
- [ ] La regla *Deny* `#` en *All Users* y las diez reglas de §3.2 cargadas.
- [ ] 5.1 en los dos puertos, y 5.2 correcto.
- [ ] 5.3: las tres pruebas de mínimo privilegio dan "no recibe nada" o el árbol vacío.
