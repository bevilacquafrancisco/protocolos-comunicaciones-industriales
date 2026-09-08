"""
prueba_perifericos.py
Autor: Francisco Bevilacqua
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Banco de pruebas del hardware local de un nodo, SIN involucrar el bus RS-485 ni
la libreria MODBus. Verifica de forma guiada el switch, el potenciometro, el LED
digital, el LED PWM y el jumper selector.

Corresponde al paso 4 del procedimiento de puesta en marcha documentado en
docs/arquitectura.md: "Probar los perifericos locales uno por vez, sin MODBus".

Por que existe este archivo
---------------------------
Es la aplicacion del principio de aislamiento de fallas: cuando un LED no
enciende, hay dos hipotesis posibles —el cableado esta mal, o el protocolo esta
mal— y no se pueden distinguir si se prueban juntas. Este script elimina por
completo la segunda hipotesis. Si las cuatro pruebas pasan, cualquier problema
posterior esta en el bus o en el firmware MODBus, no en el hardware del nodo.

Saltear este paso no ahorra tiempo: convierte un problema simple en varios
problemas superpuestos que hay que diagnosticar en simultaneo.

Uso desde Thonny
----------------
1. Cargar previamente config.py y perifericos.py en el dispositivo.
2. Abrir este archivo en Thonny (Archivo -> Abrir -> Este computador).
3. Pulsar F5.

No hace falta guardarlo en el ESP32: Thonny lo ejecuta desde la PC y no toca el
main.py que ya este cargado. Para interrumpir en cualquier momento, Ctrl+C.

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32.
- Modulos locales config.py y perifericos.py, en la raiz del dispositivo.
- NO requiere umodbus: es deliberado, para poder probar el hardware antes de
  haber instalado la libreria.
"""

import time

from machine import Pin

import config
from perifericos import (
    EntradaDigital,
    EntradaAnalogica,
    SalidaDigital,
    SalidaPWM,
    adc_a_pwm,
)


#: Duracion de cada prueba interactiva, en segundos. 10 s alcanza para accionar
#: el switch varias veces o recorrer el potenciometro de extremo a extremo sin
#: apurarse, y evita que el script quede esperando indefinidamente si el operador
#: se distrae.
DURACION_PRUEBA_S = 10

#: Periodo de refresco de las pruebas interactivas, en milisegundos. 200 ms da
#: una realimentacion que se percibe inmediata sin inundar el Shell de Thonny con
#: cientos de lineas por segundo.
REFRESCO_MS = 200


def titulo(texto):
    """
    Imprime un encabezado de seccion en el Shell.

    Parametros
    ----------
    texto : str
        Titulo de la prueba.

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna.
    """
    print()
    print("=" * 58)
    print(texto)
    print("=" * 58)


def prueba_led_digital():
    """
    Verifica la salida digital haciendo parpadear el LED cinco veces.

    Que valida
    ----------
    Que el GPIO configurado como salida gobierna efectivamente el LED: continuidad
    del cableado, polaridad correcta del LED (anodo al pin) y presencia de la
    resistencia serie.

    Que NO valida
    -------------
    El valor de la resistencia. Un LED con 100 ohm en vez de 330 tambien enciende,
    pero exige al GPIO mas corriente de la prevista. Eso se verifica midiendo.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True si el operador confirma que vio parpadear el LED.

    Excepciones
    -----------
    Ninguna.
    """
    titulo("PRUEBA 1 de 5 — LED DIGITAL (GPIO{})".format(config.PIN_LED_DIGITAL))
    print("En un esclavo, este LED corresponde al Coil 00001.")
    print("Debe parpadear 5 veces, a razon de una vez por segundo.")
    print()

    led = SalidaDigital(config.PIN_LED_DIGITAL)

    for i in range(1, 6):
        led.escribir(True)
        print("  {}. encendido".format(i))
        time.sleep_ms(500)
        led.escribir(False)
        time.sleep_ms(500)

    # Estado seguro al terminar: ningun actuador queda activo por accidente.
    led.escribir(False)
    print()

    # Se pide confirmacion en vez de asumir exito: un GPIO que conmuta sin
    # excepcion no prueba que el LED encienda. El circuito puede estar cortado
    # en cualquier punto (polaridad, resistencia, GND de retorno) y esta funcion
    # jamas se entera si nadie mira el LED y lo confirma.
    respuesta = input("  ¿Viste parpadear el LED 5 veces? (s/n): ")
    ok = respuesta.strip().lower().startswith("s")

    if not ok:
        print("  FALLA: revisar polaridad del LED, resistencia de 330 ohm,")
        print("  el cable al GPIO{}, y que su retorno llegue realmente".format(
            config.PIN_LED_DIGITAL))
        print("  al GND del ESP32 (no a un riel sin puentear).")
    return ok


