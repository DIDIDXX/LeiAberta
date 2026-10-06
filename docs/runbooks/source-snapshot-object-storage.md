# Source snapshot object storage rollout

This is an additive storage path for archived source response bytes. PostgreSQL `source_snapshots.raw_body` remains present and is the fallback. The rollout does **not** reclaim database disk while that column remains populated; reclamation requires a separately reviewed follow-up migration after verification and a restore point.

## Storage behavior

- Object keys are content-addressed from SHA-256 of the raw, uncompressed response bytes: `SOURCE_SNAPSHOT_S3_PREFIX/sha256/<first-two-hex>/<sha256>`.
- Identical content shares one object key. Existing objects are read and hashed before reuse. New objects are uploaded, read back, and hashed before a pointer can be saved.
- Database rows gain nullable `storage_backend`, `object_key`, and `size_bytes` fields. `size_bytes` records the uncompressed body length. `raw_body` is retained.
- Reads verify object bytes against the row checksum. On missing config, transport error, or checksum mismatch the application logs the failed object read and serves the retained `raw_body` copy. If both paths are unavailable, the read raises an error.
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

Do not reuse backup credentials unless the bucket policy strictly restricts them. Prefer object-store permissions scoped to this bucket/prefix. Application writes need read/head/put. Lifecycle deletion is intentionally not automated.

## Rollout

1. Deploy code and apply Alembic revision `20261006_0011` (adds three nullable columns only). It does not rewrite existing rows or touch `raw_body`.
2. Initially keep the new variables absent. Existing behavior remains database-only, and object pointers, if present, still fall back to PostgreSQL.
3. Configure a staging bucket and credentials, then write/read one known test object and confirm that a wrong checksum is rejected. Do not test by modifying a legal snapshot.
4. Run a bounded dry-run in the intended application environment; dry-run is the command default and does not contact S3 or write database state:

   ```bash
   python scripts/migrate_source_snapshots_to_object_storage.py --batch-size 25 --after-id 0
   ```

5. Review candidate count, total bytes, invalid rows, and cursor. Investigate any checksum mismatch without changing the row.
6. For a reviewed batch, explicitly pass `--apply`. The command uploads at most 100 rows (default 25) per invocation, reads each object back, verifies SHA-256, then commits the object pointers for that batch. If any S3 operation fails, SQL pointers in the batch roll back; already-uploaded content-addressed objects are safe orphans and retryable.

   ```bash
   python scripts/migrate_source_snapshots_to_object_storage.py --apply --batch-size 25 --after-id 0
   ```

7. Continue with the last emitted `last_id` as `--after-id`. Rows with an `object_key` are skipped, so reruns are idempotent. A corrupt/mismatched database row is reported in `invalid` and receives no pointer.
8. Verify pointer counts and sampled/full object reads plus checksums, then monitor read-fallback and write-failure log events. Keep the PostgreSQL bytes until a separately reviewed data-removal rollout passes its own backup/restore and integrity gates.

## Rollback

- For new-write rollback, remove/disable the `SOURCE_SNAPSHOT_S3_*` application configuration. New rows return to DB-only storage; existing objects remain untouched.
- For read-path rollback, disable object access or roll application code back. Existing `raw_body` remains available and the reader uses it as fallback.
- The additive Alembic downgrade removes only the three pointer metadata columns; it does not delete object data or `raw_body`. Roll application code back to a pre-migration release before downgrading, because code using the new model selects those columns. Downgrading after pointer population loses metadata but preserves source bytes in PostgreSQL, so run only with an explicit owner decision.
- Do not delete bucket objects during rollback. No automated object deletion is part of this change.

## Capacity and cost

- This change duplicates source bytes across Postgres and the bucket while in migration/rollback window. It can temporarily increase total storage usage and adds object API requests/egress.
- PostgreSQL capacity is unchanged until a later reviewed migration removes verified database payloads. No compression or cost saving is claimed here.
- Measure real candidate bytes, object storage pricing, and read/egress patterns before planning that destructive follow-up.
