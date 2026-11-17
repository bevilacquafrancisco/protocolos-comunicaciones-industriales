# 10 · Cierre del banco y problemas frecuentes

**Objetivo:**

- la evidencia guardada y sin secretos;
- el sistema detenido en orden;
- la microSD del laboratorio restaurada;
- los cambios temporales de la notebook deshechos.

**Tiempo:** ~20 min, más la restauración.

---

## 1. Detener en orden

| Orden | Qué | Cómo | Por qué en ese orden |
|---|---|---|---|
| 1 | Observador | Ctrl+C en su terminal. Anotar la línea `violaciones:` | Cierra su archivo |
| 2 | Edge Node | **Ctrl+C** | Publica el NDEATH **intencional** antes de desconectarse (Sparkplug 3.0). Así queda registrado el cierre limpio |
| 3 | Servidor de la web | Ctrl+C en `servir.js` | |
| 4 | Raspberry Pi | `sudo poweroff`, y esperar a que el LED verde deje de parpadear | Cortar la alimentación con el sistema escribiendo puede corromper la microSD |
| 5 | ESP32 | Desenchufar el USB | |

## 2. Guardar la evidencia (sin secretos)

**2.1 Traer los registros de la Raspberry** antes de restaurar la tarjeta. Después de restaurarla, no
se pueden recuperar:

```powershell
PS> ssh pdci@rpi-pdci-t3.local "journalctl -u pdci-t3-nodered --since today > ~/banco-nodered.log"
PS> scp pdci@rpi-pdci-t3.local:banco-*.log pdci@rpi-pdci-t3.local:banco-*.txt tarea-3\docs\capturas\banco\
```

**[SEC]** **No** se copian `~/.pdci-t3/opcua-pki` (claves privadas) ni `/etc/pdci-t3-nodered.env`.

**2.2 Buscar las claves antes de subir la evidencia.** Las cuatro claves (las tres MQTT y la de OPC UA)
se buscan tal cual en la carpeta de evidencia. Se leen del `.env` para no escribirlas:

```powershell
PS> $claves = Get-Content tarea-3\.env | Select-String '^(MQTT_CLAVE_\w+|OPCUA_CLIENTE_CLAVE)=(.+)$' | ForEach-Object { $_.Matches[0].Groups[2].Value }
PS> Get-ChildItem tarea-3\docs\capturas\banco -Recurse -File | Select-String -SimpleMatch -Pattern $claves -List | Select-Object Path
PS> Remove-Variable claves
```

Tiene que salir **vacío**. Si un archivo aparece, no se sube: se recorta o se descarta.

Las capturas de pantalla también se revisan **a ojo**: el panel de configuración del broker o una
terminal con un `.env` abierto no deben aparecer.

**2.3 Subir la evidencia** con un commit propio:

```powershell
PS> git add tarea-3/docs/capturas/banco tarea-3/docs/resultados-pruebas.md tarea-3/docs/mediciones.md
PS> git status                       # .env, config.js y pki/ NO deben figurar
PS> git commit -m "docs(tarea3): registrar la evidencia del banco de laboratorio"
```

## 3. Devolver la microSD del laboratorio

Si se usó la del laboratorio (04 §1):

1. Win32 Disk Imager. *Image File*: `rpi-lab-original.img`. *Device*: la microSD. Botón **Write**.
2. Botón **Verify Only**: el SHA256 tiene que coincidir con el anotado en 04 §1.1.
3. Volver a colocarla en **su** placa y, si se puede, encenderla para ver que arranca el programa
   original.

**[SEC]** La tarjeta regrabada tiene la clave privada OPC UA y el hash del usuario. La restauración los
borra por completo. **No se devuelve nunca una tarjeta sin restaurar.**

## 4. Deshacer los cambios temporales de la notebook

PowerShell como administrador:

```powershell
PS> Remove-NetFirewallRule -DisplayName "PdCI T3 web (temporal)"
```

**La IP fija 192.168.10.2 del cable ya no se borra** (ADR-029): el banco la necesita en cada
sesión, en cualquier red. Solo si la notebook se va a usar en otra red cableada:
`Remove-NetIPAddress -InterfaceAlias "<Ethernet>" -IPAddress 192.168.10.2 -Confirm:$false`.

## 5. Al terminar el cuatrimestre

| Qué | Cómo |
|---|---|
| Credenciales del broker | Borrarlas en la consola de EMQX. La de `host_app` estuvo en un navegador: se considera expuesta |
| Broker | Borrar el deployment Serverless de EMQX, si no se va a usar más |
| Clave del usuario OPC UA | Desaparece al restaurar la tarjeta. Si la microSD es propia y se guarda, cambiarla antes de reutilizarla |
| Imágenes de respaldo | Borrar `rpi-lab-original.img` cuando la cátedra confirme que la placa quedó bien |

---

