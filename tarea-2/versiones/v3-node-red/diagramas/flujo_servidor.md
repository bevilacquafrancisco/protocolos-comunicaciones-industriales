# Diagrama de flujo — Servidor OPC UA (Raspberry Pi 1)

**Autores:** Bevilacqua Francisco, Peralta Agustina

Cumple el requerimiento adicional 2 de la consigna: diagrama de flujo del
servidor (inicialización, creación del espacio de direcciones, generación de la
rampa, lectura del pulsador, atención de escrituras y manejo de LEDs). También
cumple el requerimiento 3 (trazabilidad de código): cada bloque nombra la
function node de Node-RED **con el mismo nombre** y el archivo que contiene su
código. `herramientas/prueba_flujos.js` verifica que la correspondencia se
mantenga.

## 1. Vista general: tareas concurrentes

En Node-RED no hay un `while True` como en el firmware de la Tarea 1. Hay
**cuatro disparadores independientes** (dos temporizadores, el GPIO y la red)
que el *event loop* de Node.js atiende de a uno por vez. Por eso ningún bloque
espera a otro: la rampa sigue generándose aunque no haya cliente conectado.

```mermaid
flowchart LR
    subgraph Disparadores
        T50["⏱ cada 50 ms"]
        GPIO["⚡ flanco en GPIO17"]
        RED["🌐 WriteRequest<br/>del cliente"]
        T1S["⏱ cada 1 s"]
    end
    T50 --> S3["S3 · Generar rampa<br/>diente de sierra"]
    GPIO --> S4["S4 · Leer pulsador"]
    S3 --> S2["S2 · Servidor OPC UA<br/>(espacio de direcciones)"]
    S4 --> S2
    RED --> S5["S5 · Atención de<br/>escrituras"]
    S5 --> S6D["S6 · LED digital"]
    S5 --> S6P["S6 · LED PWM"]
    T1S --> S7["S7 · Registro en consola"]
    S2 -. "Read / Publish" .-> CLI(["Cliente OPC UA"])
    CLI -. "Write" .-> RED
```

## 2. Bloques en detalle

```mermaid
flowchart TB
    INICIO([Arranque de Node-RED]) --> S1

    subgraph S1g["S1 · Inicialización"]
        S1["S1 · Verificar configuración<br/>¿config, senales, opcua y<br/>servidorOpcua cargados?"]
        S1 -->|no| S1E["Estado rojo + node.error<br/>no envía nada"]
        S1 -->|sí| S1V{"¿config.VERSION<br/>== 1?"}
        S1V -->|no| S1W["Advertencia<br/>(continúa)"] --> S1S
        S1V -->|sí| S1S["LED digital = 0<br/>LED PWM = 0 %<br/>(estado seguro)"]
    end

    INICIO --> S2A
    subgraph S2g["S2 · Servidor OPC UA (On Start)"]
        S2A["Crear PKI (own/ trusted/ rejected/)"] --> S2B["Crear OPCUAServer<br/>puerto 4840 · 3 endpoints<br/>alternateHostname = IPs de eth0 y wlan0"]
        S2B --> S2C["registerNamespace(urn:unraf:pdci:t2)<br/>¿índice == 1?"]
        S2C -->|no| S2X["Error: no arranca"]
        S2C -->|sí| S2D["Objects/Servidor: EstadoPulsador, Rampa+EURange<br/>Objects/Cliente: EstadoPulsador, Rampa+EURange<br/>valores iniciales false / 0"]
        S2D --> S2E{"server.start()<br/>¿EADDRINUSE?"}
        S2E -->|"sí, intento < 10"| S2R["esperar 500 ms"] --> S2B
        S2E -->|no| S2F["Estado verde<br/>'escuchando :4840'"]
    end

    subgraph S3g["S3 · Rampa (cada 50 ms)"]
        S3P{"¿rampa detenida?<br/>(botones S3 · Detener /<br/>Reanudar rampa)"} -->|sí| S3N["no publica: el valor<br/>queda fijo → solo KeepAlive"]
        S3P -->|no| S3A["t = Date.now()"]
        S3A --> S3B["k = ⌊(t mod 4000) / 50⌋<br/>valor = round(k · 65535 / 79)"]
        S3B --> S3C["publicarRampa(valor, t)<br/>→ Servidor.Rampa<br/>SourceTimestamp = t"]
    end

    subgraph S4g["S4 · Pulsador (por flanco)"]
        S4A["pigpio: glitch filter 25 000 µs"] --> S4B{"nivel == 0?"}
        S4B -->|sí| S4T["presionado = true"]
        S4B -->|no| S4F["presionado = false"]
        S4T --> S4C["log 'LATENCIA pulsador_local' + hora<br/>publicarPulsador → Servidor.EstadoPulsador"]
        S4F --> S4C
    end

    subgraph S5g["S5 · Atención de escrituras (node-opcua)"]
        S5A["WriteRequest recibido"] --> S5B{"¿AccessLevel<br/>tiene CurrentWrite?"}
        S5B -->|no| S5N["BadNotWritable"]
        S5B -->|sí| S5R{"¿rol con permiso<br/>Write?"}
        S5R -->|no| S5U["BadUserAccessDenied"]
        S5R -->|sí| S5T{"¿tipo del Variant ==<br/>DataType del nodo?"}
        S5T -->|no| S5M["BadTypeMismatch"]
        S5T -->|sí| S5OK["Good · value_changed<br/>flow.set(...)"]
    end

    subgraph S6g["S6 · LEDs"]
        S6D["Cliente.EstadoPulsador<br/>true→1 · false→0"] --> G27["GPIO27"]
        S6P["Cliente.Rampa → escala255 (gamma opcional)<br/>→ dutyAPorcentajePiGpiod"] --> G18["GPIO18 PWM 800 Hz"]
    end

    subgraph S7g["S7 · Consola (cada 1 s)"]
        S7A["node.log: generada, recibida(Cliente.Rampa),<br/>SourceTimestamp"]
    end

    S5OK --> S6D
    S5OK --> S6P
```

