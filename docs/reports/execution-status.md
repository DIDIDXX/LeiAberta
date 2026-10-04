# Execução do plano LeiAberta — Luna 6

Atualizado em 04/10/2026. Branch local: `docs/luna6-next-steps`; entrega mesclada em `main` pelo PR #1 (merge commit `197da4502a97786abca43d98f2f3f395c32ea648`). Railway production executou os deployments web `6876e9b3-ec4f-442d-8958-6d198e18309b` e worker `404e6e54-0178-45df-ada4-9885acab0fab`, ambos `SUCCESS`. Aplicação pública: https://web-production-12e95.up.railway.app.

## Resultado observado

O histórico deixou de ser apenas uma mensagem fixa: agora existe job persistido, endpoint para solicitá-lo, consulta de progresso, consulta oficial de relações do Senado e exibição separada entre relação encontrada e diff textual comprovado. Uma execução real local para a LMP consultou o Senado, persistiu 62 relações e terminou como parcial; a LGPD retornou 146 relações. Isso faz o fluxo funcionar e deixa visíveis as lacunas, mas **não reconstrói ainda todas as redações históricas**. Os três diffs anteriores da LMP continuam sendo os exemplos com texto antes/depois já verificado.

O parser corrigido foi exercitado contra quatro documentos reais do Planalto. Resultados atuais: Código Civil com 2.081 artigos, `art:1` com 57 caracteres e `art:2046` presente; Constituição com namespaces separados para Constituição e ADCT; CLT com 962 artigos; Código Penal com 413 artigos. Variantes repetidas permanecem distintas. Os contadores são diagnóstico, não prova de completude. As quatro normas continuam classificadas como texto estruturado parcial até existir auditoria independente de todo conteúdo e anexos.

O sincronizador oficial IBGE foi executado contra os endpoints atuais: 27 estados, 5.571 localidades, 5.569 legislaturas municipais elegíveis e duas localidades especiais classificadas explicitamente. Foram incluídas fontes-semente Planalto, Senado, Câmara, LexML, ALESP e SINJ-DF; sementes em estado `discovered` não significam adapter completo.

A API do Senado também foi consultada no endpoint `legislacao/lista?tipo=LEI`: HTTP 200, 8.563.787 bytes e 16.883 documentos de lei enumerados, desde 1821 até 2026. O sincronizador local importou 16.873 novas linhas e ligou 10 dessas identidades às leis-semente existentes. As demais quatro sementes são de outros tipos. A identidade externa e a data de assinatura são separadas; a data de publicação continua nula quando não veio comprovada pela listagem. Uma segunda sincronização foi idempotente: 0 novas linhas e 16.883 atualizadas. O checksum SHA-256 da resposta foi `a4bcd56d42789cd41bca622f19df3f42e34c302a08cc4242f3408a8ff1c7550f`; o checksum da sequência de IDs foi `a3bdde23e8d8662ca230110d403edac419bb3d95725e5341d69dcecea4812162`.

## Matriz de tarefas

