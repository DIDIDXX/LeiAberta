# Final cost and stability report

**Status:** execution in progress; values captured on 2026-10-06 UTC.
**Decision at this capture:** **NO-GO for public launch** pending the checks listed below.
**Repository baseline:** `main` was `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`; integrated candidate before this report was `a3b01a6` on `codex/final-stabilization-integration`. Exact merged/deployed SHAs must be appended after release verification.

## Stability, database and producer

`web`, `worker` and `postgres-backup` were confirmed by sanitized Railway reference names to use `postgres-blue` / database `railway`. Blue is PostgreSQL 18.6, Alembic `20261006_0011`; DB size 2,822,862,527 bytes, volume 3.334324224 of 5 GB (66.69%), WAL 301,989,888 bytes in 18 files. Largest relations: `laws` 2,330,796,032 bytes, `legal_nodes` 331,358,208, `source_snapshots` 107,683,840. The prior rapid increase was the large paginated SAPL catalog enumeration while text backfill was off, not a growing snapshot count. The worker check interval is now hourly; the short post-setting disk window was nearly flat, but a final deployed 30–60-minute workload soak is pending.

The worker currently runs `BACKGROUND_BACKFILL_MODE=off`, concurrency 1, and continues catalog refresh and interactive jobs. Candidate code bounds SAPL newest-ID probes and historical pages per cycle, preserves checkpoints, and logs partial progress. New high numeric IDs can arrive through incremental probes; low-ID changes and retroactive upstream edits wait for paginated historical rescans. At 20 pages/hour, one complete 1.39M-row catalog sweep could take about 29 days. This is a bounded eventual-discovery policy, not an instant update SLA.

The old Postgres still uses 4.996513792 GB of its 5 GB volume and logs a `No space left on device` panic. It remains intact because deleting it requires the owner's explicit approval, but it is not a safe rollback target in its current state.

## S3 migration and payload status

Production migration logs report `selected=14200`, `updated=14200`, `verified=14200`, `invalid=0`, across 569 apply batches, for 252,381,702 raw bytes. Current DB inventory: 14,202 S3 pointers, 14,201 unique keys, 252,709,304 raw DB payload bytes, 64,972,169 bucket-stored bytes. A 17:42 UTC in-container audit used the production application's `read_verified()` path on every unique key: 14,201/14,201 passed decompression and SHA-256, with zero missing objects, orphans, mismatches or errors; 252,701,649 unique-object raw bytes verified. One content-key duplicate is shared by two rows. A first standalone audit helper falsely reported universal mismatch and was discarded; the independent sample and full canonical recheck passed.

`raw_body` remains filled on all 14,202 rows. Physical bytes reclaimed: 0. The full snapshot relation is 107,683,840 bytes, while `laws` alone uses 2.33 GB. Even if all snapshot TOAST (93.5 MB) became reusable, that would be modest and would not shrink the Railway file automatically. No payload was nulled, no vacuum full/repack/reindex ran. Bucket versioning/lifecycle and independent restore strategy are not configured, and bucket-only dual-read has not passed an isolated restore; do not remove relational copies.

## Backup and recovery evidence

The latest production backup object is `postgres/leiaberta-production/20261006T171425Z-7a475cec.dump`, 336,161,242 bytes, SHA-256 `b899bb4f28ae6e21d947136273a2389f90322c824d532aed3958db20be5d620e`. Its manifest records `restore_verified=true` and Alembic `20261006_0011`; the full dump was downloaded and its checksum matched. Manifest row counts: laws 1,927,120; legal_nodes 211,496; source_snapshots 14,202; hydration_jobs 30,667; job_outbox 30,653; history_events 4,049; law_versions 14,135; source_registry 620. The daily backup cron has been restored at 03:00 UTC and the cron deployment settled SUCCESS.

This backup predates deployment of the locally integrated strengthened verification. The D branch now verifies dump object size and readback SHA, manifest readback and a deterministic public-schema signature (columns, constraints, indexes, triggers, sequences, views, enum labels and extensions) on isolated restore. A new run on that exact deployed SHA, with schema and constraint proof, remains pending. Previous dumps are retained.

## Product and legal evidence

Production checks at 17:26 UTC on web SHA `eb7cea7ddf22737b30bd4f21285f7ea15e26891d` passed `/`, health/readiness/worker health, stats, sources, typo search for `LGDP`, law 10.406/2002, Article 389 provenance, history, blame, change detail, `/fontes`, `/cobertura`, `/sobre`, OpenAPI and sitemap. Tested mobile/tablet/desktop layouts had no horizontal overflow; no page/console errors or HTTP 5xx were observed. Local Playwright E2E passed 5 tests; Python tests passed 209 with 6 upstream deprecation warnings.

