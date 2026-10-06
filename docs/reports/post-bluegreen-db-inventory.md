# Post blue/green database inventory

**Captured:** 2026-10-06, production; values below are measurements, not historical incident estimates.
**Target:** Railway `postgres-blue`, service `25805d38-02bf-4180-adf3-0f30c82849de`; 5 GB volume, region `asia-southeast1-eqsg3a`.
**Git at inspection:** `main` = `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`; production database schema at Alembic `20261006_0011`.

## Routing and health

Sanitized Railway variable-reference inspection confirmed `web`, `worker`, and `postgres-backup` route to the private `postgres-blue` service and database `railway`. Controlled SQL reads and normal service writes succeeded. The old `Postgres` service remains attached to its 5 GB volume at `4.996513792 GB` used. Logs show `PANIC: could not write to file "pg_logical/replorigin_checkpoint.tmp": No space left on device`; that service is not considered a working fallback. It has not been deleted or modified.

## Capacity snapshot

| Consumer | Bytes | Share of DB | Notes |
|---|---:|---:|---|
| `laws` | 2,330,796,032 | 82.56% | heap 1,868,562,432; indexes 460,251,136; TOAST 1,441,792 |
| `legal_nodes` | 331,358,208 | 11.74% | heap 77,201,408; indexes 24,838,144; TOAST 229,269,504 |
| `source_snapshots` | 107,683,840 | 3.82% | heap 8,806,400; indexes 5,308,416; TOAST 93,536,256 |
| Remaining relations | ~53,024,447 | ~1.88% | derived as difference from database size |
| **Database** | **2,822,862,527** | **100%** | `pg_database_size(current_database())` |
| WAL | 301,989,888 | — | 18 files visible from PostgreSQL |
| Railway volume used | 3.334324224 GB | 66.69% of 5 GB | at the Railway sample; DB+WAL leave ~0.21 GB unexplained by those two measures |

Postgres volume usage exceeds database size by roughly 0.511 GB. WAL accounts for about 0.302 GB; the rest may include other filesystem/runtime allocations. Railway did not expose a complete filesystem breakdown for temp files or all volume accounting, so those bytes are not assigned to a table. Do not subtract the WAL twice when reconciling the volume.

## Growth evidence and cause

Across an earlier ~10.7-hour sample, cataloged law rows rose from 1,105,140 to 1,927,120 (+821,980); source snapshots changed by one. Worker logs reported a completed SAPL enumeration over 589 sources and 1,392,607 records, without errors. `BACKGROUND_BACKFILL_MODE=off` pauses background text/history backfill, but catalog refresh has a separate loop. SAPL was paginated and wrote law/catalog/checkpoint state while the text backfill was off. This explains that rapid growth window. It does not prove all row updates were necessary or attribute exact WAL bytes to SAPL.

After setting the worker catalog check interval to one hour, 61 Railway disk samples over approximately one hour ranged from 3.334307840 to 3.334324224 GB (16,384-byte span). Treat this as a short low-activity interval, not a full representative post-release soak. The worker was observed with `BACKGROUND_BACKFILL_MODE=off` and concurrency 1. A bounded SAPL implementation is integrated in the candidate code: latest-ID probes for new rows plus resumable, time/page-limited historical scans. With a catalog of ~1.39 million rows, 20 full-scan pages/hour at 100 rows/page implies a best-case ~29 days for a complete sweep; there is no modified-since upstream cursor, so historical edits or low-ID insertions have delayed discovery until their bounded rescan.

## Snapshot storage and reclaim decision

Current DB counts: 14,202 snapshots; all 14,202 have `storage_backend='s3'` and a non-null `object_key`. One of 14,201 unique objects is referenced twice by rows with the same checksum. Sum of DB `raw_body` payload lengths: 252,709,304 bytes. Snapshot TOAST: 93,536,256 bytes. Bucket inventory: 14,201 objects, 64,972,169 stored bytes; this includes compressed objects. At 2026-10-06 17:42 UTC, an in-container audit using the application's `SourceSnapshotObjectStore.read_verified()` downloaded, decompressed and SHA-256 checked all 14,201 unique objects against the DB pointers: zero missing, zero orphan, zero mismatched, zero errors; 252,701,649 unique-object raw bytes verified. A duplicate pointer shared by two rows explains the difference from the summed DB payload bytes. An earlier standalone audit helper erroneously reported mismatch; it was discarded after the application verifier passed the single-record sample and the full set. Raw payloads were never printed.

The existing production migration's logs say 14,200 rows updated and readback-verified across 569 batches; it did not clear `raw_body`. All payloads remain present in PostgreSQL. Reclaim performed: **0 bytes**. The maximum likely internal reclaim from TOAST is ~93.5 MB (about 3.3% of database size and 1.9% of a 5 GB volume); physical volume shrink would not follow automatically. Since `laws` is ~2.33 GB and snapshots are ~0.108 GB total, nulling snapshot payloads is not a material fix for the current main consumer. D1/D2 gates are intentionally not passed: no bucket versioning/lifecycle or separate object backup/restore strategy exists, and bucket-only dual-read has not been tested against an isolated restore.

## Jobs, WAL and observability limits

Latest backup snapshot counts: 30,667 `hydration_jobs`, 30,653 `job_outbox`, and 4,049 `history_events`. Earlier production snapshot: 14,135 `law_versions`, 620 `source_registry`; the current backup records those same values. The worker stream contained 38,304 retained entries with zero pending at the capture. These counts represent retained history/queue state, not current queued work. PostgreSQL statistics counters are cumulative since `stats_reset`; without a before/after interval and unchanged reset time they are not per-cycle idempotency evidence. The current SQL inventory and runbooks include exact counts, table/index/TOAST breakdown, tuple stats, checkpoints, locks, and bounded WAL/temp visibility queries.

## Next actions

1. Append complete S3 object audit results.
2. Capture full 15/30/60-minute disk, table and WAL samples after final worker deployment.
3. Verify bounded sync activity on the exact deployed SHA; watch growth before increasing scan budgets.
4. Leave `raw_body` populated unless object durability, readback, retention, restore and bucket-only behavior are proven and the expected reclaim justifies the operational risk.
5. Keep the old database until its fate is explicitly approved; do not treat it as a healthy rollback while the volume is full and it logs filesystem errors.
