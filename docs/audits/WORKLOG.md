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

- Nenhum deploy de código nesta execução; branch isolada aguarda commit, PR e checks.
- Um Railway Function `pg-diagnostic` surgiu na ferramenta durante leitura de DB; exclusão ficou como staged delete, sem volume. Railway exige 2FA do Dashboard para confirmar; API recusou a confirmação. Não houve alteração em Postgres/Redis.

## Problemas restantes

- Produção pós-deploy, PR, merge e novos p95 ainda pendentes.
- Cobertura legal nacional e materialização completa continuam incompletas: não existe denominador nacional único disponível e acervos locais ainda precisam ser enumerados/validados.
- Railway exige 2FA no Dashboard para efetivar o staged delete do serviço diagnóstico; API/MCP explicitamente recusou.
- SQL read-only e Billing/Usage real não são expostos pelos conectores nesta sessão.

## Próxima ação exata

Validar `git diff --check`, publicar branch/PR via GitHub; aguardar CI, merge, Railway SUCCESS e smoke pós-deploy.
