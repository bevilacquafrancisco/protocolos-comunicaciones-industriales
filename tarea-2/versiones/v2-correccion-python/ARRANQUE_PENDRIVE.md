# Raspberry Pi 4 desde un pendrive, sin monitor (solo SSH)

Cómo preparar, arrancar, encontrar y diagnosticar una Raspberry Pi 4 que arranca desde un pendrive
USB y se usa **sin monitor**, solo por SSH. Sirve para las dos placas del TP (`raspberry-servidor`
y `raspberry-cliente`). Al terminar, se sigue con el [README.md](README.md) desde el §4.

Convenciones: `PC>` = PowerShell en Windows · `pi$` = terminal SSH en la Raspberry Pi.

---

## 0. Resumen: qué se hace dónde

| Paso | ¿En casa? | ¿En el laboratorio? | Necesita |
|---|---|---|---|
| Grabar el pendrive (§3) | **Sí** | Sí | PC, pendrive, internet para bajar la imagen |
| Primer arranque (§4) | Solo si tenés una Pi en casa | Sí | La Wi-Fi configurada en el pendrive tiene que estar **presente** |
| Instalar paquetes (README §4) | Solo si tenés una Pi en casa | Sí | Internet en la Pi (Wi-Fi, o la PC por cable, §6.2) |
| Red `eth0` entre placas y TP | No | Sí | Las dos placas |

**No es obligatorio usar la Wi-Fi del laboratorio.** Lo único que se necesita es que la PC y la
Raspberry estén **en la misma red** (para SSH y para UaExpert en la Parte 2.5). La forma más
simple y portátil de lograrlo es el **hotspot del teléfono** (§1).

## 1. ¿Qué red Wi-Fi configurar?

La Raspberry no tiene teclado ni pantalla: la red Wi-Fi tiene que quedar grabada en el pendrive
**antes** del primer arranque, y esa red tiene que **existir donde se arranque la placa**.

| Opción | Se prepara en casa | Funciona en el laboratorio | Ventajas | Riesgos |
|---|---|---|---|---|
| **A. Hotspot del teléfono** (recomendada) | Sí | Sí: el teléfono viaja con vos | Misma red en todos lados; vos la controlás; sin aislamiento entre clientes | Consume datos móviles (§1.1); límite de unos 5 a 10 dispositivos |
| B. Wi-Fi del laboratorio | Solo si conocés el nombre y la clave | Sí, **si** es WPA2-Personal y no aísla clientes | No consume datos | No se puede probar en casa; puede tener aislamiento entre clientes (la PC no ve a la Pi) o ser WPA2-Enterprise (Imager no la soporta) |
| C. Wi-Fi de tu casa | Sí | **No** (salvo que agregues otra red, §3.3) | Instalación en casa sin consumir datos | En el laboratorio la placa no se conecta |
| D. Varias redes a la vez (§3.3 o §7) | Sí | Sí | Se conecta a la que encuentre: casa, hotspot y laboratorio | Hay que editar un archivo o hacerlo después del primer arranque |

**Recomendación:** grabar el pendrive con el **hotspot del teléfono** (opción A) y, si alguien
tiene una Pi en casa, agregar además la Wi-Fi de su casa (opción D).

Requisitos del hotspot: **WPA2 Personal** (o WPA2/WPA3), banda de **2,4 GHz** o "compatibilidad
máxima" (la Pi 4 también usa 5 GHz, pero 2,4 GHz evita problemas de país y canal), y un nombre sin
tildes ni caracteres raros.

### 1.1 Consumo de datos aproximado (opción A)

| Actividad | Consumo |
|---|---|
| `apt full-upgrade` sobre una imagen reciente | 100 – 500 MB |
| `apt install` de los paquetes del TP | 20 – 50 MB |
| `pip install asyncua` | ~15 MB |
| Trabajo normal por SSH | despreciable |

Para no gastar datos móviles: hacé la instalación en casa (si tenés una Pi) o usá la **conexión
compartida de la PC por cable** (§6.2), que saca internet de la red de la PC.

### 1.2 ¿La Wi-Fi del laboratorio sirve? Cómo saberlo

