# Execução do plano LeiAberta — Luna 6

Atualizado em 04/10/2026. Branch local: `docs/luna6-next-steps`. O commit publicado no branch até a criação deste relatório é `6d32fd8debbdef62fd205ebde102ac30ab8400e7`; as alterações de execução abaixo ainda estão em validação e não foram implantadas.

## Resultado observado

O histórico deixou de ser apenas uma mensagem fixa: agora existe job persistido, endpoint para solicitá-lo, consulta de progresso, consulta oficial de relações do Senado e exibição separada entre relação encontrada e diff textual comprovado. Uma execução real local para a LMP consultou o Senado, persistiu 62 relações e terminou como parcial; a LGPD retornou 146 relações. Isso faz o fluxo funcionar e deixa visíveis as lacunas, mas **não reconstrói ainda todas as redações históricas**. Os três diffs anteriores da LMP continuam sendo os exemplos com texto antes/depois já verificado.

O parser corrigido foi exercitado contra quatro documentos reais do Planalto. Resultados atuais: Código Civil com 2.081 artigos, `art:1` com 57 caracteres e `art:2046` presente; Constituição com namespaces separados para Constituição e ADCT; CLT com 962 artigos; Código Penal com 413 artigos. Variantes repetidas permanecem distintas. Os contadores são diagnóstico, não prova de completude. As quatro normas continuam classificadas como texto estruturado parcial até existir auditoria independente de todo conteúdo e anexos.

O sincronizador oficial IBGE foi executado contra os endpoints atuais: 27 estados, 5.571 localidades, 5.569 legislaturas municipais elegíveis e duas localidades especiais classificadas explicitamente. Foram incluídas fontes-semente Planalto, Senado, Câmara, LexML, ALESP e SINJ-DF; sementes em estado `discovered` não significam adapter completo.

## Matriz de tarefas

| Tarefa | Estado | Evidência / lacuna |
|---|---|---|
| T00 linha de base | concluída | `docs/reports/00-baseline.md`; Railway, saúde pública e contagens de referência consultadas. |
| T01 backup e staging | bloqueada antes de qualquer migração em produção | Projeto possui apenas ambiente production. Railway MCP disponível não expõe criação de environment, snapshot ou dump; CLI Railway ausente, sem URL/credenciais de banco locais. Agente Railway confirmou que staging exige Dashboard/CLI e dados não são clonados automaticamente. Nenhum backup ou restore foi demonstrado. |
| T02 estados honestos/histórico | parcial implementada | Estado vazio não promete trabalho fantasma; preparar histórico cria job; fonte Senado exibe relações e separa comparações comprovadas. Reconstrução textual genérica continua faltando. |
| T03 fila durável | implementada no código, ainda não testada em PostgreSQL/Railway | Migração, outbox, Redis Streams, consumer group, ACK/reclaim, leases, retry e dedupe; testes locais passam. Falta teste de queda/reinício real de Redis/worker e aplicação da migration em Postgres isolado. |
| T04 arquivo de fontes | parcial | Snapshots existentes preservados e XML do Senado guardado quando já há versão materializada. Falta entidade independente de versão para arquivar a fonte antes/depois de parsing falhar. |
| T05 parser/IDs | parcial implementada | Milhar, sufixos, pontuação, redação marcada, variantes e ADCT corrigidos e fixtures reais exercitados. Hierarquia integral, notas, tabelas, anexos e auditoria de todos os 14 ainda faltam. |
| T06 PDFs/anexos | não iniciado | Não há ingestão de anexos nem extração com evidência por página. |
| T07 auditor de completude | não iniciado | Versões são deliberadamente `partial`; falta inventário reconciliável de todos os segmentos. |
| T08 leitor progressivo | parcial | Rotas por artigo e leitor atual funcionam; sumário/anexos/paginação progressiva ainda faltam. |
| T09 jurisdições/registro de fontes | parcial implementada | IBGE sincronizado e endpoint paginado; falta histórico territorial, autoridade/aliases, status por todos os acervos e tabela de lacunas completa. |
| T10 contrato/sync retomável | não iniciado | Ainda não há interfaces de adapter, cursores, partições e retomada. |
| T11 Senado/Câmara nacional | parcial de pesquisa | Adapter de relações Senado implementado; falta enumeração federal e adapter de catálogo/textos da Câmara. |
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
| T26 release Railway | bloqueado | Não houve mutação nem deploy. É necessário preparar backup/restauração e testar migrations/worker em Postgres/Redis isolados primeiro. |
| T27 documentação | parcial | README e este relatório atualizados; documentação de operação e requisitos restantes estão neste relatório/plano. |

## Validação executada

- `.venv/bin/pytest -q`: 19 testes passaram.
- `npm run test:e2e`: 4 testes passaram; incluem busca, leitura, fonte oficial, histórico/diff e resolução ambígua de artigo.
- `python -m compileall` e `git diff --check`: passaram antes da última edição documental; repetir no commit final.
- Alembic `upgrade head`: passou em SQLite recém-criado, incluindo migrations 0002 e 0003.
- IBGE: sincronização real passou em SQLite isolado, resultados acima.
- Pipeline de histórico real local: LMP criou 62 eventos oficiais; status `partial`, texto histórico pendente. A integração foi exercitada antes do endpoint de relatório final.
- Produção Railway: continua no SHA anterior; HTTP `/health` respondeu 200 antes destas alterações. Nenhuma nova versão foi implantada.

## Bloqueios para o release e para “todas as leis”

1. Criar staging Railway e obter backup lógico ou snapshot restaurável de Postgres; validar restore e migration em ambiente isolado. A API Railway disponível não oferece esses comandos e o shell desta execução não tem CLI/credenciais.
2. Implementar enums/adapters para Câmara, Senado (catálogo), Planalto histórico, ALESP/SINJ, SAPL e outras famílias; confirmar hosts e contratos por jurisdição.
3. Reconstituir antes/depois e vigência por dispositivo a partir de fontes primárias; relações do Senado não bastam para declarar histórico completo.
4. Implementar validação documental integral, anexos/PDFs e promoção de versões apenas após reconciliação.
5. Operar lotes nacionais com denominadores por acervo. “Todas” continua meta não cumprida; não existe uma API única que prove o universo legal do Brasil.

Nenhum resultado sintético foi adicionado como lei. O diretório IBGE descreve territórios, não conteúdo legislativo.
