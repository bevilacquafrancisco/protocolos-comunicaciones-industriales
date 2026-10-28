# Comandos del banco — hoja rápida

[Índice](README.md) · Detalle y justificación de cada consigna: [04_resolucion_consignas.md](04_resolucion_consignas.md)

| Prompt | Dónde se ejecuta |
|---|---|
| `PC>` | PowerShell de Windows, **en la carpeta del repo** (`cd "C:\Users\USER\Documents\Facultad UNRaf\4to año\Pro-Com-Ind\OPC-PCI"`) |
| `RPi1$` | Dentro de la RPi 1 · servidor (`ssh rpi1`) |
| `RPi2$` | Dentro de la RPi 2 · cliente (`ssh rpi2`) |
| `pi$` | En las dos placas |

Tres pestañas de Windows Terminal: **1** `ssh rpi1` · **2** `ssh rpi2` · **3** la PC.

---

## 1. tmux (dentro de cada placa)

| Acción | Comando / teclas |
|---|---|
| Abrir o retomar la sesión | `tmux attach -t tp \|\| tmux new -s tp` |
| Dividir en izquierda \| derecha | `Ctrl+b` → `%` |
| Dividir en arriba / abajo | `Ctrl+b` → `"` |
| Cambiar de panel | `Ctrl+b` → flecha (o clic) |
| Desplazarse en la salida | rueda del mouse · o `Ctrl+b` → `[`, salir con `q` |
| Cerrar un panel | `exit` |
| Salir dejando todo corriendo | `Ctrl+b` → `d` |
| Configuración (una vez) | `printf 'set -sg escape-time 300\nset -g mouse on\n' >> ~/.tmux.conf && tmux kill-server` |

Disposición: **panel izquierdo = programa** · **panel derecho = comandos y capturas**.

## 2. Levantar los programas

Orden: **servidor → cliente**. Detener siempre con `Ctrl+C`: cierra la sesión OPC UA en orden. Nunca dos
servidores a la vez.

### v1 (original)

```bash
pi$    source ~/opcua-env/bin/activate && cd ~/TP2_OPC_original && mkdir -p ~/registros
RPi1$  python -u servidor_ns1.py          2>&1 | tee ~/registros/srv_$(date +%H%M%S).log
RPi2$  python -u cliente.py               2>&1 | tee ~/registros/cliA_$(date +%H%M%S).log   # Modo A · Read cada 100 ms
RPi2$  python -u cliente_suscripcion_v2.py 2>&1 | tee ~/registros/cliB_$(date +%H%M%S).log  # Modo B · suscripción
```

### v2 (corrección: necesaria para KeepAlive, latencia y 4.7 – 4.9)

```bash
pi$    cd ~/TP2_OPC                                     # iniciar.sh activa el entorno y guarda registros/
RPi1$  ./iniciar.sh servidor.py                         # opciones: --rampa-detenida  --gamma
RPi2$  ./iniciar.sh cliente.py                          # Modo A
RPi2$  ./iniciar.sh cliente_suscripcion.py              # Modo B
#      opciones de los clientes: --sin-escritura  --seguridad None|Sign|SignAndEncrypt  --anonimo  --gamma
```

### Cargar o actualizar los programas

```powershell
PC> powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1 -Version v1   # o sin -Version: v2
```

## 3. Copiar la evidencia a la PC

```powershell
PC> scp "rpi2:*.pcapng" evidencia\capturas\
PC> scp -r rpi1:registros evidencia\rpi1\ ; scp -r rpi2:registros evidencia\rpi2\
```

Capturas con nombres que no se pisan: `sudo tcpdump -i eth0 -w ~/captura_X_$(date +%H%M%S).pcapng`.

---

## Parte 1 — Red Ethernet punto a punto