1. Tipo de red: si al conectarte te pide **usuario y contraseña** (como eduroam o un portal
   institucional), es *Enterprise* o *portal cautivo*: **no sirve** para el arranque sin monitor.
2. Aislamiento entre clientes: conectá la PC y un teléfono a esa red, averiguá la IP del teléfono
   y hacé `PC> ping <IP del teléfono>`. Si no responde, la red probablemente aísla los clientes y
   la PC tampoco va a ver a la Raspberry.

Si alguna de las dos pruebas falla, usá el hotspot.

## 2. Materiales

| Elemento | Detalle |
|---|---|
| Raspberry Pi 4 | Con la **microSD retirada** |
| Pendrive | USB 3.0, 16 GB o más, de marca. Uno por placa |
| Fuente | Oficial, 5,1 V / 3 A, USB-C |
| Cable Ethernet | Uno cualquiera: la Pi 4 y las PC actuales tienen auto MDI-X (no hace falta cable cruzado) |
| PC | Windows 10/11 con Raspberry Pi Imager y OpenSSH (incluido). Si la notebook no tiene puerto RJ45: un adaptador USB-Ethernet |
| Teléfono | Si se usa la opción A |

## 3. Grabar el pendrive (en casa o en cualquier lugar)

### 3.1 Clave SSH (una sola vez por PC)

```powershell
PC> ssh-keygen -t ed25519            # Enter para aceptar la ruta; ponerle una frase de paso
PC> Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub     # esto es lo que se pega en Imager
```

Hacé una copia de `id_ed25519` (la clave **privada**) en un lugar seguro. Sin monitor, si la
perdés, no entrás más a la placa y hay que volver a grabar el pendrive.

### 3.2 Raspberry Pi Imager

1. Conectar el pendrive. Desconectar cualquier otro pendrive o disco USB, para no equivocarse.
2. **Choose Device** → *Raspberry Pi 4*.
3. **Choose OS** → *Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)*.
4. **Choose Storage** → el pendrive (comprobá la capacidad).
5. **Next → Edit Settings**:

   | Pestaña | Campo | Valor |
   |---|---|---|
   | General | Hostname | `raspberry-servidor` o `raspberry-cliente` (**distinto en cada placa**) |
   | General | Usuario / contraseña | `pi` y una contraseña nueva, que no se escribe en ningún documento |
   | General | Wi-Fi | SSID y clave **exactos** (distingue mayúsculas); país inalámbrico `AR` |
   | General | Configuración regional | Zona `America/Argentina/Buenos_Aires`, teclado `es` |
   | Services | SSH | *Enable SSH → Allow public-key authentication only*; pegar el contenido de `id_ed25519.pub` |

6. **Save → Yes → Yes**. Esperar a *Write Successful* (graba y verifica).
7. Si Windows dice *"Debe formatear el disco"*: **Cancelar**. Esa es la partición de Linux, que
   Windows no reconoce; formatearla borra el sistema.

### 3.3 Comprobar el pendrive y, si querés, agregar más redes Wi-Fi

Desconectá el pendrive y volvé a conectarlo. Abrí la unidad **`bootfs`** en el Explorador:

| Encontrás | Imagen | Significa |
|---|---|---|
| `user-data` y `network-config` | Reciente (Debian 13 "trixie", la del banco) | Personalización aplicada con cloud-init |
| `firstrun.sh` | Anterior (Debian 12 "bookworm") | Personalización aplicada con un script |
| Ninguno de los dos | — | **Imager no aplicó la configuración**: volver a grabar. Es la causa número uno de "la placa no aparece" |

**Agregar redes antes del primer arranque** (opción D, solo con `network-config`):

1. Abrí `network-config` con el Bloc de notas.
2. Ubicá la sección `access-points:` con la red que cargó Imager.
3. Agregá debajo otra red con **la misma indentación** (espacios, nunca tabulaciones). La
   estructura es parecida a esta; respetá la del archivo:

   ```yaml
         access-points:
           "HotspotTelefono":
             password: "<clave o valor que puso Imager>"
           "WiFiCasa":
             password: "clave-de-casa"
   ```

