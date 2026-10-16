<#
.SYNOPSIS
  Programa el Job Hunter en el Programador de tareas de Windows (dos búsquedas al día).

.DESCRIPTION
  Crea dos tareas para tu usuario que ejecutan `python -m hunter run --trigger scheduler`
  con el entorno virtual de hunter/.venv. Usa pythonw.exe para que no se abra ninguna ventana.
  Las tareas solo se ejecutan con tu sesión iniciada (no guardan tu contraseña).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File hunter\scripts\install_task.ps1
  powershell -ExecutionPolicy Bypass -File hunter\scripts\install_task.ps1 -Manana 09:00 -Tarde 19:00
  powershell -ExecutionPolicy Bypass -File hunter\scripts\install_task.ps1 -Quitar
#>
param(
    [string]$Manana = "08:30",
    [string]$Tarde = "18:30",
    [switch]$Quitar
)

$ErrorActionPreference = "Stop"
$hunterDir = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $hunterDir ".venv\Scripts\pythonw.exe"
$nombres = @("CV-Optimizer Hunter (manana)", "CV-Optimizer Hunter (tarde)")

if ($Quitar) {
    foreach ($nombre in $nombres) {
        schtasks /Delete /F /TN $nombre 2>$null | Out-Null
        Write-Host "Quitada: $nombre"
    }
    exit 0
}

if (-not (Test-Path $pythonw)) {
    throw "No encuentro $pythonw. Instala antes el hunter (ver hunter\README.md)."
}
if (-not (Test-Path (Join-Path $hunterDir ".env"))) {
    throw "Falta hunter\.env. Ejecuta antes: .venv\Scripts\python -m hunter init"
}

$accion = "`"$pythonw`" -m hunter run --trigger scheduler"
$horas = @($Manana, $Tarde)
for ($i = 0; $i -lt 2; $i++) {
    schtasks /Create /F /SC DAILY /ST $horas[$i] /TN $nombres[$i] /TR $accion | Out-Null
    Write-Host ("Programada: {0} a las {1}" -f $nombres[$i], $horas[$i])
}
Write-Host ""
Write-Host "Listo. Cada ejecución queda en %LOCALAPPDATA%\CV-Optimizer\hunter\logs\hunter.log y en 'python -m hunter jobs'."
Write-Host "Para quitarlas: powershell -ExecutionPolicy Bypass -File hunter\scripts\install_task.ps1 -Quitar"
