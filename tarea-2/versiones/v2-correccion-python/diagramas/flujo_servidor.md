# Diagrama de flujo — Servidor (Raspberry Pi 1, `servidor.py`)

Requerimiento adicional 2 de la consigna. Los bloques **S1…S7** están marcados
con el mismo nombre en el código (requerimiento adicional 3).

El servidor no es un bucle único: después de arrancar corren **tres tareas
concurrentes** (S3, S4, S7) y **un manejador por evento** (S5 → S6) que asyncua
llama cuando un cliente escribe.

```mermaid
flowchart TD
    A([Inicio]) --> S1["S1 · Inicialización<br/>argumentos · certificados pki/own<br/>3 endpoints · lista de confianza<br/>usuarios (hash de OPCUA_CLAVE_HASH) y roles"]
    S1 --> C{¿Existen los<br/>certificados?}
    C -- No --> E([Fin: ejecutar generar_certificados.py])
    C -- Sí --> S2["S2 · Espacio de direcciones<br/>ApplicationUri = urn:unraf:pdci:t2 → ns=1<br/>Objects/Servidor y Objects/Cliente<br/>4 variables con NodeId fijo · EURange<br/>Cliente.* escribibles"]
    S2 --> R["Arranque: escucha en 0.0.0.0:4840"]
    R --> T3 & T4 & T7 & EV

    subgraph T3 [Tarea S3 · cada 50 ms]
        S3a{"--rampa-detenida?"} -- Sí --> S3z([Servidor.Rampa queda en 0])
        S3a -- No --> S3b["valor = sierra(t) 0..65535, período 4 s"] --> S3c["Write Servidor.Rampa<br/>(SourceTimestamp = ahora)"] --> S3d["esperar hasta t + 50 ms"] --> S3b
    end

    subgraph T4 [Tarea S4 · por evento GPIO]
        S4a["leer pulsador GPIO17"] --> S4b["Write Servidor.EstadoPulsador"] --> S4c["esperar flanco<br/>(gpiozero when_pressed / when_released)<br/>imprime LATENCIA pulsador_local"] --> S4a
    end

    subgraph EV [S5 · Atención de escrituras · por evento PostWrite]
        S5a["un cliente escribió (WriteRequest aceptado)"] --> S5b{"¿qué NodeId?"}
        S5b -- Cliente.EstadoPulsador --> S6a["S6 · LED digital GPIO27 = valor<br/>imprime LATENCIA led_digital"]
        S5b -- Cliente.Rampa --> S6b["S6 · LED PWM GPIO18<br/>duty = valor·255/65535 (gamma opcional)<br/>guarda SourceTimestamp"]
        S5b -- otro / rechazado --> S5c([sin acción])
    end

    subgraph T7 [Tarea S7 · cada 0,5 s]
        S7a["imprimir: rampa generada · Cliente.Rampa recibida,<br/>PWM 0-255 y su SourceTimestamp · pulsadores"]
    end
```

## Trazabilidad diagrama ↔ código

| Bloque | Función en [servidor.py](../servidor.py) | Consigna |
|---|---|---|
| S1 | `leer_argumentos`, `configurar_seguridad`, `GestorUsuarios`, `ReglasPorRol`, `ListaDeConfianza`, `clave_valida` | 2.1, 4.7, 4.8, 4.9 |
| S2 | `crear_modelo`, `agregar_eurange` | 2.2 |
| S3 | `tarea_rampa` (+ `comun.rampa_diente_sierra`) | 2.3, 3.4 (rampa detenida) |
| S4 | `tarea_pulsador` (+ `comun.Pulsador`) | 2.2 (origen del dato) |
| S5 | `crear_atencion_escrituras` → `al_escribir` | 2.4, 2.5 |
| S6 | `comun.Salidas.led_digital`, `comun.Salidas.led_pwm`, `comun.escalar_a_pwm` | 2.4, 3.7 |
| S7 | `tarea_consola` | 3.5 |

## Diferencias con la versión original (`servidor_ns1.py`)

| Antes | Ahora | Por qué |
|---|---|---|
| Un bucle de 50 ms hacía todo (sondeo) | Tareas concurrentes + evento de escritura | El LED reacciona al Write, no hasta 50 ms después; el pulsador no pierde pulsaciones breves |
| `sleep(0.05)` fijo | Programación sobre tiempos absolutos | Sin deriva del período |
| Solo endpoint None; cualquier usuario y clave aceptados | 3 endpoints, confianza de certificados, hash scrypt, anónimo de solo lectura | Parte 4 (4.7–4.9) |
| Consola sin SourceTimestamp | Con SourceTimestamp del dato recibido | Consigna 3.5 |
