# Envía Reporte 117 y Velocidades desde la máquina local al blob "cargas".
# Programar cada 5 minutos con el Programador de tareas:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\ruta\subir_archivos.ps1
#
# Requisito (una vez): rclone instalado y el remoto "azcargas" creado con un SAS
# de sólo escritura (ver docs/DESPLIEGUE.md, paso 5).

$ErrorActionPreference = "Stop"

# ===== Ajustar estas rutas =====
$Origenes = @(
    @{ Carpeta = "C:\RUTA\REPORTE_117";   Tipo = "reporte117";  Incluir = "*.{zip,csv,xlsx,xls}" },
    @{ Carpeta = "C:\RUTA\VELOCIDADES";   Tipo = "velocidades"; Incluir = "*.{xlsx,xls,csv}" }
)
$Rclone = "rclone"
$Log    = Join-Path $PSScriptRoot "subir_archivos.log"
# ===============================

foreach ($o in $Origenes) {
    if (-not (Test-Path $o.Carpeta)) { continue }
    & $Rclone move $o.Carpeta "azcargas:cargas/$($o.Tipo)/entrada" `
        --min-age 2m --no-traverse --no-check-dest --include $o.Incluir `
        --log-file $Log --log-level INFO
    if ($LASTEXITCODE -ne 0) { Write-Error "rclone falló para $($o.Tipo) (código $LASTEXITCODE)" }
}
