# v1 — Versión original (Agustina Peralta)

Versión Python/asyncua tal como se subió al repositorio (commits `65df5b9`, `4cd1f4c`, `fdbd322`).
Se conserva **sin modificar** como evidencia de proceso. La revisión completa está en
[CORRECCIONES.md](CORRECCIONES.md) y la versión que la corrige, en
[../v2-correccion-python/](../v2-correccion-python/).

## Archivos

| Archivo | Placa | ¿Usar? | Nota |
|---|---|---|---|
| [servidor_ns1.py](servidor_ns1.py) | RPi 1 | **Sí** | Deja el modelo en `ns=1`, como piden los NodeIds de la consigna |
| [servidor.py](servidor.py) | RPi 1 | **No** | Deja el modelo en `ns=2`: el cliente recibe `BadNodeIdUnknown` y nada funciona |
| [cliente.py](cliente.py) | RPi 2 | Sí | Modo A (Read cada 100 ms; hace 2 Read de 1 nodo, no 1 Read de 2) |
| [cliente_suscripcion_v2.py](cliente_suscripcion_v2.py) | RPi 2 | Sí | Modo B (suscripción de 100 ms, con los parámetros por defecto de asyncua) |
| [puesta_en_marcha.txt](puesta_en_marcha.txt) | — | Referencia | Guía original. Reemplazada por [../../guia/](../../guia/) |
| `Puesta_en_marcha_TP_OPC_UA_Raspberry_Pi.docx` | — | Referencia | **[SEC] Contiene la contraseña vieja de las placas** (CORRECCIONES §0). Las microSD nuevas se graban con contraseñas nuevas: esa queda inválida. No compartir el archivo |
| `Checklist_TP_OPC_UA.docx` | — | Referencia | Lista de verificación original |
| [CORRECCIONES.md](CORRECCIONES.md) | — | Leer | Qué falta o está mal, con prioridad y código probado |

## Qué cubre y qué no

| Consigna | v1 | Por qué |
|---|---|---|
| Partes 1, 2 y 3.1-3.3, 3.6 | Sí | Servidor, modelo, rampas, LEDs, Modo A/B y reconexión funcionan |
| 3.4 KeepAlive | Parcial | Sin `--rampa-detenida`, y con KeepAlive por defecto (cada 7,5 min) no aparece ninguno en 60 s |
| 3.4 Latencia | No | No imprime las líneas `LATENCIA` ni usa relojes sincronizados |
| 4.7-4.8 Sign / SignAndEncrypt | No | Solo expone el endpoint None, sin certificados |
| 4.9 Usuario y contraseña | **No (inseguro)** | Anuncia login pero acepta **cualquier** usuario y contraseña |

Para la entrega y la defensa se usa **v2**. Esta versión sirve para mostrar la evolución del
diseño o como respaldo de las Partes 1 a 3.

## Cómo ejecutarla

Carga en las placas: [../../guia/02_cargar_programas_SSH.md](../../guia/02_cargar_programas_SSH.md)
(opción **v1**). Luego:

```bash
# RPi 1
cd ~/TP2_OPC_original && source ~/opcua-env/bin/activate && python servidor_ns1.py
# RPi 2
cd ~/TP2_OPC_original && source ~/opcua-env/bin/activate && python cliente_suscripcion_v2.py   # o cliente.py
```

Conexionado: el mismo de v2 ([../../guia/03_conexionado_electrico.md](../../guia/03_conexionado_electrico.md)).
El comentario de `servidor_ns1.py` menciona una pull-down **externa** de 10 kΩ; el código activa la
**interna** (`Button(17, pull_up=False)`), así que no hace falta la resistencia (CORRECCIONES §10 e).
