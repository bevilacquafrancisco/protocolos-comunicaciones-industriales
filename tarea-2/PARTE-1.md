# Parte 1 — Montaje de la red Ethernet punto a punto

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Guía de banco de la Parte 1 de la consigna: conexión física, direccionamiento
estático, verificación por capas, convivencia con la Wi-Fi y la pregunta de
análisis 5.

**Requisito previo:** ambas placas preparadas según
[node-red/README.md](node-red/README.md) §1 a §7.

**Convención de evidencia:** cada comando se guarda con `| tee` en
`~/evidencia/parte1/` de la placa y después se copia a
[evidencia/parte1/](evidencia/) en el repositorio. Las tablas de resultados se
completan **con lo medido**; donde dice *pendiente* todavía no hay medición.

---

## 1. Conexión física

1. Ambas placas encendidas, con la Wi-Fi conectada (acceso por SSH).
2. Conectar el cable Ethernet **directamente** entre los puertos de las dos
   placas, sin switch ni router.
3. Los LED del conector RJ-45 deben encenderse en las dos placas en pocos
   segundos (verde = enlace; ámbar = actividad o velocidad, según el modelo).

No importa si el cable es directo o cruzado: auto MDI-X
([docs/arquitectura-red.md §2.1](docs/arquitectura-red.md)).

## 2. Direccionamiento estático

Procedimiento con **NetworkManager (`nmcli`)**, el gestor de red de Raspberry
Pi OS Bookworm (comandos completos en
[node-red/README.md §7](node-red/README.md)):

| Paso | RPi 1 · servidor | RPi 2 · cliente |
|---|---|---|
| Borrar el perfil DHCP por defecto | `sudo nmcli con delete "Wired connection 1"` | ídem |
| Crear el perfil estático | `… ipv4.addresses 192.168.10.1/24 ipv4.never-default yes …` | `… 192.168.10.2/24 …` |
| Activarlo | `sudo nmcli con up pdci-eth0` | ídem |
| Comprobar | `nmcli -f NAME,DEVICE,STATE con show --active` | ídem |

El perfil queda con `connection.autoconnect yes`: persiste después de un
reinicio. Verificarlo con `sudo reboot` y repitiendo §3.

## 3. Verificación por capas

Ejecutar en **cada** placa y guardar la salida:

```bash
$ mkdir -p ~/evidencia/parte1 && cd ~/evidencia/parte1
$ ethtool eth0            | tee ethtool_$(hostname).txt
$ ip -br link show eth0   | tee iplink_$(hostname).txt
$ ip addr show eth0       | tee ipaddr_$(hostname).txt
$ ip route                | tee iproute_$(hostname).txt
```

En la **RPi 2** (y al revés en la RPi 1, hacia .2):

```bash
$ ip neigh flush dev eth0                      # tabla ARP vacía, para ver el ARP del ping
$ ping -c 10 192.168.10.1 | tee ping_$(hostname).txt
$ ip neigh show dev eth0  | tee ipneigh_$(hostname).txt
```

### 3.1 Resultados

| Capa | Qué | RPi 1 | RPi 2 | Esperado |
|---|---|---|---|---|
| Física | `Link detected` | *pendiente* | *pendiente* | `yes` |
| Física | `Speed` | *pendiente* | *pendiente* | `1000Mb/s` (o `100Mb/s` con cable de 2 pares) |
| Física | `Duplex` | *pendiente* | *pendiente* | `Full` |
| Física | `Auto-negotiation` | *pendiente* | *pendiente* | `on` |
| Física | `MDI-X` | *pendiente* | *pendiente* | `on` u `off`: indica si **ese** extremo cruzó |
| Enlace | MAC de `eth0` (`ip link`) | *pendiente* | *pendiente* | OUI de Raspberry Pi |
| Enlace | Estado de `ip link` | *pendiente* | *pendiente* | `UP` + `LOWER_UP` |
| Red | Dirección (`ip addr`) | *pendiente* | *pendiente* | `192.168.10.x/24` |
| Red | Ruta (`ip route`) | *pendiente* | *pendiente* | `192.168.10.0/24 dev eth0 proto kernel scope link`, **sin** `default via` por `eth0` |
| Red | `ping` (10 paquetes) | *pendiente* | *pendiente* | 0 % de pérdida; RTT < 1 ms |
| Enlace | `ip neigh` después del ping | *pendiente* | *pendiente* | MAC del otro extremo, `REACHABLE` |

