# Espacio de direcciones OPC UA — verificación F4

> Generado por `tools/verificar_opcua.js` el 2026-11-10T18:52:48.808Z contra `opc.tcp://127.0.0.1:4840`, modo **SignAndEncrypt**, usuario **operador**. Medido **en la PC** (Node-RED + simulador del esclavo por TCP); el banco con la Raspberry Pi queda **pendiente**.
> AccessLevel / UserAccessLevel: el segundo depende de la identidad de la sesión (ADR-009).

## Objetos

| NodeId | Ruta |
|---|---|
| `ns=1;s=Dispositivo1.Inputs` | /Dispositivo1/Inputs |
| `ns=1;s=Dispositivo1.Outputs` | /Dispositivo1/Outputs |
| `ns=1;s=Dispositivo1.Status` | /Dispositivo1/Status |
| `ns=1;s=Status.MODBUS` | /Dispositivo1/Status/MODBUS |
| `ns=1;s=Status.OPCUA` | /Dispositivo1/Status/OPCUA |
| `ns=1;s=Dispositivo1.Mapa` | /Dispositivo1/Mapa |

## Variables

| NodeId | BrowseName | DataType | AccessLevel | UserAccessLevel | Value | StatusCode | SourceTimestamp | ServerTimestamp | EURange |
|---|---|---|---|---|---|---|---|---|---|
| `ns=1;s=Dispositivo1.Inputs.Pulsador` | 1:Pulsador | Boolean | CurrentRead | CurrentRead | false | Good | 2026-11-10T18:52:46.235Z | 2026-11-10T18:52:46.235Z | — |
| `ns=1;s=Dispositivo1.Inputs.Potenciometro` | 1:Potenciometro | UInt16 | CurrentRead | CurrentRead | 3469 | Good | 2026-11-10T18:52:48.544Z | 2026-11-10T18:52:48.544Z | 0 … 4095 |
| `ns=1;s=Dispositivo1.Inputs.Potenciometro_pct` | 1:Potenciometro_pct | Float | CurrentRead | CurrentRead | 84.69999694824219 | Good | 2026-11-10T18:52:48.544Z | 2026-11-10T18:52:48.544Z | 0 … 100 |
| `ns=1;s=Dispositivo1.Outputs.LedDigital` | 1:LedDigital | Boolean | CurrentRead + CurrentWrite | CurrentRead + CurrentWrite | true | Good | 2026-11-10T18:52:39.668Z | 2026-11-10T18:52:39.668Z | — |
| `ns=1;s=Dispositivo1.Outputs.LedPWM` | 1:LedPWM | UInt16 | CurrentRead + CurrentWrite | CurrentRead + CurrentWrite | 128 | Good | 2026-11-10T18:52:39.730Z | 2026-11-10T18:52:39.730Z | 0 … 255 |
| `ns=1;s=Status.MODBUS.Estado` | 1:Estado | String | CurrentRead | CurrentRead | "DONE" | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.OK` | 1:OK | UInt32 | CurrentRead | CurrentRead | 15858 | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.CRC_ERROR` | 1:CRC_ERROR | UInt32 | CurrentRead | CurrentRead | 2 | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.TIMEOUT` | 1:TIMEOUT | UInt32 | CurrentRead | CurrentRead | 174 | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.EXCEPTION` | 1:EXCEPTION | UInt32 | CurrentRead | CurrentRead | 4028 | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.UltimaTramaTx` | 1:UltimaTramaTx | String | CurrentRead | CurrentRead | "01 03 00 00 00 01 84 0A" | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.UltimaTramaRx` | 1:UltimaTramaRx | String | CurrentRead | CurrentRead | "01 03 02 00 80 B9 E4" | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.MODBUS.LatenciaMs` | 1:LatenciaMs | UInt16 | CurrentRead | CurrentRead | 16 | Good | 2026-11-10T18:52:48.230Z | 2026-11-10T18:52:48.230Z | — |
| `ns=1;s=Status.OPCUA.Estado` | 1:Estado | String | CurrentRead | CurrentRead | "DONE" | Good | 2026-11-10T18:51:28.439Z | 2026-11-10T18:51:28.439Z | — |

## Escrituras

| Nodo | Valor pedido | StatusCode del WriteResponse | Tiempo (ms) | Valor releído |
|---|---|---|---|---|
| Inputs/Pulsador (solo lectura) | true | BadNotWritable (0x803b0000) | — | — |
| Outputs.LedDigital | true | Good (0x00000000) | 26 | true |
| Outputs.LedPWM | 128 | Good (0x00000000) | 61 | 128 |
| Outputs.LedPWM | 300 | BadOutOfRange (0x803c0000) | 2 | 128 |

## Verificaciones

| Resultado | Verificación | Detalle |
|---|---|---|
| OK | jerarquia Inputs/Outputs/Status |  |
| OK | namespace ns=1 = urn:unraf:pdci:t3 |  |
| OK | variables del diccionario presentes | 14 variables |
| OK | Write sobre Inputs.Pulsador (solo lectura) rechazado | BadNotWritable (0x803b0000) |
| OK | Write Outputs.LedDigital = true confirmado por el esclavo | Good (0x00000000) en 26 ms |
| OK | Write Outputs.LedPWM = 128 confirmado por el esclavo | Good (0x00000000) en 61 ms |
| OK | Write Outputs.LedPWM = 300 fuera de EURange rechazado y valor intacto | BadOutOfRange (0x803c0000) |
