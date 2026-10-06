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
- Relation-level size and state counts remain unavailable. I have implemented only an additive, reversible snapshot-storage foundation: it preserves every `raw_body`, dual-reads verified object bytes with a database fallback, and offers bounded dry-run-by-default migration batches. It does not establish that snapshots are the largest relation or that moving them will reclaim capacity.

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

- Do not run `VACUUM FULL`, `REINDEX`, `TRUNCATE`, `DELETE`, migrations, or volume resizing from this worktree/agent. The Alembic revision and batch script are committed as code only; neither was run against production.
- Do not infer the largest table from the model alone. `source_snapshots.raw_body` is a plausible high-volume source because it stores complete fetched responses, but only live relation/TOAST sizing can establish that.
- The outage leaves only ~3.49 MB nominal free. With no measured safe deletion set, a minimum coordinated volume increase is the only immediately supportable way to recover filesystem headroom without dropping legal evidence. The production owner must determine the smallest allowed increase, its price, and apply it.
- The coordinator's staged 6,500 MB capacity is consistent with the headroom recommendation: 1.5 GB nominal additional capacity; at the observed usage, roughly 1.50 GB or 23.1% free. It is not active until the coordinator completes Railway 2FA and commits the staged patch.
- The new snapshot storage foundation is optional: with all `SOURCE_SNAPSHOT_S3_*` settings absent it stays database-only. Do not create a bucket, set secrets, apply migrations, or invoke `--apply` until the coordinator authorizes a post-recovery rollout.
- After database service recovery, use the protected read-only inventory below before selecting cleanup or claiming expected capacity savings.
- Keep the existing known-good backup until a newer backup has both verified upload and isolated restore. `SUCCESS` on the scheduled backup deployment is insufficient.

## Changes

- Added an additive nullable Alembic revision for `storage_backend`, `object_key`, and `size_bytes`; it does not change `raw_body` nullability or contents.
- Added content-addressed SHA-256 S3-compatible storage with read-after-write verification, duplicate-content reuse, checksum validation, and database fallback. New captures use the object store only when fully configured; a storage error leaves the DB copy as the source of truth.
- Added a one-batch, max-100-row migrator, dry-run by default. `--apply` must be explicit; each object is read back and verified before pointers are committed. Failed SQL commits can leave reusable object orphans; batch retry skips committed pointers.
- Updated source-document audit call sites to use the verified dual-read helper.
- No application data, Railway configuration, production database, bucket, or secret was changed. No migration was run.

## Files touched

- `docs/swarm/db-emergency-storage.md`
- `docs/audits/ADR-0002-source-snapshot-object-storage.md`
- `app/models.py`
- `app/storage/__init__.py`
- `app/storage/source_snapshots.py`
- `app/jobs.py`
- `app/main.py`
- `scripts/audit_archived_documents.py`
- `scripts/migrate_source_snapshots_to_object_storage.py`
- `migrations/versions/20261006_0011_source_snapshot_objects.py`
- `tests/test_source_snapshot_storage.py`
- `requirements.txt`
- `docs/runbooks/source-snapshot-object-storage.md`

## Tests

- `pytest -q tests/test_source_snapshot_storage.py tests/test_jobs.py tests/test_api.py tests/test_audit.py`: 41 passed, one existing Starlette/httpx deprecation warning.
- Local isolated SQLite migration check: `alembic upgrade head` adds all three nullable metadata columns; `alembic downgrade 20261005_0010` removes them and preserves the base schema.
- `python -m compileall` passed for changed Python modules; `git diff --check` passed.
- Read-only inspection performed via Railway environment inventory, 24-hour service metrics, and PostgreSQL/backup deployment logs.
- No production SQL query or object-store call was run. Exact SQL requested from the coordinator is provided below; run only after the database can accept reads and through an approved read-only connection.

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

- This work had no production write, deploy, migration, bucket, or secret impact.
- Production remains at risk until the staged resize is applied after 2FA, Postgres recovers, and readiness/core route checks pass. The resize is only staged; live capacity remains 5,000 MB and this agent did not mutate the live service.
- Existing last known-good backup metadata is evidence of a prior successful restore test only; it is not proof of the current bucket object, current recoverability, or a post-incident backup.