4. Guardar y expulsar el pendrive.

Este archivo se aplica **en el primer arranque**: modificarlo después no tiene efecto (para eso
está el §7). Si tu imagen trae `firstrun.sh`, no lo edites: agregá las redes después con el §7.

**[SEC]** El pendrive guarda la clave de la Wi-Fi y tu usuario. No lo prestes, y al terminar la
cursada cambiá la clave del hotspot.

## 4. Primer arranque

1. Placa **apagada** (fuente desenchufada). **Sacá la microSD** y guardala aparte (si es del
   laboratorio, volvé a ponerla al terminar).
2. Pendrive en un **puerto USB 3.0 azul**.
3. Encendé el hotspot o asegurate de que la red Wi-Fi configurada esté al alcance.
4. Enchufá la fuente y esperá **3 minutos**: en el primer arranque agranda la partición, aplica la
   configuración y se reinicia una vez.
5. Mirá los LED:

| LED | Estado | Significado |
|---|---|---|
| Rojo (PWR) | Fijo | Alimentación correcta |
| Rojo | Parpadea o se apaga | Tensión insuficiente: fuente oficial y nada más conectado al USB |
| Verde (ACT) | Parpadeo irregular | Leyendo el pendrive: va bien |
| Verde | Patrón repetido de destellos largos y cortos | Error de arranque: tabla del §9 |
| Verde | Apagado; la placa nunca aparece en la red | No encontró desde dónde arrancar: §8 |

## 5. Encontrar la placa por Wi-Fi

La PC tiene que estar **en la misma red Wi-Fi** que la Raspberry.

| # | Método | Cómo |
|---|---|---|
| 1 | Nombre `.local` (mDNS) | `PC> ping raspberry-servidor.local` y después `PC> ssh pi@raspberry-servidor.local` |
| 2 | Lista del hotspot | En el teléfono: *Hotspot → Dispositivos conectados*; muestra el hostname y la IP |
| 3 | Router de casa | Página de administración del router → lista de clientes DHCP |
| 4 | Barrido de la red | `PC> ipconfig` (anotar la red, p. ej. 192.168.43.0/24) y `PC> nmap -sn 192.168.43.0/24` (nmap es libre); buscar el fabricante *Raspberry Pi* |

Primera conexión: SSH pregunta si confiás en la huella del equipo; respondé `yes`. Si aparece
`REMOTE HOST IDENTIFICATION HAS CHANGED` (pendrive regrabado con el mismo nombre):
`PC> ssh-keygen -R raspberry-servidor.local`.

Si nada de esto funciona, usá el cable (§6).

## 6. Acceso y diagnóstico por cable Ethernet (PC ↔ Pi)

### 6.1 Cuándo usarlo

- La placa no aparece por Wi-Fi: clave mal escrita, la red no está, aislamiento entre clientes.
- No hay Wi-Fi utilizable en el laboratorio.
- Hace falta internet en la Pi sin consumir datos móviles (§6.2 se lo da).
- Revisar o corregir la configuración de red de la placa.

**Qué método usar según el estado de `eth0` de la placa:**

| Estado de `eth0` en la Pi | Método |
|---|---|
| De fábrica (DHCP): todavía no se hizo la Parte 1 del TP | §6.2 Conexión compartida (recomendado) |
| IP fija del TP (192.168.10.1 o .2) | §6.3 IP fija en la PC |
| No sé | Probar §6.3 primero; si no responde, §6.2 |

**Aclaración importante:** una Pi con `eth0` en DHCP y sin servidor DHCP en el cable **no** se
asigna sola una dirección 169.254.x.x (NetworkManager no lo hace por defecto). Por eso conectar el
cable directo, sin más, no alcanza: hace falta que la PC entregue una dirección (§6.2) o usar la IP
fija (§6.3).

### 6.2 Conexión compartida de Windows (la PC le da IP e internet a la Pi)

Windows hace de servidor DHCP en su puerto Ethernet y comparte su internet (Wi-Fi) con la Pi.

1. Conectá el cable entre la PC y la Pi (todavía apagada).
2. `Win + R` → `ncpa.cpl` → Enter.
3. Botón derecho sobre el adaptador **Wi-Fi** (el que tiene internet) → *Propiedades* → pestaña
   **Uso compartido**.
