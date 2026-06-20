# iBokki Deployment

How iBokki is built, deployed, and operated. The whole system runs as a Docker
Compose stack fronted by a Cloudflare Tunnel, with a simple git-based deploy
flow across three environments.

---

## Architecture

The stack is a single Docker Compose project. Every environment runs the same
set of containers:

| Service | Image / build | Role |
|---------|---------------|------|
| `web` | built from `Dockerfile` | Django HTTP via **gunicorn** (port 8000) |
| `websocket` | built from `Dockerfile` | Django Channels via **daphne** (port 8001) — chat WebSockets |
| `db` | `postgres:15-alpine` | PostgreSQL database |
| `redis` | `redis:7-alpine` | Channels layer (WebSocket message passing) |
| `nginx` | `nginx:alpine` | Reverse proxy; routes `/`, `/ws/`, `/static/`, `/media/` |
| `cloudflared` | `cloudflare/cloudflared` | **Cloudflare Tunnel** — the only ingress |

**Traffic flow:** `user → Cloudflare edge → tunnel (cloudflared) → nginx → web/websocket`.

Because `cloudflared` makes an **outbound** connection to Cloudflare, the host
needs **no inbound HTTP ports open** — Cloudflare terminates TLS at its edge.
In production (`docker-compose.prod.yml`) no container publishes a host port at
all; the only thing exposed on the server is SSH.

iBokki also acts as an **OpenID Connect provider** (`/o/...`, via
`django-oauth-toolkit`) so the self-hosted Fluxer chat can use ibokki accounts
for SSO. See the OIDC settings in `ibokki/settings.py`.

---

## Environments

| Env | Host | URL | Compose file | Branch |
|-----|------|-----|--------------|--------|
| **dev** | your local machine | `localhost:8000` | `docker-compose.yml` | feature branches |
| **staging** | WSL box | `staging.ibokki.com` | `docker-compose.staging.yml` | the branch under test |
| **prod** | Vultr (Atlanta) | `ibokki.com` | `docker-compose.prod.yml` | `main` |

`main` is the production branch. Staging and prod each have their **own
Cloudflare tunnel** so they can never interfere. Staging uses a separate Compose
project name (`ibokki-staging`) so its data volumes are isolated.

---

## Compose files

- **`docker-compose.yml`** — local dev. Publishes ports and bind-mounts the repo
  for fast iteration.
- **`docker-compose.staging.yml`** — staging on WSL. Mirrors prod
  (`DEBUG=False`), serves `staging.ibokki.com` via `cloudflared-staging/`,
  project name `ibokki-staging`.
- **`docker-compose.prod.yml`** — production. No published host ports,
  `restart: unless-stopped`, healthchecks, read-only mounts.

---

## Environment variables (`deploy/.env`)

Compose reads `deploy/.env`. It is gitignored — never commit it. Required keys:

```bash
# Django
SECRET_KEY=...
POSTGRES_PASSWORD=...

# Email (ProtonMail SMTP)
EMAIL_HOST_USER=loremipsum@ibokki.com
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=loremipsum@ibokki.com

# OIDC provider signing key (used by Fluxer SSO).
# Multi-line PEM — MUST be wrapped in double quotes so python-dotenv keeps it intact.
OIDC_RSA_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----"
```

`DEBUG`, `ENVIRONMENT`, `BASE_URL`, `REDIS_URL`, and `DATABASE_URL` are set per
environment inside each compose file's `environment:` block.

---

## Deploy workflow (dev → staging → prod)

1. **Branch** off `main`: `git checkout -b feature/x`.
2. **Develop locally** and run the dev stack:
   `docker compose -f deploy/docker-compose.yml up -d --build`
3. **Test on staging** — push the branch, check it out on WSL, and start the
   staging stack (see below). Validate the real tunnel, SSO, and **migrations**
   against a copy of prod data.
