# Deploy

How to run MyFinancePlace as a service: Docker, HTTPS behind a reverse proxy, backups, updates.

> **The app has no login yet** (Auth is "UI only"). Whoever reaches the URL sees and changes all the data.
> Never publish it on the internet as is: keep it on your machine / LAN, reach it through a VPN
> (Tailscale, WireGuard), or put a password in front of it at the reverse proxy (examples below).

## What runs

| Piece | File | Notes |
|---|---|---|
| Image | `Dockerfile` | `python:3.11-slim`, non-root user `app` (uid 1000), gunicorn on port 8000 |
| Start-up | `docker/entrypoint.sh` | generates a `SECRET_KEY` if none is given, runs `flask db upgrade`, then starts gunicorn |
| WSGI entry | `wsgi.py` | `create_app("production")` |
| Server | `gunicorn.conf.py` | 1 worker × 8 threads, timeout = `LLM_TIMEOUT` + 120 s, logs to stdout |
| Services | `docker-compose.yml` | `db` (PostgreSQL, host port 5332) and `app` (host port `APP_PORT`, default 8000) |
| Data | volumes `db` and `instance` | database, and `/app/instance`: document archive, safety copies of restores, pending imports, generated secret key |

The production config (`ProductionConfig` in `config.py`):

- refuses to start if `SECRET_KEY` is empty or a placeholder (`change-me`, `change-me-in-production`);
- sends cookies only over HTTPS, `HttpOnly`, `SameSite=Lax`; builds `https://` external URLs;
- with `BEHIND_PROXY=1` trusts the proxy's `X-Forwarded-*` headers (werkzeug `ProxyFix`, `PROXY_HOPS` hops);
- logs one line per record to stdout, level from `LOG_LEVEL`.

## Run with Docker

```bash
cp .env.example .env        # optional: every value has a default
docker compose up -d        # builds the image, starts PostgreSQL, migrates, starts the app
docker compose logs -f app  # follow the logs
```

Open `http://localhost:8000` (another port: `APP_PORT=8080` in `.env`).

