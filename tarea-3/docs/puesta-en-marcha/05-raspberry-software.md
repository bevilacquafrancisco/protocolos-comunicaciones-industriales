# 05 · Raspberry Pi: Node-RED, maestro MODBus y servidor OPC UA

**Objetivo:** el dispositivo 2 instalado como servicio systemd (`pdci-t3-nodered`) que arranca solo:

- Node-RED 4.1.16, con las versiones fijadas en `edge-nodered/package-lock.json`;
- el maestro MODBus de stack propio;
- el servidor OPC UA con usuario y lista de confianza;
- el Dashboard de configuración y estadística.

**Dónde:** donde sea, con internet (Wi-Fi). **Tiempo:** ~45 min, la mayor parte en `npm ci`.

**Requisito:** el criterio de salida de 04 (SSH, hora sincronizada, `eth0` configurada).

**Por qué así.** Node-RED se ejecuta **desde `edge-nodered/node_modules`**, no con el instalador global.
Es el mismo modo de arranque que el banco virtual, que es el camino probado (F7). Además, `settings.js`
resuelve `node-opcua` desde su propia carpeta: con Node-RED global y los módulos en `~/.node-red`,
**no arrancaría** (por eso se corrigió `edge-nodered/README.md` §4).

---

## 1. Paquetes base y Node.js

```bash
$ sudo apt install -y nodejs npm git build-essential python3
$ node --version          # tiene que ser >= v18.5 (engines de package.json)
$ npm --version           # >= 7 (lockfile versión 3)
```

| Paquete | Para qué |
|---|---|
| `nodejs`, `npm` | Ejecutar Node-RED |
| `git` | `git get-tar-commit-id` (§2) |
| `build-essential`, `python3` | Solo si `node-red-node-serialport` no trae binario precompilado para esa versión de Node.js: `npm ci` lo compila |

Si `node --version` da menos de v18.5, o el paquete no existe, instalar la versión LTS desde el
repositorio de NodeSource. **[SEC]** Ese comando ejecuta un script descargado: conviene leerlo antes,
como en la T2 §8.

Anotar las versiones de `node` y `npm`: son parte del entorno reproducible del informe.

## 2. Copiar el código (un commit exacto)

En la **notebook**, desde la raíz del repositorio. Los cambios tienen que estar en un commit:
`git archive` solo empaqueta lo commiteado.

```powershell
PS> git status                                        # sin cambios pendientes
PS> git archive --format=tar -o $env:TEMP\pdci-t3.tar HEAD tarea-3
PS> scp $env:TEMP\pdci-t3.tar pdci@rpi-pdci-t3.local:
```

En la **Raspberry**:

```bash
$ git get-tar-commit-id < ~/pdci-t3.tar        # imprime el commit: anotarlo
$ rm -rf ~/pdci-t3 ~/tarea-3
$ tar -xf ~/pdci-t3.tar -C ~ && mv ~/tarea-3 ~/pdci-t3
$ ls ~/pdci-t3                                 # edge-nodered  docs  tools  ...
```

**Por qué `git archive` y no `scp -r` de la carpeta:**

- Viajan solo los archivos versionados. Quedan afuera `node_modules` (de Windows, no sirve en ARM), los
  `.venv`, el `.env` con claves y las PKI.
- El tar lleva grabado el commit, así que siempre se sabe qué versión corre en la placa.
- Borrar `~/pdci-t3` es seguro: no tiene datos. Los datos viven en `~/.pdci-t3` (§4).

*(Alternativa: `git clone` del repositorio en la placa, con un token de **solo lectura** si es
privado, nunca con la contraseña de la cuenta.)*

## 3. Dependencias

```bash
$ cd ~/pdci-t3/edge-nodered
$ npm ci --omit=dev                    # 5-15 min en una RPi 4
$ npm ls node-red node-opcua @flowfuse/node-red-dashboard node-red-node-serialport
$ npm audit --omit=dev                 # anotar el resumen en el informe
```

