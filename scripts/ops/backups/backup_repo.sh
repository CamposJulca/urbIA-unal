#!/usr/bin/env bash
#
# backup_repo.sh — Backup automatizado del repositorio urbIA-unal
#
# Origen:  /home/pruebas/urbIA-unal/ (git bundle --all)
# Destino: camposjulca@192.168.0.104:/mnt/storage/Neusi/urbia-backups/repo/
# Política: daily=7d, weekly=28d, monthly=92d
# Uso: ./backup_repo.sh [daily|weekly|monthly]   (default: daily)

set -euo pipefail

FREQ="${1:-daily}"
TS=$(date +%Y%m%d-%H%M%S)
REPO_DIR="/home/pruebas/urbIA-unal"
REMOTE_USER="camposjulca"
REMOTE_HOST="192.168.0.104"
REMOTE_BASE="/mnt/storage/Neusi/urbia-backups/repo"
STAGING="/home/pruebas/urbia-backups/staging"
LOG_DIR="/home/pruebas/urbia-backups/logs"
LOG_FILE="${LOG_DIR}/repo_${FREQ}_${TS}.log"

case "$FREQ" in
  daily)   RETAIN_DAYS=7  ;;
  weekly)  RETAIN_DAYS=28 ;;
  monthly) RETAIN_DAYS=92 ;;
  *) echo "ERROR: frecuencia debe ser daily|weekly|monthly"; exit 1 ;;
esac

mkdir -p "$LOG_DIR" "$STAGING"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
trap 'log "ERROR en linea $LINENO — backup abortado"' ERR

log "=== Backup repo urbIA-unal $FREQ iniciado ==="

# ─── 1. Verificar que el repo existe y es git válido ───────
if [[ ! -d "$REPO_DIR/.git" ]]; then
  log "ERROR: $REPO_DIR no es un repositorio git"
  exit 2
fi

cd "$REPO_DIR"

# Capturar metadata del estado actual para incluir en log
CURRENT_BRANCH=$(git branch --show-current)
CURRENT_SHA=$(git rev-parse HEAD)
CURRENT_SHA_SHORT=$(git rev-parse --short HEAD)
DIRTY="clean"
if ! git diff --quiet || ! git diff --cached --quiet; then
  DIRTY="dirty (hay cambios no commiteados)"
fi

log "Repo: $REPO_DIR"
log "Branch actual: $CURRENT_BRANCH"
log "HEAD: $CURRENT_SHA_SHORT ($CURRENT_SHA)"
log "Working tree: $DIRTY"

# ─── 2. Crear git bundle con todas las refs ─────────────────
BUNDLE_FILE="${STAGING}/urbia_repo_${FREQ}_${TS}_${CURRENT_SHA_SHORT}.bundle"
log "Creando git bundle..."

git bundle create "$BUNDLE_FILE" --all

if [[ ! -s "$BUNDLE_FILE" ]]; then
  log "ERROR: bundle vacío o no creado"
  exit 3
fi

# Verificar integridad del bundle ANTES de transferir
if ! git bundle verify "$BUNDLE_FILE" >/dev/null 2>&1; then
  log "ERROR: git bundle verify falló localmente"
  rm -f "$BUNDLE_FILE"
  exit 4
fi

BUNDLE_SIZE=$(du -h "$BUNDLE_FILE" | cut -f1)
log "Bundle creado y verificado: $(basename "$BUNDLE_FILE") ($BUNDLE_SIZE)"

# ─── 3. Comprimir con gzip ──────────────────────────────────
gzip -c "$BUNDLE_FILE" > "${BUNDLE_FILE}.gz"
rm -f "$BUNDLE_FILE"
BUNDLE_FILE="${BUNDLE_FILE}.gz"
COMPRESSED_SIZE=$(du -h "$BUNDLE_FILE" | cut -f1)
log "Bundle comprimido: $COMPRESSED_SIZE"

# ─── 4. md5 local ───────────────────────────────────────────
MD5=$(md5sum "$BUNDLE_FILE" | cut -d' ' -f1)
echo "$MD5  $(basename "$BUNDLE_FILE")" > "${BUNDLE_FILE}.md5"
log "md5: $MD5"

# ─── 5. Transferir vía scp ──────────────────────────────────
REMOTE_DIR="${REMOTE_BASE}/${FREQ}"
log "Transfiriendo a ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
scp -q "$BUNDLE_FILE" "${BUNDLE_FILE}.md5" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# ─── 6. Verificar md5 en destino ────────────────────────────
log "Verificando md5 remoto..."
# shellcheck disable=SC2029
REMOTE_MD5=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "md5sum ${REMOTE_DIR}/$(basename "$BUNDLE_FILE") | cut -d' ' -f1")

if [[ "$MD5" != "$REMOTE_MD5" ]]; then
  log "ERROR: md5 difiere — local=$MD5 remoto=$REMOTE_MD5"
  # shellcheck disable=SC2029
  ssh "${REMOTE_USER}@${REMOTE_HOST}" "rm -f ${REMOTE_DIR}/$(basename "$BUNDLE_FILE") ${REMOTE_DIR}/$(basename "$BUNDLE_FILE").md5"
  exit 5
fi
log "md5 verificado en destino: OK"

# ─── 7. Limpiar staging ─────────────────────────────────────
rm -f "$BUNDLE_FILE" "${BUNDLE_FILE}.md5"
log "Staging local limpiado"

# ─── 8. Política de retención en .104 ───────────────────────
log "Aplicando retención: borrar archivos > $RETAIN_DAYS días en ${REMOTE_DIR}/"
# shellcheck disable=SC2029
ssh "${REMOTE_USER}@${REMOTE_HOST}" \
  "find ${REMOTE_DIR} -name 'urbia_repo_${FREQ}_*.bundle.gz' -mtime +${RETAIN_DAYS} -delete -print; \
   find ${REMOTE_DIR} -name 'urbia_repo_${FREQ}_*.bundle.gz.md5' -mtime +${RETAIN_DAYS} -delete -print" \
  | while IFS= read -r deleted; do
      [[ -n "$deleted" ]] && log "Borrado por retención: $deleted"
    done

# ─── 9. Resumen final ───────────────────────────────────────
# shellcheck disable=SC2029
REMOTE_COUNT=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "ls -1 ${REMOTE_DIR}/urbia_repo_${FREQ}_*.bundle.gz 2>/dev/null | wc -l")
# shellcheck disable=SC2029
REMOTE_SIZE=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "du -sh ${REMOTE_DIR} | cut -f1")

log "Backups actuales en ${FREQ}/: ${REMOTE_COUNT} archivos, ${REMOTE_SIZE} total"
log "SHA preservado: $CURRENT_SHA_SHORT (branch: $CURRENT_BRANCH)"
log "=== Backup repo $FREQ COMPLETADO ==="
exit 0
