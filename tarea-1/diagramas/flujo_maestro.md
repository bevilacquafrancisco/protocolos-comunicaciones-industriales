# Diagrama de flujo — Maestro MODBus RTU

**Autores:** Bevilacqua Francisco, Peralta Agustina

Cumple el requerimiento adicional 1 de la consigna ("máquina de estados, ciclo de
polling, conmutación de esclavo") y el requerimiento 2 ("trazabilidad de código":
cada bloque nombra la función de [firmware/maestro/main.py](../firmware/maestro/main.py)
que lo implementa).

## 1. Máquina de estados

```mermaid
stateDiagram-v2
    direction TB

    [*] --> M1

    M1: M1 · INICIO Y CONFIGURACIÓN
    note right of M1
        configurar_perifericos()
        configurar_maestro_modbus()
        Salidas en estado seguro (apagadas)
    end note

    M1 --> M2

    M2: M2 · LEER_SELECTOR
    note right of M2
        _accion_leer_selector()
        Muestrea GPIO13 UNA vez por ciclo
        abierto = ID 1 · a GND = ID 2
    end note

    M2 --> M3

    M3: M3 · INDICAR_SELECCION
    note right of M3
        _accion_indicar_seleccion()
        LED22 = (ID==1) · LED23 = (ID==2)
        Mutuamente excluyentes por diseño
    end note

    M3 --> M4

    M4: M4 · LEER_DI_REMOTO
    note right of M4
        _accion_leer_di_remoto()
        Función 0x02 · offset 0x0000
        Replica en LED digital local (GPIO19)
    end note

    M4 --> M5: respuesta OK
    M4 --> M9: timeout o excepción

    M5: M5 · LEER_IR_REMOTO
    note right of M5
        _accion_leer_ir_remoto()
        Función 0x04 · offset 0x0000
        adc_a_pwm() y replica en PWM local (GPIO21)
    end note

    M5 --> M6: respuesta OK
    M5 --> M9: timeout o excepción

    M6: M6 · ESCRIBIR_COIL_REMOTO
    note right of M6
        _accion_escribir_coil_remoto()
        Función 0x05 · 0xFF00 / 0x0000
        Origen: switch local (GPIO18)
    end note

    M6 --> M7: eco OK
    M6 --> M9: timeout o excepción

    M7: M7 · ESCRIBIR_HREG_REMOTO
    note right of M7
        _accion_escribir_hreg_remoto()
        Función 0x06 · valor 0-255
        Origen: potenciómetro local (GPIO34)
        Ciclo completo: fallos = 0
    end note

    M7 --> M8

    M9: M9 · REGISTRAR FALLO
    note right of M9
        _registrar_fallo()
        Incrementa contador y lo informa.
        Tras 3 ciclos seguidos, apaga los
        replicadores locales (no congelarlos)
    end note

    M9 --> M8

    M8: M8 · ESPERA
    note right of M8
        _accion_espera()
        No bloqueante, con ticks_diff()
        Cierra el período de 200 ms
    end note

    M8 --> M8: período no cumplido
    M8 --> M2: período cumplido
```

## 2. Ciclo de polling en el tiempo

Muestra por qué el período es de 200 ms y no de 100 ms — ver el cálculo completo
en `PERIODO_SONDEO_MS` de [firmware/comun/config.py](../firmware/comun/config.py).

```mermaid
sequenceDiagram
    autonumber
    participant M as Maestro
    participant B as Bus RS-485
    participant E1 as Esclavo 1
    participant E2 as Esclavo 2

    Note over M: M2 · lee selector → ID activo = 1
    Note over M: M3 · enciende LED indicador 1

    M->>B: 01 02 00 00 00 01 B9 CA
    B->>E1: (E2 recibe la trama y la descarta: no es su ID)
    E1-->>M: 01 02 01 01 60 48
    Note over M: M4 · replica el switch remoto en LED19

    M->>B: 01 04 00 00 00 01 31 CA
    E1-->>M: 01 04 02 08 00 [CRC]
    Note over M: M5 · adc_a_pwm(2048)=128 → PWM21

    M->>B: 01 05 00 00 FF 00 [CRC]
    E1-->>M: eco idéntico
    Note over E1: Coil 00001 = ON → LED19 del esclavo

    M->>B: 01 06 00 00 00 80 [CRC]
    E1-->>M: eco idéntico
    Note over E1: HR 40001 = 128 → PWM21 del esclavo

    Note over M: M8 · espera hasta completar 200 ms
    Note over E2: Sin tramas dirigidas a él:<br/>RETIENE su último estado
```

## 3. Por qué una máquina de estados y no una secuencia lineal

| Criterio | Secuencia lineal con `if` | Máquina de estados explícita |
|---|---|---|
| Correspondencia con el diagrama pedido | Difusa, hay que reconstruirla | Uno a uno, verificable |
| Bloqueo ante esclavo caído | El lazo entero queda detenido tras 4 timeouts encadenados | Se aborta el ciclo en el primer fallo y se vuelve a ESPERA |
| Agregar un tercer esclavo o transacción | Toca la lógica existente | Se agrega un estado y una entrada en la tabla de despacho |
| Instrumentación para depurar | Hay que sembrar prints por todo el código | Un único print en `ejecutar_paso()` traza todo el ciclo |

El costo es unas 40 líneas más de código y un nivel más de indirección (la tabla
`_acciones`). Se acepta porque el requerimiento 1 de la consigna pide
explícitamente representar el maestro como máquina de estados, y porque el
comportamiento ante fallo — no bloquearse — es un requisito de un sistema de
control, no un lujo.

## 4. Estados de falla y degradación

```mermaid
flowchart TD
    A[Transacción emitida] --> B{¿Hubo respuesta<br/>antes de 300 ms?}
    B -- No --> C[TIMEOUT<br/>El esclavo no contestó]
    B -- Sí --> D{¿El código de función<br/>tiene el bit 7 en 1?}
    D -- Sí --> E[EXCEPCIÓN MODBUS<br/>El esclavo está vivo<br/>pero rechaza la petición]
    D -- No --> F{¿CRC correcto?}
    F -- No --> G[TRAMA CORRUPTA<br/>Se descarta]
    F -- Sí --> H[Transacción válida<br/>fallos_consecutivos = 0]

    C --> I[_registrar_fallo]
    E --> I
    G --> I

    I --> J{¿3 ciclos seguidos<br/>con fallo?}
    J -- No --> K[Continuar el ciclo<br/>Replicadores sin cambios]
    J -- Sí --> L[Apagar replicadores locales<br/>Una indicación congelada<br/>engaña más que ninguna]

    K --> M[ESPERA]
    L --> M
    H --> M
```

**Distinción que conviene tener clara para la defensa:** un timeout y una
excepción MODBus son diagnósticos opuestos. El timeout apunta a la capa física o
al direccionamiento (cable, terminación, Unit ID equivocado, esclavo sin
alimentación). La excepción prueba que el esclavo está vivo, escuchó, verificó el
CRC y decidió rechazar: el problema está en la petición (dirección inexistente,
valor fuera de rango, función no implementada). Confundirlos hace perder horas
revisando el cableado cuando el error está en el mapa de registros.

**Importante:** la degradación afecta solo a los replicadores **locales del
maestro**. Las salidas de los esclavos conservan su último valor recibido, que es
exactamente lo que exige la Parte 3.
