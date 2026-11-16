# 04 · Raspberry Pi: microSD, primer arranque y red

**Objetivo:** la Raspberry Pi 4 (dispositivo 2) con el sistema grabado, accesible por SSH con clave
pública por Wi-Fi, con la hora sincronizada y `eth0` en 192.168.10.1/24 sobre el cable directo a la
notebook (192.168.10.2/24).

**Dónde:** el respaldo (§1), en el laboratorio; el resto, donde sea. **Tiempo:** ~45 min, más el
respaldo.

Este procedimiento es el de la T2 ([tarea-2/versiones/v3-node-red/node-red/README.md](../../../tarea-2/versiones/v3-node-red/node-red/README.md),
§4-§7), adaptado a la T3:

- hay una sola placa;
- **no hay GPIO** en la Raspberry, así que tampoco `pigpiod` y no hace falta atarse a Bookworm;
- el otro extremo del cable es la notebook.

---

## 1. ¿microSD propia o la del laboratorio?

| | microSD propia (**recomendada**) | microSD del laboratorio |
|---|---|---|
| Antes | Nada | **Respaldarla** (§1.1). Tiene el programa de otra cátedra |
| Después | Se saca y se guarda; la próxima vez arranca lista | **Restaurarla** (paso 10 §3) |
| Ventaja | Se prepara en casa, 05 incluido; el día del banco solo se enchufa | No requiere comprar una tarjeta |

### 1.1 Respaldo de la microSD del laboratorio

1. **Pedir autorización** a la cátedra para regrabarla, y avisar que se devuelve restaurada.
2. Anotar el modelo de la placa y su número de inventario, y marcar la tarjeta.
3. Insertarla en la notebook. ⚠️ Si Windows ofrece **"formatear el disco"**, elegir **Cancelar**: es la
   partición Linux, que Windows no reconoce.
4. Abrir Win32 Disk Imager:
   - *Image File*: `D:\respaldos\rpi-lab-original.img`, **fuera** del repositorio. Ocupa el tamaño total
     de la tarjeta.
   - *Device*: la letra de la microSD.
   - *Hash*: **SHA256**.
   - Botón **Read**. Al terminar, botón **Verify Only**.
5. Anotar el SHA256:

| Placa (modelo / inventario) | Archivo | SHA256 | Verificado |
|---|---|---|---|
| *completar* | `rpi-lab-original.img` | *completar* | ☐ |

Sin el respaldo verificado, **no** se pasa al §2.

## 2. Grabar el sistema

1. Abrir **Raspberry Pi Imager**:
   - **Dispositivo**: *Raspberry Pi 4*.
   - **Sistema operativo**: *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**, la versión
     actual.
     - *Lite* porque no tiene escritorio: todo se maneja por SSH, quedan libres unos 200-300 MB de RAM
       para Node-RED y hay menos software expuesto.
     - La versión actual alcanza porque la T3 no usa los GPIO de la Raspberry. Lo único que se exige
       es Node.js ≥ 18,5, y se verifica en 05 §1.
   - **Almacenamiento**: la microSD. ⚠️ Revisar dos veces que **no** sea un disco de la notebook: se
     borra entero.
2. En la **personalización del sistema** (*Editar ajustes* o el paso *Personalización*, según la
   versión de Imager):

| Ajuste | Valor | Por qué |
|---|---|---|
| Nombre de host | `rpi-pdci-t3` | Lo usa `ssh rpi-pdci-t3.local` |
| Usuario / contraseña | `pdci` / una robusta, guardada en el gestor | La unidad systemd supone `pdci` (05 §5). **[SEC]** No `pi`: es lo primero que prueban los barridos |
| Wi-Fi | SSID y clave del **punto de acceso del celular** | La Wi-Fi de la facultad suele tener portal cautivo |
| País de la Wi-Fi | `AR` | Fija el dominio regulatorio. **Sin él, la Wi-Fi arranca bloqueada** (*rfkill*) |
| Zona horaria / teclado | `America/Argentina/Cordoba` / `latam` | |
| SSH | Habilitado, **solo con clave pública**: pegar el contenido de `id_ed25519_pdci_t3.pub` (01 §3) | **[SEC]** Sin contraseña por la red |

