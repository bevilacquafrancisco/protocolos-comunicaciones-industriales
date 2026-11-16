# 11 · Actualización a la v2 y arranque rápido en cualquier red

**Para quién:** quien ya armó el banco una vez con las etapas 01 a 08 y ahora tiene que cargar la v2
y levantar el sistema completo, en casa, en el laboratorio o con el celular.

**Qué trae la v2** (ADR-028 y ADR-029):

| Cambio | Dónde corre | Hay que cargarlo en |
|---|---|---|
| Host Application nueva: ingreso con usuario y contraseña, 5 pestañas, tramas reales, CRC paso a paso, tiempos y **alarmas con recuperación** | Navegador | GitHub Pages (enlace público) o la notebook |
| Métricas de diagnóstico MODBus (tramas TX/RX y latencia) y reconexión OPC UA cada ≤ 5 s | Edge Node (notebook) | Notebook: solo actualizar el código |
| Botones «Convertir en desconocido» y «Volver a dispositivo 1» | Dashboard de Node-RED | Raspberry Pi |
| Registro de configuración `Config/Perfil` (0x0F00): el perfil se cambia sin jumper | ESP32 | ESP32, con Thonny: `config.py` y `main.py` |
| `scripts\banco.ps1`: verificar, poner en hora y abrir las ventanas | Notebook | Notebook |
| SSH y túnel por el cable: el banco no depende de la Wi-Fi | Raspberry Pi (`ufw`) y notebook (IP fija) | Una regla de `ufw` y la IP fija |

**Idea central para que ande en cualquier red:** las tres placas se hablan **solo por cables**: RS-485
entre el ESP32 y la Raspberry, y Ethernet entre la Raspberry y la notebook. La Wi-Fi solo le da
internet a la notebook, para que el Edge Node llegue al broker. La Raspberry no necesita Wi-Fi para
funcionar. La página la abren los profesores desde GitHub Pages, en su propia red.

```
 ESP32 ──RS-485── Raspberry Pi ──cable 192.168.10.1 ↔ .2── Notebook ──Wi-Fi (cualquiera)── internet ── EMQX
                                                                                             └── GitHub Pages ── profesores
```

---

## 1. Configuración de una sola vez

### 1.1 Broker EMQX (consola web)

| Qué | Cómo | Por qué |
|---|---|---|
| **Cambiar la contraseña de `host_app`** | *Access Control → Authentication*, editar `host_app`, nueva clave generada con `py -3.11 -c "import secrets; print(secrets.token_urlsafe(18))"` | Estuvo dentro del `config.js` de la v1, que el navegador descarga |
| **Un usuario por profesor** (por ejemplo `prof_apellido`) | *Authentication → Add*. Después, en *Authorization → Username*, las **mismas 4 reglas** que `host_app` (02 §3.2), con ese usuario | Cada uno entra con lo suyo; se revoca uno sin tocar a los demás |
| Revisar que la regla *Deny* `#` de *All Users* siga cargada | *Authorization → All Users* | Sin ella, EMQX permite todo |

### 1.2 Notebook (PowerShell **como administrador**, una sola vez)

La IP fija del cable es **permanente**. Si la borraste con el 10 §4 de la versión anterior, volvé a
ponerla:

```powershell
Get-NetAdapter | Format-Table Name, InterfaceDescription, Status        # el nombre de la placa Ethernet
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.10.2 -PrefixLength 24
```

Sin `-DefaultGateway`: internet sigue por la Wi-Fi.

Archivos de configuración de la notebook:

| Archivo | Qué revisar |
|---|---|
| `tarea-3\.env` | Sin cambios respecto de la v1. Si cambiaste la clave de `host_app`, actualizá `MQTT_CLAVE_HOST`, que la usa `host_comandos.py` |
| `tarea-3\hmi-web\config.js` | **Borrar la línea `clave`**. Solo queda la `url` y los identificadores |
| `C:\Users\<usuario>\.ssh\config` | La entrada de 01 §3 tiene que incluir `192.168.10.1` en la línea `Host` |

### 1.3 Raspberry Pi: SSH por el cable (una sola vez)

