# ADR 0001: Bound public catalog work before adding infrastructure

- Status: Accepted for audit branch
- Date: 2026-10-05

## Context

Production has about 833k catalog rows. `/api/stats` timed out after 20 seconds because counts repeated for each registered source; fuzzy typo fallback scanned all laws in Python; sitemap loaded every slug into one response and took 7.09 seconds.

## Decision

Aggregate statistics by source name in one grouped SQL query; cap fuzzy candidates at 2,000 curated hot laws; split sitemap output into an index plus 10k law shards. Preserve existing API routes and response shape for stats and search. Avoid PostgreSQL extensions/index migrations until relation size, free disk, query plans and index build headroom are known.

## Consequences

Expected application memory and DB query work are bounded more tightly. Typo suggestions are less comprehensive for cold catalog rows. Search substring queries may remain full scans. Sitemap shard offsets can cost more for later shards as the catalog grows; monitor response time and move to keyset-based shards or static sitemap generation if needed.

## Verification and rollback

Unit/API tests check statistics and sitemap index/shard output; Python and Playwright suites should pass. After deploy, compare endpoint duration and worker/DB metrics. Rollback is a normal code rollback to the previous image; no schema/data migration is involved.
