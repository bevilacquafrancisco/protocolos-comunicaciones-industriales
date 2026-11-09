# Tarea Nº3 — Integradora: MODBus RTU → OPC UA → MQTT/Sparkplug B

Protocolos de Comunicaciones Industriales · 4.º año, Ingeniería en Computación · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Cadena de comunicación de extremo a extremo, del campo al usuario:

```
Nivel 0/1  ESP32 (dispositivo 1) ── esclavo MODBus RTU, stack y CRC propios
               │ RS-485, half-duplex
Nivel 2    Raspberry Pi (dispositivo 2) ── Node-RED: maestro MODBus + servidor OPC UA (node-opcua)
               │ OPC UA binario, opc.tcp :4840
Nivel 3    PC / VM (dispositivo 3) ── cliente OPC UA de la T2 (asyncua) + Edge Node Sparkplug B
               │ MQTT + Sparkplug B (Protobuf) por un broker en internet
Nivel 4    Navegador ── Host Application (MQTT sobre WSS + protobuf.js)
```

**Estado: Fase F0 cerrada (análisis y documentación).** Todavía no hay código de producción.
Decisión pendiente que bloquea F2: lenguaje del firmware del esclavo
([ADR-010](docs/decisiones-adr.md)).

## Empezar acá

| Documento | Para qué |
|---|---|
| [consigna/Tarea_3_Integrador_V26.pdf](consigna/Tarea_3_Integrador_V26.pdf) | Enunciado |
| [docs/diccionario-de-datos.md](docs/diccionario-de-datos.md) | **Fuente única de verdad**: nombres, tipos, direcciones MODBus, NodeIds y métricas |
| [docs/decisiones-adr.md](docs/decisiones-adr.md) | Decisiones de arquitectura (ADR-001 a 014) y su estado |
| [docs/riesgos.md](docs/riesgos.md) | Registro de riesgos con disparadores de contingencia |
| [docs/analisis-t1.md](docs/analisis-t1.md) | Qué se reutiliza y qué se reescribe de la Tarea Nº1 |
| [docs/analisis-t2.md](docs/analisis-t2.md) | Qué se reutiliza de la Tarea Nº2 y qué mediciones se pueden citar |
| [docs/spike-nodered-opcua.md](docs/spike-nodered-opcua.md) | Por qué el dispositivo 2 es Node-RED + node-opcua y cómo se delimitan las tramas |
| [docs/matriz-trazabilidad.md](docs/matriz-trazabilidad.md) | Consigna → artefacto → evidencia → sección del informe |
| [docs/plan-de-pruebas.md](docs/plan-de-pruebas.md) | Verificación y validación, inyección de fallas |

## Estructura

| Carpeta | Contenido | Estado |
|---|---|---|
| `consigna/` | Enunciado de la T3 | ✅ |
| `docs/` | Diccionario, ADR, riesgos, análisis, matriz, plan de pruebas | ✅ F0 |
| `docs/diagramas/` | Fuentes Mermaid (`.mmd`) y PNG renderizados | vacío |
| `docs/capturas/` | Wireshark, MQTT Explorer, sniffer RS-485, fotos | vacío |
| `firmware/esclavo-modbus/` | Dispositivo 1. Lenguaje según ADR-010 | vacío |
| `edge-nodered/` | Dispositivo 2: flows por función, `lib/` (CRC, PDU), `settings.js`, `config/` | vacío |
| `gateway-sparkplug/` | Dispositivo 3: cliente OPC UA, Edge Node, `proto/sparkplug_b.proto` | vacío |
| `hmi-web/` | Host Application | vacío |
| `simuladores/` | Esclavo MODBus sobre pty virtual, esclavo "desconocido" | vacío |
| `informe/` | **Solo los PDF entregables** (hoy: `Bevilacqua_Peralta_PdCI_T3_26_preliminar.pdf`) | ✅ preliminar |
| `defensa/` | Guion de 12 min y diapositivas | vacío |

## Reutilización de las tareas anteriores

| De | Qué | Cómo |
|---|---|---|
| T1 | `config.py`, `perifericos.py`, `diagnostico.py`, mapa de registros, decisiones de capa física | Se conservan; se reescribe solo la capa de protocolo del esclavo (I-01) |
| T1 | `herramientas/modbus_tramas.py`, `sniffer_rs485.py` | Oráculo de CRC y analizador del bus |
| T2 v2 | Cliente `asyncua` 2.1.0 (`cliente_base.py`, `cliente_suscripcion.py`) | Base del dispositivo 3 (ADR-013) |
| T2 v3 | `servidor_opcua.js`, `credenciales.js` (node-opcua 2.160.0) | Base del servidor OPC UA del dispositivo 2 (ADR-011) |

## Secretos

Nada de contraseñas, hashes, claves privadas, certificados ni `flows_cred.json` en el repositorio.
Plantilla de variables: [.env.example](.env.example). El `.env` real se crea con permisos 600.
`.gitignore` cubre `.env`, `*.pem`, `*.key`, `*.der`, `pki/` y los artefactos de build.

## Comandos

### Informe

`informe/` contiene solo los PDF entregables. Las fuentes del preliminar (Markdown, bibliografía
APA 7, hoja de estilos y `construir_pdf.py`, que genera el PDF y verifica Arial 11, interlineado
1,5 y márgenes 3 / 2,5 cm) se retiraron de la carpeta y quedan en el commit `658fa3a`:

```bash
git restore --source=658fa3a -- tarea-3/informe/      # recuperarlas para editar y regenerar
```

### Diagramas (Mermaid → PNG)

```bash
npm install @mermaid-js/mermaid-cli@11.4.2      # PUPPETEER_SKIP_DOWNLOAD=true para usar el Chrome instalado
npx mmdc -i tarea-3/docs/diagramas/flujo-maestro.mmd -o tarea-3/docs/diagramas/flujo-maestro.png -b white -s 2
```

En los diagramas de secuencia, el `;` de un NodeId se escribe `#59;` (Mermaid lo toma como fin
de sentencia).

### Tareas anteriores

Todavía no hay código de producción de la T3. Las verificaciones de las tareas anteriores que la
T3 reutiliza se corren desde la raíz del repositorio (ver `CLAUDE.md` raíz):

```bash
python tarea-1/herramientas/modbus_tramas.py     # CRC-16/MODBUS contra el vector 123456789 -> 0x4B37
python tarea-1/herramientas/prueba_diagnostico.py
node --test tarea-2/versiones/v3-node-red/herramientas/prueba_senales.js tarea-2/versiones/v3-node-red/herramientas/prueba_flujos.js
```