**Qué discutir si algo no coincide:**

| Observación | Causa probable |
|---|---|
| `Speed: 100Mb/s` | Cable de solo 2 pares (algunos cables planos baratos) o categoría inferior a 5e. Para este trabajo alcanza, pero hay que documentarlo |
| `Duplex: Half` | Un extremo con la velocidad fijada a mano: desacuerdo de dúplex (*arquitectura-red.md* §2.1) |
| `ping` con pérdida | Cable dañado o conector mal crimpado |
| No hay entrada en `ip neigh` | El ping no llegó a salir por `eth0` (ver §4) |

### 3.2 Ver el ARP en acción

```bash
$ sudo ip neigh flush dev eth0
$ sudo tcpdump -i eth0 -n -e arp -c 2 &      # -e muestra las MAC
$ ping -c 1 192.168.10.1
```

Se ven dos tramas: `Request who-has 192.168.10.1 tell 192.168.10.2` hacia
`ff:ff:ff:ff:ff:ff` (difusión) y `Reply 192.168.10.1 is-at <MAC>` (unicast).
Guardar la salida como `arp_tcpdump.txt`.

## 4. Convivencia con la Wi-Fi: demostrar que el OPC UA va por `eth0`

Consigna 1.4. Cuatro pruebas independientes. Hacerlas **con el sistema OPC UA
funcionando** (después de la Parte 3):

| # | Prueba | Comando (en la RPi 2) | Resultado esperado |
|---|---|---|---|
| 1 | Decisión de ruteo del kernel | `ip route get 192.168.10.1` | `192.168.10.1 dev eth0 src 192.168.10.2` |
| 2 | Socket TCP real del cliente | `ss -tnp \| grep 4840` | `ESTAB … 192.168.10.2:<puerto> 192.168.10.1:4840` |
| 3 | Tráfico en `eth0` | `sudo timeout 10 tcpdump -i eth0 -n port 4840 \| wc -l` | Cientos de paquetes |
| 4 | Tráfico en `wlan0` | `sudo timeout 10 tcpdump -i wlan0 -n port 4840 \| wc -l` | **0** |

Complemento: contadores de la interfaz antes y después de 60 s
(`ip -s link show eth0` y `ip -s link show wlan0`): el aumento de bytes del
OPC UA aparece solo en `eth0`.

| # | Resultado medido |
|---|---|
| 1 | *pendiente* |
| 2 | *pendiente* |
| 3 | *pendiente* paquetes en 10 s |
| 4 | *pendiente* paquetes en 10 s |

**Contraprueba** (opcional, muestra que la prueba 4 detecta algo): conectar
temporalmente el cliente a la IP Wi-Fi del servidor. Entonces la prueba 4 sí
cuenta paquetes. Volver la configuración a la IP de `eth0`.

Por qué el tráfico va por `eth0` y qué trampas evita el diseño (nombre de host,
URL anunciada en GetEndpoints): [docs/arquitectura-red.md §4](docs/arquitectura-red.md).

## 5. Pregunta de análisis 5

> *Explicar teóricamente qué se debe realizar para montar una red Ethernet
> punto a punto entre dos equipos sin dispositivos intermedios.*

Desarrollada en [docs/arquitectura-red.md §2](docs/arquitectura-red.md):

| Capa | Tema | Sección |
|---|---|---|
| Física | Tipo de cable, auto MDI-X, autonegociación de velocidad y dúplex | §2.1 |
| Enlace | Direcciones MAC, rol de ARP, ausencia de colisiones en full-duplex | §2.2 |
| Red | Direccionamiento estático, máscara /24, por qué no hace falta puerta de enlace, qué pasa sin IP fija (169.254.0.0/16, RFC 3927) | §2.3 |
| Todas | Qué herramienta verifica cada capa | §2.4 |

## 6. Lista de verificación de la Parte 1

- [ ] Cable conectado directamente, LED de enlace encendidos en ambas placas.
- [ ] Perfil `pdci-eth0` con IP estática en cada placa; persiste tras reiniciar.
- [ ] Tabla §3.1 completa con los valores medidos.
- [ ] Captura del ARP (§3.2).
- [ ] Las cuatro pruebas de §4 con su salida guardada.
- [ ] Archivos de evidencia copiados a `evidencia/parte1/`.
