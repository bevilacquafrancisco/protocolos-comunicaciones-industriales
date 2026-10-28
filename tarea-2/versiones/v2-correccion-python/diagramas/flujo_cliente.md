# Diagrama de flujo — Cliente (Raspberry Pi 2, `cliente.py` y `cliente_suscripcion.py`)

Requerimiento adicional 2 de la consigna. Los bloques **C1…C7** están marcados
con el mismo nombre en el código. Los dos programas comparten todo salvo **C3**
(cómo se lee el servidor), que es justamente lo que la consigna 3.4 compara.

```mermaid
flowchart TD
    A([Inicio]) --> F["Tareas de fondo, durante TODO el programa:<br/>C2 · rampa triangular cada 50 ms<br/>C6 · consola cada 0,5 s"]
    F --> C1["C1 · Conexión a opc.tcp://192.168.10.1:4840 (eth0)<br/>seguridad None / Sign / SignAndEncrypt<br/>usuario del entorno o anónimo<br/>HEL/ACK · OPN · CreateSession · ActivateSession"]
    C1 -- error --> C7
    C1 -- sesión activa --> P["Tareas de la sesión, en paralelo"]
    P --> C3 & C5a & C5b & W

    subgraph C3 [C3 · Lectura del servidor]
        direction TB
        A3{"programa"}
        A3 -- "cliente.py (Modo A)" --> A3a["Read de Servidor.EstadoPulsador<br/>y Servidor.Rampa en UN pedido"] --> A3b["C4 · replicar"] --> A3c["esperar hasta t + 100 ms"] --> A3a
        A3 -- "cliente_suscripcion.py (Modo B)" --> B3a["CreateSubscription 100 ms<br/>KeepAlive 10 · Lifetime 300"] --> B3b["CreateMonitoredItems (2 ítems)<br/>Sampling 100 ms · QueueSize 1"] --> B3c["esperar notificaciones"]
        B3c -. "PublishResponse con datos" .-> B3d["datachange_notification → C4 · replicar"]
        B3c -. "cambio de estado" .-> B3e["status_change_notification → imprimir StatusCode"]
    end

    subgraph C4 [C4 · Replicar]
        R1["Servidor.EstadoPulsador → LED digital GPIO27<br/>(LATENCIA led_digital si cambió)"]
        R2["Servidor.Rampa → LED PWM GPIO18, 0-255"]
    end

    subgraph C5 [C5 · Escrituras]
        C5a["Cliente.EstadoPulsador:<br/>al conectar y en cada flanco del pulsador"]
        C5b["Cliente.Rampa cada 100 ms<br/>(se omite con --sin-escritura)"]
        C5c["rechazo del servidor (p. ej. anónimo):<br/>imprimir StatusCode, la sesión sigue"]
    end

    W["Aviso de pérdida del canal<br/>(watchdog de asyncua: lee ServerStatus cada 1 s)"]

    C3 -- "error de transporte" --> C7
    C5 -- "error de transporte" --> C7
    W -- "sin respuesta" --> C7
    C7["C7 · Reconexión<br/>cancelar tareas de la sesión · LED quedan congelados<br/>imprimir StatusCode o error de transporte<br/>esperar 2 s"] --> C1
```

## Trazabilidad diagrama ↔ código

| Bloque | Dónde | Consigna |
|---|---|---|
| C1 | [cliente_base.py](../cliente_base.py) `conectar`, `nodos_del_modelo` | 3.1, 4.7, 4.9 |
| C2 | `cliente_base.tarea_rampa` (+ `comun.rampa_triangular`) | 3.2 |
| C3 Modo A | [cliente.py](../cliente.py) `leer_por_polling` | 3.3, 3.4 |
| C3 Modo B | [cliente_suscripcion.py](../cliente_suscripcion.py) `leer_por_suscripcion`, `ManejadorSuscripcion` | 3.3, 3.4 |
| C4 | `cliente_base.replicar` (+ `comun.Salidas`) | 3.3, 3.6 (congelar) |
| C5 | `cliente_base.Escritor`, `tarea_escribir_pulsador`, `tarea_escribir_rampa` | 3.3 |
| C6 | `cliente_base.tarea_consola` | 3.5 |
| C7 | `cliente_base.ejecutar_sesion`, `correr_hasta_falla`, `main` | 3.6 |

## Diferencias con la versión original

| Antes | Ahora | Por qué |
|---|---|---|
| Modo A: dos Read de un nodo | Un Read con los dos nodos | No duplicar el tráfico del Modo A (comparación justa) |
| Suscripción con los valores por defecto de asyncua (KeepAlive 4500 = 7,5 min) | KeepAlive 10, Lifetime 300, revisados impresos | Ver KeepAlive en 60 s (3.4) y explicar la vida de la suscripción |
| Generador local y consola dentro de la sesión | Tareas de fondo | Durante el corte la rampa local sigue y se ve en consola (3.6) |
| Solo el tipo de excepción | StatusCode del servidor o error de transporte, con hora | Consigna 3.6 |
| Lectura inicial antes de suscribir | Eliminada | El servidor siempre envía la notificación inicial |
| Pulsador sondeado cada 100 ms | Evento de gpiozero | Latencia medible (3.4) |
