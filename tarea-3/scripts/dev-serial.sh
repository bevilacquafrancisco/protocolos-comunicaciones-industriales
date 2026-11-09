#!/usr/bin/env bash
# =============================================================================
# dev-serial.sh
# Autores: Bevilacqua Francisco, Peralta Agustina
# Fecha de creacion: 2026-11-09
# Version: 1.0
#
# Descripcion
# -----------
# Entorno serie de desarrollo SIN hardware (Linux o Raspberry Pi): crea un par de
# puertos serie virtuales con socat y arranca el simulador del esclavo en uno de los
# extremos. Node-RED se conecta al otro extremo como si fuera el conversor USB-RS485.
#
#     /tmp/pdci-maestro  <== socat ==>  /tmp/pdci-esclavo
#        (Node-RED)                      (simulador con el stack del ESP32)
#
# LIMITACION IMPORTANTE: un pty de socat IGNORA el baud rate y la paridad (no hay UART
# real: los bytes pasan igual con cualquier configuracion). Sirve para probar el maestro
# por el camino REAL de node-red-node-serialport, pero NO para el asistente de
# descubrimiento: con pty encontraria al esclavo en cualquier combinacion. Para el
# descubrimiento usar el medio TCP (el simulador emula el desajuste de linea) o el
# conversor USB-RS485 real con el ESP32 #2.
#
# Uso
# ---
#     ./tarea-3/scripts/dev-serial.sh                     # esclavo del dispositivo 1
#     ./tarea-3/scripts/dev-serial.sh desconocido         # esclavo desconocido (ADR-007)
#     ./tarea-3/scripts/dev-serial.sh dispositivo --falla crc --prob 0.2
# Despues, en el Dashboard (Configuracion MODBus): Medio = Puerto serie,
# Puerto = /tmp/pdci-maestro, y "Aplicar sin reiniciar".
#
# Dependencias: socat (sudo apt install socat), Python 3 con pyserial
# (pip install pyserial). Ctrl+C detiene el simulador y el par de pty.
# =============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAESTRO=/tmp/pdci-maestro
ESCLAVO=/tmp/pdci-esclavo
PERFIL="${1:-dispositivo}"
shift || true

command -v socat >/dev/null || { echo "Falta socat: sudo apt install socat" >&2; exit 1; }
python3 -c "import serial" 2>/dev/null || { echo "Falta pyserial: pip install pyserial" >&2; exit 1; }

case "$PERFIL" in
    dispositivo) SIM="$DIR/simuladores/esclavo_modbus_sim.py" ;;
    desconocido) SIM="$DIR/simuladores/esclavo_desconocido_sim.py" ;;
    *) echo "Perfil desconocido: $PERFIL (dispositivo | desconocido)" >&2; exit 1 ;;
esac

# raw: sin procesamiento de linea (los bytes MODBus pueden valer 0x0A, 0x03...);
# echo=0: un puerto serie no devuelve lo que se le escribe.
socat -d -d "pty,raw,echo=0,link=$MAESTRO" "pty,raw,echo=0,link=$ESCLAVO" &
PID_SOCAT=$!
trap 'kill $PID_SOCAT 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do [ -e "$ESCLAVO" ] && break; sleep 0.1; done
[ -e "$ESCLAVO" ] || { echo "socat no creo $ESCLAVO" >&2; exit 1; }

echo "Par serie listo: Node-RED -> $MAESTRO   simulador -> $ESCLAVO"
exec python3 -u "$SIM" --serie "$ESCLAVO" "$@"
