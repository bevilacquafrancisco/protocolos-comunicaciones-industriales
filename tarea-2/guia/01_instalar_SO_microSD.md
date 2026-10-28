# 01 — Instalar el sistema operativo en las microSD

**Paso 1 de 4** · [Índice](README.md) · Siguiente → [02 — Cargar los programas por SSH](02_cargar_programas_SSH.md)

Deja cada Raspberry Pi 4 con Raspberry Pi OS, conectada a una Wi-Fi y accesible por SSH desde la PC.
Se hace **dos veces**, una por placa. Tiempo: ~15 min por tarjeta + ~20 min de actualización.

Convenciones: `PC>` = PowerShell en Windows · `pi$` = terminal SSH en la Raspberry.

---

## 1. Qué queda al final

| | RPi 1 · servidor | RPi 2 · cliente |
|---|---|---|
| microSD | **32 GB** (etiqueta "SERVIDOR") | **16 GB** (etiqueta "CLIENTE") |
| Hostname | `raspberry-servidor` | `raspberry-cliente` |
| Usuario | `pi` (contraseña propia de cada placa) | `pi` |
| SSH | solo con clave pública | ídem |
| `wlan0` | Wi-Fi (DHCP): SSH, internet, UaExpert | ídem |
| `eth0` | se configura en la Parte 1 ([04 §1](04_resolucion_consignas.md#parte-1--red-ethernet-punto-a-punto)) | ídem |

Las dos tarjetas sirven para cualquiera de las placas (el sistema Lite ocupa < 3 GB). La asignación
fija es solo para no confundirlas: **la tarjeta define la identidad de la placa** (hostname, IP,
certificados).

## 2. Materiales

| Elemento | Detalle |
|---|---|
| 2 × Raspberry Pi 4 | Con disipadores si los tienen |
| 2 × microSD | 32 GB y 16 GB, ya respaldadas. **Se borran por completo** |
| Lector de microSD | En la PC o USB |
| 2 × fuente USB-C | **5,1 V / 3 A** (oficial). Un cargador de celular común provoca reinicios por baja tensión |
| PC | Windows 10/11 con [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (libre) y OpenSSH (incluido en Windows) |
| Celular | Para el hotspot (§3) |

## 3. Elegir la red Wi-Fi

La placa no tiene pantalla: la Wi-Fi se graba en la microSD **antes** del primer arranque, y esa red
tiene que **existir donde se encienda**. Además, la PC tiene que estar **en la misma red** (SSH y
UaExpert).

| ¿Dónde hacen el primer arranque? | Red a grabar con Imager | Después (§7) agregar |
|---|---|---|
| **En casa** (tienen las placas) | Wi-Fi de casa (no gasta datos en la actualización) | Hotspot del celular y Wi-Fi del laboratorio |
| **Solo en el laboratorio** | **Hotspot del celular** | Wi-Fi de casa, si la van a usar |

**Recomendación:** que el **hotspot del celular** quede siempre configurado: viaja con ustedes, la
controlan y no tiene aislamiento entre clientes. El día de la defensa es la red más confiable.

| Red | Funciona si… | No funciona si… |
|---|---|---|
| Hotspot del celular | WPA2-Personal; **2,4 GHz** (Android: *Banda 2,4 GHz*; iPhone: *Maximizar compatibilidad*); nombre sin tildes ni espacios | Está apagado o el celular bloquea la pantalla y corta el hotspot (desactivar "apagar si no hay dispositivos") |
| Wi-Fi de casa | Es WPA2/WPA3-Personal | — (solo existe en casa) |
| Wi-Fi del laboratorio | Pide **solo una clave** (WPA2-Personal) y la PC ve a otros equipos | Pide **usuario y contraseña** o un portal web (Enterprise/cautivo), o **aísla clientes** |

Prueba rápida de la Wi-Fi del laboratorio: conectar la PC y un celular a esa red y hacer
`PC> ping <IP del celular>`. Si no responde, aísla clientes: la PC tampoco va a ver a la Raspberry.
Usar el hotspot.

## 4. Clave SSH (una vez por integrante, en su propia PC)

```powershell
PC> ssh-keygen -t ed25519 -C "francisco@pc"     # Enter en la ruta; poner una frase de paso
PC> Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub   # esta línea se pega en Imager
```

- `id_ed25519.pub` es **pública**: se puede copiar. `id_ed25519` es **privada**: nunca sale de la PC.
- Ed25519 y no RSA: claves cortas, rápidas y sin parámetros débiles (recomendación de OpenSSH desde
  la versión 6.5).
- Las claves de los demás integrantes se agregan después: [02 §3](02_cargar_programas_SSH.md#3-usuarios-y-claves-ssh-del-grupo).

## 5. Grabar cada microSD con Raspberry Pi Imager

1. Insertar **una sola** microSD en la PC. Desconectar otros pendrives o discos USB.
2. **Dispositivo:** *Raspberry Pi 4*.
3. **Sistema operativo:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**.

   | Versión que van a presentar | Imagen |
   |---|---|
   | **v2 (recomendada)** o v1 — Python | Raspberry Pi OS Lite (64-bit), la actual |
   | v3 — Node-RED | **Raspberry Pi OS (Legacy) Lite (64-bit), Bookworm**: `pigpio` no existe en la versión actual |

   *Lite* (sin escritorio): todo se maneja por SSH; deja ~250 MB de RAM libres y menos software
   expuesto.
4. **Almacenamiento:** la microSD. Verificar la capacidad (32 GB o 16 GB): **se borra entera**.
5. **Siguiente → Editar ajustes / Personalización** (según la versión de Imager):

   | Pestaña | Campo | RPi 1 (32 GB) | RPi 2 (16 GB) |
   |---|---|---|---|
   | General | Hostname | `raspberry-servidor` | `raspberry-cliente` |
   | General | Usuario / contraseña | `pi` / contraseña **A** | `pi` / contraseña **B** |
   | General | Wi-Fi: SSID y clave | la red elegida en §3 (exacta: distingue mayúsculas) | la misma |
   | General | **País de la Wi-Fi** | `AR` | `AR` |
   | General | Zona horaria / teclado | `America/Argentina/Cordoba` / `latam` | ídem |
   | Servicios | SSH | **Habilitar** → *Permitir solo autenticación con clave pública* → pegar `id_ed25519.pub` | ídem |

   - **Hostnames distintos:** con el mismo nombre, `.local` resolvería a cualquiera de las dos.
   - **País `AR`:** fija el dominio regulatorio de radio. Sin él, la Wi-Fi queda bloqueada (*rfkill*).
   - **[SEC] Contraseñas:** distintas en cada placa, guardadas en un gestor (Bitwarden, libre) y
     **nunca** escritas en guías, informe ni capturas. La contraseña vieja quedó publicada en el
     `.docx` de v1: las placas nuevas no la usan.
   - **Solo clave pública:** desactiva el login por contraseña en SSH; un barrido automático en la
     Wi-Fi del laboratorio no puede adivinar nada.
6. **Guardar → Sí → Sí.** Esperar *Escritura exitosa* (graba y verifica).
7. Si Windows dice *"Debe formatear el disco"*: **Cancelar**. Es la partición Linux; formatearla
   borra el sistema.
8. Comprobar que la personalización se aplicó: retirar y volver a insertar la tarjeta, abrir la
   unidad **`bootfs`**. Tiene que haber `user-data` y `network-config` (imagen actual) o
   `firstrun.sh` (Bookworm). **Si no hay ninguno, volver a grabar**: es la causa número uno de "la
   placa no aparece".
9. Expulsar, **etiquetar la tarjeta** y repetir con la otra.

## 6. Primer arranque y uso básico de la Raspberry

1. Placa **desenchufada**. microSD en la ranura de abajo, contactos hacia la placa.
2. Hotspot encendido (o la red elegida al alcance) y la PC conectada a **esa misma red**.
3. Enchufar la fuente y esperar **3 minutos** (agranda la partición y se reinicia una vez).

   | LED | Estado | Significado |
   |---|---|---|
   | Rojo (PWR) | Fijo | Alimentación correcta |
   | Rojo | Parpadea / se apaga | Tensión baja: fuente de 3 A, nada más en los USB |
   | Verde (ACT) | Parpadeo irregular | Leyendo la tarjeta: va bien |
   | Verde | Patrón repetido largo/corto | Error de arranque: volver a grabar ([tabla de códigos](../versiones/v2-correccion-python/ARRANQUE_PENDRIVE.md#9-códigos-de-error-del-led-verde-pi-4)) |

4. Entrar por SSH:

   ```powershell
   PC> ssh pi@raspberry-servidor.local        # la otra: pi@raspberry-cliente.local
   ```

   La primera vez pregunta por la huella del equipo: `yes`. Si `.local` no resuelve: ver la IP en
   el celular (*Hotspot → Dispositivos conectados*) o en el router, y `ssh pi@<IP>`.
5. Comprobar y anotar para el informe:

   ```bash
   pi$ cat /proc/device-tree/model; echo     # Raspberry Pi 4 Model B Rev ...
   pi$ cat /etc/os-release | head -4         # versión de Debian
   pi$ hostname -I                           # IP Wi-Fi (la usa UaExpert en la Parte 2)
   ```

**Reglas de uso (todo el TP):**

| Hacer | Nunca |
|---|---|
| Apagar con `sudo poweroff` y esperar a que el LED verde se apague (~10 s) antes de desenchufar | Desenchufar con la placa encendida: corrompe la microSD |
| Cablear la protoboard **con la placa desenchufada** | Llevar **5 V** (pines 2 y 4) a un GPIO: los GPIO son de **3,3 V** y se dañan |
| Reiniciar con `sudo reboot` | Sacar la microSD con la placa encendida |

## 7. Agregar más redes Wi-Fi (casa, celular, laboratorio)

Con la sesión SSH abierta. La clave se pide sin mostrarse y no queda en el historial:

```bash
pi$ read -rsp "Clave de la Wi-Fi: " K; echo
pi$ sudo nmcli connection add type wifi ifname wlan0 con-name hotspot ssid "NombreDelHotspot" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$K" connection.autoconnect-priority 30; unset K
```

Repetir con `con-name casa` (prioridad 20) y `con-name laboratorio` (prioridad 10). Si están varias
al alcance, NetworkManager elige la de **mayor prioridad**.

```bash
pi$ nmcli -f NAME,TYPE,AUTOCONNECT-PRIORITY connection show     # comprobar que existan
```

Alternativa interactiva: `sudo nmtui` → *Edit a connection → Add → Wi-Fi*. **No activar** una red
nueva desde la misma sesión SSH por Wi-Fi: se corta la conexión. Basta con que el perfil exista.

## 8. Actualizar e instalar los paquetes base (las dos placas)

Consumo: 150–550 MB. Hacerlo en casa o con la conexión compartida de la PC por cable
([ARRANQUE_PENDRIVE §6.2](../versiones/v2-correccion-python/ARRANQUE_PENDRIVE.md#62-conexión-compartida-de-windows-la-pc-le-da-ip-e-internet-a-la-pi))
si el hotspot tiene pocos datos.

```bash
pi$ sudo apt update && sudo apt full-upgrade -y
pi$ sudo apt install -y python3-venv python3-gpiozero python3-lgpio tcpdump ethtool chrony tmux git
pi$ sudo reboot
```

| Paquete | Para qué | Consigna |
|---|---|---|
| `python3-venv`, `python3-gpiozero`, `python3-lgpio` | Entorno de los programas y GPIO (desde apt: no se compila `lgpio`) | 2, 3 |
| `tcpdump` | Capturar en `eth0` | 3.4, 4.1 |
| `ethtool` | Velocidad, dúplex y autonegociación | 1.3 |
| `chrony` | Sincronizar relojes para medir latencia | 3.4 |
| `tmux` | Sesiones que sobreviven a un corte de SSH ([02 §5](02_cargar_programas_SSH.md#5-sesiones-ssh-varias-terminales-y-tmux)) | — |
| `git` | Opción C de carga ([02 §4](02_cargar_programas_SSH.md#4-cargar-los-programas)) | — |

Versión Node-RED (v3): seguir [su guía §6](../versiones/v3-node-red/node-red/README.md#6-actualizar-el-sistema-e-instalar-los-paquetes-base) en lugar de esta tabla.

## 9. Si la placa no aparece

| Síntoma | Causa | Solución |
|---|---|---|
| No responde en ninguna red | Imager no aplicó la personalización | §5 paso 8; regrabar |
| Aparece en casa, no en el laboratorio | La red de casa no existe allá | Hotspot; §7 antes de salir de casa |
| La PC no la ve en la Wi-Fi del laboratorio | Aislamiento de clientes | Hotspot |
| `Could not resolve hostname …local` | mDNS bloqueado | Usar la IP (celular/router) |
| `Permission denied (publickey)` | Otra PC u otra clave | La PC cuya clave se pegó; [02 §3](02_cargar_programas_SSH.md#3-usuarios-y-claves-ssh-del-grupo) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Tarjeta regrabada con el mismo nombre | `PC> ssh-keygen -R raspberry-servidor.local` |
| Nada funciona por Wi-Fi | — | Entrar por cable Ethernet PC ↔ Pi: [ARRANQUE_PENDRIVE §6](../versiones/v2-correccion-python/ARRANQUE_PENDRIVE.md#6-acceso-y-diagnóstico-por-cable-ethernet-pc--pi) (vale igual para microSD) |

## ✅ Listo para seguir si…

- [ ] Las dos tarjetas están etiquetadas y cada placa responde a `ssh pi@<hostname>.local`.
- [ ] `hotspot` (y, si corresponde, `casa` / `laboratorio`) figura en `nmcli connection show`.
- [ ] `apt full-upgrade` e `apt install` terminaron sin errores en las dos.
- [ ] Modelo, versión de Debian e IP Wi-Fi anotados.

Siguiente → [02 — Cargar los programas por SSH](02_cargar_programas_SSH.md)
