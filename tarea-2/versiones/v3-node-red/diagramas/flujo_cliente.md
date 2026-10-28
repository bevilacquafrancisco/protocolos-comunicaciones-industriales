# Diagrama de flujo — Cliente OPC UA (Raspberry Pi 2)

**Autores:** Bevilacqua Francisco, Peralta Agustina

Cumple el requerimiento adicional 2 de la consigna: diagrama de flujo del
cliente (conexión, suscripción, manejo de notificaciones, escrituras y
reconexión ante pérdida del canal). La trazabilidad con el código está en §3.

## 1. Vista general

```mermaid
flowchart LR
    subgraph Disparadores
        T50["⏱ cada 50 ms"]
        T100["⏱ cada 100 ms"]
        GPIO["⚡ flanco en GPIO17"]
        NOTIF["🌐 PublishResponse /<br/>ReadResponse"]
        T1S["⏱ cada 1 s"]
    end
    T50 --> C2["C2 · Rampa triangular"]
    T100 --> C5R["C5 · Escribir rampa"]
    GPIO --> C5P["C5 · Leer pulsador<br/>+ solo al cambiar"]
    C2 -. "flow.rampaGenerada" .-> C5R
    C5R --> C1["C1 · Cliente OPC UA"]
    C5P --> C1
    NOTIF --> C1
    C1 --> C4["C4 · Replicar en LEDs"]
    C1 --> C7["C7 · Eventos de conexión"]
    T1S --> C6["C6 · Registro en consola"]
    C1 <-. "opc.tcp://192.168.10.1:4840<br/>por eth0" .-> SRV(["Servidor OPC UA"])
```

## 2. Bloques en detalle

```mermaid
flowchart TB
    INICIO([Arranque de Node-RED]) --> C0["C0 · Verificar configuración<br/>LEDs en estado seguro"]
    INICIO --> C1A

    subgraph C1g["C1 · Conexión (On Start, en segundo plano)"]
        C1A{"¿autenticación<br/>'usuario'?"} -->|sí| C1U{"¿OPCUA_CLIENTE_USUARIO<br/>y _CLAVE en el entorno?"}
        C1U -->|no| C1X["Error explícito<br/>sin conectar"]
        C1U -->|sí| C1B
        C1A -->|no, anónimo| C1B["connect(opc.tcp://192.168.10.1:4840)<br/>HEL/ACK · OPN · GetEndpoints"]
        C1B --> C1C["CreateSession + ActivateSession"]
        C1C --> C1D["Leer NamespaceArray (ns=0;i=2255)<br/>ns = índice de urn:unraf:pdci:t2"]
        C1D --> C1E{"config.lectura.modo"}
        C1B -.->|falla| C1F["Estado rojo<br/>reintento en 5 s"] -.-> C1A
        C1C -.->|falla| C1Z["disconnect()<br/>(evita el cliente zombi, I-04)"] -.-> C1F
    end

    C1E -->|A| C3A
    C1E -->|B| C3B

    subgraph C3ag["C3a · Modo A: Read periódico"]
        C3A["cada 100 ms"] --> C3A1{"¿Read anterior<br/>pendiente o<br/>reconectando?"}
        C3A1 -->|sí| C3A2["omitir y contar"]
        C3A1 -->|no| C3A3["ReadRequest(maxAge 0)<br/>Servidor.EstadoPulsador, Servidor.Rampa"]
    end

    subgraph C3bg["C3b · Modo B: suscripción"]
        C3B["CreateSubscription<br/>PublishingInterval 100 ms<br/>KeepAlive 10 · Lifetime 300"] --> C3B2["CreateMonitoredItems (1 petición, 2 ítems)<br/>SamplingInterval 100 ms · QueueSize 1<br/>DiscardOldest true"]
        C3B2 --> C3B3["registrar valores REVISADOS"]
        C3B3 --> C3B4["PublishRequest en cola<br/>(el servidor responde cuando hay datos<br/>o cada 1 s con un KeepAlive)"]
    end

    C3A3 --> C4A
    C3B4 --> C4A
    subgraph C4g["C4 · Manejo de notificaciones / respuestas"]
        C4A{"¿StatusCode == Good?"} -->|no| C4N["no aplicar · LED congelado"]
        C4A -->|sí| C4B{"variable"}
        C4B -->|servidorPulsador| C4D["LED digital GPIO27<br/>(si cambia: log 'LATENCIA led_digital' + hora)"]
        C4B -->|servidorRampa| C4P["escala255 → LED PWM GPIO18"]
    end

    subgraph C5g["C5 · Escrituras"]
        C5A["pulsador: solo al cambiar (rbe)"] --> C5C
        C5P{"¿rampa detenida?<br/>(botones C5 · Detener /<br/>Reanudar rampa)"} -->|no| C5B["rampa: cada 100 ms"]
        C5P -->|sí| C5Q["no escribe"]
        C5B --> C5C{"¿Write anterior<br/>de esa variable pendiente<br/>o reconectando?"}
        C5C -->|sí| C5O["omitir y contar<br/>(se escribe el valor VIGENTE,<br/>no una cola vieja)"]
        C5C -->|no| C5W["WriteRequest → Cliente.*"]
    end

    subgraph C7g["C7 · Pérdida y recuperación del canal"]
        C7A["connection_lost"] --> C7B["backoff: reintento cada 1 → 5 s<br/>(sin límite)"]
        C7B --> C7C["connection_reestablished<br/>nuevo canal seguro (OPN)"]
        C7C --> C7D{"¿pasaron menos de<br/>30 s (lifetime)?"}
        C7D -->|sí| C7E["la sesión y la suscripción<br/>sobreviven: republish"]
        C7D -->|no| C7F["la suscripción expiró:<br/>se transfiere o recrea"]
        C7E --> C7G["after_reconnection<br/>vuelven las notificaciones"]
        C7F --> C7G
    end
```

