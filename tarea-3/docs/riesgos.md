# Registro de riesgos — Tarea Nº3

Fase F0 · 2026-11-08 · Se revisa al cerrar cada fase. Un riesgo no se borra: se cierra con la
evidencia que lo cerró.

**Escala.** Probabilidad (P) e impacto (I) de 1 a 3. Exposición = P × I.
Impacto 3 = invalida un invariante o la demo; 2 = obliga a rehacer una fase; 1 = cuesta horas.

**Disparador de contingencia** = la observación concreta que obliga a abandonar el plan principal.
Sin disparador medible, un riesgo no está gestionado.

---

## Resumen ordenado por exposición

| ID | Riesgo | P | I | Exp. | Fase |
|---|---|---|---|---|---|
| R-05 | El esclavo de la cátedra no encaja en el maestro configurable | 3 | 3 | **9** | Defensa |
| R-01 | El stack propio del esclavo rinde peor que `umodbus` | 2 | 3 | **6** | F2 |
| R-09 | Seguridad OPC UA nunca probada en banco; relojes sin RTC | 2 | 3 | **6** | F4 |
| R-06 | Broker en la nube inaccesible desde la red del aula | 2 | 3 | **6** | F5-Defensa |
| R-04 | Adaptador USB-RS485 sin dirección automática o con latencia alta | 2 | 3 | **6** | F3 |
| R-10 | ~~ADR-010 sin decidir bloquea F2~~ **Cerrado 2026-11-09** | — | — | 0 | — |
| R-02 | Raspberry Pi disponible solo en el laboratorio | 3 | 2 | **6** | F3-F4 |
| R-07 | El ESP32 #2 hereda el 11,6 % de error del Esclavo 2 de la T1 | 2 | 2 | 4 | F2 |
| R-14 | Ciclos DDEATH/DBIRTH por fallos aislados | 2 | 2 | 4 | F5 |
| R-11 | Citar números de la T2 que no tienen evidencia en el repositorio | 2 | 2 | 4 | Informe |
| R-13 | Biblioteca Sparkplug B para Python inmadura o sin empaquetar | 2 | 2 | 4 | F5 |
| R-03 | `node-opcua` no corre en la imagen de la Raspberry Pi del laboratorio | 1 | 3 | 3 | F4 |
| R-08 | Credenciales MQTT expuestas en el navegador | 3 | 1 | 3 | F6 |
| R-12 | Restaurar mal la microSD del laboratorio | 1 | 3 | 3 | F3-F4 |
| R-15 | Erratas de la consigna mal interpretadas (nombre de archivo, criterios) | 2 | 1 | 2 | Entrega |

---

## Detalle

### R-01 — El stack propio del esclavo rinde peor que la librería que reemplaza

| | |
|---|---|
| **Causa** | I-01 obliga a reescribir lo que hacía `umodbus`. La librería resolvía detalles que se pierden fácil: `uart.flush()` + 1 carácter antes de bajar DE/RE, 200 µs tras subirlo, delimitación por silencio con `ticks_us` |
| **Efecto** | Tramas truncadas, timeouts, o tasa de error > 0 % donde la T1 midió 0,0 % |
| **Mitigación** | (1) Tests en PC del parser y del CRC con vectores *golden* de dos oráculos. (2) Replicar el `_send()` de `umodbus` 2.3.7 y citarlo. (3) Comprobar al arrancar que `UART.flush` existe (MicroPython ≥ 1.20). (4) Criterio de aceptación de banco: ≥ 750 ciclos con 0 % a 9600 bps, igual que la T1 |
| **Disparador** | Tasa de error > 0,5 % en 750 ciclos a 9600 bps con un solo esclavo, **o** cualquier trama truncada en el sniffer |
| **Contingencia** | Pasar el esclavo a C++/Arduino (ADR-010, opción 2), con el mismo mapa y los mismos vectores |

### R-02 — La Raspberry Pi solo está en el laboratorio

| | |
|---|---|
| **Causa** | `CLAUDE.md` §3: todo el dispositivo 2 se desarrolla en la notebook |
| **Efecto** | Diferencias de SO, de driver serie o de versión de Node.js aparecen tarde |
| **Mitigación** | Flows y módulos versionados y generados (patrón de la T2 v3); fijar versiones de Node.js, Node-RED, `node-opcua` y `node-red-node-serialport`; una sesión de laboratorio dedicada solo a V-1 y V-4 del spike **antes** de F3 |
| **Disparador** | Llegar a F4 sin haber corrido Node-RED con el adaptador USB-RS485 en la Raspberry Pi real |
| **Contingencia** | Usar la notebook como dispositivo 2 en la demo (la consigna admite "miniPC") y declararlo en el informe |

### R-03 — `node-opcua` no instala o no corre en la Raspberry Pi del laboratorio

