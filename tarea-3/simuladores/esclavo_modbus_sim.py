#!/usr/bin/env python3
"""
esclavo_modbus_sim.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-09
Version: 1.0

Descripcion general
-------------------
Esclavo MODBus RTU simulado, para probar el maestro de Node-RED SIN hardware.

No reimplementa el protocolo: importa el stack REAL del firmware del ESP32
(firmware/esclavo-modbus/lib/modbus_slave) y sus perfiles (src/config.py). Cada prueba del
maestro en JavaScript contra este simulador es, ademas, una prueba cruzada entre las dos
implementaciones del CRC y del protocolo (maestro JS y esclavo MicroPython/CPython).

Dos medios:
  --serie PUERTO   puerto serie (un pty de socat, o un conversor USB-RS485 real). Requiere
                   pyserial. Ojo: un pty IGNORA baud y paridad (ver scripts/dev-serial.sh).
  --tcp HOST:PORT  servidor TCP con tramas RTU crudas. Si el cliente envia al conectar la
                   linea "PDCI-LINEA <baud> <paridad> <bits> <parada>" y no coincide con la del
                   simulador, se emula un UART desajustado: todo lo recibido es basura y no se
                   responde. Es lo que hace que el asistente de descubrimiento pruebe algo.

Fallas inyectables (--falla, o en vivo por la entrada estandar):
  ninguna    responde normalmente
  silencio   no responde                      -> el maestro cuenta TIMEOUT
  crc        responde con el CRC alterado     -> CRC_ERROR
  truncada   responde sin el ultimo byte      -> trama no recomponible (CRC_ERROR)
  excepcion  responde excepcion 04            -> EXCEPTION
  retardo    responde tarde (--retardo-ms)    -> TIMEOUT si supera el timeout del maestro
con probabilidad --prob (0-1).

Comandos por la entrada estandar (una linea cada uno):
  falla <modo> [prob] [retardo_ms] · pulsador 0|1 · pote <0-4095> · auto on|off ·
  estado · salir

Dependencias externas
---------------------
Python 3.10+. pyserial solo para --serie (pip install pyserial).

Uso
---
    python tarea-3/simuladores/esclavo_modbus_sim.py --tcp 127.0.0.1:5020
    python tarea-3/simuladores/esclavo_modbus_sim.py --serie /tmp/pdci-esclavo --falla crc --prob 0.2
"""

import argparse
import random
import select
import socket
import sys
import threading
import time
from pathlib import Path

RAIZ_T3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_T3 / "firmware" / "esclavo-modbus" / "lib"))
sys.path.insert(0, str(RAIZ_T3 / "firmware" / "esclavo-modbus" / "src"))

import config as config_firmware                          # noqa: E402  perfiles del ESP32
from modbus_slave import crc16, frame_parser               # noqa: E402  stack REAL del esclavo
from modbus_slave.data_model import ModeloDatos            # noqa: E402

MODOS_FALLA = ("ninguna", "silencio", "crc", "truncada", "excepcion", "retardo")
PARIDAD_LARGA = {"N": "none", "E": "even", "O": "odd"}


def ahora_us():
    """Reloj monotono en microsegundos (sin desborde: no hace falta ticks_diff)."""
    return time.perf_counter_ns() // 1000


def hexa(datos):
    """bytes -> '01 04 00 00'."""
    return " ".join("{:02X}".format(b) for b in datos)


