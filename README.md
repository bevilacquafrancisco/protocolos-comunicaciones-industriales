# Protocolos de Comunicaciones Industriales — UNRaf

Repositorio personal: **Francisco Bevilacqua**, estudiante de Ingeniería en
Computación en la Universidad Nacional de Rafaela.  
Reúne los trabajos prácticos
de la materia **Protocolos de Comunicaciones Industriales**, cursada en el
segundo cuatrimestre de 2026.

No es solo un repositorio de entregas: cada trabajo está documentado como se
documentaría un proyecto real —con las decisiones justificadas, lo que se midió,
lo que falló y cómo se resolvió— de modo que sirva tanto para la evaluación
académica como para mostrar cómo se trabajo.

---

## Índice

- [La materia](#la-materia)
- [Trabajos](#trabajos)
  - [Tarea Nº1 — Red MODBus RTU sobre RS-485](#tarea-nº1--red-modbus-rtu-sobre-rs-485)
  - [Actividad Nº2 — Redes AS-i](#actividad-nº2--redes-as-i)
  - [Actividad Nº1 — Selección de instrumentos industriales](#actividad-nº1--selección-de-instrumentos-industriales)
- [Qué demuestra este repositorio](#qué-demuestra-este-repositorio)
- [Cómo está organizado](#cómo-está-organizado)
- [Autoría](#autoría)

---

## La materia

**Protocolos de Comunicaciones Industriales**
Ingeniería en Computación · 4.º año · Departamento de Tecnologías e Innovación
Universidad Nacional de Rafaela · 2.º cuatrimestre de 2026

**Docentes:** Mg. Ing. Martín Francisco Picó · Ing. Milton Pozzo

### Objetivo

La materia aborda **cómo se comunican entre sí los dispositivos de una planta
industrial**: desde el sensor que mide una variable física hasta los sistemas de
supervisión, pasando por los controladores y las redes de campo que los vinculan.

El eje es la **integración**: un sistema de automatización real no se compone de
un equipo, sino de instrumentos, controladores y redes de distintos fabricantes y
distintas generaciones que deben interoperar. Entender los protocolos es
entender el contrato que hace eso posible.

### Temas que se estudian

| Área | Contenidos |
|---|---|
| **Instrumentación** | Selección de instrumentos según variable y rango · señales analógicas convencionales (RTD, termopar, 4-20 mA) · identificación según norma ISA 5.1 · precisión, exactitud y grado de protección |
| **Interfaz con el controlador** | Módulos de entrada analógica en PLC de distintas gamas · resolución del sistema de medición · escalado de la señal en el software de programación |
| **Redes de nivel de campo** | AS-i (direccionamiento, imagen de proceso, sondeo cíclico maestro-esclavo, evolución v2.0 / v2.1 / v3.0 / ASi-5) · IO-Link · Safety at Work · HART sobre el lazo de 4-20 mA |
| **Buses de nivel superior** | Profibus DP · integración de subredes de campo bajo un maestro de nivel superior · arranque de motores con SIMOCODE |
| **MODBus** | Modo RTU y ASCII · modelo de datos de cuatro áreas · códigos de función · CRC-16 · delimitación de tramas por silencio · manejo de excepciones |
| **Capa física** | RS-485: señalización diferencial, half-duplex, teoría de líneas de transmisión, terminación y polarización · adaptación de niveles lógicos |
| **Arquitectura y seguridad** | Modelo de niveles Purdue / ISA-95 · integración OT/IT · ciberseguridad industrial (IEC 62443) y por qué las prioridades se invierten respecto de IT |

### Modalidad

Cada trabajo parte de un caso concreto —un instrumento real de catálogo, los
diagramas eléctricos de una planta, un sistema físico a construir— y exige
justificar las decisiones técnicas con fuentes primarias: datasheets,
especificaciones de los protocolos y normas.

---

## Trabajos

| # | Trabajo | Tema central | Tipo | Estado |
|---|---|---|---|---|
| 1 | [Actividad Nº1](act1/) | Selección de instrumentos e interfaz con PLC | Investigación técnica | Entregado |
| 2 | [Actividad Nº2](act2/) | Redes AS-i y su integración con Profibus | Análisis de caso real | Entregado |
| 3 | [**Tarea Nº1**](tarea%201/) | **Red MODBus RTU sobre RS-485 con tres microcontroladores** | **Diseño, implementación y verificación** | **Completo y verificado** |

---

### Tarea Nº1 — Red MODBus RTU sobre RS-485

> **El trabajo más extenso del repositorio y el más representativo.**
> [Documentación completa →](tarea%201/README.md)

Diseño, construcción y verificación de una red de comunicación industrial con
tres nodos **ESP32 programados en MicroPython**: un maestro MODBus RTU y dos
esclavos sobre un bus RS-485 compartido, con selección dinámica del nodo de
destino.

#### Resultados medidos

| Métrica | Valor |
|---|---|
| Ciclos de sondeo consecutivos | **750** |
| Tasa de error | **0,0 %** |
| Duración útil del ciclo (4 transacciones) | 161 ms medidos, contra 110 ms modelados |
| Pruebas del mapa de registros | 14 de 14 correctas |
| Verificaciones automáticas en la PC | 70, sin fallas |

Ninguna de estas cifras es una apreciación visual: todas provienen de la
instrumentación del propio firmware o de un banco de pruebas reproducible.

#### Qué incluye

- **Firmware** de los tres nodos, con una capa de abstracción de hardware, una
  capa de observabilidad y un único archivo de configuración como fuente de
  verdad. Los dos esclavos ejecutan **el mismo archivo**: la dirección se lee de
  un jumper físico, igual que un módulo de E/S industrial la toma de sus llaves DIP.
- **Marco teórico** de unas 2400 líneas: capa física (líneas de transmisión,
  reflexiones, terminación, polarización, adaptación de niveles), protocolo
  (tramas, CRC-16, endianness, delimitación temporal, excepciones) y el contrato
  de datos (modelo de cuatro áreas, direccionamiento, escalas).
- **Guías de construcción** escritas para que cualquiera pueda reproducir el
  sistema: cada componente con su valor de referencia, su rango admisible y el
  criterio para elegir dentro de ese rango.
- **Herramientas de análisis** que corren sin hardware: implementación propia del
  CRC-16 validada contra el vector de prueba estándar, decodificador de tramas y
  analizador pasivo del bus.
- **[Registro de los problemas encontrados](tarea%201/evidencia/INCONVENIENTES.md)**
  y cómo se resolvieron.



---

### Actividad Nº2 — Redes AS-i

[Carpeta →](act2/)

Análisis de una red AS-i real a partir de los **diagramas eléctricos y de
comunicaciones de una planta siderúrgica** (sistema de servicios auxiliares de un
molino laminador, integrador Danieli Automation), donde una línea de esclavos
AS-i convive con módulos SIMOCODE de arranque de motores bajo un maestro
Profibus DP.

El trabajo abarca:

- Interpretación de documentación técnica real de planta.
- **Cuantificación del ahorro** de cableado y de tiempo de instalación frente al
  cableado punto a punto tradicional, con datos concretos.
- Especificaciones de un maestro AS-i a partir de fuentes primarias.
- Mecanismo de direccionamiento, organización de la imagen de proceso y
  procedimiento de sondeo cíclico.
- Evolución del estándar y su posicionamiento frente a IO-Link y Safety at Work.

En colaboración con Agustina Peralta.

---

### Actividad Nº1 — Selección de instrumentos industriales

[Carpeta →](act1/)

Selección justificada de instrumentos de medición de catálogo de fabricantes
reconocidos, y análisis de su interfaz con el controlador.

| Asignación | Detalle |
|---|---|
| Variable principal | Temperatura por contacto, −50 °C a 150 °C, salida por resistencia RTD/NTC/PTC |
| Variable transversal | Caudal bifase líquido/vapor, 0,0 a 10,0 kg/h, salida 4-20 mA |
| Protocolo asignado | **HART** |

El trabajo incluye la identificación según **norma ISA 5.1**, el análisis de la
interfaz de adquisición en PLC de distintas gamas, la determinación de la
resolución del sistema de medición y el escalado de la señal. Los datasheets
consultados están en la carpeta.

---

## Qué demuestra este repositorio


| Competencia | Evidencia |
|---|---|
| **Firmware embebido** | [Tres nodos en MicroPython](tarea%201/firmware/) con capa de abstracción de hardware, máquina de estados explícita y configuración centralizada |
| **Protocolos industriales** | [MODBus RTU implementado y analizado](tarea%201/docs/protocolo-comunicacion.md) a nivel de trama, con CRC propio validado contra el vector estándar |
| **Electrónica y puesta en marcha** | [Adaptación de niveles, líneas de transmisión, terminación y polarización](tarea%201/docs/arquitectura.md), con dimensionamiento calculado y verificado con instrumento |
| **Diagnóstico sistemático** | [Registro de los tres defectos encontrados](tarea%201/evidencia/INCONVENIENTES.md), con las hipótesis descartadas y el experimento que falsó cada una |
| **Observabilidad** | [Capa de diagnóstico](tarea%201/firmware/comun/diagnostico.py): traza por niveles, captura de tramas sin alterar el timing del bus, estadística por nodo |
| **Testing** | [70 verificaciones automáticas](tarea%201/herramientas/prueba_diagnostico.py) que corren en la PC sin hardware, incluidas las de despliegue incompleto |
| **Documentación técnica** | Todo este repositorio. Más de 6000 líneas de documentación con decisiones justificadas y trade-offs explícitos |
| **Medición sobre opinión** | [Contraste entre el modelo temporal calculado y el medido](tarea%201/docs/protocolo-comunicacion.md), conservando ambos números y explicando la diferencia |

### Cómo se trabajo

Tres criterios que se repiten en todo el repositorio:

1. **Una afirmación técnica sin número no es una afirmación.** «El LED respondía
   rápido» no es un dato; 750 ciclos con 0,0 % de error, sí. Donde hubo un
   cálculo previo, está el cálculo y está la medición, aunque no coincidan.
2. **Documentar lo que falló, no solo lo que salió bien.** Un trabajo que solo
   muestra el camino correcto está probado a medias. Las pruebas de rechazo
   —escribir en un área de solo lectura, pedir una dirección inexistente— valen
   tanto como las del camino feliz.
3. **Justificar con un principio nombrado.** Cada decisión cita la norma, el
   datasheet, la medición o el trade-off que la sostiene. «Es buena práctica» sin
   fuente no es una justificación.

### Limitaciones, dichas de frente

Estos son **trabajos académicos**, no sistemas en producción. El montaje usa
cable sin trenzar en lugar de par trenzado normado, las placas son de desarrollo
y no equipamiento de campo, y el sistema operó en un banco y no en una planta.
Esas desviaciones están declaradas explícitamente en la documentación de cada
trabajo, con el análisis de qué implicarían en una instalación real.

---

## Cómo está organizado

```
.
├── tarea 1/          Red MODBus RTU sobre RS-485  ← el trabajo principal
│   ├── README.md         Punto de entrada: matriz de cumplimiento y resultados
│   ├── PARTE-1/2/3.md    Guías para reproducir el sistema desde cero
│   ├── docs/             Marco teórico: capa física, protocolo, mapa de registros
│   ├── diagramas/        Diagramas de flujo del maestro y del esclavo
│   ├── firmware/         Código de los tres nodos
│   ├── herramientas/     Análisis y pruebas que corren en la PC
│   ├── evidencia/        Registro de problemas y capturas de banco
│   └── informe/          Informe técnico
├── act2/             Redes AS-i: consigna, entrega y fuentes
└── act1/             Selección de instrumentos: consigna, entrega y datasheets
```

**Por dónde empezar:** [tarea 1/README.md](tarea%201/README.md) para el panorama
general, o [tarea 1/evidencia/INCONVENIENTES.md](tarea%201/evidencia/INCONVENIENTES.md)
si interesa más el proceso de diagnóstico que el resultado.

---

## Autoría

Repositorio personal de **Francisco Bevilacqua**. Los trabajos de la materia se
realizaron con la siguiente autoría:

| Trabajo | Autoría |
|---|---|
| Tarea Nº1 — MODBus RTU | **Francisco Bevilacqua** · **Agustina Peralta** |
| Actividad Nº2 — Redes AS-i | **Francisco Bevilacqua** · **Agustina Peralta** |
| Actividad Nº1 — Instrumentos | **Francisco Bevilacqua** |

Las consignas, los datasheets y el material de cátedra incluidos son propiedad de
sus respectivos autores y se conservan aquí únicamente como referencia del
contexto de cada trabajo.

---