Esta vez se entra **por la Wi-Fi**, como antes: la placa tiene que estar en una red que conozca, por
ejemplo el celular. Desde ahí se habilita SSH por el cable, solo desde la notebook:

```powershell
ssh pdci@rpi-pdci-t3.local
```

```bash
sudo ufw allow in on eth0 from 192.168.10.2 to any port 22 proto tcp
sudo ufw status verbose          # tienen que figurar: 22 por wlan0, 22 por eth0 desde .2, 4840 por eth0
exit
```

Desde ahora, con el cable conectado: `ssh pdci@192.168.10.1`, en cualquier red.

**Opcional: más redes Wi-Fi en la Raspberry.** Solo hace falta para instalar paquetes. Cada red se
guarda y la placa se conecta sola a la que encuentre:

```bash
sudo nmcli device wifi connect "NOMBRE-DE-LA-RED" --ask      # pide la clave sin mostrarla
nmcli connection show                                       # las redes guardadas
```

### 1.4 GitHub Pages: el enlace para los profesores

1. **El repositorio tiene que estar en GitHub con la v2.** Hoy la v2 está en la rama local
   `feat/hmi-v2`, **sin subir**. Cuando la valides en el banco:
   ```powershell
   git switch develop; git merge --no-ff feat/hmi-v2; git push origin develop
   git switch main;    git merge --no-ff develop;     git push origin main
   ```
2. **Pages en un repositorio privado necesita GitHub Pro.** Es gratis con el *GitHub Student
   Developer Pack*. Si el repositorio es público, no hace falta. Ojo: hacerlo público publica
   **todo** el repositorio. No tiene secretos, porque `.env`, `config.js` y las PKI están en
   `.gitignore`, pero revisalo antes.
3. En GitHub, en el repositorio: *Settings → Pages → Source:* **GitHub Actions**.
4. *Settings → Secrets and variables → Actions → **Variables** → New repository variable*:
   - `HMI_BROKER_URL` = `wss://v3161995.ala.us-east-1.emqxsl.com:8084/mqtt`
   - *(opcional)* `HMI_USUARIO_SUGERIDO`: un usuario que aparece precargado. **Nunca** una contraseña.
5. Un `push` a `main` que toque `tarea-3/hmi-web/` publica solo. Si no, se publica a mano desde
   *Actions → Host Application en GitHub Pages → Run workflow*.
6. El enlace queda en *Settings → Pages*: `https://bevilacquafrancisco.github.io/protocolos-comunicaciones-industriales/`.
   Para que `banco.ps1 iniciar` lo muestre: `setx PDCI_HMI_URL "<ese enlace>"`.

---

## 2. Cargar los programas nuevos

### 2.1 Notebook

```powershell
cd "<ruta al repositorio>"
git switch feat/hmi-v2                # o main, después del merge
cd tarea-3
py -3.11 firmware\esclavo-modbus\test\correr_todo.py        # TODO OK
cd gateway-sparkplug; .venv\Scripts\python -m pytest -q; cd ..   # 62 passed
cd hmi-web; npm test; cd ..                                     # 25 pass
cd edge-nodered; npx jest; cd ..                                # 179 passed
```

No hay dependencias nuevas, ni de Python ni de Node: alcanza con el código.

### 2.2 ESP32 (Thonny, con el ESP32 por USB)

Según [03-esp32.md](03-esp32.md) §3, subir **solo** estos dos archivos a la raíz del ESP32. La
carpeta `lib/modbus_slave` no cambió.

| Archivo de la PC | Destino en el ESP32 |
|---|---|
| `tarea-3\firmware\esclavo-modbus\src\config.py` | `/config.py` |
| `tarea-3\firmware\esclavo-modbus\src\main.py` | `/main.py` |

Reiniciar con el botón EN. La consola tiene que mostrar, dentro del mapa, la línea
`holding_registers 0x0F00 Config/Perfil 1..2`. **Quitar el puente de GPIO 13 a GND**, si estaba:
ya no hace falta.

### 2.3 Raspberry Pi (por el cable)

En la **notebook**, desde la raíz del repositorio y con todo commiteado:

```powershell
git status                                                     # sin cambios pendientes
git archive --format=tar -o $env:TEMP\pdci-t3.tar HEAD tarea-3
scp $env:TEMP\pdci-t3.tar pdci@192.168.10.1:
ssh pdci@192.168.10.1
```

