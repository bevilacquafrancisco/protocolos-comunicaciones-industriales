# Host Application: página web Sparkplug B

Tarea Nº3 · nivel 4 (navegador de PC o de celular) · v2 (2026-11-16, ADR-028)

Página estática con HTML, CSS y JavaScript, sin framework. Pide usuario y contraseña del broker, se
conecta por WSS y decodifica el Protobuf de Sparkplug B. Tiene cinco pestañas:

| Pestaña | Qué muestra |
|---|---|
| **Panel general** | Cadena de 5 equipos con el estado de cada tramo, E/S del dispositivo 1 con su nombre en las tres capas, controles, **recorrido del comando capa por capa** y **medición de tiempos** con sus marcas |
| **MODBus RTU** | Estructura de la trama, modelo de datos, funciones, mapa de direcciones, **tramas reales** decodificadas byte a byte y **el CRC-16 paso a paso** |
| **OPC UA** | Espacio de direcciones navegable con los atributos de cada nodo, los 14 nodos, estructura del mensaje binario, servicios y secuencia de la sesión |
| **MQTT · Sparkplug B** | Estructura del tópico, mensajes en vivo con el **payload Protobuf decodificado campo por campo**, tipos de mensaje, métricas y permisos |
| **Guía del sistema** | En qué se diferencia de la consola de Node-RED, dónde está cada cosa y qué significa cada estado |

La barra de las **cuatro capas** (MODBus, OPC UA, MQTT y Sparkplug B) está arriba en todas las
pestañas (I-05).

**Estado.** Probada en la PC: pasan 24 pruebas, y una de ellas maneja **la página real en Chrome**
contra el broker de desarrollo y el Edge Node de prueba. Recorre el ingreso, las cinco pestañas y
la vista de celular. Falta la corrida con el broker en la nube y en un celular de verdad (§7).

---

## 1. Qué hay y dónde

| Ruta | Contenido |
|---|---|
| `index.html` | Pantalla de ingreso y las cinco pestañas. CSP sin scripts ni estilos en línea |
| `sparkplug.js` | **Núcleo** sin DOM ni MQTT (ADR-024). Vigencia por métrica, `seq` y `bdSeq`, Rebirth, estados de comando con sus **marcas de tiempo**, y codec Protobuf |
| `tramas.js` | Decodificación didáctica, sin DOM: **CRC-16 paso a paso**, trama MODBus campo por campo, Protobuf byte por byte, trama de escritura reconstruida (ADR-028) |
| `modelo.js` | Modelo estático (mapa MODBus, métricas, nodos OPC UA). Una prueba **falla** si se aparta del diccionario de datos o de la verificación del servidor |
| `app.js` | Ingreso, conexión MQTT (cliente nuevo por conexión, retroceso 1-30 s), STATE y las pestañas |
| `styles.css` | Blanco, azul y verde. Ámbar y rojo solo para fallas. Contraste AA, controles de ≥ 44 px, sin fuentes externas |
| `config.example.js` | Plantilla de `config.js`: URL del broker e identificadores. **Sin clave** |
| `vendor/` | `mqtt.min.js` 5.16.1 y `protobuf.min.js` 8.8.1 copiados de `node_modules`. `VERSIONES.txt` registra su SHA-256 |
| `proto/sparkplug_b.proto` | Copia del `.proto` del dispositivo 3. Una prueba verifica que es idéntico al oficial |
| `tools/servir.js` | Servidor estático con **lista blanca** de archivos y cabeceras de seguridad |
| `tools/copiar_vendor.js` | Regenera `vendor/` y `proto/` |
| `test/` | `node:test`: núcleo, decodificación y modelo, entrega y navegador |

## 2. Vigencia de los datos

| Vigencia | Cuándo | Cómo se ve |
|---|---|---|
| **EN LÍNEA** | Llegó en el BIRTH vigente o en un DATA posterior | Valor normal y antigüedad ("hace 2 s") |
| **OBSOLETO** | Después de un NDEATH (con el `bdSeq` vigente), un DDEATH, o si la web perdió el broker | Último valor, atenuado |
| **DESCONOCIDO** | No hubo BIRTH en esta sesión | "—" y la leyenda "sin BIRTH: no válido". **Nunca se muestra un dato como válido** |

- Un DATA sin BIRTH vigente, un salto de `seq` (0-255 con vuelta) o un alias que no figura en el
  BIRTH disparan un **NCMD Rebirth**, como máximo uno cada 5 s. Cada pedido se cuenta y se avisa.
- Al conectarse, la web pide un Rebirth, porque los BIRTH no se retienen.
- Un NDEATH cuyo `bdSeq` no coincide con el vigente es el Will de una sesión vieja y se ignora.
- Comandos: **ENVIADO** (la vista no cambia) → **CONFIRMADO** (llegó el DDATA con el valor) o
  **SIN CONFIRMAR** (5 s sin DDATA, DDEATH o desconexión). Los controles muestran siempre lo confirmado.

## 3. Instalación y configuración

```bash
cd tarea-3/hmi-web
npm ci                         # solo para pruebas y para regenerar vendor/
cp config.example.js config.js # y completar la URL wss:// del broker
```

Hace falta un servidor, porque la página descarga `proto/sparkplug_b.proto` con `fetch`, y eso no
funciona con `file://`:

```bash
node tools/servir.js           # http://127.0.0.1:8080
node tools/servir.js --lan     # http://<IP de la PC>:8080, para abrirla desde el celular
```

Al abrirla pide **usuario y contraseña del broker**: los de un usuario con los permisos de la Host
Application (puesta en marcha 02 §3).

