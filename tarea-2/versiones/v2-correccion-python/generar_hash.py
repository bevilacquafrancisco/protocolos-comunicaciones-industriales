#!/usr/bin/env python3
"""
generar_hash.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-20
Version: 1.0

Descripcion general
-------------------
Genera el hash de la clave del usuario OPC UA (consigna 4.9). El servidor
guarda solo este hash, nunca la clave.

scrypt con N = 2^17, r = 8, p = 1 (minimos recomendados por OWASP para
almacenar contrasenas) y sal aleatoria de 16 bytes. Formato de salida:

    scrypt:N:r:p:sal_hex:hash_hex

Sin '$' a proposito: no lo interpreta la shell al ponerlo en un archivo de
entorno.

Uso
---
    python generar_hash.py      # pide la clave dos veces, sin mostrarla

Dependencias externas
---------------------
Ninguna. Solo biblioteca estandar de Python 3.
"""

import getpass
import hashlib
import secrets
import sys

N, R, P = 2 ** 17, 8, 1
MEMORIA_MAX = 256 * 1024 * 1024   # scrypt con N=2^17 usa 128 MiB
LARGO_MINIMO = 12


def main():
    clave = getpass.getpass("Clave del usuario OPC UA: ")   # no queda en el historial
    if len(clave) < LARGO_MINIMO:
        sys.exit(f"La clave debe tener al menos {LARGO_MINIMO} caracteres.")
    if getpass.getpass("Repetir la clave: ") != clave:
        sys.exit("Las claves no coinciden.")
    sal = secrets.token_bytes(16)
    resumen = hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=N, r=R, p=P, maxmem=MEMORIA_MAX)
    print(f"scrypt:{N}:{R}:{P}:{sal.hex()}:{resumen.hex()}")


if __name__ == "__main__":
    main()
