# QA / security / release review

**Reviewer:** QA/security/release agent
**Review base:** `main` at `22ab226` (`docs: mark v0.1.0 release complete (#80)`)
**Environment reviewed:** Railway production, read-only
**Observation time:** 2026-10-06 01:06–01:44 UTC
**Scope:** production HTTP/health/5xx, recent runtime logs and deployment state, prior backup/restore evidence, application rate limits/log behavior, existing Python/E2E suite and failover gaps. No Railway configuration, database, data, secrets, or deployments were changed.

## Release decision

**NO-GO: production currently has a P0 data-service availability incident.** At the observation time, Railway's web deployment was `SUCCESS`, but PostgreSQL connections failed with `FATAL: the database system is in recovery mode`. Web and API health checks consequently failed, and Railway's HTTP metrics showed a 70.21% 5xx rate (33 of 47 requests) over the preceding hour. The current public deployment must not be described as healthy or fully operational until the recovery gates below pass.

The immediate observed failure is in Postgres availability/recovery. The separate DB emergency review corroborated disk exhaustion: Railway reported the 5 GB Postgres volume at **4.996513792 GB used (~99.93%, about 3.49 MB nominally free)** and Postgres logs at 01:08 UTC included `PANIC: could not write to file "pg_logical/replorigin_checkpoint.tmp": No space left on device`. This is the supported cause of the recovery loop. It does not establish corruption or which relation/filesystem consumer should be removed.

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

Fresh Postgres metrics/logs read at approximately `2026-10-06T01:21Z` confirm the incident is still active: disk usage remains **4.996513792 GB** with a maximum of the same value across 61 samples in the preceding hour. Postgres logs at 01:21:51–53Z repeat `PANIC: ... No space left on device`, interrupted shutdown, automatic recovery, and FATAL recovery-mode errors. Railway still reports the Postgres and application deployments as `SUCCESS`, which is not evidence that the database is accepting traffic.

Rechecked at `2026-10-06T01:25Z`: Postgres disk remains **4.996513792 GB** (61 samples; 4.996333568 GB minimum in the preceding hour). Latest Postgres runtime logs at 01:25:15–17Z again show end-of-recovery checkpoint `PANIC: ... No space left on device`, followed by process termination and recovery restarting. Railway's environment status still lists all five services Online/Ready, no issues, and deployments `SUCCESS`; the pending volume resize remains staged and not live. Recent HTTP evidence at 01:20Z still has `/health`, `/api/stats`, `/api/laws`, and `/api/search` returning 500 while `/ready` returns 503. The status/deployment fields do not reflect the live database outage.

At `2026-10-06T01:30Z`, the latest Postgres disk sample is still **4.996513792 GB** and its latest runtime logs again record `PANIC: ... No space left on device` during recovery. At `01:43–01:44Z`, after the coordinator attempted to apply the resize, the Railway environment now reports **no staged patch/pending work**; this means the resize did not apply. The live Postgres volume remains **5,000 MB**. The latest disk sample is still **4.996513792 GB** (61 samples in the last hour). The latest captured Postgres logs (01:43:46–01:44:45Z) repeatedly show `FATAL: the database system is not yet accepting connections` / `Consistent recovery state has not been yet reached`; earlier logs continue to show the `PANIC ... No space left on device` recovery-loop cause. Railway status still labels all five services Online/Ready and deployments `SUCCESS`, which conflicts with the Postgres runtime evidence. **Release remains NO-GO.** A fresh HTTP metrics read at `01:45Z` shows **41 5xx / 48 total requests (85.42%)** in the last hour (6 2xx, 1 4xx); the latest captured probes at 01:41:52–53Z returned `/health` 500, `/ready` 503, and `/api/stats`, `/api/laws`, `/api/search` 500. This production build predates PR #81, so the proposed liveness/readiness handling is not in the live deployment.

