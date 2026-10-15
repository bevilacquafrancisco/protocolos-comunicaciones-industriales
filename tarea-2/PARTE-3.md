# Parte 3 — Cliente OPC UA e intercambio bidireccional

**Tarea N.º 2 — OPC UA** · Protocolos de Comunicaciones Industriales · UNRaf
**Autores:** Bevilacqua Francisco, Peralta Agustina

Guía de banco de la Parte 3: cliente en la RPi 2, rampa triangular,
intercambio en ambos sentidos, comparación Read/suscripción con captura,
KeepAlive, latencia, registro en consola, prueba de desconexión y corrección
gamma (opcional).

**Requisitos previos:** Partes 1 y 2 completas. RPi 2 preparada con
`cliente/flows.json` importado. Relojes sincronizados con chrony
([node-red/README.md §14](node-red/README.md)) para las mediciones de latencia.

---

## 1. Qué implementa el cliente

| Consigna | Implementación | Dónde |
|---|---|---|
| 3.1 Cliente en la RPi 2, por `eth0` | `iniciarCliente()`, endpoint `opc.tcp://192.168.10.1:4840` (IP literal, nunca nombre de host) | [cliente_opcua.js](node-red/cliente/cliente_opcua.js) |
| 3.2 Rampa triangular 0-65535, 8 s, cada 50 ms | `senales.triangular()` desde el reloj: 160 muestras, pico exacto a los 4 s | bloque C2 · [prueba_senales.js](herramientas/prueba_senales.js) prueba 3 |
| 3.3 Leer `Servidor.*` → LED de la RPi 2 | C3a/C3b → C4 → GPIO | [flujo_cliente.md](diagramas/flujo_cliente.md) |
| 3.3 Escribir pulsador (al cambiar) y rampa (cada 100 ms) | C5: filtro `rbe` + inject de 100 ms | ídem |
| 3.4 Modo A y Modo B | `config.lectura.modo` = `'A'` \| `'B'` | [config.js](node-red/comun/config.js) |
| 3.5 Consola | C6 / S7 cada 1 s | `journalctl -u nodered -f` |
| 3.6 Desconexión | C7: eventos de conexión con StatusCode | §6 |
| 3.7 Gamma (opcional) | `config.senales.usarGamma` | §7 |

## 2. Funcionamiento básico

Con ambas placas en marcha, completar la verificación de
[node-red/README.md §13](node-red/README.md) (filas 6 a 11). En particular, la
prueba visual que pide la consigna:

| Placa | Su LED PWM refleja | Forma esperada | Observado |
|---|---|---|---|
| RPi 2 | `Servidor.Rampa` (de la RPi 1) | **Diente de sierra**: sube en 4 s y se apaga de golpe | *pendiente* |
| RPi 1 | `Cliente.Rampa` (de la RPi 2) | **Triangular**: sube 4 s, baja 4 s, sin saltos | *pendiente* |

Si una placa mostrara **su propia** forma de onda, el cableado o el flujo
estarían cruzados. Las formas distintas existen justamente para detectarlo a
simple vista.

## 3. Registro en consola (consigna 3.5)

```bash
$ journalctl -u nodered -f | grep -E "SERVIDOR|CLIENTE"
```

Formato real (salida de la prueba de humo en la PC, 2026-10-14):

```text
SERVIDOR generada=14102 recibida(Cliente.Rampa)=13107 SourceTimestamp=2026-10-14T02:05:20.854Z
CLIENTE generada=44236 recibida(Servidor.Rampa)=42307 SourceTimestamp=2026-10-14T02:04:58.585Z antiguedad=130 ms modo=B
```

| Campo | Significado |
|---|---|
| `generada` | Valor que esta placa generó en ese instante (su propia rampa) |
| `recibida(…)` | Último valor recibido de la otra placa |
| `SourceTimestamp` | Cuándo **la otra placa** generó ese valor |
| `antiguedad` | Hora actual − SourceTimestamp: edad del dato (con relojes sincronizados, una medida de latencia de extremo a extremo) |

