# LeiAberta — relatório final da execução autônoma

Data: 2026-10-05. Projeto: `DIDIDXX/LeiAberta`. URL: https://web-production-12e95.up.railway.app.

## Código e produção

- SHA do código validado: `06646081480668017d288ad89e98545eead82a0c` (PRs #62–#68 integrados; PR #68 inclui heartbeat do worker).
- Deploys SUCCESS desse SHA: web `e29b4142-1f73-49f4-9c70-915635b1c03c`; worker `06b79a18-ccc6-486b-841c-311cfba2155e`; backup `8dab8856-0731-4edf-afb5-967e752a98ad`. Redis `e0cc2708-a527-4918-aa06-3f994675234a` e Postgres `78c139ee-fc38-4883-be04-99d72052c7d0` também SUCCESS. Uma réplica por serviço; sem migration nesta rodada.
- O `main` e a produção agora estão no SHA `bc9456567a76eb2836f55c4e48965a1861729680` (PR #69, atualização documental); deploys atuais também SUCCESS: web `6647d401-5f3f-4c99-b4a6-a5ed73625c5f`, worker `40a598c1-cf58-4626-88ce-3775bd4d3ab8`, backup `dc1bc8f5-9f90-4231-96ce-a54f980ca860`.
- Web, Postgres, Redis e backup em `asia-southeast1-eqsg3a`; worker em `us-east4-eqdc4a`. Volumes de 5 GB para Postgres e Redis; backup agendado diariamente.
- `/health`, `/ready`, `/worker-health`, typo search `LGDP`, histórico e sitemap deram 200. Amostras: health 0,311s; ready 0,297s; worker-health 0,261s; busca 0,287s; histórico 0,299s; sitemap 0,371s; `/api/stats` 0,824s. Não são p95.
- Revalidação direta às 17:51 UTC, depois do deploy `bc945`: health, ready, worker-health, LGDP search, history e sitemap deram 200 em 0,277–0,322s. A integração Railway mostra duas falhas antigas de web/worker às 16:16 UTC, ambas sucedidas por deploys SUCCESS às 17:49 UTC; não há falha ou alerta ativo.
- Playwright em produção: 390px e 1440px; LGDP encontrou a LGPD e Art. 7 abriu; overflow 0 px; nenhum erro JS, CSP ou de rede. CSP autoriza scripts/API same-origin e apenas os hosts Google Fonts já usados.
- Busca/histórico em produção: Lei Maria da Penha segue parcial e honesta — 65 itens, 62 relações sem texto pareado, nenhum job ativo e nenhum diff inventado.
- Catálogo no endpoint de estatísticas: 1.167.592 registros enumerados e 23.013 materializados. Isso não representa todas as leis brasileiras.

## Mudanças integradas e verificadas

- Estatísticas agrupadas, typo suggestions limitadas a catálogo hot e sitemap index/shards.
- Canonical/metadata legais e conteúdo limitado sem JavaScript; artigo longo agora quebra no mobile.
- Headers de segurança + CSP; Docker non-root; licença MIT, CI, Dependabot, guias OSS, templates e runbook backup/restore.
- `/ready` confere DB e Alembic heads; Planalto só usa HTTPS em `*.planalto.gov.br`, bloqueia redirects externos/downgrade, limita resposta a 25 MB e tem retries transitórios limitados.
- Rate budgets globais via Redis: busca 600/min, detalhe/nodes 240/min, preparação de jobs 60/min. Acima do limite, 429/Retry-After. Não confiam em IP encaminhado não verificado; se Redis cair, o middleware abre e dedupe/backpressure de jobs continuam.
- Worker grava heartbeat no Redis a cada 30s com TTL de 90s; `/worker-health` retorna 200 fresco/503 ausente ou stale.
- Testes locais: `pytest -q` 146 passed, um aviso upstream Starlette/httpx; `git diff --check` passou. CI dos PRs #66–#68 passou Python, E2E e imagem Docker. E2E CI prova fluxo de busca, artigo, histórico/diff, hidratação e desambiguação.

## Limitações externas ou sem prova disponível nesta sessão

1. **Cobertura “todas as leis”:** não há um inventário nacional completo que forneça denominator verificável; há fontes federais e integrações estaduais/municipais selecionadas. Completar exige descobrir, enumerar e validar cada catálogo oficial, sem inferir cobertura a partir do tamanho do banco.
2. **SQL/billing Railway:** os conectores não expõem SQL read-only/EXPLAIN nem invoice detalhada. Não foi possível medir tamanho por tabela/índice, conexões, bloat, fila/idade ou custo faturado. Baseline anterior mediu o volume Postgres em ~3,053/5 GB; custos continuam estimados.
3. **Limiter por usuário:** budgets globais estão ativos. Limite justo por cliente depende de provar qual IP Railway encaminha ao app; usar X-Forwarded-For sem confiança permitiria spoofing. Não se usa esse header.
4. **Política comum de todas as fontes:** Planalto está restrito; adapters diferentes ainda precisam limites/redirect allowlists próprios e fixtures, especialmente Senado. Não alteramos fontes oficiais nem criamos carga em massa.
5. **Exclusão Railway pendente de 2FA:** `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276` está com delete staged, sem volume e fora do caminho do produto. A API recusou aceitar o patch sem autenticação 2FA do Dashboard.

O restante acima é ausência de corpus/dados/permissão de conta ou falta de identidade confiável da borda; a experiência de leitura, busca, histórico parcial, segurança básica, fila protegida, CI e Railway operacional foram validados.
