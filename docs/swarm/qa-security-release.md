# QA / security / release review

**Reviewer:** QA/security/release agent
**Review base:** `main` at `22ab226` (`docs: mark v0.1.0 release complete (#80)`)
**Environment reviewed:** Railway production, read-only
**Observation time:** 2026-10-06 01:06–01:25 UTC
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

At `2026-10-06T01:30Z`, the latest Postgres disk sample is still **4.996513792 GB** and its latest runtime logs again record `PANIC: ... No space left on device` during recovery. Railway environment status still says five services Online/Ready with zero reported issues, and the one 5,000 → 6,500 MB volume patch is staged only. No production action was taken.

Railway runtime logs at `2026-10-06T01:09:37Z` show SQLAlchemy/psycopg failing to connect because Postgres reported recovery mode. At `01:09:40Z`, Railway reported its per-replica limit of 500 log lines/s and **1,410 messages dropped**. Worker logs show the same database recovery/connectivity failure and `wait_for_database_schema` retries at attempts 10, 20, and 30. The worker heartbeat is only started after its schema wait succeeds; it is therefore stale while the worker is waiting for the unavailable DB.

Railway service inventory at review time:

- Web: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- Worker: latest deployment `SUCCESS`, commit `22ab226`, 1 replica.
- PostgreSQL and Redis deployment statuses: `SUCCESS`.
- Backup service: `SUCCESS`, daily cron `0 3 * * *` UTC.
- PostgreSQL volume: 5,000 MB allocated; current disk 4.996513792 GB of nominal 5 GB per the 24-hour Railway metrics read (1,441 samples; max 4.996521984 GB). Exact filesystem accounting may differ.
- A fresh read-only inspection of the staged Railway patch shows **one non-destructive volume update only**: `postgres-volume` size **5,000 → 6,500 MB** (`destructive=false`). The earlier staged diagnostic-service delete has been cleared. This resize is not live; the owner must complete Railway's 2FA to apply it. No change was made by this review.

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

1. Postgres accepts normal read and write connections; recovery cause is understood from Railway DB logs/metrics. Verify data and migration head without destructive changes. Confirm actual volume headroom after the staged 6.5 GB resize is applied by the owner.
2. `/health` returns 200 as process liveness, `/ready` returns 200 as DB/schema readiness, and `/worker-health` returns 200 with a fresh heartbeat. A liveness 200 by itself does not mean DB-backed requests are ready.
3. `/api/stats`, `/api/search?q=LGPD`, the art. 389 change endpoint, history, and the public hero flow return expected responses; DB connection failures should surface as bounded generic 503 responses rather than traceback-driven 500s.
4. Railway HTTP 5xx rate remains below 1% over at least 30 minutes with enough real requests to make the rate meaningful; no renewed logger cap/drop warnings.
5. A post-recovery backup completes, object and manifest are present, checksum/size match, and the backup reports `restore_verified=true` (or an isolated restore is re-run against the new object).
6. Recheck at least the documented browser matrix or an agreed representative route/viewport matrix against the recovered release.

If any gate fails, keep release status NO-GO and retain this report as the incident snapshot.

## Rollback and recovery guidance

- **Do not roll back or redeploy app code as the first response to this evidence.** Current web source is `main` commit `22ab226` (docs-only after the validated app commits); logs identify Postgres recovery as the immediate failure, and the Postgres service's last deployment predates this docs commit.
- **Do not overwrite production from a backup under this review.** The disk emergency reviewer found no measured safe cleanup candidate. The owner can apply the separately reviewed, non-destructive 5.0 → 6.5 GB Postgres volume resize after completing the required 2FA; it is not yet live. Restarting/altering Postgres is outside this read-only QA authorization.
- Preserve current deployment IDs, DB/volume state, logs, and latest usable backup evidence. Have the platform/database incident owner inspect Postgres recovery logs, storage/volume health, and Railway events first.
- If recovery cannot complete, follow `docs/runbooks/backup-restore.md`: restore the verified dump into a **new isolated PostgreSQL service/volume**, compare manifest row counts and Alembic heads, validate app connections against that isolated instance, then plan a deliberate cutover with an explicit rollback target. Never test restore against the live DB.
- Roll back an application deployment only if a separate verified app regression is found and the target commit passes compatibility checks with the current DB schema. Schema downgrade or DB volume rollback is not an application rollback.

## Review status for follow-up code PRs

PR #81 (`Protect catalog queries during database pressure`) is open and unmerged at head `fcd76635edb32a4f76754a564bab9688856fc9fa`. It now makes `/health` and `/api/health` pure liveness, keeps `/ready` as DB/schema readiness, catches schema query SQLAlchemy errors as generic 503 within `/ready`, maps request `OperationalError` to no-store 503 with `Retry-After`, limits outage log output to one event per 30 seconds, and adds shared 90/min budgets for history/proceedings/coverage/audit GETs. The broader limiter covers stats, law list, search and existing detail/job routes. I ran `pytest -q` on the corresponding isolated final worktree: **158 passed**, one upstream deprecation warning. GitHub CI run 69 passed Python, E2E, and image jobs. This is code/CI validation only; it is not deployed or production-verified and must not be deployed until storage is recovered.

PR #86 (`Control automatic bulk backfills by worker mode`) is open/unmerged at exact remote head `dcfc31b6c33a00d0f3a6d6af4a8f164261f2b2e5`; CI run 70 passed. Its tree matches the reviewed local implementation commit `4e18d548ccd8ab3824c5a81b054198b2fb4c0279`, whose full local suite passed 157 tests. The change defaults background backfills to `off`, supports `hot` and `continuous`, preserves paused DB/outbox/stream jobs, exempts explicit interactive jobs, sanitizes the marker from public job messages, and has no migration. It is not production-validated.

**P1 reviewer follow-up:** the worker's `should_process_job()` currently classifies stream deliveries by the job's current message only, without first excluding terminal rows. A completed/failed/cancelled backfill job can retain its marker in the final message and be deferred forever in `off`; unmarked terminal rows are also deferred as unknown. This can occur if processing committed but the worker crashed before ACK, or Redis ACK failed. A priority promotion can similarly clear a marker, process the DB row directly, then leave the old stream item pending. This does not delete durable data or re-run completed work, but can retain pending stream entries and inflate pending counts. Worker owner was asked to handle terminal rows as safely ACKable and add regression coverage; re-review the follow-up before treating this queue-hygiene item as closed. Production DB recovery and stable storage headroom remain hard no-deploy gates.
