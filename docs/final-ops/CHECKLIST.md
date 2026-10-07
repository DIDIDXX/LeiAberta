# Final stabilization checklist

Legend: **Pass** = evidence recorded; **Pending** = needs post-deploy evidence; **Blocked** = requires owner decision or a durability/operational gate.

## Safety and capacity

- [x] Re-inspect current services, volumes, buckets, routes, database references and Railway pending changes.
- [x] Confirm `web`, `worker`, and backup use `postgres-blue`; verify Alembic head `20261006_0011` and controlled reads/writes.
- [x] Measure DB, relations, TOAST, indexes, WAL and database-to-volume gap; avoid destructive SQL.
- [x] Capture historical growth evidence: catalog laws rose by 821,980 in ~10.7h during SAPL enumeration while snapshot count was nearly flat.
- [x] Set hourly catalog refresh check and verify worker backfill off/concurrency 1.
- [ ] Run 30–60-minute representative limited-sync soak after final worker deploy; capture 15/30/60-minute disk and workload metrics.
- [ ] Confirm new deployment SHA and recheck pending changes before any Railway apply.

## Snapshots and physical storage

- [x] Production migration logs report 14,200 verified updates in 569 apply batches; 14,202 current DB rows point to S3.
- [x] Full in-container GET/decompress/SHA-256 audit via application verifier passed for all 14,201 unique object keys; no missing or orphan objects.
- [x] Measure snapshot payload: 252,709,304 raw DB bytes, 93,536,256-byte TOAST relation, 107,683,840-byte total snapshot relation.
- [x] Retain `raw_body`; no physical reclaim claimed (0 bytes). Estimated potential internal reuse is small versus the dominant `laws` relation.
- [ ] Define external-object durability/retention and recoverability before any payload nulling.
- [ ] Prove bucket-only dual-read in an isolated environment before any payload nulling.

## Backup and rollback

- [x] Current backup targets `postgres-blue`; existing daily cron is restored at `0 3 * * *` UTC, restart policy `NEVER`.
- [x] Read back full 336,161,242-byte dump and match SHA-256; earlier production job reports isolated restore success and row counts.
- [ ] Deploy strengthened backup verification and run one post-change backup with dump readback, manifest readback, schema signature, constraints and isolated restore verified.
- [ ] Reconfirm daily cron after the one-shot run; preserve previous good backups.
- [x] Keep old Postgres intact pending owner approval. Current old service has a full volume and is logging disk errors; do not count it as a working rollback.

## Ingestion and product

- [x] Integrate bounded SAPL incremental probes and paged historical scan budgets with resumable checkpoints and tests.
- [ ] Production deploy and verify logs prove the exact worker SHA applies incremental probes and bounded bootstrap.
- [ ] Safely exercise one cold-law hydration request end-to-end and observe the real worker/job terminal result.
- [ ] Re-smoke all routes, public APIs, typo search and Art. 389 Why/Blame/Diff caveat on the deployed web SHA.
- [x] Pre-deploy real-production viewport/keyboard smoke passed at tested widths; E2E fixture suite passed locally.
- [x] Preserve legal-evidence caveat: Normas.leg.br transcription is classified nonofficial; primary-source before/after excerpts are not independently proven.

## Cost, cleanup and launch

- [x] Estimate live steady-state usage using a one-hour service sample and published Railway tariffs; mark billing invoice unavailable.
- [x] Include old database and object/bucket usage in cost scenarios; target $10–15/month is not currently met.
- [ ] After safe backup and restore proof, inspect and remove only the no-volume `source-snapshot-migration` and `postgres-blue-restore` services if they contain no unique evidence.
- [ ] Complete 24-hour observation or document a safe shorter rollback interval before any old database retirement.
- [ ] Obtain explicit owner approval before deleting the old Postgres service or volume; approval has not been given.
- [ ] Final decision: **NO-GO** until critical checks and owner action above are resolved.
- [x] No domain purchase, plan upgrade, VPS migration or social post was performed.

## Rechecagem pós-PR #91 — 2026-10-06 19:50 UTC

- [x] `main`, deploy de web/worker e staged changes reinspecionados; SHA `5d49fb5956096173e3094aa422f746f0782eb92e`, sem alterações staged.
- [x] Banco azul abaixo de 70% na janela: pico 3.3036/5 GB (66.1%), atual 3.2868/5 GB; amostra 61 pontos/1 h com um ciclo catalog SAPL.
- [x] Backfill de texto OFF e concurrency efetiva 1 observada; discovery SAPL ativo; limite de full scan reduzido para 4 páginas/ciclo, deploy de variável `d0f1361b-eda1-41b6-b7c3-9bfcd6036869` SUCCESS e log confirmou `full_pages=4`, 8 probes, zero erros.
- [x] Backup pós-cutover em S3 com SHA, readback, restore isolado, row counts e schema signature válidos.
- [x] 14.201/14.201 objetos S3 íntegros; nenhum payload relacional removido.
- [x] Smoke HTTP real das 17 rotas e APIs retornou 200; QA visual anterior cobriu os breakpoints documentados.
- [x] Serviços temporários `postgres-blue-restore` e `source-snapshot-migration` removidos após inspeção: sem volumes e sem uso recente; nenhum volume foi removido.
- [ ] Deploy versionado de `Dockerfile.backup` + wrapper e próxima execução diária do cron ainda não observados.
- [ ] Política de retenção/recuperação independente dos objetos de snapshot pendente.
- [ ] 30–60 min após novo limite, mais 24 h de observação e hidratação cold com resultado estruturado pendentes.
- [ ] Aprovação do proprietário para remover o Postgres antigo pendente; não executar exclusão.
- [ ] **GO público: não aprovado. Decisão atual: NO-GO** até gates pendentes acima.

