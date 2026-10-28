# Parte 2 — Servidor OPC UA y modelo de información

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Guía de banco de la Parte 2: servidor en la RPi 1, modelo de información con
NodeIds fijos, rampa diente de sierra, salidas por LED y verificación con un
cliente genérico (UaExpert). Incluye la pregunta de análisis 6.

**Requisitos previos:** RPi 1 preparada según
[node-red/README.md](node-red/README.md) e importado `servidor/flows.json`;
periféricos conectados (§11 de esa guía). La RPi 2 puede estar apagada.

---

## 1. Qué implementa el servidor

| Consigna | Implementación | Dónde |
|---|---|---|
| 2.1 Servidor en la RPi 1, `opc.tcp://192.168.10.1:4840`, todas las interfaces | node-opcua 2.160.0 en Node-RED; escucha en 0.0.0.0:4840; anuncia un endpoint por IP | [servidor_opcua.js](node-red/servidor/servidor_opcua.js) · ADR-01 en [arquitectura-red.md](docs/arquitectura-red.md) |
| 2.2 Namespace `urn:unraf:pdci:t2`, objetos `Servidor`/`Cliente`, 4 variables con NodeIds fijos, EURange | `construirEspacioDirecciones()`; Rampa como AnalogItemType | [modelo-informacion.md](docs/modelo-informacion.md) |
| 2.3 Diente de sierra 0-65535, 4 s, cada 50 ms | `senales.sierra()` calculada desde el reloj; 80 escalones, último = 65 535 | bloque S3 · [prueba_senales.js](herramientas/prueba_senales.js) |
| 2.4 LED digital ← `Cliente.EstadoPulsador`; LED PWM ← `Cliente.Rampa` escalada a 0-255 | Bloques S5/S6; pigpiod, PWM por DMA a 800 Hz | [flujo_servidor.md](diagramas/flujo_servidor.md) |
| 2.5 Verificación con UaExpert en modo None | §3 de esta guía | — |

## 2. Puesta en marcha y comprobaciones previas

```bash
$ journalctl -u nodered -n 60 --no-pager | grep -E "Endpoint|ATENCION|Error"
```

Se esperan seis líneas `Endpoint:` (tres modos por cada IP anunciada) y
ninguna `ATENCION` ni `Error`:

```text
[function:S2 · Servidor OPC UA] Endpoint: opc.tcp://192.168.10.1:4840  None  None
[function:S2 · Servidor OPC UA] Endpoint: opc.tcp://192.168.10.1:4840  Sign  Basic256Sha256
[function:S2 · Servidor OPC UA] Endpoint: opc.tcp://192.168.10.1:4840  SignAndEncrypt  Basic256Sha256
[function:S2 · Servidor OPC UA] Endpoint: opc.tcp://<IP Wi-Fi>:4840  None  None
…
```

```bash
$ sudo ss -tlnp | grep 4840          # LISTEN 0.0.0.0:4840 (todas las interfaces)
```

Guardar ambas salidas en `evidencia/parte2/`. Anotar la **IP Wi-Fi** de la
RPi 1 (`ip -br addr show wlan0`): UaExpert se conecta por ahí.

## 3. Verificación con UaExpert (consigna 2.5)

### 3.1 Conectar en modo None

1. **Server → Add…** → pestaña *Custom Discovery* → doble clic en
   *< Double click to Add Server… >* → escribir `opc.tcp://<IP Wi-Fi de la RPi 1>:4840`.
2. Desplegar el servidor que aparece y elegir el endpoint
   **None - None (uatcp-uasc-uabinary)**.
3. *Authentication Settings*: **Anonymous**. Aceptar.
4. Clic derecho sobre el servidor → **Connect**. Si UaExpert muestra el
   diálogo de validación del certificado del servidor, revisar que el nombre de
   aplicación sea *UNRaf PdCI T2 - Servidor (RPi 1)* y elegir
   *Trust Server Certificate*.

Si UaExpert avisa que la URL del endpoint no coincide con la usada para
descubrirlo, aceptar el reemplazo por la IP de Wi-Fi: el servidor anuncia un
endpoint por cada IP (`alternateHostname`), así que la de Wi-Fi está en la
lista.

**Captura:** `uaexpert_conexion.png` (panel *Log* con *Connected*).

### 3.2 Recorrer el espacio de direcciones (Browse)

En el panel **Address Space**: `Root → Objects → Servidor` y
`Root → Objects → Cliente`. Al seleccionar cada variable, el panel
**Attributes** muestra sus atributos.

Completar con lo observado (los valores esperados salen del servidor real,
[modelo-informacion.md §2.1](docs/modelo-informacion.md)):

| Atributo | `Servidor.EstadoPulsador` | `Servidor.Rampa` | `Cliente.EstadoPulsador` | `Cliente.Rampa` |
|---|---|---|---|---|
| NodeId | `ns=1;s=Servidor.EstadoPulsador` | `ns=1;s=Servidor.Rampa` | `ns=1;s=Cliente.EstadoPulsador` | `ns=1;s=Cliente.Rampa` |
| BrowseName | `1:EstadoPulsador` | `1:Rampa` | `1:EstadoPulsador` | `1:Rampa` |
| DataType | Boolean (i=1) | UInt16 (i=5) | Boolean (i=1) | UInt16 (i=5) |
| AccessLevel | CurrentRead (1) | CurrentRead (1) | CurrentRead, CurrentWrite (3) | CurrentRead, CurrentWrite (3) |
| Value | *pendiente* | *pendiente* | *pendiente* | *pendiente* |
| StatusCode | *pendiente* (Good) | *pendiente* | *pendiente* | *pendiente* |
| SourceTimestamp | *pendiente* | *pendiente* | *pendiente* | *pendiente* |
| ServerTimestamp | *pendiente* | *pendiente* | *pendiente* | *pendiente* |

