# Tarea Nº2 — Comunicación cliente-servidor OPC UA sobre Raspberry Pi

Protocolos de Comunicaciones Industriales · 4.º año, Ingeniería en Computación · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Dos **Raspberry Pi** unidas por un enlace **Ethernet punto a punto** intercambian
el estado de un pulsador y una rampa por **OPC UA** (IEC 62541): la RPi 1 es
servidor y la RPi 2 es cliente. Ambas ejecutan **Node-RED**, con la pila OPC UA
**node-opcua** (decisión ADR-01).

**Estado:** implementación completa y verificada en la PC (servidor y cliente
reales, Node-RED real, 334 mensajes OPC UA reales decodificados). **Pendiente:**
la ejecución en las placas y las mediciones de banco (PARTE-1 a PARTE-4); las
tablas de resultados están preparadas y marcadas *pendiente*.

---

## 1. Verificaciones hechas (sin hardware)

| Verificación | Resultado | Cómo se obtuvo |
|---|---|---|
| Lógica de señales (sierra, triangular, escala, gamma, conversión para pigpio) | **9/9** | `node --test herramientas/prueba_senales.js` |
| Servidor y cliente OPC UA reales: NodeIds, ns=1, tipos, AccessLevel, EURange, BadNotWritable, BadTypeMismatch, Modo A, Modo B, 3 endpoints, usuario/clave, permisos por rol | **15/15** | `node --test herramientas/prueba_integracion_opcua.js` |
| Decodificador UA Binary contra mensajes reales de la pila en None, Sign y SignAndEncrypt | **82/82**, 0 errores en 334 mensajes | `python herramientas/prueba_opcua_tramas.py` |
| Flujos de Node-RED: al día con `config.js`, cableado, compilación, trazabilidad con los diagramas | **12/12** | `node --test herramientas/prueba_flujos.js` |
| Flujos importados en Node-RED 5.0.8 real (dos instancias en la PC) | Intercambio bidireccional de punta a punta en Modo B | Prueba de humo, [node-red/README.md §17](node-red/README.md) |
| Eficiencia de una word: OPC UA frente a MODBus RTU | **0,98 %** frente a **25 %**; 16,3 µs frente a 11,98 ms | `python herramientas/eficiencia_trama.py` |
| Predicción Modo B / Modo A (60 s) | 99 % de los mensajes con la rampa en movimiento; **11 %** con la rampa detenida | `python herramientas/comparar_modos.py` |

Antes del banco se encontraron y resolvieron **7 inconvenientes**, incluido uno
de seguridad que cambió el diseño (el servidor de la paleta aceptaba cualquier
contraseña): [evidencia/INCONVENIENTES.md](evidencia/INCONVENIENTES.md).

## 2. Cumplimiento de la consigna

### 2.1 Partes