## 6. Problemas frecuentes

Ordenados por **dónde se ve** el síntoma. Cada fila dice qué capa revisar y en qué etapa está el
detalle.

### En la web

| Síntoma | Capa | Causa probable | Ver |
|---|---|---|---|
| MQTT = CREDENCIALES RECHAZADAS | MQTT | `usuario` o `clave` en `config.js` | 08 §1 |
| MQTT queda en CONECTANDO | MQTT | URL o ruta del WebSocket, o la red bloquea el puerto 8084, o el deployment está detenido | 02 §5.1, 02 §5.4, 02 §5.5 |
| Todo DESCONOCIDO, MQTT conectado | Sparkplug | El Edge Node no está publicando | 07 |
| NODO OBSOLETO | Sparkplug | El Edge Node murió o perdió internet (NDEATH) | 07 §2 |
| OPC UA = ERROR, MODBUS = SIN DATOS | OPC UA | El servicio de la Raspberry está detenido, o el cable o la confianza fallan | 05 §5, 07 §2 |
| MODBUS = DEVICE NOT REACHED | MODBus | El ESP32 está apagado o tiene otro ID o baud, o el bus está cortado | 06 §3 |
| MODBUS = CRC ERROR | MODBus | Ruido, falta de GND común, o falta el pull-up de RO | 06 §3, 03 §2 |
| Comando SIN CONFIRMAR | OPC UA o MODBus | Falta el usuario OPC UA (`BadUserAccessDenied`), o el esclavo no devuelve el eco | 07 §4 |
| El celular no abre la página | Red local | Falta la regla del firewall, el punto de acceso aísla clientes, o la IP está mal | 08 §2, 08 §4 |

### En el log del Edge Node (notebook)

| Mensaje | Causa | Ver |
|---|---|---|
| `connection lost` / reintentos sin parar, y el panel muestra `rechazado` | Falta confiar en el certificado del cliente | 07 §2.2 |
| `el certificado del servidor ... NO es el confiado` | Cambió la PKI de la Raspberry | 07 §2.1 |
| `el servidor no ofrece SignAndEncrypt` | `OPCUA_SEGURIDAD` mal escrito, u otro servidor en esa IP | 07 §1 |
| `CONNACK rechazado` | Credenciales MQTT de `edge_node` | 02 §4 |
| `SUBACK rechazado para NCMD/DCMD` | Falta una regla de `edge_node`, o tiene un error de tipeo | 02 §3.2 |
| `el broker no autoriza spBv1.0/STATE/...` | Falta la regla `spBv1.0/STATE/#` de `edge_node` en EMQX. El nodo sigue funcionando (ADR-026) | 02 §3.2 |
| `CERTIFICATE_VERIFY_FAILED` | Windows no tiene la raíz de la CA del broker | 02 §4 (`MQTT_CA`) |

### En la Raspberry (`journalctl -u pdci-t3-nodered`)

| Mensaje | Causa | Ver |
|---|---|---|
| `Cannot find module 'node-opcua'` | No se hizo `npm ci` en `edge-nodered`, o se instaló Node-RED global | 05 §3 |
| `serial port /dev/ttyUSB0 error` | No está el adaptador, tiene otro nombre, o falta `dialout` | 06 §2 |
| `EADDRINUSE :4840` | Quedó otra instancia (por ejemplo, un Node-RED del sistema) | `sudo ss -tlnp \| grep 4840` |
| `PDCI_T3_UI_HOST expone Node-RED` (no arranca) | Se cambió `UI_HOST` sin definir los usuarios | 05, comentario de la plantilla de entorno |
| Se cambió código y "no cambia nada" | Un Deploy no recarga `lib/` | 05 §8: reiniciar el servicio |
| `get_throttled` ≠ `0x0`, reinicios | Fuente insuficiente | 01 §1 |

### Antes de todo eso

| Síntoma | Causa | Ver |
|---|---|---|
| La Raspberry no aparece en la Wi-Fi | Falta el país `AR`, o la red es WPA2-Enterprise o tiene portal cautivo | 04 §2 |
| `ssh: Could not resolve hostname rpi-pdci-t3.local` | mDNS bloqueado | Usar la IP del celular (04 §3) |
| `ping 192.168.10.1` no responde | Cable, IP de la notebook, o perfil `pdci-eth0` caído | 04 §4 |
| Thonny no ve el ESP32 | Cable USB sin datos, o falta el driver CP210x o CH340 | 03 §1 |

Para aislar una falla que no está en la tabla, conviene dividir la cadena. Cada etapa tiene su
verificación independiente:

- 03 §6: el ESP32 solo, desde la notebook;
- 06 §3: el maestro, con el Dashboard;
- 07 §4: OPC UA y la nube, con `host_comandos.py`;
- 08 §3: la web.

La primera etapa que falla es la que tiene el problema.
