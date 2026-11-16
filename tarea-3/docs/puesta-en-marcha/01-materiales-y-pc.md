# 01 · Materiales y preparación de la notebook

**Objetivo:** tener todo el hardware reunido y la notebook (dispositivo 3) con el software instalado
y **el código verificado antes de tocar el banco**.

**Dónde:** en casa, antes del día de laboratorio. **Tiempo:** ~1 h, casi todo de descargas.

---

## 1. Hardware

| Cant. | Elemento | Para qué | Observación |
|---|---|---|---|
| 2 | ESP32 DevKit (ESP-WROOM-32) | Dispositivo 1 y esclavo desconocido | Cable USB **de datos** (muchos cables de carga no tienen las líneas de datos) |
| 2 | Módulo MAX485 (o MAX3485) | Transceptor RS-485 de cada ESP32 | Alimentado a 5 V desde el VIN del ESP32 |
| 1 | Adaptador USB ↔ RS-485 | Maestro: lo enchufa la Raspberry Pi | Con conmutación automática de dirección (riesgo R-04) |
| 1 *(opcional)* | Segundo adaptador USB ↔ RS-485 | Sniffer del bus desde la notebook (09 §2) | Sin él, la captura del bus físico queda pendiente |
| 2 + 2 + 2 | Resistencias 2,2 kΩ + 3,3 kΩ + 680 Ω | Divisor y pull-up de RO, uno por ESP32 | **Obligatorio** (03 §2) |
| 2 + 2 | LED + resistencia de 330 Ω | LED digital y LED PWM del dispositivo 1 | 220 Ω también sirve |
| 1 + 1 | Pulsador + potenciómetro de 10 kΩ | Entradas del dispositivo 1 | |
| 2 *(si el bus mide más de 1,5 m)* | Resistencias de 120 Ω | Terminación en los extremos | Con buses cortos no van (03 §4) |
| — | Protoboard, cables dupont, un puente para GPIO 13 | | |
| 1 m | Par trenzado (un par de un cable UTP sirve) | Bus A/B, más un conductor para GND | |
| 1 | Raspberry Pi 4 Model B | Dispositivo 2 | La del laboratorio o una propia |
| 1 | Fuente oficial de 5,1 V / 3 A, USB-C | Alimentar la Raspberry | Un cargador de teléfono suele dar menos de 4,75 V bajo carga: *undervoltage*, y puede corromper la microSD |
| 1 | microSD de 16 GB o más, clase **A1** | Sistema de la Raspberry | Mejor propia: así no hay que respaldar ni restaurar la del laboratorio (04 §1) |
| 1 | Cable Ethernet cat. 5e | Raspberry ↔ notebook | Directo o cruzado da igual: auto MDI-X |
| 1 | Lector de microSD | Grabar y respaldar | |
| 1 | Celular con punto de acceso (WPA2 personal) | Internet para la Raspberry y la notebook | Probarlo antes (riesgo R-06) |

## 2. Software de la notebook

Todo es libre o gratuito.

| Programa | Para qué | Etapa |
|---|---|---|
| Git for Windows (incluye **Git Bash**) | Clonar el repositorio y ejecutar los `.sh` | 01, 09 |
| **Python 3.11** (python.org, con el *py launcher*) | Edge Node, observador, simuladores, pruebas | 01, 07 |
| **Node.js LTS ≥ 18.5** | Pruebas, servidor de la web, verificador OPC UA, banco virtual | 01, 08 |
| **Thonny** | Grabar MicroPython y cargar el firmware del ESP32 | 03 |
| **Raspberry Pi Imager** | Grabar el sistema de la Raspberry | 04 |
| **Win32 Disk Imager** | Respaldar y restaurar la microSD del laboratorio | 04, 10 |
| **Wireshark** (con Npcap) | Capturas OPC UA en la placa de red y en el loopback | 09 |
| **MQTT Explorer** | Ver los mensajes en el broker | 07, 09 |
| **UaExpert** (Unified Automation, registro gratuito) | Recorrer el espacio de direcciones OPC UA | 09 |
| Cliente SSH (`ssh`, `scp`) | Ya viene con Windows 10/11 | 04, 05 |
| QModMaster *(opcional)* | Probar el esclavo sin la Raspberry (03 §6) | 03 |

## 3. Clave SSH (una sola vez)

**[SEC]** La clave reemplaza a la contraseña para entrar a la Raspberry: no se puede adivinar por fuerza
bruta y no viaja por la red.

Se crea una clave **solo para el TP**, con su propio nombre de archivo (`-f`):