| | |
|---|---|
| **Causa** | Imagen distinta a la de la T2; arquitectura o Node.js viejos |
| **Efecto** | ADR-011 inviable |
| **Mitigación** | Verificación V-1 del spike en la primera sesión de laboratorio |
| **Disparador** | `npm i node-opcua@2.160.0` falla en la placa, **o** la prueba de integración del servidor no pasa en F4 tras un día de trabajo |
| **Contingencia** | Plan B del spike: servidor `asyncua` 2.1.0 (de `servidor.py` de la T2 v2) con puente TCP en `127.0.0.1` a Node-RED. Costo 2,5-3,5 días |

### R-04 — Adaptador USB-RS485 sin conmutación automática o con latencia alta

| | |
|---|---|
| **Causa** | Modelo del adaptador desconocido. La T1 documentó agrupamiento de 1-16 ms en conversores económicos (`protocolo-comunicacion.md` §4) |
| **Efecto** | Sin dirección automática el maestro no puede transmitir; con latencia alta se infla `LatenciaMs` y puede vencer el timeout |
| **Mitigación** | Delimitación por longitud (ADR-012), que no depende de la latencia; leer `latency_timer` y bajarlo a 1 ms si es FTDI; prueba de eco con el sniffer de la T1 |
| **Disparador** | El esclavo no responde nunca con el cableado verificado, **o** latencia de respuesta medida > 50 ms |
| **Contingencia** | Usar como maestro un MAX485 en el UART de la Raspberry Pi con DE/RE por GPIO (exige adaptación 5 V → 3,3 V en RO: los GPIO de la Raspberry Pi **no toleran 5 V**) |

### R-05 — El esclavo de la cátedra no encaja en el maestro configurable (riesgo mayor)

| | |
|---|---|
| **Causa** | Se desconoce todo: Unit ID, baud, paridad, mapa, FC soportadas, tipos (32 bits, float, word swap), si es RTU o ASCII |
| **Efecto** | Falla I-04 frente al tribunal, en vivo |
| **Mitigación** | (1) Mapa de registros como **tabla de datos** editable, nunca código. (2) Preajustes 9600 8N1 y 19200 8E1, y barrido de baud × paridad × ID (ADR-007). (3) Soportar FC 01-06 y 0F/10, tipos UInt16/Int16/UInt32/Float32 con orden de palabras configurable. (4) Ensayo cronometrado con el ESP32 #2 configurado por un tercero, objetivo < 3 min. (5) **Preguntar en el foro** qué tipo de esclavo traerán (marca, FC, si hay datasheet) |
| **Disparador** | En el ensayo, más de 3 minutos para establecer comunicación, **o** un parámetro del esclavo de prueba que el Dashboard no pueda expresar |
| **Contingencia** | Pantalla "trama manual" en el Dashboard: escribir la PDU en hexadecimal, el maestro agrega el CRC propio y muestra la respuesta decodificada. Sirve para cualquier FC sin escribir código |

### R-06 — El broker en la nube no es accesible desde la red del aula

| | |
|---|---|
| **Causa** | Redes universitarias suelen filtrar puertos no web; 8883 (MQTT/TLS) y 8884 (WSS de HiveMQ) no son 443 |
| **Efecto** | Falla I-03 en la demo |
| **Mitigación** | Probar desde la red de la facultad en una clase anterior; tener datos móviles compartidos probados (plan de pruebas N5); preferir un broker que ofrezca WSS en 443 como respaldo (verificar en F5) |
| **Disparador** | `openssl s_client -connect <broker>:8883` o la web por WSS fallan desde la red del aula |
| **Contingencia** | Celular como punto de acceso para el dispositivo 3 y el navegador |

### R-07 — El ESP32 #2 hereda la tasa de error del Esclavo 2 de la T1

| | |
|---|---|
| **Causa** | La T1 midió 11,6 % de error en el Esclavo 2 (238 timeouts / 2046) contra 0,2 % en el Esclavo 1; la causa física no se cerró (informe T1 §9.4.4) |
| **Efecto** | El esclavo de prueba de ADR-007 genera `DEVICE NOT REACHED` espurios y ensucia el ensayo |
| **Mitigación** | Medirlo solo en el bus con el maestro nuevo antes de usarlo; revisar pull-up de RO, masa común y terminación de fábrica del módulo MAX485 (guía `tarea-1/DEPURACION-PARTE-3.md`) |
| **Disparador** | > 1 % de error a 9600 bps en 750 ciclos |
| **Contingencia** | Cambiar módulo MAX485 o placa; documentar como I-NN en `INCONVENIENTES.md` de la T3 |

### R-09 — Seguridad OPC UA nunca probada en banco; Raspberry Pi sin reloj de tiempo real

| | |
|---|---|
| **Causa** | El informe de la T2 declara que todo se probó en None y anónimo (§9). La validación X.509 depende de la hora: una Raspberry Pi sin RTC y sin NTP arranca con la hora de su último apagado |
| **Efecto** | `BadCertificateTimeInvalid` o `BadSecurityChecksFailed` el día de la demo; la comparación de modos que pide el informe queda sin datos |
| **Mitigación** | Medir None/Sign/SignAndEncrypt en banco en F4 (tamaños, latencia, establecimiento); sincronizar con chrony como en la T2 v2 (§7 del README), con la notebook como servidor NTP por Ethernet |
| **Disparador** | Cualquier error de certificado en el primer ensayo de banco con Sign |
| **Contingencia** | Demo en SignAndEncrypt con certificados de vigencia amplia generados ese día; si persiste, demo en None con las capturas de Sign/SignAndEncrypt como evidencia en el informe |

