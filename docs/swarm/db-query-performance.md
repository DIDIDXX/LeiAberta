# DB query and request-pressure handoff

## Findings at base `22ab226`

- Do not treat the current API 500/health 500/readiness 503 as evidence of one bad endpoint query: all observed failures coincide with PostgreSQL storage at 4.9965/5 GB. This work intentionally made no production or Railway calls and did not attempt database queries.
- `/api/stats` was already changed to a single grouped scan of `laws` rather than one count per SAPL source. It still reads the large `laws` relation and runs separate counts for current structured articles, changes, source registry rows, and active Senado hydration jobs. Repeated polling therefore remains expensive.
- `/api/search` exact number lookups can use existing number/year indexes; free-text branches use leading-wildcard `ILIKE` and `CAST(aliases AS text) ILIKE`, which cannot use ordinary btree indexes. There is no trigram index in the checked-in schema/migrations. Typo fallback is limited to 2,000 curated `hot` laws, but that does not eliminate scans in the preceding free-text branches.
- `/api/laws` orders the hot catalog by `hot DESC, title`; repeated requests can sort the same catalog prefix.
- Before this change, global Redis rate limits covered search, law detail, and job preparation but not `/api/stats` or `/api/laws`. A Redis outage bypassed those limits and emitted a warning for every limited request. Search also logged every full raw query at INFO.

## Changes in this branch

- Added conservative global Redis budgets for stats (30/min), source listing (60/min), law listing (120/min), and search (300/min; previously 600/min).
- Added a separate shared budget for history, proceedings, coverage, and audit GETs (90/min) after review identified repeated history polling as another DB-heavy path.
- Added a bounded per-process fixed-window limiter for those same requests when Redis is unavailable. Reads continue to work until the local budget is exhausted; excess returns HTTP 429 with `Retry-After`. This is deliberately not represented as a globally coordinated fallback: each web process has its own counter.
- Added short cache headers to successful GETs for `/api/stats`, `/api/laws`, and `/api/search`, permitting browser and shared-cache reuse without claiming long freshness.
- Added an actual 5-minute JSON snapshot cache to `/api/stats` and `/api/sources`: Redis is shared across web instances when configured, and cache misses/failures use a per-process fallback bounded to 8 MiB total, 2 MiB per entry, and 128 entries. Source filter values are SHA-256 digested before entering cache keys. Responses expose only `X-Data-Cache` state and the fixed TTL, never cache keys or Redis details.
- Cache snapshots are read optimizations, not authoritative state for writes. No write path uses cached data, no write-side invalidation is claimed, and updates become visible after the 5-minute cache TTL.
- Downgraded search query/result logging to DEBUG and removed the raw query from the application log line.
- Made `/health` and `/api/health` pure process liveness checks; `/ready` remains a database plus schema check and returns 503 on connection failure or schema mismatch. `/worker-health` reports heartbeat freshness and database availability separately, and returns 503 unless both are ready.
- Mapped only SQLAlchemy `OperationalError` from application requests to a generic 503 with `Retry-After` and `no-store`. Readiness maps SQLAlchemy failures while querying the schema table to its explicit generic 503; other SQLAlchemy exceptions on normal application requests are not normalized as outages. Database outage logs are rate-limited to one per 30 seconds and aggregate suppressed failures without printing driver exception details.
- No migration, schema/index, Railway setting, production data, or secret was changed.

## Validation

- `pytest -q`: 162 passed (one upstream Starlette/httpx deprecation warning). Tests cover Redis cache hits and the exact 300-second TTL, local fallback hit/expiry/bounds, source-filter key hashing, cached endpoint responses, worker DB/heartbeat readiness, and bounded database outage responses.
- These are unit/API tests with SQLite fixtures; they do not establish query plans or production PostgreSQL capacity.

## Recommended follow-up after storage recovery

1. Recover PostgreSQL capacity first, then capture `pg_stat_activity`, relation/index sizes, dead tuple estimates, and representative `EXPLAIN (ANALYZE, BUFFERS)` plans for stats and search under controlled load.
2. Avoid running heavy `VACUUM FULL`, index builds, or catalog-wide query experiments while the volume is at its hard limit. Choose storage-reclamation actions with an operator who can inspect backups, WAL, snapshots, and service dependencies.
3. For free-text search, evaluate a `pg_trgm` GIN index for title/description and a normalized aliases representation. This requires storage headroom and an explicit migration/rollback plan; it is not included here.
4. The current Redis/local cache is intentionally non-authoritative and expires after five minutes. If fresher statistics become a requirement, consider a versioned worker-refreshed snapshot with explicit invalidation after measuring its write/read tradeoff.
5. Reassess budgets with production traffic and replica count. Current Redis limits are global per scope; the fallback budgets are per process and thus multiply with web replicas.
