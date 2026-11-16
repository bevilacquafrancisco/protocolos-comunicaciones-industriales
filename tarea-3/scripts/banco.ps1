<#
banco.ps1 - Puesta en marcha rapida del banco desde la notebook (dispositivo 3)
Autores: Bevilacqua Francisco, Peralta Agustina - 2026-11-16 - v1.0 (ADR-029)

Todo lo que habla con la Raspberry va por el CABLE Ethernet (192.168.10.1), no por la
Wi-Fi: el banco funciona igual en la red de casa, la del laboratorio o la del celular. La
Wi-Fi solo le da internet a la notebook (Edge Node -> broker en la nube).

Uso (PowerShell, en tarea-3):
    powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 verificar
    powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 hora
    powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 iniciar [-Observador]
    powershell -ExecutionPolicy Bypass -File scripts\banco.ps1 web

  verificar  cable, OPC UA, SSH, servicio de Node-RED, hora de la Raspberry, internet al broker
  hora       pone la hora de la Raspberry igual a la de la notebook (pide la clave de sudo una vez)
  iniciar    abre una ventana por proceso: Edge Node, tunel SSH al Dashboard y, con -Observador,
             el observador Sparkplug archivando en docs\capturas\banco\
  web        sirve la Host Application en la LAN (solo si no se usa GitHub Pages)

Variables opcionales: PDCI_RPI (por defecto pdci@192.168.10.1), PDCI_HMI_URL (enlace publico).
Sin tildes en este archivo: Windows PowerShell 5.1 lee los .ps1 sin BOM como ANSI.
#>
param(
    [ValidateSet('verificar', 'hora', 'iniciar', 'web', 'ayuda')]
    [string]$Accion = 'ayuda',
    [switch]$Observador
)

$ErrorActionPreference = 'Stop'
$T3 = Split-Path $PSScriptRoot -Parent
$GW = Join-Path $T3 'gateway-sparkplug'
$RPI = if ($env:PDCI_RPI) { $env:PDCI_RPI } else { 'pdci@192.168.10.1' }
$IP_RPI = ($RPI -split '@')[-1]

function Fila([string]$que, [bool]$ok, [string]$detalle) {
    $marca = if ($ok) { '[ OK ]' } else { '[FALLA]' }
    $color = if ($ok) { 'Green' } else { 'Red' }
    Write-Host ('{0} {1,-34} {2}' -f $marca, $que, $detalle) -ForegroundColor $color
}

function LeerEnv([string]$clave) {
    $archivo = Join-Path $T3 '.env'
    if (-not (Test-Path $archivo)) { return $null }
    $linea = Get-Content $archivo | Where-Object { $_ -match "^$clave=" } | Select-Object -First 1
    if ($linea) { return ($linea -split '=', 2)[1].Trim() }
    return $null
}

function DesfaseMs {
    # Hora de la Raspberry (ms UTC) menos la de la notebook. Incluye la mitad del ida y vuelta SSH.
    $antes = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $rpi = ssh -o BatchMode=yes -o ConnectTimeout=5 $RPI 'date +%s%3N'
    if ($LASTEXITCODE -ne 0) { throw 'sin SSH' }
    $despues = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    return [long]$rpi - [long](($antes + $despues) / 2)
}