- `SECRET_KEY`: leave it empty and the container generates one on first start and keeps it in the
  `instance` volume (`/app/instance/.secret_key`), or set your own in `.env`
  (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- Session cookies are HTTPS-only. Browsers accept them on `http://localhost`; to use the app over plain HTTP
  from another device on a trusted LAN, set `SESSION_COOKIE_SECURE=0` (otherwise flash messages get lost).
- `DATABASE_URL` in `.env` is for `python run.py` on the host; inside compose the app always talks to `db:5432`.
- AI reading with **Ollama** on the host machine: the container reaches it at `http://host.docker.internal:11434`
  (set `DOCKER_OLLAMA_URL` to point elsewhere, e.g. an `ollama` container). **Anthropic**: set `ANTHROPIC_API_KEY`
  in `.env`.
- Only the database for local development: `docker compose up -d db` (then `python run.py`, as in the README).

Without Docker: `pip install -r requirements.txt`, set `SECRET_KEY` and `DATABASE_URL`, then

```bash
flask --app wsgi db upgrade
gunicorn -c gunicorn.conf.py wsgi:app
```

### Settings (environment)

| Variable | Default | |
|---|---|---|
| `SECRET_KEY` | — (generated in Docker) | required in production |
| `LOG_LEVEL` | `INFO` | app and gunicorn |
| `BEHIND_PROXY` / `PROXY_HOPS` | `0` / `1` | set `BEHIND_PROXY=1` behind Caddy/nginx/Traefik |
| `SESSION_COOKIE_SECURE` | `1` | `0` only for plain HTTP on a trusted LAN |
| `GUNICORN_WORKERS` | `1` | keep 1: the progress of model downloads is kept in memory |
| `GUNICORN_THREADS` | `8` | concurrent requests |
| `GUNICORN_TIMEOUT` | `LLM_TIMEOUT` + 120 | a scanned statement read by a local model can take minutes |
| `APP_PORT` | `8000` | host port published by compose |
| `TZ` | `Europe/Rome` | "today" and the current month |
| `RUN_MIGRATIONS` | `1` | `0` skips `flask db upgrade` at start |

## HTTPS behind a reverse proxy

Publish the app only to the proxy, not to the whole network: in `docker-compose.yml` change the port line of
`app` to `"127.0.0.1:${APP_PORT:-8000}:8000"`, and in `.env`:

```bash
BEHIND_PROXY=1
```

Raise the proxy's timeouts and body size too: uploads have no size limit and an AI reading can take minutes.

### Caddy (automatic Let's Encrypt certificates)

```caddyfile
finanze.example.com {
    # No login in the app yet: protect it here. Hash: caddy hash-password
    basic_auth {
        me $2a$14$REPLACE_WITH_THE_HASH
    }
    request_body {
        max_size 1GB
    }
    reverse_proxy 127.0.0.1:8000 {
        transport http {
            read_timeout 15m
            write_timeout 15m
        }
    }
}
```

Caddy sets `X-Forwarded-For`/`-Proto`/`-Host` itself.

### nginx

```nginx
server {
    listen 80;
    server_name finanze.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name finanze.example.com;

    ssl_certificate     /etc/letsencrypt/live/finanze.example.com/fullchain.pem;   # certbot --nginx
    ssl_certificate_key /etc/letsencrypt/live/finanze.example.com/privkey.pem;

    # No login in the app yet: protect it here (htpasswd -c /etc/nginx/.htpasswd me)
    auth_basic           "MyFinancePlace";
    auth_basic_user_file /etc/nginx/.htpasswd;

    client_max_body_size 0;          # no limit on uploaded statements and backups
    proxy_read_timeout   900s;       # AI reading of long scans
    proxy_send_timeout   900s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
    }
}
```

## Backups

Two complementary ways; keep copies **off the server**.

1. **From the app — Esporta → Backup Completo e Ripristino** (`/export/backup`): one `.zip` with every table
   and the files of the document archive. Restoring replaces all data; the data being replaced is first saved in
   `instance/backups/` (last 10). This is the portable format: it restores into any version of the app.

2. **From the server** — the database with `pg_dump`, the files from the `instance` volume:

   ```bash
   # database
   docker compose exec -T db pg_dump -U sa -Fc myfinanceplace > mfp-$(date +%F).dump
   # documents, safety copies, secret key
   docker compose exec -T app tar -C /app/instance -cf - . > instance-$(date +%F).tar
   ```

   Restore:

   ```bash
   docker compose exec -T app tar -C /app/instance -xf - < instance-2026-09-29.tar   # as the app user
   docker compose stop app
   docker compose exec -T db pg_restore -U sa -d myfinanceplace --clean --if-exists < mfp-2026-09-29.dump
   docker compose start app
   ```

   A nightly cron job running the two backup commands (and copying the result elsewhere) is enough.

## Updating

```bash
git pull
docker compose up -d --build     # rebuilds the image; migrations run automatically at start
docker compose logs -f app       # "Running upgrade …" lines, then gunicorn "Listening at"
```

Take a backup first (above). If a migration fails the container stops before serving requests and the
error is in `docker compose logs app`; the old data is untouched (each migration runs in a transaction).

## Notes

- The `db` service keeps the original `PGDARE` variable name (a typo of `PGDATA`), so PostgreSQL stores its
  data in the image's default location (an anonymous volume of the container), not in the named volume `db`.
  The data survives `docker compose restart` and `up`, but after `docker compose down` the next `up` starts with
  an empty database (the old anonymous volume is left behind, detached). Use `docker compose stop` rather than
  `down`, keep the backups above, or fix it deliberately (dump, set `PGDATA`, restore).
- `postgres:latest` changes major version over time; a new major version cannot open an older data directory.
  Pin it (e.g. `postgres:16`) for a long-running installation, and dump/restore when upgrading.
