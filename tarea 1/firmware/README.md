# Firmware — Tarea Nº1 MODBus RTU

Tres nodos ESP32 con MicroPython sobre un bus RS-485 compartido.

| Carpeta | Se carga en | Rol |
|---|---|---|
| [comun/](comun/) | Los tres nodos | Configuración y capa de periféricos (HAL) |
| [esclavo/](esclavo/) | Esclavo 1 y Esclavo 2 | Servidor MODBus RTU |
| [maestro/](maestro/) | Maestro | Cliente MODBus RTU con máquina de estados |

**El mismo archivo `esclavo/main.py` corre en ambos esclavos.** El Unit ID lo
determina el jumper de GPIO13 en el arranque: abierto = ID 1, puenteado a GND =
ID 2. Ver el porqué en [docs/PINOUT.md](../docs/PINOUT.md) §2.1.

---

## 1. Requisitos previos

| Componente | Versión | Verificación |
|---|---|---|
| MicroPython para ESP32 | ≥ 1.19 | `import sys; sys.implementation` en el REPL |
| `mpremote` (herramienta de PC) | ≥ 1.20 | `mpremote --version` |
| `esptool` (solo para grabar MicroPython) | ≥ 4.0 | `esptool --version` |
| micropython-modbus (`umodbus`) | rama `develop` | ver §3 |

```bash
pip install mpremote esptool
```

## 2. Grabar MicroPython en el ESP32 (una vez por placa)

```bash
# 1. Descargar el firmware desde https://micropython.org/download/ESP32_GENERIC/
# 2. Borrar la flash por completo (evita arrastrar restos de un firmware previo)
esptool --chip esp32 --port COM3 erase_flash

# 3. Grabar
esptool --chip esp32 --port COM3 --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-20240602-v1.23.0.bin
```

Reemplazar `COM3` por el puerto real de cada placa (Administrador de dispositivos
en Windows). **Anotar qué puerto corresponde a qué nodo**: con tres ESP32
conectados a la vez es facilísimo cargar el firmware del maestro en un esclavo.

Verificación: `mpremote connect COM3 repl` debe mostrar el prompt `>>>`.

## 3. Instalar la librería micropython-modbus

La librería no viaja con MicroPython. Hay dos caminos y **para este trabajo
corresponde el offline**, porque ninguno de los nodos usa WiFi.

### 3.1 Camino offline (recomendado)

```bash
# En la PC, una sola vez:
git clone https://github.com/brainelectronics/micropython-modbus.git
cd micropython-modbus

# Por cada ESP32:
mpremote connect COM3 cp -r umodbus :
```

