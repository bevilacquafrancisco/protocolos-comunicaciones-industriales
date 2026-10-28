# Versiones del trabajo

Tres implementaciones de la misma consigna. **Para la entrega y la defensa: v2.**

| | [v1 — original](v1-original-agustina/) | [v2 — corrección Python](v2-correccion-python/) | [v3 — Node-RED](v3-node-red/) |
|---|---|---|---|
| Autoría | Agustina Peralta | Francisco Bevilacqua (sobre v1) | Francisco Bevilacqua, Agustina Peralta |
| Pila OPC UA | Python · asyncua | Python · asyncua 2.1.0 | Node.js · node-opcua 2.160.0 en Node-RED |
| GPIO | gpiozero | gpiozero + lgpio | pigpiod (PWM por DMA) |
| Sistema operativo | Raspberry Pi OS Lite 64-bit (actual) | Raspberry Pi OS Lite 64-bit (actual, Debian 13 "trixie") | **Bookworm (Legacy)**: `pigpio` no está en trixie |
| Host / usuario de la guía | `raspberry-servidor`, `raspberry-cliente` / `pi` | ídem | `rpi-servidor`, `rpi-cliente` / `pdci` (adaptable) |
| Pulsador | 3V3 → pulsador → GPIO17 (pull-down) | ídem | GPIO17 → pulsador → **GND** (pull-up) |
| Consignas cubiertas | Partes 1-3 (parcial 3.4) | **Todas** | Todas (sin medir en banco) |
| Carpeta en la placa | `~/TP2_OPC_original` | `~/TP2_OPC` | `~/pdci-t2` |
| Probada | PC (sin modificar) | PC: `prueba_local.py` 50/50 | PC: 118 pruebas; Node-RED real |
| Documento principal | [README.md](v1-original-agustina/README.md) · [CORRECCIONES.md](v1-original-agustina/CORRECCIONES.md) | [README.md](v2-correccion-python/README.md) · [CONSIGNA.md](v2-correccion-python/CONSIGNA.md) | [README.md](v3-node-red/README.md) · [CHECKLIST.md](v3-node-red/CHECKLIST.md) |

v1 y v2 conviven en la misma microSD (carpetas distintas, mismo entorno Python): se cambia de una a
otra sin regrabar. **Nunca ejecutar dos servidores a la vez** (puerto 4840 y GPIO ocupados).

La teoría con bibliografía (capas de red, modelo de información, protocolo, seguridad) está en
[v3-node-red/docs/](v3-node-red/docs/) y vale para las tres: solo cambian los tamaños de mensaje,
que se toman de las capturas propias.

Recorrido de punta a punta (microSD → última consigna): [../guia/](../guia/).
