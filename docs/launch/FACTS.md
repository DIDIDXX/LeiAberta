# Fact sheet — LeiAberta

Snapshot da produção após o deploy final, em 05/10/2026, aproximadamente 22:54 UTC. Os valores variam com a sincronização; a home lê as métricas em tempo real de `/api/stats`.

| Campo | Observado | Origem e ressalva |
| --- | ---: | --- |
| Registros catalogados | 1.356.548 | `GET /api/stats.indexed_laws`; metadados de fontes integradas, não total da legislação brasileira |
| Normas com texto materializado | 26.442 | `materialized_laws`; materialização não certifica completude documental |
| Artigos estruturados | 105.744 | `structured_articles`; parsing pode preservar estado parcial |
| Alterações documentadas | 537 | `documented_changes`; relação sem before/after não é contada como diff comprovado |
| Registros de fonte | 394 | `GET /api/sources`; inclui adapters e entradas de fonte descobertas |
| Fontes enumeradas | 383 | `GET /api/stats.enumerated_sources`; outras 5 falhas, 4 descobertas e 2 sincronizando no snapshot |
| Freshness | 383 atuais, 0 stale, 11 desconhecidos | `GET /api/sources`; estado pode mudar após cada tentativa |
| Jurisdições territoriais | diretório IBGE sincronizado | Cadastro territorial não significa leis catalogadas nessa jurisdição |
| Testes Python | 150 passaram | `pytest -q`; automação não prova cobertura integral |
| E2E | 2 passaram | `npm run test:e2e`; inclui busca `LGDP`, demo e contagens realistas no viewport de 390 px |
| Browser matrix | 36 combinações aprovadas | 9 páginas em 390, 430, 768 e 1440 px; sem overflow, erros de console, imagens quebradas ou requests falhados |
| Produção | web, worker e backup `SUCCESS`; PostgreSQL e Redis online | Railway, ambiente `production` |
| SHA de produção | `c66c0138f03b1a83310c07089c265654785706ae` | SHA do merge em `main`, observado como deployado por web/worker/backup |
| Custo mensal | não publicado | Nenhuma fatura disponível nesta sessão; não inferir custo de configuração |

## Atualização automática de normas

O worker consulta o relógio de refresh com intervalo padrão de 3.600 s (mínimo 300 s). Senado e IBGE têm freshness de 24 h; ALESP, SINJ-DF e SAPL, 7 dias. Uma norma nova em uma fonte ativa deve aparecer após o próximo refresh elegível, que pode esperar até o TTL, mais até um intervalo de verificação, paginação, backlog e retry limitado em caso de falha. A suíte de fixture comprovou descoberta, upsert sem duplicação, busca, elegibilidade para hidratação e recuperação após indisponibilidade simulada. Não inserimos registros sintéticos na produção.

Essa garantia se aplica somente a adapters ativos. Configurar uma jurisdição ou sincronizar o cadastro IBGE não integra automaticamente seu portal legislativo.

## Medições HTTP de produção

Uma amostra após o deploy, em segundos. Não é benchmark estatístico; inclui latência de borda/rede e pode variar.

| Rota | Status | Tempo |
| --- | ---: | ---: |
| `/` | 200 | 0,281 |
| `/buscar?q=LGDP` | 200 | 0,277 |
| `/api/search?q=LGDP` | 200 | 0,284 |
| `/lei/10406-2002/artigo/389` | 200 | 0,290 |
| `/api/laws/10406-2002/history` | 200 | 0,402 |
| `/api/laws/10406-2002/blame?limit=250` | 200 | 0,708 |
| `/api/laws/10406-2002/nodes/art%3A389/provenance` | 200 | 0,291 |
| `/api/changes/be3a1531-edaa-5a78-94ca-70c6544e3853` | 200 | 0,276 |
| `/api/sources` | 200 | 0,792 |
| `/api/stats` | 200 | 0,742 |
| `/health`, `/ready`, `/worker-health` | 200 | 0,278–0,282 |
