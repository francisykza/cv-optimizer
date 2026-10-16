<#
.SYNOPSIS
  Crea en el escritorio el acceso directo "Buscador de empleo".

.DESCRIPTION
  Un doble clic ejecuta `python -m hunter open` con el entorno virtual de hunter/.venv (pythonw.exe,
  sin ventana de consola): arranca la API local si no está encendida, lanza una búsqueda si la última
  tiene más de 12 horas y abre el Buscador en el navegador, ya conectado. La API se apaga sola un rato
  después de cerrar el Buscador (HUNTER_IDLE_MINUTES, 30 por defecto).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File hunter\scripts\crear_acceso_directo.ps1
  powershell -ExecutionPolicy Bypass -File hunter\scripts\crear_acceso_directo.ps1 -Quitar
#>
param(
    [switch]$Quitar
)

$ErrorActionPreference = "Stop"
$hunterDir = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $hunterDir ".venv\Scripts\pythonw.exe"
$icono = Join-Path $hunterDir "assets\buscador.ico"
$escritorio = [Environment]::GetFolderPath("Desktop")
$acceso = Join-Path $escritorio "Buscador de empleo.lnk"

if ($Quitar) {
    if (Test-Path $acceso) {
        Remove-Item $acceso
        Write-Host "Quitado: $acceso"
    } else {
        Write-Host "No había ningún acceso directo en $escritorio."
    }
    exit 0
}

if (-not (Test-Path $pythonw)) {
    throw "No encuentro $pythonw. Instala antes el hunter (ver hunter\README.md)."
}
if (-not (Test-Path (Join-Path $hunterDir ".env"))) {
    throw "Falta hunter\.env. Ejecuta antes: .venv\Scripts\python -m hunter init"
}

$shell = New-Object -ComObject WScript.Shell
$enlace = $shell.CreateShortcut($acceso)
$enlace.TargetPath = $pythonw
$enlace.Arguments = "-m hunter open"
$enlace.WorkingDirectory = $hunterDir
$enlace.IconLocation = "$icono,0"
$enlace.Description = "Abre el Buscador de empleo (enciende su API local si hace falta)"
$enlace.Save()

Write-Host "Creado: $acceso"
Write-Host "Doble clic para abrir el Buscador. Para quitarlo: powershell -ExecutionPolicy Bypass -File hunter\scripts\crear_acceso_directo.ps1 -Quitar"
