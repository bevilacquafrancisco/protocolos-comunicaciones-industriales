# Tarea Nº1 — Red de comunicación industrial MODBus RTU sobre RS-485

Protocolos de Comunicaciones Industriales · 4.º año, Ingeniería en Computación · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Tres nodos **ESP32 con MicroPython**, programados desde el **IDE Thonny**, sobre
un bus RS-485 compartido: un maestro MODBus RTU y dos esclavos con selección
dinámica de destino.

**Estado: las tres partes de la consigna están implementadas y verificadas sobre
hardware.**

---

## 1. Resultados

| Métrica | Valor medido | Cómo se obtuvo |
|---|---|---|
| Ciclos de sondeo consecutivos | **750** | Instrumentación del firmware del maestro |
| Ciclos con algún fallo | **0** | Ídem |
| Tasa de error | **0,0 %** | Ídem |
| Duración útil del ciclo (4 transacciones) | **161 ms** | Ídem |
| Duración útil con zona muerta activa | ≈ 124 ms | Ídem |
| Longitud del bus | 15 a 40 cm según la etapa | Medición directa |
| Pruebas del mapa de registros | **14 de 14 correctas** | Herramienta MODBus de PC, Parte 1 |
| Verificaciones automáticas en la PC | **70, sin fallas** | `herramientas/prueba_diagnostico.py` |

Ninguna de estas cifras es una apreciación visual: todas provienen de la
instrumentación del propio firmware o de un banco de pruebas reproducible. El
criterio que se sostuvo en todo el trabajo es que **«el LED respondía rápido» no
es un dato**.

## 2. Cumplimiento de la consigna

### 2.1 Las tres partes