function Verificar {
    Write-Host "Banco PdCI T3 - verificacion (Raspberry: $RPI)" -ForegroundColor Cyan
    # La ruta a la Raspberry TIENE que salir por la placa Ethernet: si la notebook perdio su IP
    # fija, el paquete sale por la Wi-Fi y puede contestar otro equipo con la misma direccion.
    $ruta = Find-NetRoute -RemoteIPAddress $IP_RPI -ErrorAction SilentlyContinue | Select-Object -First 1
    $ipLocal = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $ruta.InterfaceIndex -ErrorAction SilentlyContinue).IPAddress
    $porCable = $ipLocal -contains '192.168.10.2'
    Fila 'IP fija 192.168.10.2 en el cable' $porCable $(if ($porCable) { "interfaz $($ruta.InterfaceAlias)" } else { 'falta: New-NetIPAddress (guia de arranque, paso 1.2)' })
    if (-not $porCable) { Write-Host '  Sin la IP fija, lo que sigue no prueba nada: se corta aca.' -ForegroundColor Yellow; return }
    $ping = Test-Connection -ComputerName $IP_RPI -Count 1 -Quiet
    Fila 'Cable Ethernet (ping)' $ping $(if ($ping) { $IP_RPI } else { 'cable desconectado o Raspberry apagada' })
    $opc = (Test-NetConnection -ComputerName $IP_RPI -Port 4840 -WarningAction SilentlyContinue).TcpTestSucceeded
    Fila 'Servidor OPC UA (4840)' $opc $(if ($opc) { 'escuchando' } else { 'servicio detenido o firewall de la Raspberry' })
    $estado = ssh -o BatchMode=yes -o ConnectTimeout=5 $RPI 'systemctl is-active pdci-t3-nodered'
    if ($LASTEXITCODE -eq 0 -or $estado) {
        Fila 'SSH por el cable + servicio' ($estado -eq 'active') "pdci-t3-nodered: $estado"
        try {
            $d = DesfaseMs
            Fila 'Hora de la Raspberry' ([math]::Abs($d) -lt 1000) "desfase $d ms (si falla: banco.ps1 hora)"
        } catch { Fila 'Hora de la Raspberry' $false 'no se pudo leer' }
    } else {
        Fila 'SSH por el cable' $false 'falta la regla de ufw para eth0 o la clave SSH (guia de arranque, paso 1.3)'
    }
    $broker = LeerEnv 'MQTT_HOST'
    if ($broker) {
        $net = (Test-NetConnection -ComputerName $broker -Port 8883 -WarningAction SilentlyContinue).TcpTestSucceeded
        Fila 'Internet hacia el broker (8883)' $net $(if ($net) { $broker } else { 'sin internet en esta Wi-Fi o puerto bloqueado: usar el celular' })
    } else {
        Fila 'Archivo tarea-3\.env' $false 'falta .env o MQTT_HOST'
    }
    Fila 'Entorno de Python (venv)' (Test-Path (Join-Path $GW '.venv\Scripts\python.exe')) $GW
}

function Hora {
    $d = DesfaseMs
    Write-Host "Desfase actual: $d ms"
    if ([math]::Abs($d) -lt 1000) { Write-Host 'La hora de la Raspberry ya esta bien.' -ForegroundColor Green; return }
    $epoch = '{0:F3}' -f ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0)
    $epoch = $epoch.Replace(',', '.')
    Write-Host 'Se pone la hora de la notebook en la Raspberry (pide la clave de sudo de pdci):'
    ssh -t $RPI "sudo date -u -s @$epoch"
    Write-Host ("Desfase despues: {0} ms" -f (DesfaseMs))
}

function Ventana([string]$titulo, [string]$carpeta, [string]$comando) {
    $script = "`$host.UI.RawUI.WindowTitle = '$titulo'; Set-Location -LiteralPath '$carpeta'; $comando"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $script | Out-Null
    Write-Host "  abierta: $titulo"
}

function Iniciar {
    Write-Host 'Abriendo ventanas (cerrar el Edge Node siempre con Ctrl+C: publica el NDEATH):' -ForegroundColor Cyan
    Ventana 'PdCI - Edge Node' $GW '.\.venv\Scripts\python src\sparkplug_edge_node.py'
    Ventana 'PdCI - Tunel al Dashboard' $T3 "ssh -o ServerAliveInterval=15 -N -L 1880:127.0.0.1:1880 $RPI"
    if ($Observador) {
        $salida = Join-Path $T3 ('docs\capturas\banco\sparkplug-{0}.jsonl' -f (Get-Date -Format 'yyyyMMdd-HHmm'))
        New-Item -ItemType Directory -Force (Split-Path $salida) | Out-Null
        Ventana 'PdCI - Observador Sparkplug' $GW ".\.venv\Scripts\python tools\observador_sparkplug.py --salida '$salida'"
    }
    Write-Host ''
    Write-Host 'Dashboard de Node-RED:  http://localhost:1880/dashboard'
    $hmi = if ($env:PDCI_HMI_URL) { $env:PDCI_HMI_URL } else { 'https://<usuario>.github.io/<repositorio>/  (o: banco.ps1 web)' }
    Write-Host "Host Application:       $hmi"
}

function Web {
    Ventana 'PdCI - Host Application (LAN)' (Join-Path $T3 'hmi-web') 'node tools\servir.js --lan'
}

switch ($Accion) {
    'verificar' { Verificar }
    'hora' { Hora }
    'iniciar' { Iniciar }
    'web' { Web }
    default { Get-Help $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue; Write-Host 'Acciones: verificar | hora | iniciar [-Observador] | web' }
}