Railway runtime logs at `2026-10-06T01:09:37Z` show SQLAlchemy/psycopg failing to connect because Postgres reported recovery mode. At `01:09:40Z`, Railway reported its per-replica limit of 500 log lines/s and **1,410 messages dropped**. Worker logs show the same database recovery/connectivity failure and `wait_for_database_schema` retries at attempts 10, 20, and 30. The worker heartbeat is only started after its schema wait succeeds; it is therefore stale while the worker is waiting for the unavailable DB.

Railway service inventory at review time:

- Web: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- Worker: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- PostgreSQL and Redis deployment statuses: `SUCCESS`.
- Backup service: `SUCCESS`, daily cron `0 3 * * *` UTC.
- PostgreSQL volume: 5,000 MB allocated; current disk 4.996513792 GB of nominal 5 GB per the 24-hour Railway metrics read (1,441 samples; max 4.996521984 GB). Exact filesystem accounting may differ.
- After the coordinator's resize commit/apply attempt, a read-only Railway inspection at 01:43Z shows **no staged changes** and no pending work. The attempted 5,000 → 6,500 MB resize **did not apply**. Postgres remains on the live **5,000 MB** volume. The platform owner must stage/apply the resize from the Railway dashboard and complete the required 2FA. This review made no production changes.

A deployment's Railway `SUCCESS` state reflects the deploy lifecycle, not current end-to-end availability. The public checks and HTTP metrics above take precedence for release gating.

## Backup and restore evidence

The existing runbook and Railway runtime log show a prior verified backup from **2026-10-05 09:15:50 UTC**, about 16 hours before the emergency storage review:

- Object: `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`
- Size: 247,073,141 bytes
- SHA-256: `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190`
- Isolated restore verification: `restore_verified=true`; core row counts and Alembic revisions compared.

This is positive evidence for that backup only. The emergency storage review likewise could not verify current bucket inventory, retention, whether a newer backup object exists, or the contents of its manifest via the available read-only interface. No backup was run while production Postgres was in recovery. The scheduled next attempt is `03:00 UTC` if the service schedule remains active; success must be confirmed from the backup completion log and manifest rather than the deployment's status.

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

- `pytest -q` on the reviewed base: **150 passed**, 1 upstream Starlette/httpx deprecation warning. After adding the prompt-aligned matrix coverage below, the focused API/history/source tests passed: **37 passed**, 1 upstream deprecation warning.
- After `npm ci` and installing Chromium, `npm run test:e2e`: **2 passed** (real art. 389 before/after + device evidence; keyboard search selection of LGPD; home checked at 390/430/768/1440 px for horizontal overflow).
- The E2E test setup uses a local SQLite database and seeded fixture; it does not prove production PostgreSQL availability or failover.
- Prior launch docs record a manual browser matrix of **36 combinations** (9 routes × 390/430/768/1440 px); this review did not rerun that matrix because the live DB-backed routes are currently failing. Current automated Playwright suite has 2 tests, not 36 browser-route-width cases.
- No destructive, outage-inducing, high-rate, or production failover test was run.

### Acceptance matrix against the launch prompt

