# Tarea Nº1 — Red de comunicación industrial MODBus RTU sobre RS-485

Protocolos de Comunicaciones Industriales · 4to año, Ingeniería en Computación · UNRaf

Tres nodos ESP32 con MicroPython sobre un bus RS-485 compartido: un maestro
MODBus RTU y dos esclavos con selección dinámica de destino.

---

## 1. Estructura del repositorio

| Ruta | Contenido |
|---|---|
| [Tarea_1_MODBus_V26.pdf](Tarea_1_MODBus_V26.pdf) | Consigna original de la cátedra |
| [Marco_Teorico_y_Planificacion_TP1_MODBus.docx](Marco_Teorico_y_Planificacion_TP1_MODBus.docx) | Marco teórico y planificación previa |
| [docs/PINOUT.md](docs/PINOUT.md) | Conexionado, niveles eléctricos, bus RS-485, bring-up |
| [docs/MAPA_REGISTROS.md](docs/MAPA_REGISTROS.md) | Mapa MODBus, parámetros serie y su justificación |
| [docs/MAX481.PDF](docs/MAX481.PDF) | Datasheet del transceptor |
| [diagramas/flujo_maestro.md](diagramas/flujo_maestro.md) | Máquina de estados y ciclo de polling |
| [diagramas/flujo_esclavo.md](diagramas/flujo_esclavo.md) | Flujo del esclavo y retención de estado |
| [firmware/](firmware/) | Código de los tres nodos + guía de carga |
| [herramientas/modbus_tramas.py](herramientas/modbus_tramas.py) | CRC-16 propio y decodificador de tramas |
| `evidencia/` | Capturas de Modbus Poll, tramas y fotos del banco |
| `informe/` | Informe técnico en elaboración |

## 2. Decisiones de diseño ya tomadas

Cada una está justificada con números en el documento que se indica. Son las que
hay que poder defender oralmente.

| Decisión | Valor | Justificación | Dónde |
|---|---|---|---|
| Baudrate | 9600 | t1,5 = 1,72 ms absorbe las pausas del GC de MicroPython; a 115200 serían 143 µs | MAPA_REGISTROS §2.1 |
| Paridad | Ninguna (8N1) | El CRC-16 ya es más fuerte que la paridad; es el valor por defecto de `machine.UART` | MAPA_REGISTROS §2.2 |
| Nivel RO→RX | Divisor 2k2/3k3 | RO da ~5 V contra un máximo absoluto de 3,6 V del GPIO. Resultado: 3,15 V | PINOUT §1.2 |
| Nivel ESP32→DI/DE/RE | Directo | VIH del MAX485 = 2,0 V; el ESP32 da 3,3 V (margen 1,3 V) | PINOUT §1.1 |
| Polarización del bus | 680 Ω / 680 Ω | Da 211 mV en reposo; con 1 kΩ caería a 145 mV, dentro de la zona muerta de ±200 mV | PINOUT §3.2 |
| Período de sondeo | 200 ms | Un ciclo de 4 transacciones ocupa el bus 102 ms; con 100 ms quedaría al 100 % | config.py |
| Escala del ADC | Crudo 0-4095 | El esclavo transporta la medición, no su interpretación | MAPA_REGISTROS §3.2 |
| Unit ID | Jumper en GPIO13 | Es una dirección *física* real, y permite un único firmware para ambos esclavos | PINOUT §2.1 |
| Stack MODBus | `micropython-modbus` + CRC propio | La librería asegura la funcionalidad (35 % de la nota); el CRC propio da evidencia para la pregunta 2 | firmware/README §3 |

## 3. Plan de trabajo por fases

Ordenado por **riesgo**, no por el orden de la consigna: lo más incierto (que el
bus funcione con el hardware real) se ataca primero.

| Fase | Objetivo | Entregable verificable | Estado |
|---|---|---|---|
| 0 | Diseño y documentación previa | PINOUT, MAPA_REGISTROS, diagramas, firmware escrito | ✅ Hecho |
| 1 | Bring-up eléctrico | Divisor medido en 3,1 V · polarización en 211 mV · blink en las 3 placas | ⬜ Pendiente |
| 2 | Esclavo 1 validado desde PC (Parte 1) | Modbus Poll lee y escribe las 4 direcciones · capturas | ⬜ Pendiente |
| 3 | Maestro monoesclavo (Parte 2) | Polling bidireccional estable 5 min sin timeouts | ⬜ Pendiente |
| 4 | Multiesclavo (Parte 3) | Conmutación en vivo · el no seleccionado retiene estado | ⬜ Pendiente |
| 5 | Captura y análisis de tramas | Una trama real por cada función (02, 04, 05, 06) desglosada | ⬜ Pendiente |
| 6 | Informe técnico | PDF con el formato de la cátedra | ⬜ Pendiente |
| 7 | Defensa oral | Guion cronometrado de 12 min + video de respaldo | ⬜ Pendiente |

**Regla de avance:** no pasar a la fase siguiente sin el criterio de aceptación
de la actual. Saltear la fase 1 convierte un problema eléctrico simple en tres
problemas superpuestos que se diagnostican en simultáneo.

## 4. Formato exigido para el informe

De la consigna, sección "Entrega":

- PDF, texto justificado
- Márgenes: laterales 3 cm · superior e inferior 2,5 cm
- Arial 11, interlineado 1,5, espaciado posterior 6 y anterior 0
- Citas y referencias en APA 7ª edición
- Nombre: `Apellido1_Apellido2_Apellido3_PdCI_T3_26.pdf`

## 5. Consultas pendientes a la cátedra

Dos inconsistencias detectadas en el PDF de la consigna. Conviene preguntarlas
en el foro y dejar constancia de la respuesta:

1. **Criterios de evaluación de otro trabajo.** La sección "Evaluación y defensa"
   menciona "sincronización RGB", "el protocolo IR es estable", "colisiones en el
   canal IR" y "la secuencia de colores" (páginas 5 y 6). Nada de eso pertenece a
   este trabajo de MODBus/RS-485: parece texto arrastrado de otra consigna. Hay
   que confirmar cuáles son los criterios reales del 35 % de Funcionalidad.
2. **Nombre del archivo de entrega.** Se pide
   `Apellido1_Apellido2_Apellido3_PdCI_T3_26.pdf`, con `T3`, siendo esta la
   Tarea Nº1. Confirmar si corresponde `T1` o si el `T3` es intencional.

## 6. Puesta en marcha rápida

```bash
# Verificar la herramienta de tramas (no requiere hardware)
python herramientas/modbus_tramas.py

# Cargar un esclavo (ver firmware/README.md para el detalle)
mpremote connect COM3 cp firmware/comun/config.py :config.py
mpremote connect COM3 cp firmware/comun/perifericos.py :perifericos.py
mpremote connect COM3 cp firmware/esclavo/main.py :main.py
mpremote connect COM3 reset
```

⚠️ **Antes de conectar cualquier ESP32 al MAX485, leer
[docs/PINOUT.md](docs/PINOUT.md) §1.** El pin RO entrega ~5 V y el GPIO del ESP32
admite 3,6 V como máximo absoluto: sin el divisor resistivo se daña la placa.
