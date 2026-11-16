# Puesta en marcha del banco de laboratorio — Tarea 3

Procedimiento completo para pasar del código del repositorio al sistema funcionando en el banco y
cumplir todas las consignas del TP integrador. Se parte de lo siguiente:

- el ESP32 sin MicroPython;
- la Raspberry Pi 4 con una microSD vacía o con la del laboratorio;
- la notebook con el repositorio clonado;
- una cuenta de correo para dar de alta el broker.

**Autores:** Bevilacqua Francisco, Peralta Agustina · **Versión:** 1.0 · 2026-11-14

> ⚠️ **Seguridad eléctrica.**
> - Todo el conexionado se hace **con los equipos apagados y desenchufados**.
> - Los GPIO del ESP32 y de la Raspberry Pi son de **3,3 V y no toleran 5 V**.
> - El pin RO del MAX485 entrega ≈ 5 V: va **siempre** con el divisor 2,2 kΩ / 3,3 kΩ y el pull-up de
>   680 Ω (paso 03).

---

## 1. Qué queda funcionando al final

```
 Nivel 0/1         ESP32 #1 + MAX485  (dispositivo 1: esclavo MODBus RTU, MicroPython)
                          │  RS-485, par trenzado A/B + GND · 9600 8N1 · Unit ID 1
 Nivel 2           Adaptador USB-RS485 ──USB── Raspberry Pi 4  (dispositivo 2: Node-RED)
                                                │  eth0 192.168.10.1/24
                                                │  cable Ethernet directo · OPC UA opc.tcp:4840
 Nivel 3           Notebook (dispositivo 3: cliente OPC UA + Edge Node Sparkplug B)
                          │  Ethernet 192.168.10.2/24  ·  Wi-Fi → internet
                          │  MQTT sobre TLS :8883
 Nube              Broker EMQX Cloud (Serverless)
                          │  MQTT sobre WebSocket con TLS :8084
 Nivel 4           Navegador de la notebook y del celular (Host Application)
```

| Equipo | Interfaces | Software | Etapa |
|---|---|---|---|
| ESP32 #1 | UART2 → MAX485 → bus RS-485 · USB solo para alimentar y para Thonny | MicroPython + `firmware/esclavo-modbus` | 03 |
| ESP32 #2 *(esclavo desconocido)* | Igual, con el jumper de GPIO 13 a GND | El mismo firmware, perfil DESCONOCIDO | 03, 09 |
| Raspberry Pi 4 | `eth0` 192.168.10.1/24 (OPC UA) · `wlan0` por DHCP (SSH e instalación) · USB (adaptador RS-485) | Node-RED 4.1.16 + `edge-nodered` | 04, 05, 06 |
| Notebook | Ethernet 192.168.10.2/24 (OPC UA) · Wi-Fi a internet | Python 3.11 + `gateway-sparkplug`, Node.js + `hmi-web`, Wireshark, MQTT Explorer | 01, 07, 08 |
| Celular | Punto de acceso Wi-Fi (internet para la notebook y la Raspberry) y visor de la web | Navegador | 01, 08 |
| Broker | En internet (I-03) | EMQX Cloud Serverless, con tres credenciales y permisos por tópico | 02 |

**Plan de red.**

- El enlace OPC UA es un **cable directo**, sin router ni puerta de enlace: 192.168.10.0/24.
- Todo lo que sale a internet (el broker, los paquetes de la Raspberry, NTP) va por la **Wi-Fi del
  punto de acceso del celular**.
- La Wi-Fi de la facultad suele tener portal cautivo o WPA2-Enterprise, que la Raspberry no puede
  usar sin pantalla. Con el celular se elimina esa dependencia (riesgo R-06).

## 2. Orden de las etapas

