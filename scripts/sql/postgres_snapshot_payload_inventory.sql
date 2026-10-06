-- Exact source_snapshots raw-body lengths without returning any raw payload.
-- This scan detoasts/reads each non-NULL bytea value to calculate octet_length;
-- run only on a responsive database with headroom, preferably at low traffic.
-- Run with psql: all statements are session-default read-only.

\timing on
\set ON_ERROR_STOP off

SET application_name = 'leiaberta_snapshot_payload_inventory_readonly';
SET default_transaction_read_only = on;
SET statement_timeout = '120s';
SET lock_timeout = '2s';

\echo 'Exact snapshot payload bytes and size bands; no body contents are selected'
WITH payloads AS (
    SELECT storage_backend,
           (object_key IS NOT NULL) AS has_object_key,
           (raw_body IS NOT NULL) AS has_raw_body,
           octet_length(raw_body)::bigint AS raw_bytes,
           size_bytes
    FROM public.source_snapshots
), sized AS (
    SELECT *,
           CASE WHEN NOT has_raw_body THEN 'NULL payload'
                WHEN raw_bytes = 0 THEN '0 bytes'
                WHEN raw_bytes < 1024 THEN '<1 KiB'
                WHEN raw_bytes < 65536 THEN '1 KiB-64 KiB'
                WHEN raw_bytes < 1048576 THEN '64 KiB-1 MiB'
                WHEN raw_bytes < 10485760 THEN '1-10 MiB'
                ELSE '>=10 MiB' END AS payload_size_band
    FROM payloads
)
SELECT CASE WHEN GROUPING(storage_backend) = 1 THEN '(all backends)'
            ELSE COALESCE(storage_backend, '(null)') END AS storage_backend,
       CASE WHEN GROUPING(has_object_key) = 1 THEN '(all pointer states)'
            ELSE has_object_key::text END AS has_object_key,
       CASE WHEN GROUPING(payload_size_band) = 1 THEN '(all payload sizes)'
            ELSE payload_size_band END AS payload_size_band,
       count(*) AS snapshot_rows,
       count(*) FILTER (WHERE has_raw_body) AS rows_with_raw_body,
       count(*) FILTER (WHERE NOT has_raw_body) AS rows_without_raw_body,
       count(*) FILTER (WHERE has_object_key) AS rows_with_object_pointer,
       sum(raw_bytes) AS raw_body_bytes,
       sum(size_bytes) AS declared_uncompressed_bytes,
       min(raw_bytes) AS smallest_raw_body_bytes,
       max(raw_bytes) AS largest_raw_body_bytes,
       count(*) FILTER (
           WHERE size_bytes IS DISTINCT FROM raw_bytes
       ) AS rows_where_size_metadata_differs
FROM sized
GROUP BY GROUPING SETS (
    (storage_backend, has_object_key, payload_size_band),
    (storage_backend, has_object_key),
    ()
)
ORDER BY GROUPING(storage_backend), storage_backend,
         GROUPING(has_object_key), has_object_key,
         GROUPING(payload_size_band), payload_size_band;
