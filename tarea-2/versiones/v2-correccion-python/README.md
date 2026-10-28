# Tarea 2 OPC UA — versión Python corregida

Corrección de la versión Python/asyncua original ([../v1-original-agustina/](../v1-original-agustina/)).
**Puesta en marcha rápida, de la microSD a la última consigna:** [../../guia/](../../guia/).
**Qué se corrigió y por qué:** [../v1-original-agustina/CORRECCIONES.md](../v1-original-agustina/CORRECCIONES.md).
**Cómo cumplir cada punto de la consigna:** [CONSIGNA.md](CONSIGNA.md).
Este archivo: instalar desde cero y ejecutar.

## 1. Archivos

| Archivo | Placa | Reemplaza a | Función |
|---|---|---|---|
| [servidor.py](servidor.py) | RPi 1 | `servidor.py` y `servidor_ns1.py` | Servidor OPC UA, rampa diente de sierra, pulsador, LED, 3 endpoints, usuarios |
| [cliente.py](cliente.py) | RPi 2 | `cliente.py` | Modo A: un Read de los dos nodos cada 100 ms |
| [cliente_suscripcion.py](cliente_suscripcion.py) | RPi 2 | `cliente_suscripcion_v2.py` | Modo B: suscripción de 100 ms |
| [cliente_base.py](cliente_base.py) | RPi 2 | (código repetido en los dos clientes) | Conexión, seguridad, rampa triangular, escrituras, consola, reconexión |
| [comun.py](comun.py) | ambas | (constantes repetidas en los tres archivos) | Pines, NodeIds, rampas, escala 0-255, gamma, GPIO, línea `LATENCIA` |
| [generar_certificados.py](generar_certificados.py) | ambas | — | Certificado X.509 de aplicación (consigna 4.8) |
| [generar_hash.py](generar_hash.py) | RPi 1 | — | Hash scrypt de la clave del usuario (4.9) |
| [iniciar.sh](iniciar.sh) | ambas | — | Arranca con entorno y secretos; guarda la salida en `registros/` |
| [prueba_local.py](prueba_local.py) | PC | — | 50 verificaciones sin placas (§9) |
| [diagramas/](diagramas/) | — | figuras de la guía `.docx` | Red y conexionado, flujo del servidor (S1-S7) y del cliente (C1-C7) |
| [requirements.txt](requirements.txt) | ambas | `pip install asyncua gpiozero` sin versión | `asyncua==2.1.0` |

Esta guía reemplaza a `puesta_en_marcha.txt` y a `Puesta_en_marcha_TP_OPC_UA_Raspberry_Pi.docx`.

## 2. Materiales y conexionado

2 × Raspberry Pi 4 con microSD y fuente USB-C, 1 cable Ethernet, por placa: protoboard, 1 pulsador,
2 LED, 2 resistencias de 220 Ω y cables. Conexionado idéntico en las dos placas, **con la placa
apagada**: [diagramas/red.md](diagramas/red.md).

| Función | GPIO | Pin | Conexión |
|---|---|---|---|
| Pulsador | 17 | 11 | 3,3 V (pin 1) → pulsador → GPIO17, pull-down interno |
| LED digital | 27 | 13 | GPIO27 → 220 Ω → LED → GND |
| LED PWM | 18 | 12 | GPIO18 → 220 Ω → LED → GND |

Software en la PC: Raspberry Pi Imager, UaExpert, Wireshark (con Npcap), OpenSSH (incluido en Windows).

## 3. microSD, primer arranque y SSH

**Con microSD** (procedimiento vigente, incluye Wi-Fi de casa, celular y laboratorio):
[../../guia/01_instalar_SO_microSD.md](../../guia/01_instalar_SO_microSD.md). **Con pendrive y sin
monitor** (y diagnóstico por cable Ethernet): [ARRANQUE_PENDRIVE.md](ARRANQUE_PENDRIVE.md).
Cualquiera de las dos reemplaza este paso; después se sigue desde el §4.

1. Raspberry Pi Imager → Raspberry Pi OS (64-bit). En *Editar ajustes*:

   | | RPi 1 | RPi 2 |
   |---|---|---|
   | Hostname | `raspberry-servidor` | `raspberry-cliente` |
   | Usuario | `pi` | `pi` |
   | Wi-Fi | la misma red que la PC | la misma red que la PC |
   | SSH | **clave pública** (pegar `id_ed25519.pub`) | ídem |

   La clave SSH se crea una vez en la PC: `ssh-keygen -t ed25519`. **[SEC]** La contraseña de las
   placas no se escribe en ninguna guía ni informe.
