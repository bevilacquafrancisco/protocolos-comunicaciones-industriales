<#
.SYNOPSIS
    Copia una version del TP2 (v1 original o v2 correccion) a las Raspberry Pi por SSH/scp.

.DESCRIPTION
    Archivo:      herramientas/desplegar.ps1
    Autores:      Bevilacqua Francisco, Peralta Agustina
    Creacion:     2026-10-27 - Version 1.0

    Copia SOLO los programas. No toca pki/ (certificados y claves privadas), registros/ ni
    ~/.pdci-t2.env (secretos): esos se generan y quedan en cada placa.

      v1 -> ~/TP2_OPC_original   servidor_ns1.py, cliente.py, cliente_suscripcion_v2.py
      v2 -> ~/TP2_OPC            *.py, requirements.txt, iniciar.sh

    Requisitos: OpenSSH de Windows y los alias rpi1 / rpi2 en ~/.ssh/config
    (guia/02_cargar_programas_SSH.md, seccion 2). Sin dependencias externas.
    Se escribe en ASCII: PowerShell 5.1 lee los .ps1 sin BOM con la pagina de codigos ANSI.

.PARAMETER Version
    v1 (original de Agustina) o v2 (correccion, la que se presenta). Por defecto v2.

.PARAMETER Placa
    ambas, servidor o cliente. Por defecto ambas.

.PARAMETER Servidor
    Alias o usuario@host SSH de la RPi 1. Por defecto rpi1.

.PARAMETER Cliente
    Alias o usuario@host SSH de la RPi 2. Por defecto rpi2.

.PARAMETER Simular
    Muestra que se copiaria y a donde, sin conectarse a ninguna placa.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1
    powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1 -Version v1 -Placa servidor
    powershell -ExecutionPolicy Bypass -File herramientas\desplegar.ps1 -Servidor pi@192.168.43.20 -Simular
#>
[CmdletBinding()]
param(
    [ValidateSet('v1', 'v2')]
    [string]$Version = 'v2',

    [ValidateSet('ambas', 'servidor', 'cliente')]
    [string]$Placa = 'ambas',

    [string]$Servidor = 'rpi1',
    [string]$Cliente = 'rpi2',

    [switch]$Simular
)

$ErrorActionPreference = 'Stop'

# -----------------------------------------------------------------------------
# Que se copia de cada version (carpeta de origen en el repo y destino en la placa)
# -----------------------------------------------------------------------------
$raizRepo = Split-Path -Parent $PSScriptRoot
$versiones = @{
    'v1' = @{
        Origen  = Join-Path $raizRepo 'versiones\v1-original-agustina'
        Destino = 'TP2_OPC_original'
        # servidor.py (ns=2) NO se copia a proposito: deja el modelo en ns=2 y el cliente falla.
        Archivos = @('servidor_ns1.py', 'cliente.py', 'cliente_suscripcion_v2.py')
    }
    'v2' = @{
        Origen  = Join-Path $raizRepo 'versiones\v2-correccion-python'
        Destino = 'TP2_OPC'
        Archivos = $null   # se calcula abajo: todos los .py + requirements.txt + iniciar.sh
    }
}

$config = $versiones[$Version]
if (-not (Test-Path $config.Origen)) {
    throw "No existe la carpeta de origen: $($config.Origen)"
}

if ($null -eq $config.Archivos) {
    $config.Archivos = @(Get-ChildItem -Path $config.Origen -Filter '*.py' | ForEach-Object { $_.Name }) +
                       @('requirements.txt', 'iniciar.sh')
}

foreach ($archivo in $config.Archivos) {
    if (-not (Test-Path (Join-Path $config.Origen $archivo))) {
        throw "Falta el archivo $archivo en $($config.Origen)"
    }
}

$destinos = switch ($Placa) {
    'ambas'    { @($Servidor, $Cliente) }
    'servidor' { @($Servidor) }
    'cliente'  { @($Cliente) }
}

<#
.SYNOPSIS
    Ejecuta un comando nativo (ssh/scp) y corta el script si devuelve error.
.PARAMETER Programa
    [string] ssh o scp.
.PARAMETER Argumentos
    [string[]] argumentos, ya separados (PowerShell los cita si tienen espacios).
#>
function Invoke-Nativo {
    param([string]$Programa, [string[]]$Argumentos)
    Write-Host "  > $Programa $($Argumentos -join ' ')" -ForegroundColor DarkGray
    if ($Simular) { return }
    & $Programa @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "$Programa termino con codigo $LASTEXITCODE. Probar la conexion a mano: ssh $hostSsh"
    }
}

# -----------------------------------------------------------------------------
# Copia. Se trabaja desde la carpeta de origen y con nombres relativos: asi la ruta
# del repo (con espacios y la letra enie de "4to anio") nunca llega a scp.
# -----------------------------------------------------------------------------
Write-Host "Version $Version -> ~/$($config.Destino) en: $($destinos -join ', ')" -ForegroundColor Cyan
if ($Simular) { Write-Host "(simulacion: no se conecta a ninguna placa)" -ForegroundColor Yellow }

Push-Location $config.Origen
try {
    foreach ($hostSsh in $destinos) {
        Write-Host "[$hostSsh]" -ForegroundColor Cyan
        Invoke-Nativo 'ssh' @($hostSsh, "mkdir -p ~/$($config.Destino)")
        Invoke-Nativo 'scp' (@('-q') + $config.Archivos + @("$($hostSsh):$($config.Destino)/"))
        if ($Version -eq 'v2') {
            Invoke-Nativo 'ssh' @($hostSsh, "chmod +x ~/$($config.Destino)/iniciar.sh")
        }
        Invoke-Nativo 'ssh' @($hostSsh, "ls -l ~/$($config.Destino)")
    }
}
finally {
    Pop-Location
}

Write-Host "Listo. Siguiente paso: guia/02_cargar_programas_SSH.md, seccion 6." -ForegroundColor Green