En la **Raspberry** (la misma ventana, ya dentro por SSH):

```bash
git get-tar-commit-id < ~/pdci-t3.tar                      # anotar el commit
rm -rf ~/pdci-t3 ~/tarea-3 && tar -xf ~/pdci-t3.tar -C ~ && mv ~/tarea-3 ~/pdci-t3
cd ~/pdci-t3/edge-nodered
npm ci --omit=dev                                          # el lockfile no cambió, pero la carpeta es nueva
PDCI_T3_USERDIR=/home/pdci/.pdci-t3 node generar_flujos.js # regenera los flujos en la carpeta de datos
sudo systemctl restart pdci-t3-nodered
journalctl -u pdci-t3-nodered -n 30 --no-pager             # "servidor OPC UA en opc.tcp://..."
exit
```

Los secretos (`/etc/pdci-t3-nodered.env`) y la PKI (`~/.pdci-t3/opcua-pki`) **no se tocan**: siguen
valiendo, y la confianza OPC UA con la notebook se conserva.

---

## 3. Arranque en cada sesión (5 minutos, cualquier red)

### 3.1 Conexiones físicas, con todo apagado

1. ESP32 ↔ bus RS-485 ↔ adaptador USB-RS485 ↔ Raspberry, con **GND común** (06).
2. Cable Ethernet Raspberry ↔ notebook.
3. Encender: ESP32 (USB) y Raspberry (fuente oficial). Esperar ~1 min a que arranque: el servicio
   de Node-RED se levanta solo.
4. Conectar la notebook a **cualquier** Wi-Fi con internet: la de casa, la del laboratorio o el
   celular.

### 3.2 Ventanas de PowerShell

| Ventana | Cómo se abre | Qué corre | Se cierra con |
|---|---|---|---|
| **1 · Control** | La abrís vos, en `tarea-3` | `banco.ps1 verificar`, `hora`, `iniciar` | `exit` |
| **2 · Edge Node** | La abre `banco.ps1 iniciar` | El cliente OPC UA y el Edge Node Sparkplug B | **Ctrl+C** (publica el NDEATH) |
| **3 · Túnel al Dashboard** | La abre `banco.ps1 iniciar` | `ssh -N -L 1880:...` por el cable | Ctrl+C |
| 4 · Observador *(opcional)* | `banco.ps1 iniciar -Observador` | Archiva los mensajes en `docs\capturas\banco\` | Ctrl+C |
| 5 · Web local *(solo sin GitHub Pages)* | `banco.ps1 web` | `servir.js --lan` | Ctrl+C |

Solo la **ventana 1** se escribe a mano. Las demás las abre el script.

**Ventana 1 · Control:**

```powershell
cd "<ruta al repositorio>\tarea-3"
powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 verificar
```

Todo tiene que dar `[ OK ]`:

| Línea | Si da FALLA |
|---|---|
| IP fija 192.168.10.2 en el cable | Paso 1.2 |
| Cable Ethernet (ping) | Cable suelto o Raspberry apagada |
| Servidor OPC UA (4840) | Servicio detenido: `ssh -t pdci@192.168.10.1 "sudo systemctl restart pdci-t3-nodered"` |
| SSH por el cable | Paso 1.3 |
| Hora de la Raspberry | `banco.ps1 hora` (pide la clave de sudo de `pdci` una vez) |
| Internet hacia el broker (8883) | Esa Wi-Fi bloquea el puerto: usar el celular |

Después:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 hora          # solo si la hora dio FALLA
powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 iniciar -Observador
```

### 3.3 Navegador

| Qué | Dirección | Ingreso |
|---|---|---|
| **Host Application** | El enlace de GitHub Pages (1.4), o `http://localhost:8080` con `banco.ps1 web` | Usuario del broker y su contraseña |
| **Dashboard de Node-RED** | `http://localhost:1880/dashboard` | Ninguno: llega por el túnel SSH |
| Celular de un profesor | El enlace de GitHub Pages, desde **cualquier** red | Su usuario del broker |

---

