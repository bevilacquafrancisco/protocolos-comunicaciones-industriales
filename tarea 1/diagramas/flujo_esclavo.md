# Diagrama de flujo — Esclavo MODBus RTU

Cada bloque nombra la función de [firmware/esclavo/main.py](../firmware/esclavo/main.py)
que lo implementa (requerimiento adicional 2 de la consigna: trazabilidad de código).

## 1. Flujo del esclavo

```mermaid
flowchart TD
    INICIO([Encendido / reset]) --> E1

    E1["<b>E1 · CONFIGURACIÓN</b><br/>configurar_perifericos()<br/>Switch, ADC, LED digital, LED PWM<br/>Salidas en estado seguro: apagadas"]
    E1 --> E2

    E2["<b>E2 · LEER JUMPER DE UNIT ID</b><br/>leer_unit_id()<br/>GPIO13 con pull-up<br/>abierto → ID 1 · a GND → ID 2<br/><i>Se lee UNA sola vez, en el arranque</i>"]
    E2 --> E1b

    E1b["<b>E1 · LEVANTAR SERVIDOR MODBUS</b><br/>configurar_servidor_modbus(unit_id)<br/>UART2 · 9600 8N1 · DE/RE en GPIO4<br/>Alta de COILS, HREGS, ISTS, IREGS"]
    E1b --> E3

    subgraph LAZO ["LAZO PRINCIPAL — Bloque E6, función main()"]
        direction TB

        E3["<b>E3 · PUBLICAR ENTRADAS FÍSICAS</b><br/>publicar_entradas()<br/>set_ist(0, switch antirrebotado) → DI 10001<br/>set_ireg(0, ADC promediado 0-4095) → IR 30001"]

        E3 --> E4

        E4["<b>E4 · ATENDER EL BUS</b><br/>cliente.process()<br/>Escucha el UART; si llega una trama<br/>dirigida a MI Unit ID, la valida y responde.<br/>Las dirigidas a otro ID se descartan."]

        E4 --> D1

        D1{"¿La trama era<br/>una escritura?"}
        D1 -- "0x05 → Coil<br/>0x06 → HReg" --> E4b["El servidor actualiza<br/>su memoria interna"]
        D1 -- "Lectura o<br/>nada" --> E5
        E4b --> E5

        E5["<b>E5 · APLICAR SALIDAS FÍSICAS</b><br/>aplicar_salidas()<br/>get_coil(0) → LED digital GPIO19<br/>get_hreg(0) → LED PWM GPIO21"]

        E5 --> E3
    end
```

## 2. Cómo se cumple la retención de estado (Parte 3)

La consigna exige que "el esclavo que no esté seleccionado mantenga el último
estado recibido en sus salidas hasta recibir una nueva orden". **No hace falta
escribir ninguna lógica de retención**: es una propiedad del modelo de datos de
MODBus, no un añadido del firmware.

```mermaid
flowchart LR
    subgraph MEM ["Memoria del servidor MODBus"]
        C["Coil 0x0000<br/>último valor escrito"]
        H["HReg 0x0000<br/>último valor escrito"]
    end

    BUS["Trama 0x05 / 0x06<br/>dirigida a MI Unit ID"] -->|"única vía de cambio"| C
    BUS -->|"única vía de cambio"| H

    C -->|"cada vuelta del lazo<br/>aplicar_salidas()"| LED1["LED digital<br/>GPIO19"]
    H -->|"cada vuelta del lazo<br/>aplicar_salidas()"| LED2["LED PWM<br/>GPIO21"]

    NOSEL["Maestro hablando<br/>con el OTRO esclavo"] -.->|"no llega ninguna trama<br/>para este nodo"| MEM
```

Lo que sí depende del firmware es el requisito **complementario**: no
reinicializar esos registros dentro del lazo. Por eso los valores iniciales se
fijan una única vez, en `configurar_servidor_modbus()`, y nunca dentro de `main()`.
Un firmware que pusiera `set_coil(0, False)` en cada vuelta apagaría el LED
constantemente y rompería la retención — es el error típico en esta consigna.

## 3. Qué hace el esclavo cuando la trama no es para él

```mermaid
sequenceDiagram
    participant B as Bus RS-485
    participant E1 as Esclavo 1 (ID=1)
    participant E2 as Esclavo 2 (ID=2)

    B->>E1: 02 06 00 00 00 80 [CRC]
    B->>E2: 02 06 00 00 00 80 [CRC]

    Note over E1: Byte 0 = 0x02 ≠ mi ID (1)<br/>DESCARTA en silencio.<br/>No responde: si respondiera,<br/>colisionaría con el Esclavo 2
    Note over E2: Byte 0 = 0x02 = mi ID<br/>Verifica CRC → OK<br/>HReg 0x0000 = 128<br/>Responde con el eco

    E2-->>B: 02 06 00 00 00 80 [CRC]

    Note over E1: Sus salidas siguen<br/>con el último valor recibido
```

Todos los nodos del bus reciben **eléctricamente** todas las tramas: RS-485 es un
medio compartido, no conmutado. El filtrado por Unit ID es una decisión de
software del esclavo. Que un solo nodo responda por vez es lo que evita las
colisiones en un bus half-duplex, y por eso el modelo maestro-esclavo por sondeo
no necesita ningún mecanismo de arbitraje: el turno de palabra lo otorga el
maestro al dirigir la petición.

## 4. Por qué el lazo del esclavo no tiene espera

A diferencia del maestro, el lazo del esclavo **no** lleva un `sleep`. El ritmo lo
impone el maestro: `process()` consume el tiempo que haga falta escuchando el
UART y retorna en cuanto atiende una trama o vence su timeout interno.

Agregar una espera reduciría la fracción de tiempo en que el esclavo está
efectivamente escuchando el bus. Si la trama del maestro llega durante ese
`sleep`, los bytes se acumulan en el buffer del UART y el silencio entre ellos ya
no se puede medir: se viola la delimitación por t1,5/t3,5 y la trama se descarta.
El síntoma sería "el esclavo responde a veces sí y a veces no", uno de los más
difíciles de diagnosticar sin analizador lógico.

## 5. Orden de las operaciones dentro del lazo

El orden `publicar entradas → atender bus → aplicar salidas` no es arbitrario:

| Orden | Consecuencia |
|---|---|
| Publicar **antes** de `process()` (elegido) | La respuesta lleva el valor más reciente del switch y del ADC |
| Publicar **después** de `process()` | Cada respuesta llevaría el valor del ciclo anterior: se agregaría un período de sondeo completo (200 ms) de retardo, sin ningún beneficio |
| Aplicar salidas **después** de `process()` (elegido) | Una escritura recibida en este ciclo se refleja en el hardware de inmediato |
| Aplicar salidas **antes** de `process()` | Una orden recibida tardaría una vuelta completa en verse en el LED |
