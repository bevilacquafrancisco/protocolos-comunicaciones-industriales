# -*- coding: utf-8 -*-
"""
medir_latencia.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-14
Version: 1.0

Descripcion general
-------------------
Consigna, Parte 3.4: "medir la latencia entre el accionamiento del pulsador
en una placa y el encendido del LED en la otra".

Las function nodes X4 (pulsador) y X6 (LED digital) registran en el journal
una linea por evento:

    ... LATENCIA pulsador_local=ON t=2026-10-20T15:04:05.123Z
    ... LATENCIA led_digital=ON t=2026-10-20T15:04:05.241Z

Esta herramienta lee el registro de la placa ORIGEN (donde se presiono) y el
de la placa DESTINO (donde se encendio el LED), empareja cada flanco con el
primer cambio del LED al mismo estado que ocurre despues (dentro de una
ventana de 2 s), y calcula las estadisticas.

Condicion para que el numero signifique algo: los relojes de ambas placas
sincronizados (chrony, node-red/README.md §14). Se informa junto con el
desvio de chrony ("System time" de chronyc tracking), que acota el error.

Uso
---
En cada placa:  journalctl -u nodered --since "10 min ago" > rpiN.log
En la PC:
    python medir_latencia.py origen.log destino.log
    python medir_latencia.py --prueba          # autoverificacion

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""
import re
import statistics
import sys
from datetime import datetime

PATRON = re.compile(r"LATENCIA (pulsador_local|led_digital)=(ON|OFF) t=(\S+Z)")
VENTANA_S = 2.0


def leer_eventos(lineas, tipo):
    """
    Extrae los eventos de un tipo del registro.

    Parametros
    ----------
    lineas : iterable[str]
        Lineas del journal.
    tipo : str
        'pulsador_local' o 'led_digital'.

    Retorna
    -------
    list[tuple(datetime, str)]
        (instante, 'ON'|'OFF') en orden cronologico.
    """
    eventos = []
    for linea in lineas:
        m = PATRON.search(linea)
        if m and m.group(1) == tipo:
            instante = datetime.fromisoformat(m.group(3).replace("Z", "+00:00"))
            eventos.append((instante, m.group(2)))
    return sorted(eventos)


def emparejar(flancos, cambios_led):
    """
    Para cada flanco del pulsador, el primer cambio del LED al mismo estado
    dentro de VENTANA_S segundos.

    Retorna
    -------
    tuple(list[float], int)
        Latencias en ms y cantidad de flancos sin pareja.
    """
    latencias, huerfanos = [], 0
    for t, estado in flancos:
        candidatos = [tl for tl, el in cambios_led
                      if el == estado and 0 <= (tl - t).total_seconds() <= VENTANA_S]
        if candidatos:
            latencias.append((min(candidatos) - t).total_seconds() * 1000.0)
        else:
            huerfanos += 1
    return latencias, huerfanos


def resumen(latencias):
    """Estadisticas en ms: n, min, media, mediana, p95, max."""
    if not latencias:
        return None
    ordenadas = sorted(latencias)
    p95 = ordenadas[min(len(ordenadas) - 1, int(round(0.95 * (len(ordenadas) - 1))))]
    return {
        "n": len(ordenadas), "min": ordenadas[0], "media": statistics.mean(ordenadas),
        "mediana": statistics.median(ordenadas), "p95": p95, "max": ordenadas[-1],
    }


def autoverificar():
    """Caso sintetico con latencias conocidas de 100, 120 y 200 ms."""
    origen = [
        "x LATENCIA pulsador_local=ON t=2026-10-20T15:00:00.000Z",
        "x LATENCIA pulsador_local=OFF t=2026-10-20T15:00:01.000Z",
        "x LATENCIA pulsador_local=ON t=2026-10-20T15:00:05.000Z",
        "x LATENCIA pulsador_local=OFF t=2026-10-20T15:00:20.000Z",  # sin LED: huerfano
    ]
    destino = [
        "y LATENCIA led_digital=ON t=2026-10-20T15:00:00.100Z",
        "y LATENCIA led_digital=OFF t=2026-10-20T15:00:01.120Z",
        "y LATENCIA led_digital=ON t=2026-10-20T15:00:05.200Z",
    ]
    lat, huerfanos = emparejar(leer_eventos(origen, "pulsador_local"), leer_eventos(destino, "led_digital"))
    ok = [round(x) for x in lat] == [100, 120, 200] and huerfanos == 1
    print("Autoverificacion: " + ("OK" if ok else "FALLA {} {}".format(lat, huerfanos)))
    return ok


def main(argumentos):
    """Punto de entrada."""
    if "--prueba" in argumentos:
        return 0 if autoverificar() else 1
    if len(argumentos) != 2:
        print(__doc__)
        return 2
    with open(argumentos[0], encoding="utf-8", errors="replace") as f:
        flancos = leer_eventos(f, "pulsador_local")
    with open(argumentos[1], encoding="utf-8", errors="replace") as f:
        cambios = leer_eventos(f, "led_digital")
    lat, huerfanos = emparejar(flancos, cambios)
    r = resumen(lat)
    print("Flancos en el origen: {} · cambios del LED en el destino: {} · sin pareja: {}".format(
        len(flancos), len(cambios), huerfanos))
    if r is None:
        print("No hay pares: revisar que los registros sean de la misma prueba y los relojes esten sincronizados.")
        return 1
    print("Latencia pulsador -> LED (ms): n={n}  min={min:.1f}  media={media:.1f}  "
          "mediana={mediana:.1f}  p95={p95:.1f}  max={max:.1f}".format(**r))
    if r["min"] < 0:
        print("ATENCION: latencias negativas = relojes desincronizados")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
