-- Read-only PostgreSQL capacity inventory for LeiAberta.
-- Run with psql; each statement autocommits under default_transaction_read_only.
-- This script does not include exact source-snapshot payload sizing; that heavier
-- scan is isolated in postgres_snapshot_payload_inventory.sql.

\timing on
\set ON_ERROR_STOP off

SET application_name = 'leiaberta_capacity_inventory_readonly';
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
SET lock_timeout = '2s';

\echo 'Capture timestamp and current database size'
SELECT clock_timestamp() AS measured_at_utc,
       current_database() AS database_name,
       current_setting('server_version') AS server_version,
       pg_database_size(current_database()) AS database_bytes,
       pg_size_pretty(pg_database_size(current_database())) AS database_pretty;

\echo 'Application relation sizes: heap, indexes, TOAST, and auxiliary forks'
SELECT n.nspname AS schema_name,
       c.relname AS relation_name,
       CASE c.relkind WHEN 'm' THEN 'materialized view'
                      WHEN 'p' THEN 'partitioned table'
                      ELSE 'table' END AS relation_kind,
       pg_total_relation_size(c.oid) AS total_bytes,
       pg_relation_size(c.oid) AS main_fork_bytes,
       pg_indexes_size(c.oid) AS index_bytes,
       CASE WHEN c.reltoastrelid <> 0
            THEN pg_total_relation_size(c.reltoastrelid) ELSE 0 END AS toast_total_bytes,
       pg_total_relation_size(c.oid)
         - pg_relation_size(c.oid)
         - pg_indexes_size(c.oid)
         - CASE WHEN c.reltoastrelid <> 0
                THEN pg_total_relation_size(c.reltoastrelid) ELSE 0 END AS auxiliary_bytes,
       s.n_live_tup AS live_rows_estimate,
       s.n_dead_tup AS dead_rows_estimate,
       s.last_vacuum,
       s.last_autovacuum,
       s.last_analyze,
       s.last_autoanalyze
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables AS s ON s.relid = c.oid
WHERE c.relkind IN ('r', 'm', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY pg_total_relation_size(c.oid) DESC NULLS LAST;

\echo 'Largest application indexes; idx_scan is only since the displayed stats reset'
SELECT clock_timestamp() AS measured_at_utc,
       d.stats_reset,
       i.schemaname,
       i.relname AS table_name,
       i.indexrelname AS index_name,
       pg_relation_size(i.indexrelid) AS index_bytes,
       i.idx_scan,
       i.idx_tup_read,
       i.idx_tup_fetch
FROM pg_stat_user_indexes AS i
LEFT JOIN pg_stat_database AS d ON d.datname = current_database()
ORDER BY pg_relation_size(i.indexrelid) DESC
LIMIT 100;

\echo 'Per-table tuple activity; counters are cumulative, not rates'
SELECT clock_timestamp() AS measured_at_utc,
       d.stats_reset,
       s.schemaname,
       s.relname AS table_name,
       s.n_live_tup AS live_rows_estimate,
       s.n_dead_tup AS dead_rows_estimate,
       s.n_tup_ins AS tuples_inserted_since_stats_reset,
       s.n_tup_upd AS tuples_updated_since_stats_reset,
       s.n_tup_hot_upd AS hot_updates_since_stats_reset,
       s.n_tup_del AS tuples_deleted_since_stats_reset,
       s.last_autovacuum,
       s.last_autoanalyze,
       pg_total_relation_size(s.relid) AS total_bytes
FROM pg_stat_user_tables AS s
LEFT JOIN pg_stat_database AS d ON d.datname = current_database()
WHERE s.relname IN (
    'laws', 'law_versions', 'legal_nodes', 'source_snapshots', 'law_changes',
    'history_events', 'hydration_jobs', 'job_outbox', 'source_registry',
    'senate_proceedings', 'jurisdictions'
)
ORDER BY pg_total_relation_size(s.relid) DESC;

\echo 'Per-source last successful catalog checkpoint summary; compare captures for intervals'
SELECT id AS source_id,
       adapter,
       status,
       last_checked_at,
       scope ->> 'last_success_at' AS last_success_at,
       scope ->> 'records_expected' AS records_expected,
       scope ->> 'records_enumerated' AS records_enumerated,
       scope ->> 'records_in_database' AS records_in_database,
       scope ->> 'new_records' AS last_run_new_records,
       scope ->> 'updated_records' AS last_run_updated_records,
       scope ->> 'last_page' AS last_completed_page,
       scope ->> 'pages_expected' AS pages_expected,
       CASE WHEN json_typeof(scope -> 'page_checkpoints') = 'array'
            THEN json_array_length(scope -> 'page_checkpoints') END AS saved_page_checkpoints
FROM public.source_registry
ORDER BY last_checked_at DESC NULLS LAST, id;

\echo 'Exact table row counts; bounded by statement_timeout but scans each named table'
SELECT 'laws' AS table_name, count(*) AS exact_rows FROM public.laws
UNION ALL SELECT 'law_versions', count(*) FROM public.law_versions
UNION ALL SELECT 'legal_nodes', count(*) FROM public.legal_nodes
UNION ALL SELECT 'source_snapshots', count(*) FROM public.source_snapshots
UNION ALL SELECT 'law_changes', count(*) FROM public.law_changes
UNION ALL SELECT 'history_events', count(*) FROM public.history_events
UNION ALL SELECT 'hydration_jobs', count(*) FROM public.hydration_jobs
UNION ALL SELECT 'job_outbox', count(*) FROM public.job_outbox
UNION ALL SELECT 'source_registry', count(*) FROM public.source_registry
UNION ALL SELECT 'senate_proceedings', count(*) FROM public.senate_proceedings
UNION ALL SELECT 'jurisdictions', count(*) FROM public.jurisdictions
ORDER BY table_name;

\echo 'Snapshot object-pointer coverage; requires migration 20261006_0011'
SELECT storage_backend,
       (object_key IS NOT NULL) AS has_object_key,
       (raw_body IS NOT NULL) AS has_raw_body,
       count(*) AS snapshot_rows,
       count(*) FILTER (WHERE size_bytes IS NOT NULL) AS rows_with_size_metadata,
       sum(size_bytes) AS declared_uncompressed_bytes
FROM public.source_snapshots
GROUP BY storage_backend, (object_key IS NOT NULL), (raw_body IS NOT NULL)
ORDER BY snapshot_rows DESC;

\echo 'Hydration jobs by type/status and age; no error or payload columns are selected'
SELECT job_type,
       status,
       CASE WHEN created_at >= now() - interval '1 day' THEN '<=1 day'
            WHEN created_at >= now() - interval '7 days' THEN '1-7 days'
            WHEN created_at >= now() - interval '30 days' THEN '7-30 days'
            ELSE '>30 days' END AS age_band,
       count(*) AS jobs,
       min(created_at) AS oldest_created_at,
       max(updated_at) AS newest_updated_at,
       count(*) FILTER (WHERE lease_until > now()) AS currently_leased
FROM public.hydration_jobs
GROUP BY job_type, status, age_band
ORDER BY job_type, status, age_band;

\echo 'Outbox dispatch state and age; dispatched does not prove Redis consumer acknowledgement'
SELECT CASE WHEN dispatched_at IS NULL THEN 'pending_dispatch' ELSE 'dispatched' END AS dispatch_state,
       CASE WHEN created_at >= now() - interval '1 day' THEN '<=1 day'
            WHEN created_at >= now() - interval '7 days' THEN '1-7 days'
            WHEN created_at >= now() - interval '30 days' THEN '7-30 days'
            ELSE '>30 days' END AS age_band,
       count(*) AS outbox_rows,
       min(created_at) AS oldest_created_at,
       max(dispatched_at) AS newest_dispatched_at
FROM public.job_outbox
GROUP BY dispatch_state, age_band
ORDER BY dispatch_state, age_band;

\echo 'Current lock/activity summary; query text and parameters are deliberately omitted'
SELECT state,
       wait_event_type,
       wait_event,
       count(*) AS sessions,
       count(*) FILTER (
           WHERE xact_start < now() - interval '5 minutes'
       ) AS transactions_older_than_5m
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;

\echo 'Cumulative temporary I/O counters since database stats reset'
SELECT datname,
       stats_reset,
       temp_files,
       temp_bytes,
       deadlocks,
       blk_read_time,
       blk_write_time
FROM pg_stat_database
WHERE datname = current_database();

\echo 'Optional PostgreSQL 14+ cumulative WAL counters; these are not WAL disk occupancy'
SELECT stats_reset, wal_records, wal_fpi, wal_bytes, wal_buffers_full
FROM pg_stat_wal;

\echo 'Optional physical WAL directory total; permission or managed-service restrictions may reject this query'
SELECT count(*) AS visible_wal_files,
       COALESCE(sum(size), 0) AS current_wal_directory_bytes,
       max(modification) AS newest_wal_file_mtime
FROM pg_ls_waldir();

\echo 'Optional current temporary-directory files; visibility/permissions vary by managed service'
SELECT count(*) AS visible_temp_files,
       COALESCE(sum(size), 0) AS current_temp_directory_bytes,
       max(modification) AS newest_temp_file_mtime
FROM pg_ls_tmpdir();