def prueba_led_pwm():
    """
    Verifica la salida PWM con una rampa de intensidad ascendente y descendente.

    Que valida
    ----------
    Que el canal LEDC genera una portadora estable y que la conversion de rango
    (0-255 del registro MODBus a 0-65535 de duty_u16) es correcta en todo el
    recorrido, no solo en los extremos.

    Detalle a observar
    ------------------
    La transicion debe ser CONTINUA, sin titileo perceptible. Un titileo indicaria
    una frecuencia de portadora demasiado baja; config.PWM_FRECUENCIA_HZ es de
    1000 Hz, muy por encima del umbral de fusion de parpadeo del ojo (~60-90 Hz).

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True si el operador confirma que vio la rampa de brillo.

    Excepciones
    -----------
    Ninguna.
    """
    titulo("PRUEBA 2 de 5 — LED PWM (GPIO{})".format(config.PIN_LED_PWM))
    print("En un esclavo, este LED corresponde al Holding Register 40001.")
    print("Debe subir de apagado a maximo brillo y volver a bajar, de forma")
    print("continua y sin titilar.")
    print()

    led = SalidaPWM(config.PIN_LED_PWM)

    # Rampa ascendente y descendente en pasos de 5 sobre el rango 0-255 del
    # registro MODBus. Se recorre el rango del REGISTRO, no el interno de 16
    # bits, para probar exactamente la misma conversion que usara el firmware.
    for valor in list(range(0, config.PWM_MAXIMO + 1, 5)) + \
                 list(range(config.PWM_MAXIMO, -1, -5)):
        led.escribir(valor)
        time.sleep_ms(15)

    led.apagar()
    print("  Rampa completada (0 -> {} -> 0).".format(config.PWM_MAXIMO))
    print()

    respuesta = input("  ¿Viste subir y bajar el brillo, sin titileo? (s/n): ")
    ok = respuesta.strip().lower().startswith("s")

    if not ok:
        print("  FALLA: si no se movio nada, revisar polaridad, resistencia de")
        print("  330 ohm y el GND de retorno del GPIO{}.".format(config.PIN_LED_PWM))
        print("  Si titila: revisar config.PWM_FRECUENCIA_HZ.")
    return ok


def prueba_switch():
    """
    Verifica la entrada digital y el filtrado de rebotes.

    Que valida
    ----------
    Que el pull-up interno esta activo, que el contacto cierra a masa y que el
    antirrebote entrega un valor estable.

    Como se detecta un antirrebote insuficiente
    -------------------------------------------
    El contador de transiciones debe incrementarse UNA sola vez por cada
    accionamiento. Si sube de a dos o de a tres con una sola pulsacion, la
    ventana de config.ANTIRREBOTE_MS es demasiado corta para ese pulsador
    concreto y hay que ampliarla.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True si se detecto al menos una transicion.

    Excepciones
    -----------
    Ninguna.
    """
    titulo("PRUEBA 3 de 5 — SWITCH (GPIO{})".format(config.PIN_SWITCH))
    print("En un esclavo, corresponde al Discrete Input 10001.")
    print("Accionar el switch varias veces durante los proximos {} segundos.".format(
        DURACION_PRUEBA_S))
    print("El contador debe subir de a UNO por cada accionamiento.")
    print()

    switch = EntradaDigital(config.PIN_SWITCH)
    estado_previo = switch.leer()
    transiciones = 0

    fin = time.ticks_add(time.ticks_ms(), DURACION_PRUEBA_S * 1000)
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        estado = switch.leer()
        if estado != estado_previo:
            transiciones += 1
            print("  Transicion {}: {}".format(
                transiciones, "ACCIONADO" if estado else "suelto"))
            estado_previo = estado
        time.sleep_ms(10)

    print()
    print("  Transiciones detectadas: {}".format(transiciones))
    if transiciones == 0:
        print("  FALLA: no se detecto ninguna. Revisar que el contacto vaya a GND")
        print("  y que el cable llegue al GPIO{}.".format(config.PIN_SWITCH))
        return False
    print("  Si el contador subio de a 2 o 3 por pulsacion, ampliar")
    print("  config.ANTIRREBOTE_MS (valor actual: {} ms).".format(config.ANTIRREBOTE_MS))
    return True


