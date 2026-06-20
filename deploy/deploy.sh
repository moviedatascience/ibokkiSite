#!/usr/bin/env bash
#
# Production deploy script. Run on the prod host (Vultr) from the repo root:
#   bash deploy/deploy.sh
#
# Pulls the latest code on the current branch, rebuilds images, runs
# migrations + collectstatic, and restarts the stack. Only the web/websocket
# containers recreate (a few seconds' blip); db/redis/nginx/cloudflared keep
# running, so the tunnel stays connected throughout.
set -euo pipefail

# Move to the repo root regardless of where the script is invoked from.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE="docker compose -f deploy/docker-compose.prod.yml"

echo "==> [1/6] Pulling latest code (fast-forward only)"
git pull --ff-only

echo "==> [2/6] Building images"
$COMPOSE build

echo "==> [3/6] Ensuring database and redis are up"
$COMPOSE up -d db redis

echo "==> [4/6] Applying database migrations"
$COMPOSE run --rm web python manage.py migrate --noinput

echo "==> [5/6] Collecting static files"
$COMPOSE run --rm web python manage.py collectstatic --noinput

echo "==> [6/6] Restarting services"
$COMPOSE up -d

# Clean up dangling images from old builds.
docker image prune -f >/dev/null 2>&1 || true

echo "==> Deploy complete. Current status:"
$COMPOSE ps