4. Tildá *"Permitir que los usuarios de otras redes se conecten a través de la conexión a Internet
   de este equipo"*. En *Conexión de red doméstica*, elegí el adaptador **Ethernet** → *Aceptar*.
5. Windows pone su Ethernet en **192.168.137.1/24** y entrega direcciones 192.168.137.x.
6. Encendé la Pi y esperá 2 a 3 minutos.
7. Buscala:

   ```powershell
   PC> ping raspberry-servidor.local
   PC> arp -a -N 192.168.137.1
   ```

   En `arp -a`, la Pi aparece como una entrada *dinámica* 192.168.137.x con MAC que empieza con
   `dc-a6-32`, `e4-5f-01` o `d8-3a-dd` (prefijos de Raspberry Pi).
8. Entrá: `PC> ssh pi@192.168.137.<x>` (o por el nombre `.local`).
9. Comprobá internet desde la Pi: `pi$ ping -c 3 deb.debian.org`. Ya podés hacer `apt` y `pip` sin
   consumir datos móviles.

**Al terminar:** desactivá el uso compartido (destildar el paso 4). Si no, el Ethernet de la PC
queda fijo en 192.168.137.1.

Limitaciones: en PCs institucionales puede estar bloqueado por política; con la notebook propia
funciona.

### 6.3 IP fija en la PC (cuando la Pi ya tiene la IP del TP)

Cuando `eth0` ya está en 192.168.10.1 (servidor) o 192.168.10.2 (cliente), poné la PC en la misma
red con una dirección que no use nadie, por ejemplo **192.168.10.100/24**.

PowerShell **como administrador** (el nombre del adaptador sale de `Get-NetAdapter`):

```powershell
PC> Get-NetAdapter                                   # ver el nombre: "Ethernet", "Ethernet 2"...
PC> New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.10.100 -PrefixLength 24
PC> ping 192.168.10.1
PC> ssh pi@192.168.10.1
```

Volver a la configuración normal al terminar:

```powershell
PC> Remove-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.10.100 -Confirm:$false
PC> Set-NetIPInterface -InterfaceAlias "Ethernet" -Dhcp Enabled
```

Alternativa gráfica: `ncpa.cpl` → Ethernet → *Propiedades* → *Protocolo de Internet versión 4* →
*Usar la siguiente dirección IP* → 192.168.10.100, máscara 255.255.255.0, sin puerta de enlace.

**Precaución con el TP:** mientras la PC esté conectada al enlace entre placas, su tráfico aparece en
las capturas de la Parte 4. Para capturar, el cable tiene que ir **solo entre las dos Raspberry**.

### 6.4 Diagnóstico por capas desde la PC

Revisar en orden. La primera prueba que falla indica la capa del problema.

| Capa | Prueba | Resultado bueno | Si falla |
|---|---|---|---|
| Física | LED del conector RJ45 de la Pi y de la PC | Encendidos; el de actividad parpadea | Cable o conector: probar otro cable; verificar que la Pi esté encendida (LED rojo) |
| Física / enlace | `PC> Get-NetAdapter -Name "Ethernet" \| Format-List Status, LinkSpeed, MacAddress` | `Status: Up`, `LinkSpeed: 1 Gbps` (o 100 Mbps) | `Disconnected`: cable, adaptador USB-Ethernet o placa apagada |
| Red (PC) | `PC> ipconfig` (adaptador Ethernet) | 192.168.137.1 (§6.2) o 192.168.10.100 (§6.3) | Repetir el §6.2 o el §6.3 |
| Enlace (ARP) | `PC> ping <IP de la Pi>` y luego `PC> arp -a` | La IP de la Pi con una MAC `dc-a6-32…`, `e4-5f-01…` o `d8-3a-dd…` | Sin entrada: la Pi no tiene IP en esa red (método equivocado del §6.1, o todavía arrancando) |
| Red | `PC> ping <IP de la Pi>` | Respuestas con tiempos de 1 ms o menos | Hay entrada ARP pero no responde: firewall o IP duplicada |
| Transporte | `PC> Test-NetConnection <IP de la Pi> -Port 22` | `TcpTestSucceeded : True` | `False`: SSH no habilitado (Imager no aplicó la configuración, §3.3) |
| Aplicación | `PC> ssh -v pi@<IP de la Pi>` | Pide la frase de paso de la clave o abre la sesión | `Permission denied (publickey)`: no es la clave que se pegó en Imager. `Host key verification failed`: `ssh-keygen -R <IP>` |