def prueba_potenciometro():
    """
    Verifica la entrada analogica recorriendo el rango completo del ADC.

    Que valida
    ----------
    Que el potenciometro esta bien alimentado (extremos a 3,3 V y GND), que la
    atenuacion de 11 dB cubre el rango completo, y que el promediado entrega un
    valor estable.

    Por que se prueba en los EXTREMOS
    ---------------------------------
    Un valor plausible pero equivocado —por ejemplo, por endianness o por
    atenuacion mal configurada— es mucho mas dificil de detectar en el punto medio
    del recorrido que en los extremos, donde el error es evidente: si al girar a
    fondo el maximo se queda en ~1400 en vez de ~4095, la atenuacion esta mal.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True si el rango recorrido supera el 80 % del rango teorico del ADC.

    Excepciones
    -----------
    Ninguna.
    """
    titulo("PRUEBA 4 de 5 — POTENCIOMETRO (GPIO{})".format(config.PIN_POTENCIOMETRO))
    print("En un esclavo, corresponde al Input Register 30001.")
    print("Girar el potenciometro de un extremo al otro durante {} segundos.".format(
        DURACION_PRUEBA_S))
    print("Se muestra el valor crudo del ADC y su equivalente en PWM.")
    print()

    pote = EntradaAnalogica(config.PIN_POTENCIOMETRO)
    minimo = config.ADC_MAXIMO
    maximo = 0

    fin = time.ticks_add(time.ticks_ms(), DURACION_PRUEBA_S * 1000)
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        valor = pote.leer()
        if valor < minimo:
            minimo = valor
        if valor > maximo:
            maximo = valor

        # Barra de progreso de 40 caracteres: hace visible de un vistazo si el
        # recorrido es continuo o si tiene saltos o zonas muertas.
        barra = int(valor * 40 / config.ADC_MAXIMO)
        print("  ADC: {:5d}  PWM: {:3d}  [{}{}]".format(
            valor, adc_a_pwm(valor), "#" * barra, "." * (40 - barra)))
        time.sleep_ms(REFRESCO_MS)

    recorrido = maximo - minimo
    porcentaje = recorrido * 100 // config.ADC_MAXIMO

    print()
    print("  Minimo alcanzado: {}   Maximo alcanzado: {}".format(minimo, maximo))
    print("  Recorrido: {} de {} ({} % del rango)".format(
        recorrido, config.ADC_MAXIMO, porcentaje))

    if porcentaje < 80:
        print("  ATENCION: no se recorrio el rango completo. Puede ser que no se")
        print("  haya girado a fondo, o que la atenuacion del ADC este mal")
        print("  configurada (deberia ser ATTN_11DB para cubrir 0-3,3 V).")
        return False

    print("  OK: el ADC cubre el rango esperado.")
    return True


