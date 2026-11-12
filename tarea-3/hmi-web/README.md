# Host Application: página web Sparkplug B

Tarea Nº3 · Fase F6 · nivel 4 (navegador de PC o de celular)

Página estática con HTML, CSS y JavaScript, sin framework. Se conecta al broker por WSS y
decodifica el Protobuf de Sparkplug B. Muestra el semáforo de las cuatro capas (I-05) y el
dispositivo 1, y acciona sus salidas con DCMD.

**Estado.** Probada en la PC: 16 pruebas pasan, y una de ellas maneja la **página real en Chrome**
contra el broker de desarrollo y el Edge Node de prueba. Falta la corrida contra el broker en la
nube y en un celular de verdad (§7).

---

## 1. Qué hay y dónde

| Ruta | Contenido |
|---|---|
| `index.html` | Una sola pantalla: semáforo, dispositivo 1, controles y eventos. CSP sin scripts en línea |
| `sparkplug.js` | **Núcleo** sin DOM ni MQTT (ADR-024). Vigencia por métrica, validación de `seq` y `bdSeq`, Rebirth, estados de comando y codec Protobuf |
| `app.js` | Conexión MQTT (cliente nuevo por conexión, retroceso 1-30 s), STATE y vista |
| `styles.css` | Legible desde lejos y en celular. Contraste AA, sin animaciones, tema claro u oscuro según el sistema |
| `config.example.js` | Plantilla de `config.js`, con la explicación de por qué la clave en la página es una **mitigación y no una solución** |
| `vendor/` | `mqtt.min.js` 5.16.1 y `protobuf.min.js` 8.8.1 copiados de `node_modules`. `VERSIONES.txt` registra su SHA-256 |
| `proto/sparkplug_b.proto` | Copia del `.proto` del dispositivo 3. Una prueba verifica que es idéntico al oficial |
| `tools/servir.js` | Servidor estático con **lista blanca** de archivos y cabeceras de seguridad |
| `tools/copiar_vendor.js` | Regenera `vendor/` y `proto/` |
| `test/` | `node:test`: núcleo, interoperabilidad con Python, entrega y navegador |

El Edge Node de prueba está en `../gateway-sparkplug/tools/fake_edge_node.py`, porque usa el código
del dispositivo 3 (ver §5).

## 2. Vigencia de los datos

| Vigencia | Cuándo | Cómo se ve |
|---|---|---|
| **EN LÍNEA** | Llegó en el BIRTH vigente o en un DATA posterior | Valor normal y antigüedad ("hace 2 s") |
| **OBSOLETO** | Después de un NDEATH (con el `bdSeq` vigente), un DDEATH, o si la web perdió el broker | Último valor **tachado** y atenuado |
| **DESCONOCIDO** | No hubo BIRTH en esta sesión | "—" y la leyenda "sin BIRTH: no válido". **Nunca se muestra un dato como válido** |

**Reglas que aplica el núcleo**

- Un DATA sin BIRTH vigente, un salto de `seq` (0-255 con vuelta) o un alias que no figura en el
  BIRTH disparan un **NCMD Rebirth**. Se pide como máximo uno cada 5 s, para evitar tormentas.
  Cada pedido se cuenta y se avisa en pantalla.
- Al conectarse, la web pide un Rebirth, porque los BIRTH no se retienen.
- Un NDEATH cuyo `bdSeq` no coincide con el vigente es el Will de una sesión vieja y se ignora.

**Comandos**

- **ENVIADO**: la vista **no cambia**.
- **CONFIRMADO**: llegó el DDATA con el valor pedido.
- **SIN CONFIRMAR**: pasaron 5 s sin ese DDATA, o hubo un DDEATH o una desconexión.
- El conmutador y el deslizador muestran siempre el valor confirmado.

## 3. Instalación y configuración

```bash
cd tarea-3/hmi-web
npm ci                         # solo para pruebas y para regenerar vendor/
cp config.example.js config.js # y completar: URL wss://, usuario host_app, clave
```

Para servir la página hace falta un servidor, porque descarga `proto/sparkplug_b.proto` con
`fetch`, y eso no funciona con `file://`:

```bash
node tools/servir.js           # http://127.0.0.1:8080
node tools/servir.js --lan     # http://<IP de la PC>:8080, para abrirla desde el celular
```

La página no necesita `npm` para funcionar: `vendor/` está versionado.

**Seguridad (ADR-005, R-08)**

