# Final stabilization worklog

**Environment:** Railway production, project `ac5c9188-a792-4d4a-99d6-512740aec73e`, environment `b415a556-41ec-4f33-994f-1f5d38b633a1`
**Execution date:** 2026-10-06 (UTC)
**Coordinator:** sole production operator; agents A–E investigated and implemented in isolated branches.

## Timeline and evidence

- **Start:** re-fetched GitHub `main`; observed `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`. Inspected current Railway services, volumes, buckets, deployments, and pending changes. Pending changes were empty. `web`, `worker`, and `postgres-backup` point by Railway reference to `postgres-blue`; production database name is `railway`. No production schema migration was needed; Alembic was at `20261006_0011`.
- **Capacity gate:** read-only SQL on `postgres-blue` measured database size 2,822,862,527 bytes, Railway volume 3.334324224 GB of 5 GB, 18 WAL files / 301,989,888 bytes, and top relations: `laws` 2,330,796,032 bytes, `legal_nodes` 331,358,208 bytes, `source_snapshots` 107,683,840 bytes. There were no destructive SQL operations, full vacuum, or index rebuilds.
- **Growth cause:** in the earlier 10.7-hour window, `laws` rose from 1,105,140 to 1,927,120 rows while the snapshot count changed by one. Worker logs recorded SAPL catalog enumeration across 589 sources and 1,392,607 records with text backfill off. Catalog enumeration and checkpoint writes are independent of text/history backfill. This explains the rapid period; it does not establish the exact WAL bytes per source.
- **Pressure control:** worker deployed with `CATALOG_REFRESH_CHECK_SECONDS=3600`, catalog/hydration concurrency 1, and `BACKGROUND_BACKFILL_MODE=off`. One-hour disk samples after this change (61 samples) ranged 3.334307840–3.334324224 GB, a 16,384-byte span. This limited window is not the required post-final-deploy 30–60 minute soak.
- **Snapshot state:** existing migration service logs report apply-mode completion: 569 batches, 14,200 rows updated and verified, 252,381,702 raw bytes, zero invalid rows, zero failures. Current inventory has 14,202 rows, all with S3 pointers and `raw_body` still populated. Bucket inventory reports 14,201 unique objects and 64,972,169 stored bytes; a distinct-key/duplicate is shared by two identical checksums.
- **Backup:** current blue database backup created 2026-10-06T17:14:25Z. Dump object size 336,161,242 bytes; SHA-256 `b899bb4f28ae6e21d947136273a2389f90322c824d532aed3958db20be5d620e`; manifest says `restore_verified=true`, Alembic `20261006_0011`, with key counts recorded in `docs/reports/final-cost-and-stability.md`. The downloaded full dump matched the manifest SHA. The strengthened schema-signature and stored-object readback implementation is integrated locally but still requires production execution to claim that stronger gate.
- **Product QA:** pre-change production smoke at 17:26 UTC passed the requested public routes/APIs, typo search, Article 389/history/Blame/Why/Diff, and tested viewports. It found that Why/Blame overstated the Normas.leg.br archived transcription as official. E corrected the copy and added a local E2E assertion; production revalidation is pending deployment.
- **Integration:** agents A–E used dedicated worktrees and branches; coordinator merged their work locally into `codex/final-stabilization-integration` (`a3b01a6` before this report). Full Python suite: 209 passed, 6 upstream warnings. Playwright E2E: 5 passed. `compileall` and `git diff --check` passed. These are local checks and do not prove deployment behavior.
- **State at 17:35 UTC:** no Railway staged changes; old Postgres remains attached and untouched, but its nearly full volume logs `No space left on device` in a replication-origin checkpoint and is not a healthy rollback target. No old volume or bucket was deleted. Snapshot `raw_body` was not nulled; physical disk reclaimed: 0 bytes.

## Final storage integrity audit (17:42 UTC)

- First standalone audit helper reported 14,201 SHA mismatch errors despite a direct in-container sample passing. I discarded that helper output as invalid and reran the audit inside the production worker container using the application's `SourceSnapshotObjectStore.read_verified()` for each distinct key, which downloads, honors `Content-Encoding: gzip`, decompresses, and compares SHA-256.
- Final canonical audit: 14,202 DB pointer rows; 14,201 unique keys; 14,201 bucket objects under the prefix; 0 missing, 0 orphan, 14,201 read and SHA-256 verified, 0 errors; 64,972,169 stored bytes and 252,701,649 unique-object raw bytes verified. One duplicate pointer reference accounts for the difference from the summed DB raw bodies.
- A production sample independently confirmed the DB payload hash equals its recorded checksum and its bucket object's decompressed hash; raw payload itself was never printed.

## Next coordinator checkpoints

Append exact commit/PR and Railway SHAs, production checks, strengthened one-shot backup/restore proof, 30–60-minute disk samples, and temporary-service disposition. Keep the final launch decision NO-GO until every blocker in `CHECKLIST.md` is resolved or explicitly accepted by the owner.
