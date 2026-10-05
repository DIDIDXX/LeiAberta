# Backup and restore runbook

Last exercised restore evidence: 2026-10-05, backup object `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`, 247,073,141 bytes, SHA-256 `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`, manifest `restore_verified=true`. This previous run restored to an isolated temporary PostgreSQL and compared core row counts and Alembic versions. It did not overwrite production.

## Backup path

Railway service `postgres-backup` runs the repository's `scripts/backup_postgres_to_s3.py` daily at `0 3 * * *` UTC. It uses `pg_dump --format=custom --compress=6`, computes SHA-256, records source database size/row counts/Alembic versions in a manifest, uploads dump + manifest to Railway Object Storage, and applies configured retention. A verified backup requires both successful upload and restore verification; a deployment status alone is insufficient.

1. Check Railway backup deployment logs for `postgres_backup_finished`, object key, byte count, checksum, `restore_verified=true`, and expired count. Do not copy secrets into notes.
2. Confirm both dump and JSON manifest exist in the bucket and the manifest checksum/size match the log. Keep at least one prior known-good backup until the new one is verified.
3. If the backup fails, inspect `pg_dump`, disk space, timeout and bucket connectivity; do not delete older backups to make a failed job look green.

## Isolated restore validation

Use a temporary isolated PostgreSQL instance or the backup service's `BACKUP_VERIFY_RESTORE=1` mode. The script starts a temporary local PostgreSQL, runs `pg_restore --exit-on-error`, and compares row counts for laws, law versions, nodes, history events, source snapshots, source registry, jobs, outbox, and Alembic revision set. Verify cleanup removes temporary data. Never point this test at production.

Manual restore checklist:

1. Download the chosen dump and manifest to a restricted temporary directory.
2. Verify SHA-256 and byte size before opening it.
3. Create an isolated PostgreSQL database with compatible major version/extensions and enough disk for the expanded restore.
4. Restore with `pg_restore --exit-on-error --no-owner --no-privileges --dbname <isolated-url> <dump>`.
5. Compare manifest row counts and Alembic revisions; run read-only API smoke against the isolated DB if practical.
6. Record restore duration, validation, and cleanup. Delete the isolated copy only after validation evidence is saved.

## Production recovery

Production overwrite is a separate incident action and must never be an automatic response to a failed deploy. Before recovery, capture current Railway deployment IDs, volume attachment, latest backup, migration revision, and a second backup of current state if readable. Prefer Railway Point-in-Time Recovery when available and documented for the current plan; otherwise restore into a new PostgreSQL service/volume first, verify, then perform a controlled cutover. Confirm a fresh backup, queue/worker pause policy, connection variables, migrations, and rollback target before swapping. This connector did not expose PITR controls or safe DB shell access during this audit, so actual disaster recovery cutover remains unexercised.

## RPO/RTO and retention

Daily schedule implies a nominal worst-case backup-point gap near 24 hours only if every run and upload completes; there is no verified zero-data-loss claim. RTO is unmeasured. Record actual restore time in a quarterly exercise. Confirm `BACKUP_RETENTION_DAYS` and bucket object inventory in Railway; values and total retention were unavailable through the read-only connector. Keep access limited and avoid logging database URLs or credentials.