- `config.js` está en `.gitignore`, pero **el navegador lo descarga**: la clave del usuario
  `host_app` es pública de hecho. La mitigación es que ese usuario tenga permisos mínimos por
  tópico en el broker, y que el Edge Node y el servidor OPC UA validen cada comando. La solución en
  producción es un backend con autenticación por persona y tokens de vida corta. El detalle está
  en el comentario de `config.example.js`.
- `ws://` sin TLS se rechaza salvo contra `localhost`.
- Todo lo que llega del broker se escribe con `textContent`, nunca como HTML.
- **CSP**: no admite scripts ni estilos en línea, y solo permite conexiones `wss:`. Tiene dos
  excepciones medidas (ADR-025):
  - `'unsafe-eval'`, porque protobuf.js genera sus decodificadores al cargar el `.proto`;
  - `worker-src blob:`, porque mqtt.js corre sus temporizadores en un Worker.

## 4. Pruebas

```bash
npm test        # 16 pruebas, ~30 s. La del navegador necesita Chrome y el venv de gateway-sparkplug
```

| Archivo | Qué prueba |
|---|---|
| `sparkplug.test.js` | Codec (UInt32 en `intValue`, Int64, Float, nulo). **Interoperabilidad con el Edge Node en Python, en los dos sentidos.** DESCONOCIDO sin BIRTH. Salto de `seq` con Rebirth limitado. Vuelta 255→0 sin falso salto. DDEATH, NDEATH por `bdSeq`. Comando confirmado y sin confirmar. Desconexión |
| `entrega.test.js` | `vendor/` igual a las versiones fijadas. El servidor no entrega `package.json`, `node_modules`, `tools/` ni `..` |
| `ui.test.js` | **La página en Chrome** contra el broker de desarrollo (WebSocket) y el `fake_edge_node`: EN LÍNEA, conmutador CONFIRMADO, comando SIN CONFIRMAR sin mentir el valor, salto de `seq` → Rebirth con aviso, DEVICE NOT REACHED → OBSOLETO con controles deshabilitados, celular de 390 px sin desplazamiento horizontal y con controles de ≥ 44 px, kill del Edge → NDEATH, y **sin errores en la consola**, CSP incluida |

Capturas: `docs/capturas/hmi-escritorio.png`, `hmi-ddeath.png` y `hmi-celular.png`.

## 5. Desarrollo sin la cadena real

```bash
cd tarea-3/gateway-sparkplug
.venv/bin/python tools/broker_dev.py --carpeta .dev-broker --puerto 18883 --puerto-ws 18884
.venv/bin/python tools/fake_edge_node.py --env <.env con MQTT_*> --mqtt-ca .dev-broker/ca.pem
# en config.js: url 'ws://127.0.0.1:18884/mqtt', usuario host_app y la clave que imprimió el broker
```

`fake_edge_node.py` **no reimplementa Sparkplug**. Usa el Edge Node real con datos sintéticos.
Recibe estos comandos por teclado:

| Comando | Efecto |
|---|---|
| `dnr` / `ok` / `crc` | Estado MODBUS |
| `opcua off` / `opcua on` | Corta o restablece la sesión OPC UA |
| `saltar` | Provoca un salto de `seq` |
| `escrituras falla` / `escrituras ok` | Los comandos dejan de confirmarse, o vuelven a confirmarse |
| `pulsador 1` / `pote 2000` | Fija esos valores a mano |
| `matar` | Termina el proceso sin NDEATH: el NDEATH lo publica el broker como Will |

## 6. Decisiones

| ADR | Decisión |
|---|---|
| 024 | Núcleo puro y vista separada. Cliente MQTT nuevo por conexión, para que el STATE tenga el mismo timestamp que su Will. Bibliotecas servidas desde `vendor/` y no desde un CDN |
| 025 | CSP con `'unsafe-eval'` y `worker-src blob:`, con su justificación y la alternativa (`pbjs` estático) |

## 7. Pendiente

| # | Prueba | Criterio |
|---|---|---|
| W-1 | Contra el broker en la nube (WSS 8884) con el usuario `host_app` restringido (ADR-005) | Conecta. Publicar en `.../NBIRTH/...` con ese usuario **falla** |
| W-2 | En un celular real, por la red del aula o con datos móviles (R-06) | Se lee sin zoom y los controles responden |
| W-3 | Cadena completa: ESP32 → Raspberry Pi → dispositivo 3 → nube → web | Pulsador y potenciómetro en vivo. El LED responde al conmutador (E2E-01 a E2E-04) |
| W-4 | Cortar la red del dispositivo 3 | NDEATH a los ~15 s (keepalive 10 s × 1,5): todo OBSOLETO. Al volver, todo EN LÍNEA sin tocar la web (I-10) |