2. Encender y esperar 2-3 min. Desde PowerShell: `ssh pi@raspberry-servidor.local` (y `raspberry-cliente.local`).
3. Comprobar el sistema: `cat /etc/os-release` y `python3 --version` (anotarlos para el informe).

## 4. Paquetes y entorno Python (en las dos placas)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-gpiozero python3-lgpio tcpdump ethtool chrony
python3 -m venv --system-site-packages ~/opcua-env     # ve gpiozero y lgpio del sistema
source ~/opcua-env/bin/activate
python -c "import gpiozero, lgpio; print('GPIO OK')"
```

`--system-site-packages` evita compilar `lgpio` con pip (swig, `liblgpio-dev`), que fue el problema
de la versión anterior. Si aun así `gpiozero` cae en `NativeFactory`, la alternativa sigue siendo
`sudo apt install -y swig build-essential python3-dev liblgpio-dev && pip install lgpio`.

## 5. Red Ethernet punto a punto (consigna 1.2)

Conectar el cable entre las placas. En cada una, ver el nombre del perfil de `eth0`
(en el banco fue `netplan-eth0`; en otras imágenes, `Wired connection 1`):

```bash
nmcli -f NAME,DEVICE connection show
```

RPi 1 (en la RPi 2, `192.168.10.2/24`):

```bash
PERFIL="netplan-eth0"            # el nombre que mostró el comando anterior
sudo nmcli connection modify "$PERFIL" ipv4.method manual ipv4.addresses 192.168.10.1/24 \
     ipv4.gateway "" ipv4.dns "" ipv4.never-default yes ipv6.method disabled connection.autoconnect yes
sudo nmcli connection up "$PERFIL"
ip addr show eth0
```

`ipv4.never-default yes` es lo nuevo respecto de la guía anterior: el perfil no instala ruta por
defecto, así internet y SSH siguen por `wlan0` y por `eth0` solo va 192.168.10.0/24 (consigna 1.4).
Verificación completa por capas: [CONSIGNA.md §Parte 1](CONSIGNA.md#parte-1--red-ethernet-punto-a-punto).

## 6. Copiar los programas, certificados y secretos

**Copiar** (desde PowerShell, en la carpeta del repositorio):

```powershell
foreach ($p in "raspberry-servidor", "raspberry-cliente") {
  ssh pi@$p.local "mkdir -p ~/TP2_OPC"
  scp versiones\v2-correccion-python\*.py versiones\v2-correccion-python\requirements.txt versiones\v2-correccion-python\iniciar.sh pi@$p.local:~/TP2_OPC/
}
```

**Dependencias y certificados** (en cada placa):

```bash
cd ~/TP2_OPC && chmod +x iniciar.sh
source ~/opcua-env/bin/activate
pip install -r requirements.txt
pip freeze > registros_versiones.txt            # versiones reales, para el informe
python generar_certificados.py servidor         # en la RPi 1
python generar_certificados.py cliente          # en la RPi 2
```

Cada placa queda con `pki/own/<rol>_cert.der` (público) y `pki/own/<rol>_key.pem` (**privado, no
sale de la placa**). El cliente necesita el certificado del servidor para Sign/SignAndEncrypt
(desde PowerShell):

```powershell
scp pi@raspberry-servidor.local:~/TP2_OPC/pki/own/servidor_cert.der .
scp servidor_cert.der pi@raspberry-cliente.local:~/TP2_OPC/pki/
```

El certificado del **cliente** no se copia todavía al servidor: la Parte 4 empieza mostrando el
rechazo (CONSIGNA.md §4.7-4.8).

**Secretos del usuario OPC UA** (consigna 4.9). Elegir una clave de 12 caracteres o más.

RPi 1:

```bash
python generar_hash.py                           # pide la clave; imprime scrypt:...
install -m 600 /dev/null ~/.pdci-t2.env && nano ~/.pdci-t2.env
```
```
OPCUA_USUARIO=operador
OPCUA_CLAVE_HASH=scrypt:131072:8:1:<sal>:<hash>
```

RPi 2: `install -m 600 /dev/null ~/.pdci-t2.env && nano ~/.pdci-t2.env`
```
OPCUA_CLIENTE_USUARIO=operador
OPCUA_CLIENTE_CLAVE=<la clave>
```

El servidor guarda solo el hash; el archivo vive fuera de la carpeta del trabajo y con permisos 600.
**[SEC]** Ninguno de los dos archivos va al repositorio, al informe ni a una captura de pantalla.

## 7. Sincronizar relojes (antes de medir latencias)

La latencia entre placas se mide comparando horas (consigna 3.4): los relojes tienen que coincidir
mejor que lo medido. La RPi 1 es servidor NTP por `eth0`:

```bash
# RPi 1
echo -e "allow 192.168.10.0/24\nlocal stratum 8" | sudo tee /etc/chrony/conf.d/pdci-t2.conf
sudo systemctl restart chrony
# RPi 2
echo "server 192.168.10.1 iburst prefer" | sudo tee /etc/chrony/conf.d/pdci-t2.conf
sudo systemctl restart chrony && sleep 20 && chronyc tracking     # anotar "System time"
```

## 8. Ejecutar desde cero

Orden: servidor → (UaExpert) → cliente. Cada programa se detiene con **Ctrl+C**, que cierra la
sesión de forma ordenada (CloseSession y CLO).

```bash
# RPi 1
cd ~/TP2_OPC && ./iniciar.sh servidor.py
# RPi 2
cd ~/TP2_OPC && ./iniciar.sh cliente_suscripcion.py      # Modo B  (o cliente.py para el Modo A)
```

Salida esperada del servidor: tres endpoints (`None`, `Sign`, `SignAndEncrypt`), `ns=1`, y una
línea `[S7]` cada 0,5 s. Del cliente: `[C1] Sesion activa`, los parámetros revisados `[C3]` y
líneas `[C6]` con rampa generada, recibida y `SourceTimestamp`.

| Opción | Programa | Para qué (consigna) |
|---|---|---|
| `--rampa-detenida` | servidor | Captura de KeepAlive (3.4) |
| `--sin-escritura` | clientes | Captura de KeepAlive sin Writes intercalados (3.4) |
| `--seguridad Sign` / `SignAndEncrypt` | clientes | Modos de seguridad (4.7) |
| `--anonimo` | clientes | Mostrar que el anónimo no puede escribir (4.9) |
| `--gamma` | todos | Corrección gamma del LED PWM (3.7, opcional) |

Prueba funcional rápida: pulsador RPi 1 → LED digital RPi 2; rampa sierra → LED PWM RPi 2;
pulsador RPi 2 → LED digital RPi 1; rampa triangular → LED PWM RPi 1.

## 9. Probar en la PC, sin placas

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install asyncua==2.1.0 gpiozero==2.0.1
python versiones\v2-correccion-python\prueba_local.py
```

