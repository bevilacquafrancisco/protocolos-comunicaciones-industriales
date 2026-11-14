# 02 · Broker MQTT en la nube

**Objetivo:** un broker en internet (invariante I-03) con TLS y tres credenciales separadas. El
criterio de salida se comprueba con las herramientas del repositorio.

**Dónde:** en casa, con internet. **Tiempo:** ~30 min, incluidos 5 min de espera por la caché de
permisos.

**Decisiones:**

- ADR-005: HiveMQ Cloud Serverless, gratuito.
- [ADR-026](../decisiones-adr.md): qué permisos admite de verdad ese plan.

---

## 1. Lo que admite el plan gratuito

Según la documentación oficial (docs.hivemq.com, "Access Management Options per Cloud Plan",
consultada el 2026-11-14):

| Característica | HiveMQ Cloud Serverless |
|---|---|
| Autenticación | Usuario y contraseña (sin certificados de cliente ni JWT) |
| Permisos | **Uno por credencial**: *Publish Only*, *Subscribe Only* o *Publish and Subscribe* |
| Roles (varios permisos por usuario) | **No**. Son de Starter en adelante, que es pago |
| Cambios de credenciales | Tardan hasta 1 min en aplicarse |
| Cambios de permisos | Tardan **hasta 5 min** en aplicarse (caché) |
| Puertos | MQTT sobre TLS **8883** · WebSocket sobre TLS **8884** |

**Consecuencia (ADR-026).** El mínimo privilegio por tópico del ADR-005 no se puede configurar acá.
La clave de la web puede publicar en todo `spBv1.0/#`. El riesgo residual está medido y acotado:
cada comando lo vuelven a validar el Edge Node y el servidor OPC UA. Si hace falta el mínimo privilegio
completo, ver §6.

## 2. Alta de la cuenta y del broker

1. Entrar a **console.hivemq.cloud** y crear una cuenta (correo y contraseña, o una cuenta de GitHub o
   Google). **[SEC]** Activar la verificación en dos pasos si la consola la ofrece: quien entra a la
   consola puede crear credenciales.
2. Crear un broker del plan **Serverless** (gratuito). La región más cercana suele ser una de EE. UU.
   o de Europa; para el TP da igual.
3. En la pestaña **Overview** del broker, anotar la **URL del broker** (algo como
   `<id>.s1.eu.hivemq.cloud`) y los puertos (8883 y 8884). Si la consola muestra la URL completa del
   WebSocket, anotarla tal cual, ruta incluida.

## 3. Permisos y credenciales

Ir a **Access Management**.

**3.1 Permisos.** En *Authorization → Permissions*, botón **Add New**.

La documentación es ambigua sobre si Serverless admite un **filtro de tópico** propio. Hay que mirar
el formulario:

| Si el formulario tiene el campo *Topic Filter* | Si no lo tiene |
|---|---|
| Crear los tres permisos de la tabla de abajo | Usar los permisos por defecto (`#`): *Publish and Subscribe* para `edge_node` y `host_app`, y *Subscribe Only* para `observador` |

| Nombre del permiso | Tipo | Topic Filter | Para el usuario |
|---|---|---|---|
| `pdci-edge` | Publish and Subscribe | `spBv1.0/UNRaf_PdCI_2026/#` | `edge_node` |
| `pdci-host` | Publish and Subscribe | `spBv1.0/#` | `host_app` (necesita publicar en `spBv1.0/STATE/...`) |
| `pdci-observador` | Subscribe Only | `spBv1.0/#` | `observador` |

El permiso de `edge_node` no cubre `spBv1.0/STATE/...`, así que el Edge Node no conoce el STATE de la
Host Application. Es opcional en Sparkplug 3.0 y el Edge Node sigue funcionando: lo prueba
`test_permisos_broker.py`.

**3.2 Credenciales.** Primero generar tres claves aleatorias, una por usuario, y guardarlas en el
gestor de contraseñas:

```powershell
PS> py -3.11 -c "import secrets; [print(secrets.token_urlsafe(18)) for _ in range(3)]"
```

Después, en *Authentication → Credentials*, botón **Add New**, una vez por fila:

| Username | Permission | Password |
|---|---|---|
| `edge_node` | `pdci-edge` | la primera clave |
| `host_app` | `pdci-host` | la segunda |
| `observador` | `pdci-observador` | la tercera |

