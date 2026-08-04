-- Run by a database superuser before `alembic upgrade head`.
-- Creating roles needs privileges the application user must not have, so
-- this is deliberately kept out of the migrations.
--
--   psql -U quant -d market \
--     --set=api_password="a-strong-password" --file=scripts/create_role.sql

\set ON_ERROR_STOP on

\if :{?api_password}
\else
\echo 'Missing required psql variable: api_password'
\quit 3
\endif

-- psql does not interpolate variables inside a dollar-quoted DO block.
-- Build the DDL outside a string literal and let \gexec execute it.
SELECT format('CREATE ROLE qp_web LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qp_web')
\gexec

SELECT format('ALTER ROLE qp_web LOGIN PASSWORD %L', :'api_password')
\gexec

-- No blanket rights: the migration grants exactly what the API needs, and
-- market data stays reachable only through the vetted api.* views.
REVOKE ALL ON SCHEMA public FROM qp_web;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM qp_web;

-- Connect right on the database itself
GRANT CONNECT ON DATABASE market TO qp_web;

\echo 'Role qp_web ready. Now run: alembic upgrade head'
