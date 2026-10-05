# LeiAberta Luna 6 — worklog

## Execução atual

- Data/hora da baseline: 2026-10-05 12:36 America/Sao_Paulo (15:36 UTC); atualizado 16:05 UTC
- Branch: `codex/luna6-autonomous-audit-20261005`
- SHA inicial: `94807cd7b0673384f6d3428e7c7fc16722d634e6`
- Repositório: `DIDIDXX/LeiAberta`
- Prompt solicitado: `LeiAberta_LUNA6_AUTONOMOUS_MASTER_PROMPT.md`, SHA-256 `2917f9d2e2124d4e75e7656a13ee57296b81e58ad19330db540d086a8bd84e36`
- Railway: projeto `ac5c9188-a792-4d4a-99d6-512740aec73e`, ambiente production `b415a556-41ec-4f33-994f-1f5d38b633a1`; IDs de deploy abaixo são retrato anterior e serão revalidados.
- Fase atual: 8 — branch/review/deploy pendentes; auditoria e correções locais concluídas.

## Estado inicial observado

- O checkout local estava no commit `9744fb9`, com alterações locais que correspondiam a commits já mesclados em `main`; a branch atual foi criada limpa a partir de `origin/main` em `94807cd`. O estado anterior está preservado em stash local reversível.
- Retrato operacional anterior (05/10, 09:24 UTC): web `7465fadf-1cab-4c07-81a3-d4d4cf96da73`, worker `4a9523b7-d3ec-4c89-8d8e-ddfdae888b00`, backup `ad0ca4a3-914e-46d7-bfcb-3696585239d1`, Redis e Postgres em `SUCCESS`; health e endpoints de histórico/tramitação responderam 200. Cron de backup `0 3 * * *`.
- Evidência anterior: dump pós-migration em object storage com `restore_verified=True`; worker configurado com `HYDRATION_CONCURRENCY=24`. Essas informações ainda não substituem a nova baseline.
- Dados anteriores (09:15 UTC): 833.109 registros indexados, 14.254 textos materializados, 51.938 dispositivos estruturados, 376 alterações; 216.717 pendentes no Senado e 601.723 na soma de catálogos subnacionais (com sobreposição possível).
- Situação anterior do histórico da Lei Maria da Penha: HTTP 200, `partial`, 65 relações, 62 sem par de textos, nenhum job ativo. Dossiê da Lei 14.550/2023: `complete`.

## Medições desta execução

- Baseline consultada às 15:36 UTC via Railway metrics e smoke público entre 15:45–16:05 UTC; detalhes em `production-baseline.md`.
- Web, worker, PostgreSQL, Redis e backup estavam em `SUCCESS`; Postgres 3.053/5 GB, worker pico 5.182 GB/8 GB. Web/DB/Redis em Singapura; worker US East.
- Smoke público: health 200/0.36s, LGDP search 200/4.14s, lei 200/0.35s, nodes 200/0.26s, history 200/0.30s, proceedings 200/0.36s, sitemap 200/7.09s; `/api/stats` excedeu timeouts de 20s e 65s.
- Causas encontradas: `/api/stats` repetia contagens por fonte SAPL; fuzzy fallback varria o catálogo inteiro; sitemap criava um documento gigante. Correções locais em `app/main.py` e `app/search.py`, sem migration.
- Página da lei recebe canonical/OG e resumo seguro sem JS; headers básicos e runtime Docker UID 10001 foram adicionados.
- Suíte final: `pytest -q` 131 passed, 1 aviso Starlette/httpx; Playwright 5/5 em 32.0s incluindo viewport 390px; Docker build + container health passaram como UID 10001.
- Custos por rate público: compute proxy ~$28.08/mês; volume/bucket estimados no total ~$0.5–$1.54. Billing UI não disponível.
- Tamanho das tabelas/índices, conexões, queue age/depth e invoice não puderam ser lidos pelos conectores habilitados.

## Decisões

1. Manter PostgreSQL, Redis e worker até comparação medida de custo, durabilidade e desempenho.
2. Não alegar cobertura jurídica completa a partir de contagem de catálogo.
3. Não migrar região, trocar fila ou executar migration destrutiva sem baseline, backup verificável e rollback.
4. Não coletar de `leis.org` sem autorização/licença; usar apenas como benchmark público.
5. Ocultar variáveis secretas e dados pessoais em logs e relatórios.