Production's existing Why/Blame wording overstated the Normas.leg.br transcription as official. The candidate fixes its source label and preserves the caveat. The production recheck after deployment is pending. Art. 389 comparison remains `verified_source`, not `verified_primary`; the archived transcription is explicitly classified nonofficial, and exact primary-source excerpts before and after Lei 14.905/2024 have not been independently stored and proven. Do not elevate this legal evidence claim. A production cold-law hydration job has not yet been safely exercised end-to-end.

## Service and storage usage estimate

Observed one-hour average resources after recent stabilization (approximate, 60-second metric samples):

| Service | Avg CPU (vCPU) | Avg RAM (GB) | Current / peak RAM (GB) | Volume used |
|---|---:|---:|---:|---:|
| web | 0.0035 | 0.138 | 0.211 / 0.214 | none |
| worker | 0.0134 | 0.188 | 0.066 / 0.295 | none |
| postgres-blue | 0.0260 | 2.616 | 2.900 / 2.900 | 3.334 GB of 5 GB |
| old Postgres | 0.2335 | 0.191 | ~0.191 average; restart loop seen | 4.997 GB of 5 GB |
| Redis | 0.0025 | 0.014 | ~0.014 | 0.154 GB of 5 GB |

The sample for `postgres-backup` overlapped a one-shot verification task (peak 1.99 vCPU and 5.50 GB memory), so it was excluded from steady monthly compute and should not be multiplied by 730 hours. Daily backup resource time and network use recur at their schedule, but that job window is not a valid steady hourly sample.