4. **Merge to `main`** and push.
5. **Deploy to prod** — on the Vultr box:
   ```bash
   cd ~/ibokkiSite
   bash deploy/deploy.sh
   ```
   `deploy.sh` pulls `main`, rebuilds images, runs migrations + collectstatic,
   and restarts services. Only `web`/`websocket` recreate (a ~2s blip); the
   tunnel, db, and redis stay up.

---

## Staging (WSL)

One-time setup:

1. **Create a second Cloudflare tunnel** (separate from prod) named e.g.
   `ibokki-staging`, in Zero Trust → Networks → Tunnels, or:
   `cloudflared tunnel create ibokki-staging`.
2. Put its `<UUID>.json` credentials in `deploy/cloudflared-staging/`.
3. `cp deploy/cloudflared-staging/config.example.yml deploy/cloudflared-staging/config.yml`
   and fill in the staging tunnel UUID + credentials filename.
4. Point **`staging.ibokki.com`** at the staging tunnel (a proxied CNAME to
   `<UUID>.cfargotunnel.com`, or a public hostname on the tunnel).

Run staging on WSL:
```bash
docker compose -f deploy/docker-compose.staging.yml up -d --build
```

Refresh staging data from the latest prod backup at any time:
```bash
PROD_HOST=root@<prod-ip> bash deploy/refresh-staging.sh
```

Staging only needs to be running while you are actively testing.

---

## Backups & restore

`deploy/backup.sh` (prod, nightly via cron at 04:00) writes a gzipped
`pg_dump` and a tar of the media volume to `~/ibokki-backups`, keeping 14 days:

```bash
0 4 * * * /root/ibokkiSite/deploy/backup.sh >> /var/log/ibokki-backup.log 2>&1
```

Only the **database and uploaded media** are backed up — everything else is
reproducible from this repo.

**Restore** (e.g. onto a fresh host) is the same flow used in the cloud
migration — see `CLOUD_MIGRATION.md`:
```bash
gunzip -c db_YYYYMMDD.sql.gz | docker compose -f deploy/docker-compose.prod.yml exec -T db psql -U ibokki -d ibokki
docker run --rm -v deploy_media_volume:/data -v "$PWD":/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/media_YYYYMMDD.tgz -C /data"
```

---

## Cloudflare Tunnel

Each environment's tunnel is config-file managed. The config points at the
internal nginx so both HTTP and WebSocket reach the app:

```yaml
tunnel: <UUID>
credentials-file: /etc/cloudflared/<UUID>.json
ingress:
  - hostname: ibokki.com          # staging.ibokki.com for staging
    service: http://nginx:80
  - service: http_status:404
```

Config + credentials live in `deploy/cloudflared/` (prod) and
`deploy/cloudflared-staging/` (staging), both gitignored. DNS is a proxied CNAME
to `<UUID>.cfargotunnel.com`, created in the Cloudflare dashboard. The tunnel's
credentials JSON must be readable by the container user (`chmod 644`).

---

## First-time host setup & migration

To stand up a brand-new production host (provisioning, Docker install, data
restore, tunnel cutover), follow **`CLOUD_MIGRATION.md`**.

---

## Troubleshooting

- **502 from Cloudflare:** the tunnel can't reach the origin. Check the tunnel
  connected: `docker compose -f deploy/docker-compose.prod.yml logs --tail=20 cloudflared` (look for "Registered tunnel connection"); confirm `nginx` is up.
- **`cloudflared` "permission denied" on credentials:** `chmod 644 deploy/cloudflared/*.json`.
- **WebSockets not connecting:** confirm `redis` and `websocket` are healthy and
  nginx is proxying `/ws/` to `websocket:8001`.
- **`web` shows `unhealthy` but the site works:** the healthcheck must use
  `127.0.0.1` (gunicorn binds IPv4 only); `localhost` resolves to IPv6 first.
- **Changes not visible after deploy:** purge the Cloudflare cache (the HTML can
  be edge-cached); static assets are content-hashed so they bust automatically.
- **`git` "dubious ownership"** on a server repo owned by root:
  `git config --global --add safe.directory /root/ibokkiSite`.
