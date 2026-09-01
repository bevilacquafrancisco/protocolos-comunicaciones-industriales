# Tarea Nº1 — Red de comunicación industrial MODBus RTU sobre RS-485

Protocolos de Comunicaciones Industriales · 4to año, Ingeniería en Computación · UNRaf

Tres nodos **ESP32 con MicroPython**, programados desde el **IDE Thonny**, sobre
un bus RS-485 compartido: un maestro MODBus RTU y dos esclavos con selección
dinámica de destino.

---

## 1. Estructura del repositorio

### Marco teórico y diseño

| Documento | Qué cubre |
|---|---|
| [docs/arquitectura.md](docs/arquitectura.md) | **Todo lo físico.** Ubicación en el modelo de Purdue, diagrama de bloques, el transceptor MAX485, adaptación de niveles 5 V↔3,3 V, teoría de líneas de transmisión y reflexiones, terminación y polarización, esquema de conexionado, asignación de pines, lista de materiales y bring-up |
| [docs/protocolo-comunicacion.md](docs/protocolo-comunicacion.md) | **Todo lo lógico.** RTU vs ASCII, justificación del puerto serie, delimitación por tiempo (t1,5/t3,5), estructura de la trama, las 4 funciones con sus tramas reales, el CRC-16 en detalle, endianness MSB/LSB, límites de capacidad, excepciones y timeouts, ciclo de sondeo |
| [docs/mapa-registros.md](docs/mapa-registros.md) | **El contrato de datos.** Mapa MODBus, desfasaje off-by-one, escalas, checklist de validación con Modbus Poll |
| [diagramas/flujo_maestro.md](diagramas/flujo_maestro.md) | Máquina de estados, ciclo de polling, degradación ante fallo |
| [diagramas/flujo_esclavo.md](diagramas/flujo_esclavo.md) | Flujo del esclavo, retención de estado, filtrado por Unit ID |

### Implementación

| Ruta | Contenido |
|---|---|
| [firmware/README.md](firmware/README.md) | **Guía completa de Thonny**: instalar, grabar MicroPython, instalar `umodbus`, cargar los nodos, depurar |
| [firmware/comun/](firmware/comun/) | `config.py` (única fuente de verdad) y `perifericos.py` (capa de abstracción de hardware) |
| [firmware/esclavo/main.py](firmware/esclavo/main.py) | Servidor MODBus RTU — el mismo archivo para ambos esclavos |
| [firmware/maestro/main.py](firmware/maestro/main.py) | Cliente MODBus RTU con máquina de estados |
| [firmware/prueba_perifericos.py](firmware/prueba_perifericos.py) | Banco de pruebas de hardware sin MODBus (Fase 1) |
| [herramientas/modbus_tramas.py](herramientas/modbus_tramas.py) | CRC-16 propio y decodificador de tramas (corre en la PC) |

### Material de cátedra y evidencia

| Ruta | Contenido |
|---|---|
| [Tarea_1_MODBus_V26.pdf](Tarea_1_MODBus_V26.pdf) | Consigna original |
| [Marco_Teorico_y_Planificacion_TP1_MODBus.docx](Marco_Teorico_y_Planificacion_TP1_MODBus.docx) | Planificación previa del grupo |
| [docs/MAX481.PDF](docs/MAX481.PDF) | Datasheet del transceptor |
| `evidencia/` | Capturas de Modbus Poll, tramas y fotos del banco *(a completar)* |
| `informe/` | Informe técnico — **se redacta al final del desarrollo** |

## 2. Decisiones de diseño ya tomadas

Cada una está justificada con números en el documento que se indica. Son las que
hay que poder defender oralmente.