| Parte | Requisito | Cómo se implementó | Evidencia |
|---|---|---|---|
| **1** | Esclavo MODBus RTU con las cuatro áreas de datos | Servidor RTU sobre ESP32; mapa fijo de 4 variables | [mapa-registros.md §9](docs/mapa-registros.md#9-validación-del-mapa-sobre-hardware) — 14 pruebas |
| **1** | Validación mediante PC | Conversor USB↔RS-485 y herramienta MODBus como maestro | [PARTE-1.md](PARTE-1.md) · [logs-qmodmaster.txt](logs-qmodmaster.txt) |
| **2** | Maestro MODBus sobre ESP32 | Máquina de estados explícita, 4 transacciones por ciclo | [PARTE-2.md](PARTE-2.md) · [flujo_maestro.md](diagramas/flujo_maestro.md) |
| **2** | Comunicación bidireccional | Dos lecturas y dos escrituras por ciclo, replicadas en salidas locales | 750 ciclos, 0,0 % de error |
| **3** | Arquitectura multiesclavo | Dos servidores con el **mismo firmware**; Unit ID por jumper | [PARTE-3.md](PARTE-3.md) |
| **3** | Selección dinámica del esclavo | Llave selectora muestreada una vez por ciclo, con confirmación por muestras | [DEPURACION-PARTE-3.md §2](DEPURACION-PARTE-3.md) |
| **3** | Indicación visual del nodo activo | Dos LED mutuamente excluyentes por construcción | [PARTE-3.md](PARTE-3.md) |
| **3** | **Retención de estado del no seleccionado** | Propiedad del modelo de datos; el firmware no reinicializa los registros | [mapa-registros.md §10](docs/mapa-registros.md#10-retención-de-estado) — con traza de la verificación |

### 2.2 Requerimientos teóricos

| Requerimiento | Dónde se responde |
|---|---|
| Arquitectura de red y capa física | [arquitectura.md](docs/arquitectura.md) §2 a §7 |
| Tabla de mapeo MODBus | [mapa-registros.md §3](docs/mapa-registros.md#3-el-mapa-de-registros) |
| Diseño lógico y diagramas de flujo | [flujo_maestro.md](diagramas/flujo_maestro.md) · [flujo_esclavo.md](diagramas/flujo_esclavo.md) |
| Trazabilidad entre diagrama y código | Cada bloque de los diagramas nombra su función; cada función cita su bloque en el docstring |
| Análisis de tramas MODBus RTU | [protocolo-comunicacion.md §5 y §6](docs/protocolo-comunicacion.md) · [mapa-registros.md §6](docs/mapa-registros.md#6-las-cuatro-transacciones-campo-por-campo) · `herramientas/modbus_tramas.py` |

### 2.3 Preguntas de evaluación teórico-práctica

| Pregunta | Dónde se responde |
|---|---|
| 1 — Cantidad máxima de datos por mensaje | [protocolo-comunicacion.md §9](docs/protocolo-comunicacion.md#9-límites-de-capacidad-de-la-trama) |
| 2 — Qué genera el CRC; ¿hardware o software? | [protocolo-comunicacion.md §7](docs/protocolo-comunicacion.md#7-el-crc-16) — incluye la verificación contra el vector de prueba estándar |
| 3 — Manejo de MSB/LSB en WORDs de 16 bits | [protocolo-comunicacion.md §8](docs/protocolo-comunicacion.md#8-orden-de-bytes-msb-lsb-y-endianness) |
| 4 — Terminación, polarización y niveles TTL | [arquitectura.md §4, §5 y §6](docs/arquitectura.md) |

Las cuatro respuestas están además desarrolladas en la sección 10 del informe
técnico.

## 3. Estructura del repositorio

### Guías de construcción

Escritas para que **cualquier persona pueda reproducir el sistema** con
componentes equivalentes: cada valor lleva su rango admisible y el criterio para
elegir dentro de él.

| Documento | Qué cubre |
|---|---|
| [PARTE-1.md](PARTE-1.md) | Esclavo MODBus RTU y validación desde PC: paso a paso, conexiones, checklist de pruebas |
| [PARTE-2.md](PARTE-2.md) | Maestro ESP32 monoesclavo: la regla de un solo maestro, métricas a registrar, checklist |
| [PARTE-3.md](PARTE-3.md) | Arquitectura multiesclavo: segundo esclavo, selector, verificación de retención de estado |

### Marco teórico

| Documento | Qué cubre |
|---|---|
| [docs/arquitectura.md](docs/arquitectura.md) | **Capa física.** Ubicación en el modelo de Purdue, el transceptor, adaptación de niveles 5 V↔3,3 V, teoría de líneas de transmisión y reflexiones, terminación y polarización con su dimensionamiento, asignación de pines, lista de materiales |
| [docs/protocolo-comunicacion.md](docs/protocolo-comunicacion.md) | **Capa de enlace y aplicación.** RTU frente a ASCII, justificación del puerto serie, delimitación por silencio (t1,5/t3,5), estructura de la trama, las cuatro funciones con sus tramas reales, el CRC-16 y su verificación, endianness, límites de capacidad, excepciones y timeouts, ciclo de sondeo con el contraste entre cálculo y medición |
| [docs/mapa-registros.md](docs/mapa-registros.md) | **El contrato de datos.** Mapa MODBus, teoría del direccionamiento por áreas, el desfasaje Modicon↔offset, las cuatro transacciones campo por campo, escalas, validación sobre hardware y retención de estado |
| [diagramas/flujo_maestro.md](diagramas/flujo_maestro.md) | Máquina de estados, ciclo de sondeo, degradación ante fallo |
| [diagramas/flujo_esclavo.md](diagramas/flujo_esclavo.md) | Flujo del esclavo, retención de estado, filtrado por Unit ID |

### Implementación

| Ruta | Contenido |
|---|---|
| [firmware/README.md](firmware/README.md) | Guía de Thonny: instalar, grabar MicroPython, instalar la biblioteca, cargar los nodos, depurar |
| [firmware/comun/config.py](firmware/comun/config.py) | **Única fuente de verdad** de los parámetros del bus, pines y direcciones |
| [firmware/comun/perifericos.py](firmware/comun/perifericos.py) | Capa de abstracción de hardware |
| [firmware/comun/diagnostico.py](firmware/comun/diagnostico.py) | Capa de observabilidad: traza por niveles, captura de tramas, estadística por nodo |
| [firmware/esclavo/main.py](firmware/esclavo/main.py) | Servidor MODBus RTU — **el mismo archivo para ambos esclavos** |
| [firmware/maestro/main.py](firmware/maestro/main.py) | Cliente MODBus RTU con máquina de estados |
| [firmware/prueba_perifericos.py](firmware/prueba_perifericos.py) | Banco de pruebas de hardware, sin MODBus |

### Herramientas (se ejecutan en la PC, sin hardware)

| Herramienta | Qué hace |
|---|---|
| [herramientas/modbus_tramas.py](herramientas/modbus_tramas.py) | CRC-16 propio y decodificador de tramas. Valida contra el vector de prueba estándar |
| [herramientas/prueba_diagnostico.py](herramientas/prueba_diagnostico.py) | 70 verificaciones de la capa de diagnóstico |
| [herramientas/prueba_version_despliegue.py](herramientas/prueba_version_despliegue.py) | Verifica el mecanismo que detecta despliegues incompletos entre las tres placas |
| [herramientas/prueba_config_desactualizado.py](herramientas/prueba_config_desactualizado.py) | Comprueba que un nodo con configuración vieja arranque avisando, en vez de abortar |
| [herramientas/demo_retencion_estado.py](herramientas/demo_retencion_estado.py) | Reproduce la evidencia de retención de estado de la Parte 3 |
| [herramientas/sniffer_rs485.py](herramientas/sniffer_rs485.py) | Analizador pasivo del bus (requiere `pyserial` y un conversor USB↔RS-485) |

### Documentación de proceso y evidencia

| Ruta | Contenido |
|---|---|
| [evidencia/INCONVENIENTES.md](evidencia/INCONVENIENTES.md) | **Registro de los problemas de banco y su resolución**, con la hipótesis falsada en cada caso |
| [DEPURACION-PARTE-3.md](DEPURACION-PARTE-3.md) | Guía de diagnóstico del sistema en operación: niveles de traza, captura de tramas, árbol de decisión, verificaciones de hardware |
| [logs-qmodmaster.txt](logs-qmodmaster.txt) · [evidencia/captura-diagnostico.txt](evidencia/captura-diagnostico.txt) | Capturas de consola |
| [Tarea_1_MODBus_V26.pdf](Tarea_1_MODBus_V26.pdf) | Consigna original |
| [docs/MAX481.PDF](docs/MAX481.PDF) | Datasheet del transceptor |
| `informe/` | Informe técnico |

## 4. Decisiones de diseño

Cada una está justificada con números en el documento indicado.

| Decisión | Valor | Justificación | Dónde |
|---|---|---|---|
| Baudrate | 9600 | t1,5 = 1,72 ms absorbe las pausas del recolector de basura de MicroPython; a 115200 serían 143 µs | [protocolo §3.1](docs/protocolo-comunicacion.md) |
| Formato | 8N1 | El CRC-16 es más fuerte que la paridad, y 8N1 es el valor por defecto de todas las herramientas | [protocolo §3.3](docs/protocolo-comunicacion.md) |
| Adaptación ESP32 → transceptor | Conexión directa | Umbral de entrada alta de 2,0 V contra 3,3 V del ESP32: margen de 1,3 V | [arquitectura §4.2](docs/arquitectura.md) |
| Adaptación transceptor → ESP32 | Divisor + **pull-up** | La salida del receptor entrega ≈5 V contra un máximo absoluto de 3,6 V, y queda en alta impedancia al transmitir | [arquitectura §4.3](docs/arquitectura.md) |
| Terminación y polarización | **No instaladas** | Longitud del bus (15-40 cm) muy por debajo de la longitud crítica calculada (1,5 m). Validado con 0,0 % de error | [arquitectura §5](docs/arquitectura.md) |
| Período de sondeo | 200 ms | El ciclo ocupa el bus 161 ms medidos; deja margen para un reintento | [protocolo §11.2](docs/protocolo-comunicacion.md) |
| Escala del conversor | Crudo, 0-4095 | El esclavo transporta la medición, no su interpretación | [mapa §7](docs/mapa-registros.md#7-escala-del-potenciómetro) |
| Unit ID | Jumper por hardware | Es una dirección física real y permite **un único firmware** para ambos esclavos | [mapa §1.1](docs/mapa-registros.md#11-direccionamiento-por-hardware) |
| Stack MODBus | Biblioteca + CRC propio | La biblioteca asegura la funcionalidad; el CRC propio aporta evidencia para la pregunta 2 | [protocolo §7.3](docs/protocolo-comunicacion.md) |
| Reintento por transacción | 1 | Único mecanismo de recuperación que define MODBus; seguro porque las cuatro transacciones son idempotentes | [DEPURACION §2.1](DEPURACION-PARTE-3.md) |
| Degradación ante fallo | Por **ausencia sostenida** (2 s) | Contar fallos aislados hacía parpadear los indicadores del maestro | [DEPURACION §1](DEPURACION-PARTE-3.md) |

## 5. Reproducir el sistema

### Sin hardware — verificar las herramientas

```bash
python "tarea 1/herramientas/modbus_tramas.py"
python "tarea 1/herramientas/prueba_diagnostico.py"
python "tarea 1/herramientas/prueba_version_despliegue.py"
python "tarea 1/herramientas/demo_retencion_estado.py"
```

### Con hardware

1. Leer **[docs/arquitectura.md §4](docs/arquitectura.md)** antes de conectar nada.
2. Construir el nodo esclavo siguiendo [PARTE-1.md](PARTE-1.md) y validarlo desde
   la PC.
3. Agregar el maestro con [PARTE-2.md](PARTE-2.md).
4. Agregar el segundo esclavo con [PARTE-3.md](PARTE-3.md).

**No saltear el orden.** Los tres defectos encontrados durante la puesta en
marcha presentaron síntomas que no correspondían a su causa; haberlos enfrentado
con una sola variable nueva en juego fue lo que permitió aislarlos.

### Carga del firmware en cada placa

Cuatro archivos por placa, a la raíz del sistema de archivos del ESP32:

| Archivo | Maestro | Esclavo 1 | Esclavo 2 |
|---|---|---|---|
| `firmware/comun/config.py` → `config.py` | sí | sí | sí |
| `firmware/comun/perifericos.py` → `perifericos.py` | sí | sí | sí |
| `firmware/comun/diagnostico.py` → `diagnostico.py` | sí | sí | sí |
| `firmware/maestro/main.py` → `main.py` | sí | — | — |
| `firmware/esclavo/main.py` → `main.py` | — | sí | sí |

Los dos esclavos llevan **el mismo** `main.py`; la dirección la fija el jumper.

Cada firmware verifica al arrancar que los módulos compartidos estén en la
versión que necesita, y si detecta un despliegue incompleto **lo dice y sigue
funcionando con valores por defecto** en lugar de abortar con un error críptico.

> ⚠️ **Antes de conectar cualquier ESP32 al transceptor, leer
> [docs/arquitectura.md §4](docs/arquitectura.md).** La salida del receptor
> entrega ≈5 V y el GPIO del ESP32 admite 3,6 V como máximo absoluto: sin el
> divisor resistivo se daña la placa. Y sin el pull-up, el bus no funciona.

## 6. Limitaciones reconocidas

Se declaran explícitamente porque un trabajo que solo muestra lo que salió bien
no está completo.

- El montaje usa **cable sin trenzar**, lo que resigna parte del rechazo de ruido
  de modo común propio de RS-485. Aceptable a 9600 baudios en un bus de pocos
  centímetros; no lo sería en una instalación industrial.
- El tiempo de ciclo medido **supera en un 46 % al valor modelado**, por el costo
  de cómputo del intérprete. La ocupación real del bus es del 80,5 % frente al
  51 % previsto. Analizado en [protocolo §11.2](docs/protocolo-comunicacion.md).
- La alimentación del transceptor desde la placa de desarrollo puede quedar
  levemente por debajo del mínimo especificado cuando el conjunto se alimenta por
  USB.
- **MODBus no incorpora ningún mecanismo de seguridad**: no autentica, no cifra y
  no numera las tramas. Cualquier dispositivo con acceso físico al par
  diferencial puede leer todo el tráfico y escribir sobre las salidas. La
  mitigación es arquitectónica, no protocolar.

## 7. Formato del informe

De la consigna, sección «Entrega»:

- PDF, texto justificado
- Márgenes: laterales 3 cm · superior e inferior 2,5 cm
- Arial 11, interlineado 1,5, espaciado posterior 6 y anterior 0
- Citas y referencias en APA 7.ª edición
- Nombre: `Apellido1_Apellido2_PdCI_T3_26.pdf`
