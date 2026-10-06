# QA / security / release review

**Reviewer:** QA/security/release agent  
**Review base:** `main` at `22ab226` (`docs: mark v0.1.0 release complete (#80)`)  
**Environment reviewed:** Railway production, read-only  
**Observation time:** 2026-10-06 01:06–01:10 UTC  
**Scope:** production HTTP/health/5xx, recent runtime logs and deployment state, prior backup/restore evidence, application rate limits/log behavior, existing Python/E2E suite and failover gaps. No Railway configuration, database, data, secrets, or deployments were changed.

## Release decision

**NO-GO: production currently has a P0 data-service availability incident.** At the observation time, Railway's web deployment was `SUCCESS`, but PostgreSQL connections failed with `FATAL: the database system is in recovery mode`. Web and API health checks consequently failed, and Railway's HTTP metrics showed a 70.21% 5xx rate (33 of 47 requests) over the preceding hour. The current public deployment must not be described as healthy or fully operational until the recovery gates below pass.

The immediate observed failure is in Postgres availability/recovery. Evidence does not establish why PostgreSQL entered recovery or how much time recovery will take. Do not infer corruption from the recovery-mode message alone.

## Measured production results

Public URL: `https://web-production-12e95.up.railway.app`

Direct, read-only HTTP requests made during this review:

| Route | Result | Approx. latency / note |
| --- | --- | --- |
| `/health` | 500 | 0.287 s; DB check raises an internal error |
| `/ready` | 503 | 0.262 s; `Database schema is unavailable` |
| `/worker-health` | 503 | 0.268 s; `Worker heartbeat is stale` |
| `/` | 200 | 0.264 s; static shell is served |
| `/api/stats` | 500 | DB-backed endpoint unavailable |
| `/api/search?q=LGPD` | 500 | DB-backed endpoint unavailable |
| `/openapi.json` | 200 | OpenAPI document served |

Railway HTTP metrics for `web`, production, last hour:

- 47 total requests: 12 2xx, 2 4xx, 33 5xx.
- 5xx rate: **70.21%**; worst observed bucket: **82.76%** (24 of 29 requests).
- Railway HTTP logs also show repeated 500 responses from stats, search, law and history routes; static home/OpenAPI routes continued returning 200.

Railway runtime logs at `2026-10-06T01:09:37Z` show SQLAlchemy/psycopg failing to connect because Postgres reported recovery mode. At `01:09:40Z`, Railway reported its per-replica limit of 500 log lines/s and **1,410 messages dropped**. Worker logs show the same database recovery/connectivity failure and `wait_for_database_schema` retries at attempts 10, 20, and 30. The worker heartbeat is only started after its schema wait succeeds; it is therefore stale while the worker is waiting for the unavailable DB.

Railway service inventory at review time:

- Web: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- Worker: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- PostgreSQL and Redis deployment statuses: `SUCCESS`.
- Backup service: `SUCCESS`, daily cron `0 3 * * *` UTC.
- There is a staged Railway patch with **2 changes**, including a staged delete for `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276` and a staged Postgres-volume config change. This review did not apply or inspect the per-field staged change. Do not accept this patch as part of incident response without separately reviewing the exact diff and impact.

A deployment's Railway `SUCCESS` state reflects the deploy lifecycle, not current end-to-end availability. The public checks and HTTP metrics above take precedence for release gating.

## Backup and restore evidence

The existing runbook and Railway runtime log show a prior verified backup from **2026-10-05 09:15:50 UTC**:

- Object: `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`
- Size: 247,073,141 bytes
- SHA-256: `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`
- Isolated restore verification: `restore_verified=true`; core row counts and Alembic revisions compared.

This is positive evidence for that backup only. During this review I could not verify current bucket inventory, retention, whether a newer backup object exists, or the contents of its manifest via the available read-only interface. No backup was run while production Postgres was in recovery. The scheduled next attempt is `03:00 UTC` if the service schedule remains active; success must be confirmed from the backup completion log and manifest rather than the deployment's status.

The documented restore exercise restores to an isolated temporary PostgreSQL and does not cut production over. Production failover/recovery cutover, measured RTO, actual PITR, and recovery-point validation remain untested. The runbook's nominal backup interval is daily, so do not claim zero data loss or a known RPO.

## Security and cost-control review

The base code has Redis-backed fixed-window global limits in `app/main.py`:

- Search: 600 requests/minute.
- Law root/detail, nodes, blame, provenance: 240/minute.
- POST history/proceedings preparation and hydration: 60/minute.
- It does not trust forwarded client IPs. This avoids spoofing but means budgets are shared globally rather than fair per client.
- If Redis returns an error, the middleware fails open and logs one warning per affected request. This is an explicit availability tradeoff but provides no enforced ceiling during a Redis outage.