| Tarefa | Estado | Evidência / lacuna |
|---|---|---|
| T00 linha de base | concluída | `docs/reports/00-baseline.md`; Railway, saúde pública e contagens de referência consultadas. |
| T01 backup e staging | bloqueada antes de qualquer migração em produção | A documentação oficial Railway confirma duplicação de ambiente pela Dashboard/CLI. Nesta sessão não há CLI Railway nem token no shell, e o MCP disponível não expõe criação de environment, snapshot ou dump. O projeto só tem production no momento. Nenhum backup ou restore foi demonstrado. |
| T02 estados honestos/histórico | parcial implementada | Estado vazio não promete trabalho fantasma; preparar histórico cria job; fonte Senado exibe relações e separa comparações comprovadas. Reconstrução textual genérica continua faltando. |
| T03 fila durável | implementada e exercitada em produção | Migração, outbox, Redis Streams, consumer group, ACK/reclaim, leases, retry e dedupe; preparação da LGPD em produção terminou `succeeded` em 1 tentativa. Logs mostram tarefas de hidratação finalizadas no worker. Falta teste controlado de queda/reinício de Redis/worker. |
| T04 arquivo de fontes | parcial | Snapshots existentes preservados e XML do Senado guardado quando já há versão materializada. Falta entidade independente de versão para arquivar a fonte antes/depois de parsing falhar. |
| T05 parser/IDs | parcial implementada | Milhar, sufixos, pontuação, redação marcada, variantes e ADCT corrigidos; reparse usa versão imutável com promoção atômica. Fixtures reais exercitados. Hierarquia integral, notas, tabelas, anexos e auditoria dos 14 ainda faltam. |
| T06 PDFs/anexos | não iniciado | Não há ingestão de anexos nem extração com evidência por página. |
| T07 auditor de completude | não iniciado | Versões são deliberadamente `partial`; falta inventário reconciliável de todos os segmentos. |
| T08 leitor progressivo | parcial | Rotas por artigo e leitor atual funcionam; sumário/anexos/paginação progressiva ainda faltam. |
| T09 jurisdições/registro de fontes | parcial implementada | IBGE sincronizado e endpoint paginado; falta histórico territorial, autoridade/aliases, status por todos os acervos e tabela de lacunas completa. |
| T10 contrato/sync retomável | não iniciado | Ainda não há interfaces de adapter, cursores, partições e retomada. |
| T11 Senado/Câmara nacional | parcial implementada e sincronizada | Produção importou 16.883 registros `tipo=LEI` do Senado (16.873 novas identidades mais 10 sementes existentes; contagem total da aplicação 16.887 inclui outros tipos-semente). Faltam outros tipos federais e adapter de catálogo/textos/publicação original da Câmara. |
| T12 LexML | pesquisa bloqueada | SRU respondeu desafio HTML; não há adapter declarado funcional. |
| T13 ALESP/SINJ | pesquisa inicial | Entrypoints registrados; paginação, busca, fixtures documentais e adapters não implementados. |
| T14 SAPL/Campinas/Piracicaba | pesquisa inicial | Host candidato não confirmado; não há adapter municipal ainda. |
| T15 expansão nacional | não iniciado além do inventário de território | Não há fontes oficiais enumeradas para cada estado/localidade. |
| T16 busca nacional SQL | parcial herdada | Busca atual e ambiguidades têm testes; falta catálogo nacional e resolução contextual municipal real. |
| T17 ledger de relações | parcial implementada | Relações do Senado por dispositivo persistidas; sem resolução e download recursivo dos atos modificadores. |
| T18 operações/tempo jurídico | não iniciado | Datas de assinatura/publicação separadas em eventos; vigência por dispositivo e operações ADD/REPLACE/REPEAL genéricas não reconstruídas. |
| T19 reconstrução de versões | não iniciado genericamente | Só existem os três diffs LMP históricos previamente conferidos. |
| T20 timeline/diff | parcial | Interface apresenta diffs comprovados e relações pendentes; seletor por data e versões reais ainda faltam. |
| T21 blame | não iniciado | Sem proveniência por trecho/dispositivo além das relações existentes. |
| T22 histórico em lote | não iniciado | Job é sob demanda por norma; sem lote geral. |
| T23 processos/autoria | pesquisa apenas | Vínculo conhecido LMP pesquisado; modelos/importação não implementados. |
| T24 votos | não iniciado | Não há dados de votos associados. |
| T25 scheduler/freshness | não iniciado | Worker consome fila; falta scheduler contínuo, política de atualização e métricas por fonte. |
| T26 release Railway | release e smoke concluídos; backup/staging pendente | Web e worker chegaram a `SUCCESS`; migrations e sincronizações executaram na inicialização. `/health` 200, busca `LGDP` resolve LGPD, detalhe/artigo/histórico e fontes respondem. POST de preparação de histórico na LGPD terminou `succeeded`, retornou 146 relações e cobertura `partial`. Playwright contra produção abriu home, busca, lei, artigo e histórico em viewport 390px sem erros de console ou overflow horizontal. Nenhum staging/restore foi demonstrado; esse controle operacional continua pendente. |
| T27 documentação | parcial | README e este relatório atualizados; documentação de operação e requisitos restantes estão neste relatório/plano. |

