# Cloud Migration Runbook (WSL -> Cloud VM)

Moves the ibokki stack from local WSL to a cloud VM with **zero DNS changes**,
because Cloudflare Tunnel decouples the origin's location from its public
address. The tunnel reconnects from the new host and `ibokki.com` keeps working.

Estimated time: ~1-2 hours, most of it data transfer.

---

## 0. Before you start (on the OLD host / WSL)

Know your Docker Compose **project name** — it prefixes the volume names. With
the current setup it is `deploy` (the folder the compose file lives in), so the
volumes are `deploy_postgres_data`, `deploy_media_volume`, etc. Confirm with:

```bash
docker volume ls | grep -E 'postgres_data|media_volume'
```

---

## 1. Provision the VM

- Ubuntu 24.04 LTS, sized per the hosting notes (recommended: 4 dedicated vCPU /
  16GB for voice later; 2 vCPU / 8GB minimum for chat-only).
- Pick the datacenter **closest to your voice-chat group** (latency matters more
  than specs for screen-share smoothness).
- Firewall / cloud security group inbound rules:
  - `22/tcp` (SSH) — ideally restricted to your IP.
  - **Nothing else yet.** All web traffic arrives via the outbound Cloudflare
    Tunnel, so no `80`/`443` inbound is required.
  - (Voice/LiveKit later will need `7881/tcp` + `7882/udp` — add when you set up
    Fluxer, not now.)

## 2. Install Docker + Compose (on the NEW VM)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER    # then log out/in
docker compose version           # confirm v2
```

## 3. Get the code + secrets onto the VM

```bash
git clone <your-repo-url> ibokkiSite
cd ibokkiSite
```

Copy these from WSL (they are gitignored, so they must be moved manually):

- `deploy/.env`  (all secrets, including the quoted multi-line `OIDC_RSA_PRIVATE_KEY`)
- `deploy/cloudflared/config.yml`
- `deploy/cloudflared/<TUNNEL_UUID>.json`  (tunnel credentials)

From WSL, for example:
```bash
scp deploy/.env user@NEW_VM:~/ibokkiSite/deploy/.env
scp deploy/cloudflared/config.yml user@NEW_VM:~/ibokkiSite/deploy/cloudflared/
scp deploy/cloudflared/*.json     user@NEW_VM:~/ibokkiSite/deploy/cloudflared/
```

## 4. Dump the data (on the OLD host / WSL)

Database:
```bash
docker compose -f deploy/docker-compose.yml exec -T db \
  pg_dump -U ibokki -d ibokki --clean --if-exists > ibokki_db.sql
```

Uploaded media (emote images) — back up the named volume:
```bash
docker run --rm \
  -v deploy_media_volume:/data \
  -v "$PWD":/backup alpine \
  tar czf /backup/media.tgz -C /data .
```

Copy both to the VM:
```bash
scp ibokki_db.sql media.tgz user@NEW_VM:~/ibokkiSite/
```

## 5. Restore the data (on the NEW VM)

Start only the database first so it can accept the restore:
```bash
docker compose -f deploy/docker-compose.prod.yml up -d db
# wait until healthy:
docker compose -f deploy/docker-compose.prod.yml ps
```

Restore the database:
```bash
cat ibokki_db.sql | docker compose -f deploy/docker-compose.prod.yml exec -T db \
  psql -U ibokki -d ibokki
```

Restore the media volume:
```bash
docker run --rm \
  -v deploy_media_volume:/data \
  -v "$PWD":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/media.tgz -C /data"
```

## 6. Build and start the full stack (on the NEW VM)

```bash
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
docker compose -f deploy/docker-compose.prod.yml exec web python manage.py migrate
docker compose -f deploy/docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

`migrate` should report little or nothing to do (the dump already carried the
schema + data); it just confirms consistency.

## 7. Cut over the tunnel

A tunnel's credentials should run in **one place at a time**. For a clean
switch:

1. On WSL (old host) stop the tunnel:
   ```bash
   docker compose -f deploy/docker-compose.yml stop cloudflared
   ```
2. On the NEW VM the tunnel is already running (started in step 6). Within a few
   seconds Cloudflare routes `ibokki.com` to the new origin.

Verify from anywhere:
```bash
curl -s https://ibokki.com/o/.well-known/openid-configuration | head -c 120
curl -sI https://ibokki.com/ | head -1
```

## 8. Smoke test

- Log in at `https://ibokki.com/` with an existing account (proves DB restore).
- Open a stream/chat, send a message, confirm an emote renders (proves media
  restore + websockets + Redis).
- Right-click a user / emote (proves the latest frontend shipped).

## 9. Decommission the old host

Once the cloud instance is verified and stable for a day or two:
```bash
# on WSL
docker compose -f deploy/docker-compose.yml down
```
Keep `ibokki_db.sql` / `media.tgz` as a one-off backup until you trust the new host.

---

## Rollback

If anything goes wrong during cutover, restart the WSL tunnel and stop the cloud
one — `ibokki.com` returns to the old origin immediately:
```bash
# on the cloud VM
docker compose -f deploy/docker-compose.prod.yml stop cloudflared
# on WSL
docker compose -f deploy/docker-compose.yml up -d cloudflared
```
