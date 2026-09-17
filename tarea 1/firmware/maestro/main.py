"""
main.py  (MAESTRO MODBus RTU)
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-09-01
Version: 1.0

Descripcion general
-------------------
Firmware del dispositivo Maestro MODBus RTU sobre RS-485 (Partes 2 y 3 de la
Tarea Nº1). Es el unico nodo que inicia transacciones en el bus: sondea
periodicamente al esclavo seleccionado, replica en sus salidas locales las
entradas remotas, y escribe en las salidas remotas sus propias entradas locales.

La logica esta implementada como una MAQUINA DE ESTADOS FINITOS explicita y no
como una secuencia de banderas booleanas. Los motivos son concretos:

  1. Se corresponde uno a uno con el diagrama de flujo que exige la consigna, lo
     que hace verificable la trazabilidad entre codigo y documentacion.
  2. Cada estado ejecuta UNA sola transaccion MODBus, por lo que el lazo nunca
     queda bloqueado mas de un timeout: el maestro sigue atendiendo el switch
     selector aunque un esclavo este caido.
  3. Agregar un tercer esclavo o una transaccion nueva es agregar un estado, sin
     tocar los existentes (principio abierto/cerrado).

Ciclo de sondeo (Parte 3 completa)
----------------------------------
    LEER_SELECTOR -> INDICAR_SELECCION -> LEER_DI_REMOTO -> LEER_IR_REMOTO
        -> ESCRIBIR_COIL_REMOTO -> ESCRIBIR_HREG_REMOTO -> ESPERA -> (vuelve)

Correspondencia con el diagrama de flujo (diagramas/flujo_maestro.md)
----------------------------------------------------------------------
  Bloque M1  INICIO / CONFIGURACION        -> configurar_perifericos(), configurar_maestro_modbus()
  Bloque M2  LEER SWITCH SELECTOR          -> estado LEER_SELECTOR
  Bloque M3  ENCENDER LED INDICADOR        -> estado INDICAR_SELECCION
  Bloque M4  LEER ENTRADA DIGITAL REMOTA   -> estado LEER_DI_REMOTO      (funcion 0x02)
  Bloque M5  LEER ENTRADA ANALOGICA REMOTA -> estado LEER_IR_REMOTO      (funcion 0x04)
  Bloque M6  ESCRIBIR SALIDA DIGITAL       -> estado ESCRIBIR_COIL_REMOTO(funcion 0x05)
  Bloque M7  ESCRIBIR SALIDA PWM           -> estado ESCRIBIR_HREG_REMOTO(funcion 0x06)
  Bloque M8  ESPERAR FIN DE PERIODO        -> estado ESPERA
  Bloque M9  MANEJO DE TIMEOUT             -> funcion registrar_fallo()

Dependencias externas
---------------------
- MicroPython >= 1.19 para ESP32.
- micropython-modbus (brainelectronics), paquete `umodbus`.
- Modulos locales: config.py y perifericos.py en la raiz del ESP32.
"""

import time

from machine import Pin
from umodbus.serial import Serial as ModbusRTUMaster

import config
import diagnostico
from diagnostico import (
    DetectorDeCambio,
    EntradaConfirmada,
    EstadisticaEsclavo,
    Registrador,
    clasificar_error,
    describir_trama,
)
from perifericos import (
    EntradaDigital,
    EntradaAnalogica,
    SalidaDigital,
    SalidaPWM,
    adc_a_pwm,
)


# =============================================================================
# Definicion de los estados de la maquina de estados
# =============================================================================
# Se usan constantes enteras y no cadenas: la comparacion es mas rapida y no
# genera basura en el heap, algo que importa en un lazo que corre miles de veces
# por minuto en un interprete con recoleccion de basura.

ESTADO_LEER_SELECTOR = 0
ESTADO_INDICAR_SELECCION = 1
ESTADO_LEER_DI_REMOTO = 2
ESTADO_LEER_IR_REMOTO = 3
ESTADO_ESCRIBIR_COIL_REMOTO = 4
ESTADO_ESCRIBIR_HREG_REMOTO = 5
ESTADO_ESPERA = 6

#: Nombres legibles de los estados, solo para los mensajes de diagnostico.
NOMBRES_ESTADO = {
    ESTADO_LEER_SELECTOR: "LEER_SELECTOR",
    ESTADO_INDICAR_SELECCION: "INDICAR_SELECCION",
    ESTADO_LEER_DI_REMOTO: "LEER_DI_REMOTO",
    ESTADO_LEER_IR_REMOTO: "LEER_IR_REMOTO",
    ESTADO_ESCRIBIR_COIL_REMOTO: "ESCRIBIR_COIL_REMOTO",
    ESTADO_ESCRIBIR_HREG_REMOTO: "ESCRIBIR_HREG_REMOTO",
    ESTADO_ESPERA: "ESPERA",
}

# Nota de evolucion: hasta la Parte 2 el reporte se emitia cada N ciclos y la
# degradacion se decidia contando ciclos consecutivos con fallo. Ambos criterios
# se reemplazaron por criterios TEMPORALES (config.PERIODO_RESUMEN_MS y
# config.MS_PARA_DECLARAR_AUSENTE) al incorporar el tercer nodo, porque con
# reintentos la duracion del ciclo dejo de ser constante y, sobre todo, porque
# contar fallos aislados hacia parpadear los LED replicadores. El detalle esta
# en _registrar_fallo().

#: Registrador del nodo. Se construye a nivel de modulo, antes que cualquier
#: objeto, para que la subclase del transceptor pueda volcar tramas sin recibir
#: una referencia por constructor (la libreria instancia la clase base y no
#: admite argumentos extra).
LOG = Registrador("MAESTRO")

#: Instancia del maestro, publicada por main() para inspeccion desde el REPL.
MAESTRO = None


