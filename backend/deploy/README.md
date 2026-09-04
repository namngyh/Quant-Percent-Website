# Production staging checklist

This Compose file is the pre-server deployment target: one private network,
only Caddy publishes ports, and the browser uses same-origin `/api/*` routes.
PostgreSQL and Redis are never exposed to the Internet.

## Host prerequisites

Two things must already exist on the server. Neither can live in Git, and the
stack cannot start without them.

**1. Cloudflare Origin certificate** at `/etc/caddy/certs/origin.pem` and
`/etc/caddy/certs/origin-key.pem`, readable by the Caddy container.

The domain is proxied through Cloudflare, which intercepts both HTTP-01 and
TLS-ALPN-01, so Caddy cannot obtain a Let's Encrypt certificate. It serves a
Cloudflare-issued origin certificate instead — see the `tls` directives in
`Caddyfile` and the read-only mount in `compose.override.yml`. Those two are a
pair; remove either and Caddy will not start. Origin certificates are issued
for years rather than months and **Caddy will not renew them**, so the expiry
date belongs in a calendar reminder.

**2. A VPN interface holding `10.10.0.1`.** `compose.override.yml` binds
PostgreSQL to that address so the Windows DataPro machine can reach it over the
private link. Bound to the VPN address only — never `0.0.0.0` — so the database
is not reachable from the Internet. With the VPN down, Docker fails to bind and
the stack refuses to start, which is the intended loud failure.

`deploy.sh` checks for the certificates before doing any work and stops early
if they are missing.

## Every command needs both compose files

```
-f compose.production.yml -f compose.override.yml
```

Passing `-f` explicitly stops Compose from auto-loading the override, but the
project name is unchanged, so a command with only the production file will
reconcile the running stack down to that file alone — silently dropping the
certificate mount and the VPN port. Use `deploy.sh`, which already passes both.

## Before first start

1. Keep the three repositories in the current sibling layout.
2. Copy `.env.production.example` to `.env.production` and fill every secret.
   Generate a different URL-safe value for each password/secret with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Set `TIMESCALE_IMAGE` to a TimescaleDB PG16 tag tested against the local
   backup. Do not use a floating `latest` tag.
4. Point the domain A/AAAA record at the staging server.

## Initialize

```powershell
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml up -d timescaledb redis
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml --profile tools run --rm db-role-init
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml --profile tools run --rm migrate
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml run --rm api python -m scripts.seed_catalogue --frontend /catalogue
```

`db-role-init` and `migrate` are one-off tasks. The migration deliberately
runs with the database owner because it must create schemas and vetted views;
the long-running API uses only the restricted `qp_web` role.

The API service mounts the frontend `config/` directory read-only at
`/catalogue/config`; the checked-in `catalogue.json` is the explicit publishing
snapshot.

Start the application after migration and seeding:

```powershell
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml up -d --build
```

## Verification

```powershell
curl.exe https://example.com/healthz
curl.exe https://example.com/readyz
curl.exe https://example.com/api/v1/models
Get-Content preflight.sql | docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml exec -T timescaledb psql -U quant -d market
docker compose --env-file .env.production -f compose.production.yml -f compose.override.yml --profile tools run --rm backup
```

Copy every backup to off-server object storage. A backup remaining only on the
same VPS is not a disaster-recovery backup. Perform a restore rehearsal before
changing DNS to production.

The DataPro acquisition process is intentionally not in this Linux stack.
Connect the Windows acquisition machine over a private VPN or build an
authenticated ingestion gateway; never expose PostgreSQL or Redis publicly.
