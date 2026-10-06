# D — Backup and restore operations handoff

## Ownership and revision

- Branch: `codex/final-backup-restore`
- Worktree: `/Users/andrecruz/Documents/LeiAberta-wt-backup-restore`
- Base SHA: `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`
- Final branch SHA: reported by the coordinator after this handoff commit is merged/cherry-picked.
- Production access or mutation: none. The coordinator remains the only production operator.

## Changes

- `scripts/backup_postgres_to_s3.py` now compares a deterministic schema signature on isolated restore in addition to core row counts and Alembic revisions. Its inventory covers public columns, constraints and validation state, indexes, triggers, sequences, views, enum labels, and installed extensions.
- The dump object is checked by HEAD byte size and sequential GET/read-back SHA-256. Object metadata also records the expected SHA. The uploaded manifest is read back and compared byte-for-byte; its exact-byte SHA is included in the completion log and returned result.
- Retention now runs only after isolated restore, dump-object read-back, and manifest read-back have passed. With `BACKUP_VERIFY_RESTORE` unset/false, the job records an unverified restore and skips destructive retention.
- `pg_dump` now uses the common timeout/error wrapper, which masks both SQLAlchemy and libpq forms of the database URL from command diagnostics.
- Temporary restore cleanup keeps the directory if PostgreSQL cannot be confirmed stopped, instead of deleting files while a server might still be running. Restore duration is recorded in validation metadata.
- `docs/runbooks/backup-restore.md` documents the verified-backup gates, current-state reinspection, isolated manual restore, retention behavior, object-storage boundary, and RPO/RTO limits.

## Evidence and tests

- `/tmp/leiaberta-backup-venv/bin/pytest -q tests/test_backup_postgres_to_s3.py` — 9 passed.
- `/tmp/leiaberta-backup-venv/bin/python -m compileall -q scripts/backup_postgres_to_s3.py` — passed.
- `git diff --check` — passed.
- Local PostgreSQL 14 exercise: created a temporary source cluster and custom-format dump; restored it through `_verify_restore` into a second isolated temporary PostgreSQL cluster; row counts, Alembic revision, and schema signature matched. Reported local restore duration was 0.359 seconds for the small synthetic fixture. Both temporary clusters were stopped and removed.
- The exercise used a synthetic database and local PostgreSQL 14. It did not use production credentials, Railway, a Railway object bucket, the production dump, or the production container image.

## Production impact, risk, and dependencies

- No production impact from this branch before deployment. No production service, database, bucket object, or backup was inspected or mutated.
- Verified daily runs now read the full uploaded dump back from S3-compatible storage. This proves actual stored bytes, but adds one full object read per verified backup; measure its duration and any provider egress charge. The snapshot bucket still needs a separate durability and restore check because the SQL dump contains pointers, not external snapshot bodies.
- Restore verification requires compatible PostgreSQL server binaries and temporary disk for an expanded isolated restore. The Docker image currently pins PostgreSQL 18; validate that image and available temporary storage in the current service before treating the next production run as proof.
- The production operator must confirm the current `postgres-backup` source DB reference, deployed SHA, `BACKUP_VERIFY_RESTORE=1`, bucket settings, current job completion, object size/SHA, manifest SHA, restore verification, retention result, and restore cleanup. None of those runtime facts are established by this local work.
- Retention remains destructive by design after all gates pass and still depends on the configured prefix/days being correct. Do not change retention settings or remove old database/backup services as part of this handoff.

## Dependencies and rollback

- The coordinator must deploy/integrate this branch before these checks apply to the Railway backup job, then execute and inspect one post-change one-shot backup before calling it verified.
- If deployment or a post-change backup is unhealthy, roll back the backup-service image/commit to the prior known-good revision; retain all current and older dump/manifest objects. A failed verification skips retention. No schema migration is introduced.
- Files changed: `scripts/backup_postgres_to_s3.py`, `tests/test_backup_postgres_to_s3.py`, `docs/runbooks/backup-restore.md`, and this handoff.