Las validaciones de S5 las hace **node-opcua antes** de que el valor llegue al
código del trabajo: cuando se ejecuta `alEscribirCliente()` el valor ya es del
tipo correcto. La prueba de integración las verifica una por una (pruebas 4, 5
y 15).

## 3. Trazabilidad diagrama ↔ código

| Bloque | Function node en Node-RED | Archivo con el código | Función de biblioteca |
|---|---|---|---|
| S1 | `S1 · Verificar configuracion` | [comun/funciones/X1_verificar_config.js](../node-red/comun/funciones/X1_verificar_config.js) | — |
| S2 | `S2 · Servidor OPC UA` (On Start) | [servidor/funciones/S2_servidor_opcua.inicio.js](../node-red/servidor/funciones/S2_servidor_opcua.inicio.js) | `iniciarServidor()`, `construirEspacioDirecciones()` en [servidor_opcua.js](../node-red/servidor/servidor_opcua.js) |
| S2 | `S2 · Servidor OPC UA` (On Message) | [servidor/funciones/S2_servidor_opcua.js](../node-red/servidor/funciones/S2_servidor_opcua.js) | `publicarRampa()`, `publicarPulsador()` |
| S2 | `S2 · Servidor OPC UA` (On Close) | [servidor/funciones/S2_servidor_opcua.fin.js](../node-red/servidor/funciones/S2_servidor_opcua.fin.js) | `detener(0)` |
| S3 | `S3 · Generar rampa diente de sierra` | [servidor/funciones/S3_generar_rampa.js](../node-red/servidor/funciones/S3_generar_rampa.js) | `senales.sierra()` |
| S4 | `S4 · Leer pulsador` | [comun/funciones/X4_leer_pulsador.js](../node-red/comun/funciones/X4_leer_pulsador.js) | nodo `pi gpiod in` |
| S5 | (callback dentro de S2) | `alEscribirCliente` en S2_servidor_opcua.inicio.js | evento `value_changed` de node-opcua |
| S6 | `S6 · LED digital`, `S6 · LED PWM` | [comun/funciones/X6_led_digital.js](../node-red/comun/funciones/X6_led_digital.js), [X6_led_pwm.js](../node-red/comun/funciones/X6_led_pwm.js) | `senales.escala255()`, `senales.dutyAPorcentajePiGpiod()` |
| S7 | `S7 · Registro en consola` | [servidor/funciones/S7_consola.js](../node-red/servidor/funciones/S7_consola.js) | `node.log()` |

Los archivos `X*` son **comunes a ambas placas** (mismo código en el servidor y
en el cliente), igual que el único `main.py` de esclavo de la Tarea 1.
