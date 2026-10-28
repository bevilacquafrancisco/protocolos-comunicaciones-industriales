# Estadísticas de las capturas con Wireshark y tshark

**Tarea N.º 2 — OPC UA** · Comandos para las Partes 3.4 y 4.

`tshark` es la versión de línea de comandos de Wireshark y se instala junto
con él. En Windows queda en `C:\Program Files\Wireshark\tshark.exe`: agregar
esa carpeta al `PATH` o invocarlo con la ruta completa. Los comandos son los
mismos en PowerShell y en bash.

> Los nombres de los campos del disector `opcua` pueden variar entre versiones
> de Wireshark. Si un filtro no funciona: seleccionar el campo en el panel de
> detalle → clic derecho → *Apply as Filter → Selected*, y copiar el nombre que
> aparece en la barra de filtro.

## 1. Totales de una captura (Parte 3.4)

```powershell
tshark -r captura_modo_A.pcapng -q -z io,stat,0                 # tramas y bytes totales
tshark -r captura_modo_A.pcapng -q -z io,stat,0,"opcua"         # solo tramas con OPC UA
tshark -r captura_modo_A.pcapng -q -z conv,tcp                   # por sentido de la conexión
```

## 2. Mensajes por servicio

```powershell
tshark -r captura_modo_B.pcapng -Y opcua -T fields -e opcua.servicenodeid.numeric | sort | uniq -c
```

| Número | Servicio |
|---|---|
| 631 / 634 | ReadRequest / ReadResponse |
| 673 / 676 | WriteRequest / WriteResponse |
| 826 / 829 | PublishRequest / PublishResponse |
| 787 / 790 | CreateSubscription |
| 751 / 754 | CreateMonitoredItems |

(En PowerShell, `sort | uniq -c` se reemplaza por
`Group-Object | Select-Object Count,Name`.)

## 3. KeepAlive: período

Con la rampa detenida (Modo B), todos los PublishResponse son KeepAlive:

```powershell
tshark -r captura_modo_B_quieto.pcapng -Y "opcua.servicenodeid.numeric == 829" -T fields -e frame.time_relative -e frame.len
```

La diferencia entre tiempos consecutivos es el período (esperado ≈ 1 s).

## 4. Escrituras de la rampa y del pulsador (Parte 3.3)

```powershell
tshark -r captura_modo_B.pcapng -Y "opcua.servicenodeid.numeric == 673" -T fields -e frame.time_relative -e frame.len
```

Los Write de `Cliente.Rampa` (≈ 180 bytes de trama) aparecen cada ~0,1 s; los
de `Cliente.EstadoPulsador` (8 bytes más) solo en los flancos.

## 5. Latencia petición → respuesta por modo de seguridad (Parte 4.8)

```powershell
tshark -r captura_sign.pcapng -Y "tcp.port==4840 && tcp.len>0" -T fields -e frame.time_relative -e tcp.srcport -e tcp.len > campos_sign.tsv
python tarea-2\herramientas\latencia_captura.py campos_sign.tsv
```

Funciona igual en SignAndEncrypt porque no necesita leer el contenido. Medir
con el **Modo A y la rampa del servidor detenida**: así cada mensaje del
cliente tiene una única respuesta del servidor.

## 6. Extraer una trama para decodificarla byte a byte (Partes 4.4 y 4.5)

En Wireshark: seleccionar la trama → clic derecho en *Frame* → **Copy → …as a
Hex Stream**. Luego:

```powershell
python tarea-2\herramientas\opcua_tramas.py --ethernet --markdown "<pegar acá>" > tabla.md
```

O por número de trama, con tshark:

```powershell
tshark -r captura_none.pcapng -Y "frame.number == 42" -T fields -e frame.raw
```

(`frame.raw` requiere Wireshark 4.x; en versiones anteriores, usar la copia
desde la interfaz.)