## Arquivos alterados

- Bootstrap e auditoria: `docs/audits/WORKLOG.md`, `docs/audits/CHECKLIST.md`, relatórios em `docs/audits/`, `docs/runbooks/backup-restore.md`, `docs/reports/post-audit-status.md`.
- Código: agregação stats/sitemap/SEO/headers em `app/main.py`, fuzzy bound em `app/search.py`, runtime non-root/CA opcional em `Dockerfile`, config Alembic, testes API e fluxo E2E mobile.
- OSS/CI: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, workflows, Dependabot e templates GitHub.

## Testes executados

- `pytest -q`: 131 passed, 1 aviso Starlette/httpx, 1.70s.
- Playwright: 5/5 passaram em 32.0s incluindo mobile.
- `docker build` passou com CA de proxy montada somente no passo de `pip`; imagem respondeu `/health` 200 como UID 10001.
- `git diff --check` será executado antes do commit.

## Deploy realizado nesta execução

- CI inicial: Python e Docker passaram; E2E revelou que Playwright usava caminho `.venv/bin` indisponível no runner GitHub. `playwright.config.js` foi ajustado para usar `.venv/bin/python` local quando existe e `python` do runner fora do ambiente; E2E local passou novamente, 5/5 em 30.0s. CI rerun #2 está em andamento.
- PR #47 aberto; head atual `d58783078ae3db7abe9fcbf491b8b48c650905be`, aguardando checks finais.
- Nenhum deploy de código nesta execução; branch isolada aguarda CI verde, merge e deploy.
- Um Railway Function `pg-diagnostic` surgiu na ferramenta durante leitura de DB; exclusão ficou como staged delete, sem volume. Railway exige 2FA do Dashboard para confirmar; API recusou a confirmação. Não houve alteração em Postgres/Redis.

## Problemas restantes

- Produção pós-deploy, PR, merge e novos p95 ainda pendentes.
- Cobertura legal nacional e materialização completa continuam incompletas: não existe denominador nacional único disponível e acervos locais ainda precisam ser enumerados/validados.
- Railway exige 2FA no Dashboard para efetivar o staged delete do serviço diagnóstico; API/MCP explicitamente recusou.
- SQL read-only e Billing/Usage real não são expostos pelos conectores nesta sessão.

## Próxima ação exata

Validar CI rerun, merge PR #47, acompanhar Railway SUCCESS e smoke pós-deploy.


## Retomada e validação final (2026-10-05 UTC)

- PR #62 foi integrado como `81982a28d36836563acf83b7115af355b31ea830`; CI (python, e2e, image) verde. Railway web/worker/backup em SUCCESS (`679ff153-080e-4ee1-9e88-27b2a52c7a77`, `034f637d-1546-461e-9d36-a69861d7582c`, `6c2e5d02-39cb-4b38-a08f-56acab1cd3bc`).
- Browser smoke de produção: 390px e 1440px; scrollWidth igual à viewport; LGDP resolveu LGPD, Art. 7 visível; nenhum erro de console, pageerror ou request.
- Produção: `/health` 0.395s, typo search 0.390s, HTML lei 0.396s, nodes 0.409s, history 0.416s, sitemap index 0.485s, `/api/stats` 0.896s. `art 7 LGPD` retornou 200/2.705s em teste concorrente. Amostras, não p95.
- História Maria da Penha: 65 relações oficiais, 62 sem redação pareada; status parcial permanece e não há diffs inferidos.
- Hardening local adicional: CSP same-origin, `/ready` (conectividade DB + Alembic heads), cap de 25 MB no fetcher Planalto. `pytest -q`: 138 passed, 1 aviso upstream; Playwright: 5/5 passed; `git diff --check` passou. Estes itens ainda aguardam PR/CI/merge/deploy.
- Pendências/bloqueios: inventário nacional exaustivo sem denominator oficial; SQL/EXPLAIN/fatura indisponíveis via connector; cliente confiável de proxy ainda não verificado para rate limit; validação uniforme de redirects/adapters; readiness + worker heartbeat precisam confirmação após deploy; exclusão staged do diagnóstico Railway requer 2FA no Dashboard.
- Próxima ação exata: criar branch e PR do hardening; CI verde; merge/deploy; confirmar `/ready` e CSP via HTTP; reexecutar browser/smoke; atualizar status com SHA e deployment IDs definitivos.