## Fechamento pós-deploy f6084ab — 2026-10-06 20:25 UTC

- [x] Web/worker/backup deploys SUCCESS no SHA `f6084abcea82bebe0ade4699c1ce9460947cc571`; Railway sem staged changes.
- [x] Build do backup incluiu o shell wrapper e o Dockerfile; config cron `0 3 * * *`, start wrapper e restart NEVER.
- [ ] Próxima execução do cron às 03:00 UTC ainda precisa gravar objeto+manifest e passar leitura/restore; backup manual atual já passou.
- [x] Soak pós-deploy >30 min: disk azul permaneceu 3.2709 GB nos últimos pontos; amostra 1 h 3.2709–3.3036 GB, sempre <70%.
- [x] Worker após deploy: 8 probes incrementais, 4 páginas históricas, zero erros, BACKGROUND_BACKFILL_MODE=off, concurrency=1; descoberta adicionou normas.
- [x] Smoke proxy pós-deploy 19/19 HTTP 200; ready/worker heartbeat fresh.
- [ ] Observação por 24 h, limite diário persistente de ingestão, recuperação independente/retention dos objetos S3 e resultado estruturado da hidratação cold ainda pendentes.
- [ ] Aprovação expressa do proprietário para descartar Postgres antigo continua pendente; banco intacto em 4.9965/5 GB.
- **Decisão segue NO-GO para lançamento público.**

## Fechamento de lançamento — 2026-10-07 (substitui o estado pendente anterior quando há prova direta)

- [x] Reinspecionar serviços, deploy SHA, volume e staged changes; confirmar `web`, `worker` e backup em `postgres-blue`; nenhum segredo gravado no relatório.
- [x] Backup iniciado pelo cron 03:00 UTC observado em 07/10; objeto de 336.126.530 B, SHA-256 válido; manifesto 112.783 B/SHA válido; restore isolado 26,406 s, schema/Alembic/contagens conferidos; retenção removeu zero.
- [ ] Reexecutar backup após integrar a checagem do registro/hash do Art. 389 e `law_changes`; prova atual confirma counts/schema, não conteúdo jurídico específico restaurado.
- [x] Banco azul abaixo de 70% na amostra Railway de 24 h: atual 3,1950/5 GB, máximo 3,3343 GB (66,7%). Isso não é uma série física SQL 15/30/60 minutos pós-fix.
- [x] Encontrado consumidor dominante: `laws` ~2,338 GB (em query SQL de 07/10); snapshots relação ~107,7 MB. Backfill textual está OFF, mas SAPL/catalog escreve dados e checkpoints; full scan está limitado a quatro páginas/ciclo e probes incrementais continuam.
- [x] Script de migração S3 atual em main é retomável e testado; auditoria de produção documentada em 06/10 verificou 14.201/14.201 objetos únicos. Essa auditoria não foi refeita em 07/10.
- [x] Na auditoria anterior, `raw_body` permaneceu nas 14.202 rows com pointer; backup atual conta 14.203 snapshots e a row nova não foi recontada. Recuperação física por nulificação/rebuild = 0 B. Não remover: laws domina e D1 (dual-read, durabilidade/recovery independente) não foi provado.
- [x] Old Postgres/volume preservados: 4,9965/5 GB, PANIC por disco e banco em recovery. Manifests não provam serviço de origem nem cobrem `law_changes`; gate de dados exclusivos falhou. Não apagar.
- [x] QA Playwright real 40 rota/viewport combinations em 07/10; APIs e art.389 smoke passaram; caveat Normas.leg.br não oficial está visível no produto.
- [ ] Deploy do fix de retry interativo; job de hidratação Manaus `b5104e15-f6ec-41c7-a16b-f295dcf8bfad` atingiu fetch e encontrou timeout oficial, ficou em retry_wait; observar até resultado terminal com retry mantido.
- [ ] Deploy/revalidar ajuste visual `advogado. Produção de efeitos`; ajuste de apresentação local sem mudança de payload jurídico.
- [x] `BACKGROUND_BACKFILL_MODE=off`, worker concurrency 1; heartbeat recente; SAPL discovery segue ativo.
- [x] Estimativa Railway por média de 24 h: ~US$29,59/mês com antigo e ~$19,91/mês sem antigo, mais ~$0,04 buckets e egress; invoice não acessível. Sem antigo ainda ~$4,95 acima da meta US$15.
- [x] Release `v0.1.0`, MIT, README e demais documentos OSS estão públicos; cinco issues e dez Dependabot PRs mantidos abertos.
- [ ] GitHub About description/homepage/topics: ainda vazios; atualização exige sessão GitHub autenticada que não estava disponível nesta execução.
- [x] Textos LinkedIn/X atualizados sem métricas dinâmicas não comprovadas; capturas recentes com alt text e vídeo real de 20,52s preparados; nenhum post publicado.
- [ ] Depois de integrar, executar CI completo e revalidar o SHA exato de todos os deploys. Esperar 24 h para decisão de aposentadoria do banco antigo; remover somente se evidência de unicidade for resolvida.

