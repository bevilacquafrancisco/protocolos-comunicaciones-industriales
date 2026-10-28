# Firmware — Tarea Nº1 MODBus RTU

**Autores:** Bevilacqua Francisco, Peralta Agustina

Tres nodos ESP32 con **MicroPython**, programados desde el **IDE Thonny**, sobre
un bus RS-485 compartido.

| Carpeta | Se carga en | Rol |
|---|---|---|
| [comun/](comun/) | Los tres nodos | Configuración y capa de periféricos (HAL) |
| [esclavo/](esclavo/) | Esclavo 1 y Esclavo 2 | Servidor MODBus RTU |
| [maestro/](maestro/) | Maestro | Cliente MODBus RTU con máquina de estados |
| [prueba_perifericos.py](prueba_perifericos.py) | Cualquier nodo, temporalmente | Banco de pruebas de hardware (Fase 1, sin MODBus) |

**El mismo archivo `esclavo/main.py` corre en ambos esclavos.** El Unit ID lo
determina el jumper de GPIO13 en el arranque: abierto = ID 1, puenteado a GND =
ID 2. Ver el porqué en [docs/arquitectura.md §8.2](../docs/arquitectura.md#82-esclavo-1-y-esclavo-2--firmware-idéntico).

> ⚠️ **Antes de conectar cualquier ESP32 al MAX485, leer
> [docs/arquitectura.md §4](../docs/arquitectura.md#4-adaptación-de-niveles-lógicos-5-v--33-v).**
> El pin RO entrega ≈5 V y el GPIO del ESP32 admite 3,6 V como máximo absoluto:
> sin el divisor resistivo 2,2 kΩ / 3,3 kΩ se daña la placa.

---

## Índice

1. [Instalar Thonny](#1-instalar-thonny)
2. [Grabar MicroPython en el ESP32](#2-grabar-micropython-en-el-esp32)
3. [Instalar la librería umodbus](#3-instalar-la-librería-umodbus)
4. [Cargar el firmware en cada nodo](#4-cargar-el-firmware-en-cada-nodo)
5. [Ejecutar y ver la salida](#5-ejecutar-y-ver-la-salida)
6. [Trabajar con tres ESP32 a la vez](#6-trabajar-con-tres-esp32-a-la-vez)
7. [Probar el hardware antes de MODBus](#7-probar-el-hardware-antes-de-modbus)
8. [Resolución de problemas](#8-resolución-de-problemas)
9. [Herramienta de análisis de tramas](#9-herramienta-de-análisis-de-tramas)

---

## 1. Instalar Thonny

Thonny es un IDE de Python pensado para principiantes, **libre y gratuito**
(licencia MIT), que trae soporte nativo para MicroPython: graba el firmware,
instala librerías, sube archivos y da acceso al REPL sin necesidad de ninguna
herramienta de línea de comandos.

1. Descargar de **[thonny.org](https://thonny.org)** e instalar (Windows, macOS o Linux).
2. Al abrirlo por primera vez, elegir el modo **Estándar** (*Standard*).
3. En Windows, si el ESP32 no aparece como puerto COM, instalar el driver del
   conversor USB-serie de la placa: **CP210x** (Silicon Labs) o **CH340**
   (WCH), según el chip que traiga el DevKit. Se identifica mirando el
   Administrador de dispositivos con la placa conectada.

**Verificación:** con el ESP32 conectado por USB, el Administrador de
dispositivos de Windows debe mostrarlo en *Puertos (COM y LPT)* como `COM3`,
`COM4`, etc.

## 2. Grabar MicroPython en el ESP32

Una sola vez por placa. Thonny incluye el instalador, así que **no hace falta
`esptool` ni ninguna descarga manual del firmware**.

1. Conectar **una sola** placa por USB.
2. Menú **Herramientas → Opciones… → Intérprete** (*Tools → Options… → Interpreter*).
3. En el desplegable superior elegir **MicroPython (ESP32)**.
4. En *Puerto*, seleccionar el COM correspondiente.
5. Abajo a la derecha, hacer clic en **"Instalar o actualizar MicroPython"**
   (*Install or update MicroPython*).
6. En el diálogo que se abre:
   - **Puerto:** el COM de la placa
   - **Familia:** `ESP32`
   - **Variante:** `Espressif ESP32 / WROOM`
   - **Versión:** la estable más reciente (≥ 1.19; probado con 1.23)
7. Pulsar **Instalar** y esperar a que termine la barra de progreso.

> **Si la instalación falla o se queda esperando:** algunas placas necesitan que
> se mantenga presionado el botón **BOOT** durante los primeros segundos del
> grabado, hasta que la barra empiece a avanzar.

**Verificación:** aceptar el diálogo y mirar el panel **Shell** abajo. Debe
aparecer el prompt de MicroPython:

```
MicroPython v1.23.0 on 2024-06-02; Generic ESP32 module with ESP32
Type "help()" for more information.
>>>
```

Escribir `print("hola")` y pulsar Enter: si responde `hola`, la placa está lista.

## 3. Instalar la librería umodbus

El proyecto usa **micropython-modbus** (de brainelectronics), que aporta el
paquete `umodbus` con el servidor y el cliente MODBus RTU. No viene con
MicroPython: hay que instalarla en **cada una de las tres placas**.

### 3.1 Vía recomendada: gestor de paquetes de Thonny

1. Conectarse a la placa (el Shell debe mostrar el prompt `>>>`).
2. Menú **Herramientas → Administrar paquetes…** (*Tools → Manage packages…*).
3. Comprobar que la ventana dice que instalará **en el dispositivo MicroPython**,
   no en la PC.
4. Buscar `micropython-modbus`.
5. Pulsar **Instalar**.

Thonny descarga el paquete desde PyPI a la PC y lo sube al directorio `/lib` del
ESP32. MicroPython incluye `/lib` en su ruta de búsqueda de módulos, por lo que
`from umodbus.serial import ModbusRTU` funciona sin configurar nada más.

### 3.2 Vía alternativa: subir la carpeta a mano

Útil si el gestor de paquetes falla o si no hay Internet en el momento de cargar
las placas. Tiene una ventaja adicional: deja una copia del código fuente en la
PC, que es lo que permite citar en el informe los parámetros exactos de cada
función — requisito explícito de la consigna ("en el caso de emplear librerías,
especificar qué parámetros requiere la configuración, qué funciones se emplean y
qué parámetros con tipo requieren").

1. Descargar el repositorio de
   `https://github.com/brainelectronics/micropython-modbus`
   (botón **Code → Download ZIP**) y descomprimirlo.
2. En Thonny, menú **Ver → Archivos** (*View → Files*) para abrir el panel de
   archivos. Muestra dos mitades: **Este computador** arriba y **Dispositivo
   MicroPython** abajo.
3. En la mitad superior, navegar hasta la carpeta descomprimida y ubicar la
   carpeta **`umodbus`**.
4. Clic derecho sobre `umodbus` → **Subir a /** (*Upload to /*).

### 3.3 Verificación

En el Shell de Thonny:

```python
>>> from umodbus.serial import ModbusRTU, Serial
>>> print("umodbus OK")
umodbus OK
```

Si aparece `ImportError: no module named 'umodbus'`, la librería no quedó
instalada **en esa placa**. Es un error frecuente: hay que repetir la instalación
en las tres.

## 4. Cargar el firmware en cada nodo

MicroPython tiene un **sistema de archivos plano** y no busca módulos en
subcarpetas. Los tres archivos —`config.py`, `perifericos.py` y `main.py`— deben
quedar **en la raíz** del dispositivo, no dentro de una carpeta.

El archivo llamado **`main.py` se ejecuta automáticamente** cada vez que la placa
arranca o se resetea. Por eso el firmware de cada nodo se guarda con ese nombre.

### 4.1 Procedimiento en Thonny

Para **cada uno de los tres archivos**:

1. **Archivo → Abrir…** (*File → Open…*) y elegir **Este computador**.
2. Abrir el archivo desde la carpeta del repositorio.
3. **Archivo → Guardar como…** (*File → Save as…*) y elegir
   **Dispositivo MicroPython** (*MicroPython device*).
4. Escribir el nombre de destino **sin ninguna ruta de carpeta** y aceptar.

> **Alternativa más rápida:** con el panel **Ver → Archivos** abierto, navegar en
> la mitad superior hasta la carpeta del archivo, hacer clic derecho sobre él y
> elegir **Subir a /** (*Upload to /*). Para `main.py` hay que renombrarlo
> después en el dispositivo (clic derecho → Renombrar), porque los tres se llaman
> igual en el repositorio.

### 4.2 Qué archivo va en cada nodo

| Nodo | Archivo de origen | Nombre en el dispositivo |
|---|---|---|
| **Los tres** | `firmware/comun/config.py` | `config.py` |
| **Los tres** | `firmware/comun/perifericos.py` | `perifericos.py` |
| Esclavo 1 *(jumper GPIO13 abierto)* | `firmware/esclavo/main.py` | `main.py` |
| Esclavo 2 *(jumper GPIO13 a GND)* | `firmware/esclavo/main.py` | `main.py` |
| Maestro | `firmware/maestro/main.py` | `main.py` |

Los dos esclavos reciben **exactamente el mismo archivo**. Lo que los diferencia
es el jumper de hardware, no el software.

### 4.3 Verificación de la carga

En el panel **Ver → Archivos**, la mitad inferior (*Dispositivo MicroPython*)
debe listar:

```
boot.py
config.py
lib/            ← si se instaló umodbus con el gestor de paquetes
main.py
perifericos.py
umodbus/        ← si se subió la carpeta a mano
```

## 5. Ejecutar y ver la salida

### 5.1 Ejecución

| Acción | Cómo |
|---|---|
| Ejecutar el archivo abierto | **F5** o el botón ▶ verde |
| Detener el programa | **Ctrl+C** en el Shell |
| Reiniciar la placa (arranca `main.py`) | **Ctrl+F2**, o *Ejecutar → Reiniciar el intérprete* |
| Salir del programa en marcha para recuperar el prompt | **Ctrl+C**, luego Enter |

### 5.2 Salida esperada

Cada nodo imprime su configuración al arrancar. Un esclavo sano muestra en el
Shell:

```
==========================================================
ESCLAVO MODBus RTU  |  Unit ID = 1
Bus: 9600 baudios, 8N1
UART2  TX=GPIO17  RX=GPIO16  DE/RE=GPIO4
Registros: DI 10001 | IR 30001 | Coil 00001 | HR 40001
==========================================================
```

> **Comprobar que el Unit ID impreso coincide con el jumper** antes de conectar
> el nodo al bus. Dos esclavos con el mismo ID responden a la vez, sus tramas
> colisionan y el maestro recibe basura que falla el CRC siempre — con el síntoma
> engañoso de "problema de cableado".

El maestro imprime además el período de sondeo y la convención del selector, y
reporta cada fallo de transacción con la función que falló y el contador de
fallos consecutivos.

## 6. Trabajar con tres ESP32 a la vez

**Una ventana de Thonny ocupa un puerto serie en exclusiva.** Es la fricción
principal de este proyecto, que tiene tres placas.

| Necesidad | Cómo resolverlo |
|---|---|
| Cargar las placas de a una | Cambiar el puerto en *Herramientas → Opciones → Intérprete* antes de conectar la siguiente |
| Ver la salida de dos nodos en simultáneo | Abrir **una segunda instancia de Thonny** y configurar cada una en un puerto distinto |
| Que un nodo corra sin PC | No hace falta Thonny: con `main.py` cargado, la placa arranca sola al alimentarla por USB o por VIN |

**Recomendación práctica para el banco:** anotar con una etiqueta física en cada
placa qué rol tiene y en qué COM aparece. Con tres ESP32 idénticos conectados es
facilísimo cargar el firmware del maestro en un esclavo, y el error tarda en
notarse porque el nodo arranca igual.

Los números de COM **pueden cambiar** al reconectar las placas en distinto orden
o en otro puerto USB: conviene verificar el rol en el mensaje de arranque del
Shell, que es la fuente de verdad, y no en el número de puerto.

## 7. Probar el hardware antes de MODBus

[prueba_perifericos.py](prueba_perifericos.py) verifica switch, potenciómetro,
LED digital y LED PWM **sin involucrar el bus ni la librería MODBus**.
Corresponde al paso 4 del procedimiento de puesta en marcha
([docs/arquitectura.md §10](../docs/arquitectura.md#10-procedimiento-de-puesta-en-marcha)).

Su valor está en el aislamiento: si un LED no enciende, hay que saber si el
problema es el cableado o el protocolo, y esas dos hipótesis se separan
probándolas por separado.

**Cómo usarlo:** abrirlo en Thonny y pulsar **F5**. Se ejecuta desde la PC sin
necesidad de guardarlo en el dispositivo, y sin tocar el `main.py` que ya esté
cargado. Necesita que `config.py` y `perifericos.py` ya estén en la placa.

El script recorre las pruebas de forma guiada e imprime los resultados en el
Shell. Solo cuando las cuatro pasan tiene sentido cargar el firmware MODBus.

## 8. Resolución de problemas

Diagnóstico ordenado: **una hipótesis, un experimento, una variable por vez.**
Antes de tocar el software, descartar la capa física con
[docs/arquitectura.md §10](../docs/arquitectura.md#10-procedimiento-de-puesta-en-marcha).

### 8.1 Problemas de Thonny y del entorno

| Síntoma | Causa más probable | Solución |
|---|---|---|
| El puerto COM no aparece en Thonny | Falta el driver CP210x o CH340 | Instalar el driver del chip USB-serie de la placa |
| `Could not open port COM3: Access denied` | Otro programa ocupa el puerto | Cerrar la otra instancia de Thonny, o Modbus Poll si está abierto sobre ese puerto |
| El Shell no responde y no aparece `>>>` | `main.py` está corriendo su lazo infinito | **Ctrl+C** para interrumpir, luego Enter |
| No se puede guardar un archivo en el dispositivo | El programa está en ejecución | **Ctrl+C** primero, después guardar |
| `ImportError: no module named 'umodbus'` | La librería no se instaló en **esa** placa | Repetir el paso 3 en esa placa |
| `ImportError: no module named 'config'` | Los archivos quedaron dentro de una carpeta | Deben estar en la raíz `/`, no en `/comun/` |
| Al reiniciar no arranca nada | El firmware se guardó con otro nombre | Debe llamarse exactamente `main.py` |

### 8.2 Problemas de hardware y de bus

| Síntoma | Causa más probable | Verificación |
|---|---|---|
| El ESP32 no arranca o reinicia en bucle | RO conectado directo al GPIO16 **sin el divisor**, o un periférico en un pin de *strapping* | Medir la tensión en GPIO16: debe ser ≈3,1 V, **nunca 5 V** |
| El esclavo nunca responde | Unit ID equivocado, baudrate distinto, o líneas A/B invertidas | Comparar la cabecera que imprime cada nodo; probar intercambiando A y B |
| Bytes basura constantes en el bus | Falta la polarización de reposo | Medir V(A)−V(B) con todos los nodos callados: debe dar ≈211 mV |
| Responde a veces sí y a veces no | Falta terminación, o baudrate demasiado alto | Verificar los dos 120 Ω en los extremos; comprobar `BAUDRATE = 9600` |
| El maestro reporta timeouts periódicos | Período de sondeo demasiado corto | Subir `PERIODO_SONDEO_MS` a 300 y observar |
| Excepción 02 (ILLEGAL DATA ADDRESS) | Desfasaje off-by-one en la herramienta de PC | En Modbus Poll, verificar si direcciona con base 0 o base 1 |
| El LED PWM titila con el potenciómetro quieto | Ruido del ADC | Subir `MUESTRAS_ADC` a 16 (debe ser potencia de 2) |
| Modbus Poll da errores intermitentes | Latencia del buffer del conversor USB-RS485 | Administrador de dispositivos → propiedades del puerto COM → *Latency Timer* a 1 ms |

## 9. Herramienta de análisis de tramas

[herramientas/modbus_tramas.py](../herramientas/modbus_tramas.py) corre en la
**PC con Python 3 estándar** (no en el ESP32) y no tiene dependencias. Genera la
evidencia para la sección de análisis de tramas del informe.

**Desde Thonny:** cambiar el intérprete a *Python local* en
*Herramientas → Opciones → Intérprete*, abrir el archivo y pulsar **F5**.

**Desde una terminal:**

```bash
# Autoverificación del CRC + todas las tramas de ejemplo desglosadas
python herramientas/modbus_tramas.py

# Decodificar una trama capturada con el analizador lógico o Modbus Poll
python herramientas/modbus_tramas.py "01 04 00 00 00 01 31 CA"
```

Fundamento teórico del CRC y de las tramas en
[docs/protocolo-comunicacion.md](../docs/protocolo-comunicacion.md).