`npm ls` tiene que mostrar node-red **4.1.16**, node-opcua **2.160.0**, dashboard **1.33.0** y
serialport **2.0.3**. `--omit=dev` deja afuera Jest: en la placa no se corren pruebas.

## 4. Secretos y carpeta de datos

**4.1 Clave del usuario OPC UA.** La elige el equipo: al menos 12 caracteres, guardada en el gestor de
contraseñas. En la Raspberry solo se guarda su **hash**:

```bash
$ node ~/pdci-t3/tools/generar_hash_opcua.js
Contrasena OPC UA:            (no se ve al escribir)
Repetir:
PDCI_T3_OPCUA_HASH=scrypt:131072:8:1:...
```

La clave **en claro** va solo a la notebook: `OPCUA_CLIENTE_CLAVE` en `tarea-3/.env`, en el paso 07.

**4.2 Archivo de entorno.** **[SEC]** Se crea con permisos 600 **antes** de escribir el hash en él:

```bash
$ sudo install -m 600 -o pdci -g pdci /dev/null /etc/pdci-t3-nodered.env
$ cat ~/pdci-t3/edge-nodered/despliegue/pdci-t3-nodered.env.ejemplo > /etc/pdci-t3-nodered.env
$ nano /etc/pdci-t3-nodered.env          # pegar el hash en PDCI_T3_OPCUA_HASH, sin comillas
$ ls -l /etc/pdci-t3-nodered.env          # -rw------- pdci pdci
```

La plantilla fija `PDCI_T3_USERDIR=/home/pdci/.pdci-t3`. Ahí viven los **datos**:

- `flows.json`;
- la PKI OPC UA: certificado del servidor, **clave privada** y lista de confianza;
- la configuración del maestro aplicada desde el Dashboard;
- los contadores.

Están separados del código para que actualizar el código (§7) no cambie el certificado que los
clientes ya confiaron.

**4.3 Flujos.** Se generan **en la placa**, apuntando a esa carpeta:

```bash
$ cd ~/pdci-t3/edge-nodered
$ PDCI_T3_USERDIR=/home/pdci/.pdci-t3 node generar_flujos.js
...
../../.pdci-t3/flows.json: 57 nodos (lo carga Node-RED)
```

## 5. Servicio systemd

```bash
$ command -v node                                  # /usr/bin/node (si no, corregir ExecStart en la unidad)
$ sudo cp ~/pdci-t3/edge-nodered/despliegue/pdci-t3-nodered.service /etc/systemd/system/
$ sudo systemd-analyze verify /etc/systemd/system/pdci-t3-nodered.service   # sin errores
$ sudo systemctl daemon-reload
$ sudo systemctl enable --now pdci-t3-nodered
$ systemctl status pdci-t3-nodered --no-pager      # active (running)
$ journalctl -u pdci-t3-nodered -n 60 --no-pager
```

La unidad ([despliegue/pdci-t3-nodered.service](../../edge-nodered/despliegue/pdci-t3-nodered.service))
hace lo siguiente:

- corre como `pdci` con el grupo `dialout`, que da acceso al adaptador USB;
- lee los secretos de `/etc/pdci-t3-nodered.env`;
- se reinicia sola ante una falla;
- se detiene con SIGINT, para que Node-RED cierre el puerto serie y el servidor OPC UA;
- impide escalar privilegios.

**Qué esperar en el log en este punto** (sin el adaptador RS-485 todavía):

| Línea | Significado |
|---|---|
| `[warn] Projects disabled` | Normal: la función *Projects* de Node-RED está apagada a propósito |
| `[warn] Using unencrypted credentials` | Normal: `credentialSecret: false` en `settings.js`. Los flujos **no** guardan credenciales (los secretos van por `/etc/pdci-t3-nodered.env`), y así no se depende de una clave autogenerada que se perdería al regrabar la microSD |
| `certificado de aplicacion creado: /home/pdci/.pdci-t3/opcua-pki/own/certs/servidor_pdci_t3.pem` | Solo en el primer arranque (F4) |
| `servidor OPC UA en opc.tcp://<ip>:4840 (... endpoint(s) de red)` | El servidor escucha. Puede aparecer unos segundos después de `Started flows`: si no está, volver a mirar el log |
| `serial port /dev/ttyUSB0 error` | **Esperado** hasta conectar el adaptador (06) |
| Con el adaptador ya conectado: `opened` → `closed` → `opened` | **Esperado**: el nodo serie abre el puerto con su configuración inicial, y M1 lo reabre con la configuración guardada del maestro (`serial control`, I-04) |
| `Status.OPCUA.Estado = ERROR` | **Esperado**: todavía no hay datos del esclavo |

