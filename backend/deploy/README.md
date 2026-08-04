# Production staging checklist

This Compose file is the pre-server deployment target: one private network,
only Caddy publishes ports, and the browser uses same-origin `/api/*` routes.
PostgreSQL and Redis are never exposed to the Internet.

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
docker compose --env-file .env.production -f compose.production.yml up -d timescaledb redis
docker compose --env-file .env.production -f compose.production.yml --profile tools run --rm db-role-init
docker compose --env-file .env.production -f compose.production.yml --profile tools run --rm migrate
docker compose --env-file .env.production -f compose.production.yml run --rm api python -m scripts.seed_catalogue --frontend /catalogue
```

`db-role-init` and `migrate` are one-off tasks. The migration deliberately
runs with the database owner because it must create schemas and vetted views;
the long-running API uses only the restricted `qp_web` role.

The API service mounts the frontend `config/` directory read-only at
`/catalogue/config`; the checked-in `catalogue.json` is the explicit publishing
snapshot.

Start the application after migration and seeding:

```powershell
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

## Verification

```powershell
curl.exe https://example.com/healthz
curl.exe https://example.com/readyz
curl.exe https://example.com/api/v1/models
Get-Content preflight.sql | docker compose --env-file .env.production -f compose.production.yml exec -T timescaledb psql -U quant -d market
docker compose --env-file .env.production -f compose.production.yml --profile tools run --rm backup
```

Copy every backup to off-server object storage. A backup remaining only on the
same VPS is not a disaster-recovery backup. Perform a restore rehearsal before
changing DNS to production.

The DataPro acquisition process is intentionally not in this Linux stack.
Connect the Windows acquisition machine over a private VPN or build an
authenticated ingestion gateway; never expose PostgreSQL or Redis publicly.