| Prompt flow / viewport | Evidence exercised | Status and remaining gap |
| --- | --- | --- |
| Existing law before/after and provenance evidence | Browser E2E opens the existing Código Civil art. 389 comparison, checks both texts and official-source link, then opens device evidence. | **Pass locally.** Fixture is seeded in SQLite; this does not validate Railway/Postgres. |
| Search by a typo and keyboard operation | Browser E2E types `LGDP`, moves to the LGPD result with ArrowDown, checks `aria-selected`, presses Enter, and checks navigation. | **Pass locally.** One known result/query exercised. |
| Home at 390, 430, 768, and 1440 px | Browser E2E checks the home heading and `scrollWidth <= innerWidth` at each requested width. | **Pass for home only.** No all-route viewport sweep or visual comparison at those widths was run. |
| Law history page, queued/running/partial states, and preparing history | Python API/job tests cover `test_history_is_explicitly_not_requested_until_a_real_job_exists`, `test_history_prepare_creates_a_persisted_job`, `test_queued_text_hydration_does_not_claim_history_is_being_prepared`, and persisted official-history fixtures. | **Backend tests only.** Browser history route, status polling, error/retry presentation, and accessibility were not E2E-tested. |
| Cold catalog law → interactive hydration queued → worker completion | API test `test_senado_catalog_entry_can_queue_text_without_claiming_it_is_ready` and launch fixture test for catalog search/hydration/retry cover the API queue response and idempotence. | **Partial.** No browser-triggered cold-law flow or end-to-end worker completion was exercised. |
| Coverage and sources pages | Python coverage/stats and `test_sources_api_exposes_success_freshness_and_delta_fields` exercise supporting API data. | **Partial.** Browser routes `/cobertura` and `/fontes`, their source links, and loading/error states were not E2E-tested. |
| Keyboard/accessibility beyond search | Searchbox accessible name and ArrowDown/Enter are exercised in browser E2E. | **Partial.** No full keyboard-only route traversal, focus-order audit, screen-reader check, or automated WCAG scan was run. |
| Browser route × width matrix | Prior launch documentation lists 9 routes × 390/430/768/1440 px (36 combinations). | **Not run as a full matrix.** Only home was checked at all four widths; comparison/provenance E2E used the default Playwright viewport. |

## Release gates

Do not declare release/production healthy until all of the following are observed after database recovery:

1. Postgres accepts normal read and write connections; recovery cause is understood from Railway DB logs/metrics. Verify data and migration head without destructive changes. Confirm actual volume headroom after the owner applies the required volume resize from the dashboard (the prior 5,000 → 6,500 MB attempt did not apply).
2. `/health` returns 200 as process liveness, `/ready` returns 200 as DB/schema readiness, and `/worker-health` returns 200 with a fresh heartbeat. A liveness 200 by itself does not mean DB-backed requests are ready.
3. `/api/stats`, `/api/search?q=LGPD`, the art. 389 change endpoint, history, and the public hero flow return expected responses; DB connection failures should surface as bounded generic 503 responses rather than traceback-driven 500s.
4. Railway HTTP 5xx rate remains below 1% over at least 30 minutes with enough real requests to make the rate meaningful; no renewed logger cap/drop warnings.
5. A post-recovery backup completes, object and manifest are present, checksum/size match, and the backup reports `restore_verified=true` (or an isolated restore is re-run against the new object).
6. Recheck at least the documented browser matrix or an agreed representative route/viewport matrix against the recovered release.

If any gate fails, keep release status NO-GO and retain this report as the incident snapshot.

## Rollback and recovery guidance

- **Do not roll back or redeploy app code as the first response to this evidence.** Current web source is `main` commit `22ab226` (docs-only after the validated app commits); logs identify Postgres recovery as the immediate failure, and the Postgres service's last deployment predates this docs commit.
- **Do not overwrite production from a backup under this review.** The disk emergency reviewer found no measured safe cleanup candidate. The coordinator attempted to apply the separately reviewed, non-destructive 5.0 → 6.5 GB resize, but it did not apply and no patch is staged now. The live volume remains 5,000 MB; the owner must stage/apply it in the Railway dashboard and complete 2FA. Restarting/altering Postgres is outside this read-only QA authorization.
- Preserve current deployment IDs, DB/volume state, logs, and latest usable backup evidence. Have the platform/database incident owner inspect Postgres recovery logs, storage/volume health, and Railway events first.
- If recovery cannot complete, follow `docs/runbooks/backup-restore.md`: restore the verified dump into a **new isolated PostgreSQL service/volume**, compare manifest row counts and Alembic heads, validate app connections against that isolated instance, then plan a deliberate cutover with an explicit rollback target. Never test restore against the live DB.
- Roll back an application deployment only if a separate verified app regression is found and the target commit passes compatibility checks with the current DB schema. Schema downgrade or DB volume rollback is not an application rollback.