def prueba_selector():
    """
    Muestra el estado del jumper/switch selector y el Unit ID que implica.

    Que valida
    ----------
    Que el jumper de direccionamiento fisico funciona ANTES de cargar el firmware
    MODBus. Es la verificacion mas barata de todas y evita el error mas costoso de
    la Parte 3: dos esclavos con el mismo Unit ID responden a la vez, sus tramas
    colisionan, el CRC falla siempre y el sintoma aparenta ser un problema de
    cableado del bus.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    bool
        True siempre; es una prueba de observacion.

    Excepciones
    -----------
    Ninguna.
    """
    titulo("PRUEBA 5 de 5 — SELECTOR (GPIO{})".format(config.PIN_SELECTOR))
    print("En un ESCLAVO: jumper de Unit ID (abierto = ID 1, a GND = ID 2).")
    print("En el MAESTRO: selector de esclavo destino.")
    print("Cambiar la posicion durante los proximos {} segundos.".format(
        DURACION_PRUEBA_S))
    print()

    selector = Pin(config.PIN_SELECTOR, Pin.IN, Pin.PULL_UP)
    estado_previo = None

    fin = time.ticks_add(time.ticks_ms(), DURACION_PRUEBA_S * 1000)
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        estado = selector.value()
        if estado != estado_previo:
            unit_id = config.ID_ESCLAVO_1 if estado else config.ID_ESCLAVO_2
            print("  Pin en {} ({})  ->  Unit ID {}".format(
                estado, "abierto" if estado else "a GND", unit_id))
            estado_previo = estado
        time.sleep_ms(50)

    print()
    print("  Verificar que ambas posiciones se detecten.")
    print("  Si el pin queda siempre en 1, el jumper no hace contacto con GND.")
    return True


def main():
    """
    Ejecuta las cinco pruebas en secuencia y presenta un resumen.

    El orden no es arbitrario: primero las SALIDAS (LED digital y PWM), que no
    requieren intervencion del operador y confirman que la placa esta viva y bien
    cableada; despues las ENTRADAS, que si la requieren. Si una salida falla, no
    tiene sentido seguir probando entradas en esa placa.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    None

    Excepciones
    -----------
    Ninguna se propaga. Una interrupcion con Ctrl+C se atrapa e informa, para no
    ensuciar el Shell de Thonny con una traza de KeyboardInterrupt.
    """
    print()
    print("#" * 58)
    print("# BANCO DE PRUEBAS DE PERIFERICOS — Tarea N1 MODBus")
    print("# Verifica el hardware local SIN usar el bus RS-485")
    print("#" * 58)
    print()
    print("Pines configurados (de config.py):")
    print("  Switch          GPIO{}".format(config.PIN_SWITCH))
    print("  Potenciometro   GPIO{}".format(config.PIN_POTENCIOMETRO))
    print("  LED digital     GPIO{}".format(config.PIN_LED_DIGITAL))
    print("  LED PWM         GPIO{}".format(config.PIN_LED_PWM))
    print("  Selector        GPIO{}".format(config.PIN_SELECTOR))
    print()
    print("Interrumpir en cualquier momento con Ctrl+C.")

    pruebas = [
        ("LED digital", prueba_led_digital),
        ("LED PWM", prueba_led_pwm),
        ("Switch", prueba_switch),
        ("Potenciometro", prueba_potenciometro),
        ("Selector", prueba_selector),
    ]

    resultados = []
    try:
        for nombre, funcion in pruebas:
            resultados.append((nombre, funcion()))
    except KeyboardInterrupt:
        print()
        print("Pruebas interrumpidas por el operador.")
        return

    titulo("RESUMEN")
    todas_ok = True
    for nombre, ok in resultados:
        print("  [{}] {}".format("OK   " if ok else "FALLA", nombre))
        todas_ok = todas_ok and ok

    print()
    if todas_ok:
        print("Hardware local verificado. Se puede continuar con el paso 5 del")
        print("procedimiento (docs/arquitectura.md): armar el bus y medir la")
        print("polarizacion de reposo.")
    else:
        print("Hay pruebas fallidas. NO cargar el firmware MODBus todavia:")
        print("resolver el hardware primero, o los sintomas se van a superponer")
        print("y el diagnostico se vuelve mucho mas caro.")


if __name__ == "__main__":
    main()