Además: expandir `Servidor.Rampa` y verificar la propiedad **EURange**
(Low = 0, High = 65 535), y `Root → Objects → Server → Namespaces` o el
atributo `NamespaceArray`: `[1] = urn:unraf:pdci:t2`.

**Capturas:** `uaexpert_browse.png`, `uaexpert_atributos_<variable>.png` (una por
variable), `uaexpert_eurange.png`.

### 3.3 Forma de onda de `Servidor.Rampa`

1. **Document → Add…** → tipo **Trend View**.
2. Arrastrar `Servidor.Rampa` desde *Address Space* al Trend View.
3. Configurar el intervalo de muestreo en **50 ms** y la ventana de tiempo en
   ~20 s.

Se espera un **diente de sierra**: cinco rampas en 20 s, subida lineal de 0 a
65 535 en 4 s y caída vertical a 0. Medir con el cursor el período (≈ 4 s) y
contar los escalones si el zoom lo permite (80 por período).

| Medición | Esperado | Medido |
|---|---|---|
| Período | 4,00 s | *pendiente* |
| Mínimo / máximo | 0 / 65 535 | *pendiente* |
| Forma | Subida lineal, caída abrupta | *pendiente* |

**Captura:** `uaexpert_tendencia_rampa.png`.

### 3.4 Escribir `Cliente.*` y verificar los LED

En el *Data Access View* (documento por defecto) arrastrar las dos variables
`Cliente.*`. Doble clic en la columna **Value**, escribir el valor y Enter:

| Escritura | LED esperado en la RPi 1 | Observado |
|---|---|---|
| `Cliente.EstadoPulsador = true` | LED digital encendido | *pendiente* |
| `Cliente.EstadoPulsador = false` | LED digital apagado | *pendiente* |
| `Cliente.Rampa = 0` | LED PWM apagado | *pendiente* |
| `Cliente.Rampa = 16384` (25 %) | Brillo bajo | *pendiente* |
| `Cliente.Rampa = 32768` (50 %) | Brillo medio | *pendiente* |
| `Cliente.Rampa = 65535` | Brillo máximo | *pendiente* |

En la RPi 1, `journalctl -u nodered -f` debe mostrar en la línea de consola
(S7) `recibida(Cliente.Rampa)=<valor>`.

Observación para la Parte 3.7: con escala lineal, el salto de brillo entre 0 y
25 % se percibe mucho mayor que entre 75 % y 100 %.

### 3.5 Escribir una variable de solo lectura

Doble clic en **Value** de `Servidor.Rampa`, escribir `100`, Enter. El panel
**Log** de UaExpert registra el rechazo:

| Esperado | Medido |
|---|---|
| `Write … failed … BadNotWritable (0x803B0000)` | *pendiente* |

El valor de la rampa sigue cambiando normalmente: el rechazo no afecta al
servidor. Verificado de antemano en la prueba de integración 4. Probar también
un tipo incorrecto, por ejemplo escribir `true` en una Rampa si UaExpert lo
permite: **BadTypeMismatch** (prueba 5).

**Captura:** `uaexpert_bad_not_writable.png`.

## 4. Pregunta de análisis 6

> *¿Qué diferencia conceptual existe entre el par cliente-servidor de OPC UA y
> el par maestro-esclavo de MODBus? ¿Qué ventaja aporta navegar el espacio de
> direcciones frente a conocer de antemano una tabla de registros?*

Desarrollada en [docs/modelo-informacion.md §7](docs/modelo-informacion.md).
Síntesis para la defensa:

- **MODBus transfiere registros; OPC UA intercambia información.** El esclavo
  MODBus expone memoria cruda sin significado; el servidor OPC UA expone
  objetos con nombre, tipo, rango, nivel de acceso, calidad y marcas de tiempo.
- **Con estado frente a sin estado.** Cada transacción MODBus es independiente;
  OPC UA mantiene canal, sesión y suscripciones, y dentro de una suscripción
  **el servidor decide cuándo informar**.
- **Navegar frente a tabla externa.** UaExpert, que no sabe nada de este
  trabajo, mostró el modelo completo, el tipo, el rango y los permisos **leídos
  del propio servidor**. En la Tarea 1, QModMaster necesitó que se le cargaran
  dirección, función y cantidad de cada registro según un documento externo, y
  un error en ese documento no producía ningún error de protocolo.

## 5. Lista de verificación de la Parte 2

- [ ] Seis endpoints en el registro; `LISTEN 0.0.0.0:4840`.
- [ ] UaExpert conectado en None/Anonymous por la IP de Wi-Fi.
- [ ] Tabla de atributos de §3.2 completa; EURange y NamespaceArray verificados.
- [ ] Tendencia de `Servidor.Rampa` con el período medido.
- [ ] Escrituras de `Cliente.*` con su efecto en los LED.
- [ ] `BadNotWritable` al escribir `Servidor.Rampa`.
- [ ] Capturas `.png` en `evidencia/capturas/`.
