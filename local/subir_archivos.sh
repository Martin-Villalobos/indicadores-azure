#!/usr/bin/env bash
# Envía Reporte 117 y Velocidades desde la máquina local al blob "cargas".
# Programar cada 5 minutos con cron:
#   */5 * * * * /ruta/subir_archivos.sh
#
# Requisito (una vez): rclone instalado y el remoto "azcargas" creado con un SAS
# de sólo escritura (ver docs/DESPLIEGUE.md, paso 5).
set -euo pipefail

# ===== Ajustar estas rutas =====
RUTA_117=/RUTA/REPORTE_117
RUTA_VELOCIDADES=/RUTA/VELOCIDADES
LOG="$(dirname "$0")/subir_archivos.log"
# ===============================

subir() {  # carpeta tipo patron
  [ -d "$1" ] || return 0
  rclone move "$1" "azcargas:cargas/$2/entrada" \
    --min-age 2m --no-traverse --no-check-dest --include "$3" \
    --log-file "$LOG" --log-level INFO
}

subir "$RUTA_117"         reporte117  "*.{zip,csv,xlsx,xls}"
subir "$RUTA_VELOCIDADES" velocidades "*.{xlsx,xls,csv}"
