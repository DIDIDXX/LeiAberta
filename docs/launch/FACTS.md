# Fact sheet — LeiAberta

Snapshot observado na produção em 05/10/2026, aproximadamente 21:40 UTC. Métricas do acervo mudam conforme os workers sincronizam catálogos e materializam textos; a home deve sempre obtê-las de `/api/stats`.

| Campo | Observado | Origem e ressalva |
| --- | ---: | --- |
| Registros catalogados | 1.327.541 | `GET /api/stats.indexed_laws`; registros das fontes integradas, não a legislação brasileira total |
| Normas com texto materializado | 25.964 | `materialized_laws`; materialização não certifica completude documental |
| Artigos estruturados | 100.975 | `structured_articles`; parser pode preservar estado parcial/revisão |
| Alterações documentadas | 537 | `documented_changes`; relação sem before/after não está incluída como diff comprovado |
| Fontes | 375 registries; 370 status `enumerated` | `GET /api/sources`; inclui linhas descobertas e em sincronização, nem todas são adapters de catálogo |
| Jurisdições territoriais | cadastro IBGE sincronizado | Diretório territorial não implica leis catalogadas por jurisdição |
| Testes Python | 150 passaram | `pytest -q`; testes são automação, não prova de cobertura integral |
| E2E | 2 passaram | `npm run test:e2e`; Playwright local com fixture de alteração oficial arquivada |
| Infraestrutura | Railway: web, worker, PostgreSQL, Redis | Topologia observada; sem serviço externo novo nesta rodada |
| Custo mensal | Não publicado | Não há comprovante de billing/invoice nesta sessão; não inferir custo de configuração de recurso |
| SHA de produção inicial | `a795b403530f818e3e6d1840a68e4dd7469c81e8` | Será substituído pelo SHA final após merge/deploy |

## Atualização automática

O worker consulta o relógio de refresh com intervalo padrão de 3.600 s (mínimo 300 s). Senado e IBGE têm freshness de 24 h; ALESP, SINJ-DF e SAPL, 7 dias. O tempo observado até uma norma aparecer pode incluir a parte restante do TTL, até um intervalo de verificação, paginação/sincronização e backlog; após falha, existe retry limitado. Essas frequências se aplicam somente aos adapters ativos.