class MaestroRTUConTimeout(ModbusRTUMaster):
    """
    Interfaz MODBus RTU maestra con el timeout de respuesta adaptado a un esclavo
    que corre MicroPython.

    Responsabilidad dentro del sistema
    ----------------------------------
    Es la unica adaptacion que este proyecto le hace a la libreria umodbus.
    Reemplaza el timeout de recepcion por defecto, que es inservible cuando el
    esclavo tambien es un ESP32 con MicroPython.

    El problema que resuelve
    ------------------------
    umodbus calcula su timeout por defecto como el doble del silencio entre
    tramas:

        t1char             = 1000000 x (8 datos + 1 parada + 2) / 9600 = 1145 us
        inter_frame_delay  = t1char x 3,5                              = 4007 us
        timeout por defecto = 2 x inter_frame_delay                    = 8014 us

    **8 ms.** Ese valor asume un esclavo que responde en hardware, casi
    instantaneamente. Un esclavo MicroPython no puede hacerlo, y no por ser
    lento: es fisicamente imposible por el propio protocolo.

        Deteccion del fin de la peticion (t3,5, obligatorio)     4007 us
        Procesamiento en el interprete (optimista)              ~1000 us
        Activacion de DE en el transceptor                        200 us
        Transmision de la respuesta (6 bytes x t1char)           6870 us
                                                              -----------
        Minimo teorico absoluto                                12077 us

    **12,1 ms de piso contra un presupuesto de 8,0 ms.** Ni siquiera con tiempo
    de procesamiento cero entraria: solo transmitir la respuesta ya consume
    6,87 ms, y antes hay que esperar los 4 ms de silencio que la especificacion
    exige para dar la peticion por terminada. El maestro abandonaba mientras el
    esclavo todavia estaba por empezar a contestar.

    Por que no se toca `_inter_frame_delay` en su lugar
    ---------------------------------------------------
    Seria la otra forma de subir el timeout, pero ese atributo cumple DOS
    funciones: fija el timeout (x2) y define cuanto silencio hay que ver para dar
    por completa una trama recibida. Inflarlo a 150 ms daria el timeout deseado,
    pero agregaria 150 ms a CADA transaccion: el ciclo de cuatro pasaria de
    ~102 ms a mas de 600 ms y reventaria el periodo de sondeo de 200 ms.

    Sobrescribir solo el timeout mantiene la delimitacion de tramas en los
    4007 us que manda la especificacion —o sea, el ciclo sigue costando lo
    calculado— y desacopla la unica variable que habia que mover.

    Trade-off asumido
    -----------------
    Se sobrescribe un metodo interno de una libreria de terceros (el guion bajo
    indica que no es API publica), lo que ata este codigo a esa implementacion.
    Se acepta porque la alternativa —inflar `_inter_frame_delay`— tambien toca un
    atributo privado Y ademas rompe el presupuesto temporal del ciclo. Entre dos
    intervenciones igual de invasivas, se elige la que no degrada el diseno.

    Si una version futura de umodbus renombrara este metodo, el sintoma volveria
    a ser el mismo timeout permanente, y este docstring es el mapa para
    encontrarlo.

    Segundo problema resuelto: glitch de conmutacion DE/RE
    --------------------------------------------------------
    Con el timeout ya corregido aparecio un sintoma distinto: el maestro fallaba
    el 100% de las lecturas con "invalid response CRC", mientras un analizador
    pasivo (herramientas/sniffer_rs485.py) escuchando el MISMO bus al mismo
    tiempo capturaba las tramas del esclavo perfectamente formadas. Que un
    observador ajeno vea el bus limpio mientras el propio maestro lo ve corrupto
    descarta el cableado y el esclavo: el problema tiene que estar en algo que
    le pasa solo al maestro, en el instante en que deja de transmitir.

    La causa esta en como `_uart_read_frame()` decide cuando empezo a llegar una
    respuesta: hace polling de `uart.any()` durante el `timeout` configurado, y
    apenas ve UN byte disponible pasa de inmediato al modo "esperar silencio de
    inter_frame_delay (4007 us) para dar la trama por completa" — sin distinguir
    si ese primer byte es una respuesta real o ruido.

    Ahi esta el problema: justo cuando el maestro apaga DE/RE para volver a modo
    recepcion, el transceptor puede inyectar un byte espurio en el UART — ya sea
    ruido de conmutacion del propio MAX485, o la cola de su propia transmision
    si el timing de flush no fue exacto. Ese byte espurio hace que `uart.any()`
    se satisfaga de inmediato, y el lector pasa a esperar 4007 us de silencio.
    Como el esclavo recien puede empezar a responder ~12 ms despues (ver arriba:
    tiene que completar su propia deteccion de t3,5 mas el procesamiento), el
    bus queda en silencio mucho mas de 4007 us despues de ese byte espurio, y el
    lector concluye "trama completa" usando solo el byte de ruido — muchisimo
    antes de que la respuesta real del esclavo siquiera empiece a transmitirse.
    El CRC de esa "trama" de un byte falla siempre, en el 100% de los ciclos, y
    la respuesta real del esclavo llega despues sin que nadie la escuche.

    Por que el sniffer no ve este problema: nunca transmite ni conmuta su propio
    transceptor, asi que no genera (ni sufre) este glitch. Escucha el bus de
    forma continua y ve la trama real completa, sin la ventana de confusion que
    solo afecta al nodo que acaba de transmitir.

    La correccion: antes de delegar a la logica original, se espera un margen
    fijo y se DRENA cualquier byte que haya llegado durante ese margen. Ningun
    byte que llegue en esa ventana puede ser una respuesta legitima, porque el
    esclavo esta fisicamente obligado a tardar al menos ~4 ms en darse cuenta de
    que la peticion termino antes de siquiera empezar a procesarla. Descartar
    con margen de sobra dentro de esa ventana elimina el glitch sin arriesgar
    ni un byte de la respuesta real.

    Relaciones con otras clases
    ---------------------------
    Hereda de umodbus.serial.Serial. La consume configurar_maestro_modbus().
    """

    #: Margen de espera-y-descarte tras cada transmision, en microsegundos,
    #: antes de empezar a escuchar "en serio". Cualquier byte que llegue dentro
    #: de esta ventana es necesariamente ruido de conmutacion o cola de la
    #: propia transmision, nunca la respuesta real del esclavo: el esclavo
    #: recien puede empezar a responder despues de completar su propia
    #: deteccion de fin de trama (t3,5 = 4007 us a 9600 baudios). Se elige un
    #: valor bien por debajo de eso (2000 us, la mitad) para no arriesgar
    #: ningun byte legitimo aunque el timing real tenga variacion, y muy por
    #: encima de cualquier transitorio de conmutacion del MAX485 (tZH/tZL del
    #: datasheet: 40-70 ns tipico/maximo, tres ordenes de magnitud menor).
    _VENTANA_DESCARTE_GLITCH_US = 2000

    def _uart_read_frame(self, timeout=None):
        """
        Lee una trama del UART aplicando un piso de timeout y descartando el
        glitch de conmutacion DE/RE antes de empezar a interpretar la respuesta.

        Se impone un PISO de timeout en lugar de reemplazar el valor: si una
        version de la libreria pasara un timeout explicito mayor al
        configurado, se respeta ese valor mayor. Solo se corrigen los timeouts
        demasiado cortos, que son el problema real.

        Parametros
        ----------
        timeout : int, opcional
            Tiempo maximo de espera en MICROsegundos que pasa la libreria. Si es
            None o menor que config.TIMEOUT_RESPUESTA_MS, se eleva a ese valor.

        Retorna
        -------
        bytearray
            La trama recibida, o vacia si vencio el tiempo de espera.

        Excepciones
        -----------
        Las que propague la implementacion de la clase base.
        """
        # config.TIMEOUT_RESPUESTA_MS esta en milisegundos y la libreria trabaja
        # en microsegundos: de ahi el factor 1000.
        timeout_minimo_us = config.TIMEOUT_RESPUESTA_MS * 1000

        if timeout is None or timeout < timeout_minimo_us:
            timeout = timeout_minimo_us

        # Espera fija y descarte de lo acumulado: ver "Segundo problema
        # resuelto" en el docstring de la clase. Ningun byte legitimo del
        # esclavo puede llegar dentro de esta ventana.
        time.sleep_us(self._VENTANA_DESCARTE_GLITCH_US)
        descartado = self._uart.read()

        # Lo descartado no es basura sin valor: si aqui aparecen bytes de forma
        # sistematica, el bus esta entregando algo fuera de la ventana de
        # respuesta (eco de la propia transmision, un nodo que habla sin que se
        # lo interrogue, o ruido de linea). Se registra en nivel TRAMA porque es
        # exactamente el dato que distingue esas tres causas.
        if descartado and LOG.habilitado(diagnostico.TRAMA):
            LOG.trama("RX descartado en la ventana de guarda", descartado)

        trama = super()._uart_read_frame(timeout)

        if LOG.habilitado(diagnostico.TRAMA):
            LOG.trama("RX", trama)
            if trama:
                LOG.detalle("RX  {}".format(describir_trama(trama)))

        return trama