- Smoke CSP em produção encontrou bloqueio da folha já existente do Google Fonts; patch restrito a `fonts.googleapis.com` e `fonts.gstatic.com` preparado, após validar necessidade pelo console do browser. Precisa CI/merge/redeploy e smoke limpo.


## Fechamento publicado (2026-10-05 UTC)

- HEAD `b2054b00aa934a1eea94f5cd5428dbac2e97fcb9`; PR #64. Deploys finais SUCCESS: web `ae4ba59d-eaed-4791-813e-b2308a70faab`, worker `15ec5d66-6b66-4a9c-8156-cfa4a420b992`, backup `0380388b-ad6f-4b0e-b189-88a68b414396`; Redis/Postgres SUCCESS.
- Browser após CSP final: mobile 390 e desktop 1440, página Art. 7 cabe sem overflow, busca LGDP funciona e console/network limpos. Hosts Google Fonts já existentes permitidos de forma explícita e restrita.
- Readiness `/ready` 200; saúde e smoke endpoints passaram. Últimas amostras: health .343s, ready .424s, search typo .356s, lei .382s, nodes .353s, history .329s, sitemap .442s, stats .826s. Não são p95.
- Catálogo: 1.162.975 registros, 22.293 materializadas no endpoint de estatísticas. History Maria da Penha mantém 65 itens, 62 sem texto correlato, estado partial.
- Testes local/remoto: Python 138 passou com 1 deprecation warning; Playwright 5/5; CI dos PR #62/#63/#64 (python/e2e/image) verde.
- Post-audit status atualizado com limitações: corpus nacional sem denominator, SQL/billing ausentes no connector, confiança do IP de proxy sem verificação, limites/redirects heterogêneos de adapters, heartbeat de worker e exclusão Railway exigindo 2FA.
- Próxima ação técnica recomendada: obter via ambiente autenticado consulta SQL read-only + billing, verificar forwarded IP no app/proxy Railway e implementar limiter apropriado; expandir fontes oficiais em catálogo por jurisdição. Única ação de conta imediata: aceitar remoção staged do diagnóstico com 2FA no Dashboard.

- Revisão final do fetcher: URLs Planalto agora forçam HTTPS, domínio `*.planalto.gov.br`, porta 443 e validação prévia de cada redirect; limite 25 MB permanece. Retry limitado (3 tentativas) apenas para HTTP 429/5xx e falhas de transporte, sempre na mesma URL HTTPS. 142 Python tests passaram. E2E local teve 2 falhas por Planalto responder 503 após repetidas hidratações; não houve novo retry do teste local, para não pressionar a fonte. PR #66 precisa CI E2E (runner externo) antes do merge.

## Rate limiting global (2026-10-05 UTC)

- Adicionados budgets Redis globais sem confiar em forwarded IP: busca 600/min, detalhe/nodes 240/min, preparação explícita 60/min; 429 traz `Retry-After` e `Cache-Control: no-store`.
- Redis já faz parte da arquitetura; não adicionei dependência/serviço. Se o rate-store estiver indisponível, middleware falha aberto e jobs ainda têm dedupe/backpressure. Limiter por cliente depende de comprovar a identidade encaminhada pelo proxy.
- `pytest -q`: 144 passed, uma advertência upstream; `git diff --check` passou. E2E e imagem Docker precisam CI após PR.


## Worker heartbeat (2026-10-05 UTC)

- Worker publica `leiaberta:worker:heartbeat` no Redis a cada 30s com TTL 90s; log contém timestamp, concurrency e consumer id (sem dados jurídicos/secrets). Endpoint `/worker-health` confirma heartbeat fresco e retorna 503 se ausente/obsoleto. `/ready` segue limitado a DB/schema para não acoplar leitura web à disponibilidade do worker.
- `pytest -q`: 146 passed, um warning upstream; `git diff --check` passou. E2E/Docker aguardam CI.