3. Grabar y esperar la verificación.

## 3. Primer arranque y SSH

1. Insertar la microSD y enchufar la fuente oficial. Esperar **2-3 minutos**: el primer arranque
   expande la partición y se reinicia una vez.
2. Con la notebook conectada a la misma Wi-Fi (la del celular):

```powershell
PS> ssh pdci@rpi-pdci-t3.local
```

Responder `yes` a la huella la primera vez. Si `.local` no resuelve (mDNS bloqueado), buscar la IP en
la lista de dispositivos del celular y usar `ssh -i $env:USERPROFILE\.ssh\id_ed25519_pdci_t3 pdci@<ip>`.
La entrada de `~/.ssh/config` (01 §3) no cubre esa IP, por eso va el `-i`.

3. Actualizar el sistema y comprobar la placa:

```bash
$ cat /proc/device-tree/model; echo          # "Raspberry Pi 4 Model B ..."
$ sudo apt update && sudo apt full-upgrade -y
$ sudo reboot
```

4. Reconectar y verificar la alimentación y la hora:

```bash
$ vcgencmd get_throttled           # throttled=0x0  (si no, la fuente no alcanza)
$ timedatectl                      # "System clock synchronized: yes"
```

**La hora importa.** La Raspberry no tiene reloj de tiempo real: toma la hora por NTP, por la Wi-Fi.
El certificado OPC UA se genera en el primer arranque de Node-RED (05) con la fecha del sistema. Con
la hora mal, los clientes lo rechazarían por "todavía no válido" (riesgo R-09). **No** seguir a 05 sin
`synchronized: yes`.

## 4. Red Ethernet punto a punto

**4.1 Raspberry Pi.** NetworkManager trae un perfil `Wired connection 1` que pide IP por DHCP. En un
cable directo no hay servidor DHCP, así que se reemplaza por uno estático:

```bash
$ nmcli con show
$ sudo nmcli con delete "Wired connection 1"         # si existe
$ sudo nmcli con add type ethernet ifname eth0 con-name pdci-eth0 \
      ipv4.method manual ipv4.addresses 192.168.10.1/24 \
      ipv4.never-default yes ipv6.method disabled connection.autoconnect yes
$ sudo nmcli con up pdci-eth0
```

`ipv4.never-default yes` evita que el perfil instale una ruta por defecto. Internet sigue por
`wlan0`, y por `eth0` solo va 192.168.10.0/24, que es justo el tráfico OPC UA.

**4.2 Notebook** (PowerShell **como administrador**). Primero identificar el adaptador Ethernet:

```powershell
PS> Get-NetAdapter | Format-Table Name, InterfaceDescription, Status
PS> New-NetIPAddress -InterfaceAlias "<Ethernet>" -IPAddress 192.168.10.2 -PrefixLength 24
```

**Sin** `-DefaultGateway`: la salida a internet de la notebook sigue por la Wi-Fi. Para deshacerlo al
terminar (paso 10):

```powershell
PS> Remove-NetIPAddress -InterfaceAlias "<Ethernet>" -IPAddress 192.168.10.2
```

**4.3 Conectar el cable** entre la Raspberry y la notebook, y verificar:

```powershell
PS> ping -n 3 192.168.10.1
```

```bash
$ ip -br addr show eth0                 # 192.168.10.1/24, estado UP
$ ip route | grep default               # la ruta por defecto sale por wlan0, no por eth0
$ sudo apt install -y ethtool && sudo ethtool eth0 | grep -E "Speed|Duplex"   # 1000 o 100 Mb/s, Full
```

`ping` de la Raspberry hacia la notebook puede **no** responder: el firewall de Windows bloquea el ICMP
entrante por defecto. No es un problema, porque el tráfico OPC UA lo inicia la notebook.

---

## Criterio de salida

- [ ] *(Si es la del laboratorio)* Respaldo con SHA256 verificado y anotado.
- [ ] `ssh pdci@rpi-pdci-t3.local` entra **sin** pedir la contraseña del usuario (clave pública).
- [ ] `get_throttled=0x0` y `System clock synchronized: yes`.
- [ ] `ping 192.168.10.1` desde la notebook responde por el cable, y la ruta por defecto de la
      Raspberry sale por `wlan0`.
