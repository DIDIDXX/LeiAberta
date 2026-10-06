# ADR-0002: Worker bulk backfill and HOT/WARM/COLD policy

- **Status:** Proposed in PR #86; not deployed
- **Date:** 2026-10-06
- **Decision owners:** LeiAberta maintainers

## Context

The catalog is substantially larger than the materialized text and structured-history stores. Catalog discovery is comparatively lightweight and makes records searchable; hydration fetches and stores full source text, parsed provisions, history evidence, and provenance. Treating every catalog record as an immediate hydration target can grow the PostgreSQL volume and worker memory faster than available headroom.

Production PostgreSQL was reported at 4.9965 GB of a 5 GB volume and in recovery. Critical routes and readiness were failing at that snapshot. Therefore, this policy is code and operator guidance only; it does not authorize a production deployment or data operation during recovery.

## Decision

Keep discovery and materialization as separate work classes:

- **Discovery** enumerates supported sources, upserts catalog metadata, and refreshes according to each adapter's freshness policy. It continues independently of `BACKGROUND_BACKFILL_MODE`.
- **Hydration** fetches complete source text, structure, historical relations, or provenance. Automatic bulk hydration is disabled by default. Explicit user requests for hydration, history, and provenance remain eligible in every mode.

Introduce `BACKGROUND_BACKFILL_MODE=off|hot|continuous`:

| Mode | Automatic bulk scheduling and dispatch |
| --- | --- |
| `off` (default) | Do not enqueue or process tagged bulk jobs. Leave database jobs, outbox rows, and Redis stream messages intact. |
| `hot` | Schedule and process only tagged jobs whose law has `Law.hot = true`. Interactive requests remain eligible. |
| `continuous` | Schedule eligible source batches and process the existing backlog, still subject to source caps, concurrency, retries, and adapter freshness. |

Treat operational priority tiers as follows:

- **HOT:** the existing curated `Law.hot` subset. It is the only background hydration class admitted by `hot`; users can still explicitly request any supported law.
- **WARM:** catalog entries with recent product demand or other evidence of likely reuse, but not in the curated HOT subset. Hydrate on explicit demand and reuse stored materialization; do not add an automatic warm sweep in this change.
- **COLD:** catalog-only entries without a current use signal. Keep them searchable from metadata and hydrate only on explicit demand unless a later measured, approved continuous run includes them.

The tier names do not promise source coverage, legal completeness, or effective-date verification. They are operational prioritization, and only HOT currently maps to a persisted field. WARM/COLD are policy descriptions, not new schema values.

Persist the bulk classification in the existing job message with an internal marker, avoiding a schema migration. Recognize the previous batch producer's exact queue messages. In `off` and `hot`, ambiguous legacy queued/retry messages are deferred conservatively; explicit user requests can promote a queued row to the interactive marker, and `continuous` can resume all eligible jobs. Public API job messages hide the internal marker. Terminal or missing-job stream deliveries may be passed to the existing process function, whose durable guard returns without work, so stale messages can be ACKed safely. Retryable queued/running evidence is not ACKed or deleted.

## Rollout

1. Keep the worker on `off` while PostgreSQL recovery is unresolved.
2. After database recovery, restore `/ready` and critical route health, check DB free space and worker memory, and observe current queue/outbox/stream state without modifying it.
3. Deploy the code and verify the exact commit, worker heartbeat, API health, and unchanged catalog discovery/refresh.
4. Keep `off` initially. If measured headroom allows, switch to `hot` and restart the worker; compare DB growth, worker memory, queue age, failures, and source rate limits.
5. Use `continuous` only after explicit operator decision, disk budgeting for the planned batch, and confirmed backpressure/cap settings. It can resume old ambiguous backlog, so it is a deliberate opt-in.
6. Do not change worker region during the recovery or rollout. Region alignment awaits measured post-recovery comparison of database round-trip latency, egress, worker memory, queue throughput, and source-fetch behavior.

Worker schema readiness waits use capped exponential retries (3, 6, 12, 24, then at most 30 seconds) within the existing five-minute timeout, with log messages on attempt one and every tenth attempt and no raw exception details. After startup, classified SQLAlchemy database and Redis transport failures in the outer queue loop use the same capped backoff, reset after a successful loop, and emit sparse error summaries with suppressed-event counts. Other exceptions keep normal traceback visibility. This reduces repeated DB connection and log pressure during recovery; it is not a circuit breaker for application queries.

After startup, the worker also logs Redis stream length and consumer-group pending count every five minutes. This is a private aggregate log only; it contains no record IDs and is not exposed as a public metric. Telemetry errors are caught so they cannot block queue processing.

## Rollback

Set `BACKGROUND_BACKFILL_MODE=off` and restart the worker. This pauses new automatic producers and processing without changing or deleting durable jobs or source evidence. A code rollback requires no migration reversal; the previous image may resume older automatic work, so keep the worker stopped or retain conservative source active-job caps until a safe mode is restored.

## Consequences

- Catalog search and freshness refresh can continue without materializing every full text.
- Interactive requests remain useful when bulk work is paused.
- Paused Redis stream entries may remain pending until the worker restarts in an eligible mode and its lease-based `XAUTOCLAIM` recovers them.
- WARM/COLD scheduling, per-law user-demand scoring, disk-aware admission control, and cost telemetry remain future work.
- No production data cleanup, volume expansion, migration, region move, or worker deployment is part of this decision.

## Validation

`pytest -q` covers mode parsing, off/hot batch selection, interactive bypass, durable outbox resumption, ambiguous legacy deferral, terminal stale-message ACK behavior, and API marker sanitization. Deployment health and disk behavior must be revalidated only after the production recovery incident is resolved.
