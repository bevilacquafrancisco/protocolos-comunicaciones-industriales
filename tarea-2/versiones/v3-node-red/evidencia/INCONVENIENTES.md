# Inconvenientes encontrados durante el desarrollo y su resolución

**Tarea Nº2 — OPC UA cliente-servidor sobre Raspberry Pi** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Mismo criterio que en la Tarea 1: cada problema queda registrado con el
contexto, el diagnóstico (incluidas las hipótesis descartadas), la solución y
la evidencia de que la solución funciona.

Los registros **I-01 a I-07** se detectaron **antes de llegar al banco**, al
leer el código fuente de las bibliotecas y en las pruebas de integración en la
PC. Los problemas que aparezcan con las placas se agregan a partir de **I-08**
con la plantilla del final.

---

## Índice

| # | Problema | Dónde se detectó | Estado |
|---|---|---|---|
| [I-01](#i-01-el-antirrebote-de-pi-gpiod-está-en-microsegundos-no-en-milisegundos) | El antirrebote de `pi-gpiod` está en µs, no en ms | Lectura del código del nodo | Resuelto en `config.js` |
| [I-02](#i-02-el-nodo-pwm-de-pi-gpiod-no-puede-generar-el-ciclo-de-trabajo-255) | El nodo PWM no puede generar el ciclo de trabajo 255 | Prueba exhaustiva de los 256 niveles | Documentado; error de 0,4 % aceptado |
| [I-03](#i-03-el-compact-server-acepta-cualquier-usuario-y-contraseña) | El Compact-Server acepta cualquier usuario y contraseña | Lectura del código del nodo | Cambio de diseño (ADR-01) |
| [I-04](#i-04-cliente-zombi-después-de-un-fallo-de-arranque) | Cliente zombi después de un fallo de arranque | Prueba de integración que tardaba 300 s | Resuelto en `cliente_opcua.js` |
| [I-05](#i-05-el-modo-de-seguridad-del-canal-aparece-como-invalid) | El modo de seguridad del canal aparece como `Invalid` | Prueba de integración 11 | Resuelto en `servidor_opcua.js` |
| [I-06](#i-06-el-decodificador-inventaba-campos-a-partir-de-bytes-cifrados) | El decodificador inventaba campos a partir de bytes cifrados | Vectores reales SignAndEncrypt | Resuelto en `opcua_tramas.py` |
| [I-07](#i-07-cola-de-mensajes-sin-límite-si-el-servidor-no-está-al-arrancar) | Cola de mensajes sin límite si el servidor no está al arrancar | Análisis del código de Node-RED | Resuelto por diseño |

---

## I-01. El antirrebote de `pi-gpiod` está en microsegundos, no en milisegundos

**Contexto.** El nodo `pi gpiod in` tiene un campo *debounce* con valor por
defecto `25`. Se lo había interpretado como 25 ms, el valor típico de
antirrebote para un pulsador.

**Diagnóstico.** En `pi-gpiod.js` el campo se pasa directamente a
`PiGPIO.set_glitch_filter(pin, node.debounce)`. La documentación de pigpio
define `set_glitch_filter(gpio, steady)` con `steady` **en microsegundos**
(0-300 000). El valor por defecto son, entonces, **25 µs**: el rebote mecánico
de un pulsador táctil dura de 1 a 10 ms, entre 40 y 400 veces más, y pasa sin
filtrar.

**Síntoma que habría producido.** Varias escrituras de
`Cliente.EstadoPulsador` por cada pulsación. En la captura de la Parte 4 eso se
habría visto como ráfagas de WriteRequest, y la cuenta de tramas de la Parte
3.4 habría quedado inflada.

**Solución.** `config.gpio.antirreboteUs = 25000`, con el comentario que
explica la unidad. `generar_flujos.js` lo escribe en el nodo, y la prueba de
flujos verifica que coincida.

**Pendiente de banco:** contar las transiciones del pulsador con el filtro en
25 µs y en 25 000 µs, para tener la evidencia medida.

## I-02. El nodo PWM de `pi-gpiod` no puede generar el ciclo de trabajo 255

**Contexto.** La consigna pide escalar la rampa a 0-255. El nodo
`pi gpiod out` en modo PWM recibe un porcentaje 0-100 y aplica
`set_PWM_dutycycle(pin, parseInt(pct * 2.55))`.

**Diagnóstico.** Dos problemas:

1. Si se le pasa `Math.round(duty / 2.55)`, solo hay **101 niveles** distintos:
   se pierde resolución respecto de los 256 de la consigna.
2. Ni siquiera con el máximo admitido se llega a 255: en coma flotante
   `100 * 2.55 = 254.99999999999997`, y `parseInt` lo trunca a **254**.

**Solución.** `senales.dutyAPorcentajePiGpiod(duty)` devuelve
`(duty + 0.5) / 2.55` (acotado a 100). Sumar medio paso antes de dividir hace
que `parseInt` recupere exactamente el ciclo de trabajo original.
`prueba_senales.js` (prueba 9) lo verifica en los **256 niveles**, replicando la
cuenta del nodo. Única excepción: 255 → 254, una diferencia de 1/255 = 0,4 % de
brillo, imperceptible. Se acepta y se documenta.

## I-03. El Compact-Server acepta cualquier usuario y contraseña

**Contexto.** El plan aprobado usaba el nodo **Compact-Server**
(`node-red-contrib-opcua-server` 1.1.1), el que muestra el material de clase.

**Diagnóstico.** Al revisar el código instalado para resolver un *gap* del
plan (si permitía fijar `ns=1`), se encontró en `opcuaCompact/core/security.js`:

```js
function checkUserLogon(){ return !0 }      // es decir: return true
```

Esa función es el `userManager.isValidUser` del servidor: **cualquier
combinación de usuario y contraseña es aceptada**. Además:

- depende de **node-opcua 2.64.1** (2022) y de **vm2 3.9.x**, con
  vulnerabilidades críticas de escape del sandbox publicadas
  (GHSA-g644-9gfx-q4q4, GHSA-cchq-frgv-rjh5, entre otras) y sin mantenimiento;
- el paquete no recibe actualizaciones desde 2022.

**Alternativa también descartada.** El nodo *OpcUa-Server* de
`node-red-contrib-opcua` arma un espacio de direcciones de demostración propio
y lee los usuarios de un `users.json` con **contraseñas en texto plano**.

**Solución.** Cambio de diseño, registrado como **ADR-01** en
[docs/arquitectura-red.md](../docs/arquitectura-red.md): Node-RED sigue siendo
el entorno de ejecución (temporizadores, GPIO, consola), y la pila OPC UA es
**node-opcua 2.160.0 usado directamente desde function nodes**. Es la misma API
que muestra la diapositiva 32 del material de clase. La prueba de integración 13
verifica que una clave incorrecta es rechazada.

**Lección.** "Lo muestra la clase" no garantiza que esté bien implementado.
Se detectó solo porque se leyó el código antes de usarlo.

## I-04. Cliente zombi después de un fallo de arranque

**Contexto.** La primera corrida de `prueba_integracion_opcua.js` dio 11 de 14
pruebas correctas, pero tardó **301 s** en vez de los ~10 s esperados.

**Hipótesis descartada.** Que el apagado del servidor (`shutdown(1000)`) se
colgara: medido aparte, tardaba 1,02 s.

**Diagnóstico.** La prueba 14 pedía autenticación por usuario sin definir las
variables de entorno. `iniciarCliente()` **conectaba primero** y fallaba
después, al armar la identidad, sin desconectar. Con `maxRetry: -1`, el
cliente quedaba reintentando en segundo plano para siempre y mantenía vivo el
proceso hasta el *timeout* de la prueba.

**Por qué importa en el banco.** En la RPi 2, un error de configuración habría
dejado un cliente oculto reconectándose indefinidamente: tráfico extra en las
capturas y sesiones fantasma en el servidor.

**Solución.** (a) La identidad se valida **antes** de conectar. (b) Todo lo
posterior a `connect()` está en un `try` que ejecuta `disconnect()` si algo
falla. Resultado: 15/15 pruebas en 11,4 s.

## I-05. El modo de seguridad del canal aparece como `Invalid`

**Contexto.** La prueba 11 buscaba en el registro del servidor la línea con
`modo=SignAndEncrypt` y no la encontraba.

**Diagnóstico.** El registro se hacía en el evento `newChannel`. node-opcua lo
emite cuando se acepta la conexión TCP, **antes** de procesar el OPN, y en ese
momento `securityMode` todavía vale `Invalid`. Es una muestra concreta de que
conexión TCP y canal seguro son cosas distintas (Parte 4.3): la conexión existe
antes de que se negocie la seguridad.

**Solución.** El modo y la política se registran en `create_session`, cuando
el canal seguro ya está establecido. `newChannel` registra solo
"Conexión TCP aceptada".

## I-06. El decodificador inventaba campos a partir de bytes cifrados

**Contexto.** Al pasar por `opcua_tramas.py` los 88 mensajes reales en modo
SignAndEncrypt, 73 daban error ("máscara de NodeId desconocida: 0xA3") y
algunos se "decodificaban" como servicios con campos sin sentido.

**Diagnóstico.** En SignAndEncrypt está cifrado **todo** lo que sigue al
TokenId, incluida la cabecera de secuencia. El decodificador intentaba leer
NodeIds en bytes aleatorios. Un error es tolerable; un campo **inventado** es
peor, porque podría terminar en el informe como si fuera real.

**Solución.** Si el TypeId no corresponde a un servicio conocido, el
decodificador retrocede y marca el resto como **Opaco** con su motivo. Con una
política distinta de `None`, el OPN se marca como cifrado (RSA) sin intentar
leerlo. Verificado: 0 errores en los 334 mensajes reales, y en SignAndEncrypt
solo quedan legibles MessageType, ChunkType, MessageSize, SecureChannelId y
TokenId (`prueba_opcua_tramas.py`, sección 7).

## I-07. Cola de mensajes sin límite si el servidor no está al arrancar

**Contexto.** El "On Start" de una function node de Node-RED es asíncrono, y
el nodo no procesa mensajes hasta que termina.

**Diagnóstico.** Si el "On Start" del cliente esperara la conexión
(`await iniciarCliente(...)`) y la RPi 1 estuviera apagada, los temporizadores
de 50 y 100 ms seguirían enviándole mensajes, que Node-RED encola: unos 30
mensajes por segundo acumulándose sin límite mientras el servidor no aparezca.

**Solución.** El cliente conecta **en segundo plano**, sin `await`. El nodo
queda listo de inmediato y descarta y cuenta lo que llega sin conexión. El
servidor, en cambio, sí espera en On Start, porque arranca en menos de 2 s.

---

## Plantilla para los problemas de banco (I-08 en adelante)

```markdown
## I-NN. Título que describe el síntoma

**Contexto.** Qué se estaba haciendo y en qué parte de la consigna.
**Síntoma.** Lo observado, con la evidencia (línea de journalctl, captura, foto).
**Hipótesis descartadas.** Cada una con la prueba que la descartó.
**Diagnóstico.** La causa raíz y cómo se confirmó.
**Solución.** Qué se cambió (archivo y commit).
**Verificación.** La medición que demuestra que quedó resuelto.
```