### R-10 — La decisión del lenguaje del esclavo (ADR-010) sigue abierta — **CERRADO**

**Cerrado el 2026-11-09:** Francisco eligió MicroPython con Thonny. Se conserva el registro.

| | |
|---|---|
| **Causa** | `CLAUDE.md` de la T3 supone C++/PlatformIO; la T1 y el flujo de trabajo del grupo son MicroPython/Thonny |
| **Efecto** | No se puede empezar F2 ni escribir los vectores en el lenguaje correcto |
| **Mitigación** | Decidir antes de cerrar F0; actualizar `CLAUDE.md` §3-§4 y el plan de pruebas N1.1 según la decisión |
| **Disparador** | F1 terminada sin decisión |
| **Contingencia** | Avanzar F3 (maestro) y los vectores JSON, que no dependen del lenguaje del esclavo |

### R-11 — Citar números de la T2 sin evidencia en el repositorio

| | |
|---|---|
| **Causa** | El informe T2 cita una captura de 4453 paquetes que no está versionada; describe la v1 mientras se declara presentada la v2; varias mediciones son de PC |
| **Efecto** | Un número no reproducible en el informe de la T3 |
| **Mitigación** | Citar solo `captura_none.pcapng` y los vectores; marcar "medido en PC" donde corresponda (analisis-t2.md §5) |
| **Disparador** | Un número del informe sin archivo en `docs/capturas/` o sin test que lo reproduzca |
| **Contingencia** | Repetir la medición en el banco de la T3 |

### R-12 — Restaurar mal la microSD del laboratorio

| | |
|---|---|
| **Causa** | Las placas del laboratorio traen otro programa (lección de la T2) |
| **Efecto** | Se deja inutilizada una placa ajena |
| **Mitigación** | Respaldar la imagen antes de grabar, con el procedimiento de `tarea-2/guia/01_instalar_SO_microSD.md`; o trabajar sobre una microSD propia |
| **Disparador** | Respaldo no verificado (tamaño o hash) antes de grabar |
| **Contingencia** | No grabar; usar la notebook como dispositivo 2 (R-02) |

### R-13 — Biblioteca Sparkplug B para Python

| | |
|---|---|
| **Causa** | La consigna recomienda Eclipse Tahu; su empaquetado para Python no se verificó en F0 |
| **Efecto** | Tiempo extra generando el código Protobuf a mano |
| **Mitigación** | Spike corto al inicio de F5: compilar `sparkplug_b.proto` con `protoc` y probar codificar/decodificar un NBIRTH contra MQTT Explorer |
| **Disparador** | Más de medio día sin un NBIRTH decodificado correctamente por MQTT Explorer |
| **Contingencia** | `protobuf` oficial + `sparkplug_b_pb2.py` generado y versionado, sin Tahu |

### R-14 — Ciclos DDEATH/DBIRTH por fallos aislados

| | |
|---|---|
| **Causa** | Ligar `DDEATH` a un timeout aislado reproduce el parpadeo de 1 Hz de la T1 en la capa Sparkplug |
| **Efecto** | Tráfico MQTT inútil y una web que "parpadea" en la defensa |
| **Mitigación** | ADR-014: `DDEATH` solo tras ausencia sostenida (2000 ms) |
| **Disparador** | Más de un par DDEATH/DBIRTH por minuto con el esclavo conectado |
| **Contingencia** | Subir la ausencia sostenida y revisar la capa física (R-07) |

### R-08 — Credenciales MQTT en el navegador

Ya tratado en ADR-005 (tres usuarios con privilegio mínimo por tópico). P = 3 (es inevitable en una
web estática), I = 1 con la mitigación aplicada. **Disparador:** el usuario `host_app` puede publicar
fuera de `STATE`, `NCMD` y `DCMD` → corregir las ACL del broker.

### R-15 — Erratas de la consigna

`CLAUDE.md` §9. **Mitigación:** consultar en el foro el nombre de archivo (`T2` frente a `T3`) y los
criterios de evaluación copiados de otro TP. **Disparador:** una semana antes de la entrega sin
respuesta → usar `T3` y declararlo en la carátula.

---

## Gaps de información que alimentan estos riesgos

| Gap | Riesgos |
|---|---|
| Modelo del adaptador USB-RS485 | R-04 |
| Tipo y marca del esclavo que traerá la cátedra | R-05 |
| Imagen y versión de SO de la Raspberry Pi del laboratorio | R-02, R-03, R-09, R-12 |
| Puertos abiertos en la red de la facultad | R-06 |
| Fechas de informe preliminar y defensa | Todos (no hay cronograma en el repositorio; `PLAN_TAREA3.md` no existe) |
| Decisión ADR-010 | R-01, R-10 |