class Simulador:
    """
    Un esclavo MODBus RTU con el stack del firmware y fallas inyectables.

    Atributos principales:
        perfil (str), unit_id (int), baud (int), paridad (str 'none'|'even'|'odd'),
        bits_parada (int), modelo (ModeloDatos), ensamblador (EnsambladorTramas),
        falla (str), prob (float), retardo_ms (int), auto (bool),
        estadistica (dict): respuestas, fallas inyectadas y bytes de basura.
    """

    def __init__(self, args):
        perfil = config_firmware.PERFILES[args.perfil]
        self.perfil = args.perfil
        self.unit_id = args.id if args.id is not None else perfil["unit_id"]
        self.baud = args.baud if args.baud is not None else perfil["baud"]
        self.paridad = args.paridad or PARIDAD_LARGA[perfil["paridad"]]
        self.bits_parada = perfil["bits_parada"]
        self.modelo = ModeloDatos(perfil["mapa"])
        _, t15, t35 = frame_parser.tiempos_us(self.baud)
        # Por TCP o pty los bytes llegan en bloques: la regla de t1,5 no se puede medir y se
        # desactiva; el fin de trama sigue siendo t3,5 calculado del baud rate, como en el ESP32.
        self.ensamblador = frame_parser.EnsambladorTramas(t15, t35, verificar_t15=False)
        self.falla, self.prob, self.retardo_ms = args.falla, args.prob, args.retardo_ms
        self.auto = not args.manual
        self.verbose = args.verbose
        self.inicio = time.monotonic()
        self.pulsador_manual, self.pote_manual = False, 0
        self.salidas_previas = None
        self.estadistica = {"tramas": 0, "respondidas": 0, "inyectadas": 0, "basura_bytes": 0}
        self.cerradura = threading.Lock()
        self.activo = True

    # ------------------------------------------------------------------ entradas y salidas
    def actualizar_entradas(self):
        """Pulsador y potenciometro simulados: automaticos (onda) o fijados a mano."""
        t = time.monotonic() - self.inicio
        if self.auto:
            pulsador = int(t / 3) % 2 == 1                       # cambia cada 3 s
            fase = (t % 20) / 20                                 # triangular de 20 s
            pote = int(4095 * (2 * fase if fase < 0.5 else 2 * (1 - fase)))
        else:
            pulsador, pote = self.pulsador_manual, self.pote_manual
        self.modelo.fijar_entrada("pulsador", pulsador)
        self.modelo.fijar_entrada("potenciometro", pote)
        self.modelo.fijar_entrada("uptime_s", int(t) & 0xFFFF)

    def informar_salidas(self):
        """Imprime los cambios de las salidas (lo que haria el LED del ESP32)."""
        salidas = (self.modelo.valor_de_senal("led_digital"), self.modelo.valor_de_senal("led_pwm"))
        if salidas != self.salidas_previas:
            self.salidas_previas = salidas
            print("[SIM] salidas: LED digital={} LED PWM={}".format(*salidas), flush=True)

    # ------------------------------------------------------------------ protocolo
    def atender(self, trama, defectuosa, escribir):
        """Procesa una trama con el stack del firmware y aplica la falla configurada."""
        self.estadistica["tramas"] += 1
        respuesta, motivo = frame_parser.procesar_trama(trama, self.unit_id, self.modelo, defectuosa)
        if self.verbose:
            print("[SIM] RX {} -> {}".format(hexa(trama), motivo), flush=True)
        if respuesta is None:
            return
        falla = self.falla if (self.falla != "ninguna" and random.random() < self.prob) else "ninguna"
        if falla != "ninguna":
            self.estadistica["inyectadas"] += 1
        if falla == "silencio":
            return
        if falla == "crc":
            respuesta = bytearray(respuesta)
            respuesta[-1] ^= 0x5A
        elif falla == "truncada":
            respuesta = respuesta[:-1]
        elif falla == "excepcion":
            respuesta = crc16.agregar_crc(bytes([self.unit_id, trama[1] | 0x80, 0x04]))
        elif falla == "retardo":
            time.sleep(self.retardo_ms / 1000)
        escribir(bytes(respuesta))
        self.estadistica["respondidas"] += 1
        if self.verbose:
            print("[SIM] TX {}{}".format(hexa(respuesta), "" if falla == "ninguna" else "  (falla: " + falla + ")"),
                  flush=True)
        self.informar_salidas()

    def bucle(self, leer, escribir, linea_ok=lambda: True):
        """
        Lazo comun a TCP y serie: leer() devuelve bytes (b'' si no hay), escribir(bytes).
        Si linea_ok() es False (UART desajustado), lo recibido se descarta como basura.
        """
        ultimo_refresco = 0.0
        while self.activo:
            datos = leer()
            ahora = ahora_us()
            with self.cerradura:
                if datos:
                    if not linea_ok():
                        self.estadistica["basura_bytes"] += len(datos)
                        continue
                    cerrada = self.ensamblador.alimentar(datos, ahora)
                    if cerrada:
                        self.atender(cerrada[0], cerrada[1], escribir)
                    continue
                trama = self.ensamblador.trama_completa(ahora)
                if trama:
                    self.atender(trama[0], trama[1], escribir)
                    continue
                if time.monotonic() - ultimo_refresco > 0.05:
                    ultimo_refresco = time.monotonic()
                    self.actualizar_entradas()

    # ------------------------------------------------------------------ medios
    def servir_tcp(self, direccion):
        """Servidor TCP: un maestro a la vez; una conexion nueva reemplaza a la anterior."""
        host, port = direccion.rsplit(":", 1)
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((host, int(port)))
        servidor.listen(1)
        print("[SIM] {} | Unit ID {} | {} {} {} | TCP {}".format(
            self.perfil, self.unit_id, self.baud, self.paridad, self.bits_parada, direccion), flush=True)
        print("LISTO", flush=True)        # marca para las pruebas automaticas
        while self.activo:
            conexion, _ = servidor.accept()
            conexion.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            estado = {"pendiente": b"", "linea_ok": True, "preambulo": None}

            def leer():
                listos, _, _ = select.select([conexion], [], [], 0.0005)
                if not listos:
                    return b""
                datos = conexion.recv(4096)
                if not datos:
                    raise ConnectionResetError
                if estado["preambulo"] is None:
                    # El primer bloque puede traer la linea PDCI-LINEA seguida de bytes RTU.
                    estado["pendiente"] += datos
                    if estado["pendiente"].startswith(b"PDCI-LINEA"):
                        if b"\n" not in estado["pendiente"]:
                            return b""
                        linea, _, resto = estado["pendiente"].partition(b"\n")
                        estado["preambulo"] = linea.decode(errors="replace")
                        estado["linea_ok"] = self.linea_coincide(estado["preambulo"])
                        print("[SIM] maestro conectado: {} -> {}".format(
                            estado["preambulo"], "linea OK" if estado["linea_ok"] else "DESAJUSTE (basura)"),
                            flush=True)
                        return resto
                    estado["preambulo"] = ""          # cliente sin preambulo: se asume la linea OK
                    return estado["pendiente"]
                return datos

            try:
                self.bucle(leer, conexion.sendall, lambda: estado["linea_ok"])
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                conexion.close()

    def linea_coincide(self, preambulo):
        """Compara 'PDCI-LINEA baud paridad bits parada' con la configuracion propia."""
        partes = preambulo.split()
        try:
            return (int(partes[1]) == self.baud and partes[2] == self.paridad
                    and int(partes[3]) == 8 and int(partes[4]) == self.bits_parada)
        except (IndexError, ValueError):
            return False

    def servir_serie(self, puerto):
        """Puerto serie con pyserial (pty de socat o conversor USB-RS485)."""
        import serial
        paridad = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN, "odd": serial.PARITY_ODD}[self.paridad]
        ser = serial.Serial(puerto, self.baud, bytesize=8, parity=paridad, stopbits=self.bits_parada, timeout=0)
        print("[SIM] {} | Unit ID {} | {} {} {} | serie {}".format(
            self.perfil, self.unit_id, self.baud, self.paridad, self.bits_parada, puerto), flush=True)
        print("LISTO", flush=True)

        def leer():
            n = ser.in_waiting
            if n:
                return ser.read(n)
            time.sleep(0.0002)
            return b""
        self.bucle(leer, lambda d: (ser.write(d), ser.flush()))

    # ------------------------------------------------------------------ consola
    def consola(self):
        """Comandos por la entrada estandar (hilo aparte)."""
        for linea in sys.stdin:
            partes = linea.split()
            if not partes:
                continue
            with self.cerradura:
                cmd = partes[0]
                if cmd == "falla" and len(partes) >= 2 and partes[1] in MODOS_FALLA:
                    self.falla = partes[1]
                    self.prob = float(partes[2]) if len(partes) > 2 else 1.0
                    if len(partes) > 3:
                        self.retardo_ms = int(partes[3])
                    print("[SIM] falla={} prob={} retardo={} ms".format(self.falla, self.prob, self.retardo_ms), flush=True)
                elif cmd == "pulsador" and len(partes) == 2:
                    self.auto, self.pulsador_manual = False, partes[1] == "1"
                elif cmd == "pote" and len(partes) == 2:
                    self.auto, self.pote_manual = False, max(0, min(4095, int(partes[1])))
                elif cmd == "auto" and len(partes) == 2:
                    self.auto = partes[1] == "on"
                elif cmd == "estado":
                    print("[SIM] {} | LED={} PWM={}".format(self.estadistica, self.modelo.valor_de_senal("led_digital"),
                                                            self.modelo.valor_de_senal("led_pwm")), flush=True)
                elif cmd == "salir":
                    self.activo = False
                    break
                else:
                    print("[SIM] comando no reconocido: " + linea.strip(), flush=True)
        # Entrada estandar cerrada: el simulador sigue (puede correr en segundo plano).


