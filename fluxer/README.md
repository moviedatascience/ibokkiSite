# Fluxer (self-hosted chat) — deployment

Self-hosted [Fluxer](https://github.com/fluxerapp/fluxer) provides the Discord-
like chat/voice at `chat.ibokki.com`, with login delegated to ibokki via SSO
(ibokki is the OIDC provider; see the `OAUTH2_PROVIDER` settings and `/o/...`
endpoints in the main app).

Fluxer runs as its own Docker Compose stack in `~/fluxer` on each host —
**separate from the ibokki app**. This folder holds only the non-secret
*customizations* we add on top of Fluxer's stock files. Secrets, tunnel
credentials, and Fluxer's own downloaded files are NOT committed.

| Env | Host | Hostname | ibokki OIDC issuer |
|-----|------|----------|--------------------|
| staging | WSL | `chat-staging.ibokki.com` | `https://staging.ibokki.com/o` |
| prod | Vultr | `chat.ibokki.com` | `https://ibokki.com/o` |

## Files in this folder

- `sso-injector.conf` — nginx that proxies to Fluxer's Caddy and injects the
  auto-redirect script into the login page.
- `sso-auto.js` — auto-clicks "Continue with SSO" so enforced SSO is zero-click.
- `cloudflared.compose.yml` — Compose override adding the injector + tunnel.
- `cloudflared/config.example.yml` — tunnel config template.

These get copied into `~/fluxer/` on the host. `~/fluxer/.env` and
`~/fluxer/cloudflared/*.json` (secrets/credentials) stay host-local.

## Deploy (per host)

1. **Download Fluxer's stack files** into `~/fluxer`:
   ```bash
   mkdir -p ~/fluxer && cd ~/fluxer
   BASE=https://raw.githubusercontent.com/fluxerapp/fluxer/main/deploy/self-hosting
   curl -fsSL -O $BASE/docker-compose.yml -O $BASE/Caddyfile -O $BASE/livekit.yaml
   curl -fsSL $BASE/.env.example -o .env
   ```
2. **Generate fresh secrets** in `.env` (one per host — never reuse across envs):
   set every `CHANGE_ME` with `openssl rand -hex 32` (and
   `FLUXER_MEDIA_PROXY_UPLOAD_RELAY_SECRET_BASE64` with `openssl rand -base64 32`,
   VAPID keys with `web-push generate-vapid-keys`). Set `FLUXER_DOMAIN` to the
   env hostname and `FLUXER_CADDY_SITE_ADDRESS=:80` (TLS is at Cloudflare).
3. **Copy these customizations** into `~/fluxer`: `sso-injector.conf`,
   `sso-auto.js`, `cloudflared.compose.yml`, and `cloudflared/config.yml`
   (from `config.example.yml`).
4. **Create the tunnel** and route the hostname (see `config.example.yml`),
   drop the `<UUID>.json` into `~/fluxer/cloudflared/`, `chmod 644` it.
5. **Voice ports (prod only):** `ufw allow 7881/tcp && ufw allow 7882/udp`
   (LiveKit media can't traverse the tunnel — it needs the public IP).
6. **Start:** `docker compose -f docker-compose.yml -f cloudflared.compose.yml up -d`

## SSO wiring

1. Register the first Fluxer account at the hostname using **the same email as
   your ibokki account** (Fluxer binds SSO logins to existing accounts by email).
2. Register an OAuth client on the matching ibokki env:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml exec web python manage.py shell -c "
   import secrets; from oauth2_provider.models import Application
   p=secrets.token_urlsafe(48)
   a,c=Application.objects.get_or_create(name='Fluxer Prod', defaults=dict(
     client_type='confidential', authorization_grant_type='authorization-code',
     redirect_uris='https://chat.ibokki.com/auth/sso/callback',
     algorithm='RS256', skip_authorization=True, client_secret=p))
   print('ID:',a.client_id); print('SECRET:', p if c else '(exists)')"
   ```
3. In Fluxer admin (`/admin`) → SSO: set issuer (the env's `…/o`), the client
   id/secret, allowed email domains empty, **enabled** on. Test with **enforced
   off** first (confirm it binds to your admin), then turn **enforced on**.

## Gotchas we hit (don't relearn these the hard way)

- **Voice needs a server registered in admin.** Fluxer's auto-initializer only
  creates a default voice region/server if a default region is configured, and
  that config isn't in the self-hosting `.env`. Symptom: `liveKitServersSearched: 0`
  and "Voice server timeout." Fix: admin → **Voice Regions** (create a default
  region) → **Voice Servers** (add one): endpoint `wss://<hostname>/livekit`,
  API key `fluxer`, API secret = `LIVEKIT_API_SECRET` from `.env`.
- **`no-store` on `/sso-auto.js` is mandatory** — Cloudflare otherwise caches it
  and edits never take effect.
- **Desktop app can't target a self-hosted instance yet** (hardcoded to
  `web.fluxer.app`); known upstream bug, no ETA. Use the browser meanwhile.
- **Screen-share audio** is a browser-picker setting, not a Fluxer one: Chrome/
  Edge, share **Entire Screen + "share system audio"** (per-window has no audio).
