# Execução do plano LeiAberta — Luna 6

Atualizado em 05/10/2026 às 02:16 UTC. Código de produção: main 953b10f10e7e9daca53cab215e72e8b728308a4c. Railway web e worker em SUCCESS; /api/health responde 200. Deploys web 552576e2-b37b-41eb-a53a-573f0a3dae33 e worker 77a4d645-b3f1-4422-ab0a-1742df97f863.

## Estado de produção

| Fonte | Escopo verificado | Com texto na coleta | Estado |
|---|---:|---:|---|
| Senado Federal | 47.316 registros em 6 tipos: LEI, LCP, EMC, MPV, DLG e RSF | 4.053 | Enumeração concluída nesses tipos; outras classes federais e atos da Câmara ainda não integrados. |
| ALESP — SP | 181.172 | 154 | Todas as 37 páginas da consulta oficial gravadas; hidratação ativa. |
| SINJ-DF | 125.478 | 175 | Todas as 26 páginas do snapshot gravadas; hidratação ativa. |
| SAPL — Manaus | 9.846 | 3 | 99/99 páginas, 9.846 no banco; hidratação ativa. |

Na mesma medição: 363.826 registros indexados, 4.397 com texto estruturado, 29.902 dispositivos, 57 alterações documentadas e 5.205 jobs ativos. Estes contadores mudam com o worker. “Pendente” descreve o estado naquela coleta e não prova que a fonte publique anexo para cada registro.

A sincronização SAPL completou em 05/10 às 02:08:30 UTC: 9.846 listados, 1.846 inseridos, 8.000 atualizados, checksum de IDs 2fbbeace09e072fa1e75dc69e5a508d6eac0f557dfed18bc56ae5ced2fc2d3ae. O bloqueio da página 34 foi identificado como conflito de linha entre a atualização periódica de laws.coverage e jobs de hidratação. A sincronização agora evita regravar timestamps por norma quando nada mudou; a enumeração terminou sem novo lock. Depois, o worker foi ampliado para 16 tarefas concorrentes com prioridade preservada para pedidos interativos. Nos primeiros 88 segundos de execução com o limite novo, 80 jobs de hidratação terminaram.

## Busca, texto e histórico

- A API pública está saudável e a busca cobre os registros armazenados nas fontes conectadas.
- O histórico da Lei 11.340/2006 retorna 65 itens: 3 comparações textuais comprovadas e 62 relações oficiais sem texto suficiente para comparar. O estado é partial, sem job ativo; a interface informa a lacuna em vez de manter “preparando”.
- O leitor DOU foi corrigido para publicações senatoriais que aparecem como “Resolução” sob a hierarquia oficial “Atos do Senado Federal”. RSF 24/2024, 25/2024 e 27/2024 foram baixadas e processadas ao vivo; os respectivos jobs concluíram com 27, 27 e 25 dispositivos.
- A Lei SAPL 115/1949, publicada em 05/01/1949, foi hidratada em produção. A versão tem 6 nós, 4 artigos extraídos e 1.165 caracteres estruturados. A auditoria registra 241.460 caracteres extraíveis da fonte e marca a estrutura review_required; não certifica que a transcrição contenha todo o PDF. A fonte original segue ligada.
- O histórico da Lei 115/1949 foi consultado com job succeeded. O SAPL não retornou relações oficiais para essa norma. A interface mostra que ausência de relação não comprova que nunca houve alteração.

## Validação executada

- Suíte Python completa: 88 testes passaram, com 3 avisos de depreciação.
- Playwright local: 4 E2E passaram — busca LGDP/LGPD, diff oficial no histórico, hidratação sob demanda e ambiguidade na busca por artigo.
- O teste E2E usou banco SQLite descartável separado; o arquivo .e2e.db existente foi preservado.
- Railway web e worker estão em SUCCESS e /api/health retorna 200.

## Estado por tarefa do plano

