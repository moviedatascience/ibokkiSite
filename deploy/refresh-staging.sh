#!/usr/bin/env bash
#
# Refresh the STAGING database + media from the latest PRODUCTION backup, so you
# test against realistic data with zero risk to live. Run on the staging host
# (WSL). Requires SSH access to the prod box (the same key you deploy with).
#
#   PROD_HOST=root@1.2.3.4 bash deploy/refresh-staging.sh
#
# Defaults assume the prod box at the IP below with backups in ~/ibokki-backups.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROD_HOST="${PROD_HOST:-root@155.138.192.190}"
PROD_BACKUP_DIR="${PROD_BACKUP_DIR:-/root/ibokki-backups}"
COMPOSE="docker compose -f deploy/docker-compose.staging.yml"
MEDIA_VOLUME="ibokki-staging_media_volume"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Finding latest prod backup on $PROD_HOST ..."
LATEST_DB=$(ssh "$PROD_HOST" "ls -t $PROD_BACKUP_DIR/db_*.sql.gz | head -1")
LATEST_MEDIA=$(ssh "$PROD_HOST" "ls -t $PROD_BACKUP_DIR/media_*.tgz | head -1")
echo "    db:    $LATEST_DB"
echo "    media: $LATEST_MEDIA"

echo "==> Downloading backups ..."
scp "$PROD_HOST:$LATEST_DB" "$TMP/db.sql.gz"
scp "$PROD_HOST:$LATEST_MEDIA" "$TMP/media.tgz"

echo "==> Ensuring staging database is up ..."
$COMPOSE up -d db
sleep 10

echo "==> Restoring database into staging ..."
gunzip -c "$TMP/db.sql.gz" | $COMPOSE exec -T db psql -U ibokki -d ibokki

echo "==> Restoring media into staging ..."
docker run --rm -v "$MEDIA_VOLUME":/data -v "$TMP":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/media.tgz -C /data"

echo "==> Staging refreshed from production backup."