class MaestroModbus:
    """
    Maestro MODBus RTU con seleccion dinamica de esclavo.

    Responsabilidad dentro del sistema
    ----------------------------------
    Ser el unico iniciador de transacciones del bus. Ejecuta ciclicamente cuatro
    transacciones contra el esclavo activo (dos lecturas y dos escrituras),
    gobierna los LED indicadores de seleccion y maneja los timeouts sin bloquear.

    Atributos principales
    ---------------------
    _bus : umodbus.serial.Serial
        Interfaz MODBus RTU sobre el UART2.
    _perifericos : dict
        Perifericos locales (switch, potenciometro, LED replicadores e indicadores).
    _estado : int
        Estado actual de la maquina de estados.
    _id_activo : int
        Unit ID del esclavo con el que se esta interactuando en este ciclo.
    _di_remoto : bool
        Ultimo valor leido del Discrete Input del esclavo (switch remoto).
    _ir_remoto : int
        Ultimo valor leido del Input Register del esclavo (ADC remoto).
    _fallos_consecutivos : int
        Contador de ciclos seguidos en los que alguna transaccion fallo.
    _instante_fin_espera : int
        Marca de tiempo (ticks_ms) en que termina el estado ESPERA.

    Relaciones con otras clases
    ---------------------------
    Depende de la capa de perifericos (composicion) y de la interfaz MODBus de
    umodbus. No conoce detalles de machine.Pin ni de la trama MODBus.
    """

    def __init__(self, bus, perifericos):
        """
        Inicializa la maquina de estados en un estado de arranque conocido.

        Parametros
        ----------
        bus : umodbus.serial.Serial
            Interfaz MODBus RTU ya configurada.
        perifericos : dict
            Diccionario devuelto por configurar_perifericos().

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._bus = bus
        self._perifericos = perifericos

        self._estado = ESTADO_LEER_SELECTOR
        self._id_activo = config.ID_ESCLAVO_1

        self._di_remoto = False
        self._ir_remoto = 0

        self._fallos_consecutivos = 0
        self._instante_fin_espera = time.ticks_ms()

        # --- Diagnostico y robustez (Parte 3) -------------------------------
        #: Registrador compartido con la subclase del transceptor.
        self._log = LOG

        #: Estadistica desglosada por Unit ID. Es lo que permite separar un
        #: problema del bus (fallan los dos esclavos por igual) de un problema
        #: de un nodo (falla uno solo).
        self._estadistica = {
            config.ID_ESCLAVO_1: EstadisticaEsclavo(),
            config.ID_ESCLAVO_2: EstadisticaEsclavo(),
        }

        #: Instante de la ultima transaccion exitosa contra CADA esclavo. La
        #: degradacion se decide sobre este valor y no sobre un contador de
        #: ciclos: lo que define a un esclavo ausente es el tiempo que lleva sin
        #: contestar, no cuantos intentos aislados fallaron.
        self._ultimo_exito_ms = {
            config.ID_ESCLAVO_1: time.ticks_ms(),
            config.ID_ESCLAVO_2: time.ticks_ms(),
        }

        #: Instante del ultimo INTENTO de sondeo contra cada esclavo, exitoso o
        #: no. Es distinto del anterior y hace falta para poder decir hace cuanto
        #: que un esclavo no se sondea: sin este dato, un nodo simplemente no
        #: seleccionado y un nodo caido producen exactamente la misma linea de
        #: log, que es la ambiguedad que este reporte viene a eliminar.
        self._ultimo_sondeo_ms = {
            config.ID_ESCLAVO_1: time.ticks_ms(),
            config.ID_ESCLAVO_2: time.ticks_ms(),
        }

        #: Bandera de esclavo declarado ausente, para emitir el aviso una sola
        #: vez al entrar y otra al salir, en lugar de una linea por ciclo.
        self._ausente = False

        #: Ultimo valor PWM efectivamente escrito en cada esclavo, para aplicar
        #: la zona muerta y no consumir una transaccion en reescribir lo mismo.
        self._pwm_escrito = {
            config.ID_ESCLAVO_1: None,
            config.ID_ESCLAVO_2: None,
        }

        #: Detectores de cambio. Convierten un valor muestreado continuamente en
        #: una secuencia de eventos con instante, que es la unica forma de dejar
        #: registrado un parpadeo.
        self._cambio_seleccion = DetectorDeCambio()
        self._cambio_di = DetectorDeCambio()
        self._cambio_ir = DetectorDeCambio(umbral=diagnostico.opcion("ZONA_MUERTA_PWM", 2))

        #: Instante del ultimo resumen periodico emitido.
        self._instante_resumen = time.ticks_ms()

        # Parametros de robustez leidos UNA vez, al construir, y no en cada uso.
        # Dos motivos: se evita repetir el acceso a config en el lazo, y se
        # centraliza aqui la tolerancia a un config.py desactualizado en la placa
        # -un fallo de despliegue habitual con tres nodos-, de modo que el nodo
        # arranca con valores por defecto seguros e informa, en lugar de abortar.
        self._reintentos = diagnostico.opcion("REINTENTOS_TRANSACCION", 1)
        self._ms_ausente = diagnostico.opcion("MS_PARA_DECLARAR_AUSENTE", 2000)
        self._zona_muerta_pwm = diagnostico.opcion("ZONA_MUERTA_PWM", 2)
        self._periodo_resumen = diagnostico.opcion("PERIODO_RESUMEN_MS", 5000)

        # --- Instrumentacion (Parte 2) --------------------------------------
        # El TP pide registrar el comportamiento temporal del sondeo, y "el LED
        # respondia rapido" no es un dato. Estos contadores producen la medicion
        # que va al informe: tiempo real de ciclo y tasa de error sobre una
        # poblacion de ciclos, no sobre una impresion subjetiva.
        #
        # Costo: cuatro enteros y una resta por ciclo. Despreciable frente a los
        # 200 ms del periodo, y se gana observabilidad de un sistema que de otro
        # modo solo se puede juzgar mirando LEDs.

        #: Ciclos de sondeo completados desde el arranque.
        self._ciclos_totales = 0

        #: Ciclos en los que al menos una de las 4 transacciones fallo.
        self._ciclos_con_fallo = 0

        #: Marca de tiempo del inicio del ciclo en curso.
        self._instante_inicio_ciclo = time.ticks_ms()

        #: Duracion util del ultimo ciclo (sin contar la espera), en ms. Es el
        #: tiempo que el bus estuvo efectivamente ocupado con las 4 transacciones.
        self._duracion_ciclo_ms = 0

        #: Bandera de "este ciclo ya conto como fallido", para no contabilizar
        #: dos veces un ciclo en el que fallen varias transacciones.
        self._ciclo_actual_fallido = False

        # Despachador estado -> metodo. Reemplaza una cadena de if/elif por una
        # tabla, que es la forma canonica de implementar una maquina de estados
        # y hace que agregar un estado no implique tocar la logica existente.
        self._acciones = {
            ESTADO_LEER_SELECTOR: self._accion_leer_selector,
            ESTADO_INDICAR_SELECCION: self._accion_indicar_seleccion,
            ESTADO_LEER_DI_REMOTO: self._accion_leer_di_remoto,
            ESTADO_LEER_IR_REMOTO: self._accion_leer_ir_remoto,
            ESTADO_ESCRIBIR_COIL_REMOTO: self._accion_escribir_coil_remoto,
            ESTADO_ESCRIBIR_HREG_REMOTO: self._accion_escribir_hreg_remoto,
            ESTADO_ESPERA: self._accion_espera,
        }

    # -------------------------------------------------------------------------
    # BLOQUE M2 — Lectura del switch selector de esclavo (Parte 3)
    # -------------------------------------------------------------------------
    def _accion_leer_selector(self):
        """
        Determina a que esclavo se dirigiran las transacciones de este ciclo.

        El selector se lee UNA vez por ciclo y no antes de cada transaccion. Es
        una decision deliberada: si se releyera entre transacciones, un cambio
        del switch a mitad de ciclo produciria una secuencia incoherente (leer
        del Esclavo 1 y escribir al Esclavo 2), dejando a ambos en un estado que
        no corresponde a ninguna orden completa. Muestrear al inicio garantiza
        que las cuatro transacciones del ciclo son atomicas respecto del destino.

        Convencion del switch (pull-up interno, contacto a GND):
            abierto   -> pin en 1 -> Esclavo 1
            a GND     -> pin en 0 -> Esclavo 2

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            Siguiente estado: ESTADO_INDICAR_SELECCION.

        Excepciones
        -----------
        Ninguna.
        """
        self._id_activo = (
            config.ID_ESCLAVO_1
            if self._perifericos["selector"].leer()
            else config.ID_ESCLAVO_2
        )

        # Un cambio de destino es un evento, no un estado: se registra al ocurrir.
        # Si en la consola aparecen cambios que el operador no provoco, el
        # problema esta en el selector y no en el bus, y el contador de rechazos
        # de la entrada confirmada lo cuantifica.
        if self._cambio_seleccion.cambio(self._id_activo):
            self._log.aviso("Seleccion -> Esclavo {} (cambios={} rechazos={})".format(
                self._id_activo,
                self._cambio_seleccion.transiciones - 1,
                self._perifericos["selector"].rechazos,
            ))

        # Marca de inicio del ciclo, para medir su duracion util (instrumentacion).
        self._instante_inicio_ciclo = time.ticks_ms()
        self._ciclo_actual_fallido = False

        return ESTADO_INDICAR_SELECCION

    # -------------------------------------------------------------------------
    # BLOQUE M3 — Indicacion visual del esclavo activo (Parte 3)
    # -------------------------------------------------------------------------
    def _accion_indicar_seleccion(self):
        """
        Enciende el LED indicador del esclavo activo y apaga el otro.

        Los dos LED son mutuamente excluyentes por construccion: se calculan a
        partir de la misma variable _id_activo, de modo que es imposible que
        queden ambos encendidos o ambos apagados. Derivar los dos estados de una
        unica fuente de verdad, en vez de encender uno y apagar el otro en
        lineas separadas, elimina por diseno el estado invalido.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            Siguiente estado: ESTADO_LEER_DI_REMOTO.

        Excepciones
        -----------
        Ninguna.
        """
        es_esclavo_1 = self._id_activo == config.ID_ESCLAVO_1
        self._perifericos["indicador_1"].escribir(es_esclavo_1)
        self._perifericos["indicador_2"].escribir(not es_esclavo_1)
        return ESTADO_LEER_DI_REMOTO

    # -------------------------------------------------------------------------
    # Ejecutor comun de transacciones: reintento, medicion y traza
    # -------------------------------------------------------------------------
    def _transaccion(self, etiqueta, operacion):
        """
        Ejecuta una transaccion MODBus con reintento, medicion y registro.

        Concentrar aqui el reintento, el cronometraje y la traza evita repetir
        cuatro veces el mismo bloque try/except y, sobre todo, garantiza que las
        cuatro transacciones se midan y se registren con el mismo criterio: si
        cada estado lo hiciera a su manera, los numeros no serian comparables
        entre si y la estadistica perderia sentido.

        Sobre el reintento: MODBus no confirma ni numera las tramas, de modo que
        reintentar es el unico mecanismo de recuperacion que define la
        especificacion. Es seguro aqui porque las cuatro operaciones son
        idempotentes: dos lecturas, y dos escrituras de valor absoluto. Repetir
        una escritura deja al esclavo en el mismo estado que ejecutarla una vez.

        Parametros
        ----------
        etiqueta : str
            Nombre de la funcion MODBus para los mensajes, por ejemplo
            "0x02 Read Discrete Inputs".
        operacion : callable
            Funcion sin argumentos que ejecuta la transaccion y devuelve su
            resultado. Se pasa como funcion y no como datos para que el reintento
            vuelva a emitir la peticion completa.

        Retorna
        -------
        tuple(bool, objeto)
            (True, resultado) si tuvo exito; (False, None) si se agotaron los
            reintentos.

        Excepciones
        -----------
        Ninguna se propaga: se atrapan, se clasifican y se contabilizan.
        """
        ultimo_error = None
        self._ultimo_sondeo_ms[self._id_activo] = time.ticks_ms()

        for intento in range(self._reintentos + 1):
            comienzo = time.ticks_ms()
            try:
                resultado = operacion()
            except Exception as error:
                ultimo_error = error
                clase = clasificar_error(error)
                self._estadistica[self._id_activo].registrar(clase)
                self._log.detalle("{} ID={} intento {}/{} FALLO {} ({} ms)".format(
                    etiqueta, self._id_activo, intento + 1,
                    self._reintentos + 1, clase,
                    time.ticks_diff(time.ticks_ms(), comienzo),
                ))
                continue

            self._estadistica[self._id_activo].registrar(None)
            self._ultimo_exito_ms[self._id_activo] = time.ticks_ms()
            self._log.detalle("{} ID={} OK {} ({} ms)".format(
                etiqueta, self._id_activo, resultado,
                time.ticks_diff(time.ticks_ms(), comienzo),
            ))
            if intento:
                # Que el reintento haya salvado la transaccion es informacion de
                # primer orden: significa que la perdida es esporadica y no que
                # el nodo este caido.
                self._log.aviso("{} ID={} recuperada en el reintento {}".format(
                    etiqueta, self._id_activo, intento,
                ))
            self._restaurar_si_estaba_ausente()
            return True, resultado

        self._registrar_fallo(etiqueta, ultimo_error)
        return False, None

    # -------------------------------------------------------------------------
    # BLOQUE M4 — Lectura del Discrete Input remoto (funcion 0x02)
    # -------------------------------------------------------------------------
    def _accion_leer_di_remoto(self):
        """
        Lee el switch del esclavo activo y lo replica en el LED digital local.

        Transaccion MODBus emitida (Modicon 10001 -> offset 0x0000):

            Peticion:  [ID][02][00 00][00 01][CRC_lo CRC_hi]        8 bytes
            Respuesta: [ID][02][01][estado][CRC_lo CRC_hi]          6 bytes

        Metodo de la libreria:
            read_discrete_inputs(slave_addr: int, starting_addr: int,
                                 input_qty: int) -> tuple[bool, ...]
            Devuelve una tupla de booleanos con tantos elementos como se pidieron;
            se toma el indice 0 porque se solicita una sola entrada.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_LEER_IR_REMOTO si la lectura fue exitosa; ESTADO_ESPERA si
            fallo, para no encadenar tres transacciones mas contra un esclavo
            que evidentemente no esta respondiendo.

        Excepciones
        -----------
        Ninguna se propaga: se atrapan y se contabilizan en registrar_fallo().
        """
        exito, respuesta = self._transaccion(
            "0x02 Read Discrete Inputs",
            lambda: self._bus.read_discrete_inputs(
                slave_addr=self._id_activo,
                starting_addr=config.DIR_DISCRETE_INPUT_SWITCH,
                input_qty=1,
            ),
        )
        if not exito:
            return ESTADO_ESPERA

        self._di_remoto = bool(respuesta[0])

        # Replicacion pedida por la Parte 2: la entrada digital del esclavo
        # se refleja en el LED digital local del maestro.
        self._perifericos["led_replicador_digital"].escribir(self._di_remoto)

        if self._cambio_di.cambio((self._id_activo, self._di_remoto)):
            self._log.info("DI Esclavo {} -> {} (LED digital local)".format(
                self._id_activo, 1 if self._di_remoto else 0,
            ))

        return ESTADO_LEER_IR_REMOTO

    # -------------------------------------------------------------------------
    # BLOQUE M5 — Lectura del Input Register remoto (funcion 0x04)
    # -------------------------------------------------------------------------
    def _accion_leer_ir_remoto(self):
        """
        Lee el potenciometro del esclavo activo y lo replica en el LED PWM local.

        Transaccion MODBus emitida (Modicon 30001 -> offset 0x0000):

            Peticion:  [ID][04][00 00][00 01][CRC_lo CRC_hi]        8 bytes
            Respuesta: [ID][04][02][val_MSB val_LSB][CRC_lo CRC_hi] 7 bytes

        Sobre el orden de bytes: el valor de 16 bits viaja BIG-ENDIAN dentro del
        registro (primero el byte mas significativo), a diferencia del CRC, que
        viaja little-endian. La libreria ya recompone el entero, por lo que el
        codigo de aplicacion recibe un int y no necesita hacer el corrimiento a
        mano. La verificacion de este punto esta en herramientas/decodificar_trama.py.

        Metodo de la libreria:
            read_input_registers(slave_addr: int, starting_addr: int,
                                 register_qty: int, signed: bool) -> tuple[int, ...]
            signed=False porque el ADC entrega un valor sin signo de 0 a 4095;
            con signed=True, cualquier lectura por encima de 32767 se
            interpretaria como negativa (no ocurre con 12 bits, pero declararlo
            explicitamente documenta la intencion y evita una sorpresa si el
            rango del registro se ampliara).

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESCRIBIR_COIL_REMOTO si tuvo exito, ESTADO_ESPERA si fallo.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        exito, respuesta = self._transaccion(
            "0x04 Read Input Registers",
            lambda: self._bus.read_input_registers(
                slave_addr=self._id_activo,
                starting_addr=config.DIR_INPUT_REGISTER_POTE,
                register_qty=1,
                signed=False,
            ),
        )
        if not exito:
            return ESTADO_ESPERA

        self._ir_remoto = respuesta[0]

        # Replicacion pedida por la Parte 2: el ADC remoto (0-4095) gobierna
        # la intensidad del LED PWM local (0-255). El escalado se hace aca,
        # en el consumidor del dato, no en el esclavo.
        pwm_local = adc_a_pwm(self._ir_remoto)
        self._perifericos["led_replicador_pwm"].escribir(pwm_local)

        if self._cambio_ir.cambio(pwm_local):
            self._log.info("IR Esclavo {} -> {} = PWM {} (LED PWM local)".format(
                self._id_activo, self._ir_remoto, pwm_local,
            ))

        return ESTADO_ESCRIBIR_COIL_REMOTO

    # -------------------------------------------------------------------------
    # BLOQUE M6 — Escritura del Coil remoto (funcion 0x05)
    # -------------------------------------------------------------------------
    def _accion_escribir_coil_remoto(self):
        """
        Escribe el estado del switch local en el LED digital del esclavo activo.

        Transaccion MODBus emitida (Modicon 00001 -> offset 0x0000):

            Peticion:  [ID][05][00 00][FF 00][CRC_lo CRC_hi]        8 bytes
            Respuesta: eco identico a la peticion                   8 bytes

        Sobre el valor 0xFF00: la especificacion MODBus no usa 0x0001 para
        "encendido" en la funcion 0x05, sino los valores 0xFF00 (ON) y 0x0000
        (OFF); cualquier otro valor debe rechazarse con una excepcion 03. La
        libreria hace esa traduccion a partir del booleano, pero conviene
        conocerla porque es lo que se va a ver en la captura de la trama.

        Metodo de la libreria:
            write_single_coil(slave_addr: int, output_address: int,
                              output_value: bool | int) -> bool
            Devuelve True si el esclavo confirmo con el eco esperado.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESCRIBIR_HREG_REMOTO si tuvo exito, ESTADO_ESPERA si fallo.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        estado_local = self._perifericos["switch_local"].leer()
        exito, _ = self._transaccion(
            "0x05 Write Single Coil",
            lambda: self._bus.write_single_coil(
                slave_addr=self._id_activo,
                output_address=config.DIR_COIL_LED_DIGITAL,
                output_value=estado_local,
            ),
        )
        return ESTADO_ESCRIBIR_HREG_REMOTO if exito else ESTADO_ESPERA

    # -------------------------------------------------------------------------
    # BLOQUE M7 — Escritura del Holding Register remoto (funcion 0x06)
    # -------------------------------------------------------------------------
    def _accion_escribir_hreg_remoto(self):
        """
        Escribe el potenciometro local en el PWM del esclavo activo.

        Transaccion MODBus emitida (Modicon 40001 -> offset 0x0000):

            Peticion:  [ID][06][00 00][00 XX][CRC_lo CRC_hi]        8 bytes
            Respuesta: eco identico a la peticion                   8 bytes

        El valor local del ADC (0-4095) se convierte al rango 0-255 que declara
        el mapa de registros ANTES de enviarlo. Enviar el valor crudo escribiria
        hasta 4095 en un registro documentado como 0-255: el esclavo lo acotaria
        y el sistema funcionaria, pero el contrato del mapa de registros quedaria
        violado y la lectura de vuelta del registro no coincidiria con lo escrito.

        Metodo de la libreria:
            write_single_register(slave_addr: int, register_address: int,
                                  register_value: int, signed: bool) -> bool

        Este es el ultimo estado del ciclo util: cuando termina, se cierra la
        ronda y se pasa a ESPERA. Ademas, un ciclo completado sin errores
        reinicia el contador de fallos consecutivos.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESPERA en cualquier caso (con o sin exito): el ciclo termino.

        Excepciones
        -----------
        Ninguna se propaga.
        """
        valor_local = adc_a_pwm(self._perifericos["potenciometro_local"].leer())

        # Zona muerta: si el valor no se movio mas alla del ruido del conversor,
        # no se emite la transaccion. Evita dos cosas a la vez: el titileo del
        # LED del esclavo por oscilaciones de una unidad, y el gasto de una
        # transaccion del bus para reescribir lo que ya estaba escrito.
        anterior = self._pwm_escrito[self._id_activo]
        if anterior is not None and abs(valor_local - anterior) <= self._zona_muerta_pwm:
            self._log.detalle("0x06 omitida ID={} (PWM {} dentro de la zona muerta)".format(
                self._id_activo, valor_local,
            ))
            exito = True
        else:
            exito, _ = self._transaccion(
                "0x06 Write Single Register",
                lambda: self._bus.write_single_register(
                    slave_addr=self._id_activo,
                    register_address=config.DIR_HOLDING_REGISTER_PWM,
                    register_value=valor_local,
                    signed=False,
                ),
            )
            if exito:
                self._pwm_escrito[self._id_activo] = valor_local

        if exito:
            # Ciclo completo sin errores: el esclavo esta sano.
            self._fallos_consecutivos = 0

        # --- Cierre del ciclo: instrumentacion ------------------------------
        # Se mide ACA y no en ESPERA porque lo que interesa es el tiempo que las
        # cuatro transacciones ocuparon el bus, no el periodo completo (que
        # incluye la espera y por definicion da PERIODO_SONDEO_MS).
        self._duracion_ciclo_ms = time.ticks_diff(
            time.ticks_ms(), self._instante_inicio_ciclo
        )
        self._ciclos_totales += 1
        if self._ciclo_actual_fallido:
            self._ciclos_con_fallo += 1

        # El resumen se emite por TIEMPO y no cada N ciclos. Con reintentos, la
        # duracion del ciclo es variable, de modo que un criterio por ciclos
        # produciria un resumen a intervalos irregulares, justamente cuando el
        # sistema esta degradado y el intervalo importa para leer la traza.
        if time.ticks_diff(time.ticks_ms(), self._instante_resumen) >= self._periodo_resumen:
            self._instante_resumen = time.ticks_ms()
            self._informar_estadisticas()

        return ESTADO_ESPERA

    def _informar_estadisticas(self):
        """
        Imprime por consola las metricas acumuladas del sondeo.

        Es la fuente de los datos cuantitativos que pide el informe: tiempo real
        de ocupacion del bus por ciclo y tasa de error medida sobre una poblacion
        de ciclos. Reemplaza afirmaciones subjetivas del tipo "respondia rapido"
        por numeros reproducibles.

        Formato de la linea emitida:

            [MAESTRO] ciclos=25 fallos=0 (0.0%) t_ciclo=104ms | ID=1 DI=0 IR=2048 -> PWM=128

        donde t_ciclo es la duracion util del ultimo ciclo (las 4 transacciones,
        sin la espera), DI e IR son los ultimos valores leidos del esclavo, y PWM
        el valor replicado en la salida local.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        # --- Linea 1: el ciclo de sondeo ------------------------------------
        # Conserva los mismos nombres de campo que la version anterior
        # (ciclos, fallos, t_ciclo, ID, DI, IR, PWM) para que las capturas ya
        # incluidas en el informe sigan siendo legibles con la misma leyenda.
        self._log.info(
            "ciclos={} fallos={} ({}) t_ciclo={}ms | ID={} DI={} IR={} -> PWM={}".format(
                self._ciclos_totales,
                self._ciclos_con_fallo,
                diagnostico.porcentaje(self._ciclos_con_fallo, self._ciclos_totales),
                self._duracion_ciclo_ms,
                self._id_activo,
                1 if self._di_remoto else 0,
                self._ir_remoto,
                adc_a_pwm(self._ir_remoto),
            )
        )

        # --- Lineas 2 y 3: una por esclavo ----------------------------------
        # Cada linea separa DOS informaciones que antes se confundian en una:
        #
        #   ventana  lo ocurrido desde el reporte anterior -> el estado ACTUAL
        #   total    lo acumulado desde el arranque        -> el HISTORIAL
        #
        # La confusion no era cosmetica. Con un solo esclavo seleccionado, el
        # otro conserva sus totales congelados, y una linea que repite
        # "err=239 (11.6%)" cada cinco segundos se lee como un nodo que esta
        # fallando ahora, cuando en realidad no se lo esta sondeando. Marcar el
        # esclavo activo e indicar hace cuanto que el otro no se sondea elimina
        # esa lectura equivocada.
        #
        # El criterio de diagnostico se mantiene: si AMBOS esclavos muestran una
        # tasa parecida y distinta de cero EN VENTANA, el sospechoso es el medio
        # compartido; si falla uno solo, el sospechoso es ese nodo.
        ahora = time.ticks_ms()
        for unit_id in sorted(self._estadistica):
            estadistica = self._estadistica[unit_id]

            if unit_id == self._id_activo:
                situacion = "ACTIVO"
            else:
                inactivo_s = time.ticks_diff(ahora, self._ultimo_sondeo_ms[unit_id]) // 1000
                situacion = "pausa {}s".format(inactivo_s)

            self._log.continuacion(diagnostico.INFO, "{} E{} {:<13} {:>18}  acum: {}".format(
                "->" if unit_id == self._id_activo else "  ",
                unit_id,
                situacion,
                estadistica.resumen_ventana(),
                estadistica.resumen(),
            ))
            estadistica.cerrar_ventana()

    def reiniciar_estadisticas(self):
        """
        Pone a cero los contadores de ambos esclavos y los del ciclo.

        Se invoca desde el Shell de Thonny antes de comenzar una medicion que se
        vaya a documentar. Permite separar la etapa de puesta a punto -donde los
        errores son esperables y no dicen nada del sistema terminado- de la
        corrida que se reporta, sin reiniciar la placa: un reinicio obligaria a
        reconstruir el estado del bus y a repetir la puesta en marcha.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.

        Ejemplo de uso
        --------------
        >>> MAESTRO.reiniciar_estadisticas()
        """
        for estadistica in self._estadistica.values():
            estadistica.reiniciar()
        self._ciclos_totales = 0
        self._ciclos_con_fallo = 0
        self._log.aviso("Estadisticas reiniciadas: comienza una medicion nueva")

    # -------------------------------------------------------------------------
    # BLOQUE M8 — Espera hasta completar el periodo de sondeo
    # -------------------------------------------------------------------------
    def _accion_espera(self):
        """
        Espera de forma NO BLOQUEANTE a que se cumpla el periodo de sondeo.

        No se usa time.sleep(): una espera bloqueante congela el nodo y, si mas
        adelante se agregaran tareas locales (una pantalla, un segundo bus, un
        pulsador de emergencia), quedarian sin atender durante todo el intervalo.
        La comparacion con ticks_diff() permite que el lazo principal siga
        girando libremente.

        Se usa ticks_diff() y no una resta directa porque el contador de
        milisegundos de MicroPython desborda y vuelve a cero; una resta simple
        daria un valor negativo enorme en ese instante y el maestro quedaria
        esperando indefinidamente.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        int
            ESTADO_ESPERA mientras no se cumpla el periodo; ESTADO_LEER_SELECTOR
            cuando corresponde iniciar un ciclo nuevo.

        Excepciones
        -----------
        Ninguna.
        """
        if time.ticks_diff(self._instante_fin_espera, time.ticks_ms()) > 0:
            return ESTADO_ESPERA

        self._instante_fin_espera = time.ticks_add(
            time.ticks_ms(), config.PERIODO_SONDEO_MS
        )
        return ESTADO_LEER_SELECTOR

    # -------------------------------------------------------------------------
    # BLOQUE M9 — Manejo de fallos de comunicacion
    # -------------------------------------------------------------------------
    def _registrar_fallo(self, funcion, error):
        """
        Contabiliza un fallo de transaccion y degrada de forma segura si persiste.

        Distincion importante para el informe: un TIMEOUT (el esclavo no
        respondio) y una EXCEPCION MODBus (el esclavo respondio con un codigo de
        error 01 a 04) son cosas distintas. La primera indica un problema de bus,
        direccion o alimentacion; la segunda indica que el esclavo esta vivo y
        entiende el protocolo, pero rechaza la peticion concreta. La libreria
        senaliza ambos casos como excepcion de Python, por lo que se registra el
        texto del error para poder distinguirlos en el diagnostico.

        Politica de degradacion: tras config.MS_PARA_DECLARAR_AUSENTE
        milisegundos sin NINGUNA transaccion exitosa contra el esclavo en curso,
        se apagan los LED replicadores locales. El criterio de ingenieria es que
        una indicacion congelada es peor que ninguna indicacion: un operador que
        ve el LED replicador encendido supone que esa es la lectura actual del
        esclavo, cuando en realidad es un valor viejo de hace varios segundos.

        El criterio es TEMPORAL y no por fallos contados. Contando fallos, tres
        perdidas aisladas separadas por ciclos correctos disparaban igualmente la
        degradacion, y el efecto visible era un parpadeo de los LED del maestro
        que no correspondia a ningun cambio real en el esclavo.

        Notese que esto NO afecta a las salidas del esclavo, que conservan su
        ultimo valor recibido: eso es exactamente lo que pide la Parte 3.

        Parametros
        ----------
        funcion : str
            Nombre de la funcion MODBus que fallo, para el mensaje de consola.
        error : Exception
            Excepcion capturada.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        self._fallos_consecutivos += 1
        # Marca el ciclo en curso como fallido. Se usa una bandera y no un
        # contador para que un ciclo con varias transacciones caidas cuente como
        # UN ciclo fallido: la metrica que interesa es "que fraccion de los
        # ciclos de sondeo salio completa", no cuantas tramas se perdieron.
        self._ciclo_actual_fallido = True

        self._log.error("Fallo {} con Esclavo {} [{}] ({} consecutivos): {}".format(
            funcion, self._id_activo, clasificar_error(error),
            self._fallos_consecutivos, error,
        ))

        # Degradacion por AUSENCIA SOSTENIDA, no por fallos contados.
        #
        # El criterio anterior apagaba los LED replicadores tras tres ciclos
        # consecutivos con algun fallo. Con tres nodos en el bus, las perdidas
        # esporadicas dejan de ser raras, y ese criterio hacia que los LED del
        # maestro se apagaran y se volvieran a encender cada pocos cientos de
        # milisegundos: el parpadeo observado en banco no era el esclavo
        # cambiando de estado, era la politica de degradacion reaccionando a
        # perdidas aisladas. Exigir un intervalo sin NINGUNA transaccion exitosa
        # mantiene intacta la intencion original -no mostrar un dato viejo como
        # si fuera actual- y elimina la reaccion desproporcionada.
        sin_respuesta_ms = time.ticks_diff(
            time.ticks_ms(), self._ultimo_exito_ms[self._id_activo]
        )
        if sin_respuesta_ms >= self._ms_ausente and not self._ausente:
            self._ausente = True
            self._perifericos["led_replicador_digital"].escribir(False)
            self._perifericos["led_replicador_pwm"].apagar()
            self._log.aviso(
                "Esclavo {} AUSENTE ({} ms sin responder): replicadores apagados".format(
                    self._id_activo, sin_respuesta_ms,
                )
            )

    def _restaurar_si_estaba_ausente(self):
        """
        Sale del estado degradado tras recuperar la comunicacion.

        Se emite una sola linea al volver, y no una por cada transaccion
        exitosa: el evento es la transicion, no la permanencia. Sin esta
        funcion, el estado de ausencia quedaria pegado y el maestro nunca
        volveria a informar que el esclavo regreso.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna.
        """
        if self._ausente:
            self._ausente = False

            # Se olvida el ultimo PWM escrito para forzar una reescritura en el
            # ciclo siguiente. Sin esto, la zona muerta introduciria un fallo
            # sutil: si el esclavo se reinicio durante la ausencia, sus salidas
            # arrancan en el estado seguro (PWM 0) y el maestro, al comparar
            # contra el valor que creia escrito, decidiria que no hace falta
            # reescribir. El LED del esclavo quedaria apagado hasta que alguien
            # moviera el potenciometro del maestro.
            #
            # Es el caso general de toda optimizacion basada en "ya lo escribi":
            # solo es valida mientras se pueda sostener que el otro extremo no
            # perdio el estado. Una reconexion rompe exactamente esa premisa.
            self._pwm_escrito[self._id_activo] = None

            self._log.aviso("Esclavo {} PRESENTE otra vez: replicadores activos, "
                            "se fuerza reescritura del PWM".format(self._id_activo))

    # -------------------------------------------------------------------------
    # Motor de la maquina de estados
    # -------------------------------------------------------------------------
    def ejecutar_paso(self):
        """
        Ejecuta la accion del estado actual y transiciona al siguiente.

        Es el unico punto donde cambia self._estado, lo que hace que el flujo sea
        facil de seguir y de instrumentar: para depurar el ciclo alcanza con
        imprimir NOMBRES_ESTADO[self._estado] en esta funcion.

        Parametros
        ----------
        Ninguno.

        Retorna
        -------
        None

        Excepciones
        -----------
        Ninguna se propaga. Un error inesperado en la accion de un estado se
        informa y la maquina se reinicia en ESTADO_ESPERA, de modo que el maestro
        nunca queda trabado en un estado invalido.
        """
        try:
            self._estado = self._acciones[self._estado]()
        except Exception as error:
            print("[MAESTRO] Error inesperado en estado {}: {}".format(
                NOMBRES_ESTADO.get(self._estado, self._estado), error,
            ))
            self._estado = ESTADO_ESPERA


# =============================================================================
# BLOQUE M1 del diagrama de flujo — Inicializacion del nodo
# =============================================================================

def configurar_perifericos():
    """
    Instancia los perifericos locales del maestro.

    Son ocho en total: los cuatro comunes a todos los nodos (switch,
    potenciometro, LED digital, LED PWM) mas los cuatro que agrega la Parte 3
    (switch selector y dos LED indicadores; el selector se lee como Pin crudo
    porque no necesita antirrebote — ver nota abajo).

    Nota sobre el selector sin antirrebote: se muestrea una sola vez por ciclo de
    sondeo (cada 200 ms), intervalo mucho mayor que la duracion de los rebotes
    (1-10 ms). En el peor caso, un rebote hace que un unico ciclo se dirija al
    esclavo equivocado, y el siguiente ya corrige. Agregar antirrebote aca seria
    resolver un problema que el muestreo lento ya resuelve (YAGNI).

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    dict
        Perifericos indexados por nombre.

    Excepciones
    -----------
    ValueError
        Propagada desde la capa de perifericos si un pin de config.py fuera
        incompatible con su uso.
    """
    return {
        "switch_local": EntradaDigital(config.PIN_SWITCH),
        "potenciometro_local": EntradaAnalogica(config.PIN_POTENCIOMETRO),
        "led_replicador_digital": SalidaDigital(config.PIN_LED_DIGITAL, estado_inicial=False),
        "led_replicador_pwm": SalidaPWM(config.PIN_LED_PWM),
        # El selector se envuelve en EntradaConfirmada: se muestrea una sola vez
        # por ciclo, de modo que un unico pulso espurio en ese instante desviaria
        # las cuatro transacciones del ciclo al esclavo equivocado. Exigir varias
        # muestras coincidentes convierte ese pulso en un evento descartado, y el
        # contador de rechazos deja registrado cuanto ruido recibe la entrada.
        "selector": EntradaConfirmada(Pin(config.PIN_SELECTOR, Pin.IN, Pin.PULL_UP)),
        "indicador_1": SalidaDigital(config.PIN_LED_INDICADOR_1, estado_inicial=False),
        "indicador_2": SalidaDigital(config.PIN_LED_INDICADOR_2, estado_inicial=False),
    }


def configurar_maestro_modbus():
    """
    Crea la interfaz MODBus RTU en modo maestro.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    umodbus.serial.Serial
        Interfaz lista para emitir transacciones.

    Excepciones
    -----------
    OSError
        Si el UART indicado no puede inicializarse.

    Detalle de la configuracion de la libreria
    ------------------------------------------
    Constructor Serial(uart_id, baudrate, data_bits, stop_bits, parity, pins,
    ctrl_pin). A diferencia del esclavo, NO recibe un parametro `addr`: un
    maestro MODBus no tiene direccion propia porque nunca es destinatario de una
    trama, solo emisor. Es una diferencia conceptual que conviene tener a mano
    para la defensa oral.
    """
    return MaestroRTUConTimeout(
        uart_id=config.UART_ID,
        baudrate=config.BAUDRATE,
        data_bits=config.BITS_DATOS,
        stop_bits=config.BITS_PARADA,
        parity=config.PARIDAD,
        pins=(config.PIN_UART_TX, config.PIN_UART_RX),
        ctrl_pin=config.PIN_DE_RE,
    )


def main():
    """
    Punto de entrada del firmware del maestro.

    Parametros
    ----------
    Ninguno.

    Retorna
    -------
    None. Contiene el lazo infinito del dispositivo.

    Excepciones
    -----------
    Ninguna se propaga hacia afuera.
    """
    # Primero de todo: confirmar que esta placa tiene el config.py de esta
    # version. Es un chequeo de despliegue, no de logica, y por eso va antes de
    # construir nada.
    diagnostico.verificar_config()

    global MAESTRO

    perifericos = configurar_perifericos()
    bus = configurar_maestro_modbus()
    maestro = MaestroModbus(bus, perifericos)

    # Se publica la instancia a nivel de modulo para poder inspeccionarla y
    # operarla desde el Shell de Thonny tras interrumpir con Ctrl+C, sin
    # reiniciar la placa ni perder el estado del bus. Es el equivalente
    # embebido de una consola de administracion:
    #
    #   >>> MAESTRO.reiniciar_estadisticas()   antes de una medicion
    #   >>> LOG.fijar_nivel(diagnostico.TRAMA) para capturar tramas
    MAESTRO = maestro

    print("=" * 58)
    print("MAESTRO MODBus RTU")
    print("Bus: {} baudios, {}{}{}".format(
        config.BAUDRATE,
        config.BITS_DATOS,
        "N" if config.PARIDAD is None else "E",
        config.BITS_PARADA,
    ))
    print("UART{}  TX=GPIO{}  RX=GPIO{}  DE/RE=GPIO{}".format(
        config.UART_ID, config.PIN_UART_TX, config.PIN_UART_RX, config.PIN_DE_RE,
    ))
    print("Periodo de sondeo: {} ms  |  Timeout: {} ms  |  Reintentos: {}".format(
        config.PERIODO_SONDEO_MS, config.TIMEOUT_RESPUESTA_MS,
        diagnostico.opcion("REINTENTOS_TRANSACCION", 1),
    ))
    print("Nivel de traza: {} (0 silencio ... 5 trama)".format(
        diagnostico.opcion("NIVEL_LOG", diagnostico.INFO),
    ))
    print("Selector GPIO{}: abierto = Esclavo 1, a GND = Esclavo 2".format(
        config.PIN_SELECTOR,
    ))
    print("=" * 58)

    while True:
        maestro.ejecutar_paso()


if __name__ == "__main__":
    main()