| Tarefas | Estado | Evidência e lacuna atual |
|---|---|---|
| T00 — linha de base | concluído | Repositório, serviços Railway, migrations, fontes e APIs auditados. |
| T01 — backup restaurável e staging | bloqueado por plano/acesso | Railway Hobby informa maxBackupsCount=0; o conector não oferece shell/execução SQL/pg_dump/restore. Não há backup restaurável demonstrado. |
| T02 — estados de job e cobertura | implementado | Busca, hidratação e histórico têm estados próprios; falha ou texto ausente não fica mascarado como job em andamento. |
| T03 — fila durável e recuperação | implementado | Outbox, Redis Streams, ACK após processamento e recuperação de mensagens. Pedidos interativos têm prioridade sobre o backfill. |
| T04 — arquivo bruto e proveniência | implementado para fontes conectadas | Captura, checksums e referência à publicação original são preservados; reprocessamento não substitui silenciosamente a origem. |
| T05 — identidade e parser | implementado nos formatos cobertos | Identidade oficial é verificada; o parser não inventa número, vigência ou origem. DOU e SAPL têm casos de exceção testados. |
| T06 — PDF, tabelas, anexos e OCR | parcial por fonte | PDF/OCR/DOCX estão cobertos em algumas integrações; documentos sem anexo precisam de outra fonte oficial. |
| T07 — auditoria de completude | parcial | Auditoria detecta divergências, mas não certifica sozinha a validade jurídica. A Lei 115/1949 ficou review_required. |
| T08 — leitor progressivo | parcial | Busca, navegação por dispositivo e estados de hidratação funcionam; faltam modelos e anexos de fontes não integradas. |
| T09 — inventário territorial | parcial | IBGE fornece 27 UFs e 5.571 localidades, mas isso não equivale a catálogo legislativo dessas jurisdições. |
| T10 — sincronização retomável | implementado nas quatro fontes conectadas | Senado, ALESP, SINJ-DF e SAPL/Manaus registram escopo, paginação, checkpoints e status. |
| T11 — catálogo federal | parcial | Senado enumera seis tipos; falta reconciliar outros atos federais e integrar a Câmara dos Deputados. |
| T12 — LexML | bloqueio de acesso observado | O probe SRU recebeu HTML de desafio anti-automação, sem resultados utilizáveis nesta sessão. |
| T13 — ALESP e SINJ-DF | enumeração concluída | SP: 181.172; DF: 125.478 no snapshot gravado. O backfill de texto continua. |
| T14 — SAPL/municípios | Manaus enumerada por completo | 9.846 registros da API oficial no banco; outros municípios não são cobertos pelo adapter Manaus. |
| T15 — demais estados e municípios | não concluído; trabalho executável | Não existe denominador nacional oficial demonstrado nem adapters validados para as demais UFs e milhares de Câmaras. A falta de integração não é impossibilidade técnica comprovada. |
| T16 — busca | implementada sobre os dados armazenados | A busca opera sobre o catálogo conectado; não encontra registros fora dele. |
| T17 — relações e histórico | implementado para Planalto, Senado, ALESP, SINJ-DF e SAPL; conteúdo parcial | Só gera diff quando os dois textos e a identidade do dispositivo foram verificados. |
| T18/T19 — vigência e reconstrução temporal | parcial | Vigência por dispositivo e redações para intervalos históricos não são inferidas sem prova oficial. |
| T20 — timeline e diff | parcial, baseado em evidência | Diff é exposto quando existe comparação textual verificada; outras relações aparecem como referência. |
| T21 — autoria e atribuição | parcial | Alguns metadados de autoria existem; autoria por dispositivo e cadeia política completa não são inferidas. |
| T22 — backfill nacional | ativo, incompleto | Há 5.205 jobs ativos na medição e dezenas de milhares de textos pendentes. O worker agora aceita 16 jobs concorrentes; o processo segue em lotes e depende das fontes. |
| T23/T24 — proposições, emendas e votos | não concluído | Falta ligar com confiança cada alteração a proposição, relatoria, autoria e votos individuais. |
| T25 — atualização e frescor | parcial | Catálogos conectados atualizam periodicamente; faltam alertas e SLAs por jurisdição/fonte. |
| T26 — Railway | publicado e saudável | Deploy web/worker SUCCESS; API health 200. |
| T27 — documentação | atualizado nesta revisão | Este relatório registra evidências, limites comprovados e trabalho ainda executável. |

## Limitações externas comprovadas

1. **Backup e restore:** o plano Railway Hobby não disponibiliza backups gerenciados (maxBackupsCount=0). As ferramentas conectadas também não oferecem uma sessão SQL/container para executar e validar pg_dump/restore. Por isso não foi possível demonstrar recuperação nem staging a partir de backup nesta sessão.
2. **LexML SRU:** a rota consultada respondeu um desafio HTML anti-automação em HTTP 200, em vez de registros. Não havia credencial ou rota alternativa autenticada disponível pelo conector.
3. **Anexos SINJ-DF:** 5.184 registros do snapshot anterior não declaravam arquivo textual. A busca de acervos oficiais alternativos ainda é necessária para esses casos.
4. **Redações históricas:** relação de alteração sem redações anterior/posterior ou vigência por dispositivo não permite produzir um diff jurídico confiável. A interface mostra essa relação sem inventar o texto.
5. **Classificação jurídica da fonte:** Normas.leg.br identifica algumas transcrições/compilações como não oficiais; LeiAberta mantém essa classificação.

## Trabalho que não deve ser chamado de impossibilidade técnica

O Brasil não tem um único endpoint oficial nacional demonstrado com todas as normas de todas as Casas Legislativas. Isso torna a integração federada extensa: cada fonte precisa ser descoberta, ligada ao domínio oficial, paginada, reconciliada e validada. Não prova que os adapters ausentes sejam impossíveis. As demais UFs, os outros municípios, tipos federais adicionais, proposições/votos e a auditoria completa continuam fora da cobertura e exigem trabalho de integração.

Também não terminou o backfill de texto: 4.397 de 363.826 registros estavam materializados na medição. O worker continua ativo; o saldo depende de resposta dos portais, existência de anexos, qualidade do OCR e validação documental.