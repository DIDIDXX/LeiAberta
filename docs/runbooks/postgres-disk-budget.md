# PostgreSQL disk budget and response

## Scope

Use this runbook for the Railway volume mounted at `/var/lib/postgresql/data`. Railway's deployment state (`SUCCESS`) is not a database health check: verify `/ready`, PostgreSQL runtime logs, HTTP routes, and the volume metric. Do not select deletion candidates from guesses about table size.

## Monitoring

In Railway's Observability dashboard, add a disk-usage monitor for the Postgres service/volume if the workspace plan exposes monitors. Configure email and in-app notifications at:

| Volume used | Severity | Required action |
| ---: | --- | --- |
| 70% | Warning | Record current/average/max usage and 24h growth; inspect database and table sizing; confirm a recent upload plus restore-verified backup. |
| 80% | Critical | Keep bulk backfill disabled; set worker `SAPL_FULL_SOURCES_PER_CYCLE=0` (or `SAPL_FULL_PAGES_PER_CYCLE=0`) to pause historical SAPL catalog enumeration while incremental probes and interactive work continue if there is headroom. Inspect write growth, WAL, jobs/outbox, and source snapshots with read-only queries. |
| 85% | Stop threshold | Set worker `BACKGROUND_BACKFILL_MODE=off`, `SAPL_FULL_SOURCES_PER_CYCLE=0`, and `SAPL_INCREMENTAL_SOURCES_PER_CYCLE=0`; pause other nonessential producers. Keep user-priority hydration only if DB health and headroom permit. Escalate before any cleanup. |

Railway's built-in monitor sends notifications; it does not pause jobs. This runbook is the operational backstop, not an application dependency on the Railway API. If no monitor feature is available on the plan, use the dashboard at least daily while disk exceeds 70%, and add a calendar/on-call owner to the service runbook.

## At 85% or rising rapidly

1. Verify database readiness and disk usage from independent signals; examine Postgres deploy logs for `No space left on device`, recovery loops, failed checkpoints, and connection failures.
2. Disable bulk producers/consumers first. `BACKGROUND_BACKFILL_MODE=off` does not stop the catalog refresh loop; inspect source-registry checkpoints and worker logs, then pause/limit non-essential full catalog enumeration if further writes threaten the disk budget. Preserve interactive jobs and resume catalog discovery gradually after headroom returns. Do not purge Redis streams or SQL rows to reduce queue counts.
3. Confirm the latest backup object and manifest exist and match recorded size/SHA; preferably restore to an isolated database. A green scheduled backup deployment alone is not proof.
4. Use bounded read-only queries to size relations, indexes, TOAST, dead tuples, source payload bytes, terminal jobs, and acknowledged outbox rows. Reconcile SQL relation totals with Railway disk use because WAL, temp files, filesystem reserve, and non-database files contribute to volume usage.
5. If the database cannot recover and no safe, verified cleanup target exists, add capacity to the existing volume using the smallest supported in-place increment. Review all staged changes; do not include service/volume deletion or unrelated configuration changes.
6. After recovery, make a fresh backup, confirm at least 20% free space (30% preferred), and observe disk trend before restarting optional background work. Leave bulk off in the default OSS steady state.

## SAPL catalog write budget

The worker separates recent-law discovery from historical catalog enumeration. Defaults per worker refresh cycle are eight incremental SAPL probes, one descending-ID page per probed source, at most four full-scan sources, at most five full-scan pages per source, twenty full-scan pages total, and a five-minute soft cycle budget. The refresh scheduler runs at most hourly by default. Full scans persist page checkpoints and report completion/progress separately; a deployment `SUCCESS` is not a scan-completion signal.

At 80%, setting either `SAPL_FULL_SOURCES_PER_CYCLE=0` or `SAPL_FULL_PAGES_PER_CYCLE=0` pauses historical enumeration while leaving recent-ID probes available. At the 85% stop threshold, set `SAPL_INCREMENTAL_SOURCES_PER_CYCLE=0` too, then restore the normal limits gradually only after the volume has headroom. These are temporary operator controls; they do not delete checkpoints or records. Restart the worker after changing service variables.

The incremental probe orders SAPL by descending numeric ID and imports records newer than the stored maximum. This is a best-effort fast path for monotonically assigned new records. It is not a source-guaranteed modified-since cursor: a newly published low-ID record or metadata correction depends on a completed periodic full scan. A full descending page made entirely of unseen IDs marks backlog and forces the full scan due. The worker emits separate incremental and full-scan progress logs.

## Safe sizing queries (read-only)

Run only after the database is responsive. Use a dedicated read-only role when available. The scripts below set a read-only session default, statement and lock timeouts, and avoid selecting payloads or job error text.

