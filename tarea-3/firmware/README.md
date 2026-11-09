# Firmware del dispositivo 1 — esclavo MODBus RTU con stack propio

Tarea Nº3 · Fase F2 · ESP32 + MAX485 · MicroPython con el IDE Thonny (ADR-010)

Es el esclavo de la Tarea Nº1 con la capa de protocolo **reescrita**: ya no usa `umodbus`. El
CRC-16, la delimitación de tramas por silencio t3,5, el despacho de funciones y las excepciones
son código propio (invariante **I-01**). El mismo firmware hace también de **esclavo
desconocido** para ensayar la configuración en vivo del maestro (ADR-007).

**Estado:** probado en la PC (169 verificaciones, más compilación con `mpy-cross` para ESP32).
**Falta verificarlo en el banco** (§7).

---

## 1. Qué cumple

| Requisito | Dónde |
|---|---|
| Stack propio, sin biblioteca de protocolo (I-01) | `esclavo-modbus/lib/modbus_slave/` no importa nada externo; `prueba_config.py` verifica que no importe `machine` |
| CRC-16/MODBUS: polinomio 0xA001 reflejado, inicial 0xFFFF; verificado al recibir y generado al transmitir | `crc16.py` · `verificar_crc()` [DF-1.9], `agregar_crc()` [DF-1.15] |
| FC 01, 02, 03, 04, 05, 06 | `frame_parser._ejecutar()` [DF-1.10] a [DF-1.12] |
| Excepciones 01, 02, 03 y 04 | `frame_parser.procesar_trama()` [DF-1.13] |
| Fin de trama por silencio t3,5 **calculado del baud rate** | `frame_parser.tiempos_us()` [DF-1.2]; fórmula en su docstring |
| DE/RE con vaciado del buffer de transmisión antes de soltar la línea | `main.Esclavo.transmitir()` [DF-1.16]: `uart.flush()` + 1 t_car |
| ID ajeno y distinto de 0: descarte en silencio | `procesar_trama()` [DF-1.8] |
| Difusión (ID 0): ejecuta las escrituras y no responde | `procesar_trama()` [DF-1.14] |
| Mapa, Unit ID, baud y paridad en un solo lugar | `esclavo-modbus/src/config.py` |

La numeración `[DF-1.x]` es la de [docs/diagramas/flujo-esclavo.mmd](../docs/diagramas/flujo-esclavo.mmd);
cada función la cita en su comentario.

## 2. Estructura

```
firmware/esclavo-modbus/
├── lib/modbus_slave/          ← stack de protocolo, SIN dependencias del hardware
│   ├── __init__.py            VERSION de la interfaz (main.py la verifica al arrancar)
│   ├── crc16.py               CRC por tabla (firmware) y bit a bit (referencia)
│   ├── frame_parser.py        tiempos t1,5/t3,5 · EnsambladorTramas · procesar_trama()
│   └── data_model.py          las cuatro tablas y sus reglas de acceso
├── src/                       ← lo que va a la raíz del ESP32
│   ├── main.py                capa de hardware: UART2, DE/RE, GPIO, ADC, PWM y lazo
│   ├── config.py              perfiles DISPOSITIVO_1 y DESCONOCIDO, pines, parámetros
│   └── perifericos.py         HAL de la Tarea 1, copiada SIN cambios (verificada en banco)
└── test/                      ← pruebas en la PC con CPython, sin placa
    ├── correr_todo.py
    ├── prueba_crc.py          vectores golden (tarea-3/tests/fixtures/crc_vectors.json)
    ├── prueba_frame_parser.py casos de plan-de-pruebas §N1.2, tiempos, delimitación
    ├── prueba_data_model.py   límites, desbordes, direcciones fuera de rango
    └── prueba_config.py       perfiles, pines, I-06, compilación con mpy-cross
```

Los vectores del CRC los genera `tarea-3/tools/generar_vectores_crc.py` con **pymodbus 3.8.6
como oráculo** y la rutina de la Tarea 1 como segundo oráculo; el script aborta si discrepan. Son
los mismos que va a usar el maestro en JavaScript (F3).

## 3. Conexionado

Idéntico a la Tarea 1 ([tarea-1/docs/arquitectura.md §7-§8](../../tarea-1/docs/arquitectura.md)):
las placas ya cableadas no se tocan.

### 3.1 ESP32 ↔ MAX485 ↔ bus

