# Technical audit

Date: 2026-10-05. Evidence combines the source at `94807cd`, the production baseline in this folder, `pytest`, and the prior Playwright run. Each severity is about observed impact, not theoretical possibility.

## Executive findings

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| T-01 | P1 | `/api/stats` issued three counts per source name; the SAPL registry can have hundreds of entries. Production request exceeded 20 seconds. | Fixed in this branch by one grouped law-table aggregate; production timing needs post-deploy confirmation. |
| T-02 | P1 | Sitemap loaded every law slug into memory and generated one URL set. Production took 7.09 seconds; a sitemap is limited to 50,000 URLs and 50 MB uncompressed. | Fixed in this branch with index + 10,000-URL shards. |
| T-03 | P1 | Typo fallback loaded every law and applied `SequenceMatcher` in Python. `LGDP` took 4.14 seconds at production scale. | Fixed in this branch: fuzzy suggestions now inspect at most 2,000 curated `hot` laws. Cold-catalog typo suggestions become less comprehensive by design. |
| T-04 | P1 | Postgres occupies 3.053/5 GB; relation breakdown and growth rate are not available through current connector. | Thresholds/runbook documented; no data deletion or unmeasured resize performed. |
| T-05 | P1 | Worker is deployed in US while Postgres/Redis/web are in Singapore; 24-hour worker memory peaked at 5.18 GB. | Documented; no region move or concurrency increase without latency/cost comparison and rollback. |
| T-06 | P1 | Law detail URL served a generic JavaScript shell without law-specific metadata or body for crawlers/JS-off users. | Fixed in this branch with canonical/Open Graph metadata and a bounded first-10-articles `<noscript>` section; needs deployed smoke. |
| T-07 | P1 | No distinct readiness probe verified schema version or worker heartbeat; `/health` checked only DB connectivity (`SELECT 1`). | Added `/ready`, which checks DB access and exact Alembic heads; 200/503 paths are tested. Railway deployment and a worker heartbeat endpoint remain separate follow-up work. |
| T-08 | P1 | Per-request public detail/nodes routes may enqueue work for uncached laws. Dedupe is durable and backfills are bounded, but there is no client-level rate limit/cooldown. | Remains open: Railway client-IP forwarding has not been verified end-to-end, so no untrusted forwarded header is used as identity. Queue caps, dedupe and backpressure exist in `app/jobs.py`. Add a limiter after verifying the edge trust boundary. |
| T-09 | P1 | `Law.description` and JSON aliases are not indexed for substring matching; regular full-text search can still scan the large law table. | Remains open pending `EXPLAIN (ANALYZE, BUFFERS)` and free disk capacity. A trigram GIN migration can materially increase storage and must be tested off production first. |
| T-10 | P2 | SQLAlchemy uses default per-process pool settings. One web + one worker could open up to the default pool plus overflow per process. | Remains open; max connections / observed activity unavailable, so no speculative pool changes. |
| T-11 | P2 | Python requirements are unpinned ranges; JS has `package-lock.json`. | Remains open; lock generation and vulnerability policy added via CI/Dependabot, but no Python lockfile chosen. |
| T-12 | P2 | Docker web image runs as root. `.dockerignore` excludes git, virtualenv, node modules, databases and env files. | Fixed in this branch by a non-root runtime user. Image build is checked in CI, pending Docker availability locally. |
| T-13 | P2 | Source fetchers vary; Planalto previously read an unbounded response and accepted a stored URL/redirect. | Planalto now reads at most 25,000,001 bytes and rejects responses over 25 MB; unit-tested. Final redirect host/scheme validation and uniform Senate/adapter limits remain open. |
| T-14 | P2 | No response caching/ETag policy; repeated immutable law/article/history reads hit Postgres. Job state is dynamic and must not receive long-lived caching. | Remains open; only add validators to immutable versioned resources after representative query/load measurements. |
| T-15 | P2 | Startup applies migrations and seeds hot laws, but does not run catalog scans. This is appropriately short; lock-recovery and migration retry add startup complexity. | Existing design retained; verify readiness and migration lock behavior in restart tests before altering. |
| T-16 | P2 | History API distinguishes official relation records from validated before/after diffs; Maria da Penha baseline has 65 relations but 62 without paired text. | Correctly reports partial coverage; do not convert relation counts into verified diffs. |
| T-17 | P2 | Current API lacks explicit version prefix, pagination for the history/proceedings payloads, and machine-readable coverage schema. | Documented roadmap; preserve current routes for compatibility and introduce additive `/api/v1` only with a migration plan. |
| T-18 | P2 | Backup has an observed verified restore from a prior run, but retention, restore cadence and measured RTO/RPO are not established. | Runbook added; restore procedure still needs a scheduled isolated exercise. |
| T-19 | P3 | Search uses Python similarity for small suggestion candidates rather than PostgreSQL FTS/trigram. | Bounded now; evaluate ranking on Brazilian abbreviations before choosing a new index. |
| T-20 | P3 | Health and SEO pages do not expose an explicit source freshness summary on the HTML shell. | Product roadmap. |

## Data correctness and provenance

Models preserve a source URL, fetched timestamp/checksum and parser version for captured snapshots and structured versions. Law changes carry a source norm and marker; Senate proceedings are a cached dossier separate from the enacted text. History events are explicitly documented as relations that are not necessarily validated diffs. This is the right distinction. Gaps remain: source-level freshness and per-record retrieval provenance are not uniform across every adapter; legislative authorship/rapporteur/vote evidence is not a complete normalized chain; status/in-force claims need source-backed semantics. Never infer authorship or repeal from a link or title.

Catalog inventory is not completeness. Current sources include federal Planalto/Senado and only selected state/municipal integrations. The historical 833,109 rows and candidate SAPL endpoints do not prove that every Brazilian law has been enumerated or fully captured. Source-specific authoritative coverage inventories and duplicate/jurisdiction reconciliation remain required.

## Queue, worker, and startup

The durable `hydration_jobs` + outbox record precedes Redis dispatch; active work is deduplicated per law/type with a partial unique index; stale running jobs use leases/heartbeats; worker checks schema readiness; backfills use active-job caps and batches. These are good foundations. Public reads can still request new work across many distinct slugs and no client-level limit exists. Redis is part of the dispatch fast path; exercise Redis unavailable/recovery and outbox replay, not replace it with a second queue service without evidence.

Startup migrations use an advisory lock/retry path in the current main. It seeds the curated hot catalog but avoids full network sync. Runbook and tests must keep DDL out of request-serving replicas under unbounded lock waits.

## Reproduction and post-change validation

- Baseline: 127 tests passed, 3 warnings; Playwright 4/4 passed in 30.1 s (prior deployment).
- Audit branch full suite: `pytest -q` — 131 passed, 1 Starlette/httpx warning.
- Audit branch Playwright: `npm run test:e2e` — 5/5 passed in 32.0 seconds, including 390px mobile homepage/search.
- Docker image build and non-root container smoke: succeeded with proxy CA mounted only during build; `/health` returned 200 and process UID was 10001.
- New production measures to capture after merge: `/api/stats`, `/api/search?q=LGDP`, `/sitemap.xml`, a sitemap shard; p50/p95 under explicit concurrency; DB disk; worker max RAM; exact deployments/SHA.

## Prioritization

Ship low-risk T-01 to T-03 first, then non-root runtime and OSS/CI. Keep T-04/T-05 under alert and evaluate with billing and SQL visibility. Defer index migrations, database/queue replacement, region moves, multi-replica rollout, complete national ingestion, and parser-wide redesign until exact plans, backup, cost, and data-quality checks exist.
