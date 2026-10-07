# B — Snapshot migration handoff

## Scope and result

- Branch: `codex/final-snapshot-migration`
- Starting repository SHA inspected: `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`
- Implementation and tested SHA: `40929611c251a1653a30595778519bfb7d6407ce`.
- Handoff documentation is a follow-up commit on the same branch; no implementation code changed after the tested SHA.
- Production impact: none. This worktree used SQLite fixtures and a fake S3 client only; no production database, bucket, credentials, Railway service, or deploy was accessed.
- `source_snapshots.raw_body` is unchanged and no schema migration was edited.

The repository contains `scripts/migrate_source_snapshots_to_object_storage.py`, but not the previously observed module `scripts.migrate_all_source_snapshots_to_object_storage`. The former script handled only one manually-cursored batch and the observed service command omitted `--apply`, which means that command could not have uploaded anything even if the module name resolved.

The existing script is now a finite high-water scan with bounded SQL transactions (up to 100 rows and a default 64 MiB of uncompressed data), an atomic local JSON checkpoint, a configurable restart limit, bounded whole-operation retries, per-batch progress JSON, and a final database-backed completion report. It SHA-256 validates the DB bytes and `put_verified` reads back/decompresses and hashes the bucket object before writing a pointer. SQL pointer writes commit by batch; a failed upload rolls back that batch and leaves the cursor unchanged. New pointer writes include `storage_backend`, `object_key`, and uncompressed `size_bytes`; pointer inconsistencies keep status partial. Object store config validates the endpoint URL and path/virtual addressing choice, and SDK retries are single-shot so the runner's retry count is bounded.

## Local verification

- Focused storage tests: `12 passed`.
- Full suite: `196 passed, 6 warnings` (warnings are upstream Starlette/httpx and PyMuPDF deprecations).
- `compileall` for the changed Python modules and tests: passed.
- `git diff --check`: passed.
- CLI `--help`: passed and shows the resumable options.

All these checks are local. They do not prove S3 credentials, bucket policy, Railway command configuration, upload counts, production checksums, or production migration completion.

## Production operation and evidence needed

After verifying backup/restore, target DB, S3 access, and staged Railway changes, replace the stale command with a one-shot command equivalent to:

```bash
python -u -m scripts.migrate_source_snapshots_to_object_storage --apply --batch-size 25 --max-batch-bytes 67108864 --checkpoint /<durable-mounted-path>/source-snapshot-migration.json
```

Use the owner's actual durable checkpoint mount path; do not assume one exists. The application must have the dedicated `SOURCE_SNAPSHOT_S3_*` variables, a working endpoint, bucket, region, addressing style, and scoped `get`/`head`/`put` access. Without `--apply` the run is a read-only dry-run. Stop the temporary service after the one-shot completes.

Retain the final JSON and batch progress logs. Require `status=complete`, zero pending pointers, and zero pointer inconsistencies. Report the fixed `max_id`, snapshot and unique key counts, raw bytes, verified object read-back, compressed/reference bytes, invalid rows, attempts/failures, elapsed time, and pointer totals. A process `SUCCESS` is not evidence of migration completion. The `bucket_bytes_added` counter describes objects whose missing-before/upload/read-back path succeeded in this run; it is not an authoritative bucket inventory after orphan recovery or concurrent same-key writes. Compare with S3 inventory/HEAD evidence for actual occupancy.

## Limits, risk, rollback

- Checkpoint JSON contains aggregate metrics and IDs only. Keep it on a durable mounted path for replacement/restart recovery. The database pointers remain the source of truth; if the checkpoint is lost, a fresh scan skips committed pointers, but operation counters from the lost checkpoint cannot be reconstructed exactly from the local log.
- A database checksum mismatch or missing DB payload is reported by ID only, gets no pointer, and leaves the migration `partial`; investigate without rewriting legal bytes/checksums. `--reset-checkpoint` starts a fresh scan after an operator decision.
- Existing pointers are counted and structurally checked, but this migration does not independently read every pre-existing pointer object. Each legacy row it migrates receives S3 read-back SHA verification. Do a separate full-object audit before any raw-body removal.
- A crash after object PUT but before SQL commit can leave a content-addressed orphan. It is safe for retry, but actual total bucket occupancy requires an inventory or full audit.
- Rollback: stop the one-shot job, disable new S3 writes by removing the approved object-store configuration, and roll back application code if needed. Existing DB copies remain intact; do not delete bucket objects or downgrade pointer columns as part of this handoff.
- No proof here supports reclaiming PostgreSQL disk. That requires the separate D1/D2 gates and remains explicitly out of scope.

## Atualização do coordenador — 2026-10-06

A auditoria real terminou: 14.202 linhas apontam a 14.201 objetos únicos (64.972.169 bytes comprimidos/armazenados; 252.701.649 bytes brutos verificados), zero objetos faltando, órfãos, checksum divergente ou falhas. O migrador de produção registrou 14.200 updates verificados em 569 lotes; há uma linha duplicada por checksum. `raw_body` continua presente nas 14.202 linhas. Economia física PostgreSQL: 0 bytes. A tabela snapshot representa ~108 MB contra 2.331 GB da tabela `laws`; D1/D2 seguem fechados até dual-read/backup de objeto e estratégia de retenção/restore serem demonstrados. O serviço one-shot tem zero uso medido e nenhuma montagem de volume, o serviço `source-snapshot-migration` foi removido depois de auditoria completa; não possuía volume montado e CPU/RAM/disco estavam em zero. Objetos verificados permanecem no bucket e métricas nesta handoff.

## Rechecagem do coordenador — 2026-10-07

- O `main` atual contém o runner finito/retomável (420 linhas) e `app.storage.source_snapshots` usado pela aplicação. A auditoria operacional de 14.201 chaves foi executada em 06/10 via download, descompressão e SHA-256; não foi repetida em 07/10.
- 06/10: 14.200 rows migradas em 569 lotes; 14.201 objetos únicos lidos e verificados; 64.972.169 B em bucket e 252.701.649 B brutos distintos; zero missing/orphan/mismatch/erro. Backup de 07/10 relata 14.203 source_snapshot rows; pointers da nova linha não foram contados nesta auditoria.
- Serviço temporário `source-snapshot-migration` foi removido antes desta rechecagem após inspeção de ausência de volume/dado persistente. Buckets ficam intactos. Nenhum `raw_body` foi removido; D1/dual-read, durability/recovery independente de objeto e ganho material não passaram.
- Nenhuma operação de limpeza/SQL foi feita. Continuar preferindo Postgres para conteúdo enquanto um teste isolado bucket-only e a política de recuperação dos objetos S3 não existirem.