| ESP32 | Pin MAX485 | Conexión | Por qué |
|---|---|---|---|
| GPIO 17 (UART2 TX) | DI | Directa | VIH del MAX485 ≥ 2,0 V; el ESP32 entrega 3,3 V |
| GPIO 16 (UART2 RX) | RO | **Divisor 2,2 kΩ (serie) / 3,3 kΩ (a GND) + pull-up 680 Ω de RO a 5 V** | RO entrega ≈ 5 V y el GPIO admite 3,6 V como máximo absoluto. Sin el pull-up, al transmitir RO queda en alta impedancia y el divisor genera bytes `0x00` espurios (incidente 4 de la T1) |
| GPIO 4 | DE y RE unidos | Directa | 1 = transmite, 0 = escucha |
| 5 V (VIN) | VCC | — | El MAX485 es de 5 V |
| GND | GND | — | **Masa común con todos los nodos del bus** |
| — | A, B | Par trenzado al bus | A con A, B con B en todos los nodos |

```
                         5 V
                          │
                       [680 Ω]
                          │
  MAX485 RO ──────────────┴──[2,2 kΩ]──┬──[3,3 kΩ]── GND
                                       │
                                    GPIO 16 (RX)
```

### 3.2 Periféricos y selección de perfil

| Señal | GPIO | Conexión | Variable MODBus (perfil DISPOSITIVO_1) |
|---|---|---|---|
| Pulsador | 18 | A GND; pull-up interno; activo en bajo | Discrete Input 10001 (0x0000) |
| Potenciómetro | 34 (ADC1_CH6) | Cursor al pin; extremos a 3,3 V y GND | Input Register 30001 (0x0000), 0-4095 crudo |
| LED digital | 19 | Ánodo al pin, 330 Ω a GND | Coil 00001 (0x0000) |
| LED PWM | 21 | Ánodo al pin, 330 Ω a GND | Holding Register 40001 (0x0000), 0-255 |
| Jumper de perfil | 13 | Abierto = DISPOSITIVO_1 · a GND = DESCONOCIDO | — |

**Cambio respecto de la T1:** el jumper de GPIO 13 elegía el Unit ID (1 o 2); ahora elige el
**perfil**. Así las dos placas siguen cargando exactamente los mismos archivos.

### 3.3 Terminación y polarización

No se instalan mientras el bus mida menos de ≈ 1,5 m (longitud crítica del MAX485; la T1 midió
0,0 % de error con 15-40 cm sin terminación). Si el bus crece: 120 Ω solo en los dos extremos y,
junto con ellas, la polarización de 680 Ω en un único punto (informe T1 §5.5-5.6).

## 4. Carga en el ESP32 con Thonny

Requisito: **MicroPython ≥ 1.20** (por `UART.flush()`; `main.py` se niega a arrancar sin él). El
grabado de MicroPython con Thonny está en [tarea-1/firmware/README.md §2](../../tarea-1/firmware/README.md).

1. Conectar la placa y, en Thonny, **Ver → Archivos**.
2. **Borrar del ESP32 lo que quedó de la Tarea 1** que ya no se usa: la carpeta `umodbus` (en
   `/lib` o en `/`) y `diagnostico.py`. Que la biblioteca no esté en la placa es la mejor
   evidencia de I-01 en la defensa.
3. En el ESP32, crear la carpeta `/lib/modbus_slave` y subir ahí los cuatro archivos de
   `esclavo-modbus/lib/modbus_slave/` (clic derecho → **Subir a /lib/modbus_slave**).
4. Subir a la raíz `/` los tres archivos de `esclavo-modbus/src/`: `main.py`, `config.py` y
   `perifericos.py`.
5. Reiniciar con **Ctrl+D**. La consola muestra el perfil, el Unit ID, los parámetros del enlace,
   los tiempos t1,5/t3,5 calculados y el mapa de registros.

Si aparece `lib/modbus_slave desactualizado en esta placa`, falta volver a subir la carpeta
`lib/modbus_slave` (mismo mecanismo de versión que la T1).

> **Antes de subir un archivo editado:** cerrarlo y reabrirlo en Thonny. El editor trabaja sobre
> su propio buffer (lección de la T1).

**"Compilar".** MicroPython interpreta el código en la placa; no hay paso de compilación
obligatorio. Para verificar en la PC que todo es sintaxis válida de MicroPython se usa
`mpy-cross`, el compilador oficial (lo hace `prueba_config.py` si está instalado).

## 5. Pruebas en la PC (sin placa)

```bash
# Desde la raíz del repositorio
python tarea-3/firmware/esclavo-modbus/test/correr_todo.py

# Opcional: con mpy-cross para verificar la compilación para ESP32
pip install -r tarea-3/tools/requirements-dev.txt
python tarea-3/firmware/esclavo-modbus/test/correr_todo.py

# Regenerar los vectores golden (requiere pymodbus)
python tarea-3/tools/generar_vectores_crc.py
```