| # | Documento | Dónde | Tiempo | Criterio de salida |
|---|---|---|---|---|
| 01 | [Materiales y PC](01-materiales-y-pc.md) | Casa | 1 h | La notebook corre las tres suites de pruebas en verde |
| 02 | [Broker MQTT en la nube](02-broker-mqtt.md) | Casa | 30 min | El observador recibe un NCMD de prueba a través de la nube |
| 03 | [ESP32: firmware y conexionado](03-esp32.md) | Casa o laboratorio | 45 min | La consola muestra el perfil DISPOSITIVO_1, Unit ID 1, 9600 8N1 |
| 04 | [Raspberry Pi: microSD y red](04-raspberry-microsd.md) | Laboratorio (respaldo) o casa | 45 min | SSH por Wi-Fi y `ping 192.168.10.1` desde la notebook por el cable |
| 05 | [Raspberry Pi: software](05-raspberry-software.md) | Cualquier lugar con internet | 45 min | El servicio está activo y el log dice "servidor OPC UA en opc.tcp" |
| 06 | [Bus RS-485 y primer enlace](06-bus-rs485.md) | Laboratorio | 20 min | El Dashboard muestra MODBUS = DONE y el LED responde |
| 07 | [Notebook: dispositivo 3](07-dispositivo-3.md) | Laboratorio | 30 min | Sesión OPC UA en SignAndEncrypt; NBIRTH y DBIRTH en el broker |
| 08 | [Host Application](08-host-application.md) | Laboratorio | 15 min | La web, en la notebook y en el celular, muestra todo EN LÍNEA y acciona el LED |
| 09 | [Verificación integral y consignas](09-verificacion-y-consignas.md) | Laboratorio | 2-3 h | Cada consigna con su evidencia guardada en `docs/capturas/banco/` |
| 10 | [Cierre y problemas frecuentes](10-cierre-y-problemas.md) | Laboratorio | 20 min | La microSD del laboratorio restaurada y la evidencia copiada |

Las etapas 01, 02 y 03 se hacen **antes** del día de laboratorio. El 05 también, si se usa una microSD
propia (ver 04 §1). Así, en el laboratorio solo queda lo que necesita el banco armado.

## 3. Convenciones

| Prefijo | Dónde se ejecuta |
|---|---|
| `PS>` | PowerShell de la notebook (Windows) |
| `GB$` | Git Bash de la notebook (para los scripts `.sh`) |
| `$` | Raspberry Pi, por SSH |
| *Thonny* | Thonny, con el ESP32 conectado |

- Los valores entre `<...>` se reemplazan. Nunca se escriben claves en un comando: los programas las
  piden por teclado o las leen de un archivo de entorno con permisos restringidos.
- **[SEC]** marca una decisión de seguridad. **⚠️** marca un paso que puede dañar el hardware o borrar
  datos.
- Cada etapa termina con su **criterio de salida**. No se pasa a la siguiente sin cumplirlo: un error
  que se arrastra se vuelve mucho más difícil de aislar con tres equipos en cadena.

## 4. Secretos: qué se crea, dónde vive, quién lo ve

Ningún secreto va al repositorio. Se guardan en un gestor de contraseñas (por ejemplo, Bitwarden, que
es gratuito).

| Secreto | Se crea en | Vive en | Lo lee |
|---|---|---|---|
| Clave del usuario MQTT `edge_node` | Consola de EMQX (02) | `tarea-3/.env` de la notebook | Edge Node |
| Clave del usuario MQTT `host_app` | Consola de EMQX (02) | `hmi-web/config.js` (ignorado por git) | Navegador. **Es pública de hecho** (ADR-005, ADR-027) |
| Clave del usuario MQTT `observador` | Consola de EMQX (02) | `tarea-3/.env` y MQTT Explorer | Observador, MQTT Explorer |
| Clave del usuario OPC UA `operador` | La elige el equipo (05 §4) | Hash scrypt en `/etc/pdci-t3-nodered.env` (Raspberry); en claro en `tarea-3/.env` (notebook) | Servidor OPC UA (hash); Edge Node (clave) |
| Clave privada SSH (solo para el TP) | Notebook (01 §3) | `C:\Users\<usuario>\.ssh\id_ed25519_pdci_t3` | Solo la notebook |
| Claves privadas OPC UA | Se generan solas en el primer arranque | `~/.pdci-t3/opcua-pki` (Raspberry) y `gateway-sparkplug/pki` (notebook) | Servidor y cliente |

## 5. Qué cumple cada etapa

| Consigna | Se monta en | Se verifica en |
|---|---|---|
| 1 (MODBus RTU, CRC propio, contadores, reconfiguración en vivo) | 03, 05, 06 | 06, 09 §2 |
| 2 (OPC UA, cliente de la T2, trama) | 05, 07 | 07, 09 §3 |
| 3 (MQTT + Sparkplug B, Host Application) | 02, 07, 08 | 08, 09 §4 |
| 4 (fallas: detección y recuperación) | — | 09 §5 |
| Defensa (demo, informe) | — | 09 §6-7 |

Detalle de cada requisito y su evidencia: [matriz-trazabilidad.md](../matriz-trazabilidad.md).
Procedimiento de las pruebas: [plan-de-pruebas.md](../plan-de-pruebas.md).
