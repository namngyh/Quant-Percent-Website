\set ON_ERROR_STOP on

SELECT current_database() AS database,
       current_setting('server_version') AS postgres_version,
       (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb')
         AS timescaledb_version;

SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
WHERE schemaname IN ('public', 'web', 'quant')
ORDER BY schemaname, relname;

SELECT 'ticks' AS feed, max(ts) AS latest FROM public.ticks
UNION ALL
SELECT 'bars_1m', max(ts) FROM public.bars_1m
UNION ALL
SELECT 'model_forecasts', max(data_as_of) FROM quant.model_forecasts;

SELECT count(*) AS published_models,
       count(*) FILTER (WHERE research_profile IS NOT NULL)
         AS models_with_research,
       count(*) FILTER (WHERE show_forecast)
         AS models_with_live_output
FROM web.models
WHERE visibility = 'public';

SELECT slug, status, show_forecast,
       research_profile IS NOT NULL AS has_research
FROM web.models
WHERE slug IN ('raemf-mc', 'rarf-fhe', 'dynamic-graph', 'msdp')
ORDER BY slug;
