# Agent

Agente 1 — db-emergency-storage

# Branch

`codex/db-emergency-storage`

# Base SHA

`22ab2262678e040879f6220bae4f5c4c23afc4aa`

## Findings

- PostgreSQL is in an active disk exhaustion incident. Railway's PostgreSQL log at 2026-10-06 01:08 UTC shows repeated crash recovery followed by `PANIC: could not write to file "pg_logical/replorigin_checkpoint.tmp": No space left on device`.
- DB queries and routes are known to fail from the coordinator's revalidation. Railway's deployment `SUCCESS` status is not evidence of database readiness.
- The application stores source response bytes in PostgreSQL: `SourceSnapshot.raw_body` is `LargeBinary` (`bytea` on PostgreSQL). Parsed legal text is also relational in `legal_nodes.text`; `law_versions` supplies version identity and checksums. These latter records and verified evidence are not cleanup candidates.
- This agent's Railway connector offers infrastructure status, logs, and service metrics, but no SQL/query or volume filesystem interface. Railway CLI is not installed in this workspace. Therefore this run cannot honestly identify the largest relations, TOAST tables, indexes, dead tuples, retained job counts, replication/WAL usage, or open connections.
- There is no storage evidence to support deletion of source snapshots, legal versions, changes, evidence, or queue records. No retention policy change or migration is justified without relation sizing and state counts.

## Measurements

Read-only Railway measurements for project `ac5c9188-a792-4d4a-99d6-512740aec73e`, environment `b415a556-41ec-4f33-994f-1f5d38b633a1`:

| Measurement | Observed value | Evidence / limitation |
| --- | ---: | --- |
| PostgreSQL volume allocation | 5,000 MB | `postgres-volume`, mounted at `/var/lib/postgresql/data` |
| PostgreSQL current disk | 4.996513792 GB | Railway `DISK_USAGE_GB`, 24-hour metrics read; ~99.93% of nominal 5 GB |
| PostgreSQL maximum disk in window | 4.996521984 GB | 1,441 samples |
| PostgreSQL average disk in window | 2.845913793 GB | Includes earlier lower-usage time; not representative of present headroom |
| Nominal remaining volume capacity | ~0.00349 GB (~3.49 MB) | Arithmetic from the reported current/5 GB values; Railway/OS accounting may differ |
| Headroom to 20% free target | ~1 GB additional capacity or safe reclamation | Target corresponds to <=4 GB occupied on a 5 GB volume |
| PostgreSQL memory, current / average / max | 2.145 / 1.964 / 3.421 GB | Railway 24-hour metrics |
| Last restore-verified dump observed in service logs | 2026-10-05 09:10:36Z | `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`; 247,073,141 bytes; SHA-256 `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`; completion 09:15:50Z, `restore_verified=True` |
| Backup service schedule / region | `0 3 * * *` UTC / `asia-southeast1-eqsg3a` | Latest service deployment is `SUCCESS`; this does not certify a current backup object |
| Backup artifact freshness | Unverified | No object list/HEAD/read-only S3 query is available through this connector. The last observed verified artifact is about 16 hours before this check. |
| Postgres, web, Redis regions | `asia-southeast1-eqsg3a` | Railway environment inventory |
| Worker region | `us-east4-eqdc4a` | Cross-region; no migration/cutover performed by this agent |

At initial inspection, production had a pre-existing staged delete for service `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276`. The coordinator subsequently discarded that staged delete without touching the live service, then staged a volume-only increase for `postgres-volume` from 5,000 MB to 6,500 MB (`destructive=false`). The resize remains staged and is not live because Railway requires 2FA to commit it. This agent did not stage, accept, or otherwise apply either Railway change.

## Decisions

- Do not run `VACUUM FULL`, `REINDEX`, `TRUNCATE`, `DELETE`, migrations, or volume resizing from this worktree/agent.
- Do not infer the largest table from the model alone. `source_snapshots.raw_body` is a plausible high-volume source because it stores complete fetched responses, but only live relation/TOAST sizing can establish that.
- The outage leaves only ~3.49 MB nominal free. With no measured safe deletion set, a minimum coordinated volume increase is the only immediately supportable way to recover filesystem headroom without dropping legal evidence. The production owner must determine the smallest allowed increase, its price, and apply it.
- The coordinator's staged 6,500 MB capacity is consistent with the headroom recommendation: 1.5 GB nominal additional capacity; at the observed usage, roughly 1.50 GB or 23.1% free. It is not active until the coordinator completes Railway 2FA and commits the staged patch.
- After database service recovery, use the protected read-only inventory below before selecting cleanup or an object-storage migration.
- Keep the existing known-good backup until a newer backup has both verified upload and isolated restore. `SUCCESS` on the scheduled backup deployment is insufficient.

## Changes