| Consigna | Comando |
|---|---|
| 1.2 IP fija | `RPi1$ sudo nmcli connection modify netplan-eth0 ipv4.method manual ipv4.addresses 192.168.10.1/24 ipv4.gateway "" ipv4.dns "" ipv4.never-default yes ipv6.method disabled connection.autoconnect yes && sudo nmcli connection up netplan-eth0` (RPi 2: `192.168.10.2/24`) |
| 1.2 evidencia | `pi$ nmcli connection show netplan-eth0 \| grep -E "^ipv4\.(method\|addresses\|gateway\|never)"` |
| 1.3 física | `pi$ sudo ethtool eth0` |
| 1.3 enlace | `pi$ ip -br link show eth0` · `pi$ ip neigh show dev eth0` |
| 1.3 red | `pi$ ip addr show eth0` · `RPi1$ ping -c 4 192.168.10.2` · `RPi2$ ping -c 4 192.168.10.1` |
| 1.3 ARP en acción | `RPi2$ sudo ip neigh flush dev eth0; sudo tcpdump -i eth0 -e -n arp -c 2 & sleep 1; ping -c 1 192.168.10.1` |
| 1.4 (con la Parte 3 corriendo) | `RPi2$ ip route` · `ip route get 192.168.10.1` · `ss -tn \| grep 4840` · `sudo timeout 10 tcpdump -i eth0 -n port 4840 \| wc -l` · `sudo timeout 10 tcpdump -i wlan0 -n port 4840 \| wc -l` (= 0) |
| 1.4 desde el servidor | `RPi1$ sudo timeout 10 tcpdump -i wlan0 -n port 4840 and host 192.168.10.2 \| wc -l` (= 0 aunque UaExpert esté conectado) |

## Parte 2 — Servidor y UaExpert

| Consigna | Comando |
|---|---|
| 2.1 servidor | `RPi1$ python -u servidor_ns1.py …` (sección 2) · panel derecho: `ss -tlnp \| grep 4840` → `0.0.0.0:4840` |
| 2.5 IP para UaExpert | `RPi1$ hostname -I` → UaExpert: `opc.tcp://<IP Wi-Fi>:4840`, None / None, Anonymous |
| 2.5 d escribir Cliente.* | **Antes:** `Ctrl+C` del cliente en la RPi 2 (si no, pisa lo que escribe UaExpert) |

## Parte 3 — Cliente e intercambio

| Consigna | Comando |
|---|---|
| 3.1 – 3.3 | Servidor + cliente Modo B (sección 2); filmar las dos placas |
| 3.4 Modo A, 60 s | izq: `RPi2$ python -u cliente.py …` · esperar 5 s · der: `RPi2$ sudo timeout 60 tcpdump -i eth0 -w ~/captura_modo_A.pcapng port 4840` |
| 3.4 Modo B, 60 s | izq: `RPi2$ python -u cliente_suscripcion_v2.py …` · der: `… -w ~/captura_modo_B.pcapng port 4840` |
| 3.4 KeepAlive (solo v2) | `RPi1$ ./iniciar.sh servidor.py --rampa-detenida` · `RPi2$ ./iniciar.sh cliente_suscripcion.py --sin-escritura` · der: `… -w ~/captura_modo_B_quieto.pcapng port 4840` |
| 3.4 tramas y bytes | `PC> & "C:\Program Files\Wireshark\tshark.exe" -r evidencia\capturas\captura_modo_A.pcapng -q -z io,stat,0` |
| 3.4 por servicio | `PC> & "C:\Program Files\Wireshark\tshark.exe" -r <captura> -Y opcua -T fields -e _ws.col.Info \| Group-Object \| Select-Object Count,Name` |
| 3.4 latencia (v2) | Relojes: `RPi1$ echo -e "allow 192.168.10.0/24\nlocal stratum 8" \| sudo tee /etc/chrony/conf.d/pdci-t2.conf && sudo systemctl restart chrony` · `RPi2$ echo "server 192.168.10.1 iburst prefer" \| sudo tee /etc/chrony/conf.d/pdci-t2.conf && sudo systemctl restart chrony && sleep 30 && chronyc tracking` · `PC> python versiones\v3-node-red\herramientas\medir_latencia.py <log_origen> <log_destino>` |
| 3.4 latencia (v1) | Video en cámara lenta (240 fps) de las dos placas; contar cuadros pulsador → LED |
| 3.5 consola | Ya queda en `~/registros/` por el `tee` |
| 3.6 desconexión | Con Modo B corriendo: desenchufar el cable ~5 s, ~20 s y ~45 s; filmar; mirar el registro del cliente |
| 3.6 ruta sin cable | `RPi2$ ip route get 192.168.10.1` (debe seguir por eth0) |
| 3.7 gamma (v2) | `./iniciar.sh servidor.py --gamma` · `./iniciar.sh cliente_suscripcion.py --gamma` |