| Prueba | Verificaciones | Qué cubre |
|---|---|---|
| `prueba_crc.py` | 35 | 23 vectores golden, tabla y bit a bit, orden de bytes, residuo, todos los errores de 1 y 2 bits |
| `prueba_data_model.py` | 48 | Mapa inválido no arranca, rangos, 0xFFFF, excepciones 02 y 03, saturación de entradas |
| `prueba_frame_parser.py` | 57 | Los 8 casos de N1.2, las 6 funciones, excepción 04, difusión, t1,5/t3,5, 20 000 tramas aleatorias |
| `prueba_config.py` | 29 (+7 con mpy-cross) | Perfiles, pines prohibidos, nombres del diccionario (I-06), compilación |

Las cuatro pruebas se validaron con **mutaciones**: alterar una entrada de la tabla del CRC, el
límite de 125 registros, los bits por carácter o la dirección de difusión hace fallar la batería.

## 6. Variante del esclavo desconocido (ADR-007)

El perfil `DESCONOCIDO` de `src/config.py` simula el esclavo que trae la cátedra: hoy es Unit ID
17, 19 200 bps, paridad par, y un mapa en otras direcciones con variables extra (`Inputs/Listo`,
`Inputs/Uptime_s`, `Outputs/Bandera`, `Outputs/Consigna`).

**Para el ensayo a ciegas:**

1. Quien prepara el ensayo edita **solo** el bloque `"DESCONOCIDO"` de `config.py`: Unit ID,
   `baud`, `paridad`, `bits_parada` y las direcciones del `mapa`. No se lo dice a quien opera el
   maestro.
2. Reglas: Unit ID 1-247; **baud ≤ 19 200** (ADR-010: por encima, t1,5 cae por debajo de 0,86 ms
   frente a las pausas del intérprete); cada señal física (`pulsador`, `potenciometro`,
   `led_digital`, `led_pwm`, `uptime_s`) a lo sumo una vez.
3. Correr `python tarea-3/firmware/esclavo-modbus/test/prueba_config.py`: si el mapa quedó mal
   escrito, falla en la PC y no en el ensayo.
4. Subir `config.py` al ESP32 #2 y **puentear GPIO 13 a GND** (o poner `PERFIL = "DESCONOCIDO"`).
5. Poner `NIVEL_LOG = 0`: la consola de arranque muestra el mapa, y el operador del maestro no
   debe verlo.
6. Cronometrar cuánto tarda el maestro en establecer la comunicación (meta: < 3 minutos).

Las dos placas pueden quedar en el bus a la vez: distinto Unit ID, y cada una ignora en silencio
las tramas de la otra. **Ojo:** si tienen distinto baud rate, cada una ve las tramas de la otra
como basura (cuentan en `invalidas` o `crc`); no responde, pero el ensayo es más limpio con una
sola placa conectada.

## 7. Verificación en el banco (pendiente)

| # | Prueba | Criterio |
|---|---|---|
| B-1 | Con QModMaster y el conversor USB-RS485, repetir las 14 pruebas de la T1 (`mapa-registros.md` §9) | 14/14, más excepción 03 al escribir 256 en 40001 |
| B-2 | Sniffer de la T1 (`tarea-1/herramientas/sniffer_rs485.py`) durante B-1 | Todas las respuestas con CRC válido; ninguna trama truncada |
| B-3 | 750 ciclos contra el maestro de F3, perfil DISPOSITIVO_1 | 0,0 % de error, igual que la T1 |
| B-4 | Mismo ensayo con el perfil DESCONOCIDO a 19 200 8E1 | < 1 % de error; si no, reabrir ADR-010 |
| B-5 | Latido con el bus limpio | `invalidas` no crece; si crece, poner `VERIFICAR_T15 = False` y documentarlo como I-NN |

Los resultados van a `docs/resultados-pruebas.md` y los defectos, a un `INCONVENIENTES.md` de la T3.

## 8. Decisiones y limitaciones

| Tema | Decisión | Motivo |
|---|---|---|
| Holding register fuera de rango | **Excepción 03** (en la T1, el PWM saturaba en 255) | Que el maestro lo cuente como `EXCEPTION` y el operador vea que la orden no se cumplió |
| CRC en el firmware | Por tabla (512 B de RAM) | En la T1 el cómputo del intérprete costaba ≈ 12,8 ms por transacción (ADR-010) |
| Tiempos | 11 bits por carácter, redondeo hacia arriba | Norma MODBus serie; sobreestima con 8N1 y queda del lado seguro |
| Tareas lentas | Solo con el bus en reposo | El ADC y los `print()` no deben demorar la recepción (efecto sonda de la T1) |
| Medición de t1,5 | Entre bloques leídos del UART | El UART tiene FIFO: el software ve bloques, no bytes. Un lazo demorado puede medir un hueco mayor que el real; por eso existe `VERIFICAR_T15` y el contador `invalidas` (B-5) |
| Espera tras subir DE | 200 µs | Valor de `umodbus` 2.3.7 con el que la T1 midió 0,0 % de error |
