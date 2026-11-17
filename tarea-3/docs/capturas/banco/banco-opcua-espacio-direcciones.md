# Espacio de direcciones OPC UA — verificación F4

> Generado por `tools/verificar_opcua.js` el 2026-11-17T03:07:59.442Z contra `opc.tcp://192.168.10.1:4840`, modo **None**, usuario **operador**. Medido **en el banco real**: Raspberry Pi 4 (Node-RED + servidor OPC UA) por el cable Ethernet, con el ESP32 por RS-485. Modo None porque el certificado del verificador no está en la lista de confianza del servidor (Sign y SignAndEncrypt fueron rechazados con ERR, como corresponde). Las escrituras accionaron los LED reales.
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
| `ns=1;s=Dispositivo1.Inputs.Pulsador` | 1:Pulsador | Boolean | CurrentRead | CurrentRead | false | Good | 2026-11-17T02:58:38.238Z | 2026-11-17T02:58:38.238Z | — |
| `ns=1;s=Dispositivo1.Inputs.Potenciometro` | 1:Potenciometro | UInt16 | CurrentRead | CurrentRead | 0 | Good | 2026-11-17T02:58:45.530Z | 2026-11-17T02:58:45.530Z | 0 … 4095 |
| `ns=1;s=Dispositivo1.Inputs.Potenciometro_pct` | 1:Potenciometro_pct | Float | CurrentRead | CurrentRead | 0 | Good | 2026-11-17T02:58:45.530Z | 2026-11-17T02:58:45.530Z | 0 … 100 |
| `ns=1;s=Dispositivo1.Outputs.LedDigital` | 1:LedDigital | Boolean | CurrentRead + CurrentWrite | CurrentRead + CurrentWrite | true | Good | 2026-11-17T03:06:20.990Z | 2026-11-17T03:06:20.990Z | — |
| `ns=1;s=Dispositivo1.Outputs.LedPWM` | 1:LedPWM | UInt16 | CurrentRead + CurrentWrite | CurrentRead + CurrentWrite | 128 | Good | 2026-11-17T03:06:21.075Z | 2026-11-17T03:06:21.075Z | 0 … 255 |
| `ns=1;s=Status.MODBUS.Estado` | 1:Estado | String | CurrentRead | CurrentRead | "DONE" | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.OK` | 1:OK | UInt32 | CurrentRead | CurrentRead | 121342 | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.CRC_ERROR` | 1:CRC_ERROR | UInt32 | CurrentRead | CurrentRead | 24 | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.TIMEOUT` | 1:TIMEOUT | UInt32 | CurrentRead | CurrentRead | 4886 | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.EXCEPTION` | 1:EXCEPTION | UInt32 | CurrentRead | CurrentRead | 0 | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.UltimaTramaTx` | 1:UltimaTramaTx | String | CurrentRead | CurrentRead | "01 03 00 00 00 01 84 0A" | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.UltimaTramaRx` | 1:UltimaTramaRx | String | CurrentRead | CurrentRead | "01 03 02 00 80 B9 E4" | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.MODBUS.LatenciaMs` | 1:LatenciaMs | UInt16 | CurrentRead | CurrentRead | 24 | Good | 2026-11-17T03:07:58.689Z | 2026-11-17T03:07:58.689Z | — |
| `ns=1;s=Status.OPCUA.Estado` | 1:Estado | String | CurrentRead | CurrentRead | "DONE" | Good | 2026-11-17T02:23:59.066Z | 2026-11-17T02:23:59.066Z | — |

## Escrituras

| Nodo | Valor pedido | StatusCode del WriteResponse | Tiempo (ms) | Valor releído |
|---|---|---|---|---|
| Inputs/Pulsador (solo lectura) | true | BadNotWritable (0x803b0000) | — | — |
| Outputs.LedDigital | true | Good (0x00000000) | 45 | true |
| Outputs.LedPWM | 128 | Good (0x00000000) | 55 | 128 |
| Outputs.LedPWM | 300 | BadOutOfRange (0x803c0000) | 4 | 128 |

## Verificaciones

| Resultado | Verificación | Detalle |
|---|---|---|
| OK | jerarquia Inputs/Outputs/Status |  |
| OK | namespace ns=1 = urn:unraf:pdci:t3 |  |
| OK | variables del diccionario presentes | 14 variables |
| OK | Write sobre Inputs.Pulsador (solo lectura) rechazado | BadNotWritable (0x803b0000) |
| OK | Write Outputs.LedDigital = true confirmado por el esclavo | Good (0x00000000) en 45 ms |
| OK | Write Outputs.LedPWM = 128 confirmado por el esclavo | Good (0x00000000) en 55 ms |
| OK | Write Outputs.LedPWM = 300 fuera de EURange rechazado y valor intacto | BadOutOfRange (0x803c0000) |
