# A-db-capacity handoff

## Ownership and status

- Scope: read-only capacity inventory SQL and disk-budget runbook guidance.
- Branch: `codex/final-db-capacity`.
- Base observed at start: `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`.
- Production access or database writes: none. No SQL from these scripts was run against production.
- Current production SHA, volume usage, relation sizes, WAL usage, locks, queue rows, and growth rate remain unmeasured by this agent. Historical values in older incident documents are not treated as current evidence.

## Findings from repository inspection

- `BACKGROUND_BACKFILL_MODE` defaults to `off` in `app/jobs.py:44-49`. The worker's text and history batch loops are guarded by `backfill_mode != "off"`, but the catalog refresh loop is separate (`app/worker.py:356-394`). It still schedules Senate, IBGE, ALESP, SINJ-DF, and SAPL refresh tasks.
- `CATALOG_REFRESH_CHECK_SECONDS` is clamped to at least 300 seconds and defaults to 3600 seconds (`app/worker.py:248`). Refresh checks start immediately when the worker loop starts.
- SAPL freshness is seven days (`app/catalog_sync/sapl.py:27-29,638-643`). A due sync fully paginates each configured SAPL catalog in pages of 100, commits per-page catalog and checkpoint data, and records per-run added/refreshed counts in source-registry JSON (`app/catalog_sync/sapl.py:721-763, 800-815`). `sync_all_sapl_catalogs` has a separate concurrency setting defaulting to 4 (`app/catalog_sync/sapl.py:821-834`), so `CATALOG_SYNC_CONCURRENCY=1` does not mean only one SAPL instance is processed at a time.
- Senate catalog freshness is 24 hours (`app/catalog_sync/senado.py:23,321-332`); ALESP and SINJ-DF use seven days (`app/catalog_sync/alesp.py:25`, `app/catalog_sync/sinj_df.py:27`). Their catalog refreshes also run independently of text-backfill mode.
- The catalog synchronization code proves that catalog enumeration and registry writes can continue with text backfill off. It does not establish actual production bytes or WAL per cycle. SQL and same-window Railway volume samples are required. Do not claim unchanged law rows all receive UPDATEs: PostgreSQL write/update volume and WAL amplification must be measured.
- `source_snapshots.raw_body` is a `bytea`-backed `LargeBinary`; pointer fields are nullable and `raw_body` remains present (`app/models.py:110-128`, migration `20261006_0011`). Object pointers alone do not reclaim PostgreSQL space.

## Changes

- Added `scripts/sql/postgres_capacity_inventory.sql`: read-only session defaults and bounded query timeouts; current database bytes; heap/index/TOAST/auxiliary relation sizes; top indexes; estimated live/dead rows; cumulative tuple activity; source-registry last-run/checkpoint summaries; bounded exact row counts; snapshot pointer/size metadata; job/outbox state and age; lock/activity summary; cumulative temp/WAL counters; optional physical WAL/temp directory totals.
- Added `scripts/sql/postgres_snapshot_payload_inventory.sql`: exact row counts, raw-body byte sums and size bands grouped by object pointer state, using `octet_length` only. It never returns payload contents.
- Expanded `docs/runbooks/postgres-disk-budget.md` with safe execution guidance, interpretation limits, a sampling method, and the code-backed reason catalog writes continue while backfill is off.

## SQL limits and production dependencies

- Neither script is a measured result. Run them only against the confirmed `postgres-blue` database after validating service-variable references and Alembic head.
- The general inventory's exact `COUNT(*)` union can scan all listed tables. Keep the statement timeout and run at low traffic if the database is pressured.
- The snapshot payload script is more I/O intensive: exact `octet_length(bytea)` may read/detoast all raw bodies. Run it separately only with safe headroom, or adapt to primary-key windows if it times out. It requires object-pointer columns from migration `20261006_0011`.
- `pg_stat_user_tables.n_live_tup` and `n_dead_tup` are estimates. Tuple/WAL/temp counters are cumulative since statistics reset; capture at least two timestamped samples and confirm `stats_reset` did not change before calculating rates.
- `pg_database_size` and relation sizes are not Railway volume usage. Reconcile them with the same-timestamp Railway metric; other databases, WAL, temporary files, filesystem metadata/reserve, and managed-service accounting can explain a gap.
- `pg_stat_wal` requires PostgreSQL 14+. `pg_ls_waldir()` and `pg_ls_tmpdir()` may be unavailable or permission-restricted on Railway; a permission error is not a zero reading. The scripts run statements independently so such optional errors do not roll back earlier results.
- Table counts require the repository's expected schema, including `senate_proceedings`; pointer queries additionally require revision `20261006_0011`. Validate `alembic_version` before relying on those blocks.
- These files do not determine that snapshots, jobs, or any other relation should be deleted/rebuilt. No cleanup, vacuum, index rebuild, or compaction is proposed.

## Validation, production impact, and rollback

- Validation performed: repository/schema/code-path inspection and `git diff --check` passed after the final edits. No PostgreSQL connection was available to this workstream, so SQL execution was intentionally not attempted.
- Not performed: production SQL, Railway metrics retrieval, SQL execution against a local PostgreSQL, tests, deploy, migration, bucket access, or any data change.
- Production impact: none.
- Rollback: revert this branch's added SQL files and runbook/handoff edits. All changes are documentation or SELECT-only SQL; no schema or data rollback is needed.
- Coordinator dependency: after confirming `postgres-blue` routing and head, run the general inventory through an authenticated read-only `psql` session; capture timestamped relation/tuple/WAL samples after 15/30/60 minutes; compare Railway disk at the same times; run exact snapshot payload sizing only after headroom is established. Include output evidence, metrics windows, and unavailability/permission notes in the final inventory report.

## Risk and decision note

No live byte consumer can be identified from repository inspection alone. The code makes ongoing full catalog enumeration a plausible write source while background text work is off, particularly due SAPL's paginated checkpoints and separate internal fan-out. Whether it materially explains the reported volume growth remains a production measurement question. Do not label source snapshots as the cause until exact payload totals are compared with TOAST/relation bytes, nor infer physical disk reclaim from `UPDATE raw_body = NULL`.