| Parte | Requisito | Implementación | Guía de banco · teoría |
|---|---|---|---|
| **1** | Enlace punto a punto, IP estáticas, verificación por capas | NetworkManager, perfil `pdci-eth0`, `never-default` | [PARTE-1.md](PARTE-1.md) · [arquitectura-red.md §2-4](docs/arquitectura-red.md) |
| 1.4 | Todo el OPC UA por `eth0` con la Wi-Fi activa | Endpoint por IP literal; `endpointMustExist: false`; 4 pruebas | [PARTE-1.md §4](PARTE-1.md) |
| 1.5 | Pregunta de análisis | — | [arquitectura-red.md §2](docs/arquitectura-red.md) |
| **2** | Servidor en `opc.tcp://192.168.10.1:4840` | [servidor_opcua.js](node-red/servidor/servidor_opcua.js) | [PARTE-2.md](PARTE-2.md) |
| 2.2 | Namespace, NodeIds fijos, EURange | `skipOwnNamespace` + `registerNamespace`; AnalogItemType | [modelo-informacion.md](docs/modelo-informacion.md) |
| 2.3-2.4 | Sierra de 4 s; LED digital y PWM 0-255 | Bloques S3 y S6; pigpiod | [flujo_servidor.md](diagramas/flujo_servidor.md) |
| 2.5 | UaExpert: atributos, tendencia, escritura, BadNotWritable | — | [PARTE-2.md §3](PARTE-2.md) |
| 2.6 | Pregunta de análisis | — | [modelo-informacion.md §7](docs/modelo-informacion.md) |
| **3** | Cliente por `eth0`, rampa triangular de 8 s | [cliente_opcua.js](node-red/cliente/cliente_opcua.js) | [PARTE-3.md](PARTE-3.md) |
| 3.3 | Lectura y replicación; escritura al cambiar y cada 100 ms | Bloques C3-C5; filtro `rbe` | [flujo_cliente.md](diagramas/flujo_cliente.md) |
| 3.4 | Modo A / Modo B, tramas y bytes, Publish y KeepAlive, latencia | `config.lectura.modo`; botones de pausa; `comparar_modos.py`, `medir_latencia.py` | [PARTE-3.md §4](PARTE-3.md) · [protocolo-opcua.md §7](docs/protocolo-opcua.md) |
| 3.5 | Registro en consola | Bloques S7 y C6 | [PARTE-3.md §3](PARTE-3.md) |
| 3.6 | Desconexión: LED congelado, StatusCode, recuperación | Bloque C7; tres cortes (corto, medio, largo) | [PARTE-3.md §6](PARTE-3.md) |
| 3.7 | Gamma (opcional) | `config.senales.usarGamma` | [PARTE-3.md §7](PARTE-3.md) |
| **4** | Captura en la RPi y análisis en Wireshark | `tcpdump` en `eth0` | [PARTE-4.md §1](PARTE-4.md) |
| 4.2-4.3 | Secuencia; conexión TCP, canal y sesión | Diagrama con los mensajes reales | [secuencia_sesion.md](diagramas/secuencia_sesion.md) · [protocolo-opcua.md §4](docs/protocolo-opcua.md) |
| 4.4-4.5 | Encapsulamiento; decodificación byte a byte | `opcua_tramas.py --ethernet --markdown` | [protocolo-opcua.md §6 y §8](docs/protocolo-opcua.md) |
| 4.6 | Eficiencia frente a MODBus RTU | `eficiencia_trama.py` | [protocolo-opcua.md §9](docs/protocolo-opcua.md) |
| 4.7-4.8 | Tres endpoints, certificados y trust list, legibilidad, latencia | `config.seguridad`; `latencia_captura.py` | [PARTE-4.md §7](PARTE-4.md) · [seguridad.md](docs/seguridad.md) |
| 4.9 | Usuario y contraseña además del anónimo | Hash scrypt; roles | [PARTE-4.md §8](PARTE-4.md) · [seguridad.md §5](docs/seguridad.md) |

### 2.2 Requerimientos adicionales

| Requerimiento | Dónde |
|---|---|
| 1. Diagrama de red con interfaces, IP y conexionado | [diagramas/red.md](diagramas/red.md) |
| 2. Diagramas de flujo del servidor y del cliente | [flujo_servidor.md](diagramas/flujo_servidor.md) · [flujo_cliente.md](diagramas/flujo_cliente.md) |
| 3. Trazabilidad de código | Cada function node se llama como su bloque (`S3 · …`, `C5 · …`); tabla de trazabilidad en cada diagrama; verificada por `prueba_flujos.js` |
| 4. Capturas `.png` | `evidencia/capturas/` (en el banco) |
| Librerías: parámetros, funciones con tipos, retorno | Docstrings con la firma en cada función de `servidor_opcua.js`, `cliente_opcua.js` y en cada function node |

### 2.3 Nota sobre la consigna

La sección *Evaluación y defensa* de la consigna menciona "canal IR",
"protocolo IR", "secuencia de colores", "sincronización RGB" y "persistencia de
datos". Son restos de otra consigna y **no se consideran**. La defensa
([defensa/guion.md](defensa/guion.md)) se organiza con el contenido real de
esta tarea: latencias, intercambio pulsador/rampa ↔ LED y recuperación ante la
desconexión.

## 3. Estructura

| Ruta | Contenido |
|---|---|
| [node-red/README.md](node-red/README.md) | **Puesta a punto desde la microSD vacía**: grabación, SSH, red, Node-RED, copia de archivos, secretos, conexionado, importación, verificación |
| [PARTE-1.md](PARTE-1.md) … [PARTE-4.md](PARTE-4.md) | Guías de banco por parte, con tablas de resultados y listas de verificación |
| `docs/` | [arquitectura-red.md](docs/arquitectura-red.md) (capas, transportes, RS-485, **ADR**) · [modelo-informacion.md](docs/modelo-informacion.md) · [protocolo-opcua.md](docs/protocolo-opcua.md) · [seguridad.md](docs/seguridad.md) |
| `diagramas/` | Red, flujo del servidor, flujo del cliente, secuencia de la sesión (Mermaid) |
| `node-red/comun/` | [config.js](node-red/comun/config.js) (**única fuente de verdad**), [senales.js](node-red/comun/senales.js), [credenciales.js](node-red/comun/credenciales.js), funciones comunes `X*.js` |
| `node-red/servidor/`, `node-red/cliente/` | Módulo OPC UA, código de cada function node (`funciones/`) y `flows.json` **generado** |
| [node-red/generar_flujos.js](node-red/generar_flujos.js) | Genera los `flows.json` desde `config.js` y `funciones/` |
| [node-red/settings.pdci-t2.js](node-red/settings.pdci-t2.js) | Agregado al `settings.js` de Node-RED: módulos y seguridad del editor |
| `herramientas/` | Decodificador UA Binary, eficiencia, comparación A/B, latencia, captura local, pruebas |
| `herramientas/vectores/` | Mensajes OPC UA reales de la pila node-opcua (no son capturas de banco) |
| `evidencia/` | [INCONVENIENTES.md](evidencia/INCONVENIENTES.md); capturas y registros del banco |
| [defensa/guion.md](defensa/guion.md) | Guion de 12 minutos y banco de preguntas |