## 4. Prueba integral (10 minutos)

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Entrar a la Host Application | Las 4 capas en ✔ y sin alarmas |
| 2 | Pulsador y potenciómetro | Cambian en la web y en el Dashboard |
| 3 | LED digital y PWM desde la web | CONFIRMADO; el recorrido del comando y la tabla de tiempos se completan |
| 4 | Pestaña MODBus RTU | Tramas reales con CRC ✔ y el cálculo paso a paso |
| 5 | Pestañas OPC UA y Sparkplug B | Atributos de los nodos; payload decodificado byte por byte |
| 6 | Celular de un profesor | Entra con su usuario; con una contraseña mala, la pantalla de ingreso lo dice |

## 5. Fallas para la defensa

En todas, la web muestra una **alarma** que dice qué falló, desde cuándo y qué revisar. Al
resolverse aparece **RECUPERADO** con la duración, sin tocar nada.

| Falla | Cómo provocarla | Qué se ve | Recuperación |
|---|---|---|---|
| **Cable Ethernet** | Desenchufar el cable de la notebook | Alarma «Enlace OPC UA · cable Ethernet» en unos segundos (watchdog de 1 s + espera de 4 s). OPC UA en ERROR, MODBus SIN DATOS, dispositivo OBSOLETO (DDEATH). El Dashboard sigue andando | Volver a enchufar: la sesión se retoma sola, reintentando cada ≤ 5 s, y llega un DBIRTH. El túnel SSH se corta: Ctrl+C y `banco.ps1 iniciar` de nuevo |
| **Bus RS-485** | Desconectar A o B (o el ESP32) | Unos 2 s después: alarma «Bus RS-485 · ESP32», DEVICE NOT REACHED, DDEATH, controles bloqueados | Reconectar: el maestro sigue preguntando, DONE, DBIRTH |
| **Esclavo desconocido** | Dashboard → *Prueba* → **Convertir en desconocido** | El ESP32 responde y cambia de Unit ID, baud y mapa: alarma del bus, DEVICE NOT REACHED | *Descubrimiento* → aplicar lo encontrado (I-04). Para volver: **Volver a dispositivo 1**, o el botón EN del ESP32 + «Restaurar fábrica» |
| **Edge Node** | Ctrl+C, o cerrar su ventana | Alarma «Edge Node» (NDEATH); todo OBSOLETO | Relanzarlo: `banco.ps1 iniciar`, o en su carpeta `.\.venv\Scripts\python src\sparkplug_edge_node.py`. NBIRTH con `bdSeq` + 1 |
| **Internet de la notebook** | Cortar la Wi-Fi | Unos 15 s: NDEATH por keepalive (web en otra red) | Volver a conectar: el Edge Node reconecta (retroceso de hasta 30 s) |

Los tiempos son los **esperados por diseño**. Los medidos en el banco se anotan en
`resultados-pruebas.md` (09 §5), con la fecha.

## 6. Apagar

1. Ventana 2 (Edge Node): **Ctrl+C**. Ventanas 3 y 4: Ctrl+C.
2. `ssh -t pdci@192.168.10.1 "sudo poweroff"` y esperar a que el LED verde deje de parpadear.
3. Desenchufar el ESP32.

La IP fija de la notebook **se deja**.

---

## 7. Lo que tenés que configurar vos (resumen)

| Dónde | Qué | Paso |
|---|---|---|
| EMQX | Nueva clave para `host_app`; un usuario por profesor con las 4 reglas de `host_app` | 1.1 |
| Notebook | IP fija 192.168.10.2 en Ethernet (permanente) | 1.2 |
| Notebook | Borrar `clave` de `hmi-web\config.js`; actualizar `MQTT_CLAVE_HOST` en `.env` si cambió | 1.2 |
| Raspberry | Regla de `ufw` para SSH por `eth0` desde 192.168.10.2 | 1.3 |
| GitHub | Subir la v2 a `main`; Pages con *GitHub Actions*; variable `HMI_BROKER_URL`; Pro o repositorio público | 1.4 |
| ESP32 | Subir `config.py` y `main.py`; quitar el puente de GPIO 13 | 2.2 |
| Raspberry | Copiar la v2, regenerar los flujos, reiniciar el servicio | 2.3 |