## Validação executada

- `.venv/bin/pytest -q`: 23 testes passaram na validação mais recente.
- `npm run test:e2e`: 4 testes passaram após as últimas alterações de fila, catálogo e leitor; incluem busca, leitura, fonte oficial, histórico/diff e resolução ambígua de artigo.
- `python -m compileall` e `git diff --check`: passaram antes da última edição documental; repetir no commit final.
- Alembic `upgrade head`: passou em SQLite recém-criado, incluindo migrations 0002 e 0003.
- IBGE: sincronização real passou em SQLite isolado, resultados acima.
- Senado: listagem integral `tipo=LEI` foi sincronizada em SQLite isolado; busca com typo e número/ano passou contra os 16.883 registros.
- PostgreSQL 18: migrations 0001–0005 passaram em banco isolado, incluindo downgrade/upgrade da restrição de representações imutáveis; migration de datas arquiva alegações legadas como não verificadas e downgrade restaura campo/cobertura. Em outra base PG, seed e job da LGPD passaram; endpoint real do Senado terminou com 146 relações e cobertura parcial.
- Busca contra catálogo de 16.883 leis: `LGPD`, `LGDP`, `13709/18`, `lei 13709` e busca por ementa responderam corretamente; consulta typo `LGDP` levou ~43 ms no banco de teste já aquecido.
- Pipeline de histórico real local: LMP criou 62 eventos oficiais; status `partial`, texto histórico pendente. A integração foi exercitada antes do endpoint de relatório final.
- Produção Railway: web e worker `SUCCESS`; `/health` 200 e `/api/stats` relata 16.887 metadados, 8.734 artigos estruturados e 3 diffs comprovados. O worker já reprocessou versões de destaques com estado parcial. Busca, detalhe, artigo 7, histórico existente e fontes responderam HTTP 200. História da LGPD sob demanda completou em 5 segundos, armazenando 146 relações oficiais como parciais, sem inventar diff textual. Playwright público passou os caminhos `/`, `/buscar?q=LGDP`, detalhe da LGPD, artigo 7 e histórico em viewport móvel, sem erros JavaScript e sem largura excedente.
- Logs iniciais do worker registraram `UndefinedTable job_outbox` enquanto o serviço web ainda aplicava migrations; após essa janela, o worker processou hidratações com sucesso. A fila de preparação do histórico foi verificada ao vivo após migrations e concluiu sem erro. A classificação textual permanece `partial` de propósito.

## Próximas entregas necessárias para “todas as leis”

1. Criar staging Railway e obter backup lógico ou snapshot restaurável de Postgres; validar restore e migration em ambiente isolado. A API Railway disponível não oferece esses comandos e o shell desta execução não tem CLI/credenciais. O deploy feito não é evidência de backup/restore.
2. Ampliar o catálogo do Senado para outros tipos normativos; implementar adapters Câmara/Planalto histórico/ALESP/SINJ/SAPL e confirmar hosts/contratos por jurisdição.
3. Reconstituir antes/depois e vigência por dispositivo a partir de fontes primárias; relações do Senado não bastam para declarar histórico completo.
4. Implementar validação documental integral, anexos/PDFs e promoção de versões apenas após reconciliação.
5. Operar lotes nacionais com denominadores por acervo. “Todas” continua meta não cumprida; não existe uma API única que prove o universo legal do Brasil.

Nenhum resultado sintético foi adicionado como lei. O diretório IBGE descreve territórios, não conteúdo legislativo.