**Decisão de lançamento nesta revisão: NO-GO**, até correção/produção dos itens de job/backup e acesso GitHub para About. O Postgres antigo não será excluído enquanto sua recuperação/dados exclusivos forem inconclusivos.

### Validação local do candidato (antes do PR)

- [x] `pytest -q`: 210 passed, 6 warnings upstream.
- [x] `npm run test:e2e`: 6 passed; executado no servidor local para regressões, além do Playwright real de produção já documentado.
- [x] `compileall` e `git diff --check`.
- [ ] CI do PR, deploy e produção ainda pendentes; testes locais não substituem esses gates.

## Fechamento coordenador — 2026-10-07 15:09 UTC

- [x] PR #94 integrou o candidato anterior no `main` `c6e74a3c47fa7b5edb4a596ecf10c59a27860370`; deploys web/worker online SUCCESS nesse SHA.
- [x] Backup runner do SHA `c6e74a3` teve execução iniciada pelo agendador com cadência temporária; objeto + manifesto lidos de volta, SHA-256 válido, restore isolado passou (`restore_verified=True`), nenhuma remoção por retenção.
- [x] Cron diário retornou para `0 3 * * *` UTC e deployment `be50e6a7-320f-4d02-8777-35383a16b17b` SUCCESS; execução do próximo horário diário normal continua pendente.
- [x] Regressão de produção da lei fria identificada: após timeout da fonte e job terminal failed, GET re-enfileirava durante cooldown de 6 h e mostrava falso “aguardando”. Correção local agora retorna erro honesto e evita repetição em GET; cobertura do cooldown expirado também testada.
- [x] Novos screenshots reais Diff/Blame desktop e texto Art. 389 mobile, pós-deploy c6, revisados e incluídos em `MEDIA.md` com alt text; nenhum post enviado.
- [x] Testes locais candidatos: pytest 212 passed/6 warnings; Playwright E2E 7 passed (inclui UI de timeout com API local roteada); compileall e diff check passaram.
- [ ] CI, PR, deploy e smoke browser de produção do novo fix ainda pendentes.
- [ ] Soak de 30–60 min após o próximo deploy final; 24 h ainda pendentes para qualquer descarte de rollback.
- [ ] Sobrepor a prova atual de cron com a próxima execução diária normal, agora com `0 3 * * *` restaurado.
- [ ] Atualizar About GitHub após recuperar sessão autenticada; não conseguimos gravar Description/homepage/topics.
- [ ] Definir retenção e restauração independente dos objetos S3 antes de qualquer remoção de `raw_body`.
- [x] Manter `raw_body` e o Postgres antigo intactos: reclaim físico de `raw_body` = 0 B; dados exclusivos do antigo continuam inconclusivos. Não excluir banco/volume.
- [x] Decisão atual **NO-GO** até ao menos o fix de hidratação em produção, soak, próximo cron diário e About serem verificados; preço estimado segue ~$29.99/mês com antigo e ~$20.18/mês sem antigo (+ egress), sem invoice real.

## Reinspeção final de integração — 2026-10-07 15:20 UTC

- [x] Railway services/volumes/buckets recontados: seis serviços live, três volumes de 5 GB, dois buckets e nenhuma mudança staged; web/worker/backup usam postgres-blue.
- [x] Sample pós-c6 em postgres-blue 61 pontos: 3.19500288–3.195150336 GB/5 GB (~63,9%); RAM média/pico 2.61/2.83 GB. Janela limitada sem ciclo horário de catálogo comprovado; não declarar soak representativo.
- [x] Nova job Manaus real falhou com timeout de SAPL sob código c6; GET da página ainda pode re-enfileirar dentro do cooldown. Fix local + regressão testados, mas não no Railway.
- [ ] PR/CI/deploy do fix não completados: GitHub API write respondeu erro interno; Git push sem sessão autenticada falhou, Browser GitHub deslogado e Mac bloqueado.
- [ ] GO permanece bloqueado; branch local contém o patch; serviço em produção ainda está no SHA c6.
