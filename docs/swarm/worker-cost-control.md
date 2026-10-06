# Worker bulk backfill control

## Goal and scope

Add a reversible worker policy for automatic text and history backfills while keeping user-requested hydration, history, and provenance jobs available. This is a code-only change: no migration, production database operation, Railway mutation, queued-job cancellation, or data deletion is included.

## Mode behavior

`BACKGROUND_BACKFILL_MODE` accepts `off`, `hot`, or `continuous`; an unset value means `off`. Invalid values fail validation instead of silently starting an unknown policy.

| Mode | Automatic batch enqueue | Existing marked batch jobs | Interactive jobs | Catalog discovery and refresh |
| --- | --- | --- | --- | --- |
| `off` | Paused | Left queued/pending and unacknowledged | Processed normally | Continues |
| `hot` | Only laws with `Law.hot = true` | Only hot laws may run | Processed normally | Continues |
| `continuous` | All eligible laws, subject to existing caps | Resumes all queued work | Processed normally | Continues |

Batch jobs receive an internal marker in the existing `HydrationJob.message` field, so this needs no schema change. Pre-existing queue messages from the previous batch producers are also recognized. An older queued/retry job whose message no longer identifies its origin is treated as ambiguous and remains deferred in `off` and `hot`; a new user request can promote an active queued row to the explicit interactive marker, or `continuous` can resume all work. The API strips the internal marker from job-message responses so readers do not see it. Dedupe remains based on the existing active-job constraint and is unchanged.

When a paused batch job already has a Redis Streams entry, the worker leaves it pending and does not ACK it. Its database job and outbox remain intact. Unsent outbox rows are excluded from dispatch while paused; switching to `hot` or `continuous` makes eligible outbox rows dispatchable again. A worker restart reads the configured mode; pending Redis entries can be recovered by the existing `XAUTOCLAIM` lease path. Terminal or missing-job deliveries are passed to the existing job processor, whose durable guard confirms no work is eligible and lets the delivery be ACKed. No retryable queue item is deleted or reset.

## Runtime configuration

Configure the variable on the worker service only unless the same process also runs the worker. The safe default is `off`. To resume all existing backlog, set `continuous` and restart the worker after PostgreSQL is healthy. To resume only prioritized laws, set `hot` and restart.

Catalog refresh remains independent of this setting. Existing per-source active-job caps, hydration concurrency, catalog concurrency, source freshness, dedupe, and retry rules remain in force.

## Validation performed

Command:

```sh
pytest -q
```

Result: 162 passed; one existing Starlette/httpx deprecation warning. Coverage includes default-off and invalid-mode validation; all three producers paused without mutation; hot-only selection; legacy queued-job recognition; preservation and mode-based resumption of outbox work (`off` → `hot` → `continuous`); interactive job dispatch; safe ACK of terminal stale stream entries while ambiguous queued work remains pending; API marker hiding; bounded retry delays, suppressed-error summaries, successful-loop reset, schema-wait error redaction, and private aggregate queue-depth telemetry with failure isolation.

No live Railway, PostgreSQL, or Redis validation was performed. At implementation time the production database was reported in recovery, so this change must not be deployed until that incident is resolved and readiness is restored. Production deployment is intentionally outside this branch task.

Worker schema readiness retries also use capped exponential delays (default 3, 6, 12, 24, then at most 30 seconds) within the existing five-minute timeout. Readiness logs are emitted on the first and every tenth attempt, and exception text is not logged. The main worker loop applies the same capped delay to classified SQLAlchemy database and Redis transport failures, resets it after a successful loop, and logs the first and every tenth identical error with the number suppressed. Other exceptions retain normal traceback visibility and the short retry interval.

Every five minutes, the worker emits a private operational log summary containing only Redis stream length and consumer-group pending count. It does not log law/job IDs, consumer names, or publish queue depth through the public API. Redis telemetry errors are caught and reduced to the exception class so queue processing continues.

## Rollback

Rollback is a normal application code rollback; there is no schema change. Existing job and outbox rows remain valid. If bulk work must pause immediately, set `BACKGROUND_BACKFILL_MODE=off` and restart the worker. If code rollback is required, return the worker to the prior image; the old worker may resume queued batches, so keep worker replicas stopped or retain its active-job caps until the intended policy is restored.

## Operational limits

The mode is read when the worker starts; changing it requires a worker restart. Paused stream entries remain pending until a worker in an eligible mode reclaims them. `hot` depends on the current `Law.hot` flag and does not infer urgency from user traffic. This change controls bulk queue consumption and automatic producers; it does not reclaim PostgreSQL disk space or repair the reported database recovery state. Observe disk and worker memory after any later resumption.
