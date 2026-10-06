# PostgreSQL backup and restore runbook

## What a verified backup means

The backup runner is `scripts/backup_postgres_to_s3.py`. A usable backup is the exact dump object plus its JSON manifest, with a matching byte count and SHA-256, an isolated restore that completes without errors, matching core row counts, matching Alembic revisions, and a matching schema signature. A green Railway deployment alone is not evidence of a usable backup.

The runner now performs these checks in order:

1. Read database metadata without selecting row payloads. The manifest records core table counts, relation sizes, job/outbox status counts, Alembic revisions, and a schema inventory/signature covering public columns, constraints, indexes, triggers, sequences, views, enum labels, and installed extensions.
2. Create a custom-format dump with `pg_dump`, compute SHA-256, and restore it into an isolated temporary local PostgreSQL instance using `pg_restore --jobs=2 --exit-on-error`.
3. Compare core row counts, Alembic revisions, and schema signature between source and isolated restore. A completed restore is marked `restore_verified=true`; failures do not reach retention cleanup.
4. Upload the dump with its checksum as object metadata, check the object size, and stream the object back to recompute SHA-256 over the actual stored bytes. It then uploads and reads back the exact manifest bytes.
5. Apply retention only after isolated restore and object/manifest read-back validation pass. If `BACKUP_VERIFY_RESTORE` is false or unset, the run may create a checksum-verified object and manifest, but it skips retention and records `restore_verified=false`.

The runner verifies only the PostgreSQL dump. A SQL backup contains object-storage pointers and metadata; it does not contain the legal snapshot payloads in `leiaberta-source-snapshots`. Keep the snapshot bucket's durability/retention and a sample object restore check as separate operational requirements.

## Production run inspection

The coordinator must reinspect the current Railway service configuration and deployment SHA before relying on this runbook. Do not infer current variable references, schedule, source database, restore state, or service activity from a previous run.

The previous recorded run was on 2026-10-05: `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`, 247,073,141 bytes, SHA-256 `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`, with `restore_verified=true`. This is historical evidence only; it does not prove a backup after that point or identify the current production target.

For each current run, capture these non-secret fields from the logs and bucket:

- exact Railway deployment SHA and completion timestamp;
- confirmed source DB service/reference (never paste a connection string);
- dump object key, bytes, SHA-256, read-back result, and manifest key;
- manifest SHA-256, `restore_verified`, counts, schema signature, Alembic revisions, and restore duration;
- retention count, and whether retention was skipped;
- isolated restore outcome and temporary PostgreSQL cleanup outcome.

Required settings are `DATABASE_URL`, `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`, and `BACKUP_S3_REGION`. Optional settings are `BACKUP_S3_ADDRESSING_STYLE` (defaults to `path`), `BACKUP_S3_PREFIX`, `BACKUP_RETENTION_DAYS` (minimum 7; defaults to 30), `BACKUP_VERIFY_RESTORE` (must be truthy for restore validation and retention), and `LOG_LEVEL`. Never print or copy secret values.

The restore image must include PostgreSQL server tools (`initdb`, `pg_ctl`, `pg_restore`) compatible with the source dump. The repository's `Dockerfile.backup` currently uses PostgreSQL 18. Restore verification requires temporary disk space for the expanded database. The runner uses two restore jobs and a 3600-second `pg_restore` timeout; if that limit is exceeded, investigate dump/table timing, available disk, and compute before considering a carefully measured timeout change. Do not increase timeouts blindly. If stopping the temporary server fails, the runner preserves its temporary directory and logs its path instead of deleting files under a possibly live server.

## Isolated manual restore

Use this when validating an already stored object independently of the scheduled runner. Download to a restricted temporary directory with adequate free space. Keep the dump and manifest out of the repository. Confirm manifest `dump_key`, byte count, and SHA-256 before restore. Never use a production URL as the restore target.

```sh
sha256sum /restricted/tmp/backup.dump
stat -f '%z bytes' /restricted/tmp/backup.dump   # macOS; use `stat -c '%s bytes'` on Linux
initdb --pgdata /restricted/tmp/restore-data --username=postgres --auth-local=trust --auth-host=trust
pg_ctl --pgdata /restricted/tmp/restore-data --options '-h 127.0.0.1 -p 55432' --wait start
createdb --host=127.0.0.1 --port=55432 --username=postgres leiaberta_restore_check
pg_restore --jobs=2 --exit-on-error --no-owner --no-privileges \
  --host=127.0.0.1 --port=55432 --username=postgres \
  --dbname=leiaberta_restore_check /restricted/tmp/backup.dump
```

Compare all manifest core row counts, the Alembic revision set, and schema signature/inventory. Also inspect `pg_constraint.convalidated`, run read-only application smoke checks against the isolated database if the environment is configured, record elapsed restore time, stop PostgreSQL, and remove temporary files only after evidence is captured. The script's automated drill enforces `pg_restore --exit-on-error`, core row counts, revisions, and schema signature; this manual checklist adds the opportunity to inspect data/application behavior.

## Recovery and rollback

Never automatically overwrite a production database after a failed deploy. First record active deployments, variable references, attached volumes, migration head, queue state, and the newest independently verified backup. Preserve the existing database and the last known-good dump. Restore a selected dump to a new isolated service/volume, verify the manifest SHA and schema/data checks, and only then plan an explicitly reviewed cutover with a rollback target.

This repository does not automate Railway service/volume replacement, PITR, bucket-object restoration, or a complete disaster recovery cutover. The current code's restore drill is local to the backup container; it proves dump readability and data/schema consistency but does not prove a replacement Railway database can be provisioned or switched over. A failed isolated restore blocks marking that backup verified and blocks deleting earlier known-good backups.

## Retention, RPO, and RTO

The daily backup schedule was previously observed as `0 3 * * *` UTC, but the coordinator must verify the current schedule and target. A daily schedule gives a nominal backup point gap approaching 24 hours only if every run finishes and the newest backup is independently usable. This is not a zero-loss guarantee. Report actual RPO from observed successful backup timestamps. RTO is the measured elapsed time to restore and validate; a `pg_restore` timeout means RTO is not yet established. Retention configuration and total bucket inventory must be read from the current service/bucket, not inferred from defaults.

The dump object read-back adds a full object read per verified backup; track its duration and storage-provider egress/cost. Do not annualize one-time restore compute as steady-state workload. The backup is a scheduled one-shot; a completed verification run must not be left running as resident compute.
