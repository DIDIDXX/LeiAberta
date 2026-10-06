# Source snapshot object storage rollout

This is an additive storage path for archived source response bytes. PostgreSQL `source_snapshots.raw_body` remains present and is the fallback. The rollout does **not** reclaim database disk while that column remains populated; reclamation requires a separately reviewed follow-up migration after verification and a restore point.

## Storage behavior

- Object keys are content-addressed from SHA-256 of the raw, uncompressed response bytes: `SOURCE_SNAPSHOT_S3_PREFIX/sha256/<first-two-hex>/<sha256>`. HTML, XML, JSON and `text/*` are stored with standard deterministic gzip (`ContentEncoding: gzip`); binary documents stay uncompressed. The original MIME string is recorded as `ContentType`, and the digest is checked after decompression.
- Identical content shares one object key. Existing objects are read and hashed before reuse. New objects are uploaded, read back, and hashed before a pointer can be saved.
- Database rows gain nullable `storage_backend`, `object_key`, and `size_bytes` fields. `size_bytes` records the uncompressed body length. `raw_body` is retained.
- Reads honor `ContentEncoding`, decompress gzip before hashing, and verify the original bytes against the row checksum. On missing config, transport error, decompression error, or object checksum mismatch, the application logs a bounded error type and serves `raw_body` only if its SHA-256 independently matches the same row checksum. If both copies are unavailable or invalid, it raises an integrity error rather than serving unverified evidence.
- New source captures are uploaded when complete object-store configuration is available. If upload/verification fails, the application retains the new source bytes in PostgreSQL and continues; the exception is logged without credentials or payload bytes.
- Upload succeeds before SQL pointer commit. A process/transaction failure may leave an unreferenced immutable object; a later retry safely reuses it.

## Preconditions

1. Recover PostgreSQL and verify readiness before considering this rollout. Do not use this object migration as emergency disk reclamation.
2. Confirm a current PostgreSQL backup and isolated restore verification. Keep the previous known-good backup.
3. Provision a **separate** S3-compatible bucket for source documents; do not mix it with `leiaberta-backups`.
4. Set these application/worker variables only through the production owner's approved secret-management process:

   - `SOURCE_SNAPSHOT_S3_ENDPOINT`
   - `SOURCE_SNAPSHOT_S3_ACCESS_KEY_ID`
   - `SOURCE_SNAPSHOT_S3_SECRET_ACCESS_KEY`
   - `SOURCE_SNAPSHOT_S3_REGION`
   - `SOURCE_SNAPSHOT_S3_BUCKET`
   - `SOURCE_SNAPSHOT_S3_PREFIX` (optional; defaults to `source-snapshots`)
   - `SOURCE_SNAPSHOT_S3_ADDRESSING_STYLE` (optional; defaults to `path`)

Do not reuse backup credentials unless the bucket policy strictly restricts them. Prefer object-store permissions scoped to this bucket/prefix. The app requires `get`, `head`, and `put` access. Some S3-compatible services return 403 rather than 404 for `HEAD` of a missing object unless `ListBucket` is allowed; scope any needed list permission to this prefix. In that case a write failure safely leaves the database copy in use. Lifecycle deletion is intentionally not automated.

## Rollout

1. Deploy code and apply Alembic revision `20261006_0011` (adds three nullable columns only). It does not rewrite existing rows or touch `raw_body`.
2. Initially keep the new variables absent. Existing behavior remains database-only, and object pointers, if present, still fall back to PostgreSQL.
3. Configure a staging bucket and credentials, then write/read a text round-trip, a binary object, and confirm that a wrong checksum is rejected. Do not test by modifying a legal snapshot.
4. The repository at the implementation SHA contains `scripts/migrate_source_snapshots_to_object_storage.py`; it does not contain the previously observed module `scripts.migrate_all_source_snapshots_to_object_storage`. Replace that service command with the script below. The command must include `--apply` to upload anything; omitting it is read-only dry-run. Do not run it as a permanently resident service: use a one-shot job or temporary run-and-stop service.

   Checkpoint files contain only IDs and aggregate counters. Point `--checkpoint` at a durable mounted path if the job must resume after process or machine replacement. The database pointers are authoritative and the runner is idempotent, so if a local checkpoint is lost, `--reset-checkpoint` safely rescans rows while skipping committed pointers. Never place bucket secrets in the checkpoint or command line.

5. Run a dry-run in the intended application environment; dry-run is the command default and does not contact S3 or write database state. It scans in bounded pages up to a fixed high-water ID and reports its aggregate at the end:

   ```bash
   python -u -m scripts.migrate_source_snapshots_to_object_storage --batch-size 25
   ```

