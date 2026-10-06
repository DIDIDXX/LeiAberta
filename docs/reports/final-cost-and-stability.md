# Final cost and stability report

**Status:** execution in progress; values captured on 2026-10-06 UTC.
**Decision at this capture:** **NO-GO for public launch** pending the checks listed below.
**Repository baseline:** `main` was `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`; integrated candidate before this report was `a3b01a6` on `codex/final-stabilization-integration`. Exact merged/deployed SHAs must be appended after release verification.

## Stability, database and producer

`web`, `worker` and `postgres-backup` were confirmed by sanitized Railway reference names to use `postgres-blue` / database `railway`. Blue is PostgreSQL 18.6, Alembic `20261006_0011`; DB size 2,822,862,527 bytes, volume 3.334324224 of 5 GB (66.69%), WAL 301,989,888 bytes in 18 files. Largest relations: `laws` 2,330,796,032 bytes, `legal_nodes` 331,358,208, `source_snapshots` 107,683,840. The prior rapid increase was the large paginated SAPL catalog enumeration while text backfill was off, not a growing snapshot count. The worker check interval is now hourly; the short post-setting disk window was nearly flat, but a final deployed 30–60-minute workload soak is pending.

The worker currently runs `BACKGROUND_BACKFILL_MODE=off`, concurrency 1, and continues catalog refresh and interactive jobs. Candidate code bounds SAPL newest-ID probes and historical pages per cycle, preserves checkpoints, and logs partial progress. New high numeric IDs can arrive through incremental probes; low-ID changes and retroactive upstream edits wait for paginated historical rescans. At 20 pages/hour, one complete 1.39M-row catalog sweep could take about 29 days. This is a bounded eventual-discovery policy, not an instant update SLA.

The old Postgres still uses 4.996513792 GB of its 5 GB volume and logs a `No space left on device` panic. It remains intact because deleting it requires the owner's explicit approval, but it is not a safe rollback target in its current state.

## S3 migration and payload status

Production migration logs report `selected=14200`, `updated=14200`, `verified=14200`, `invalid=0`, across 569 apply batches, for 252,381,702 raw bytes. Current DB inventory: 14,202 S3 pointers, 14,201 unique keys, 252,709,304 raw DB payload bytes, 64,972,169 bucket-stored bytes. A 17:42 UTC in-container audit used the production application's `read_verified()` path on every unique key: 14,201/14,201 passed decompression and SHA-256, with zero missing objects, orphans, mismatches or errors; 252,701,649 unique-object raw bytes verified. One content-key duplicate is shared by two rows. A first standalone audit helper falsely reported universal mismatch and was discarded; the independent sample and full canonical recheck passed.

`raw_body` remains filled on all 14,202 rows. Physical bytes reclaimed: 0. The full snapshot relation is 107,683,840 bytes, while `laws` alone uses 2.33 GB. Even if all snapshot TOAST (93.5 MB) became reusable, that would be modest and would not shrink the Railway file automatically. No payload was nulled, no vacuum full/repack/reindex ran. Bucket versioning/lifecycle and independent restore strategy are not configured, and bucket-only dual-read has not passed an isolated restore; do not remove relational copies.

## Backup and recovery evidence

The latest production backup object is `postgres/leiaberta-production/20261006T171425Z-7a475cec.dump`, 336,161,242 bytes, SHA-256 `b899bb4f28ae6e21d947136273a2389f90322c824d532aed3958db20be5d620e`. Its manifest records `restore_verified=true` and Alembic `20261006_0011`; the full dump was downloaded and its checksum matched. Manifest row counts: laws 1,927,120; legal_nodes 211,496; source_snapshots 14,202; hydration_jobs 30,667; job_outbox 30,653; history_events 4,049; law_versions 14,135; source_registry 620. The daily backup cron has been restored at 03:00 UTC and the cron deployment settled SUCCESS.

This backup predates deployment of the locally integrated strengthened verification. The D branch now verifies dump object size and readback SHA, manifest readback and a deterministic public-schema signature (columns, constraints, indexes, triggers, sequences, views, enum labels and extensions) on isolated restore. A new run on that exact deployed SHA, with schema and constraint proof, remains pending. Previous dumps are retained.

## Product and legal evidence

