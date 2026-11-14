#!/usr/bin/env bash
# =============================================================================
# inyectar-fallas.sh — Tarea 3 · F7 · consigna 4 (plan de pruebas N4, F-01 a F-10)
# Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-14 · v1.0
#
# Menu para provocar cada falla de forma REPETIBLE, en el ensayo y en la demo.
#
#   MODO=pc     (por defecto) banco virtual: la cadena completa en esta PC, sin hardware
#               (tools/banco_virtual.js levantar). Las fallas se provocan por software.
#   MODO=banco  hardware real. Lo fisico se pide al operador (desenchufar, cerrar la pestana);
#               lo de software se ejecuta (ssh a la Raspberry, kill del Edge Node, interfaz de red).
#
# Uso:
#   scripts/inyectar-fallas.sh                    menu interactivo
#   scripts/inyectar-fallas.sh levantar           (MODO=pc) levanta la cadena virtual
#   scripts/inyectar-fallas.sh F-04               inyecta una falla
#   scripts/inyectar-fallas.sh F-04 restaurar     la quita
#   scripts/inyectar-fallas.sh bajar              (MODO=pc) termina la cadena virtual
#
# Variables (MODO=banco):
#   RPI_SSH   usuario@ip de la Raspberry Pi (dispositivo 2), p. ej. pi@192.168.10.1
#   IFACE     interfaz del dispositivo 3 hacia internet (F-06): "Wi-Fi" en Windows, wlan0 en Linux
#   T3_ENV    .env del dispositivo 3 (por defecto tarea-3/.env)
#
# Se ejecuta desde cualquier carpeta; en Windows, con Git Bash.
# =============================================================================
set -euo pipefail

T3="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODO="${MODO:-pc}"
RUN="$T3/.banco"
CMD="$RUN/cmd"
GW="$T3/gateway-sparkplug"
if [ -x "$GW/.venv/bin/python" ]; then PY="$GW/.venv/bin/python"; else PY="$GW/.venv/Scripts/python.exe"; fi
T3_ENV="${T3_ENV:-$T3/.env}"

case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WINDOWS=1 ;; *) WINDOWS=0 ;; esac

# Termina sin aviso (kill -9) los procesos cuya linea de comandos contiene el patron. En Windows
# (Git Bash no trae pkill) se hace con PowerShell sobre la linea de comandos de cada proceso.
matar_proc() {
    if [ "$WINDOWS" = 1 ]; then
        powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match '$1' -and \$_.CommandLine -notmatch 'CimInstance' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
    else
        pkill -9 -f "$1" || true
    fi
}

# Baja o sube la interfaz de red del dispositivo 3 (F-06). Requiere administrador.
interfaz() {   # interfaz down|up
    if [ "$WINDOWS" = 1 ]; then
        local verbo; [ "$1" = down ] && verbo=Disable-NetAdapter || verbo=Enable-NetAdapter
        powershell.exe -NoProfile -Command "$verbo -Name '$IFACE' -Confirm:\$false"
    else
        sudo ip link set "$IFACE" "$1"
    fi
}

