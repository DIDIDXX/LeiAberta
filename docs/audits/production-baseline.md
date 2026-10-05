# LeiAberta production baseline

Snapshot taken 2026-10-05 (UTC). Values below are observations, not an availability or capacity guarantee. This is a production system; requests were read-only. No queue, catalog, source registry, or law text was modified during the baseline.

## Deployment inventory

Railway project `LeiAberta`, production environment `b415a556-41ec-4f33-994f-1f5d38b633a1`, project `ac5c9188-a792-4d4a-99d6-512740aec73e`.

| Service | Region | Replicas | Deployment | State at baseline |
| --- | --- | ---: | --- | --- |
| web | `asia-southeast1-eqsg3a` | 1 | `7465fadf-1cab-4c07-81a3-d4d4cf96da73` | SUCCESS |
| worker | `us-east4-eqdc4a` | 1 | `4a9523b7-d3ec-4c89-8d8e-ddfdae888b00` | SUCCESS |
| PostgreSQL 18 | `asia-southeast1-eqsg3a` | 1 | `78c139ee-fc38-4883-be04-99d72052c7d0` | SUCCESS |
| Redis 8.2 | `asia-southeast1-eqsg3a` | 1 | `e0cc2708-a527-4918-aa06-3f994675234a` | SUCCESS |
| postgres-backup | `asia-southeast1-eqsg3a` | cron `0 3 * * *` | `ad0ca4a3-914e-46d7-bfcb-3696585239d1` | SUCCESS |

Postgres and Redis each have a 5,000 MB volume. At measurement Postgres disk was 3.053 GB (61.1% of allocated volume); Redis disk was 0.141 GB (2.8%). A single backup object was verified at 247,073,141 bytes, SHA-256 `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`; restore verification was reported successful by the preceding execution. Total bucket inventory and backup retention were not exposed by the available connector.

The worker is in `us-east4`; web, PostgreSQL, Redis and backup are in Singapore. This is a confirmed cross-region worker-to-database path. Latency and egress between those regions were not independently instrumented; do not assume a measured cost or latency from the topology alone.

## Metrics

Railway service metrics, 24-hour window (1,440/1,441 samples, retrieved near 15:36 UTC):

| Service | CPU avg / max | Memory avg / max / latest | Disk latest |
| --- | ---: | ---: | ---: |
| web | 0.013 / 0.885 vCPU | 0.080 / 0.304 / 0.080 GB | metric 0 |
| worker | 0.201 / 1.462 vCPU | 1.083 / 5.182 / 3.396 GB | metric 0 |
| PostgreSQL | 0.053 / 2.588 vCPU | 1.091 / 2.467 / 1.747 GB | 3.053 GB of 5 GB volume |
| Redis | 0.002 / 0.004 vCPU | 0.017 GB average | 0.141 GB of 5 GB volume |

Worker's most recent hour was steadier: CPU average 0.744, max 1.389 vCPU; memory average 3.437, max 3.748, latest 3.396 GB. Its 24-hour maximum was 5.182 GB with an 8 GB reported limit. Current 24-concurrency setting is below the measured limit but leaves limited headroom during the earlier peak; inspect before raising it. PostgreSQL volume has 1.947 GB free at this snapshot.

The Railway metrics connector does not provide billing invoice, connection count, table/index size breakdown, or queue age/depth. Exact `pg_total_relation_size`, `pg_stat_activity`, Redis stream lag and oldest active job remain unmeasured. PostgreSQL log sample showed routine checkpoints and one connection timeout; the sample is insufficient to infer an incident rate.

## Catalog and application behavior

Last exact application counts obtained in the prior production snapshot (2026-10-05 around 09:15 UTC): 833,109 indexed laws, 14,254 with materialized text, 51,938 structured articles and 376 documented changes. Senate catalog had 216,717 pending texts; subnational catalog pending totals summed to 601,723, with overlaps possible. These are catalog rows, not a census of every Brazilian law. At the 15:45 UTC check the public `/api/stats` did not return within a 20-second client timeout, so those counts were not re-certified in this run.

Production smoke observations, around 15:45 UTC:

| Request | Status | Observed duration | Response detail |
| --- | ---: | ---: | --- |
| `/health`, `/api/health` | 200 | 0.36s / 0.27s | JSON liveness and DB `SELECT 1` |
| `/api/search?q=LGDP` | 200 | 4.14s | typo suggestion returned; overly slow |
| `/lei/13709-2018` | 200 | 0.35s | generic HTML shell |
| `/api/laws/13709-2018/nodes?article=7` | 200 | 0.26s | 4,472 bytes sampled |
| `/api/laws/11340-2006/history` | 200 | 0.30s | 38,125 bytes sampled |
| `/api/laws/senado-36981001/proceedings` | 200 | 0.36s | 241,736 bytes sampled |
| `/sitemap.xml` | 200 | 7.09s | first 500,000 bytes sampled; full response not downloaded |
| `/api/stats` | — | >65s | read timed out on a second, longer client request |
| `/robots.txt` | 200 | 0.27s | points at `/sitemap.xml` |

The previous execution's four Playwright flows passed (LGPD/article/source, history diff, cold hydration, ambiguous article-only search) in 30.1 seconds; this is pre-change baseline evidence. Python baseline was 127 passed, 3 warnings in 1.95 seconds. Warnings were Starlette/httpx deprecation and Alembic's missing `path_separator` configuration.

## Interpretation / immediate thresholds

- P1: Postgres disk at 61%; alert at 70% (3.5 GB) and plan volume resize/retention before 80% (4 GB). Do not delete snapshots without a retention and restore policy.
- P1: stats timeout and single unsharded sitemap are public availability/SEO bottlenecks; a code correction is in this audit branch and must be measured after deployment.
- P1: worker is cross-region from the database and hit 5.18 GB; compare queue throughput, p95 DB round-trip and memory before changing region or concurrency.
- A real Railway bill, active plan, full relation sizes, connection counts, queue metrics, and load-test p95 are technically unavailable through the connected read-only Railway metrics/API surface. Pricing scenarios therefore remain explicit estimates in `cost-analysis.md`.
