# Cost analysis

Snapshot and rate source checked 2026-10-05. The Railway billing UI/invoice and workspace plan were not available through the connected account, so this is a rate-based estimate, not a statement of actual charges.

## Railway published rates used

Railway documents $10/GB-month RAM, $20/vCPU-month CPU, $0.05/GB network egress and $0.15/GB-month volume storage. Hobby subscription is $5 and includes $5 usage; Pro is $20 and includes $20 usage. Usage above included amount is billed as the excess such that the final amount is the greater of subscription or metered usage. Rates and plan terms can change; verify in the workspace billing page. Source: [Railway pricing plans](https://docs.railway.com/pricing/plans).

## Resource estimate from 24-hour average metrics

Assumption: the retrieved average CPU and RAM are representative 24/7 for 30 days. Formula: `avg GB × $10 + avg vCPU × $20`; this uses service metrics, not invoices. Egress and attached volume estimates below are approximate and partial.

| Service | RAM estimate | CPU estimate | Approx. monthly compute |
| --- | ---: | ---: | ---: |
| web | $0.80 | $0.26 | $1.06 |
| worker | $10.83 | $4.01 | $14.84 |
| PostgreSQL | $10.91 | $1.05 | $11.96 |
| Redis | $0.17 | $0.05 | $0.22 |
| **Total compute** | **$22.71** | **$5.37** | **$28.08** |

Provisioned volumes total 10 GB; if billing is on the full allocated size, estimate $1.50/month. If billed on actual used size, 3.194 GB observed across PG + Redis implies about $0.48/month. The backup bucket had one verified object of 0.247 GB, roughly $0.04/month at the same published storage rate if bucket bytes are billed similarly; actual object storage price/retention was not exposed. Reported web/worker 24-hour TX metrics imply about 0.52 GB/month and $0.03 egress at the published rate, but service metric egress may omit other user-facing or internal paths. Therefore a rough metered subtotal is $28.6–$29.7/month before any other services, plan-floor adjustments or unobserved network/storage. The account's final bill cannot be stated without its selected plan, current invoice, and complete egress/bucket data.

## Workload scenarios requested

These scenarios describe what is known and what cannot yet be responsibly extrapolated. No production load test was run.

| Scenario | Expected cost interpretation | Confidence |
| --- | --- | --- |
| 0 requests/day | Persistent web, worker, DB and Redis still use memory. Current average-resource proxy is about $28.08/month compute plus volume/object storage; autosleeping only web does not remove DB/worker baseline. | Medium for sampled compute; low for full bill. |
| 1,000 requests/day | Incremental CPU/egress depends on endpoint mix and cached bytes. Use base proxy plus `$20 × incremental average vCPU + $10 × incremental average GB RAM + $0.05 × incremental egress GB`. | Low; endpoint mix/load not measured. |
| 10,000 requests/day | Same formula; stats/sitemap/search currently dominate latency, so do not assume linear scale until fixes are deployed and p95 tested. | Low. |
| 100,000 requests/day | Could require read caching, better search indexes and/or web replicas; DB, connection pool and worker queue are unbenchmarked. | Very low. |
| 10 / 100 / 1,000 hydrations/day | Each fetch can download a source document, parse/store raw bytes, nodes and indexes; cost per job varies substantially by source/size. Formula adds worker CPU/RAM minutes, egress bytes, DB WAL/write and retained source bytes. No valid single-job average exists yet. | Very low. |

Measure representative requests and hydration sizes first, then use the published per-minute rates and measured concurrency to calculate scenarios. Do not use total article count as storage bytes or assume one hydration equals one database row.

## Cost and risk decisions

- The worker is the largest compute estimate (~$14.84/mo) and runs in a different region from Postgres/Redis. Compare p95 and network cost before relocating.
- Two 5 GB volumes are close to a free-tier-style storage cap only if actual plan limits apply; current Postgres uses 61% of its volume. Plan headroom before large full-text backfills or new indexes.
- Current service idling means cost does not approach zero at 0 requests/day. Scale-to-zero is not recommended for Postgres/Redis; consider worker sleep only after durable queue wake-up behavior is tested.
- No extra database, queue, cache, monitoring vendor, or region was provisioned by this audit.
