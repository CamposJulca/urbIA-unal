#!/usr/bin/env bash
#
# backup_mongo.sh — Backup automatizado de MongoDB UrbIA
#
# Origen:  contenedor urbia-mongo en .102 (auth habilitada)
# Destino: camposjulca@192.168.0.104:/mnt/storage/Neusi/urbia-backups/mongo/
# Política: daily=7d, weekly=28d, monthly=92d
# Uso: ./backup_mongo.sh [daily|weekly|monthly]   (default: daily)

set -euo pipefail

FREQ="${1:-daily}"
TS=$(date +%Y%m%d-%H%M%S)
CONTAINER="urbia-mongo"
REMOTE_USER="camposjulca"
REMOTE_HOST="192.168.0.104"
REMOTE_BASE="/mnt/storage/Neusi/urbia-backups/mongo"
STAGING="/home/pruebas/urbia-backups/staging"
LOG_DIR="/home/pruebas/urbia-backups/logs"
LOG_FILE="${LOG_DIR}/mongo_${FREQ}_${TS}.log"

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

log "=== Backup MongoDB $FREQ iniciado ==="

# ─── 1. Credenciales dinámicas ──────────────────────────────
MONGO_USER=$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "^MONGO_INITDB_ROOT_USERNAME=" | cut -d= -f2)
MONGO_PASS=$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "^MONGO_INITDB_ROOT_PASSWORD=" | cut -d= -f2)

if [[ -z "$MONGO_USER" || -z "$MONGO_PASS" ]]; then
  log "ERROR: no pude extraer MONGO_INITDB_ROOT_USERNAME/PASSWORD"
  exit 2
fi
log "Origen: $CONTAINER (user=$MONGO_USER, auth=admin)"

# ─── 2. mongodump completo con --archive --gzip ─────────────
DUMP_FILE="${STAGING}/urbia_mongo_${FREQ}_${TS}.archive.gz"
log "Ejecutando mongodump..."

docker exec "$CONTAINER" mongodump \
  --username="$MONGO_USER" \
  --password="$MONGO_PASS" \
  --authenticationDatabase=admin \
  --archive --gzip > "$DUMP_FILE"

if [[ ! -s "$DUMP_FILE" ]]; then
  log "ERROR: dump vacío o no creado"
  exit 3
fi
DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
log "Dump creado: $(basename "$DUMP_FILE") ($DUMP_SIZE)"

# ─── 3. md5 local ───────────────────────────────────────────
MD5=$(md5sum "$DUMP_FILE" | cut -d' ' -f1)
echo "$MD5  $(basename "$DUMP_FILE")" > "${DUMP_FILE}.md5"
log "md5: $MD5"

# ─── 4. Transferir vía scp ──────────────────────────────────
REMOTE_DIR="${REMOTE_BASE}/${FREQ}"
log "Transfiriendo a ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
scp -q "$DUMP_FILE" "${DUMP_FILE}.md5" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# ─── 5. Verificar md5 en destino ────────────────────────────
log "Verificando md5 remoto..."
# shellcheck disable=SC2029
REMOTE_MD5=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "md5sum ${REMOTE_DIR}/$(basename "$DUMP_FILE") | cut -d' ' -f1")

if [[ "$MD5" != "$REMOTE_MD5" ]]; then
  log "ERROR: md5 difiere — local=$MD5 remoto=$REMOTE_MD5"
  # shellcheck disable=SC2029
  ssh "${REMOTE_USER}@${REMOTE_HOST}" "rm -f ${REMOTE_DIR}/$(basename "$DUMP_FILE") ${REMOTE_DIR}/$(basename "$DUMP_FILE").md5"
  exit 4
fi
log "md5 verificado en destino: OK"

# ─── 6. Limpiar staging ─────────────────────────────────────
rm -f "$DUMP_FILE" "${DUMP_FILE}.md5"
log "Staging local limpiado"

# ─── 7. Política de retención en .104 ───────────────────────
log "Aplicando retención: borrar archivos > $RETAIN_DAYS días en ${REMOTE_DIR}/"
# shellcheck disable=SC2029
ssh "${REMOTE_USER}@${REMOTE_HOST}" \
  "find ${REMOTE_DIR} -name 'urbia_mongo_${FREQ}_*.archive.gz' -mtime +${RETAIN_DAYS} -delete -print; \
   find ${REMOTE_DIR} -name 'urbia_mongo_${FREQ}_*.archive.gz.md5' -mtime +${RETAIN_DAYS} -delete -print" \
  | while IFS= read -r deleted; do
      [[ -n "$deleted" ]] && log "Borrado por retención: $deleted"
    done

# ─── 8. Resumen final ───────────────────────────────────────
# shellcheck disable=SC2029
REMOTE_COUNT=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "ls -1 ${REMOTE_DIR}/urbia_mongo_${FREQ}_*.archive.gz 2>/dev/null | wc -l")
# shellcheck disable=SC2029
REMOTE_SIZE=$(ssh "${REMOTE_USER}@${REMOTE_HOST}" "du -sh ${REMOTE_DIR} | cut -f1")

log "Backups actuales en ${FREQ}/: ${REMOTE_COUNT} archivos, ${REMOTE_SIZE} total"
log "=== Backup MongoDB $FREQ COMPLETADO ==="
exit 0
