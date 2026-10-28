# 02 — Cargar los programas por SSH

**Paso 2 de 4** · ← [01 — Instalar el SO](01_instalar_SO_microSD.md) · [Índice](README.md) · Siguiente → [03 — Conexionado eléctrico](03_conexionado_electrico.md)

Deja en cada placa la versión elegida del programa, sus dependencias, los certificados y los
secretos. En una Raspberry Pi no se "flashea" firmware como en un microcontrolador: el "firmware" del
TP son **los programas Python** que se copian por SSH y se ejecutan sobre Linux.

Requisito: [01](01_instalar_SO_microSD.md) terminado (las dos placas responden por SSH).
`PC>` = PowerShell en la carpeta del repositorio · `pi$` = SSH en la placa · `RPi1$` / `RPi2$` = en
esa placa.

---

## 1. Elegir la versión

| Versión | Carpeta en el repo | Carpeta en la placa | Cuándo usarla |
|---|---|---|---|
| **v2 — corrección** | [versiones/v2-correccion-python/](../versiones/v2-correccion-python/) | `~/TP2_OPC` | **Entrega y defensa**: cubre todas las consignas |
| v1 — original (Agustina) | [versiones/v1-original-agustina/](../versiones/v1-original-agustina/) | `~/TP2_OPC_original` | Mostrar la evolución; respaldo de las Partes 1-3. No cubre 4.7-4.9 ([detalle](../versiones/v1-original-agustina/README.md#qué-cubre-y-qué-no)) |
| v3 — Node-RED | [versiones/v3-node-red/](../versiones/v3-node-red/) | `~/pdci-t2` | Requiere otra imagen (Bookworm): seguir [su guía](../versiones/v3-node-red/node-red/README.md#8-instalar-node-red) desde el §8 |

v1 y v2 pueden estar cargadas a la vez (mismo entorno Python, carpetas distintas). Se ejecuta **una
sola** por placa en cada momento.

## 2. Configurar SSH en la PC (una vez por integrante)

**Alias de conexión.** Crear `~/.ssh/config`:

```powershell
PC> $f = "$env:USERPROFILE\.ssh\config"; if (-not (Test-Path $f)) { New-Item $f -ItemType File | Out-Null }; notepad $f
```

```sshconfig
Host rpi1
    HostName raspberry-servidor.local
Host rpi2
    HostName raspberry-cliente.local
# Por cable PC <-> placa, con la PC en 192.168.10.100/24 (solo diagnóstico)
Host rpi1-cable
    HostName 192.168.10.1
Host rpi2-cable
    HostName 192.168.10.2
Host rpi1 rpi2 rpi1-cable rpi2-cable
    User pi
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 15
    ServerAliveCountMax 4
```

Desde ahora: `ssh rpi1`, `scp archivo rpi2:~/`. `ServerAlive*` detecta en ~60 s una sesión muerta
(Wi-Fi caída) en lugar de dejar la terminal colgada. El script de carga (§4) usa estos alias.

**Agente SSH** (para escribir la frase de paso una sola vez por sesión de Windows). PowerShell **como
administrador**, una sola vez:

```powershell
PC> Get-Service ssh-agent | Set-Service -StartupType Automatic; Start-Service ssh-agent
```

Luego, en PowerShell normal: `PC> ssh-add` (pide la frase de paso).

Prueba: `PC> ssh rpi1 hostname` → `raspberry-servidor`; `PC> ssh rpi2 hostname` → `raspberry-cliente`.

## 3. Usuarios y claves SSH del grupo

**Diseño:** un único usuario Linux `pi` por placa y **una clave pública por integrante** en
`~/.ssh/authorized_keys`.

| Opción | Gana | Pierde | Decisión |
|---|---|---|---|
| **Usuario `pi` compartido, una clave por persona** | Los programas, `pki/`, el entorno y los registros están en un solo `$HOME`; cualquiera retoma la sesión del otro | Los registros del sistema muestran "pi", no la persona (el comentario de la clave sí la identifica en `journalctl -u ssh`) | **Elegida**: es un banco de laboratorio de 2-3 personas |
| Un usuario Linux por persona | Trazabilidad individual (no repudio) | Cada uno necesitaría su copia del entorno, `pki/` y grupos `gpio`; más pasos con poco tiempo | Descartada para el TP; recomendada en producción |

**Agregar la clave de otro integrante** (la pública se puede mandar por chat; la privada, nunca). Lo
hace quien ya tiene acceso, **en las dos placas**:

```bash
pi$ echo 'ssh-ed25519 AAAA...resto... agustina@pc' >> ~/.ssh/authorized_keys
pi$ chmod 600 ~/.ssh/authorized_keys
pi$ cut -d' ' -f3 ~/.ssh/authorized_keys          # lista quién tiene acceso
```

Quitar un acceso: borrar su línea con `nano ~/.ssh/authorized_keys`.

**Comprobar que SSH no acepta contraseñas** (Imager lo configura con "solo clave pública"):

```bash
pi$ sudo sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin|pubkeyauthentication)'
# esperado: passwordauthentication no · permitrootlogin without-password · pubkeyauthentication yes
```

Si dice `passwordauthentication yes`, **con otra sesión por clave ya abierta** (para no quedar
afuera):

```bash
pi$ echo "PasswordAuthentication no" | sudo tee /etc/ssh/sshd_config.d/10-solo-clave.conf
pi$ sudo systemctl reload ssh
```

Opcional (cuenta propia por persona): `sudo adduser agustina`, `sudo usermod -aG sudo,gpio agustina`
y su clave en `/home/agustina/.ssh/authorized_keys` (permisos 700 / 600, dueña `agustina`).

## 4. Cargar los programas

Tres formas equivalentes; **A** es la más rápida.

### Opción A — Script desde la PC (recomendada)

```powershell
PC> powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1 -Simular   # ver qué hará
PC> powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1            # v2 a las dos placas
PC> powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1 -Version v1 # v1 a las dos
```

Opciones: `-Placa servidor|cliente` (una sola), `-Servidor pi@<IP>` / `-Cliente pi@<IP>` (sin
alias). `-ExecutionPolicy Bypass` vale solo para esa ejecución: no cambia la política de Windows.
El script ([herramientas/desplegar.ps1](../herramientas/desplegar.ps1)) **no toca** `pki/`,
`registros/` ni `~/.pdci-t2.env`: se puede volver a correr después de cada cambio de código.

### Opción B — `scp` a mano

```powershell
# v2 (desde la raíz del repo)
PC> cd versiones\v2-correccion-python
PC> foreach ($p in "rpi1", "rpi2") { ssh $p "mkdir -p ~/TP2_OPC"; scp (Get-ChildItem *.py).Name requirements.txt iniciar.sh "${p}:TP2_OPC/"; ssh $p "chmod +x ~/TP2_OPC/iniciar.sh" }
PC> cd ..\..

# v1
PC> cd versiones\v1-original-agustina
PC> foreach ($p in "rpi1", "rpi2") { ssh $p "mkdir -p ~/TP2_OPC_original"; scp servidor_ns1.py cliente.py cliente_suscripcion_v2.py "${p}:TP2_OPC_original/" }
PC> cd ..\..
```

### Opción C — `git` en la placa (necesita internet y la rama `develop` subida a GitHub)

```bash
pi$ git clone -b develop https://github.com/AgustinaPeralt/OPC-PCI.git ~/OPC-PCI
pi$ ln -sfn ~/OPC-PCI/versiones/v2-correccion-python ~/TP2_OPC                  # v2
pi$ ln -sfn ~/OPC-PCI/versiones/v1-original-agustina ~/TP2_OPC_original         # v1
pi$ chmod +x ~/TP2_OPC/iniciar.sh
```

Actualizar: `cd ~/OPC-PCI && git pull`. Si `~/TP2_OPC` ya existe como carpeta (opción A o B), no
mezclar: usar la misma opción siempre. Si el repositorio es privado, usar un *token* de **solo
lectura**, nunca la contraseña de GitHub.

## 5. Sesiones SSH: varias terminales y `tmux`

Cada placa necesita al menos **dos terminales**: una con el programa y otra para `tcpdump`, `ip`,
`ss`. Si el programa corre en una SSH común y se corta la Wi-Fi, **el programa muere**. Con `tmux`
sigue corriendo y se retoma.

```bash
pi$ tmux new -s tp          # crear la sesión (la primera vez)
pi$ tmux attach -t tp       # retomarla (después de un corte o desde otra PC)
```

| Teclas (`Ctrl+b` y luego…) | Acción |
|---|---|
| `%` / `"` | Dividir la pantalla vertical / horizontal |
| flechas | Moverse entre paneles |
| `c` / `n` | Ventana nueva / siguiente |
| `d` | Desconectarse **dejando todo corriendo** |
| `[` | Desplazarse por la salida (salir con `q`) |

Disposición sugerida, igual en las dos placas: panel izquierdo = programa (`./iniciar.sh …`), panel
derecho = comandos y capturas. Dos integrantes pueden ver la misma sesión a la vez (`tmux attach`
desde dos PC): útil en la defensa.

Alternativa sin `tmux`: varias pestañas de Windows Terminal, una `ssh rpi1` y otra `ssh rpi2` por
tarea (pero se pierde el programa si se corta la sesión).

## 6. Entorno Python y dependencias (las dos placas; sirve para v1 y v2)

```bash
pi$ python3 -m venv --system-site-packages ~/opcua-env    # ve gpiozero y lgpio instalados con apt
pi$ source ~/opcua-env/bin/activate
pi$ pip install -r ~/TP2_OPC/requirements.txt             # v2: asyncua==2.1.0 (versión probada)
pi$ pip install asyncua==2.1.0                            # v1: no trae requirements.txt; misma versión
pi$ python -c "import asyncua, gpiozero, lgpio; print('OK')"
pi$ pip freeze > ~/TP2_OPC/registros_versiones.txt        # versiones reales, para el informe (v1: ~/TP2_OPC_original/)
```

Con v1 sola no existe `~/TP2_OPC`: usar la segunda línea en lugar de la primera. No instalar
`gpiozero` ni `lgpio` con pip: ya vienen de apt.

`--system-site-packages`: `lgpio` viene compilado desde apt; instalarlo con pip exige compilarlo
(fue el problema de v1). Versión fija (`==2.1.0`): un `pip install asyncua` sin versión podría traer
otra el día de la defensa.

## 7. Certificados y secretos (solo v2)

Necesarios para Sign/SignAndEncrypt (4.7) y usuario/contraseña (4.9). Detalle:
[v2 README §6](../versiones/v2-correccion-python/README.md#6-copiar-los-programas-certificados-y-secretos).

```bash
RPi1$ cd ~/TP2_OPC && source ~/opcua-env/bin/activate && python generar_certificados.py servidor
RPi2$ cd ~/TP2_OPC && source ~/opcua-env/bin/activate && python generar_certificados.py cliente
```

El cliente necesita el certificado **público** del servidor:

```powershell
PC> scp rpi1:TP2_OPC/pki/own/servidor_cert.der $env:TEMP\ ; scp $env:TEMP\servidor_cert.der rpi2:TP2_OPC/pki/
```

El certificado del cliente **no** se copia al servidor todavía: la Parte 4.8 empieza mostrando el
rechazo.

Usuario OPC UA `operador` (clave de 12 caracteres o más, distinta de la de las placas):

```bash
RPi1$ python generar_hash.py                                  # pide la clave, imprime scrypt:...
RPi1$ install -m 600 /dev/null ~/.pdci-t2.env && nano ~/.pdci-t2.env
#   OPCUA_USUARIO=operador
#   OPCUA_CLAVE_HASH=scrypt:...   (la línea impresa)
RPi2$ install -m 600 /dev/null ~/.pdci-t2.env && nano ~/.pdci-t2.env
#   OPCUA_CLIENTE_USUARIO=operador
#   OPCUA_CLIENTE_CLAVE=<la clave>
```

El archivo se lee como un script de shell (`iniciar.sh`): si la clave tiene espacios, `$`, comillas
o `` ` ``, escribirla entre comillas simples (`OPCUA_CLIENTE_CLAVE='…'`). Lo más simple: solo letras,
números, `-` y `_`.

**[SEC]** `pki/own/*_key.pem` (clave privada) y `~/.pdci-t2.env` **no salen de la placa**: ni al repo
(`.gitignore` los excluye), ni al informe, ni a capturas de pantalla. El servidor guarda solo el
hash scrypt.

## 8. Prueba de humo (antes de cablear)

```bash
RPi1$ cd ~/TP2_OPC && ./iniciar.sh servidor.py       # v2: lista 3 endpoints y ns=1; Ctrl+C para salir
RPi1$ cd ~/TP2_OPC_original && source ~/opcua-env/bin/activate && python servidor_ns1.py   # v1
```

Sin protoboard, gpiozero funciona igual (los pines quedan sin carga). El cliente se prueba después
de configurar `eth0` (Parte 1): se conecta a `192.168.10.1`.

| Para ejecutar | v2 | v1 |
|---|---|---|
| Servidor (RPi 1) | `cd ~/TP2_OPC && ./iniciar.sh servidor.py` | `cd ~/TP2_OPC_original && python servidor_ns1.py` |
| Cliente Modo A (RPi 2) | `./iniciar.sh cliente.py` | `python cliente.py` |
| Cliente Modo B (RPi 2) | `./iniciar.sh cliente_suscripcion.py` | `python cliente_suscripcion_v2.py` |
| Detener | `Ctrl+C` (cierra la sesión OPC UA en orden) | `Ctrl+C` |

v1 requiere `source ~/opcua-env/bin/activate` antes; `iniciar.sh` (v2) lo hace solo, carga los
secretos y guarda la salida en `registros/`. Opciones de v2: [v2 README §8](../versiones/v2-correccion-python/README.md#8-ejecutar-desde-cero).

## 9. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `desplegar.ps1 … no está firmado digitalmente` | Política de ejecución | Usar `powershell -ExecutionPolicy Bypass -File …` |
| `ssh: Could not resolve hostname rpi1` | Falta `~/.ssh/config` | §2 |
| `scp` copió dentro de `~/TP2_OPC/TP2_OPC` | Se usó `scp -r` de la carpeta | Usar §4 A o B (copian archivos, no la carpeta) |
| `./iniciar.sh: Permission denied` | Sin permiso de ejecución | `chmod +x ~/TP2_OPC/iniciar.sh` |
| `/usr/bin/env: 'bash\r'` | Fin de línea de Windows | `sed -i 's/\r$//' ~/TP2_OPC/iniciar.sh` |
| `ModuleNotFoundError: asyncua` | Entorno no activado | `source ~/opcua-env/bin/activate` (o usar `iniciar.sh`) |
| `gpiozero` cae en `NativeFactory` | Venv sin `--system-site-packages` | Recrear el venv (§6) |
| `OSError: [Errno 98] Address already in use` | Otro servidor ya en el 4840 | `pkill -f servidor` o cerrar el otro panel de `tmux` |
| `Faltan …/servidor_cert.der` | No se generaron certificados | §7 |

## ✅ Listo para seguir si…

- [ ] `ssh rpi1` y `ssh rpi2` entran sin pedir contraseña de la placa; las claves de todo el grupo están cargadas.
- [ ] La versión elegida está en `~/TP2_OPC` (v2) y/o `~/TP2_OPC_original` (v1) de las dos placas.
- [ ] `python -c "import asyncua, gpiozero, lgpio"` da `OK` en las dos.
- [ ] (v2) `pki/own/` generado en cada placa, `servidor_cert.der` en la RPi 2 y `~/.pdci-t2.env` en las dos.
- [ ] El servidor arranca y muestra sus endpoints.

Siguiente → [03 — Conexionado eléctrico](03_conexionado_electrico.md)
