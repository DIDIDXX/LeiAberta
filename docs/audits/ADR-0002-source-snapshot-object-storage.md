# ADR-0002: Content-addressed object storage for source snapshots

- **Status:** Accepted as an additive implementation; production rollout and payload removal are deferred.
- **Date:** 2026-10-06
- **Owners:** LeiAberta maintainers

## Context

`source_snapshots.raw_body` stores complete upstream response bytes in PostgreSQL. Those bytes are valuable legal-source evidence and must remain retrievable. Current production relation sizes are unavailable, so this ADR does not assert that snapshots are the largest space consumer or promise a storage-cost reduction. PostgreSQL is recovering from an incident and the database/object migration must happen only after service health and backup integrity are re-established.

## Decision

Add an optional S3-compatible, content-addressed replica for raw source bytes. The object key is derived from SHA-256 of the raw bytes (`<prefix>/sha256/<digest-prefix>/<digest>`), so identical bodies share a deterministic key. Preserve `raw_body` in the initial rollout and treat it as the authoritative fallback.

The additive database metadata is nullable: `storage_backend`, `object_key`, and `size_bytes`. Object-store configuration is opt-in and uses a dedicated source-snapshot bucket separate from the database-backup bucket. Missing configuration keeps the existing database-only behavior.

Object writes validate the source checksum, check whether the deterministic key already exists, and read object bytes back to verify SHA-256 before the application writes a database pointer. HTML/XML/JSON and `text/*` use deterministic standard gzip; binary payloads remain uncompressed. The S3 object records the raw MIME type and `ContentEncoding`. Readers decompress when indicated, verify the original bytes against the snapshot checksum, and fall back to retained `raw_body` on object errors only if that database copy independently verifies against the same checksum. If neither copy verifies, the read raises an integrity error instead of serving unverified evidence. New captures also keep the raw body in PostgreSQL. Upload failures therefore preserve existing operation/evidence in the database; failed SQL commits can leave harmless reusable objects.

Existing rows are copied with a small restartable command. It is dry-run by default, processes at most 100 rows per invocation (default 25), validates each database body before upload, verifies each uploaded object before setting a pointer, and leaves source bytes untouched. A batch SQL failure rolls back its pointers; already uploaded objects are content-addressed and retryable. Rows with a pointer are skipped on subsequent runs.

## Rollout and retention

1. Restore stable PostgreSQL operation and establish a current verified backup/isolated restore point.
2. Apply Alembic revision `20261006_0011`, which only adds nullable metadata fields.
3. Test against a staging bucket, including a deliberate checksum mismatch and database fallback.
4. Measure `source_snapshots` table/TOAST size and candidate body bytes before predicting capacity benefit.
5. Start with the default dry run; review row count, byte count, checksum errors, and cursor. Apply small batches only with explicit `--apply` and coordinator authorization.
6. Verify pointer coverage and object checksums, monitor object read/write fallback errors, and retain the database copy through the rollback window.
7. Keep bucket retention non-expiring during the migration/rollback period. Do not automate object deletion.
8. Do not implement job/outbox cleanup as part of this ADR. Preserve queued/running/leased jobs, all undispatched or Redis-pending outbox work, and the latest succeeded job for each `(law_slug, job_type)`. Failed jobs younger than 180 days are retained. Terminal rows older than 180 days are only candidates after a read-only size/status/age inventory, current checksum-verified and isolated-restored backup, dry-run report that rules out Redis PEL entries and latest-success markers, preserved audit summary, and explicit coordinator approval. The existing outbox has no ACK field (`dispatched_at` records `XADD`, not ACK), so pending state must be verified in Redis. No cleanup command is included.

Removing `raw_body` is explicitly outside this ADR's implementation. It needs a separate decision after full pointer coverage and checksum verification, a current tested backup, reader monitoring, a restore/cutover plan, measured disk benefit, and explicit approval. A failed or unavailable object read must not become unrecoverable by prematurely deleting PostgreSQL bytes.

## Consequences

- Before any later payload-removal migration, the system holds duplicate copies and can use more total storage and S3 requests/egress. Text object copies are gzip-compressed; DB bytes remain unchanged. This ADR does not free PostgreSQL space.
- Verified object reads add network latency and depend on object-service availability; retained DB fallback preserves availability while the duplicate exists.
- Content addressing supports deduplication and safe retries, but does not by itself enforce provider-side immutability. Restrict bucket write/delete permissions and consider provider versioning/object lock if supported and operationally appropriate.
- Snapshot sizes, object pricing, egress, request rate, DB relation sizes, and net savings are not measured; no cost reduction is claimed.
- The three-column Alembic downgrade is structurally additive, but application code that selects these fields must be rolled back before dropping them. Object data and `raw_body` remain untouched by that downgrade.

## Rollback

- Disable the optional `SOURCE_SNAPSHOT_S3_*` configuration or revert to a pre-migration app version; retained `raw_body` remains available.
- Keep all uploaded objects during rollback. Do not delete them as a response to a failed deployment or checksum error.
- If dropping the additive schema, first roll back all code that maps/selects the new fields, then run the migration downgrade. The downgrade drops metadata columns only; it does not delete legal bytes.
- Reattempt only after investigating access, endpoint, checksum, and database-commit failures. A mismatched object is not overwritten automatically; preserve it for investigation.

## Alternatives considered

- **Keep snapshots only in PostgreSQL:** lowest operational complexity, but does not provide an independent object replica if snapshot payloads prove to be a material database storage consumer.
- **Move and delete all raw bodies in one migration:** rejected. It risks evidence loss, requires per-object verification, can produce unbounded locks/transactions, and would eliminate the simple fallback/rollback path.
- **Compress database bodies in place:** deferred until actual relation/TOAST measurements show expected gains; it still leaves the payload in PostgreSQL and would require a separate encoding/read migration.