### 6.5 Diagnóstico dentro de la Pi (una vez que entraste por cable)

```bash
pi$ nmcli device status                       # estado de eth0 y wlan0
pi$ nmcli -f NAME,TYPE,DEVICE,AUTOCONNECT connection show
pi$ ip -br addr                               # direcciones de cada interfaz
pi$ ip route                                  # la ruta "default" tiene que salir por wlan0 (o por eth0 en el §6.2)
pi$ nmcli device wifi list                    # redes que ve la Pi (¿aparece la tuya?)
pi$ journalctl -b -u NetworkManager | grep -iE "wlan0|wifi|auth|fail" | tail -20
pi$ iw reg get                                # país inalámbrico: debe decir AR
pi$ rfkill list                               # "Soft blocked: yes" en wlan → sudo rfkill unblock wifi
```

| Síntoma en la Pi | Causa | Solución |
|---|---|---|
| `nmcli device wifi list` no muestra tu red | Hotspot en 5 GHz con un canal no permitido, o fuera de alcance | Hotspot en 2,4 GHz o "compatibilidad máxima" |
| `journalctl` muestra `secrets were required` o `auth failed` | Clave incorrecta | Corregir con el §7 |
| `wlan0` como `unavailable` | Wi-Fi bloqueada o sin país | `sudo rfkill unblock wifi`; `sudo raspi-config` → *Localisation Options → WLAN Country → AR* |
| Wi-Fi conectada pero la PC no ve la Pi | Aislamiento de clientes en la red | Usar el hotspot o trabajar por cable |

## 7. Agregar o corregir redes Wi-Fi después del primer arranque

Desde una sesión SSH (por Wi-Fi o por cable):

```bash
pi$ sudo nmtui
#   Edit a connection → Add → Wi-Fi → SSID y clave → OK
#   (interactivo: la clave no queda en el historial de la shell)
```

Prioridades: si la placa ve varias redes conocidas, NetworkManager elige la de mayor prioridad.

```bash
pi$ nmcli -f NAME,AUTOCONNECT-PRIORITY connection show
pi$ sudo nmcli connection modify "HotspotTelefono" connection.autoconnect-priority 20
pi$ sudo nmcli connection modify "WiFiCasa" connection.autoconnect-priority 10
pi$ sudo nmcli connection up "HotspotTelefono"      # probarla ahora mismo
```

Consejo: antes de llevar la placa a otro lugar, comprobá desde SSH que el perfil nuevo existe
(`nmcli connection show`). Si cambiás la red Wi-Fi por la que estás conectado, la sesión SSH se
corta: hacelo por cable (§6).

## 8. Si no arranca desde el pendrive: bootloader (sin monitor)

La Pi 4 arranca desde USB si su bootloader (grabado en la placa) es de **septiembre de 2020 o
posterior** y su `BOOT_ORDER` incluye USB. El valor de fábrica más común, `0xf41`, se lee de
derecha a izquierda: **1** = microSD, **4** = USB, **f** = repetir. Sin microSD puesta, arranca del
USB.

**Si tenés una microSD con Raspberry Pi OS a la que entrás por SSH:**

```bash
pi$ vcgencmd bootloader_version                    # fecha ≥ septiembre de 2020
pi$ vcgencmd bootloader_config | grep BOOT_ORDER   # tiene que contener 4
pi$ sudo apt update && sudo apt full-upgrade -y
pi$ sudo rpi-eeprom-update -a && sudo reboot       # solo si el bootloader es viejo
```

**Si no tenés ninguna microSD con sistema:** en Imager, *Misc utility images → Bootloader (Pi 4
family) → USB Boot*, grabado en una **microSD** (no en el pendrive). Arrancá con esa microSD:

