# LeiAberta — worklog final

## Identificação

- Data: 2026-10-05 UTC.
- Repositório: `DIDIDXX/LeiAberta`.
- Branch publicada: `main`.
- SHA funcional validado: `06646081480668017d288ad89e98545eead82a0c` (PR #68).
- URL: https://web-production-12e95.up.railway.app.
- Ambiente Railway: `b415a556-41ec-4f33-994f-1f5d38b633a1`.

## Baseline e decisão

- Topologia final: web, Redis, Postgres e backup em Singapura; worker em US East; uma réplica por serviço.
- Postgres volume 5 GB; baseline anterior mediu ~3,053 GB utilizados. SQL e billing não são expostos pelo connector; relação/index size, conexões, queue age/EXPLAIN e invoice não disponíveis.
- Custo sem serviço novo nesta rodada: rate limiting usa Redis já existente. Não houve migration de DB nem backfill destrutivo.
- Não usar `X-Forwarded-For` como identidade até provar a confiança do proxy. Aplicar budgets globais Redis enquanto isso.
- Não declarar corpus nacional completo: nenhuma fonte única oferece denominator de todas as normas federais, estaduais e municipais.

## Entregas

- PR #62: quebra de texto comprido em mobile; E2E Art. 7; CI verde.
- PR #63: `/ready`, CSP, cap 25 MB Planalto; CI verde.
- PR #64: allowlist mínima para Google Fonts já usados; browser smoke sem erros.
- PR #65: relatório de produção.
- PR #66: Planalto HTTPS/host allowlist, redirects verificados antes do follow, retries transitórios limitados; CI verde depois de preservar User-Agent compatível com a fonte.
- PR #67: rate budgets Redis (search 600/min, detail/nodes 240/min, job prepare 60/min), 429 + Retry-After; sem trust em forwarded IP.
- PR #68: heartbeat Redis com TTL 90s, emitido a cada 30s; `/worker-health` 200/503.
- Auditorias, ADR, custo/escala, runbook backup/restore, licença MIT, contribuição, segurança, Code of Conduct, CI, Dependabot e templates já integrados.

## Testes e produção

- `pytest -q`: 146 passed; um aviso upstream Starlette/httpx.
- `npm run test:e2e`: CI Python/E2E/Docker verde nos PRs #66, #67 e #68. Uma tentativa local anterior falhou após Planalto devolver 503 repetidos; CI externo passou após restaurar o User-Agent previamente compatível.
- Browser após deploy: 390px e 1440px; LGDP → LGPD → Art. 7, overflow 0, nenhum erro console/page/network.
- Smoke final: health 200/0,311s; ready 200/0,297s; worker-health 200/0,261s; LGDP 200/0,287s; Maria da Penha history 200/0,299s/parcial; sitemap 200/0,371s; stats 200/0,824s. Medições amostrais, não p95.
- Stats final consultado: 1.167.592 entradas enumeradas, 23.013 materializadas.
- Serviços/deploys SUCCESS: web `e29b4142-1f73-49f4-9c70-915635b1c03c`; worker `06b79a18-ccc6-486b-841c-311cfba2155e`; backup `8dab8856-0731-4edf-afb5-967e752a98ad`; Redis `e0cc2708-a527-4918-aa06-3f994675234a`; Postgres `78c139ee-fc38-4883-be04-99d72052c7d0`.
- Histórico de `11340-2006`: 65 itens, 62 sem redação pareada, estado partial; a UI não inventa comparação.

## Itens não concluídos / bloqueios concretos

- Corpus nacional de todas as leis: sem denominator nacional ou fonte completa; expansão tem que ser por integração/validação oficial.
- SQL read-only/EXPLAIN e billing: não disponíveis via integração Railway nesta sessão.
- Rate limit por IP/cliente: origem confiável não demonstrada; budgets globais reduzem picos sem aceitar identidade falsificável.
- Limites/redirect tests de todos os adapters: cobertura comum ainda varia por fonte; Planalto foi fechado neste ciclo.
- Remover serviço diagnóstico: patch staged requer 2FA no Dashboard e o connector recusou efetivação sem esse fator.

## Próxima ação exata fora do código

1. No Railway Dashboard, com sessão autenticada/2FA, aceitar o delete staged do `pg-diagnostic`.
2. Com ferramenta SQL read-only e billing access, medir índices/tabelas/conexões/queue age e invoice antes de ajustar custo/índices.
3. Só implementar limiter per-client depois de confirmar o IP de origem fornecido pelo proxy Railway; manter o budget global ativo até lá.
4. Expandir cobertura jurídica conectando fontes oficiais por jurisdição e registrando denominator/evidência de cada integração.
