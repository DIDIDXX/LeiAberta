# Scale analysis

Date: 2026-10-05. This report separates observed production behavior from estimates. No synthetic load was applied to production.

## Observed operating point

- Catalog baseline: 833,109 law records; 14,254 current texts; 51,938 structured articles; 376 changes (prior exact API snapshot near 09:15 UTC).
- PostgreSQL data volume: 3.053/5 GB at snapshot, about 61.1% full; Redis volume: 0.141/5 GB.
- Worker 24-hour max memory 5.182 GB, current 3.396 GB; reported limit 8 GB. Latest hour max 3.748 GB.
- `LGDP` search 4.14 s; sitemap 7.09 s and >500 KB; `/api/stats` exceeded 20 s. Other direct law/node/history/proceeding requests were 0.26–0.36 s.
- Four existing browser flows passed at baseline; this is functional smoke, not concurrent load.

## Bottlenecks and changes

1. Stats performed repeated counts per each registered source. A registry with N sources could do O(N) scans of the 833k-row law table. Audit branch groups by `source_name` in one aggregate and derives totals in memory: O(one table pass + registry rows).
2. Sitemap materialized all slug strings and returned one URL set. It is slow, memory-heavy, and violates sitemap protocol limits as the catalog grows. Audit branch emits an index and 10k-row URL shards; the shard uses ordered primary-key reads and bounded memory.
3. Fuzzy fallback ran similarity over all law rows. Audit branch caps fuzzy candidates at 2k curated hot rows; exact SQL search remains separate. Cold-catalog typo suggestion coverage is consequently reduced.
4. Normal text search still uses substring `ILIKE` and JSON alias casts, which have no demonstrated trigram index. A PostgreSQL GIN migration is not approved in this work because storage is only 1.95 GB free and no `EXPLAIN`/table-size access is available. Measure with a production-like clone and include index build disk/WAL headroom first.
5. DB and worker are cross-region. Measure query p50/p95 from the worker, queue throughput, and egress before moving worker. A move can reduce cross-region traffic but could affect source-fetch geography and rollback availability.

## Capacity, limits, and missing measurements

No p50/p95 concurrency test, PostgreSQL query plan, table/index size breakdown, current connections, stream lag, oldest queued job, or source request rate was exposed. Therefore 1k/10k/100k request/day capacity is not claimed. A real capacity test should run against an isolated data clone and cover:

- search by exact number, title and typo; detail, article nodes, history, proceedings, stats;
- cold hydration, duplicate hydration, concurrent unique jobs, Redis outage/outbox recovery;
- sitemap index and each shard; time-to-first-byte and memory at 1, 10, 50 concurrent clients;
- warm/cold PostgreSQL and connection pool saturation; record p50/p95/p99 and DB CPU/I/O;
- production-equivalent worker memory with 1, 8, 16 and 24 concurrent fetches, verifying source-domain limits.

## Growth controls

- Alert PostgreSQL volume at 70% (3.5 GB) and page/plan intervention at 80% (4 GB). Keep a verified restore point before retention or index operations.
- Worker concurrency must be tuned against RSS/peak and failure/retry rate, not CPU alone. Do not exceed 24 without new evidence; if memory approaches 6 GB persistently, lower it to 16 and compare backlog drain time.
- Track `queued`, `running`, `failed`, job age, retries, source error rate, outbox age, worker heartbeat, disk size and free volume daily.
- Add paginated responses for large history/proceeding datasets and explicit max response bytes where applicable.
- Avoid eager national backfills until storage sizing and source-specific rate budgets are set. Catalog presence and text materialization are separate coverage states.

## Scale decision

Keep the current PostgreSQL + Redis Streams/outbox + one worker architecture for now. The code already has durable job rows, deduplication, retries/leases and bounded batches. A queue rewrite or horizontal worker scaling without queue-age, connection and memory telemetry would increase failure modes without measured benefit. Shard the sitemap and eliminate repeated catalog scans first; the rest requires load evidence.
