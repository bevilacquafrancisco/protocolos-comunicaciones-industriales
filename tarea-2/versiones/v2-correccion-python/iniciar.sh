#!/usr/bin/env bash
# =============================================================================
# iniciar.sh
# Autores: Bevilacqua Francisco, Peralta Agustina
# Fecha de creacion: 2026-10-20 · Version: 1.0
#
# Arranca un programa del trabajo con el entorno virtual y los secretos
# cargados, y guarda TODA la salida en registros/ (evidencia de las consignas
# 3.4, 3.5 y 3.6) sin dejar de mostrarla en pantalla.
#
# Uso:  ./iniciar.sh <programa.py> [opciones]
#   ./iniciar.sh servidor.py
#   ./iniciar.sh cliente_suscripcion.py --seguridad SignAndEncrypt
#
# Dependencias: ~/opcua-env (README §4) y, opcional, ~/.pdci-t2.env (README §6).
# =============================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Uso: $0 <programa.py> [opciones]" >&2
    exit 2
fi

cd "$(dirname "$0")"
set +u      # el script activate del venv no es compatible con nounset en todas las versiones
# shellcheck disable=SC1090
source ~/opcua-env/bin/activate
set -u

# Secretos fuera del repositorio, con permisos 600. set -a exporta las variables.
if [ -f ~/.pdci-t2.env ]; then
    set -a
    # shellcheck disable=SC1090
    . ~/.pdci-t2.env
    set +a
fi

mkdir -p registros
registro="registros/$(basename "$1" .py)_$(date +%Y%m%d_%H%M%S).log"
echo "Registro: $registro"
# tee -i ignora Ctrl+C: Python cierra la sesion OPC UA (CloseSession, CLO)
# y tee sigue escribiendo hasta la ultima linea.
python -u "$@" 2>&1 | tee -i "$registro"