1. Confirm the intended database and Alembic head in a separate safe check, then run `scripts/sql/postgres_capacity_inventory.sql` from an already-authenticated `psql` session. It measures database size, table heap/index/TOAST/auxiliary bytes, top indexes, tuple estimates and cumulative activity counters, exact row counts, snapshot pointer counts/declared sizes, job/outbox age and status, active lock summary, and temporary/WAL counters where exposed.
2. The exact row-count section is a bounded `COUNT(*)` scan across the named application tables. It is read-only but can consume disk I/O; skip or run it during low traffic if the service is under pressure. `n_live_tup` in the table-size/activity sections is an estimate, not an exact count.
3. Run `scripts/sql/postgres_snapshot_payload_inventory.sql` separately only when the database has safe headroom and is responsive. `octet_length(raw_body)` must read/detoast each non-null bytea to calculate exact original payload lengths. It returns aggregates and size bands, never raw payload contents, but can create substantial read I/O. Its 120-second statement timeout bounds a single attempt; after a timeout, use bounded primary-key ranges during low traffic rather than repeatedly rescanning the whole table.
4. Capture snapshots of the table activity section at UTC timestamps at least 15 minutes apart, and again at 30/60 minutes when practical. Compare `n_tup_ins`, `n_tup_upd`, `n_tup_del`, `n_tup_hot_upd`, and relation bytes only when `stats_reset` is unchanged. These are database-wide table counters since reset, not per-source rates. Derive a sampled rate as delta / elapsed seconds; do not multiply a one-off incident workload into a monthly steady-state estimate.
5. Compare `pg_database_size(current_database())` and relation totals with the Railway volume metric at the same timestamps. SQL relation size excludes some physical volume consumers and accounting overhead, including other databases, WAL, temporary files, filesystem overhead, and reserved space. `pg_ls_waldir()`/`pg_ls_tmpdir()` may be denied by managed-service permissions; a permission error means “not visible,” not zero usage. `pg_stat_wal.wal_bytes` and `pg_stat_database.temp_bytes` are cumulative counters, not current directory occupancy.

The exact snapshot query requires the object-pointer columns from migration `20261006_0011`. The object pointer, raw-body row count, and `size_bytes` totals do not prove object integrity; use the snapshot migrator's full read-back SHA verification for that. Preserve legal rows and payloads until external-object integrity and a current isolated restore are separately established.

### Interpret growth with producer state

`BACKGROUND_BACKFILL_MODE=off` prevents the text and history batch-enqueue loops from running, but does not stop catalog refresh. In the repository at `eb7cea7`, the worker continues scheduling Senate, IBGE, ALESP, SINJ-DF, and SAPL catalog refreshes at `max(300 seconds, CATALOG_REFRESH_CHECK_SECONDS)` (default 1 hour). SAPL's per-source catalog freshness is 7 days; a refresh enumerates all pages, writes page checkpoints to `source_registry`, and syncs catalog records in 100-record pages. `sync_all_sapl_catalogs` has its own concurrency setting (default 4), separate from `CATALOG_SYNC_CONCURRENCY` in the worker. Therefore, text-backfill-off is compatible with continuing catalog additions and registry writes. It does not by itself explain a particular number of bytes: use table activity deltas, relation sizes, source-level sync logs, and volume samples before attributing growth. Repeated full catalog enumeration is visible in code; exact no-op update/WAL amplification must be measured rather than assumed.

The catalog refresh paths also differ: Senate metadata freshness is 24 hours; ALESP and SAPL default to 7 days. Catalog pages are not text hydration. Do not pause all catalog refresh indefinitely to reduce writes; cap expensive bootstrap/enumeration first, preserve incremental discovery, and resume gradually after disk headroom is proven.

## Prohibited emergency shortcuts

- Do not run `VACUUM FULL`, `REINDEX`, broad `DELETE`, `TRUNCATE`, or a schema migration while the volume is at capacity or before backup and lock/space impact are understood.
- Do not delete legal text, versions, changes, checksums, source URLs, provenance, or source snapshots before verified content-addressed copies exist.
- Do not claim a backup is current because its service/deployment status is `SUCCESS`.
- Do not resume continuous backfill to prove the system works. Prove interactive hydration, catalog discovery, and controlled HOT behavior independently.

## Recovery acceptance

Close the incident only after Postgres accepts connections; readiness and critical API smoke checks pass; the disk stays below the agreed budget; a new backup is confirmed; bulk work is paused; worker memory and queue state are stable; and there are no new disk-full logs during a meaningful observation window. Record timestamps, metric windows, commit SHA, and rollback actions in `docs/reports/p0-db-full-incident.md`.

## Estado operacional — 2026-10-06 19:50 UTC

Medição atual do serviço Postgres azul: 65.7% no último ponto e pico de 66.1% na janela de 1 h; todas 61 amostras ficam abaixo de 70%. A janela inclui um ciclo SAPL que processou 20 páginas/4.000 registros; o delta total de disco foi pequeno (max 3.3036 GB e último 3.2868 GB), sujeito a WAL/reuso.

O coordenador ajustou `SAPL_FULL_PAGES_PER_CYCLE=4` (deploy `d0f1361b-eda1-41b6-b7c3-9bfcd6036869` SUCCESS; log real confirmou 4 páginas, 8 probes, zero erros) enquanto preserva probes incrementais. Um ciclo/h sem erros dá no máximo aproximado de 9.600 linhas paginadas/dia, mas retries podem adiantar ciclo; não é controle rígido por bytes. Monitorar antes/depois do deploy. Em 70% alertar/revisar SQL e growth; 80% pausar bulk full-catalog não essencial; 85% interromper produtores não essenciais e tratar como P0. A aplicação não lê métricas Railway e não há auto-pause confiável. Nunca executar `VACUUM FULL`, `REINDEX` ou `pg_repack` sem espaço/lock/runbook medidos.