6. Review candidate count, raw bytes, invalid IDs, and high-water ID. Investigate any checksum mismatch without changing the row.
7. For a reviewed migration, explicitly pass `--apply`. The runner processes the entire fixed ID range in SQL transactions of at most 100 rows (default 25) and approximately 64 MiB of uncompressed source data, emits a progress JSON line after every committed batch, and writes an atomic checkpoint. A single object larger than the byte budget is processed alone so it cannot starve the cursor. It uses bounded retries (default three retries after the first attempt) around each complete upload/read-back verification. If any S3 operation still fails, the current SQL batch rolls back and the checkpoint cursor does not advance; uploaded content-addressed objects are safe orphans and retryable.

   ```bash
   python -u -m scripts.migrate_source_snapshots_to_object_storage --apply --batch-size 25 --checkpoint /durable/path/source-snapshot-migration.json
   ```

8. Treat only final JSON `status: complete` as completion, and check that `pending_pointers_at_end` and `pointer_inconsistencies_at_end` are zero. `SUCCESS` from a job/deployment only means the process exited; it is not a migration metric. The report separates rows/bytes selected and verified, raw bytes, object references' stored bytes, newly created bucket bytes, reused content-addressed objects, retry attempts, invalid rows, elapsed time, high-water ID, and end-of-run pointers. A successful `put_verified` reads every selected object back and SHA-256 checks the decompressed payload before SQL commit.
9. A database-checksum-invalid row remains pending and makes the report `partial`; investigate it, then use `--reset-checkpoint` after correction/decision. Do not edit the checksum or source bytes just to clear the gate. On an upload failure, rerun with the same checkpoint. Rows with committed `object_key` pointers are skipped, so retries are idempotent. Existing object pointers outside this run's scanned range are counted but are not re-read by this migration; if independent revalidation is required, run a separate bounded audit before removing any DB payload.
10. Verify counts from the report against read-only SQL and retain the report/checkpoint. Keep PostgreSQL bytes until a separately reviewed data-removal rollout passes its own bucket-only test and backup/restore gates.

The migration report's `bucket_bytes_added` counts objects whose creation and read-back succeeded in this run. If a process dies after an S3 PUT but before its SQL commit/checkpoint, that orphan may later be reused and will not be counted as a new successful object in the resumed run. Use a bucket inventory or full object audit for exact total bucket occupancy; never infer it from migration counters alone.

## Rollback

- For new-write rollback, remove/disable the `SOURCE_SNAPSHOT_S3_*` application configuration. New rows return to DB-only storage; existing objects remain untouched.
- For read-path rollback, disable object access or roll application code back. Existing `raw_body` remains available and the reader uses it as fallback.
- The additive Alembic downgrade removes only the three pointer metadata columns; it does not delete object data or `raw_body`. Roll application code back to a pre-migration release before downgrading, because code using the new model selects those columns. Downgrading after pointer population loses metadata but preserves source bytes in PostgreSQL, so run only with an explicit owner decision.
- Do not delete bucket objects during rollback. No automated object deletion is part of this change.

## Capacity and cost

- This change duplicates source bytes across Postgres and the bucket while in migration/rollback window. It can temporarily increase total storage usage and adds object API requests/egress.
- PostgreSQL capacity is unchanged until a later reviewed migration removes verified database payloads. Gzip applies to object copies only; no database compression or cost saving is claimed here.
- Measure real candidate bytes, object storage pricing, and read/egress patterns before planning that destructive follow-up.

## Job and outbox retention gate

No job or outbox cleanup command is included or authorized by this rollout. Preserve all `queued` and `running` jobs, every non-null lease, all outbox rows with `dispatched_at IS NULL`, and any job whose Redis stream message is still pending/unacknowledged. `dispatched_at` alone means `XADD` succeeded; it is not proof of worker ACK. Also preserve the latest `succeeded` job for every `(law_slug, job_type)` because `queue_job()` uses that success marker to avoid unnecessary duplicate work. Do not delete failed rows younger than 180 days.

Only terminal rows (`succeeded`, `failed`, or `cancelled`) older than 180 days may be proposed for cleanup, and then only after all of these gates pass:

1. Read-only relation/row/age/status sizing confirms the target is material to storage; do not infer a benefit from row count alone.
2. A current backup is uploaded, checksum-verified, and successfully restored in isolation.
3. A dry-run candidate report excludes active/leased jobs, latest-success markers, undispatched outbox rows, Redis pending entries, and every failed row younger than 180 days.
4. Preserve an audit summary containing job ID, law slug/type, terminal status, timestamps, attempts and bounded error category before any deletion; never discard unique legal source/evidence data with queue housekeeping.
5. Obtain explicit coordinator approval, perform a small transaction-bounded batch, then verify counts, FK integrity, worker/outbox recovery and core routes.

The current outbox schema has no durable ACK field, so operator verification of Redis pending state is required; do not interpret `dispatched_at` as ACK. Cleanup stays unexecuted until SQL sizes/counts and backup/restore verification are available. No destructive cleanup script should be added without separate tests and coordinator review.