| LED verde (a los ~10 s) | Significado |
|---|---|
| Parpadea **rápido y sin parar** | Bootloader actualizado, con USB primero (`0xf14`). Apagar, sacar la microSD y volver al §4 |
| Patrón largo/corto | Error (§9) |

Para que el USB tenga prioridad aunque haya una microSD puesta: `pi$ sudo raspi-config` → *6
Advanced Options → A4 Boot Order → B2 USB Boot*. En las placas del laboratorio, solo con
autorización (modifica la placa, aunque es reversible con *B1 SD Card Boot*).

## 9. Códigos de error del LED verde (Pi 4)

Se cuentan los destellos **largos** y luego los **cortos**; el patrón se repite.

| Largos · cortos | Significado | Qué hacer |
|---|---|---|
| 0 · 3 | Falla genérica de arranque | Volver a grabar el pendrive |
| 0 · 4 | No encuentra `start*.elf` | Imagen incompleta: volver a grabar y verificar |
| 0 · 7 | No encuentra el kernel | Imagen de otro modelo: *Raspberry Pi 4* en Imager |
| 2 · 1 | La partición de arranque no es FAT | Pendrive formateado a mano: volver a grabar con Imager |
| 2 · 2 | No puede leer la partición | Pendrive defectuoso o incompatible: probar con otro |
| 3 · 1 / 3 · 2 | Error de la EEPROM | §8, imagen *Bootloader* |
| 4 · 4 | Modelo de placa no soportado | Imagen o bootloader equivocados |
| 4 · 6 / 4 · 7 | Falla de alimentación | Fuente oficial; nada más conectado al USB |

## 10. Comprobar que arrancó desde el pendrive

```bash
pi$ findmnt -no SOURCE /       # /dev/sda2 = pendrive · /dev/mmcblk0p2 = microSD
pi$ df -h /                    # tamaño ≈ capacidad del pendrive (la partición se agrandó)
pi$ lsusb -t                   # 5000M = USB 3.0 · 480M = está en un puerto USB 2.0
pi$ dmesg | grep -iE "sda|usb" | grep -iE "error|reset"    # sin salida = sin errores de disco
```

## 11. Apagado y cuidado del pendrive

```bash
pi$ sudo poweroff
```

Esperá a que el LED verde haga sus últimos parpadeos y quede **apagado** (unos 10 s). Recién
entonces desenchufá la fuente. Cortar la alimentación en medio de una escritura puede dañar el
sistema de archivos.

- No desconectes el pendrive con la placa encendida.
- Antes de una entrega o de la defensa, conviene una copia de seguridad del pendrive ya configurado,
  con Win32 Disk Imager (*Read*) en la PC. Si falla, se restaura en minutos.
- Cada pendrive queda asociado a su placa por el hostname: etiquetalos (**servidor** / **cliente**).

## 12. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| La placa no aparece en ninguna red | Personalización no aplicada | §3.3: comprobar `user-data`/`firstrun.sh`; volver a grabar |
| Aparece en casa pero no en el laboratorio | La red de casa no existe en el laboratorio | Hotspot (§1) o agregar la red (§7) |
| En la red del laboratorio la PC no la ve | Aislamiento entre clientes | Hotspot o cable (§6) |
| `ssh: Could not resolve hostname …local` | mDNS bloqueado en la red | Buscar la IP (§5, métodos 2-4) o por cable (§6) |
| `Permission denied (publickey)` | Otra clave, u otra PC | Usar la PC y la clave que se cargaron en Imager |
| Arranca la microSD en lugar del pendrive | microSD puesta con `BOOT_ORDER=0xf41` | Sacar la microSD |
| Lenta, con `I/O error` en `dmesg` | Pendrive malo o en un puerto USB 2.0 | Pendrive USB 3.0 de marca, en puerto azul |
| Hora incorrecta; `apt` falla por certificados | Sin internet no hay sincronización de hora (la Pi no tiene reloj propio) | Darle internet (Wi-Fi o §6.2) |
| Windows pide formatear el pendrive | No lee ext4 | **Cancelar** |