Mientras el canal está caído no llegan datos: **C4 no recibe nada y los LED
quedan congelados en su último valor**, y el generador local (C2) sigue
funcionando. Es exactamente el comportamiento que pide la Parte 3.6, y sale del
diseño sin código adicional. C6 lo hace visible en la consola: la
`antiguedad` del último dato crece segundo a segundo.

Los umbrales de 30 s (suscripción) y 60 s (sesión) de C7 salen de
`config.suscripcion`. La prueba de desconexión de la Parte 3.6 se hace dos
veces, con cortes de menos y de más de 30 s, para observar las dos ramas.

## 3. Trazabilidad diagrama ↔ código

| Bloque | Function node en Node-RED | Archivo con el código | Función de biblioteca |
|---|---|---|---|
| C0 | `C0 · Verificar configuracion` | [comun/funciones/X1_verificar_config.js](../node-red/comun/funciones/X1_verificar_config.js) | — |
| C1 | `C1 · Cliente OPC UA` (On Start) | [cliente/funciones/C1_cliente_opcua.inicio.js](../node-red/cliente/funciones/C1_cliente_opcua.inicio.js) | `iniciarCliente()`, `prepararSesion()` en [cliente_opcua.js](../node-red/cliente/cliente_opcua.js) |
| C2 | `C2 · Generar rampa triangular` | [cliente/funciones/C2_generar_rampa.js](../node-red/cliente/funciones/C2_generar_rampa.js) | `senales.triangular()` |
| C3a / C3b | (dentro de C1) | `cliente_opcua.js`, bloques C3a y C3b | `session.read()`, `createSubscription2()`, `ClientMonitoredItemGroup.create()` |
| C4 | `C4 · Replicar en LEDs`, `C4 · LED digital`, `C4 · LED PWM` | [cliente/funciones/C4_replicar.js](../node-red/cliente/funciones/C4_replicar.js), [comun/funciones/X6_*.js](../node-red/comun/funciones/) | `senales.escala255()` |
| C5 | `C5 · Leer pulsador`, `C5 · Solo al cambiar`, `C5 · Escribir rampa`, botones `C5 · Detener/Reanudar rampa`; escritura en `C1` (On Message) | [comun/funciones/X4_leer_pulsador.js](../node-red/comun/funciones/X4_leer_pulsador.js), [cliente/funciones/C5_escribir_rampa.js](../node-red/cliente/funciones/C5_escribir_rampa.js), [C1_cliente_opcua.js](../node-red/cliente/funciones/C1_cliente_opcua.js) | `session.write()` |
| C6 | `C6 · Registro en consola` | [cliente/funciones/C6_consola.js](../node-red/cliente/funciones/C6_consola.js) | `node.log()` |
| C7 | `C7 · Eventos de conexion` | [cliente/funciones/C7_eventos.js](../node-red/cliente/funciones/C7_eventos.js) | eventos `connection_lost`, `backoff`, `after_reconnection` de `OPCUAClient` |