- Added this handoff with observed storage, restart-loop and backup evidence, explicit measurement limitations, and a read-only sizing/retention investigation sequence.
- No application behavior, database schema, data, Railway configuration, or production state was changed.
- No storage/retention code change is proposed from this agent because its benefit and safety cannot be validated without live table measurements.

## Files touched

- `docs/swarm/db-emergency-storage.md`

## Tests

- Documentation-only change; no automated test suite was run.
- Read-only inspection performed via Railway environment inventory, 24-hour service metrics, and PostgreSQL/backup deployment logs.
- No direct SQL query was possible in the available tools. Exact SQL requested from the coordinator is provided below; run only after the database can accept reads and through an approved read-only connection.

Read-only relation, TOAST and index sizing:

```sql
SELECT c.relname,
       pg_total_relation_size(c.oid) AS total_bytes,
       pg_relation_size(c.oid) AS heap_bytes,
       pg_indexes_size(c.oid) AS index_bytes,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_pretty
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC;
```

```sql
SELECT schemaname, relname, indexrelname,
       pg_relation_size(indexrelid) AS bytes,
       idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

```sql
SELECT relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_autoanalyze,
       pg_total_relation_size(relid) AS total_bytes
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

After access returns, separately measure `source_snapshots` row count and `octet_length(raw_body)` distribution/sum, plus job counts by status/age and outbox rows by dispatched state. Run bounded/timeout-protected aggregate reads; avoid full payload selection. Query-based sizes will not include every volume consumer such as WAL, temporary files, filesystem reserve, or non-`public` objects, so reconcile totals against Railway disk metrics.

## Production impact

- This work had no production write or deploy impact.
- Production remains at risk until the staged resize is applied after 2FA, Postgres recovers, and readiness/core route checks pass. The resize is only staged; live capacity remains 5,000 MB and this agent did not mutate the live service.
- Existing last known-good backup metadata is evidence of a prior successful restore test only; it is not proof of the current bucket object, current recoverability, or a post-incident backup.

## Migration impact

- None created or run.
- Potential future additive source-snapshot migration: add nullable backend/object-key/size metadata while preserving existing `raw_body`; dual-read; copy in small restartable batches to immutable content-addressed bucket keys; verify SHA-256 against each row; switch reads only after sampled and complete integrity checks; retain DB bytes through a monitored rollback window; only then plan a separately reviewed removal migration. Do not put this in a single blocking transaction.
- Migration sizing is unmeasured. Existing backup/restore and no-free-space conditions make this a post-recovery task, not an emergency patch.

## Cost impact

- No change, invoice lookup, or cost claim from this agent.
- Required capacity recovery increases allocated storage cost. Exact minimum supported increment and price are not available in the connector; coordinator should record before/after allocation and Railway's displayed price.
- A bucket migration could reduce PostgreSQL growth while increasing object storage/request/egress charges. Current snapshot bytes, compression ratio, bucket price, and source-read request rate are unmeasured, so no savings estimate is defensible.

## Risks

- Current storage exhaustion can prevent WAL/checkpoint/recovery writes and produce repeated database restarts; the logs already show this failure mode.
- The older verified dump may omit writes after its snapshot time. Freshness and bucket-object presence are unverified.
- Deleting raw snapshots before verified external copies would remove source evidence. Deleting terminal jobs/outbox rows without state/age and foreign-key/operational review could interfere with retry or audit behavior.
- `VACUUM FULL` and index rebuilds require additional free space and can lock tables; they are not emergency compaction techniques for this state.
- Volume growth restores operational margin but does not fix continuing data growth.

## Rollback

- No rollback is required for this documentation-only change.
- The coordinator can leave the resize staged if 2FA is unavailable; no live capacity change has occurred. If committed, treat the increase as durable/non-shrinkable under Railway volume behavior.
- For a future object migration, roll back the application read path to `raw_body` while retaining both the additive pointer fields and verified objects. Never delete source payloads in the same rollout that switches readers.
- A Railway volume increase is generally not shrinkable; treat it as a durable cost decision and contain future growth through measured retention/storage redesign.

## Dependencies on other agents

- Coordinator / sole production owner: recover Postgres, decide on the smallest safe volume capacity increase if there is no verified cleanup candidate, and validate health/ready/routes before resuming normal work.
- Coordinator with approved SQL read access: capture relation/TOAST/index and dead-tuple sizes, key table counts, transaction/WAL state, and job/outbox state; provide read-only evidence to this agent before any cleanup or migration proposal.
- Backup owner: confirm the latest successful dump and manifest are present in `leiaberta-backups` and that their size/checksum match logs; run isolated restore verification before authorizing cleanup.
- Worker-cost agent: keep bulk producers capped until database headroom is stable. This agent did not inspect or change worker queue state.

## PR / commit

- Documentation-only PR requested by the coordinator; no runtime/storage code or deployment change is included.
- Branch `codex/db-emergency-storage`, based on `22ab2262678e040879f6220bae4f5c4c23afc4aa`.