## 4. Decisiones de diseño

| Decisión | Valor | Justificación | Dónde |
|---|---|---|---|
| Pila OPC UA | node-opcua 2.160.0 desde function nodes | Los nodos servidor de la paleta aceptan cualquier contraseña o la guardan en texto plano | ADR-01, [arquitectura-red.md §8](docs/arquitectura-red.md) |
| GPIO | pigpiod, PWM por DMA a 800 Hz | Sin jitter por carga del CPU; 250 pasos reales | ADR-02 |
| Configuración | Un `config.js`; flujos generados | El invariante de la Tarea 1: ningún número duplicado | ADR-03 |
| Rampas | Calculadas desde el reloj | El *event loop* no garantiza ticks exactos; un contador acumularía deriva | [senales.js](node-red/comun/senales.js) |
| Namespace | ns=1 por `skipOwnNamespace`; el cliente lo **resuelve por URI** | El índice es local al servidor | [modelo-informacion.md §4](docs/modelo-informacion.md) |
| Endpoint del cliente | IP literal 192.168.10.1 | Un nombre de host podría resolverse por Wi-Fi | [arquitectura-red.md §4](docs/arquitectura-red.md) |
| Suscripción | 100 ms, QueueSize 1, KeepAlive 10, Lifetime 300 | Último valor; KeepAlive por segundo; un corte < 30 s conserva la suscripción | [config.js](node-red/comun/config.js) |
| Escrituras | Una pendiente por variable; las demás se omiten | Al reconectar se escribe el valor vigente, no una cola vieja | [cliente_opcua.js](node-red/cliente/cliente_opcua.js) |
| Ante desconexión | Mantener el último valor bueno | Prioridad de disponibilidad en OT; lo pide la consigna | [PARTE-3.md §6](PARTE-3.md) |
| Contraseñas | scrypt (N = 2¹⁷), secretos en `/etc`, nada en git | OWASP; IEC 62443 | [seguridad.md](docs/seguridad.md) |
| Editor de Node-RED | Solo en loopback + túnel SSH + adminAuth | El editor ejecuta código arbitrario | [node-red/README.md §10](node-red/README.md) |

## 5. Cómo verificar (en la PC, sin placas)

```bash
node --test tarea-2/herramientas/prueba_senales.js
node --test tarea-2/herramientas/prueba_flujos.js
python tarea-2/herramientas/prueba_opcua_tramas.py
python tarea-2/herramientas/eficiencia_trama.py
python tarea-2/herramientas/comparar_modos.py
python tarea-2/herramientas/medir_latencia.py --prueba
python tarea-2/herramientas/latencia_captura.py --prueba
# requiere node-opcua@2.160.0 instalado en alguna carpeta node_modules:
NODE_PATH=<ruta>/node_modules node --test tarea-2/herramientas/prueba_integracion_opcua.js
```

Las pruebas de la Tarea 1 siguen funcionando (`eficiencia_trama.py` importa su
`modbus_tramas.py`).

## 6. Limitaciones reconocidas

- **Todo lo medido hasta ahora es en la PC.** Las latencias, los conteos de
  tramas y los tiempos de la RPi pueden diferir; las tablas de banco lo
  mostrarán.
- **Raspberry Pi 5 no soportada** por pigpiod (supuesto S1 del plan).
- El nodo PWM de pigpiod no alcanza el ciclo de trabajo 255 (máximo 254, error
  de 0,4 %; I-02).
- El endpoint **None** y el acceso **anónimo** quedan habilitados porque la
  consigna los requiere; en producción se deshabilitarían
  ([seguridad.md §7](docs/seguridad.md)).
- El comportamiento de NetworkManager al perder la portadora es una hipótesis a
  verificar ([PARTE-3.md §6.1](PARTE-3.md)).
