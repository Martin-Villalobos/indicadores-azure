#!/usr/bin/env bash
# Envía Reporte 1.117 y Velocidades desde el espejo FTP local al blob "cargas" de Azure.
# Sigue la misma lógica que copyToServer.sh: los archivos del espejo NO se mueven ni
# se borran (lftp los volvería a bajar); se anota en un registro local qué ya se subió.
#
# Requisitos (una vez):
#   - rclone instalado y el remoto "azcargas" creado con un SAS de lectura y escritura sin borrado (racwl)
#     (ver docs/DESPLIEGUE.md, paso 5).
# Programar con cron cada 5 minutos, por ejemplo:
#   */5 * * * * /opt/indicadores-azure/subir_archivos.sh >> /var/log/subir_azure.log 2>&1
set -euo pipefail

# ===== Configuración =====
ESPEJO_SONDA=${ESPEJO_SONDA:-/data/ftpmirror/sonda/OUT}
ESPEJO_DTPM=${ESPEJO_DTPM:-/data/ftpmirror/dtpm}
REMOTO=${REMOTO:-azcargas:cargas}
RCLONE=${RCLONE:-rclone}
ESTADO_DIR=${ESTADO_DIR:-$HOME/.subir_azure}   # registros de lo ya subido
# Sólo se consideran archivos modificados desde esta fecha (evita subir años de historia
# en la primera corrida).
DESDE=${DESDE:-2026-11-01}
# Minutos sin cambios antes de subir un archivo (por si lftp todavía lo está bajando).
MIN_EDAD=${MIN_EDAD:-2}
# =========================

mkdir -p "$ESTADO_DIR"
exec 9>"$ESTADO_DIR/lock"
flock -n 9 || { echo "$(date '+%F %T') Otra ejecución sigue corriendo; se omite."; exit 0; }

log() { echo "$(date '+%F %T') $*"; }

# candidatos RAIZ [condiciones de find...] -> rutas relativas a RAIZ, una por línea
candidatos() {
  local raiz=$1; shift
  [ -d "$raiz" ] || return 0
  (cd "$raiz" && find . -type f -mmin +"$MIN_EDAD" -newermt "$DESDE" "$@" -printf '%P\n')
}

# subir NOMBRE RAIZ TIPO  (lee de stdin las rutas candidatas, relativas a RAIZ)
subir() {
  local nombre=$1 raiz=$2 tipo=$3
  local registro="$ESTADO_DIR/$nombre.subidos" lista
  touch "$registro"
  lista=$(mktemp)
  sort -u | comm -23 - <(sort -u "$registro") > "$lista"
  if [ -s "$lista" ]; then
    log "$nombre: $(wc -l < "$lista") archivo(s) nuevo(s)"
    if "$RCLONE" copy "$raiz" "$REMOTO/$tipo/entrada" --files-from-raw "$lista" \
         --no-traverse --no-check-dest --log-level INFO; then
      cat "$lista" >> "$registro"
    else
      log "$nombre: rclone falló; se reintenta en la próxima ejecución"
    fi
  fi
  rm -f "$lista"
}

log "Inicio"

# --- Reporte 1.117: zips ---
candidatos "$ESPEJO_SONDA/Reporte_1.117" -name '*.zip' \
  | subir r117 "$ESPEJO_SONDA/Reporte_1.117" reporte117

# --- Velocidades ---
VEL="$ESPEJO_DTPM/VELOCIDADES"
# Fuera de línea (definitivos): todos los .xlsx bajo carpetas *OFF*
candidatos "$VEL" -path '*OFF*' -name '*.xlsx' \
  | subir velocidades_off "$VEL" velocidades
# En línea: sólo si todavía no existe la versión fuera de línea con el mismo nombre
offline=$(mktemp)
candidatos "$VEL" -path '*OFF*' -name '*.xlsx' | awk -F/ '{print $NF}' | sort -u > "$offline"
candidatos "$VEL" -path '*ON*' -not -path '*OFF*' -name '*.xlsx' \
  | awk -F/ 'NR==FNR {off[$0]; next} !($NF in off)' "$offline" - \
  | subir velocidades_on "$VEL" velocidades
rm -f "$offline"

log "Fin"