Guardar 60 s de consola de cada placa en `evidencia/consola/`:
`journalctl -u nodered --since "1 min ago" > consola_rpi1.txt`.

## 4. Lectura cíclica frente a suscripción (consigna 3.4)

### 4.1 Hipótesis antes de medir

Predicción con el servidor y el cliente reales en la PC
(`python herramientas/comparar_modos.py`; análisis completo en
[protocolo-opcua.md §7.3](docs/protocolo-opcua.md)):

| Escenario | Modo B / Modo A (mensajes) | Modo B / Modo A (bytes) |
|---|---|---|
| Rampa en movimiento | **99 %** | **82 %** |
| Rampa detenida | **11 %** | **7 %** |

Hipótesis: con la rampa cambiando cada 50 ms, más rápido que el
PublishingInterval, la suscripción **no** reduce el tráfico. Con datos
estáticos lo reduce en un orden de magnitud.

### 4.2 Procedimiento de captura

Para cada modo:

1. En la **PC**, editar `tarea-2/node-red/comun/config.js` →
   `lectura.modo: 'A'` (o `'B'`).
2. Copiar la carpeta a la **RPi 2** ([README §9.2](node-red/README.md)) y
   `sudo systemctl restart nodered` (los módulos de `functionGlobalContext`
   solo se cargan al arrancar, README §15).
3. Esperar a que C1 esté en verde y la consola muestre `modo=A` (o `B`).
4. Capturar **60 s** en la RPi 2:

   ```bash
   $ sudo timeout 60 tcpdump -i eth0 -w ~/captura_modo_A.pcapng port 4840
   ```

5. Repetir con la rampa **detenida** (para el KeepAlive, §4.4): en el editor de
   la RPi 1 pulsar el botón **S3 · Detener rampa**, y en el de la RPi 2
   **C5 · Detener rampa**; sin tocar los pulsadores. Archivos
   `captura_modo_A_quieto.pcapng` y `captura_modo_B_quieto.pcapng`.
