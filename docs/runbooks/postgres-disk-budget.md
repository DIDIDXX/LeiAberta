# PostgreSQL disk budget and response

## Scope

Use this runbook for the Railway volume mounted at `/var/lib/postgresql/data`. Railway's deployment state (`SUCCESS`) is not a database health check: verify `/ready`, PostgreSQL runtime logs, HTTP routes, and the volume metric. Do not select deletion candidates from guesses about table size.

## Monitoring

In Railway's Observability dashboard, add a disk-usage monitor for the Postgres service/volume if the workspace plan exposes monitors. Configure email and in-app notifications at:

| Volume used | Severity | Required action |
| ---: | --- | --- |
| 70% | Warning | Record current/average/max usage and 24h growth; inspect database and table sizing; confirm a recent upload plus restore-verified backup. |
| 80% | Critical | Keep bulk backfill disabled; inspect write growth, WAL, jobs/outbox, and source snapshots with read-only queries. Plan capacity or a verified storage migration. |
| 85% | Stop threshold | Set worker `BACKGROUND_BACKFILL_MODE=off` (once deployed) and all legacy bulk producer limits to `0`; keep catalog discovery and user-priority hydration available only if DB health and headroom permit. Escalate before any cleanup. |

Railway's built-in monitor sends notifications; it does not pause jobs. This runbook is the operational backstop, not an application dependency on the Railway API. If no monitor feature is available on the plan, use the dashboard at least daily while disk exceeds 70%, and add a calendar/on-call owner to the service runbook.

## At 85% or rising rapidly

1. Verify database readiness and disk usage from independent signals; examine Postgres deploy logs for `No space left on device`, recovery loops, failed checkpoints, and connection failures.
2. Disable bulk producers/consumers first. Preserve catalog refresh and interactive jobs where the database can still accept writes. Do not purge Redis streams or SQL rows to reduce queue counts.
3. Confirm the latest backup object and manifest exist and match recorded size/SHA; preferably restore to an isolated database. A green scheduled backup deployment alone is not proof.
4. Use bounded read-only queries to size relations, indexes, TOAST, dead tuples, source payload bytes, terminal jobs, and acknowledged outbox rows. Reconcile SQL relation totals with Railway disk use because WAL, temp files, filesystem reserve, and non-database files contribute to volume usage.
5. If the database cannot recover and no safe, verified cleanup target exists, add capacity to the existing volume using the smallest supported in-place increment. Review all staged changes; do not include service/volume deletion or unrelated configuration changes.
6. After recovery, make a fresh backup, confirm at least 20% free space (30% preferred), and observe disk trend before restarting optional background work. Leave bulk off in the default OSS steady state.

## Safe sizing queries (read-only)

Run only after the database is responsive. Use a statement timeout and a read-only connection where available.

```sql
SET statement_timeout = '10s';
SET default_transaction_read_only = on;

SELECT c.relname,
       pg_total_relation_size(c.oid) AS total_bytes,
       pg_relation_size(c.oid) AS heap_bytes,
       pg_indexes_size(c.oid) AS index_bytes,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_pretty
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC;

SELECT relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_autoanalyze,
       pg_total_relation_size(relid) AS total_bytes
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

Inspect row counts by job state/age and acknowledged outbox rows separately before proposing retention. Do not select large `raw_body` values in diagnostic queries; aggregate `octet_length(raw_body)` instead.

## Prohibited emergency shortcuts

- Do not run `VACUUM FULL`, `REINDEX`, broad `DELETE`, `TRUNCATE`, or a schema migration while the volume is at capacity or before backup and lock/space impact are understood.
- Do not delete legal text, versions, changes, checksums, source URLs, provenance, or source snapshots before verified content-addressed copies exist.
- Do not claim a backup is current because its service/deployment status is `SUCCESS`.
- Do not resume continuous backfill to prove the system works. Prove interactive hydration, catalog discovery, and controlled HOT behavior independently.

## Recovery acceptance

Close the incident only after Postgres accepts connections; readiness and critical API smoke checks pass; the disk stays below the agreed budget; a new backup is confirmed; bulk work is paused; worker memory and queue state are stable; and there are no new disk-full logs during a meaningful observation window. Record timestamps, metric windows, commit SHA, and rollback actions in `docs/reports/p0-db-full-incident.md`.