## Review status for follow-up code PRs

### Current PR/check matrix (read-only refresh at 2026-10-06 01:45 UTC)

All six PRs below are open, unmerged, based on `22ab2262678e040879f6220bae4f5c4c23afc4aa`, and reported mergeable by GitHub. GitHub Actions CI is successful on every exact current head; none of these checks establish production readiness.

| PR | Exact head | Current CI | Review / remaining gate |
| --- | --- | --- | --- |
| #81 Query protection | `0beb637a65ca6409e3729ea3c9424a14492db606` | run #83: success; local `pytest -q`: 162 passed (reported by author) | Reviewed current code: pure liveness vs DB readiness; OperationalError 503; throttled no-detail outage logs; Redis/local bounded rate budgets and snapshots. Snapshot caches intentionally stale up to 5 min; no production check/deploy. |
| #82 QA handoff | `fd210e2807567d47357cc51939295c7219cb3aeb` before this report refresh | run #78: success | This report update will trigger CI. Local base suite 150 passed; focused API/history/source 37 passed; E2E 2 passed. Acceptance gaps below remain. |
| #83 OSS cost/support docs | `485f56bccf7fad6e7d2959e62cef91a1968e93a1` | run #82: success | Documentation only; Railway bill and actual post-recovery cost pivot remain unverified. |
| #84 Snapshot storage | `ea92064040abae106ee13185fff1129c6b5f7600` | run #84: success | Additive migration and dry-run-first uploader not applied; bucket/credentials, actual sizing, retention and production restore/cutover remain unverified. |
| #85 Accessible deep links | `94747386993ced5de966d68465e2a6945384bc21` | run #71: success | Local 159 Python tests and 2 E2E passed (reported); no production deployment or live URL/copy behavior verified. |
| #86 Worker backfill control | `1f1525b4059dda210740f90c0fb4ee13be4c3f55` | run #81: success; local `pytest -q`: 162 passed (reported by author) | Reviewed current queue marker/mode, paused-message preservation, terminal ACK guard and private aggregate telemetry. No migration; behavior not deployed or production-measured. |

PR #81 (`Protect catalog queries during database pressure`) adds shared 5-minute Redis JSON snapshots for stats/sources plus an 8 MiB/128-entry bounded local fallback, route request budgets with per-process fallback during Redis errors, pure `/health` and DB/schema `/ready`, separate worker heartbeat/database health, generic no-store 503 handling for `OperationalError`, and outage logs deduplicated to at most one per 30 seconds. The current source hashes source filters before using them in cache keys; cache freshness is intentionally eventual (up to five minutes), with no write-path invalidation. Review found no blocker in the reviewed diff; the Redis/process-local budgets and cache paths still require deployed/configured behavior validation, and production must remain blocked by the database incident.

PR #86 (`Control automatic bulk backfills by worker mode`) defaults automatic backfills to `off`, supports `hot` and `continuous`, preserves queued/outbox/stream jobs when paused, exempts explicit interactive work, hides internal queue markers in public job responses, defers ambiguous retries, and ACKs terminal deliveries only after the durable process guard. Capped DB/Redis retries, sparse sanitized logs, and five-minute private aggregate queue depth telemetry are covered in its latest head. CI run #81 passed and the author reports 162 local tests passed. No production rollout or rate/cost measurement is included.

PRs #83–#85 have green CI but are not production-validated. In particular, #84's migration/storage path is intentionally not run against production during recovery; #83 cannot substantiate cost savings until an invoice/usage period is measured; #85's links/support affordances have only local test evidence.

**Hard release gate:** despite every deployment's Railway `SUCCESS` and all GitHub CI checks being green, Postgres is still at 4.996513792 GB on a 5,000 MB volume and is not reaching consistent recovery. The 5,000 → 6,500 MB update attempted by the coordinator did not apply; there are no staged changes now. Owner dashboard action and 2FA are required. Do not merge/deploy these code PRs into production or report the service recovered until the production gates above pass.
