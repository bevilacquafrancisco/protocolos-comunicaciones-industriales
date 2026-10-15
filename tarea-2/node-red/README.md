# Puesta a punto de las Raspberry Pi — desde la microSD vacía

**Tarea N.º 2 · Protocolos de Comunicaciones Industriales · UNRaf**
**Autores:** Bevilacqua Francisco, Peralta Agustina

Esta guía lleva cada Raspberry Pi desde una microSD vacía hasta Node-RED
ejecutando el servidor (RPi 1) o el cliente (RPi 2) OPC UA. Cumple el mismo
papel que [tarea-1/firmware/README.md](../../tarea-1/firmware/README.md) en la
Tarea 1: el procedimiento completo y reproducible, con el porqué de cada
decisión.

Todo se hace **dos veces**, una por placa. Donde los pasos difieren, la guía lo
indica con una tabla **RPi 1 · servidor / RPi 2 · cliente**.

> ⚠️ **Antes de conectar periféricos:** los GPIO de la Raspberry Pi trabajan a
> **3,3 V y no toleran 5 V**. Conectar 5 V a un GPIO lo daña de forma
> permanente. Cablear siempre **con la placa apagada** (§10).

---

## Índice

1. [Qué queda funcionando al final](#1-qué-queda-funcionando-al-final)
2. [Materiales](#2-materiales)
3. [Preparar la PC](#3-preparar-la-pc)
4. [Grabar las microSD](#4-grabar-las-microsd)
5. [Primer arranque y acceso por SSH](#5-primer-arranque-y-acceso-por-ssh)
6. [Actualizar el sistema e instalar los paquetes base](#6-actualizar-el-sistema-e-instalar-los-paquetes-base)
7. [Red Ethernet punto a punto](#7-red-ethernet-punto-a-punto)
8. [Instalar Node-RED](#8-instalar-node-red)
9. [Copiar los archivos del trabajo a cada placa](#9-copiar-los-archivos-del-trabajo-a-cada-placa)
10. [Secretos y configuración de Node-RED](#10-secretos-y-configuración-de-node-red)
11. [Conexionado de los periféricos](#11-conexionado-de-los-periféricos)
12. [Importar el flujo y desplegar](#12-importar-el-flujo-y-desplegar)
13. [Verificación de la puesta en marcha](#13-verificación-de-la-puesta-en-marcha)
14. [Sincronización de relojes (para medir latencia)](#14-sincronización-de-relojes-para-medir-latencia)
15. [Actualizar después de un cambio](#15-actualizar-después-de-un-cambio)
16. [Problemas frecuentes](#16-problemas-frecuentes)
17. [Probar el sistema sin las placas](#17-probar-el-sistema-sin-las-placas)

---

## 1. Qué queda funcionando al final

| | RPi 1 · servidor | RPi 2 · cliente |
|---|---|---|
| Nombre de host | `rpi-servidor` | `rpi-cliente` |
| Usuario | `pdci` | `pdci` |
| `eth0` (enlace directo) | 192.168.10.1/24 | 192.168.10.2/24 |
| `wlan0` (internet, SSH, UaExpert) | DHCP del router o del teléfono | DHCP del router o del teléfono |
| Servicios | `nodered`, `pigpiod`, `chronyd` | `nodered`, `pigpiod`, `chronyd` |
| Flujo de Node-RED | `servidor/flows.json` | `cliente/flows.json` |
| Puerto OPC UA | escucha en 4840 | se conecta a 192.168.10.1:4840 |
| Editor de Node-RED | `127.0.0.1:1880`, por túnel SSH | `127.0.0.1:1880`, por túnel SSH |

Tiempo estimado: ~1 h 30 min por placa la primera vez, la mayor parte esperando
descargas e instalaciones.

## 2. Materiales

| Cantidad | Elemento | Observación |
|---|---|---|
| 2 | Raspberry Pi 3B+ o 4 | Con una **RPi 5** ver §16: `pigpiod` no la soporta |
| 2 | microSD de **16 GB o más**, clase **A1** | A1 garantiza un mínimo de IOPS aleatorias. El sistema hace muchas escrituras chicas y las tarjetas sin clasificar lo vuelven lento |
| 2 | Fuente oficial: **5,1 V / 3 A USB-C** (RPi 4) o **5,1 V / 2,5 A micro-USB** (RPi 3B+) | Un cargador de teléfono suele caer por debajo de 4,75 V bajo carga; la placa lo informa como *undervoltage* y puede corromper la microSD |
| 1 | Cable Ethernet categoría 5e o superior | **Directo o cruzado, da igual**: ambas placas tienen auto MDI-X (explicado en [PARTE-1.md](../PARTE-1.md)) |
| 1 | Lector de microSD para la PC | |
| 2 + 4 | Pulsadores + LED (2 por placa: digital y PWM) | |
| 4 | Resistencias de **330 Ω** | Una por LED (cálculo en §11) |
| — | Protoboard y cables dupont hembra-macho | |
| — | Red Wi-Fi **WPA2 personal** (router doméstico o **punto de acceso del teléfono**) | La Wi-Fi de la facultad suele usar portal cautivo o WPA2-Enterprise, que no se configuran desde el grabador. El punto de acceso del teléfono es la opción más simple para el banco |

## 3. Preparar la PC

Todo es software libre y gratuito.

| Programa | Para qué | De dónde |
|---|---|---|
| **Raspberry Pi Imager** | Grabar el sistema operativo en la microSD | raspberrypi.com/software |
| Cliente SSH (`ssh`, `scp`) | Entrar a las placas y copiar archivos | Ya viene en Windows 10/11 (PowerShell) |
| WinSCP *(opcional)* | Copiar archivos con interfaz gráfica | winscp.net |
| **Wireshark** | Analizar las capturas (Parte 4) | wireshark.org |
| **UaExpert** | Cliente OPC UA genérico (Parte 2.5) | unified-automation.com (requiere registro gratuito) |
| Node.js 18 o superior *(opcional)* | Regenerar los flujos y correr las pruebas en la PC | nodejs.org |

### 3.1 Crear la clave SSH de la PC (una sola vez)

La clave reemplaza a la contraseña para entrar por SSH: no se puede adivinar
por fuerza bruta y no viaja por la red.

```powershell
ssh-keygen -t ed25519 -C "pdci-t2"
```

Aceptar la ruta por defecto (`C:\Users\<usuario>\.ssh\id_ed25519`) y poner una
frase de paso. La clave **pública** queda en `id_ed25519.pub`; es la que se
copia a las placas en el paso siguiente. La privada (`id_ed25519`, sin
extensión) **no sale de la PC**.

## 4. Grabar las microSD

Repetir para cada tarjeta.

1. Insertar la microSD en la PC y abrir **Raspberry Pi Imager**.
2. **Dispositivo:** el modelo de Raspberry Pi.
3. **Sistema operativo:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite
   (64-bit)** basado en **Bookworm** (Debian 12). Si Bookworm figura como
   *Legacy*, elegir esa.
   - **Lite** (sin escritorio): todo se maneja por SSH y el editor de Node-RED se
     abre en el navegador de la PC. Sin escritorio quedan libres unos 200-300 MB
     de RAM y CPU para Node-RED, y hay menos software expuesto.
   - **Bookworm** y no una versión más nueva: `pigpiod`, el demonio que maneja
     el PWM por DMA (decisión en [docs/arquitectura-red.md](../docs/arquitectura-red.md)),
     está en los repositorios de Bookworm. En §6 se verifica antes de seguir.
4. **Almacenamiento:** la microSD. ⚠️ Revisar dos veces que no sea un disco de
   la PC: se borra entero.
5. Cuando pregunte por la **personalización del sistema**, elegir *Editar
   ajustes* (Imager 1.8/1.9) o completar el paso *Personalización* (Imager 2.x):

   | Ajuste | RPi 1 · servidor | RPi 2 · cliente |
   |---|---|---|
   | Nombre de host | `rpi-servidor` | `rpi-cliente` |
   | Usuario / contraseña | `pdci` / una contraseña robusta | `pdci` / otra contraseña robusta |
   | Wi-Fi: SSID y clave | los de la red de §2 | los mismos |
   | **País de la Wi-Fi** | `AR` | `AR` |
   | Zona horaria | `America/Argentina/Cordoba` | ídem |
   | Teclado | `latam` (o `es`) | ídem |
   | **SSH** | habilitado, **solo con clave pública**: pegar el contenido de `id_ed25519.pub` | ídem |

   - **El país de la Wi-Fi no es decorativo:** fija el dominio regulatorio de
     radio. Sin él, la Wi-Fi arranca bloqueada (*rfkill*) y la placa nunca se
     conecta.
   - **Usuario `pdci` y no `pi`:** desde abril de 2022 Raspberry Pi OS no trae
     usuario por defecto, justamente porque `pi`/`raspberry` era la primera
     credencial que probaban los barridos automáticos.
   - **Nombres distintos en cada placa:** con el mismo nombre, `.local` (mDNS)
     resolvería a cualquiera de las dos.
6. Grabar y esperar la verificación. Al terminar, Imager expulsa la tarjeta.

## 5. Primer arranque y acceso por SSH

1. Insertar la microSD en la placa, conectar la fuente y esperar **2 a 3
   minutos**. En el primer arranque el sistema expande la partición a toda la
   tarjeta y se reinicia una vez. El LED verde parpadea mientras lee la
   tarjeta.
2. Desde PowerShell en la PC (conectada a la misma Wi-Fi):

   ```powershell
   ssh pdci@rpi-servidor.local      # o rpi-cliente.local
   ```

   La primera vez pregunta si se confía en la huella del equipo: responder
   `yes`.
3. Si `.local` no resuelve, buscar la IP de la placa en la lista de
   dispositivos del router o del teléfono, y usar `ssh pdci@<ip>`.

> Desde acá, los comandos que empiezan con `$` se ejecutan **en la Raspberry Pi**
> (por SSH) y los que empiezan con `PS>`, **en la PC**.

## 6. Actualizar el sistema e instalar los paquetes base

En **cada** placa:

```bash
$ cat /proc/device-tree/model; echo        # confirmar el modelo
$ sudo apt update && sudo apt full-upgrade -y
$ sudo reboot
```

Reconectar por SSH y verificar que `pigpio` exista en el repositorio **antes**
de seguir:

```bash
$ apt policy pigpio
```

Si informa un *Candidate:* con número de versión, continuar. Si dice
`Unable to locate package`, la imagen no es Bookworm: volver a §4.

```bash
$ sudo apt install -y pigpio tcpdump ethtool chrony git
```

| Paquete | Para qué | Parte de la consigna |
|---|---|---|
| `pigpio` | Demonio `pigpiod`: GPIO y PWM por hardware (DMA) | 2.4, 3.3 |
| `tcpdump` | Capturar el tráfico de `eth0` | 4.1 |
| `ethtool` | Ver la velocidad y el dúplex negociados | 1.3 |
| `chrony` | Sincronizar los relojes entre placas (§14) | 3.4 (latencia) |
| `git` | Opción C de §9 | — |

Activar `pigpiod` y comprobar **en qué dirección escucha**:

```bash
$ sudo systemctl enable --now pigpiod
$ sudo ss -tlnp | grep 8888
```

Tiene que figurar `127.0.0.1:8888`. **[SEC]** `pigpiod` no tiene
autenticación: cualquiera que alcance su puerto puede leer y escribir todos los
GPIO. Si figura `0.0.0.0:8888` o `*:8888`, restringirlo a loopback:

```bash
$ sudo systemctl edit pigpiod
```

En el editor que se abre, entre las líneas de comentario, escribir:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/pigpiod -l
```

Guardar (Ctrl+O, Enter, Ctrl+X), luego `sudo systemctl restart pigpiod` y
repetir el `ss`. (La línea `ExecStart=` vacía borra la orden original antes de
definir la nueva; sin ella, systemd rechaza dos `ExecStart` en un servicio
simple.)

## 7. Red Ethernet punto a punto

Esta sección deja configurada la red; la verificación capa por capa y la
explicación teórica (pregunta 5 de la Parte 1) están en
[PARTE-1.md](../PARTE-1.md).

Conectar el cable Ethernet entre las dos placas. Raspberry Pi OS Bookworm
administra la red con **NetworkManager**, que trae un perfil
`Wired connection 1` que pide IP por DHCP. En un enlace directo no hay servidor
DHCP, así que ese perfil se reemplaza por uno estático:

```bash
$ nmcli con show                                   # ver perfiles existentes
$ sudo nmcli con delete "Wired connection 1"       # si existe
```

| | RPi 1 · servidor | RPi 2 · cliente |
|---|---|---|
| Dirección | `192.168.10.1/24` | `192.168.10.2/24` |

```bash
$ sudo nmcli con add type ethernet ifname eth0 con-name pdci-eth0 \
      ipv4.method manual ipv4.addresses 192.168.10.1/24 \
      ipv4.never-default yes ipv6.method disabled connection.autoconnect yes
$ sudo nmcli con up pdci-eth0
```

(En la RPi 2, `192.168.10.2/24`.)

- `ipv4.never-default yes`: el perfil **no** instala ruta por defecto. La
  salida a internet sigue por `wlan0`, y por `eth0` solo pasa lo que va a
  192.168.10.0/24, que es exactamente el requisito 1.4 de la consigna.
- Sin puerta de enlace: los dos equipos están en el mismo prefijo /24 y se
  alcanzan directamente.

Prueba rápida desde la RPi 2: `ping -c 3 192.168.10.1`.

## 8. Instalar Node-RED

Con el instalador oficial, que instala Node.js LTS y Node-RED como servicio
`systemd`:

```bash
$ bash <(curl -sL https://github.com/node-red/linux-installers/releases/latest/download/update-nodejs-and-nodered-deb)
```

**[SEC]** Este comando ejecuta un script descargado. Es el método documentado
por el proyecto Node-RED; quien prefiera revisarlo antes puede descargarlo con
`curl -sLo instalar.sh <misma URL>`, leerlo y después ejecutar
`bash instalar.sh`.

Respuestas a las preguntas del instalador:

| Pregunta | Respuesta | Por qué |
|---|---|---|
| *Are you really sure you want to do this?* | `y` | |
| *Would you like to install the Pi-specific nodes?* | `n` | Instala `rpi-gpio`, que usa PWM por software. Se usa `pi-gpiod` (§9.3) |
| *Customise settings now?* | `n` | El `settings.js` se ajusta en §10.3 |

Habilitar el arranque automático y comprobar el servicio:

```bash
$ sudo systemctl enable nodered
$ sudo systemctl start nodered
$ systemctl status nodered --no-pager      # debe decir active (running)
$ node --version; node-red --version 2>/dev/null | head -1
```

Anotar ambas versiones en [evidencia/INCONVENIENTES.md](../evidencia/INCONVENIENTES.md)
o en el informe: son parte del entorno reproducible.

## 9. Copiar los archivos del trabajo a cada placa

### 9.1 Qué se copia y adónde

Las **dos placas reciben la misma carpeta** `tarea-2/node-red` completa, en
`/home/pdci/pdci-t2`. Es el mismo criterio que la Tarea 1 con `config.py`: una
sola copia de la configuración compartida, sin variantes por placa. Lo que
distingue a cada placa es **qué flujo se importa** (§12):

| Archivo en el repositorio | RPi 1 · servidor | RPi 2 · cliente |
|---|---|---|
| `comun/config.js` — única fuente de verdad | se usa | se usa |
| `comun/senales.js` — rampas, escala PWM | se usa | se usa |
| `comun/credenciales.js` — hash de la clave | se usa (y genera el hash) | no se usa |
| `servidor/servidor_opcua.js` | se usa | se carga, no se usa |
| `cliente/cliente_opcua.js` | se carga, no se usa | se usa |
| `settings.pdci-t2.js` | se usa | se usa |
| `servidor/flows.json` | **se importa** | — |
| `cliente/flows.json` | — | **se importa** |

Los `flows.json` no hace falta copiarlos a la placa: se importan desde el
navegador de la PC (§12).

### 9.2 Copiar la carpeta

**Opción A — `scp` desde PowerShell** (recomendada; viene con Windows). Desde
la raíz del repositorio en la PC:

```powershell
PS> scp -r .\tarea-2\node-red pdci@rpi-servidor.local:/home/pdci/pdci-t2
PS> scp -r .\tarea-2\node-red pdci@rpi-cliente.local:/home/pdci/pdci-t2
```

⚠️ **Trampa de `scp -r`:** si `/home/pdci/pdci-t2` **ya existe**, `scp` copia
la carpeta **adentro** (`pdci-t2/node-red/...`) en lugar de reemplazar el
contenido. Para actualizar, borrar primero la copia vieja (no contiene secretos
ni certificados: esos viven en `/etc/nodered-pdci.env` y en
`~/.node-red/opcua-pki`):

```powershell
PS> ssh pdci@rpi-servidor.local "rm -r /home/pdci/pdci-t2"
PS> scp -r .\tarea-2\node-red pdci@rpi-servidor.local:/home/pdci/pdci-t2
```

**Opción B — WinSCP** (interfaz gráfica): protocolo SFTP, host
`rpi-servidor.local`, usuario `pdci`, y en *Avanzado → SSH → Autenticación*
la clave privada (WinSCP la convierte a `.ppk`). Arrastrar la carpeta
`tarea-2/node-red` a `/home/pdci/` y renombrarla `pdci-t2`. Para actualizar,
*Comandos → Sincronizar* con dirección *Remoto*.

**Opción C — `git`** (si el repositorio está en GitHub):

```bash
$ git clone <url-del-repositorio> ~/repo-pdci
$ ln -s ~/repo-pdci/tarea-2/node-red ~/pdci-t2
```

Para actualizar alcanza con `cd ~/repo-pdci && git pull`. Si el repositorio es
privado, usar un *token* de acceso personal de **solo lectura**, nunca la
contraseña de la cuenta.

Verificar en la placa:

```bash
$ ls ~/pdci-t2
cliente  comun  generar_flujos.js  README.md  servidor  settings.pdci-t2.js ...
$ node -e "console.log(require('/home/pdci/pdci-t2/comun/config.js').VERSION)"
1
```

### 9.3 Instalar las dependencias en `~/.node-red`

En **cada** placa, con versiones fijas (las mismas con las que se probó en la
PC: un `npm install` sin versión podría traer una incompatible el día de la
defensa):

```bash
$ cd ~/.node-red
$ npm install --omit=dev node-opcua@2.160.0 node-red-node-pi-gpiod@0.5.1
$ npm audit --omit=dev
```

`node-opcua` tarda entre 3 y 10 minutos en una RPi 3B+/4. Anotar en el informe
el resumen de `npm audit`.

**No** instalar `node-red-contrib-opcua` ni `node-red-contrib-opcua-server`: se
evaluaron y se descartaron por razones de seguridad
([docs/seguridad.md](../docs/seguridad.md), ADR-01 en
[docs/arquitectura-red.md](../docs/arquitectura-red.md)).

## 10. Secretos y configuración de Node-RED

### 10.1 Generar los secretos

| Secreto | Cómo se genera | Dónde va |
|---|---|---|
| Hash de la clave del **editor** de Node-RED | `node-red admin hash-pw` (pide la clave, imprime `$2b$...`) | ambas placas |
| Clave de cifrado de credenciales | `openssl rand -hex 32` | ambas placas |
| Hash de la clave del **usuario OPC UA** | `node ~/pdci-t2/comun/credenciales.js` (pide la clave, mínimo 12 caracteres, imprime `scrypt$...`) | solo RPi 1 |
| Clave del usuario OPC UA **en claro** | la misma que se ingresó en el paso anterior | solo RPi 2 |

Las claves se piden por teclado y no se escriben en la línea de comandos, para
que no queden en el historial de la shell (`~/.bash_history`).

### 10.2 Guardarlos en el archivo de entorno

Crear el archivo **con permisos 600** (solo lectura y escritura para `pdci`)
**antes** de escribir nada en él:

```bash
$ sudo install -m 600 -o pdci -g pdci /dev/null /etc/nodered-pdci.env
$ nano /etc/nodered-pdci.env
```

Completar según la plantilla [.env.ejemplo](.env.ejemplo): las líneas de "ambas
placas" más las de la placa correspondiente. **Sin comillas**, y los `$` de los
hashes se escriben tal cual.

Indicarle a systemd que cargue ese archivo en el servicio:

```bash
$ sudo systemctl edit nodered
```

y escribir, entre los comentarios:

```ini
[Service]
EnvironmentFile=/etc/nodered-pdci.env
```

### 10.3 Agregar la configuración del trabajo a `settings.js`

```bash
$ nano ~/.node-red/settings.js
```

1. **Primera línea** del archivo:

   ```js
   const pdci = require('/home/pdci/pdci-t2/settings.pdci-t2.js');
   ```

2. Ir al **final** del archivo. La última llave de cierre `}` es la de
   `module.exports = { ... }`. **Justo antes** de ella, agregar:

   ```js
       ...pdci.ajustes,
   ```

   (Si la línea anterior no termina en coma, agregársela.)

Va al final y no al principio porque el `settings.js` original ya trae
`functionGlobalContext: {}` y `functionExternalModules: true` activos. En un
objeto de JavaScript gana la última clave repetida, así que de esta forma los
valores del trabajo reemplazan a esos sin editar nada más.

Qué agrega [settings.pdci-t2.js](settings.pdci-t2.js):

| Ajuste | Valor | Por qué |
|---|---|---|
| `uiHost` | `127.0.0.1` | **[SEC]** El editor no queda expuesto en la Wi-Fi. Se accede por túnel SSH (§12) |
| `adminAuth` | usuario y hash del entorno | **[SEC]** Quien entra al editor puede ejecutar código arbitrario en la placa |
| `credentialSecret` | del entorno | Cifra `flows_cred.json` |
| `functionGlobalContext` | `config`, `senales`, `opcua`, módulos servidor/cliente | Las function nodes usan una sola implementación, la misma que se prueba en la PC |
| `functionExternalModules` | `false` | Las function nodes no pueden instalar módulos por su cuenta |

### 10.4 Reiniciar y revisar el registro

```bash
$ sudo systemctl restart nodered
$ journalctl -u nodered -n 40 --no-pager
```

**No** tienen que aparecer líneas `[pdci-t2] ATENCION`. Si aparecen:

| Mensaje | Causa | Solución |
|---|---|---|
| `editor sin adminAuth` | Faltan `NODE_RED_ADMIN_USER`/`HASH` o systemd no carga el archivo | Revisar §10.2; `sudo systemctl cat nodered` debe mostrar `EnvironmentFile=` |
| `... no parece un hash bcrypt` / `OPCUA_CLAVE_HASH mal formado` | El hash se copió incompleto o entre comillas | Volver a pegarlo, sin comillas |
| `Cannot find module 'node-opcua'` | No se hizo §9.3 en `~/.node-red` | `cd ~/.node-red && npm install ...` |
| `Cannot find module '/home/pdci/pdci-t2/...'` | La carpeta quedó en otra ruta (trampa de `scp -r`, §9.2) | `ls ~/pdci-t2`; recopiar |

## 11. Conexionado de los periféricos

**Con la placa apagada** (`sudo poweroff`, esperar a que el LED verde deje de
parpadear y desconectar la fuente). El conexionado es **idéntico en ambas
placas**: los pines salen de `comun/config.js`.

| Señal | GPIO (BCM) | Pin físico | Conexión |
|---|---|---|---|
| Pulsador | GPIO17 | 11 | Un terminal al pin 11 y el otro a **GND** (pin 9). Sin resistencia externa: se usa el *pull-up* interno |
| LED digital | GPIO27 | 13 | Pin 13 → resistencia 330 Ω → ánodo del LED (pata larga); cátodo a **GND** (pin 14) |
| LED PWM | GPIO18 | 12 | Pin 12 → resistencia 330 Ω → ánodo; cátodo a **GND** (pin 6) |

**Cálculo de la resistencia del LED:** con un LED rojo (V<sub>F</sub> ≈ 2,0 V),
I = (3,3 V − 2,0 V) / 330 Ω ≈ **3,9 mA**. Queda muy por debajo del límite
recomendado de **16 mA por pin**, y entre los dos LED suman menos de 8 mA de los
~50 mA totales que admite el banco de GPIO de 3,3 V. Un LED azul o blanco
(V<sub>F</sub> ≈ 3,0 V) daría ~0,9 mA: se ve tenue, pero funciona.

**Por qué el pulsador va a GND con *pull-up* y no a 3,3 V con *pull-down*:**
un cable de pulsador suelto o cortado deja el pin en "no presionado" (nivel
alto por el *pull-up*), es decir, en estado seguro. Además, el pin nunca recibe
una tensión externa que pudiera ser la equivocada.

El diagrama de red completo, con interfaces, direcciones y periféricos, está en
[diagramas/red.md](../diagramas/red.md).

## 12. Importar el flujo y desplegar

### 12.1 Abrir el editor por túnel SSH

El editor escucha solo en `127.0.0.1` de la placa. Desde PowerShell se abre un
túnel que lleva el puerto 1880 de la PC al 1880 de la placa:

```powershell
PS> ssh -L 1880:localhost:1880 pdci@rpi-servidor.local
```

Dejar esa ventana abierta y entrar con el navegador de la PC a
**http://localhost:1880**. Iniciar sesión con el usuario y la clave del editor
(§10.1). Para la otra placa se usa otro puerto local y así se pueden tener las
dos abiertas a la vez:

```powershell
PS> ssh -L 1881:localhost:1880 pdci@rpi-cliente.local     # -> http://localhost:1881
```

### 12.2 Importar

1. Menú **≡** → **Importar**.
2. **Seleccionar un archivo para importar** →

   | RPi 1 · servidor | RPi 2 · cliente |
   |---|---|
   | `tarea-2/node-red/servidor/flows.json` | `tarea-2/node-red/cliente/flows.json` |

   (desde el repositorio en la PC).
3. Elegir **Importar a: flujo nuevo**. Si el editor avisa que hay nodos
   repetidos de una importación anterior, elegir **Reemplazar**.
4. Borrar la pestaña *Flow 1* vacía que crea Node-RED la primera vez.
5. Botón **Desplegar** (*Deploy*).

Los `flows.json` **no se editan en el editor**: se generan desde `config.js` y
desde los archivos `*/funciones/*.js` con `generar_flujos.js` (§15). Un cambio
hecho a mano en el editor se pierde en la próxima importación.

## 13. Verificación de la puesta en marcha

Con ambas placas encendidas y el cable Ethernet conectado:

| # | Verificación | Dónde | Resultado esperado |
|---|---|---|---|
| 1 | `systemctl is-active nodered pigpiod` | ambas | `active` `active` |
| 2 | Estado del nodo **S1/C0 · Verificar configuración** | editor | punto verde, `config v1` |
| 3 | Estado de los nodos **GPIO** | editor | punto verde (conectados a `pigpiod`) |
| 4 | Estado de **S2 · Servidor OPC UA** | editor RPi 1 | verde, `escuchando :4840` |
| 5 | Estado de **C1 · Cliente OPC UA** | editor RPi 2 | verde, `Modo B None/None` |
| 6 | `journalctl -u nodered -f` | RPi 1 | una línea por segundo `SERVIDOR generada=… recibida(Cliente.Rampa)=…` con el valor cambiando |
| 7 | `journalctl -u nodered -f` | RPi 2 | `CLIENTE generada=… recibida(Servidor.Rampa)=… antiguedad=… modo=B` |
| 8 | Presionar el pulsador de la RPi 1 | — | se enciende el LED digital de la **RPi 2** |
| 9 | Presionar el pulsador de la RPi 2 | — | se enciende el LED digital de la **RPi 1** |
| 10 | Mirar los LED PWM | — | la RPi 2 sube y cae de golpe cada 4 s (diente de sierra de la RPi 1); la RPi 1 sube y baja suave en 8 s (triangular de la RPi 2) |
| 11 | `sudo ss -tnp \| grep 4840` | RPi 2 | conexión `192.168.10.2:xxxxx → 192.168.10.1:4840`: el tráfico va por `eth0` |

La verificación 10 es la que propone la consigna (Parte 3.2): como las formas de
onda son distintas, se ve a simple vista que cada LED PWM refleja la rampa **de
la otra placa**.

Si las once dan lo esperado, la puesta a punto está terminada. Las mediciones
de cada parte siguen en [PARTE-1.md](../PARTE-1.md) a
[PARTE-4.md](../PARTE-4.md).

## 14. Sincronización de relojes (para medir latencia)

Para medir la latencia entre placas comparando marcas de tiempo (Parte 3.4),
los dos relojes tienen que coincidir mejor que la latencia que se mide. Con NTP
por internet el error típico es de algunos milisegundos; sincronizando la RPi 2
contra la RPi 1 por el enlace directo baja a decenas de microsegundos, porque
el retardo del enlace es mínimo y simétrico.

**RPi 1 · servidor** — servidor NTP del enlace:

```bash
$ echo -e "allow 192.168.10.0/24\nlocal stratum 8" | sudo tee /etc/chrony/conf.d/pdci-t2.conf
$ sudo systemctl restart chrony
```

**RPi 2 · cliente** — toma la hora de la RPi 1 con preferencia:

```bash
$ echo "server 192.168.10.1 iburst prefer" | sudo tee /etc/chrony/conf.d/pdci-t2.conf
$ sudo systemctl restart chrony
$ chronyc sources -v          # 192.168.10.1 debe figurar con '*'
$ chronyc tracking            # "System time": desvio actual
```

Anotar el valor de `System time` junto a cada medición de latencia: es la cota
de error de la marca de tiempo.

## 15. Actualizar después de un cambio

| Qué cambió | Qué hacer |
|---|---|
| `comun/config.js`, `comun/senales.js`, `servidor_opcua.js`, `cliente_opcua.js` o `settings.pdci-t2.js` | 1) En la PC: `node tarea-2/node-red/generar_flujos.js` (si cambió `config.js`). 2) Recopiar la carpeta (§9.2) **en las dos placas**. 3) `sudo systemctl restart nodered`. 4) Si se regeneraron los flujos, reimportarlos (§12.2) |
| Un archivo `*/funciones/*.js` | 1) En la PC: `node tarea-2/node-red/generar_flujos.js`. 2) Reimportar el `flows.json` de esa placa y desplegar. No hace falta reiniciar |
| Modo de lectura A/B o modo de seguridad del cliente | Son claves de `config.js`: primera fila |
| Secretos | Editar `/etc/nodered-pdci.env` y `sudo systemctl restart nodered` |

**Un *Deploy* no recarga los módulos de `functionGlobalContext`:** Node-RED los
carga una sola vez, al arrancar. Por eso los cambios de la primera fila
requieren reiniciar el servicio. Es el error más fácil de cometer: se
modifica `config.js`, se despliega y "no cambia nada".

Antes de copiar a las placas, correr en la PC las pruebas (README de la
tarea, §Verificación): un error de sintaxis en un módulo compartido deja a las
dos placas sin arrancar.

## 16. Problemas frecuentes

| Síntoma | Causa probable | Verificación / solución |
|---|---|---|
| La placa no aparece en la Wi-Fi | País de Wi-Fi no configurado, red WPA2-Enterprise o portal cautivo, o una RPi 3B (sin "+", solo 2,4 GHz) frente a una red de 5 GHz | Regrabar con país `AR` y una red WPA2 personal; con una RPi 3B, que el punto de acceso emita en 2,4 GHz (§4) |
| `ssh: Could not resolve hostname rpi-servidor.local` | mDNS bloqueado en la red | Usar la IP de la lista del router o del teléfono |
| Rayo amarillo en pantalla / `vcgencmd get_throttled` ≠ `0x0` | Fuente insuficiente | Fuente oficial (§2) |
| Nodos GPIO en rojo `ECONNREFUSED 127.0.0.1:8888` | `pigpiod` detenido | `sudo systemctl enable --now pigpiod` |
| `pigpiod` no arranca: `initInitialise: Can't lock /var/run/pigpio.pid` | Quedó una instancia vieja | `sudo killall pigpiod; sudo systemctl restart pigpiod` |
| **RPi 5:** `pigpiod` no inicia | pigpio no soporta el chip RP1 de la RPi 5 | Reemplazar los nodos `pi-gpiod` por `node-red-node-pi-gpio` y reescalar el PWM a 0-100 % (supuesto S1 del plan) |
| El pulsador cambia varias veces por pulsación | Antirrebote en microsegundos | El campo *debounce* del nodo es en **µs** ([INCONVENIENTES.md](../evidencia/INCONVENIENTES.md), I-01); el flujo generado ya trae 25 000 |
| C1 en rojo `BadSecurityChecksFailed` (Sign/SignAndEncrypt) | Certificado del otro extremo no confiado | Procedimiento de confianza en [PARTE-4.md](../PARTE-4.md) |
| S2 en rojo `EADDRINUSE` | El puerto 4840 sigue ocupado | `sudo ss -tlnp \| grep 4840` muestra quién lo usa |
| El cliente se conecta pero el tráfico va por Wi-Fi | Endpoint configurado con nombre de host | `config.opcua.endpointCliente` debe ser `opc.tcp://192.168.10.1:4840` (IP, no nombre) |
| Se cambió `config.js` y no cambia nada | Falta reiniciar Node-RED | §15 |

## 17. Probar el sistema sin las placas

Antes de ir al banco, todo lo que no depende del hardware se verifica en la PC.
Así se probó este trabajo antes de tocar las placas:

```powershell
PS> node --test tarea-2/herramientas/prueba_senales.js
PS> python tarea-2/herramientas/prueba_opcua_tramas.py
PS> $env:NODE_PATH = "<carpeta node_modules con node-opcua@2.160.0>"
PS> node --test tarea-2/herramientas/prueba_integracion_opcua.js
```

La prueba de integración levanta el servidor y el cliente reales en
`127.0.0.1` y verifica el namespace, los NodeIds, EURange, `BadNotWritable`,
los modos A y B, los tres endpoints de seguridad y la autenticación por usuario.

También se pueden ejecutar los dos flujos en dos instancias de Node-RED en la
misma PC (puertos 1880 y 1881), con el endpoint del cliente apuntando a
`127.0.0.1` mediante la variable `PDCI_T2_CONFIG_EXTRA`, que solo sirve para
pruebas y se documenta en [settings.pdci-t2.js](settings.pdci-t2.js). Los nodos
GPIO quedan en rojo, porque no hay `pigpiod`, y el resto funciona de punta a
punta.