## Migration impact

- Created but did not run Alembic revision `20261006_0011` (`down_revision=20261005_0010`). It adds three nullable columns only; downgrade drops only these columns. An isolated SQLite upgrade/downgrade check passed.
- The batch migrator defaults to dry-run, processes <=100 rows/invocation (default 25), verifies the row checksum before upload and reads each object back to verify before pointer assignment. It commits one bounded batch and can resume from `last_id`; rows with `object_key` are skipped. It never changes/deletes `raw_body`.
- Existing snapshot counts and bytes are unmeasured. Running this online adds external writes and duplicate storage but does not free DB space. Treat rollout as post-recovery and separately authorized.

## Cost impact

- No production cost change, invoice lookup, or savings claim from this agent. `boto3` was added to the application dependency set; no production image was built from this branch.
- Required capacity recovery increases allocated storage cost. Exact minimum supported increment and price are not available in the connector; coordinator should record before/after allocation and Railway's displayed price.
- The current implementation retains both copies, so it increases object storage usage and may add request/egress costs without reducing PostgreSQL usage. Bucket and snapshot size/call volume are unmeasured; no savings estimate is defensible.

## Risks

- Current storage exhaustion can prevent WAL/checkpoint/recovery writes and produce repeated database restarts; the logs already show this failure mode.
- The older verified dump may omit writes after its snapshot time. Freshness and bucket-object presence are unverified.
- Deleting raw snapshots before verified external copies would remove source evidence. Deleting terminal jobs/outbox rows without state/age and foreign-key/operational review could interfere with retry or audit behavior.
- `VACUUM FULL` and index rebuilds require additional free space and can lock tables; they are not emergency compaction techniques for this state.
- Volume growth restores operational margin but does not fix continuing data growth.
- Object storage availability, credentials, bucket policy, and Railway S3 compatibility have not been tested; production integration remains off unless all configuration is supplied.
- External reads add latency and can fall back to the DB; no timeout/latency benchmark is included. DB fallback means the feature is not a disk-reclamation fix until a future, separately approved payload-removal migration.

## Rollback

- Runtime rollback: disable/remove the new `SOURCE_SNAPSHOT_S3_*` configuration or revert application code; the DB `raw_body` fallback stays available. The content objects are left untouched.
- The coordinator can leave the resize staged if 2FA is unavailable; no live capacity change has occurred. If committed, treat the increase as durable/non-shrinkable under Railway volume behavior.
- For a future object migration, roll back the application read path to `raw_body` while retaining both the additive pointer fields and verified objects. Never delete source payloads in the same rollout that switches readers.
- A Railway volume increase is generally not shrinkable; treat it as a durable cost decision and contain future growth through measured retention/storage redesign.

## Dependencies on other agents

- Coordinator / sole production owner: recover Postgres, decide on the smallest safe volume capacity increase if there is no verified cleanup candidate, and validate health/ready/routes before resuming normal work.
- Coordinator with approved SQL read access: capture relation/TOAST/index and dead-tuple sizes, key table counts, transaction/WAL state, and job/outbox state; provide read-only evidence before deciding whether to schedule any snapshot-copy batches.
- Coordinator: provision a dedicated source-snapshot bucket, evaluate object-store pricing/network access, and stage secrets/migration only after the Postgres incident is stable; this agent did not create or configure storage.
- Backup owner: confirm the latest successful dump and manifest are present in `leiaberta-backups` and that their size/checksum match logs; run isolated restore verification before authorizing cleanup.
- Worker-cost agent: keep bulk producers capped until database headroom is stable. This agent did not inspect or change worker queue state.

## PR / commit

- PR #84, open, base `main` at `22ab2262678e040879f6220bae4f5c4c23afc4aa`; updated to include the additive storage foundation, tests, and runbook. Not merged.
- Implementation is additive; no runtime rollout or Railway deploy is requested by this PR.