Railway published tariffs used: CPU $20/vCPU-month, RAM $10/GB-month, volume $0.15/GB-month and service egress $0.05/GB; storage buckets $0.015/GB-month with bucket API and bucket egress free. See [Railway plans](https://docs.railway.com/pricing/plans) and [bucket billing](https://docs.railway.com/storage-buckets/billing). The bucket's roughly 1.36 GB occupied by backups and snapshots costs about $0.02/month at that bucket-storage rate. A rough CPU+RAM estimate from the service averages is about $37/month with the old database attached and $30.5/month after its compute is removed. Adding used-volume rates and bucket storage yields about $38.3 and $31.0/month before traffic egress and scheduled backup time. Including roughly $1.83/month web egress and $0.50/month daily-backup egress gives $40.2–$40.7 now and $32.9–$33.4 after old DB removal. Costs are estimates, not guarantees, and exclude unknown plan minimum/credits. Actual invoice access was unavailable. The aspirational $10–15 target is **not met**.

Volumes: blue 5 GB configured / 3.334 GB used; old Postgres 5 GB / 4.997 GB; Redis 5 GB / 0.154 GB (15 GB provisioned total, ~8.485 GB used). Buckets: backup ~1.295 GB and source snapshots ~0.065 GB (about 1.360 GB total). Temporary backup/restore and migration services have no mounted volumes; restore and migration replicas are zero at capture. Backup is daily. Old database currently adds an estimated ~$7–8/month between average compute and volume charges, while retaining a full, unhealthy service.

## Exact revisions and launch gates

At initial inspection `main` and all primary service deployments were on `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`; backup's latest scheduled deployment on that revision is `ea5b459b-e572-4f21-b975-c639bcdbeb83`. Current production deploy SHAs must be refreshed after the integrated PR is merged; update this report with per-service SHA and deployment ID before declaring release complete.

**Decision: NO-GO.** The remaining release gates are: final candidate deployment and production Why/Blame recheck; full bucket integrity audit result; strengthened post-change backup with schema signature and isolated restore; cold-law hydration through the real worker; representative disk soak and 24-hour observation; object retention/recovery strategy; and owner approval before removing the old DB. The old service has disk errors, so keep it intact for forensics while acknowledging it is not a reliable rollback. No old database, bucket, or legal payload was deleted.

## Atualização autoritativa de produção — 2026-10-06 19:50 UTC

Esta atualização substitui estados “pendente” do retrato inicial quando marcada como comprovada abaixo; não substitui nem reescreve os relatórios históricos.

### SHA, topologia e proteção

`main` no início desta atualização: `5d49fb5956096173e3094aa422f746f0782eb92e`. Web `192d8752-8712-492f-a786-d243a9c8924a` e worker `04bf9413-3d40-4e7b-85af-614baeea50d2` estão nesse SHA; configuração Railway descreve `postgres-blue` como DB novo, Postgres antigo separado e nenhum staged change. Os valores de `DATABASE_URL` estão redacted pela integração OAuth; o CLI local solicitou login, portanto não foi possível reler host nessa amostragem. O inventário anterior registrou as referências como `postgres-blue`; a rodada de backup/row counts concorda com o banco atual. Não escrever essa limitação como nova verificação independente.

### Volume, sync e métrica

Postgres azul, janela Railway 1 h/61 amostras: capacidade 5 GB; max 3.303645184 GB (66.1%), min 3.302301696 GB, último 3.286777856 GB (65.7%). A janela inclui ciclo representativo SAPL; queda de ~17 MB no último ponto pode ser rotação/reuso de arquivos e não se atribui a `raw_body` (intacto). CPU 0.0021 média/0.0060 max; RAM 2.637/2.944 GB. Worker CPU 0.00117/0.00936, RAM 0.0808/0.0833 GB, concurrency observada 1. Web RAM 0.0742 GB; Redis RAM 0.0137 GB e disco 0.1527 GB. Banco antigo permaneceu em 4.996513792/5 GB, CPU média 0.243, RAM 0.218 GB.

O ciclo após fix do watermark retornou `incremental_probes=8`, `full_pages=20`, `records=4000`, `sources=12`, `errors=0`, `full_scans_incomplete=4`, 300 s de teto; as páginas completas observadas atualizaram 100 linhas com `added=0`. O worker check é horário; 589 fontes e 8 probes/ciclo implicam rotação teórica de ~74 h. O cap de bootstrap foi reduzido para 4 páginas/ciclo em config Railway, deployment `d0f1361b-eda1-41b6-b7c3-9bfcd6036869` concluiu SUCCESS: `incremental_probes=8`, `full_pages=4`, `records=1400` no checkpoint, `sources=9`, `errors=0`, uma fonte ainda incompleta, e quatro páginas com `added=0`. O teto por ciclo está ativo; limite diário em bytes/novos registros não existe. Se houver exatamente um ciclo/h, 4×100×24 = 9.600 linhas de página/dia como limite aritmético aproximado, mas falhas provocam retry mais cedo e não existe contador persistente de orçamento diário em bytes. Não declarar teto diário rígido.

### S3 e bytes relacionais

Migração e auditoria: 14.202 snapshots apontam para 14.201 objetos únicos; 64.972.169 bytes no bucket, 252.701.649 bytes brutos verificados em download/descompressão/SHA-256; zero faltando, órfão, divergência ou erro. O job migrou 14.200 linhas em 569 lotes; uma duplicata content-addressed explica a cardinalidade. DB manteve `raw_body` nas 14.202 linhas. Reclaim físico atribuído à remoção: 0 bytes; tabela completa ~107.683.840 B / TOAST 93.536.256 B, menor que `laws` 2.330.796.032 B. D1/D2 não passaram: bucket-only dual-read e restore de objetos, retenção/versionamento independente não provados.

### Backup pós-cutover

Backup completo: `postgres/leiaberta-production/20261006T183241Z-6c86c047.dump`, 336.170.020 B, SHA dump `6a6ee28d4fa5b0b57db28b1b115aa6c14ddd5ce93f7e81eb2909be17131c42c5`; manifest `postgres/leiaberta-production/20261006T183241Z-6c86c047.dump.json`, 112.778 B, SHA `a7e895806c68987b1cd4b193a70ec7695645097eb659f66d51803abed8fb9c83`. Ambos foram lidos de volta; restore isolado `restore_verified=true` em 45.458 s; row counts/schema signature/Alembic `20261006_0011` conferiram. Contagens: laws 1.927.162, legal_nodes 211.497, snapshots 14.203, hydration_jobs 30.668, job_outbox 30.654, history_events 4.049, law_versions 14.136, source_registry 620.

Os serviços temporários `postgres-blue-restore` e `source-snapshot-migration` foram removidos após confirmar zero volumes e zero uso recente; buckets e os três volumes persistentes do Postgres antigo, blue e Redis permanecem.

Config de backup foi definida como start `sh /app/run_backup_as_postgres.sh`, cron `0 3 * * *`, restart NEVER, mas o container live continua sendo runner one-shot iniciado pela CLI e não contém ainda o wrapper versionado. O próximo deploy precisa provar que imagem Dockerfile inicia como `postgres` e o cron executa; até lá, há backup manual comprovado, cron configurado, mas não cron operacional verificado.

### Produto, custo e decisão

Smoke HTTP novo: 17/17 rotas e APIs com HTTP 200; APIs incluem busca `LGDP`, estatísticas/fontes, Código Civil art. 389, nodes, histórico, blame, provenance e diff. QA visual prévio em 390/430/768/1440 px passou; caveat do comparativo arquivado de Art. 389 ainda é Normas.leg.br não oficial, sem transcrição primária exata before/after salva. Cold hydration real completou processamento, mas com resultado parcial e `article_count=0`, então o resultado deve seguir como revisão necessária.

Estimativa publicada com tarifas Railway e uso anterior: US$ 40.2–40.7/mês incluindo Postgres antigo; US$ 32.9–33.4 depois de aposentadoria aprovada, antes de mudanças de tráfego/uso. Fatura real não acessível; alvo aspiracional US$ 10–15 não atendido. Permanecem ~15 GB de volumes configurados (três volumes de 5 GB); soma de ocupação em 1 h: azul 3.287 GB, antigo 4.997 GB, Redis 0.153 GB. Bucket backup+snapshots estimado no relatório anterior ~1.36 GB.

**Decisão: NO-GO para lançamento público agora.** Gates restantes: deployment e execução real do cron wrapper; observar worker cap pós-deploy e 24 h; política de retenção/recuperação de objetos; confirmar referência DB atual via ferramenta autorizada; revalidar hidratação cold estruturada e fontes com falha sem inferir ausência; aprovação expressa antes de retirar DB antigo. Fatura e custo alvo não foram comprovados.

## Estado após deploy funcional f6084ab — 2026-10-06 20:25 UTC

Este é o SHA funcional final validado nesta rodada: `f6084abcea82bebe0ade4699c1ce9460947cc571`. Deploys Railway: web `69750e48-27eb-47d7-af3b-9acdfa20f7c1`, worker `fe448b29-bab9-4cbe-a4bb-2fedcc068394`, backup `4e4e9f6b-63e5-4453-86e0-500e8235bf24`; os três SUCCESS nesse SHA. `main` era esse SHA no fechamento do deploy; a atualização desta seção é relatório do mesmo estado.

### Soak e workload

Soak de 19:54:51 a 20:25:36 UTC (30 min 45 s a partir do worker pronto). Múltiplas amostras de métrica Railway: disco azul 3.270852608 GB nos pontos finais; janela de 1 h no fechamento current/min 3.270852608 e max 3.303645184 GB (65.4%–66.1% do volume de 5 GB). Sem expansão observada pós-ciclo capado; variação negativa vs máximo anterior não é reclaim de `raw_body`, e sim arquivos/reuso/WAL não discriminados pelo provedor. Na última janela: Postgres CPU avg/max 0.00474/0.08120, RAM avg/max 2.371/2.413 GB; worker CPU 0.00300/0.04081, RAM 0.0810/0.1564 GB; web RAM 0.0963/0.1582 GB; Redis RAM 0.0142 GB/disco 0.1527 GB. Old Postgres continua 4.9965/5 GB e CPU média 0.250.

O ciclo real final do worker processou 8 probes e 4 full pages, zero erros, uma fonte ainda em bootstrap. Probes incrementais gravaram normas recentes; full scan revisou 4×100 linhas sem novas linhas. `BACKGROUND_BACKFILL_MODE=off`, concurrency 1, Redis stream `pending_count=0` (38.305 entradas retidas não são fila pendente). O limite `SAPL_FULL_PAGES_PER_CYCLE=4` é por ciclo: ~9.600 linhas de página/dia com exatamente um ciclo/hora, mas retry pode adiantar ciclo. Ainda não existe quota persistente diária em bytes/novos registros. Não extrapolar esse soak para 24 h.

### Backup wrapper e cron

No mesmo SHA, o build do backup mostrou `COPY scripts/run_backup_as_postgres.sh` e `chmod 0755`; deployment SUCCESS; config live usa wrapper, cron 03:00 UTC e restart NEVER. O log do deployment não tem um novo `postgres_backup_finished` até 20:25; logo o cron ainda não executou. Já existe backup manual pós-cutover completo com objeto e manifest lidos do bucket, SHA correto, restore isolado (45.458 s), row counts, assinatura e Alembic confirmados, listado acima. Não confundir deployment de cron SUCCESS com backup automático concluído.

### Smoke final, custo e GO

Proxy produziu 19/19 HTTP 200 durante o smoke pós-deploy; `/ready` retornou ready e `/worker-health` heartbeat fresh/database ready/processing ready. Cobertura incluiu home, art.389, Why/Blame/Diff/History, typo search, fontes/cobertura, OpenAPI/sitemap e endpoints jurídicos. Browser check anterior em 390/430/768/1440 px sem overflow; a ressalva de Normas.leg.br continua não oficial.

Serviços temporários `postgres-blue-restore` e `source-snapshot-migration` removidos, sem volumes. Custo estimado, calculado por uso/tarifas publicados e não pela fatura real: US$ 40.2–40.7/mês com antigo Postgres lotado presente; US$ 32.9–33.4 após descarte somente com aprovação do proprietário. O acesso à fatura não estava disponível; alvo aspiracional US$ 10–15 não atingido.

**Decisão: NO-GO.** Bloqueios atuais: 24 h de observação; próxima execução cron ainda não concluída; ausência de quota diária persistente; política independente de retenção/restore dos objetos; hidratação cold parcial sem artigos estruturados; host atual de DATABASE_URL redacted nesta sessão; custo acima do alvo aspiracional; aprovação explícita antes de aposentar Postgres antigo. O banco antigo e `raw_body` seguem intactos.