Levanta el servidor y los clientes reales con GPIO simulado sobre 127.0.0.1 y hace 50
verificaciones (modelo, rampa, StatusCodes, usuarios y roles, certificados, Modo A y Modo B en
None y SignAndEncrypt, consola). Resultado al 2026-10-20: **50/50**. Lo que **no** reemplaza:
tiempos, latencias y tramas reales del banco.

## 10. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Faltan .../servidor_cert.der` al arrancar el servidor | Certificados no generados | §6 |
| `ATENCION: falta OPCUA_CLAVE_HASH` | No se cargó `~/.pdci-t2.env` | Arrancar con `./iniciar.sh`; revisar el archivo |
| Cliente: `Write ... rechazado: BadUserAccessDenied` | Sesión anónima (sin credenciales o `--anonimo`) | `~/.pdci-t2.env` de la RPi 2 |
| Cliente Sign/SignAndEncrypt: `BadCertificateUntrusted` | Certificado del cliente no confiado | CONSIGNA.md §4.7-4.8 |
| UaExpert rechazado con `BadCertificateUntrusted` | UaExpert presenta su certificado | Confiarlo igual que al cliente: de `pki/rechazados/` a `pki/trusted/` |
| `BadCertificateUriInvalid` | URI del certificado ≠ ApplicationUri | Regenerar con `generar_certificados.py` (borrar `pki/own/`) |
| `gpiozero` usa `NativeFactory` | Falta lgpio en el entorno | §4 |
| Pulsador siempre en 0 | Patas del pulsador del mismo lado | 3,3 V y GPIO17 en lados opuestos |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | microSD regrabada | `ssh-keygen -R raspberry-servidor.local` |
| `scp` no encuentra el archivo / `source` no reconocido | Comando en la máquina equivocada | `scp` en PowerShell de la PC; `source` dentro de SSH |

Apagado: `sudo poweroff` y esperar antes de quitar la alimentación.