**Seguridad (ADR-027, ADR-028, R-08)**

- **No hay claves en la página.** Usuario y contraseña se escriben al entrar, viajan por TLS y
  quedan solo en memoria: recargar o tocar *Salir* los borra. Si `config.js` todavía tiene una
  `clave` de la v1, la página la ignora y avisa que hay que borrarla.
- Cada usuario del broker tiene permisos mínimos por tópico: el de la Host Application publica solo
  su STATE, NCMD y DCMD, y no puede hacerse pasar por el Edge Node. Además, el Edge Node y el
  servidor OPC UA validan cada comando.
- Una clave equivocada se informa en la pantalla de ingreso (CONNACK 4 o 5) y no se reintenta sola.
- `ws://` sin TLS se rechaza salvo contra `localhost`.
- Todo lo que llega del broker se escribe con `textContent`, nunca como HTML.
- **CSP**: no admite scripts ni estilos en línea, y solo permite conexiones `wss:`. Tiene dos
  excepciones medidas (ADR-025): `'unsafe-eval'` (protobuf.js) y `worker-src blob:` (mqtt.js).

## 4. Pruebas

```bash
npm test        # 24 pruebas, ~20 s. La del navegador necesita Chrome y el venv de gateway-sparkplug
HMI_CAPTURAS=<carpeta> npm test     # además guarda una captura de cada pestaña
```

| Archivo | Qué prueba |
|---|---|
| `sparkplug.test.js` | Codec, **interoperabilidad con el Edge Node en Python en los dos sentidos**, DESCONOCIDO sin BIRTH, salto de `seq`, vuelta 255→0, DDEATH, NDEATH por `bdSeq`, comandos, desconexión |
| `tramas.test.js` | **CRC-16 contra tramas reales del sistema** (`84 0A`, `31 CA`, `B8 44`, `B9 E4`), paso a paso y residuo 0. Decodificación MODBus (petición, respuesta, excepción, eco). Protobuf byte por byte. **`modelo.js` igual al diccionario y a la verificación OPC UA.** Marcas de tiempo de un comando |
| `entrega.test.js` | `vendor/` igual a las versiones fijadas. El servidor no entrega `package.json`, `node_modules`, `tools/` ni `..` |
| `ui.test.js` | **La página en Chrome**: clave equivocada rechazada y clave correcta; EN LÍNEA; comando CONFIRMADO con su recorrido (FC 05 reconstruida con CRC) y sus tiempos; tramas reales y CRC en MODBus; atributos OPC UA; payload Sparkplug; SIN CONFIRMAR sin mentir el valor; salto de `seq`; DDEATH; F-04; celular de 390 px **sin desplazamiento horizontal en ninguna pestaña**; NDEATH; **sin errores en la consola** |

## 5. Desarrollo sin la cadena real

```bash
cd tarea-3/gateway-sparkplug
.venv/bin/python tools/broker_dev.py --carpeta .dev-broker --puerto 18883 --puerto-ws 18884
.venv/bin/python tools/fake_edge_node.py --env <.env con MQTT_*> --mqtt-ca .dev-broker/ca.pem
# config.js: url 'ws://127.0.0.1:18884/mqtt'. Al entrar: host_app y la clave que imprimió el broker
```

`fake_edge_node.py` usa el Edge Node real con datos sintéticos, incluidas tramas MODBus válidas
(CRC correcto) en las métricas de diagnóstico. Comandos por teclado:

| Comando | Efecto |
|---|---|
| `dnr` / `ok` / `crc` | Estado MODBUS (con `dnr`, la RX llega vacía: TIMEOUT) |
| `opcua off` / `opcua on` | Corta o restablece la sesión OPC UA |
| `saltar` | Provoca un salto de `seq` |
| `escrituras falla` / `escrituras ok` | Los comandos dejan de confirmarse, o vuelven a confirmarse |
| `pulsador 1` / `pote 2000` | Fija esos valores a mano |
| `matar` | Termina el proceso sin NDEATH: el NDEATH lo publica el broker como Will |

## 6. Decisiones

| ADR | Decisión |
|---|---|
| 024 | Núcleo puro y vista separada. Cliente MQTT nuevo por conexión. Bibliotecas desde `vendor/`, no desde un CDN |
| 025 | CSP con `'unsafe-eval'` y `worker-src blob:` |
| 028 | Ingreso con usuario y clave del broker (sin secretos en la página). Tramas MODBus reales por Sparkplug. Lo que no se puede capturar desde el navegador (OPC UA cifrado, la trama de escritura) se muestra **reconstruido y rotulado como tal** |

## 7. Pendiente

| # | Prueba | Criterio |
|---|---|---|
| W-1 | Contra el broker en la nube (WSS 8084) con un usuario de la Host Application | Entra con su clave; con una clave mala, la pantalla de ingreso lo dice. Publicar en NBIRTH con ese usuario **no** llega a nadie (02 §5.3) |
| W-2 | En un celular real, por la red del aula o con datos móviles (R-06) | Se lee sin zoom y los controles responden |
| W-3 | Cadena completa: ESP32 → Raspberry Pi → dispositivo 3 → nube → web | Pulsador y potenciómetro en vivo. El LED responde. Las tramas de la pestaña MODBus son las del bus real |
| W-4 | Cortar la red del dispositivo 3 | NDEATH a los ~15 s: todo OBSOLETO. Al volver, todo EN LÍNEA sin tocar la web (I-10) |
| W-5 | Medición de tiempos en el banco, con NTP en la Raspberry y la notebook | Tramos intermedios positivos; total comparado con la PC (mediana 192 ms) |
