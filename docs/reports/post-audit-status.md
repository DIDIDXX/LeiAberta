# LeiAberta — relatório final da execução autônoma

Data: 2026-10-05. Repositório: `DIDIDXX/LeiAberta`. URL: https://web-production-12e95.up.railway.app.

## Estado implantado

- SHA principal: `b2054b00aa934a1eea94f5cd5428dbac2e97fcb9` (PR #64). CI verde nos checks Python, E2E e imagem Docker; PRs #62–#64 integrados.
- Railway SUCCESS: web `ae4ba59d-eaed-4791-813e-b2308a70faab`, worker `15ec5d66-6b66-4a9c-8156-cfa4a420b992`, backup `0380388b-ad6f-4b0e-b189-88a68b414396`, Redis `e0cc2708-a527-4918-aa06-3f994675234a` e Postgres `78c139ee-fc38-4883-be04-99d72052c7d0`. Réplicas: uma por serviço. Web, DB, Redis e backup em Singapura; worker em US East. Volumes provisionados de 5 GB para Postgres e Redis.
- `/health` 200/0,343s; `/ready` 200/0,424s (conexão DB e Alembic heads atuais); typo search `LGDP` 200/0,356s; busca `art 7 LGPD` 200/2,263s; lei HTML 200/0,382s; nodes Art. 7 200/0,353s; histórico Maria da Penha 200/0,329s; sitemap 200/0,442s; `/api/stats` 200/0,826s. São amostras, não p95/benchmark controlado.
- Catálogo reportou 1.162.975 registros e 22.293 leis materializadas nesta coleta. Isso mede registros enumerados por fontes integradas, não cobertura nacional completa.
- Playwright em produção: 390px e 1440px; `scrollWidth` da página igual à viewport; busca LGDP abriu a LGPD; Art. 7 visível; zero erros de console, página ou rede. CSP ativo permite scripts/API same-origin e apenas os hosts Google Fonts já usados para stylesheet/font.
- Maria da Penha: histórico segue `partial`, com 65 itens, 62 relações sem texto pareado e sem job ativo; não foi criado diff para relação sem dois textos comprovados.

## Alterações integradas

- `/api/stats` consolidado em consulta agrupada; typo suggestions limitadas aos candidatos quentes; sitemap dividido em índice e fragmentos.
- Canonical/metadata e resumo sem JS; correção de overflow legal em dispositivos móveis.
- CSP e headers de segurança; readiness com verificação de schema; fetch do Planalto limitado a 25 MB; container web non-root.
- CI (Python/E2E/Docker), Dependabot, licença MIT, documentação de contribuição/segurança, templates e runbook de backup/restore.
- Histórico da Maria da Penha solicitado no worker; trabalho terminou sem travar o status: UI/API expõem lacunas como parciais.

## Verificação de código

- `pytest -q`: 138 passed, uma advertência upstream Starlette/httpx.
- `npm run test:e2e`: 5 passed; inclui busca, artigo, histórico/diff comprovado, preparação de lei fria e desambiguação.
- CI remoto dos PRs #63 e #64: Python, E2E e build Docker concluídos com sucesso.
- Nenhuma migration de produção ou exclusão de dados foi executada.

## Limitações que permanecem

1. **Corpus “todas as leis”:** não há inventário nacional único que forneça um denominador verificável; acervos estaduais/municipais têm fontes e cobertura independentes. Portanto, “todas” não pode ser garantido por engenharia nesta sessão. Aumentar cobertura requer localizar e validar cada catálogo oficial e materializar os textos sem exceder política das fontes.
2. **Métricas DB/fatura:** a integração Railway não oferece SQL read-only/EXPLAIN nem billing detalhado. Baseline mediu o volume Postgres em ~3,053/5 GB, mas não tamanho por relação/índice, conexões, EXPLAIN, idade da fila ou invoice real. O custo do relatório é estimativa por preço público.
3. **Rate limit por cliente:** Railway ingress logs exibem IP na borda, mas não comprovamos qual identidade/IP chega à aplicação nem a confiança/ordem dos forwarded headers. Usar `X-Forwarded-For` sem prova permite spoofing; os limites de fila, dedupe e backpressure existentes permanecem, e limiter por cliente precisa de teste de confiança do proxy.
4. **Redirects e adapters:** Planalto agora tem limite de resposta de 25 MB. Validação uniforme do host final/scheme e limites para todos os adapters (em especial Senado) ainda exige fixtures e verificação de redirects legítimos das fontes oficiais.
5. **Worker heartbeat de aplicação:** Railway confirma worker Online e deploy SUCCESS, mas não existe heartbeat separado com regra de frescor visível em API.
6. **Serviço diagnóstico Railway:** `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276` permanece com ação de delete staged (sem volume, fora do caminho do produto). Railway recusou efetivar o patch pelo connector por exigir 2FA no Dashboard. A exclusão exige a sessão autenticada humana já existente no Railway.

Esses itens estão diferenciados entre impossibilidade de provar por esta integração (DB/billing/2FA), ausência de denominador oficial nacional e trabalho técnico futuro (proxy/rate limit, redirects, heartbeat e expansão da cobertura). Não são apresentados como corrigidos.