Production checks at 17:26 UTC on web SHA `eb7cea7ddf22737b30bd4f21285f7ea15e26891d` passed `/`, health/readiness/worker health, stats, sources, typo search for `LGDP`, law 10.406/2002, Article 389 provenance, history, blame, change detail, `/fontes`, `/cobertura`, `/sobre`, OpenAPI and sitemap. Tested mobile/tablet/desktop layouts had no horizontal overflow; no page/console errors or HTTP 5xx were observed. Local Playwright E2E passed 5 tests; Python tests passed 209 with 6 upstream deprecation warnings.

Production's existing Why/Blame wording overstated the Normas.leg.br transcription as official. The candidate fixes its source label and preserves the caveat. The production recheck after deployment is pending. Art. 389 comparison remains `verified_source`, not `verified_primary`; the archived transcription is explicitly classified nonofficial, and exact primary-source excerpts before and after Lei 14.905/2024 have not been independently stored and proven. Do not elevate this legal evidence claim. A production cold-law hydration job has not yet been safely exercised end-to-end.

## Service and storage usage estimate

Observed one-hour average resources after recent stabilization (approximate, 60-second metric samples):

| Service | Avg CPU (vCPU) | Avg RAM (GB) | Current / peak RAM (GB) | Volume used |
|---|---:|---:|---:|---:|
| web | 0.0035 | 0.138 | 0.211 / 0.214 | none |
| worker | 0.0134 | 0.188 | 0.066 / 0.295 | none |
| postgres-blue | 0.0260 | 2.616 | 2.900 / 2.900 | 3.334 GB of 5 GB |
| old Postgres | 0.2335 | 0.191 | ~0.191 average; restart loop seen | 4.997 GB of 5 GB |
| Redis | 0.0025 | 0.014 | ~0.014 | 0.154 GB of 5 GB |

The sample for `postgres-backup` overlapped a one-shot verification task (peak 1.99 vCPU and 5.50 GB memory), so it was excluded from steady monthly compute and should not be multiplied by 730 hours. Daily backup resource time and network use recur at their schedule, but that job window is not a valid steady hourly sample.

Railway published tariffs used: CPU $20/vCPU-month, RAM $10/GB-month, volume $0.15/GB-month and service egress $0.05/GB; storage buckets $0.015/GB-month with bucket API and bucket egress free. See [Railway plans](https://docs.railway.com/pricing/plans) and [bucket billing](https://docs.railway.com/storage-buckets/billing). The bucket's roughly 1.36 GB occupied by backups and snapshots costs about $0.02/month at that bucket-storage rate. A rough CPU+RAM estimate from the service averages is about $37/month with the old database attached and $30.5/month after its compute is removed. Adding used-volume rates and bucket storage yields about $38.3 and $31.0/month before traffic egress and scheduled backup time. Including roughly $1.83/month web egress and $0.50/month daily-backup egress gives $40.2–$40.7 now and $32.9–$33.4 after old DB removal. Costs are estimates, not guarantees, and exclude unknown plan minimum/credits. Actual invoice access was unavailable. The aspirational $10–15 target is **not met**.

Volumes: blue 5 GB configured / 3.334 GB used; old Postgres 5 GB / 4.997 GB; Redis 5 GB / 0.154 GB (15 GB provisioned total, ~8.485 GB used). Buckets: backup ~1.295 GB and source snapshots ~0.065 GB (about 1.360 GB total). Temporary backup/restore and migration services have no mounted volumes; restore and migration replicas are zero at capture. Backup is daily. Old database currently adds an estimated ~$7–8/month between average compute and volume charges, while retaining a full, unhealthy service.

## Exact revisions and launch gates

At initial inspection `main` and all primary service deployments were on `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`; backup's latest scheduled deployment on that revision is `ea5b459b-e572-4f21-b975-c639bcdbeb83`. Current production deploy SHAs must be refreshed after the integrated PR is merged; update this report with per-service SHA and deployment ID before declaring release complete.

**Decision: NO-GO.** The remaining release gates are: final candidate deployment and production Why/Blame recheck; full bucket integrity audit result; strengthened post-change backup with schema signature and isolated restore; cold-law hydration through the real worker; representative disk soak and 24-hour observation; object retention/recovery strategy; and owner approval before removing the old DB. The old service has disk errors, so keep it intact for forensics while acknowledging it is not a reliable rollback. No old database, bucket, or legal payload was deleted.