**Esperar 5 minutos** antes de verificar: es la caché de permisos (§1).

## 4. Cargar los datos en la notebook

Desde `tarea-3/`:

```powershell
PS> Copy-Item .env.example .env
PS> notepad .env
```

Completar la sección del dispositivo 3 y la del observador:

| Variable | Valor |
|---|---|
| `MQTT_HOST` | la URL del broker (§2), sin `mqtts://` |
| `MQTT_PUERTO_TLS` | `8883` |
| `MQTT_USUARIO_EDGE` / `MQTT_CLAVE_EDGE` | `edge_node` / su clave |
| `MQTT_USUARIO_HOST` / `MQTT_CLAVE_HOST` | `host_app` / su clave (la usa `tools/host_comandos.py`) |
| `MQTT_USUARIO_OBSERVADOR` / `MQTT_CLAVE_OBSERVADOR` | `observador` / su clave |
| `MQTT_CA` | vacío: el certificado del broker lo firma una CA pública |

**[SEC]**

- `.env` está en `.gitignore`. Confirmarlo con `git status`: el archivo **no** debe aparecer.
- No guardar el repositorio en una carpeta sincronizada (OneDrive, Google Drive), porque el `.env` se
  subiría a la nube.

## 5. Verificación

**5.1 TLS de punta a punta** (Git Bash trae `openssl`):

```bash
GB$ openssl s_client -connect <url-del-broker>:8883 -brief < /dev/null
GB$ openssl s_client -connect <url-del-broker>:8884 -brief < /dev/null
```

Esperado en las dos: `Verification: OK` y el protocolo (TLSv1.2 o TLSv1.3). Si falla, ver la tabla.

**5.2 Publicar y recibir por la nube**, con dos terminales en `tarea-3/gateway-sparkplug`:

```powershell
PS> .venv\Scripts\python tools\observador_sparkplug.py          # terminal 1: usuario observador
PS> .venv\Scripts\python tools\host_comandos.py rebirth          # terminal 2: usuario host_app
```

El observador tiene que mostrar una línea `NCMD ... Node Control/Rebirth=True`. Eso prueba TLS, las
dos credenciales y el broker de punta a punta.

**5.3 El observador no puede publicar.** En MQTT Explorer, crear una conexión con `observador` (host,
puerto 8883, *Encryption (tls)* activado) e intentar publicar en `spBv1.0/prueba` desde el panel
*Publish*. El observador de 5.2 **no** debe recibir nada.

**5.4 Desde la red del aula (riesgo R-06).** Repetir 5.1 el día del laboratorio, conectados a la red
donde se va a defender:

- si 8883 u 8884 no responden, usar el punto de acceso del celular;
- si tampoco responden por el celular, revisar la URL del broker.

| Síntoma | Causa probable | Solución |
|---|---|---|
| `connect: Connection timed out` | La red filtra el puerto | Usar el punto de acceso del celular |
| `Verification error` | Se conectó a otro equipo (portal cautivo) o la hora de la notebook está mal | Verificar la hora; salir del portal cautivo |
| `CONNACK ... Not authorized` | Usuario o clave mal copiados, o todavía no pasó 1 min | Volver a copiarlos desde el gestor; esperar |
| El NCMD no llega al observador | Todavía no pasaron 5 min, o el permiso no cubre el tópico | Esperar; revisar el filtro de `pdci-observador` |

## 6. Referencia: mínimo privilegio completo (opción C del ADR-026)

Si el sistema pasara a producción, o el tribunal pidiera mínimo privilegio real, hay dos caminos:

- **HiveMQ Starter** con roles (pago);
- **Mosquitto propio**: se instala en una VM en la nube (gratis en una capa *always free*, o unos USD
  4-6/mes en un VPS básico), con TLS de Let's Encrypt, y con este `acl_file`. Es exactamente el perfil
  `minimo` que reproduce `tools/broker_dev.py --acl minimo`:

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

Con ese perfil, la clave de la web **no** puede publicar un NBIRTH falso. Está medido en
`test_permisos_broker.py`.

---

## Criterio de salida

- [ ] Broker Serverless creado. URL y puertos anotados.
- [ ] Tres credenciales con permisos separados; claves en el gestor y en `tarea-3/.env`, que no
      figura en `git status`.
- [ ] 5.1 en los dos puertos y 5.2 correctos.
- [ ] 5.3: el observador no puede publicar.
