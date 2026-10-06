# C-sync-budget-worker handoff

## Ownership and revision

- Branch: `codex/final-sync-budget`
- Base SHA: `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`
- Implementation commit: `828f05d3d739da7d1e8f3e91ff5df240f9a7dbb9`
- Branch head after handoff documentation update: reported to coordinator
- Production access or mutation: none
- Database schema changes: none

## Findings

- `sync_all_sapl_catalogs()` previously submitted every configured SAPL instance at once (32 configured installations) with up to four parallel catalog writers by default.
- Each source scan fetched every ascending page in one call. Page checkpoints made an interrupted scan resumable, but there was no per-cycle page or time budget, and the worker log did not distinguish an incomplete scan from a completed one.
- A completed source was skipped for seven days, so new records at an active source could wait for a full rescan. SAPL adapter code has no documented modified-since cursor; newest numeric IDs provide a useful incremental fast path, while retroactive/low-ID additions still require a full scan.
- `BACKGROUND_BACKFILL_MODE=off` already pauses automatic text/history backfill while leaving catalog refresh and interactive jobs separate.

## Changes

- Added a descending-ID, latest-page probe for enumerated sources and in-progress scans that have a safe known-ID watermark. It upserts only IDs newer than the watermark and persists its timestamp and maximum ID in the existing `source_registry.scope`; it adds no schema dependency.
- Kept periodic full scans for historical completeness. They now process a bounded number of pages per call, preserve page checkpoints on partial completion, return `complete=false` plus progress, and accumulate added/refreshed totals across resumed pages.
- Replaced the unbounded parallel fan-out with a fair oldest-check-first scheduler. It limits the number of probe sources, full-scan sources, total full-scan pages, pages per source, and a soft cycle time budget.
- A full descending page made only of IDs newer than the saved watermark marks an incremental backlog and makes the full scan due, avoiding a false claim that the whole backlog was covered.
- Worker logs now include incremental probes, full-page totals, incomplete-scan counts, per-source progress, and the cycle budget.
- Added an operator pause for optional historical enumeration with `SAPL_FULL_SOURCES_PER_CYCLE=0` or `SAPL_FULL_PAGES_PER_CYCLE=0`. `SAPL_INCREMENTAL_SOURCES_PER_CYCLE=0` also pauses incremental catalog writes for stop-threshold response. Interactive hydration remains governed by its existing queue policy.

## Default operating values

- Refresh scheduler: at most hourly (`CATALOG_REFRESH_CHECK_SECONDS`, existing default).
- Incremental probes: 8 eligible sources per cycle, one newest-ID page per source, refresh interval 1 hour. With 32 eligible sources, approximate revisit interval is four cycles under a healthy scheduler; this is not a production measurement or source SLA.
- Historical full scan: 4 sources per cycle, up to 5 pages per source, up to 20 pages total per cycle.
- Soft cycle budget: 300 seconds. HTTP operations are bounded by remaining time where possible, but a source library retry or an in-flight request can overrun the deadline slightly.
- These defaults are safety bounds, not a monthly-cost or growth-rate guarantee. Tune only with measured Postgres disk and sync workload.

## Validation

- `/tmp/leiaberta-sync-budget-venv/bin/python -m pytest -q`
- Result: 196 passed; six existing Starlette/httpx and PyMuPDF binding deprecation warnings.
- `/tmp/leiaberta-sync-budget-venv/bin/python -m compileall -q app/catalog_sync/sapl.py app/worker.py`: passed.
- `git diff --check`: passed before commit.
- No production, live-source, Railway, Postgres, Redis, or cost validation was performed.

## Impact, risk, and dependencies

- New monotonic SAPL IDs can be discovered without waiting for full historical enumeration, subject to the per-cycle source schedule and page cap.
- Low-ID additions, upstream reassignments, or metadata corrections are not guaranteed by the latest-page probe. They depend on the bounded full scan; if the catalog is large, completion may span multiple hourly cycles. Logs expose progress and completion separately.
- If more than one page of new IDs arrives between probes, the code flags backlog and schedules the full scan. The first newest page is still imported; the full scan is what completes coverage.
- Existing sync configuration and `source_registry.scope` are required. No migration is required. Railway worker environment variables are not changed by this branch.
- Parent coordinator should apply the branch only after production gates/backup are satisfied, inspect effective worker values, and verify that the exact deployed SHA emits the new progress fields while the disk stays within budget.

## Rollback

- Normal code rollback to the preceding worker image; schema state is unchanged.
- If a release must stop historical writes before rollback, set `SAPL_FULL_SOURCES_PER_CYCLE=0` and `SAPL_FULL_PAGES_PER_CYCLE=0`; set `SAPL_INCREMENTAL_SOURCES_PER_CYCLE=0` if all SAPL catalog writes must pause. Restart the worker after applying variable changes.
- Existing `source_registry.scope` checkpoints and laws remain intact. No cleanup or destructive operation is part of this work.

## Atualização do coordenador — 2026-10-06

PR #91 corrigiu starvation de 13 fontes SAPL enumeradas sem watermark: o probe agora persiste watermark/última tentativa e habilita continuidade paginada quando houver backlog. Em produção, 589 instâncias SAPL elegíveis; 8 probes/ciclo, check a cada 3600 s (rotação teórica ~74 h), full scan 20 páginas/ciclo (~4.000 registros) e quatro scans incompletos observados. Um ciclo teve timeout de Manaus após retries; ciclo subsequente fechou sem erros. Não tratar timeout como ausência. Para reduzir bootstrap, coordenador definiu `SAPL_FULL_PAGES_PER_CYCLE=4`; deployment `d0f1361b-eda1-41b6-b7c3-9bfcd6036869` terminou SUCCESS; primeiro log pós-config mostrou 8 probes, `full_pages=4`, 1 scan incompleto, zero erros; as 4 páginas do ciclo percorreram 400 linhas e registraram `added=0`. Isso dá teto operacional aproximado de 9.600 linhas de página/dia se ocorrer exatamente uma vez por hora; erros podem antecipar ciclo e portanto não é um teto diário rígido. Ainda não há orçamento diário persistente em bytes/novos registros. Backfill OFF, worker concurrency 1; jobs interativos seguem ativos. Soak após a nova configuração é requisito.

## Fechamento pós-deploy — 2026-10-06 20:25 UTC

Worker final no SHA funcional `f6084abcea82bebe0ade4699c1ce9460947cc571`, deployment `fe448b29-bab9-4cbe-a4bb-2fedcc068394`. Primeiro ciclo: 8 probes, `full_pages=4`, erros=0, 1 scan incompleto; full scan sem novas linhas, probes reportaram normas novas. `BACKGROUND_BACKFILL_MODE=off`, concurrency 1; fila pendente=0. Soak >30 min após readiness e disk estável. Não há limite diário persistente de bytes/novos registros; 24h de observação segue bloqueando GO.
