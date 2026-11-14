#!/usr/bin/env python3
"""
proxy_corte.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-11-12
Version: 1.0

Descripcion general
-------------------
Proxy TCP para simular la falla F-06 (se corta internet en el dispositivo 3) sin tocar la red de
la maquina. Se interpone entre el Edge Node y el broker:

    Edge Node --> 127.0.0.1:<escucha> --> proxy --> <destino host:puerto> (broker)

Comandos por la entrada estandar:
    cortar     las conexiones siguen ABIERTAS pero los bytes se descartan en los dos sentidos.
               Es un cable cortado o un router caido: nadie recibe FIN ni RST, y solo el keepalive
               MQTT (10 s; el broker espera 1,5 x 10 s = 15 s) detecta la perdida. Distinto de
               matar el proceso (F-05), donde el sistema operativo cierra el socket al instante.
               Las conexiones nuevas tampoco llegan al broker.
    restaurar  vuelve la red. Las conexiones "colgadas" se cierran: a esa altura los dos extremos ya
               las dieron por muertas, y reanudar un flujo TLS con bytes perdidos lo corromperia.
    estado     imprime el modo y las conexiones activas.

Uso:
    python tools/proxy_corte.py --escucha 18893 --destino 127.0.0.1:18883
    (y el Edge Node con MQTT_PUERTO_TLS=18893)

Para TLS el proxy es transparente: no descifra nada, solo reenvia bytes.
Dependencias externas: ninguna (asyncio).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time


class Proxy:
    """
    Atributos:
        cortado (bool): modo de corte silencioso.
        conexiones (set): pares (lector, escritor) activos, para cerrarlos al restaurar.
    """

    def __init__(self, destino_host: str, destino_puerto: int):
        self.destino = (destino_host, destino_puerto)
        self.cortado = False
        self.conexiones: set = set()

    async def _bombear(self, lector, escritor):
        """Copia bytes en un sentido; en modo corte, los lee y los descarta."""
        try:
            while True:
                datos = await lector.read(65536)
                if not datos:
                    break
                if not self.cortado:
                    escritor.write(datos)
                    await escritor.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            escritor.close()

    async def atender(self, lector_cli, escritor_cli):
        if self.cortado:
            # Sin ruta: se acepta y se deja colgado (el cliente vencera su espera del CONNACK).
            self.conexiones.add(escritor_cli)
            return
        try:
            lector_srv, escritor_srv = await asyncio.open_connection(*self.destino)
        except OSError:
            escritor_cli.close()
            return
        self.conexiones.update({escritor_cli, escritor_srv})
        await asyncio.gather(self._bombear(lector_cli, escritor_srv), self._bombear(lector_srv, escritor_cli))
        self.conexiones.difference_update({escritor_cli, escritor_srv})

    def cortar(self):
        self.cortado = True
        print(f"[PROXY] {time.time():.3f} CORTADO (corte silencioso: sin FIN ni RST)", flush=True)

    def restaurar(self):
        self.cortado = False
        for escritor in list(self.conexiones):
            try:
                escritor.transport.abort()          # RST: la sesion vieja ya estaba muerta
            except Exception:
                pass
        self.conexiones.clear()
        print(f"[PROXY] {time.time():.3f} RESTAURADO", flush=True)


def main():
    p = argparse.ArgumentParser(description="Proxy TCP con corte silencioso (falla F-06)")
    p.add_argument("--escucha", type=int, required=True)
    p.add_argument("--destino", required=True, help="host:puerto del broker")
    args = p.parse_args()
    host, puerto = args.destino.rsplit(":", 1)
    proxy = Proxy(host, int(puerto))

    async def principal():
        servidor = await asyncio.start_server(proxy.atender, "127.0.0.1", args.escucha)
        loop = asyncio.get_running_loop()

        def consola():
            for linea in sys.stdin:
                cmd = linea.strip()
                if cmd == "cortar":
                    loop.call_soon_threadsafe(proxy.cortar)
                elif cmd == "restaurar":
                    loop.call_soon_threadsafe(proxy.restaurar)
                elif cmd == "estado":
                    print(f"[PROXY] {'CORTADO' if proxy.cortado else 'normal'} · {len(proxy.conexiones)} conexiones", flush=True)

        threading.Thread(target=consola, daemon=True).start()
        print(f"[PROXY] 127.0.0.1:{args.escucha} -> {args.destino} LISTO", flush=True)
        async with servidor:
            await servidor.serve_forever()

    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
