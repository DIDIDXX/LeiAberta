# LeiAberta — launch polish worklog

## Sessão

- Data: 2026-10-05 UTC.
- Repositório `DIDIDXX/LeiAberta`; branch local `codex/launch-polish-20261005`.
- SHA inicial e produção revalidada: `a795b403530f818e3e6d1840a68e4dd7469c81e8`.
- Produção: https://web-production-12e95.up.railway.app.
- Objetivo: demonstrar uma alteração legislativa real com evidência oficial, tornar gaps/freshness públicos e preparar um kit OSS sem publicar posts.

## Revalidação (05/10/2026)

- Railway web/worker/Postgres/Redis/backup estavam `SUCCESS`; `/health`, `/ready`, `/worker-health` responderam 200.
- API observada: 1.327.541 registros catalogados, 25.964 normas com texto, 100.975 artigos e 537 alterações documentadas. São métricas agregadas e variáveis, não total de leis brasileiras.
- `/api/sources`: 375 registros de fonte; 370 com status `enumerated`, um `syncing` e quatro `discovered` na amostra. Registros de fonte não significam adapters todos de catálogo.
- Hero case: inclusão do art. 19, § 4º, da Lei 11.340/2006 pela Lei 14.550/2023, Planalto direto; diff `3b1c3ba3-dc6e-4481-9aa0-3e197f2f8c10`. A estrutura/histórico geral da Lei Maria da Penha continua parcial. Há um processo compatível no dossiê do Senado da Lei 14.550/2023; não usamos relação processual como prova do diff.
- Refresh: relógio do worker 3.600 s por padrão, mínimo 300 s; TTL de 24 h para Senado/IBGE, sete dias para ALESP/SINJ-DF/SAPL. Falhas ativam retry limitado. Apenas fontes com adapters ativos entram na automação.

## Implementado localmente

- Rotas `/api/laws/{slug}/blame` (consulta em lote) e `/nodes/{node_id}/provenance`; evidência e estado desconhecido explícitos.
- `/api/sources` com freshness, contagens, último sucesso, deltas quando registrados e falhas de sync separadas de falha por registro.
- Home com busca imediata, exemplos, CTA para diff real e métricas servidas por `/api/stats`; páginas `/fontes`, `/cobertura`, `/sobre`; Blame e ações por dispositivo.
- Metadados server-side por norma/artigo, imagem OG, fontes de README/API e launch kit.
- Observabilidade de sync aditiva em `scope` JSON existente; sem migration.
- Playwright usa fixture legal gravada em banco E2E local. O caminho de nova norma chama o adapter Senado com fetch fixtureado e verifica dedupe, falha conservadora, recuperação, busca e elegibilidade de hidratação.

## Validação local

- `pytest -q`: 150 passaram; um aviso de depreciação upstream Starlette/httpx.
- `npm run test:e2e`: 2 passaram, fluxo do hero e typo/mobile, sem chamadas reais aos catálogos oficiais.
- `node --check`, `compileall`, `git diff --check`: passaram.
- `docker build`: apt instala, mas `pip` não valida o certificado interceptado do proxy para PyPI neste executor. A imagem continua no gate CI GitHub.

## Assets e deploy

- OG SVG e script Playwright de captura criados. Screenshots do site ainda serão feitos somente após o deploy final.
- Nenhum commit/PR/deploy desta branch concluído ainda; próxima fase é publicar commits lógicos via GitHub, aguardar CI, merge e conferir Railway.
- Railway apresentou patch já staged desde 15:41 UTC que remove o serviço `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276`. Está marcado destrutivo. Não faz parte do diff deste branch e não foi aceito junto ao deploy do app.
- Durante a medição de performance às 22:07 UTC, `/worker-health` retornou 503 (`Worker heartbeat is stale`) enquanto os logs Railway mostravam o worker completando páginas do catálogo SAPL. A emissão do heartbeat estava no mesmo loop do despacho e podia ficar atrasada por trabalho prolongado; foi movida para thread daemon próprio e coberta por teste. Aguardar deploy para confirmar recuperação em produção.

## Próximas ações

1. Atualizar facts/worklog e aguardar CI do head mais recente do PR.
2. Merge, esperar web/worker Railway em `SUCCESS` e conferir SHA.
3. Smoke de APIs/páginas, browser em 390/430/768/1440 px e performance amostral.
4. Capturar screenshots reais do deploy final, atualizar README/FACTS/relatório e decidir release se houver suporte disponível.