```bash
$ sudo ss -tlnp | grep -E ':4840|:1880'
```

Tiene que figurar 4840 en todas las interfaces y **1880 solo en `127.0.0.1`**. **[SEC]** El editor y el
Dashboard no quedan expuestos en la Wi-Fi.

## 6. Firewall: OPC UA solo por el cable

**[SEC]** El servidor OPC UA escucha en todas las interfaces, y eso incluye la Wi-Fi del celular. Se
deja abierto solo por `eth0`, como en la regla de la T2 de que todo el tráfico OPC UA vaya por el
cable. **Primero** se permite SSH: si no, se pierde la sesión. SSH entra por la Wi-Fi y también
por el cable, solo desde la notebook (ADR-029): así el túnel al Dashboard funciona en cualquier red.

```bash
$ sudo apt install -y ufw
$ sudo ufw allow in on wlan0 to any port 22 proto tcp
$ sudo ufw allow in on eth0 from 192.168.10.2 to any port 22 proto tcp   # SSH por el cable (ADR-029)
$ sudo ufw allow in on eth0  to any port 4840 proto tcp
$ sudo ufw default deny incoming
$ sudo ufw enable
$ sudo ufw status verbose
```

## 7. Dashboard por túnel SSH y huella del servidor

En la notebook, en una ventana que queda abierta:

```powershell
PS> ssh -L 1880:127.0.0.1:1880 pdci@rpi-pdci-t3.local
```

- **http://localhost:1880/dashboard**. En *Configuración → Servidor OPC UA · lista de confianza*,
  anotar la **Huella del servidor** (SHA-1): se compara en el paso 07.
- **http://localhost:1880** es el editor de Node-RED. Los flujos **no** se editan ahí: se generan
  (§4.3).

## 8. Actualizar después de un cambio en el código

| Qué cambió | Qué hacer |
|---|---|
| Cualquier archivo de `edge-nodered` | Commit en la notebook → §2 (archivo, copia, extracción) → `sudo systemctl restart pdci-t3-nodered` |
| `package-lock.json` | Además, §3 (`npm ci --omit=dev`) antes de reiniciar |
| `funciones/`, `plantillas/` o `config/` | Además, §4.3 (regenerar los flujos) antes de reiniciar |
| Secretos | Editar `/etc/pdci-t3-nodered.env` y reiniciar |

Un *Deploy* desde el editor **no** recarga `lib/` ni `settings.js`: Node-RED los carga una vez, al
arrancar (lección de la T2). Siempre se reinicia el servicio.

**Opcional.** Con todo funcionando, sacar una imagen de **esta** tarjeta (`rpi-pdci-t3.img`, igual
que en 04 §1.1). Para la próxima sesión alcanza con restaurarla.

---

## Criterio de salida

- [ ] `node --version` ≥ 18,5. Versiones de `node`, `npm` y el commit (§2) anotados.
- [ ] `npm ls` con las cuatro versiones fijadas.
- [ ] `/etc/pdci-t3-nodered.env` con permisos `-rw-------`, con el hash, y **sin** la clave en claro.
- [ ] `pdci-t3-nodered` en *active (running)* y habilitado. El log muestra
      `servidor OPC UA en opc.tcp`.
- [ ] 1880 solo en `127.0.0.1`; `ufw` activo con SSH en `wlan0` y 4840 en `eth0`.
- [ ] Dashboard abierto por el túnel y huella del servidor anotada.