pausa()   { printf '\n  >> %s\n' "$*"; }
paso()    { printf '  [%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
manual()  { printf '\n  *** ACCION MANUAL ***\n  %s\n' "$*"; if [ -t 0 ]; then read -r -p "  (Enter cuando este hecho) " _; fi; }
confirmar() { if [ -t 0 ]; then read -r -p "  $* [s/N] " r; [ "$r" = "s" ]; else return 0; fi; }

# ----------------------------------------------------------------------------- banco virtual
enviar() {   # escribe un comando al proceso tools/banco_virtual.js levantar
    [ -f "$CMD" ] || { echo "la cadena virtual no esta levantada: $0 levantar"; exit 1; }
    echo "$*" >> "$CMD"
    paso "-> $*"
}

levantar() {
    mkdir -p "$RUN"
    : > "$CMD"
    paso "levantando la cadena virtual (simulador, Node-RED, OPC UA, Edge Node, broker, web)..."
    # El proceso queda en segundo plano SIN heredar la entrada ni la salida del script: si las heredara,
    # quien leyera la salida de este script (una tuberia, otro script) esperaria un EOF que nunca llega.
    ( tail -n 0 -f "$CMD" 2>/dev/null | node "$T3/tools/banco_virtual.js" levantar --salida "$RUN/corrida" > "$RUN/banco.log" 2>&1 & ) \
        < /dev/null > /dev/null 2>&1
    for _ in $(seq 1 180); do
        if grep -q "CADENA LISTA" "$RUN/banco.log" 2>/dev/null; then
            grep "CADENA LISTA" "$RUN/banco.log" | sed 's/^/  /'
            echo "  Abrir la web en el navegador. Registro: $RUN/banco.log"
            return 0
        fi
        sleep 1
    done
    echo "  no levanto en 180 s: ver $RUN/banco.log"; exit 1
}

bajar() { enviar bajar; sleep 3; rm -f "$CMD"; paso "cadena virtual terminada"; }

# ----------------------------------------------------------------------------- fallas
# Cada falla: f_<id> inyectar|restaurar. Lo esperado sale del plan de pruebas N4.

f_F01() {   # el esclavo no responde
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar sim falla silencio; else manual "Desenchufar la alimentacion del ESP32 #1."; fi
        pausa "Esperado: ~2 s (ausencia sostenida, ADR-014) -> MODBUS = DEVICE NOT REACHED, TIMEOUT sube, DDEATH; la web marca el dispositivo OBSOLETO."
    else
        if [ "$MODO" = pc ]; then enviar sim falla ninguna; else manual "Volver a enchufar el ESP32 #1."; fi
        pausa "Esperado: DBIRTH nuevo y la web EN LINEA sola (medido en la PC: 0,5 s)."
    fi
}

f_F02() {   # error de CRC
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar sim falla crc 0.3
        else manual "Provocar ruido en el par A/B (p. ej. tocar brevemente A y B con un cable largo suelto). Puede dar TIMEOUT en vez de CRC ERROR: el modo pc lo reproduce exacto."; fi
        pausa "Esperado: MODBUS = CRC ERROR (amarillo), contador CRC_ERROR sube, el sondeo continua."
    else
        if [ "$MODO" = pc ]; then enviar sim falla ninguna; else manual "Quitar la fuente de ruido."; fi
        pausa "Esperado: MODBUS = DONE; CRC_ERROR queda como registro historico."
    fi
}

f_F03() {   # Unit ID equivocado (siempre desde el Dashboard: es lo que se evalua, I-04)
    local url="http://127.0.0.1:1880/dashboard/configuracion"
    [ "$MODO" = banco ] && url="http://127.0.0.1:1880/dashboard/configuracion (por tunel SSH: ssh -L 1880:127.0.0.1:1880 \$RPI_SSH)"
    if [ "$1" = inyectar ]; then
        manual "En $url, panel Enlace: Unit ID = 7 -> 'Aplicar sin reiniciar'."
        pausa "Esperado: DEVICE NOT REACHED y DDEATH."
    else
        manual "En el mismo panel: Unit ID = 1 -> 'Aplicar sin reiniciar'."
        pausa "Esperado: la comunicacion vuelve SIN reiniciar nada: DBIRTH."
    fi
}

f_F04() {   # cae el servidor OPC UA
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar matar nodered
        else : "${RPI_SSH:?definir RPI_SSH=usuario@ip}"; ssh -t "$RPI_SSH" sudo systemctl stop pdci-t3-nodered; fi
        pausa "Esperado: OPC UA = ERROR, MODBUS = SIN DATOS (no un DONE viejo), DDEATH."
    else
        if [ "$MODO" = pc ]; then enviar iniciar nodered; else ssh -t "$RPI_SSH" sudo systemctl start pdci-t3-nodered; fi
        pausa "Esperado: el cliente reconecta solo (retroceso 1-30 s), OPC UA = DONE, DBIRTH."
    fi
}

f_F05() {   # cae el Edge Node
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar matar edge; else matar_proc sparkplug_edge_node.py; paso "kill -9 del Edge Node"; fi
        pausa "Esperado: el BROKER publica el NDEATH (Will) al instante; la web: NODO OBSOLETO."
    else
        if [ "$MODO" = pc ]; then enviar iniciar edge
        else nohup "$PY" "$GW/src/sparkplug_edge_node.py" --env "$T3_ENV" > "$GW/logs/edge-node.out" 2>&1 & paso "Edge Node reiniciado (PID $!)"; fi
        pausa "Esperado: bdSeq + 1, NBIRTH con seq = 0, DBIRTH, web EN LINEA sin tocarla."
    fi
}

f_F06() {   # se corta internet en el dispositivo 3
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar proxy cortar
        else : "${IFACE:?definir IFACE (p. ej. Wi-Fi en Windows, wlan0 en Linux)}"
            confirmar "Se baja la interfaz $IFACE de ESTA maquina (si es la del SSH, se pierde la sesion). ¿Seguir?" || return 0
            interfaz down; fi
        pausa "Esperado: ~15 s (keepalive 10 s x 1,5) -> el broker publica el NDEATH; la web: NODO OBSOLETO."
    else
        if [ "$MODO" = pc ]; then enviar proxy restaurar; else interfaz up; fi
        pausa "Esperado: reconexion sola: bdSeq + 1, Reconexiones + 1, NBIRTH, DBIRTH, web EN LINEA."
    fi
}

f_F07() {   # mensajes perdidos: salto de seq desde un Edge de prueba
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar saltar-seq
        else
            matar_proc sparkplug_edge_node.py
            ( sleep 8; echo saltar; sleep 3600 ) | "$PY" "$GW/tools/fake_edge_node.py" --env "$T3_ENV" > "$GW/logs/fake.out" 2>&1 &
            paso "Edge de prueba lanzado; salta un seq a los 8 s"
        fi
        pausa "Esperado (a los ~8 s): la web avisa 'Salto de seq', publica NCMD Rebirth (contador + 1) y llega un NBIRTH."
    else
        if [ "$MODO" = pc ]; then enviar volver-edge
        else matar_proc fake_edge_node.py; f_F05 restaurar; fi
    fi
}

f_F08() {   # se cae la Host Application
    if [ "$1" = inyectar ]; then
        manual "Cerrar la pestana de la web (o matar el navegador)."
        pausa "Esperado: spBv1.0/STATE/HA01_WebDashboard = {online: false} RETENIDO (verlo en MQTT Explorer)."
    else
        manual "Volver a abrir la web."
        pausa "Esperado: STATE online, la web pide Rebirth y se reconstruye sola."
    fi
}

f_F09() {   # credenciales invalidas
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then
            manual "Abrir la web con /mala/ al final de la URL (la sirve con una clave incorrecta): ver la URL en $RUN/banco.log."
        else
            manual "Cambiar la clave en hmi-web/config.js y recargar la web."
        fi
        pausa "Esperado: semaforo MQTT = CREDENCIALES RECHAZADAS y aviso (no un fallo silencioso)."
    else
        [ "$MODO" = banco ] && manual "Restaurar la clave en hmi-web/config.js y recargar."
        true
    fi
}

f_F10() {   # esclavo desconocido
    if [ "$1" = inyectar ]; then
        if [ "$MODO" = pc ]; then enviar iniciar desconocido; else manual "Conectar el ESP32 #2 (perfil DESCONOCIDO) en lugar del #1."; fi
        pausa "Esperado: el maestro no comunica (DDEATH). Cronometro: menos de 3 min hasta comunicar."
        manual "En el Dashboard: Descubrimiento -> 'Descubrir esclavo' -> 'Aplicar' en el hallazgo."
        pausa "Esperado: MODBUS = DONE con el esclavo nuevo, sin recompilar ni reiniciar (medido en la PC: 4,1 s)."
    else
        if [ "$MODO" = pc ]; then enviar iniciar sim; else manual "Volver a conectar el ESP32 #1."; fi
        manual "En el Dashboard, panel Enlace: volver a 9600 8N1, Unit ID 1 (en modo pc, Medio TCP 127.0.0.1:5020) -> Aplicar."
    fi
}

# ----------------------------------------------------------------------------- menu
DESCR=(
  "F-01 El esclavo MODBus no responde"
  "F-02 Error de CRC"
  "F-03 Unit ID equivocado (Dashboard)"
  "F-04 Se cae el servidor OPC UA"
  "F-05 Se cae el Edge Node (kill)"
  "F-06 Se corta internet en el dispositivo 3"
  "F-07 Mensajes perdidos (salto de seq)"
  "F-08 Se cae la Host Application"
  "F-09 Credenciales MQTT invalidas"
  "F-10 Esclavo desconocido de la catedra"
)

ejecutar() {   # ejecutar F-0X inyectar|restaurar
    local id="${1/-/}"
    declare -F "f_$id" > /dev/null || { echo "falla desconocida: $1"; exit 2; }
    "f_$id" "${2:-inyectar}"
}

menu() {
    while true; do
        printf '\n=== Inyeccion de fallas · MODO=%s ===\n' "$MODO"
        [ "$MODO" = pc ] && echo "  0) levantar la cadena virtual        b) bajarla"
        for i in "${!DESCR[@]}"; do printf '  %2d) %s\n' "$((i + 1))" "${DESCR[$i]}"; done
        echo "  q) salir"
        read -r -p "Opcion: " op
        case "$op" in
            q) exit 0 ;;
            0) levantar ;;
            b) bajar ;;
            [1-9]|10)
                local id; id="$(printf 'F-%02d' "$op")"
                ejecutar "$id" inyectar
                read -r -p "  Enter para RESTAURAR (o 'n' para dejar la falla): " r
                [ "$r" = n ] || ejecutar "$id" restaurar ;;
            *) echo "opcion invalida" ;;
        esac
    done
}

case "${1:-}" in
    "") menu ;;
    levantar) levantar ;;
    bajar) bajar ;;
    F-*) ejecutar "$1" "${2:-inyectar}" ;;
    *) echo "uso: $0 [levantar|bajar|F-0X [restaurar]]"; exit 2 ;;
esac
