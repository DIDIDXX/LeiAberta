# Final stabilization checklist

Legend: **Pass** = evidence recorded; **Pending** = needs post-deploy evidence; **Blocked** = requires owner decision or a durability/operational gate.

## Safety and capacity

- [x] Re-inspect current services, volumes, buckets, routes, database references and Railway pending changes.
- [x] Confirm `web`, `worker`, and backup use `postgres-blue`; verify Alembic head `20261006_0011` and controlled reads/writes.
- [x] Measure DB, relations, TOAST, indexes, WAL and database-to-volume gap; avoid destructive SQL.
- [x] Capture historical growth evidence: catalog laws rose by 821,980 in ~10.7h during SAPL enumeration while snapshot count was nearly flat.
- [x] Set hourly catalog refresh check and verify worker backfill off/concurrency 1.
- [ ] Run 30–60-minute representative limited-sync soak after final worker deploy; capture 15/30/60-minute disk and workload metrics.
- [ ] Confirm new deployment SHA and recheck pending changes before any Railway apply.

## Snapshots and physical storage

- [x] Production migration logs report 14,200 verified updates in 569 apply batches; 14,202 current DB rows point to S3.
- [x] Full in-container GET/decompress/SHA-256 audit via application verifier passed for all 14,201 unique object keys; no missing or orphan objects.
- [x] Measure snapshot payload: 252,709,304 raw DB bytes, 93,536,256-byte TOAST relation, 107,683,840-byte total snapshot relation.
- [x] Retain `raw_body`; no physical reclaim claimed (0 bytes). Estimated potential internal reuse is small versus the dominant `laws` relation.
- [ ] Define external-object durability/retention and recoverability before any payload nulling.
- [ ] Prove bucket-only dual-read in an isolated environment before any payload nulling.

## Backup and rollback

- [x] Current backup targets `postgres-blue`; existing daily cron is restored at `0 3 * * *` UTC, restart policy `NEVER`.
- [x] Read back full 336,161,242-byte dump and match SHA-256; earlier production job reports isolated restore success and row counts.
- [ ] Deploy strengthened backup verification and run one post-change backup with dump readback, manifest readback, schema signature, constraints and isolated restore verified.
- [ ] Reconfirm daily cron after the one-shot run; preserve previous good backups.
- [x] Keep old Postgres intact pending owner approval. Current old service has a full volume and is logging disk errors; do not count it as a working rollback.

## Ingestion and product

- [x] Integrate bounded SAPL incremental probes and paged historical scan budgets with resumable checkpoints and tests.
- [ ] Production deploy and verify logs prove the exact worker SHA applies incremental probes and bounded bootstrap.
- [ ] Safely exercise one cold-law hydration request end-to-end and observe the real worker/job terminal result.
- [ ] Re-smoke all routes, public APIs, typo search and Art. 389 Why/Blame/Diff caveat on the deployed web SHA.
- [x] Pre-deploy real-production viewport/keyboard smoke passed at tested widths; E2E fixture suite passed locally.
- [x] Preserve legal-evidence caveat: Normas.leg.br transcription is classified nonofficial; primary-source before/after excerpts are not independently proven.

## Cost, cleanup and launch

- [x] Estimate live steady-state usage using a one-hour service sample and published Railway tariffs; mark billing invoice unavailable.
- [x] Include old database and object/bucket usage in cost scenarios; target $10–15/month is not currently met.
- [ ] After safe backup and restore proof, inspect and remove only the no-volume `source-snapshot-migration` and `postgres-blue-restore` services if they contain no unique evidence.
- [ ] Complete 24-hour observation or document a safe shorter rollback interval before any old database retirement.
- [ ] Obtain explicit owner approval before deleting the old Postgres service or volume; approval has not been given.
- [ ] Final decision: **NO-GO** until critical checks and owner action above are resolved.
- [x] No domain purchase, plan upgrade, VPS migration or social post was performed.
