# -*- coding: utf-8 -*-
"""
latencia_captura.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-14
Version: 1.0

Descripcion general
-------------------
Consigna, Parte 4.8: "medir si cambia la latencia del intercambio" en los
modos None, Sign y SignAndEncrypt.

En SignAndEncrypt no se puede saber que servicio lleva cada mensaje (esta
cifrado), asi que la latencia se mide a nivel TCP: el tiempo entre un
segmento con datos del cliente hacia el puerto 4840 y el PRIMER segmento con
datos del servidor que le sigue. Con los Write de la rampa cada 100 ms, cada
par es un WriteRequest y su WriteResponse. Como la captura se hace en la
RPi 2 (el cliente), ese tiempo incluye la ida y vuelta por el cable y el
procesamiento del servidor: es la latencia que ve el cliente.

Entrada: la salida de tshark con tres campos separados por tabulador:

    tshark -r captura.pcapng -Y "tcp.port==4840 && tcp.len>0" \
           -T fields -e frame.time_relative -e tcp.srcport -e tcp.len > campos.tsv

Uso
---
    python latencia_captura.py campos.tsv
    python latencia_captura.py --prueba

Limitacion: en el Modo B los PublishResponse llegan sin pedido inmediato y
pueden emparejarse con un Write. Para medir esta latencia conviene el Modo A
con la rampa del servidor detenida, o filtrar por tamano (--min-bytes).

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""
import statistics
import sys

PUERTO = 4840


def emparejar(filas, ventana_s=0.5):
    """
    Latencias peticion -> respuesta a partir de (tiempo, puerto_origen, largo).

    Parametros
    ----------
    filas : list[tuple(float, int, int)]
    ventana_s : float
        Respuestas que tardan mas que esto se descartan (no son la respuesta).

    Retorna
    -------
    list[float]
        Latencias en milisegundos.
    """
    latencias = []
    pendiente = None
    for t, puerto, _ in filas:
        if puerto != PUERTO:          # cliente -> servidor
            if pendiente is None:
                pendiente = t
        elif pendiente is not None:   # servidor -> cliente
            if t - pendiente <= ventana_s:
                latencias.append((t - pendiente) * 1000.0)
            pendiente = None
    return latencias


def leer(ruta, min_bytes=0):
    """Lee el TSV de tshark: tiempo, puerto origen, largo TCP."""
    filas = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            partes = linea.split()
            if len(partes) == 3 and int(partes[2]) >= min_bytes:
                filas.append((float(partes[0]), int(partes[1]), int(partes[2])))
    return filas


def main(argumentos):
    """Punto de entrada."""
    if "--prueba" in argumentos:
        filas = [(0.000, 51000, 114), (0.004, 4840, 64), (0.100, 51000, 114), (0.103, 4840, 64),
                 (0.200, 51000, 114), (0.900, 4840, 89)]   # el ultimo: fuera de ventana
        lat = [round(x) for x in emparejar(filas)]
        ok = lat == [4, 3]
        print("Autoverificacion: " + ("OK" if ok else "FALLA {}".format(lat)))
        return 0 if ok else 1
    if not argumentos:
        print(__doc__)
        return 2
    min_bytes = 0
    if "--min-bytes" in argumentos:
        min_bytes = int(argumentos[argumentos.index("--min-bytes") + 1])
    lat = emparejar(leer(argumentos[0], min_bytes))
    if not lat:
        print("Sin pares peticion/respuesta.")
        return 1
    orden = sorted(lat)
    print("n={}  min={:.2f} ms  mediana={:.2f} ms  media={:.2f} ms  p95={:.2f} ms  max={:.2f} ms".format(
        len(orden), orden[0], statistics.median(orden), statistics.mean(orden),
        orden[int(0.95 * (len(orden) - 1))], orden[-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