6. Copiar las cuatro capturas a la PC:
   `scp pdci@rpi-cliente.local:~/captura_*.pcapng .\tarea-2\evidencia\capturas\`

### 4.3 Conteo de tramas y bytes

Con Wireshark: *Statistics → Conversations → TCP* (tramas y bytes por
sentido) y *Statistics → Protocol Hierarchy*. O con `tshark` (comandos en
[herramientas/estadisticas_captura.md](herramientas/estadisticas_captura.md)):

| Modo | Escenario | Tramas totales | Bytes totales | Tramas OPC UA | Mensajes PublishResponse / ReadResponse | KeepAlive |
|---|---|---|---|---|---|---|
| A · Read | rampa en movimiento | *pendiente* | *pendiente* | *pendiente* | *pendiente* | — |
| B · Suscripción | rampa en movimiento | *pendiente* | *pendiente* | *pendiente* | *pendiente* | *pendiente* |
| A · Read | rampa detenida | *pendiente* | *pendiente* | *pendiente* | *pendiente* | — |
| B · Suscripción | rampa detenida | *pendiente* | *pendiente* | *pendiente* | *pendiente* | *pendiente* (~56/min previstos) |

Las tramas totales incluyen los ACK puros de TCP, que la predicción no cuenta:
el banco va a dar **más tramas** que la tabla §4.1. Si la relación B/A se
aparta mucho de la prevista, es un hallazgo: registrarlo en
[INCONVENIENTES.md](evidencia/INCONVENIENTES.md) con la explicación.

### 4.4 Parámetros de la suscripción: documentarlos desde la trama

Abrir `captura_modo_B.pcapng` en Wireshark con el filtro `opcua` y ubicar:

| Mensaje | Campo | Pedido (config) | Revisado (medido) |
|---|---|---|---|
| CreateSubscriptionRequest / Response | PublishingInterval | 100 ms | *pendiente* |
| | MaxKeepAliveCount | 10 | *pendiente* |
| | LifetimeCount | 300 | *pendiente* |
| CreateMonitoredItemsRequest / Response | SamplingInterval (cada ítem) | 100 ms | *pendiente* |
| | QueueSize | 1 | *pendiente* |
| | DiscardOldest | true | (solo en el pedido) |

Los valores **revisados** son los que rigen. En la PC dieron exactamente los
pedidos (`prueba_opcua_tramas.py` §6). Explicación de cada parámetro y del
mecanismo PublishRequest/PublishResponse con KeepAlive:
[protocolo-opcua.md §7](docs/protocolo-opcua.md).

En la captura **quieta** del Modo B: medir el tiempo entre KeepAlive
consecutivos (Wireshark: filtro `opcua.servicenodeid.numeric == 829`, columna
de tiempo *delta displayed*). Se esperan ≈ 1 s (en la PC: 1,09 s).

### 4.5 Latencia pulsador → LED

**Método:** cada placa registra el instante del flanco de su pulsador
(`LATENCIA pulsador_local=…`) y el de cada cambio de su LED digital
(`LATENCIA led_digital=…`). Con los relojes sincronizados por chrony:

1. Anotar el desvío: `chronyc tracking | grep "System time"` en la RPi 2.
2. Presionar y soltar el pulsador de la RPi 1 **20 veces**, a ritmo irregular.
3. Repetir con el pulsador de la RPi 2.
4. Extraer y calcular:

   ```bash
   $ journalctl -u nodered --since "5 min ago" > ~/lat_rpi1.log     # en cada placa
   PS> python tarea-2\herramientas\medir_latencia.py lat_rpi1.log lat_rpi2.log   # RPi 1 -> LED de RPi 2
   PS> python tarea-2\herramientas\medir_latencia.py lat_rpi2.log lat_rpi1.log   # RPi 2 -> LED de RPi 1
   ```

5. Hacerlo en Modo A y en Modo B.

**Hipótesis** (para contrastar). Atención: pigpio entrega el flanco **después**
de que el nivel se mantuvo estable 25 ms (filtro de rebote), así que la marca
`LATENCIA pulsador_local` ya es posterior al antirrebote. La latencia medida
con los registros **excluye** esos 25 ms; la física (la que mide el video),
los **incluye**.

| Sentido | Mecanismo | Componentes (medidos por registro) | Esperado por registro | Esperado físico (video) |
|---|---|---|---|---|
| RPi 2 → LED de RPi 1 | **Write al cambiar** (evento) | Write + ida y vuelta (< 1 ms) + Node-RED en ambas placas | **~5 ms**, poca dispersión, igual en A y en B | ~30 ms |
| RPi 1 → LED de RPi 2, Modo A | Read cada 100 ms (sondeo) | espera al próximo Read (0-100 ms, uniforme) + ida y vuelta | media **~50 ms**, máximo ~105 ms | ~75 ms |
| RPi 1 → LED de RPi 2, Modo B | Muestreo 100 ms + publicación 100 ms | espera al muestreo (0-100) + espera a la publicación | media **~75-100 ms**, máximo ~205 ms | ~100-125 ms |

La asimetría es esperable: **escribir** es un evento, y **leer** depende de un
muestreo. Con la suscripción, el pulsador **no** se ve más rápido que con el
Read de 100 ms: lo que se gana es tráfico (§4), no latencia.

| Sentido / modo | n | mín (ms) | media | mediana | p95 | máx | desvío chrony |
|---|---|---|---|---|---|---|---|
| RPi 2 → RPi 1, Modo A | *pendiente* | | | | | | |
| RPi 2 → RPi 1, Modo B | *pendiente* | | | | | | |
| RPi 1 → RPi 2, Modo A | *pendiente* | | | | | | |
| RPi 1 → RPi 2, Modo B | *pendiente* | | | | | | |

**Validación independiente** (opcional): filmar las dos placas juntas con un
celular en cámara lenta (240 fps ≈ 4,2 ms por cuadro) y contar los cuadros
entre el LED de la placa que tiene el pulsador (un LED auxiliar no hace falta:
se usa el dedo) y el LED remoto. Si concuerda con los timestamps, la
sincronización de relojes es correcta.

## 5. Escrituras: comprobación en la captura

En `captura_modo_B.pcapng` con el filtro `opcua`:

- WriteRequest de `Cliente.Rampa` cada ~100 ms (consigna: cada 100 ms).
- WriteRequest de `Cliente.EstadoPulsador` **solo** al presionar o soltar, no
  periódicamente (consigna: al cambiar). Contar: tantos como flancos.

| Comprobación | Esperado | Medido |
|---|---|---|
| Período de Write de `Cliente.Rampa` | ~100 ms | *pendiente* |
| Write de `Cliente.EstadoPulsador` en 60 s sin tocar el pulsador | 0 | *pendiente* |
| Write de `Cliente.EstadoPulsador` por pulsación | 2 (presionar + soltar) | *pendiente* |

Si aparecen más de 2 Write por pulsación, revisar el antirrebote
([INCONVENIENTES.md I-01](evidencia/INCONVENIENTES.md)).

## 6. Prueba de desconexión (consigna 3.6)

### 6.1 Comprobación previa: ¿adónde va el tráfico sin cable?

Con el sistema funcionando, **desconectar el cable** y en la RPi 2 ejecutar a
los 10 s:

```bash
$ ip route get 192.168.10.1
$ nmcli -f DEVICE,STATE dev
```

- Si responde `… dev eth0 …`: la ruta se mantiene. Continuar con §6.2.
- Si responde `… via <router> dev wlan0 …`: **NetworkManager quitó la ruta del
  enlace** al perder la portadora, y los reintentos de conexión del cliente
  saldrían por la Wi-Fi, lo que incumple la Parte 1.4. Registrarlo como
  inconveniente y aplicar en **ambas placas** una ruta de bloqueo con métrica
  alta, que solo actúa cuando la ruta de `eth0` no está:

  ```bash
  $ sudo nmcli con modify pdci-eth0 +ipv4.routes "192.168.10.0/24 type=prohibit metric=4000"
  ```

  Si NetworkManager también la retira con el enlace caído, instalarla en el
  perfil de la Wi-Fi (`nmcli con show` para ver su nombre). Repetir la
  comprobación: `ip route get` debe responder `prohibit`.

### 6.2 Procedimiento

Tres cortes, con la consola de ambas placas abierta
(`journalctl -u nodered -f`) y el Modo B activo:

| Corte | Duración | Qué se espera observar |
|---|---|---|
| Corto | ~5 s | Probablemente **nada** a nivel OPC UA: TCP retransmite los segmentos perdidos y la conexión sigue. Los LED se congelan unos segundos y luego se pone al día |
| Medio | ~20 s (menor que el Lifetime de 30 s) | El cliente detecta la caída (`connection_lost`), reintenta (`backoff`) y al volver el cable abre un **canal nuevo** y **reactiva la misma sesión**; la suscripción sobrevive (`after_reconnection`) |
| Largo | ~45 s (mayor que 30 s, menor que la sesión de 60 s) | La suscripción **expiró** en el servidor (LifetimeCount): al reconectar, la sesión se recupera pero la suscripción se recrea o transfiere |

Durante cada corte, verificar y anotar:

| Comprobación | Corto | Medio | Largo |
|---|---|---|---|
| LED PWM de cada placa congelado en el último valor | *pend.* | *pend.* | *pend.* |
| Generador local sigue (`generada=` cambia en la consola) | *pend.* | *pend.* | *pend.* |
| `antiguedad` en la consola de la RPi 2 crece | *pend.* | *pend.* | *pend.* |
| Primer evento en C7 y a qué tiempo del corte | *pend.* | *pend.* | *pend.* |
| StatusCode informado (C7, `read_error`/`write_error`, `subscription_status`) | *pend.* | *pend.* | *pend.* |
| Escrituras omitidas (contador en C1) | *pend.* | *pend.* | *pend.* |
| Tiempo desde reconectar el cable hasta datos nuevos | *pend.* | *pend.* | *pend.* |
| Secuencia de eventos de recuperación | *pend.* | *pend.* | *pend.* |

Guardar los eventos de C7 de cada corte en `evidencia/consola/desconexion_*.txt`.
Si se captura con `tcpdump` durante la reconexión, se ven: retransmisiones TCP,
un nuevo SYN, HEL/ACK, **OPN nuevo** (otro SecureChannelId), **ActivateSession**
sobre el canal nuevo y, si la suscripción sobrevivió, **Republish** o la
reanudación de los Publish.

**Por qué los LED se congelan y no se apagan:** C4 solo actúa cuando llega un
dato; sin datos no hace nada y el GPIO conserva su último estado. Es la
política de **mantener el último valor bueno**, la habitual en control. Una
alternativa sería llevar las salidas a un estado seguro después de un tiempo
sin datos (*watchdog* de comunicación); la consigna pide congelar.

Explicación de por qué la sesión sobrevive al canal:
[protocolo-opcua.md §4](docs/protocolo-opcua.md).

## 7. Corrección gamma (opcional, consigna 3.7)

**Activación:** `config.js` → `senales.usarGamma: true`, copiar a ambas placas
y reiniciar Node-RED.

**Qué hace:** `brillo = 255 · (valor / 65535)^2,2` en lugar de
`brillo = 255 · valor / 65535` (`senales.escala255`, verificada en
`prueba_senales.js` prueba 6).

**Por qué una rampa lineal en PWM no se percibe lineal:**

1. El LED convierte el ciclo de trabajo en flujo luminoso **promedio**
   proporcional: el PWM a 800 Hz es invisible, y el ojo integra.
2. La **percepción** del brillo no es proporcional al flujo luminoso. Sigue
   aproximadamente una ley de potencia (Stevens): brillo percibido ∝ L^0,33-0,5.
   La luminosidad CIE L* usa una raíz cúbica. El ojo es mucho más sensible a
   los cambios con poca luz que con mucha (ley de Weber-Fechner: el umbral
   diferencial es proporcional al nivel).
3. Consecuencia: con escala lineal, el primer 20 % del ciclo de trabajo cubre
   la mayor parte del cambio **percibido**, y la mitad superior de la rampa
   parece casi constante.
4. Aplicar el exponente 2,2, la inversa aproximada de la respuesta del ojo y
   el mismo de la curva sRGB (IEC 61966-2-1), compensa: a mitad de la rampa el
   ciclo de trabajo es 22 % (56/255), que **se percibe** como la mitad del
   brillo.

**Verificación:** observar la rampa triangular de la RPi 2 en el LED de la
RPi 1 con gamma desactivada y activada. Con gamma, la subida y la bajada deben
percibirse **uniformes**; sin gamma, el LED "satura" rápido y pasa la mayor
parte del tiempo brillante.

| | Sin gamma | Con gamma 2,2 |
|---|---|---|
| Percepción de la rampa triangular | *pendiente* | *pendiente* |

## 8. Lista de verificación de la Parte 3

- [ ] Cada LED PWM muestra la forma de onda de la **otra** placa.
- [ ] Consola de ambas placas guardada (60 s).
- [ ] Cuatro capturas de 60 s (A/B × movimiento/quieto) y tabla §4.3.
- [ ] Parámetros revisados de la suscripción leídos de la trama (§4.4).
- [ ] KeepAlive identificados y su período medido.
- [ ] Latencias en los cuatro casos (§4.5) con el desvío de chrony.
- [ ] Escrituras verificadas en la captura (§5).
- [ ] Comprobación de ruta sin cable (§6.1) y tres cortes documentados (§6.2).
- [ ] (Opcional) gamma.