```powershell
PS> ssh-keygen -t ed25519 -C "pdci-t3" -f $env:USERPROFILE\.ssh\id_ed25519_pdci_t3
```

- Poner una frase de paso.
- ⚠️ **No usar la ruta por defecto (`id_ed25519`) si ya existe**: si `ssh-keygen` pregunta
  `Overwrite (y/n)?`, responder **`n`**. Sobrescribirla borra la clave que ya se usa para GitHub u otros
  equipos, y se pierde ese acceso.
- **Por qué una clave aparte:** si se compromete (la notebook se usa en el aula, la microSD pasa por
  otras manos), se descarta sin afectar ningún otro acceso. Es el mismo criterio de credenciales
  separadas que se usa en el broker.
- La clave pública (`id_ed25519_pdci_t3.pub`) es la que se le da a la Raspberry en 04 §2.
- La privada (`id_ed25519_pdci_t3`, sin extensión) **no sale de la notebook**.

Para que `ssh`, `scp`, el túnel al Dashboard y el menú de fallas usen esa clave sin escribir `-i` en
cada comando, agregar esta entrada a `C:\Users\<usuario>\.ssh\config` (si el archivo no existe, se
crea):

```text
Host rpi-pdci-t3.local 192.168.10.1
    User pdci
    IdentityFile ~/.ssh/id_ed25519_pdci_t3
    IdentitiesOnly yes
```

- `IdentitiesOnly yes` evita que SSH le ofrezca primero a la placa las otras claves de la notebook.
- La entrada cubre el nombre mDNS y la IP fija del cable (192.168.10.1, 04 §4). Si se entra por la IP
  que asigna el celular, que cambia, hay que indicar la clave a mano: `ssh -i
  $env:USERPROFILE\.ssh\id_ed25519_pdci_t3 pdci@<ip>`.

*(Alternativa: reutilizar la clave existente, `id_ed25519.pub`. Funciona, pero comparte el riesgo con
todos los demás accesos de esa clave.)*

## 4. Repositorio y dependencias

```powershell
PS> git clone https://github.com/bevilacquafrancisco/protocolos-comunicaciones-industriales.git
PS> cd protocolos-comunicaciones-industriales
PS> git switch develop
PS> cd tarea-3
```

**Dispositivo 3** (Python, con las herramientas de desarrollo, que las pruebas necesitan):

```powershell
PS> cd gateway-sparkplug
PS> py -3.11 -m venv .venv
PS> .venv\Scripts\pip install -r requirements-dev.txt
PS> cd ..
```

**Node-RED y la web** (las versiones salen de los `package-lock.json`):

```powershell
PS> cd edge-nodered; npm ci; cd ..
PS> cd hmi-web; npm ci; cd ..
```

`npm ci` y no `npm install`: instala **exactamente** lo que está en el lockfile, la misma versión de
cada paquete que se probó. Un `npm install` podría traer otra el día de la defensa.

## 5. Verificar el código antes de ir al banco

Desde `tarea-3/`:

```powershell
PS> py -3.11 firmware\esclavo-modbus\test\correr_todo.py
PS> cd edge-nodered; npx jest; cd ..
PS> cd gateway-sparkplug; .venv\Scripts\python -m pytest -q; cd ..
PS> cd hmi-web; npm test; cd ..
```

| Suite | Resultado esperado (2026-11-14) |
|---|---|
| Firmware del esclavo (CPython) | `TODO OK`: 169 verificaciones (35 + 48 + 57 + 29) |
| `edge-nodered` (Jest) | 179 de 179 |
| `gateway-sparkplug` (pytest) | 61 de 61 |
| `hmi-web` (`node:test`, incluye la página en Chrome) | 16 de 16 |

Si una suite falla en la notebook del banco y no en otra, la diferencia está en el entorno: versión de
Python o de Node, o un puerto ocupado. Hay que resolverlo acá y no en el laboratorio.

**Opcional, recomendado.** Ensayar la cadena completa sin hardware con el banco virtual. Levanta todo
con el software real y permite practicar las fallas antes del banco:

```bash
GB$ scripts/inyectar-fallas.sh          # opción 0: levantar la cadena virtual
```

---

## Criterio de salida

- [ ] Hardware de §1 reunido. La microSD propia, si se usa, está etiquetada.
- [ ] Software de §2 instalado.
- [ ] Clave SSH creada (§3).
- [ ] Las cuatro suites de §5 en verde **en la notebook que se lleva al banco**, con los números de la
      tabla.