## Parte 4 — Tramas y seguridad

| Consigna | Comando |
|---|---|
| 4.1 sesión completa | Cliente **detenido** → `pi$ sudo ip neigh flush dev eth0` (las dos) → der: `RPi2$ sudo tcpdump -i eth0 -w ~/captura_none_$(date +%H%M%S).pcapng` → izq: arrancar el cliente, ~15 s, pulsadores → `Ctrl+C` del cliente → 2 s → `Ctrl+C` del tcpdump |
| 4.1 filtro Wireshark | `opcua \|\| arp \|\| tcp.flags.syn==1 \|\| tcp.flags.fin==1` |
| 4.2 diagrama | Wireshark: **Statistics → Flow Graph** → *Limit to display filter* · *TCP Flows* |
| 4.2 GetEndpoints (v1) | `RPi1$ sudo tcpdump -i wlan0 -w ~/captura_getendpoints.pcapng port 4840` y en UaExpert *Add Server* → desplegar |
| 4.4 PublishResponse | Filtro `opcua.servicenodeid.numeric == 829` (los de 204 B) |
| 4.5 Write | Filtros `opcua && frame contains "Cliente.Rampa"` · `opcua && frame contains "Cliente.EstadoPulsador"`; respuesta: clic derecho en RequestId → *Apply as Filter* |
| 4.5 decodificar | Wireshark: *Frame* → *Copy → …as a Hex Stream* · `PC> python versiones\v3-node-red\herramientas\opcua_tramas.py --markdown "<hex>"` (con `--ethernet` si es la trama completa) |
| 4.6 eficiencia | `PC> python versiones\v3-node-red\herramientas\eficiencia_trama.py --ua-bytes 107` |
| 4.7 – 4.8 (v2) | `RPi2$ ./iniciar.sh cliente_suscripcion.py --seguridad Sign` (rechazado) → `RPi1$ openssl x509 -inform DER -in pki/rechazados/*.der -noout -fingerprint -sha256` · `RPi2$ openssl x509 -inform DER -in pki/own/cliente_cert.der -noout -fingerprint -sha256` → `RPi1$ mv pki/rechazados/*.der pki/trusted/cliente_cert.der` → reintentar; luego `--seguridad SignAndEncrypt` |
| 4.8 capturas por modo (v2) | `RPi1$ ./iniciar.sh servidor.py --rampa-detenida` · `RPi2$ ./iniciar.sh cliente.py --seguridad <modo>` · der: `sudo timeout 60 tcpdump -i eth0 -w ~/captura_<modo>.pcapng port 4840` |
| 4.8 latencia por modo | `PC> & "C:\Program Files\Wireshark\tshark.exe" -r evidencia\capturas\captura_sign.pcapng -Y "tcp.port==4840 && tcp.len>0" -T fields -e frame.time_relative -e tcp.srcport -e tcp.len > campos_sign.tsv` · `PC> python versiones\v3-node-red\herramientas\latencia_captura.py campos_sign.tsv` |
| 4.9 usuarios (v2) | `RPi2$ ./iniciar.sh cliente.py --anonimo` (Write rechazado) · `./iniciar.sh cliente.py` (escribe) · clave errónea en `~/.pdci-t2.env` (ActivateSession rechazado) |
| 4.9 token | Captura como en 4.1 con la v2 → filtro `opcua.servicenodeid.numeric == 467` → UserIdentityToken |

## Apagado

```bash
pi$ sudo poweroff        # esperar a que el LED verde se apague antes de desenchufar
```

Resultado del análisis de la captura de sesión completa (v1): [../evidencia/ANALISIS_captura_none.md](../evidencia/ANALISIS_captura_none.md).
