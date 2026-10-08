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

## Fechamento da missão de lançamento — 2026-10-07

### SHA e deploys atuais

GitHub `main` continua em `a17ad2c415d9f036096d07719c710d9be58f1a08` (CI run #113 passou). Railway: web `e161e005-7ead-456b-b92a-4a5f5829e994`, worker `5b543cd8-6589-44ee-808a-e0dc2427259a`, backup `bb483ded-08b5-4491-ba6e-8e288ed883f3` estão SUCCESS no SHA `a17ad2c`; postgres-blue `d7743494-246d-472c-bca2-13847dad4b49`; Redis `e0cc2708-a527-4918-aa06-3f994675234a`. Nenhuma mudança staged foi vista no fechamento desta captura.

### Backup observado pelo cron

Às 03:04:54.219Z o cron diário de 03:00 UTC iniciou e às 03:06:25.723Z concluiu como sucesso. Backup lido de volta do bucket: `postgres/leiaberta-production/20261007T030453Z-aa430f1a.dump`, 336.126.530 B, SHA-256 `d2d156c7992c0ebba720616363ded58b5b10a18cdd12d7b162c2317ca0d55485`. Manifest `.dump.json`, 112.783 B, SHA-256 `e2f8ca5bc1379880660b61fd0ed58fd9abb66eb022b32bccacda560325718dea`. Runner reportou `uploaded_object_verified=true`, `restore_verified=true`, `expired_objects_removed=0`, `retention_skipped=false`; restore isolado durou 26,406 s. Alembic `20261006_0011`, assinatura de schema e as contagens principais foram iguais entre origem e restore. Restore: laws 1.927.298; legal_nodes 211.497; snapshots 14.203; versions 14.136; history_events 4.049; hydration_jobs 30.668; job_outbox 30.654; source_registry 620.

**Limite da prova:** essa execução ainda não incluiu contagem/verificação de `law_changes`, `senate_proceedings` ou hash/ID do registro do Código Civil art. 389. Alteração local adiciona essas checagens ao runner e tem 9 testes focados passando, mas precisa CI/deploy e nova execução do backup para ser prova. O restore de hoje não pode ser descrito como confirmação específica do artigo.

### Inventário e snapshot

Railway metrics API consultada em 07/10: janela móvel de 24 h, 289 amostras. Blue atual 3,1950 GB, média 3,2580, máximo 3,3343 GB/5 GB; 63,9% atual e 66,7% máximo. Serviço permanece abaixo de 70%, mas não há uma nova série de 15/30/60 min de SQL de bytes depois do patch candidato.

Último tamanho de banco SQL disponível nesta rodada: 2.830.522.047 B; `laws` 2.338.455.552 B; `legal_nodes` 331.358.208 B; `source_snapshots` 107.683.840 B. Snapshot brutos eram 252.701.649 B distintos; tabela `laws` é aproximadamente 21,7× a relação de snapshots. Não nulificar raw bodies: physical reclaim comprovado = 0 B. A auditoria de 14.201 objetos únicos com SHA verificado ocorreu em 06/10; backup de 07/10 contém 14.203 rows de snapshot, então pointer/object coverage da nova row não foi recontada.

O banco velho permanece ligado ao volume `postgres-volume`, 4,996513792/5 GB. Log registra PANIC por `No space left on device`; tentativa read-only recebeu “database system is in recovery mode”. Manifests não identificam host/serviço de origem, não contêm hash por registro e omitem `law_changes`. Não há evidência segura de ausência de dados únicos. O serviço/volume não foi excluído; sua autorização era condicional e condição C não passou.

### Produto, sync e hidratação

Smoke coordenado real passou 16+ rotas e APIs, todas HTTP 200; `/ready`, `/worker-health`, `/api/stats`, `/api/sources`, busca LGPD/LGDP, página art.389, Why/Blame, History, Diff e provenance. A API descreve art.389 e history como parcial. E cobriu 10 rotas em 390/430/768/1440 px via Playwright (40 combinações), sem overflow, console errors, falha de request ou 5xx; capturas reais 07/10 estão em `docs/final-ops/evidence`. Caveat da transcrição Normas.leg.br está na tela; não há verificação dos trechos primários anterior/posterior armazenados.

Worker mantém backfill OFF e concurrency 1; quatro páginas SAPL full por ciclo e probes incrementais continuam. Job frio real Manaus `b5104e15-f6ec-41c7-a16b-f295dcf8bfad` chegou ao fetch e sofreu timeout da fonte externa. Ele ficou em `retry_wait`, tentativa 1. A inspeção do código revelou que o retry interativo podia ser bloqueado como ambíguo; fix local usa marcador de work class e mantém o backoff. Depois de deploy, reclassificar job, deixá-lo terminar e reportar `succeeded`/`failed` com o estado honesto da fonte.

### Custos medidos e estimados

Tarifas atuais consultadas na página pública de [preços Railway](https://railway.com/pricing): CPU US$20/vCPU-mês, RAM US$10/GB-mês, volumes US$0,15/GB-mês, egress US$0,05/GB e Object Storage US$0,015/GB-mês. Estimativa calculada pelas médias de CPU/RAM da janela Railway de 24 h, storage dos volumes de 5 GB; buckets aproximados 2,3 GB backups + 0,065 GB snapshots. Egress é excluído porque a interface retornou métricas agregadas sem total diário confiável. A fatura real não foi disponibilizada pelas ferramentas.

| Serviço | CPU média / pico (vCPU) | RAM média / pico (GB) | Disco atual | Uso estimado/mês |
|---|---:|---:|---:|---:|
| web | 0,0021 / 0,0332 | 0,1136 / 0,2872 | — | US$1,18 |
| worker | 0,0053 / 0,1328 | 0,1498 / 0,2951 | — | US$1,60 |
| postgres-blue | 0,0055 / 0,1203 | 1,2301 / 2,9441 | 3,195 GB / 5 GB | US$13,16 |
| Postgres antigo | 0,3048 / 0,4451 | 0,2836 / 0,3930 | 4,9965 GB / 5 GB | US$9,68 |
| Redis | 0,0026 / 0,0040 | 0,0136 / 0,0165 | 0,1527 GB / 5 GB | US$0,94 |
| postgres-backup | 0,0062 / 0,7782 | 0,2902 / 2,5339 | — | US$3,03* |
| Buckets | — | — | ~2,365 GB | ~US$0,04 |
| **Total observado pela média 24 h** |  |  |  | **~US$29,63 + egress** |
| **Sem Postgres antigo** |  |  |  | **~US$19,95 + egress** |

* O valor de backup usa a média do serviço durante essa janela. O job do backup é diário e a telemetria agregada não permite decompor exatamente compute ocioso versus a execução; não multiplicar o pico de 03:00 pelo mês. Para cobrança efetiva, usar invoice/usage do workspace, que não estava acessível.

O cenário sem o antigo ainda supera a meta de US$15 em aproximadamente US$4,95, antes de egress. Picos medidos no período foram blue 0,120 vCPU/2,944 GB, worker 0,133/0,295 GB, backup 0,778/2,534 GB; não há duração representativa suficiente para monetizar uma operação pesada como regime mensal. Próximas duas otimizações de maior impacto: (1) resolver com segurança o Postgres antigo, que representa ~US$9,68/mês; (2) reduzir o componente de RAM do postgres-blue (~US$12,30/mês na média) por avaliação de configuração/uso após soak, sem sacrificar margem de capacidade. Snapshot export não é otimização material aqui.

### GitHub e materiais de publicação

MIT público, README/CONTRIBUTING/CODE_OF_CONDUCT/SECURITY e templates presentes; release pública `v0.1.0` existe e mantém os caveats, mas seu tag é anterior à aplicação atual. CI #113 em `a17ad2c` passou. Cinco issues de colaboração e dez Dependabot PRs seguem abertos, sem merge em massa. About está vazio e não pôde ser atualizado: sessão GitHub deslogada, token `gh` local inválido e connector sem escrita de settings. Capturas com texto alternativo e `demo.webm` de 20,52 s estão documentados em `docs/launch/MEDIA.md`.

### Decisão

**NO-GO para anúncio público neste fechamento.** Necessários: publicar o fix de retry e fechar o job cold com resposta terminal honesta; integrar o check legal específico no runner, fazer nova execução/restore; salvar About GitHub com autenticação e revalidar deploy/código. O antigo Postgres permanece preservado por risco de dados exclusivos. Não houve exclusão de evidência, upgrade, contratação, compra de domínio ou publicação social.

## Atualização pós-PR #94 — 2026-10-07 15:09 UTC

- `main`: `c6e74a3c47fa7b5edb4a596ecf10c59a27860370`. Web `6359b280-fbc0-4df7-99a6-23387fd584fd` e worker `d5fbec36-3bce-4c85-ad4b-e73abfbdd846` SUCCESS nesse SHA. O runner do backup foi implantado nesse SHA; cron diário restaurado para `0 3 * * *` após execução programada de verificação temporária.
- Execução programada pelo scheduler 14:55:40–14:57:10Z: dump `postgres/leiaberta-production/20261007T145539Z-a4fa5070.dump`, 336.118.221 B, SHA-256 `cc5393d07e852fa6927ec29b16afdb3e33acfb5bea8ee225c598175eb62eebd4`, manifest bytes SHA-256 `c5f3e98a79cab9c402a1dc1dccabe92fd4077b8cb480881edbc0561b48936ae8`; log `uploaded_object_verified=true`, `restore_verified=True`, retenção removeu zero. A próxima execução diária na cadência normal fica pendente; a execução de teste não é descrita como execução diária.
- Smoke HTTP de rotas públicas/API e QA real de navegação do Art. 389 no SHA c6 passaram antes desta correção: as rotas testadas responderam 200 e Why/Blame/Diff preservam a ressalva não oficial do Normas.leg.br. Screenshots atuais em [`MEDIA.md`](../launch/MEDIA.md), gerados do site real após c6.
- Hidratação fria real de Manaus concluiu `failed` após cinco timeouts do SAPL. O resultado honesto não indica ausência da lei. Foi encontrado um bug adicional: o GET do detalhe enfileirava novamente durante o cooldown e escondia a falha. Patch local retorna o job terminal, evita repetir GET e expõe a falha/ausência do texto e fonte; testes locais passam, mas CI/deploy/QA visual desse patch ainda estão pendentes.
- A janela Railway de 24 h consultada por volta de 15:00Z estima ~$29,99/mês incluindo o antigo Postgres e ~$20,18/mês sem ele, mais egress; bucket ~$0,04/mês está incluído no primeiro total. Não é valor de fatura. Azul 3,195 GB atual e máximo 3,334 GB/5 GB. `laws` ~2,338 GB; `source_snapshots` ~107,7 MB; `raw_body` permanece e não houve reclaim físico.
- O serviço Postgres antigo e `postgres-volume` continuam preservados: falta prova de ausência de dados jurídicos exclusivos, ainda que aplicações e backup apontem para blue. Serviços temporários `postgres-blue-restore` e `source-snapshot-migration` já foram removidos, sem volume montado. Metadados About não puderam ser salvos sem autenticação GitHub; cinco issues/10 PRs de dependências seguem abertas para revisão individual.

**Decisão nesta atualização: NO-GO.** Faltam PR/CI/deploy e smoke real do bug de hidratação recém-identificado, janela de soak após o código final, próxima execução diária normal, About autenticado e política recuperável independente para os objetos de snapshots. Banco antigo não é removido enquanto os dados exclusivos forem inconclusivos. Nenhum post foi publicado. Ver [WORKLOG](../final-ops/WORKLOG.md) para SHAs, medidas e logs integrais.

## Reinspeção final — 2026-10-07 15:20 UTC

- Railway environment foi listado novamente: seis serviços, três volumes e dois buckets; `staged=null`. Web, worker e backup seguem apontados para postgres-blue. Service ID atualizado de blue: `25805d38-02bf-4180-adf3-0f30c82849de`; volume `c7f9b69c-59b4-46d6-b89a-33b1df10cbfc` (5 GB). Cron live `0 3 * * *`; runner em `be50e6a7-320f-4d02-8777-35383a16b17b` SUCCESS.
- Janela 1 h/61 pontos: disco blue 3.19500288–3.195150336 GB (63,9% do volume); RAM 2.610 GB média/2.828 GB pico; CPU 0.00805/0.28172 vCPU média/pico. Worker 0.00258/0.04672 vCPU e .16865/.32335 GB RAM; web .00400/.12998 e .13558/.24730 GB; Redis .00258/.00385 e .01359/.01629 GB, disk .15269–.15390. Métricas Railway incluem zeros/sleep em outros serviços; backup desta janela teve .01685 vCPU/1.050 GB RAM média e peak .707/3.041 durante o job pontual. Nada disso altera a estimativa mensal de 24h anterior; não é invoice.
- A produção c6 falhou novamente ao hidratar `manaus-sapl-2198`: job `88b0db12-168c-455c-b071-186367d4022c`, timeout em SAPL às 15:12Z. GET detalhamento em cooldown ainda dispara retry e pode mascarar falha. Patch local resolve com `failed` terminal, sem GET requeue, texto honesto, checksum “Não obtido” e retry manual. Coberto por Python 212/212 e Playwright local 7/7; sem CI ou deploy.
- Último smoke HTTP pós-c6: 18/18 rotas/APIs verificadas retornaram 200, incluindo `/health`, `/ready`, `/worker-health`, stats/sources/search `LGDP`, art.389, history/blame/provenance, diff, fontes/cobertura/sobre, OpenAPI e sitemap. `/api/sources` respondeu com ~2,75 MB. O teste evitou outra leitura da página Manaus porque o código antigo ainda pode enfileirar retry em GET.
- Integração não foi possível pelos meios disponíveis: create_blob/update_file no conector GitHub retornaram erro interno; `git push` HTTPS não encontrou credencial e SSH não aceitou public key. O browser GitHub mostrou “Sign in” e a UI informou Mac bloqueado. Existe branch remota scaffold no SHA c6, mas sem o patch; nenhum PR #95 nem CI foi gerado. A versão local está no worktree de lançamento e precisa ser integrada com uma sessão autenticada antes de deploy seguro.
- Semântica de dados e backups não mudou: não se apagou Postgres antigo ou jurídico; migração bucket-only não passou gates; reclaim físico `raw_body=0 B`. O teste programado do runner novo e hashes/restore estão registrados acima; execução diária normal do próximo slot ainda pendente.

**Decisão atualizada: NO-GO.** Patch crítico e capturas não estão em `main`/Railway; além disso, faltam browser QA na production do patch, soak 30–60 min com ciclo limitado representativo, cron diário normal, metadados About, recuperação independente do bucket de snapshots e prova de que Postgres antigo não possui dados únicos. Nenhum social post saiu.


## Revalidação final após o merge — 2026-10-07 18:06 UTC

### Produção e código

`main`, web, worker e postgres-backup: `73a2216b47d1e077777902f45197c8f2b5feccb8`. Deployments web `32894798-94b9-4f25-b877-aa4634fed14b`, worker `5cac5b89-ae2e-4bd0-85f7-05724137b14d`, backup `6e4e0061-e1db-41fd-ac84-f8d52b8a523d`: `SUCCESS`. PR #95 foi testado no head `f377f0d…`; a tree é idêntica à do commit de merge. Actions #116: Python, E2E e imagem concluídos com sucesso.

Teste local válido em Python do projeto: pytest 212 passed; Playwright 7 passed; compileall e `git diff --check` passaram. O navegador gráfico conectado à produção percorreu home, busca LGPD/LGDP, Código Civil/art. 389, histórico, comparação, Blame/Why, fonte externa, cópia/abertura do deep link, /fontes, /cobertura, /sobre, busca sem resultado e lei fria. Inspeções visuais com viewport configurado em 390, 430, 768 e 1440 px; nenhum defeito visual bloqueador ou erro de console foi observado. O caveat Normas.leg.br continua explícito.

22 rotas/API smoke pós-deploy: todas HTTP 200. Soak de 3 min: 36 leituras de saúde, catálogo e leis, nenhuma resposta não-200/5xx; métricas Railway registraram 0/146 respostas 5xx em uma hora e um 499 de cliente cancelado. Heartbeat do worker foi observado até 18:01:33Z; concurrency 1, `BACKGROUND_BACKFILL_MODE=off`, SAPL 4 páginas completas por ciclo e orçamento 300 s; queue pending 0. RAM do worker ~80 MB média/~82.5 MB pico na última hora. Blue: 3.178 GB/5 GB (~63.6%), máximo da hora 3.195 GB (~63.9%).

### Hidratação e backup

A norma fria real `manaus-sapl-2198` falhou após timeout do SAPL, sem texto estruturado. A tela diz isso explicitamente e oferece retry manual. Três reloads visuais permaneceram no estado terminal; duas leituras retornaram o mesmo job `88b0db12-168c-455c-b071-186367d4022c`, `failed`; nenhuma tentativa foi criada por GET.

O cron diário `0 3 * * *` registrou backup às 03:04:54Z. Dump em `leiaberta-backups`: `postgres/leiaberta-production/20261007T030453Z-aa430f1a.dump`, 336,126,530 bytes, SHA-256 `d2d156c7992c0ebba720616363ded58b5b10a18cdd12d7b162c2317ca0d55485`, SHA-256 do manifesto `e2f8ca5bc1379880660b61fd0ed58fd9abb66eb022b32bccacda560325718dea`; `uploaded_object_verified=true`, `restore_verified=True`. O runner atualizado executou também às 14:55Z com objeto e restore verificados.

### GitHub e decisão

Repo público: README renderizado, MIT, CONTRIBUTING e release v0.1.0 acessíveis; 5 issues legítimas e 10 PRs Dependabot preservados. Screenshots em `docs/launch/assets` abrem pelo GitHub e demonstram Diff desktop, Blame desktop e art. 389 mobile; screenshot home e vídeo WebM também estão no pacote. Nenhum post foi publicado.

O About foi conferido visualmente e ainda diz “No description, website, or topics provided”. A sessão conectada mostra Sign in e token `gh` inválido; não foi possível salvar os três valores sem autenticação humana. O antigo `Postgres` (4.9965/5 GB) permanece: serviços web/worker/backup apontam ao blue e não há TCP proxy, mas dados jurídicos exclusivos não puderam ser descartados com segurança. Isso e o custo acima da meta não são bloqueios de produto.

Estimativas documentadas por consumo/tarifa, sem invoice real: ~US$29.99/mês com banco antigo e ~US$20.18/mês após uma aposentadoria futura segura, ambos + egress. Não houve compra/upgrade.

**Status de lançamento:** tecnicamente aprovado; **NO-GO estrito até salvar e confirmar visualmente Description, Website e Topics no GitHub**. Após isso, não resta pendência técnica de apresentação identificada nesta revisão.
