#!/usr/bin/env bash
#
# Nightly backup of the things that can't be rebuilt from git: the Postgres
# database and the uploaded media (emote images). Everything else (code,
# containers, configs) is reproducible from the repo, so it is not backed up.
#
# Run on the prod host (Vultr). Intended for cron, e.g.:
#   0 4 * * * /root/ibokkiSite/deploy/backup.sh >> /var/log/ibokki-backup.log 2>&1
#
# Override the destination with BACKUP_DIR=/path bash deploy/backup.sh
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE="docker compose -f deploy/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$HOME/ibokki-backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Backing up database..."
$COMPOSE exec -T db pg_dump -U ibokki -d ibokki --clean --if-exists \
  | gzip > "$BACKUP_DIR/db_$STAMP.sql.gz"

echo "[$(date)] Backing up media volume..."
docker run --rm \
  -v deploy_media_volume:/data \
  -v "$BACKUP_DIR":/backup alpine \
  tar czf "/backup/media_$STAMP.tgz" -C /data .

echo "[$(date)] Pruning backups older than $RETAIN_DAYS days..."
find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -name 'media_*.tgz' -mtime +"$RETAIN_DAYS" -delete

echo "[$(date)] Backup complete -> $BACKUP_DIR (db_$STAMP.sql.gz, media_$STAMP.tgz)"