| Decisión | Valor | Justificación | Dónde |
|---|---|---|---|
| Baudrate | 9600 | t1,5 = 1,72 ms absorbe las pausas del GC de MicroPython; a 115200 serían 143 µs | [protocolo §3.1](docs/protocolo-comunicacion.md#31-baudrate-9600--la-decisión-menos-obvia-y-la-más-importante) |
| Paridad | Ninguna (8N1) | El CRC-16 ya es más fuerte que la paridad, y es el valor por defecto de todas las herramientas | [protocolo §3.3](docs/protocolo-comunicacion.md#33-paridad-ninguna-n) |
| Nivel RO→RX | Divisor 2k2/3k3 | RO da ≈5 V contra un máximo absoluto de 3,6 V del GPIO. Resultado: 3,15 V | [arquitectura §4.3](docs/arquitectura.md#43-sentido-max485--esp32-ro--rx-divisor-resistivo-obligatorio) |
| Nivel ESP32→DI/DE/RE | Directo | VIH del MAX485 = 2,0 V; el ESP32 da 3,3 V (margen 1,3 V) | [arquitectura §4.2](docs/arquitectura.md#42-sentido-esp32--max485-di-de-re-conexión-directa) |
| Terminación | 120 Ω en los 2 extremos | Con tR = 15 ns la longitud crítica es 1,5 m: **el bus de banco ya es eléctricamente largo** | [arquitectura §5](docs/arquitectura.md#5-teoría-de-líneas-de-transmisión-por-qué-hay-que-terminar-el-bus) |
| Polarización del bus | 680 Ω / 680 Ω | Da 211 mV en reposo; con 1 kΩ caería a 145 mV, dentro de la zona muerta de ±200 mV | [arquitectura §6](docs/arquitectura.md#6-polarización-de-reposo-fail-safe-biasing) |
| Período de sondeo | 200 ms | Un ciclo de 4 transacciones ocupa el bus 102 ms; con 100 ms quedaría al 100 % | [protocolo §11.2](docs/protocolo-comunicacion.md#112-cálculo-del-período-de-sondeo) |
| Escala del ADC | Crudo 0-4095 | El esclavo transporta la medición, no su interpretación | [mapa §5](docs/mapa-registros.md#5-escala-del-potenciómetro) |
| Unit ID | Jumper en GPIO13 | Es una dirección *física* real, y permite un único firmware para ambos esclavos | [arquitectura §8.2](docs/arquitectura.md#82-esclavo-1-y-esclavo-2--firmware-idéntico) |
| Stack MODBus | `micropython-modbus` + CRC propio | La librería asegura la funcionalidad; el CRC propio da evidencia para la pregunta 2 | [protocolo §7.3](docs/protocolo-comunicacion.md#73-automático-por-hardware-o-por-software) |

## 3. Dónde se responde cada requerimiento de la consigna

| Requerimiento | Documento |
|---|---|
| Arquitectura de red y capa física | [arquitectura.md](docs/arquitectura.md) §2 a §7 |
| Tabla de mapeo MODBus | [mapa-registros.md](docs/mapa-registros.md) §3 |
| Diseño lógico y diagramas de flujo | [flujo_maestro.md](diagramas/flujo_maestro.md) · [flujo_esclavo.md](diagramas/flujo_esclavo.md) |
| Trazabilidad de código | Cada bloque de los diagramas nombra su función; cada función cita su bloque |
| Análisis de tramas MODBus RTU | [protocolo-comunicacion.md](docs/protocolo-comunicacion.md) §5 y §6 + `modbus_tramas.py` |
| Pregunta 1 — cantidad máxima de datos por mensaje | [protocolo-comunicacion.md §9](docs/protocolo-comunicacion.md#9-límites-de-capacidad-de-la-trama) |
| Pregunta 2 — CRC: qué genera, hardware o software | [protocolo-comunicacion.md §7](docs/protocolo-comunicacion.md#7-el-crc-16) |
| Pregunta 3 — manejo de MSB/LSB en WORDs de 16 bits | [protocolo-comunicacion.md §8](docs/protocolo-comunicacion.md#8-orden-de-bytes-msb-lsb-y-endianness) |
| Pregunta 4 — terminación, polarización y niveles TTL | [arquitectura.md §4, §5 y §6](docs/arquitectura.md#5-teoría-de-líneas-de-transmisión-por-qué-hay-que-terminar-el-bus) |
| Análisis Parte 1 — quién es maestro y quién esclavo | [arquitectura.md §1](docs/arquitectura.md#1-ubicación-del-sistema-en-una-arquitectura-industrial) |

## 4. Plan de trabajo por fases

Ordenado por **riesgo**, no por el orden de la consigna: lo más incierto (que el
bus funcione con el hardware real) se ataca primero.

| Fase | Objetivo | Entregable verificable | Estado |
|---|---|---|---|
| 0 | Diseño y documentación previa | Arquitectura, protocolo, mapa de registros, diagramas, firmware escrito | ✅ Hecho |
| 1 | Bring-up eléctrico | Divisor medido en ≈3,1 V · polarización en ≈211 mV · `prueba_perifericos.py` en verde en las 3 placas | ⬜ Pendiente |
| 2 | Esclavo 1 validado desde PC (Parte 1) | Las 14 pruebas del checklist de [mapa-registros.md §8](docs/mapa-registros.md#8-validación-del-mapa-fase-2-del-plan) + capturas | ⬜ Pendiente |
| 3 | Maestro monoesclavo (Parte 2) | Polling bidireccional estable 5 min sin timeouts | ⬜ Pendiente |
| 4 | Multiesclavo (Parte 3) | Conmutación en vivo · el no seleccionado retiene estado | ⬜ Pendiente |
| 5 | Captura y análisis de tramas | Una trama real por cada función (02, 04, 05, 06) desglosada | ⬜ Pendiente |
| 6 | Informe técnico | PDF con el formato de la cátedra | ⬜ Pendiente |
| 7 | Defensa oral | Guion cronometrado de 12 min + video de respaldo | ⬜ Pendiente |

**Regla de avance:** no pasar a la fase siguiente sin el criterio de aceptación
de la actual. Saltear la fase 1 convierte un problema eléctrico simple en tres
problemas superpuestos que se diagnostican en simultáneo.

## 5. Formato exigido para el informe

De la consigna, sección "Entrega":

- PDF, texto justificado
- Márgenes: laterales 3 cm · superior e inferior 2,5 cm
- Arial 11, interlineado 1,5, espaciado posterior 6 y anterior 0
- Citas y referencias en APA 7ª edición
- Nombre: `Apellido1_Apellido2_Apellido3_PdCI_T3_26.pdf`

## 6. Puesta en marcha rápida

### Verificar la herramienta de tramas (no requiere hardware)

```bash
python herramientas/modbus_tramas.py
```

### Preparar un ESP32 con Thonny

1. Instalar [Thonny](https://thonny.org) (libre y gratuito).
2. *Herramientas → Opciones → Intérprete* → **MicroPython (ESP32)** → puerto COM
   → **Instalar o actualizar MicroPython**.
3. *Herramientas → Administrar paquetes* → buscar `micropython-modbus` → **Instalar**.
4. Subir `config.py`, `perifericos.py` y el `main.py` que corresponda al nodo,
   **a la raíz** del dispositivo.
5. Ctrl+F2 para reiniciar; la cabecera de arranque aparece en el Shell.

Detalle completo, incluidas las fricciones de trabajar con tres placas a la vez,
en [firmware/README.md](firmware/README.md).

> ⚠️ **Antes de conectar cualquier ESP32 al MAX485, leer
> [docs/arquitectura.md §4](docs/arquitectura.md#4-adaptación-de-niveles-lógicos-5-v--33-v).**
> El pin RO entrega ≈5 V y el GPIO del ESP32 admite 3,6 V como máximo absoluto:
> sin el divisor resistivo se daña la placa.