def argumentos(argv=None, perfil_por_defecto="DISPOSITIVO_1"):
    """Opciones de linea de comandos."""
    p = argparse.ArgumentParser(description="Esclavo MODBus RTU simulado con el stack del firmware")
    medio = p.add_mutually_exclusive_group(required=True)
    medio.add_argument("--tcp", help="HOST:PUERTO, p. ej. 127.0.0.1:5020")
    medio.add_argument("--serie", help="puerto serie, p. ej. /tmp/pdci-esclavo o COM7")
    p.add_argument("--perfil", default=perfil_por_defecto, choices=sorted(config_firmware.PERFILES))
    p.add_argument("--id", type=int, help="Unit ID (por defecto, el del perfil)")
    p.add_argument("--baud", type=int, help="baud rate (por defecto, el del perfil)")
    p.add_argument("--paridad", choices=("none", "even", "odd"), help="paridad (por defecto, la del perfil)")
    p.add_argument("--falla", default="ninguna", choices=MODOS_FALLA)
    p.add_argument("--prob", type=float, default=1.0, help="probabilidad de la falla (0-1)")
    p.add_argument("--retardo-ms", type=int, default=500)
    p.add_argument("--manual", action="store_true", help="entradas fijas (pulsador 0, pote 0) en vez de automaticas")
    p.add_argument("--verbose", action="store_true", help="una linea por trama")
    return p.parse_args(argv)


def main(argv=None, perfil_por_defecto="DISPOSITIVO_1"):
    """Punto de entrada."""
    args = argumentos(argv, perfil_por_defecto)
    sim = Simulador(args)
    threading.Thread(target=sim.consola, daemon=True).start()
    try:
        if args.tcp:
            sim.servir_tcp(args.tcp)
        else:
            sim.servir_serie(args.serie)
    except KeyboardInterrupt:
        print("\n[SIM] detenido", flush=True)


if __name__ == "__main__":
    main()
