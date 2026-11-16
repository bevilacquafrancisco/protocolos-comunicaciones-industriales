# 08 · Host Application: la página web

**Objetivo:** la web conectada al broker de la nube por WSS (I-08). Se tiene que ver en la notebook y en
el **celular** (lo exige la consigna) con:

- el semáforo de las cuatro capas (I-05);
- el dispositivo 1 en vivo;
- los comandos confirmados.

**Requisitos:** el criterio de salida de 07 (Edge Node publicando). **Tiempo:** ~15 min.

Detalle: [hmi-web/README.md](../../hmi-web/README.md).

---

## 1. `config.js`

```powershell
PS> cd tarea-3\hmi-web
PS> Copy-Item config.example.js config.js
PS> notepad config.js
```

| Campo | Valor |
|---|---|
| `url` | `wss://<direccion-del-broker>:8084/mqtt` (02 §2) |
| `usuario` / `clave` | `host_app` / su clave |
| `grupo`, `nodo`, `dispositivo`, `hostId` | Los de la plantilla (diccionario §4) |

**[SEC]**

- `config.js` está en `.gitignore`: verificar que **no** aparezca en `git status`.
- Igual lo descarga el navegador, así que la clave de `host_app` es pública de hecho. El comentario de
  `config.example.js` explica por qué esto es una mitigación y no una solución, y el ADR-027 describe los
  permisos por tópico que acotan lo que se puede hacer con ella.

## 2. Servir la página

La página necesita un servidor (no `file://`), porque descarga `proto/sparkplug_b.proto`.
`tools/servir.js` entrega **solo** los archivos de la página, con cabeceras de seguridad:

```powershell
PS> node tools\servir.js --lan
Host Application en http://<IP de esta PC>:8080/
```

Para el **celular**, el firewall de Windows tiene que dejar entrar al puerto 8080. Se agrega una regla
**temporal** (PowerShell como administrador) que se borra en el paso 10:

```powershell
PS> New-NetFirewallRule -DisplayName "PdCI T3 web (temporal)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Any
PS> (Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4).IPAddress     # la IP de la notebook
```

## 3. Verificación en la notebook

Abrir **http://localhost:8080**. En el registro de eventos, que muestra lo más nuevo **arriba**, tienen
que aparecer estas líneas. Se leen de abajo hacia arriba; acá van en orden cronológico:

```
MQTT conectado a <broker> · STATE online (timestamp ...)
Conexión nueva sin BIRTH vigente → NCMD Rebirth solicitado (#1)
STATE online
NBIRTH bdSeq=N seq=0
DBIRTH seq=1: dispositivo EN LÍNEA
```

El NCMD #1 es normal: los BIRTH no se retienen, así que una página nueva pide uno (ADR-024).

| ✓ | Esperado |
|---|---|
| ☐ | Semáforo con las cuatro capas en ✔: MODBUS DONE con sus contadores, OPC UA DONE, MQTT CONECTADO, SPARKPLUG NODO EN LÍNEA |
| ☐ | Pulsador y potenciómetro cambian en vivo; la antigüedad dice "hace 0 s" |
| ☐ | Conmutador del LED: **ENVIADO** → **CONFIRMADO**. El LED físico enciende. El conmutador cambia **solo** cuando vuelve el DDATA |
| ☐ | Deslizador PWM (al soltarlo): CONFIRMADO, y el brillo del LED cambia |
| ☐ | El registro dice `Comando Outputs/LedDigital = true CONFIRMADO (NNN ms)`. **Anotar NNN**: es la latencia del comando medida en el banco real, con la nube incluida (09 §6) |

Si la tarjeta MQTT dice **CREDENCIALES RECHAZADAS**, revisar `usuario` y `clave`. Si queda en
CONECTANDO, revisar la URL y la ruta del WebSocket (02 §5.1, puerto 8084).

## 4. Verificación en el celular

El celular hace de punto de acceso, y la notebook está conectada a él. En el navegador del celular,
abrir `http://<IP de la notebook>:8080`.

| ✓ | Esperado |
|---|---|
| ☐ | Una sola columna, **sin desplazamiento horizontal**, todo legible sin zoom |
| ☐ | El mismo estado que en la notebook. Los dos navegadores son Host Applications |
| ☐ | El conmutador del LED responde con el dedo, y la notebook también ve el comando |

Algunos puntos de acceso aíslan a los clientes entre sí. Si el celular no llega a la notebook, probar
con otro celular conectado al mismo punto de acceso, o mostrar la vista de celular de la notebook
(herramientas de desarrollador del navegador, 390 px). La prueba de interfaz de F6 cubre ese caso.

---

## Criterio de salida

- [ ] La web en la notebook muestra las cuatro capas en ✔ y el dispositivo EN LÍNEA, y acciona el LED con
      confirmación.
- [ ] La latencia del comando (`CONFIRMADO (NNN ms)`) anotada.
- [ ] La web en el celular, legible y operable.
- [ ] `config.js` sin aparecer en `git status`.