Ventaja adicional: queda una copia del código fuente de la librería en la PC, que
es lo que permite citar en el informe los parámetros exactos de cada función
(requisito de la consigna: "en el caso de emplear librerías, especificar qué
parámetros requiere la configuración, qué funciones se emplean y qué parámetros
con tipo requieren").

### 3.2 Camino por red (solo si el ESP32 tiene WiFi configurado)

```bash
mpremote connect COM3 mip install github:brainelectronics/micropython-modbus
```

`mip` se ejecuta **en el dispositivo** y necesita conexión a Internet desde el
ESP32. No aplica a este montaje.

### 3.3 Verificación

```bash
mpremote connect COM3 exec "from umodbus.serial import ModbusRTU, Serial; print('umodbus OK')"
```

## 4. Cargar el firmware

MicroPython tiene un sistema de archivos plano y no busca módulos en
subcarpetas: `config.py`, `perifericos.py` y `main.py` deben quedar **todos en la
raíz** del ESP32.

### Esclavo 1 (jumper de GPIO13 abierto)

```bash
mpremote connect COM3 cp comun/config.py :config.py
mpremote connect COM3 cp comun/perifericos.py :perifericos.py
mpremote connect COM3 cp esclavo/main.py :main.py
mpremote connect COM3 reset
```

### Esclavo 2 (jumper de GPIO13 puenteado a GND)

Exactamente los mismos tres archivos, en la otra placa:

```bash
mpremote connect COM4 cp comun/config.py :config.py
mpremote connect COM4 cp comun/perifericos.py :perifericos.py
mpremote connect COM4 cp esclavo/main.py :main.py
mpremote connect COM4 reset
```

### Maestro

```bash
mpremote connect COM5 cp comun/config.py :config.py
mpremote connect COM5 cp comun/perifericos.py :perifericos.py
mpremote connect COM5 cp maestro/main.py :main.py
mpremote connect COM5 reset
```

### Verificación de la carga

```bash
mpremote connect COM3 ls
```

Debe listar: `boot.py`, `config.py`, `main.py`, `perifericos.py` y `umodbus/`.

## 5. Ver la salida de diagnóstico

```bash
mpremote connect COM3 repl
```

El nodo imprime su configuración al arrancar. Un esclavo sano muestra:

```
==========================================================
ESCLAVO MODBus RTU  |  Unit ID = 1
Bus: 9600 baudios, 8N1
UART2  TX=GPIO17  RX=GPIO16  DE/RE=GPIO4
Registros: DI 10001 | IR 30001 | Coil 00001 | HR 40001
==========================================================
```

**Comprobar que el Unit ID impreso coincide con el jumper** antes de conectar el
nodo al bus. Dos esclavos con el mismo ID responden a la vez y sus tramas
colisionan: el maestro recibe basura y el CRC falla siempre, con el síntoma
engañoso de "problema de cableado".

Salir del REPL: `Ctrl+]`. Interrumpir el programa sin desconectar: `Ctrl+C`.

## 6. Resolución de problemas

Diagnóstico ordenado: una hipótesis, un experimento, una variable por vez.
Antes de tocar el software, descartar la capa física con
[docs/PINOUT.md](../docs/PINOUT.md) §5.

| Síntoma | Causa más probable | Verificación |
|---|---|---|
| El ESP32 no arranca o reinicia en bucle | RO conectado directo al GPIO16 sin el divisor, o un periférico en un pin de strapping | Medir la tensión en GPIO16: debe ser ≈3,1 V, nunca 5 V |
| El esclavo nunca responde | Unit ID equivocado, baudrate distinto, o A/B invertidas | Comparar la cabecera impresa por cada nodo; probar intercambiando A y B |
| Bytes basura constantes en el bus | Falta la polarización de reposo | Medir V(A)−V(B) con todos los nodos callados: debe dar ≈210 mV |
| Responde a veces sí y a veces no | Falta terminación, o baudrate demasiado alto | Verificar los dos 120 Ω; comprobar que `BAUDRATE = 9600` |
| El maestro reporta timeouts periódicos | Período de sondeo demasiado corto | Subir `PERIODO_SONDEO_MS` a 300 y observar |
| Excepción 02 (ILLEGAL DATA ADDRESS) | Desfasaje off-by-one en la herramienta de PC | Modbus Poll: verificar si direcciona con base 0 o base 1 |
| El LED PWM titila con el potenciómetro quieto | Ruido del ADC | Subir `MUESTRAS_ADC` a 16 (debe ser potencia de 2) |
| `ImportError: no module named 'umodbus'` | La librería no se copió a esa placa | `mpremote connect COMx ls` |
| `ImportError: no module named 'config'` | Los módulos quedaron en una subcarpeta | Deben estar en la raíz, no en `/comun/` |

## 7. Herramienta de análisis de tramas

[herramientas/modbus_tramas.py](../herramientas/modbus_tramas.py) corre en la PC
(CPython, sin dependencias) y sirve para generar la evidencia del informe:

```bash
# Autoverificación del CRC + todas las tramas de ejemplo desglosadas
python herramientas/modbus_tramas.py

# Decodificar una trama capturada con el analizador lógico o Modbus Poll
python herramientas/modbus_tramas.py "01 04 00 00 00 01 31 CA"
```

Su salida está pensada para pegarse directamente en la sección "Análisis de
tramas" del informe técnico.
