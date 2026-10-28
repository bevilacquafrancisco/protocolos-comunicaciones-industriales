# Evidencia del banco

Requerimiento adicional 4 de la consigna: capturas `.png` y archivos usados en el informe.
Se llena desde la PC al final de cada sesión ([guia/04 §0](../guia/04_resolucion_consignas.md#0-organización-del-tiempo-y-la-evidencia)).

| Carpeta | Contenido | Cómo llega |
|---|---|---|
| `rpi1/registros/` | Salida del servidor (`servidor_<fecha>.log`) | `PC> scp -r rpi1:TP2_OPC/registros evidencia\rpi1\` |
| `rpi2/registros/` | Salida de los clientes | `PC> scp -r rpi2:TP2_OPC/registros evidencia\rpi2\` |
| `capturas/` | `.pcapng` de `tcpdump` | `PC> scp "rpi2:*.pcapng" evidencia\capturas\` |
| `png/` | Capturas de pantalla (UaExpert, Wireshark) y fotos | A mano |

**Análisis ya hecho:** [ANALISIS_captura_none.md](ANALISIS_captura_none.md), Parte 4.1 – 4.6 y parámetros de 3.4
sobre `capturas/captura_none.pcapng`.

Nombres de las `.png`: `parte<N>_<consigna>_<qué>.png`, por ejemplo `parte2_5c_tendencia_rampa.png`,
`parte4_8_signandencrypt_campos.png`. Así el informe las referencia sin ambigüedad.

**[SEC] Nunca va acá:** `pki/own/*_key.pem` (claves privadas), `~/.pdci-t2.env` (clave del usuario
OPC UA), contraseñas de las placas o de la Wi-Fi, ni capturas de pantalla donde se vean. Las capturas
`.pcapng` en modo None muestran el nombre de usuario `operador` (la contraseña va cifrada): es
aceptable y es justamente lo que se analiza en 4.9.