**P1 abuse/cost gap:** the policy does not include several DB-backed GET routes, including `/api/laws/{slug}/history`, `/proceedings`, `/coverage`, and `/audit`. Railway's incident-period HTTP logs include a sequence of history requests, all returning 500 while Postgres was unavailable. They were not rate-limited by the current route matcher. Consider budgeting expensive GET routes consistently, with stricter request/response bounds for histories. Do not live-test the threshold on production; current DB availability is already impaired. The unit suite verifies policy selection and synthetic 429/`Retry-After`, but no controlled live 429 test was run.

**Log storm:** HTTP requests that trigger uncaught DB connection exceptions produce full traceback logs. The Railway logger then drops messages after 500 lines/s, making incident diagnosis less reliable. Repeated health and API requests during DB recovery can amplify this. Prefer concise, sampled, deduplicated DB outage logging and avoid per-request full traceback in known dependency outages; preserve exception detail in bounded diagnostic fields or a correlation sample. Worker schema polling logs every tenth attempt and is comparatively bounded, but retry jitter/backoff and a capped outage summary would reduce cross-service amplification.

Other noted limitations: the rate limiter is global, not per-client; it fails open if Redis is unavailable; raw search query logging remains in `app/main.py`; adapter fetch security is not uniform. These are not the observed P0 cause.

## Automated QA performed

On the isolated `codex/qa-security-release` worktree at base `22ab226`:

- `pytest -q`: **150 passed**, 1 upstream Starlette/httpx deprecation warning.
- After `npm ci` and installing Chromium, `npm run test:e2e`: **2 passed** (real art. 389 before/after + device evidence; LGDP typo search and 390 px mobile home).
- The E2E test setup uses a local SQLite database and seeded fixture; it does not prove production PostgreSQL availability or failover.
- Prior launch docs record a manual browser matrix of **36 combinations** (9 routes × 390/430/768/1440 px); this review did not rerun that matrix because the live DB-backed routes are currently failing. Current automated Playwright suite has 2 tests, not 36 browser-route-width cases.
- No destructive, outage-inducing, high-rate, or production failover test was run.

## Release gates

Do not declare release/production healthy until all of the following are observed after database recovery:

1. Postgres accepts normal read and write connections; current recovery cause is understood from Railway DB logs/metrics. Verify data and migration head without destructive changes.
2. `/health` and `/ready` return 200; `/worker-health` returns 200 with a fresh heartbeat.
3. `/api/stats`, `/api/search?q=LGPD`, the art. 389 change endpoint, history, and the public hero flow return expected non-5xx responses.
4. Railway HTTP 5xx rate remains below 1% over at least 30 minutes with enough real requests to make the rate meaningful; no renewed logger cap/drop warnings.
5. A post-recovery backup completes, object and manifest are present, checksum/size match, and the backup reports `restore_verified=true` (or an isolated restore is re-run against the new object).
6. Recheck at least the documented browser matrix or an agreed representative route/viewport matrix against the recovered release.

If any gate fails, keep release status NO-GO and retain this report as the incident snapshot.

## Rollback and recovery guidance

- **Do not roll back or redeploy app code as the first response to this evidence.** Current web source is `main` commit `22ab226` (docs-only after the validated app commits); logs identify Postgres recovery as the immediate failure, and the Postgres service's last deployment predates this docs commit.
- **Do not accept the staged Railway patch, delete the staged diagnostic service, alter the Postgres volume, restart Postgres, or overwrite production from a backup under this review.** Those operations risk destroying diagnostic or recovery state and are outside the read-only QA authorization.
- Preserve current deployment IDs, DB/volume state, logs, and latest usable backup evidence. Have the platform/database incident owner inspect Postgres recovery logs, storage/volume health, and Railway events first.
- If recovery cannot complete, follow `docs/runbooks/backup-restore.md`: restore the verified dump into a **new isolated PostgreSQL service/volume**, compare manifest row counts and Alembic heads, validate app connections against that isolated instance, then plan a deliberate cutover with an explicit rollback target. Never test restore against the live DB.
- Roll back an application deployment only if a separate verified app regression is found and the target commit passes compatibility checks with the current DB schema. Schema downgrade or DB volume rollback is not an application rollback.

## Review status for worker/cost proposal

The worker/cost-control branch was not yet available for review at the time this document was first drafted. The separate reviewer proposal described an existing-job marker and `off`/`hot`/`continuous` backfill modes, with no migration, while preserving marked pending jobs. Before approval, inspect the exact diff for queue ACK/deletion behavior, priority job exemption, lease/outbox recovery, and mode changes; run its focused tests and full CI; then compare worker query/HTTP/log volume in a non-production or safely observable rollout. Production DB recovery must be stable before changing worker throughput policy.
