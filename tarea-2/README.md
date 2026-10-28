# Tarea 2 — OPC UA cliente-servidor sobre Raspberry Pi 4

Protocolos de Comunicaciones Industriales · 4.º año, Ingeniería en Computación · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Dos Raspberry Pi 4 unidas por un enlace Ethernet punto a punto intercambian el estado de un pulsador
y una rampa por OPC UA (IEC 62541): la RPi 1 es servidor (`192.168.10.1`) y la RPi 2, cliente
(`192.168.10.2`).

## Empezar acá

**[guia/](guia/README.md)** — puesta en marcha de punta a punta, en orden:

1. [Instalar el SO en las microSD](guia/01_instalar_SO_microSD.md)
2. [Cargar los programas por SSH](guia/02_cargar_programas_SSH.md)
3. [Conexionado eléctrico](guia/03_conexionado_electrico.md)
4. [Resolución de todas las consignas](guia/04_resolucion_consignas.md)

## Estructura

| Carpeta | Contenido |
|---|---|
| [consigna/](consigna/) | [Tarea_2_OPC_V26.pdf](consigna/Tarea_2_OPC_V26.pdf) (enunciado) · [CxI_OPC_2022.pdf](consigna/CxI_OPC_2022.pdf) (material de cátedra) |
| [guia/](guia/README.md) | Las cuatro guías de puesta en marcha y el diagrama de conexiones |
| [versiones/](versiones/README.md) | Las tres implementaciones, comparadas |
| ├ [v1-original-agustina/](versiones/v1-original-agustina/README.md) | Versión Python original, sin modificar, y su revisión ([CORRECCIONES.md](versiones/v1-original-agustina/CORRECCIONES.md)) |
| ├ [v2-correccion-python/](versiones/v2-correccion-python/README.md) | **Versión que se presenta**: Python/asyncua corregida, cubre todas las consignas |
| └ [v3-node-red/](versiones/v3-node-red/README.md) | Versión Node-RED/node-opcua, con la teoría completa en `docs/` y las herramientas de análisis |
| [herramientas/](herramientas/desplegar.ps1) | `desplegar.ps1`: copia v1 o v2 a las placas con un comando |
| [evidencia/](evidencia/README.md) | Registros, capturas `.pcapng` y `.png` del banco |

## Ramas

| Rama | Uso |
|---|---|
| `main` | Historial original |
| `develop` | Esta organización; trabajo en curso |
