# Execução do plano LeiAberta — Luna 6

Atualizado em 05/10/2026 às 09:20 UTC. Retratos da API às 09:15 e do diretório de fontes às 09:17. Repositório `DIDIDXX/LeiAberta`, `main` no commit `3abebdd47677654712ce983ef65e0325dd7738ed`. Produção: https://web-production-12e95.up.railway.app.

## O que está funcionando em produção

- Web, worker, PostgreSQL e Redis estão online. O deploy web `d311681b-f3fb-4e0f-856c-2618ce2b29c1` e o worker atual `e51525f1-859a-4eb0-9f72-a0c2c5a598d5` terminaram em `SUCCESS`. A variável `HYDRATION_CONCURRENCY` foi configurada em 24, limite definido no código, e o worker foi redeployado com `SUCCESS`; os logs mostram hidratações concorrentes e commits SAPL avançando. O Railway não publica essa variável em log de startup, então o valor vem da configuração aplicada, não de uma leitura em runtime. A sincronização simultânea de catálogos SAPL continua em 1 para proteger o banco.
- `GET /health`, `GET /api/laws/11340-2006/history` e `GET /api/laws/senado-36981001/proceedings` responderam `200` em produção. A página de tramitação e `static/app.js` também responderam `200`.
- O histórico não fica mais preso em “está sendo preparado”: para a Lei Maria da Penha a API responde `status=partial`, 65 relações oficiais e nenhum job ativo. Sessenta e duas relações seguem sem os dois textos necessários para comparação (`events_pending_text=62`); o sistema mostra as relações sem inventar diffs. Verificação da API às 09:22 UTC.
- O dossiê piloto da Lei 14.550/2023 está completo: ligação exata ao PL 1604/2022, emenda e votação no Senado, referência oficial cruzada para a Câmara, proposição com 46 movimentações, 20 proposições relacionadas, nove sessões de votação e 379 votos nominais. Respostas oficiais foram arquivadas com checksum.

## Backup e Railway

- O backup depois da migration de tramitação concluiu em 05/10/2026 às 09:15:50 UTC; duração 5m14s. O log final confirma dump `postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump`, 247.073.141 bytes, SHA-256 `d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190` e `restore_verified=True`.
- Após essa confirmação, o cron foi restaurado para `0 3 * * *` (diário às 03:00 UTC). Railway mostra serviço de backup ativo e nenhum staged change. O dump imediatamente anterior à migration também havia sido verificado: `postgres/leiaberta-production/20261005T071058Z-b543db8f.dump`, SHA-256 `f490f6f56433b67452a9bb20b553c89331ea36e0038421d4b7ddd9eb79888ae4`.
- A migration `20261005_0010` foi aplicada após remover apenas conexões PostgreSQL que correspondiam integralmente às identidades obsoletas verificadas (PID, endereço/porta, tempos da conexão/transação e tipo de lock). A migration agora também limita lock e statement timeout. O healthcheck do web passou.
- Foi medido o uso da última hora antes de elevar a concorrência: worker com pico de 0,19 vCPU e 0,77 GB de RAM em limites de 8; Postgres com pico de 2,59 vCPU e 1,84 GB em limites de 8. A mudança para 24 usa o limite já imposto pelo programa. Monitorar erros de origem e carga após o rollout.

## Retrato dos dados

| Medida | API às 09:15 UTC |
|---|---:|
| Normas indexadas | 833.109 |
| Normas com texto materializado | 14.254 (cerca de 1,7% do índice) |
| Artigos/dispositivos estruturados | 51.938 |
| Alterações documentadas | 376 |
| Catálogo do Senado | 227.849 |
| Senado: texto disponível / indisponível / pendente | 10.621 / 511 / 216.717 |
| Jobs ativos de texto do Senado | 7.176 |
| Chaves de catálogo subnacional na API de métricas | 88 |
| Catálogos subnacionais somados por fonte | 605.346; 3.619 com texto; 4 indisponíveis; 601.723 pendentes |

Os catálogos subnacionais podem conter sobreposição entre fontes; a soma não é uma contagem de normas únicas. Contagem de normas indexadas também não é um denominador nacional.

O diretório de fontes às 09:17 tinha 117 entradas: 111 enumeradas, duas em sincronização e quatro descobertas. São 86 entradas SAPL. O plano de fontes contém 589 instalações SAPL candidatas (581 municipais e oito estaduais); 503 ainda não estão enumeradas no diretório ativo. A sincronização SAPL salva checkpoints e continuava avançando páginas no momento desta leitura. Os números mudam à medida que o worker trabalha.

## T00–T27 — situação e razão do que falta

| Tarefa | Situação | O que falta / por quê |
|---|---|---|
| T00 — linha de base | Concluída | Repositório, APIs, fontes e Railway foram inspecionados. |
| T01 — backup e restauração | Concluída | Dump pós-migration foi restaurado em ambiente isolado e comparado; cron diário está de volta às 03:00 UTC. |
| T02 — estado de job e cobertura | Concluída | APIs persistem estados; histórico da Maria da Penha já responde `partial`, não preparação infinita. |
| T03 — fila durável | Concluída | Outbox, Redis Streams, recuperação e prioridade interativa ativos. |
| T04 — proveniência | Concluída nos adapters integrados | Snapshot e checksum são arquivados nos fluxos verificados. Fontes ainda sem adapter não podem ser atestadas. |
| T05 — identidade e parsing | Parcial | Parsing exige formatos e identidades reconhecíveis; documentos ambíguos precisam de revisão da fonte. |
| T06 — PDF, OCR, DOCX e tabelas | Parcial por fonte | O pipeline serve os formatos encontrados nos adapters; arquivo ausente, ilegível ou sem extração exige original legível ou revisão. |
| T07 — auditoria de completude | Parcial | Diferenças mecânicas são destacadas; certificar que uma consolidação não omite dispositivo exige documento de referência e revisão jurídica integral. |
| T08 — leitor progressivo | Funcional para dados importados | Busca, texto, origem, histórico e estados carregam em produção; conteúdo ainda não importado não aparece completo. |
| T09 — inventário territorial | IBGE concluído; legislação parcial | Há 27 UFs e 5.571 localidades no diretório; cada Casa legislativa ainda requer um catálogo legal de fonte própria. |
| T10 — sincronização retomável | Implementada e ativa | Checkpoints e hashes permitem retomar; a enumeração das instalações candidatas ainda está em execução. |
| T11 — catálogo federal | Parcial | 24 classes do Senado estão integradas; não equivalem a todos os atos federais de todos os órgãos. |
| T12 — LexML | Bloqueado para coleta automática testada | O SRU retorna desafio anti-automação. É necessário acesso autorizado ou outra fonte oficial; o bloqueio não será contornado. |
| T13 — ALESP e SINJ-DF | Catálogos integrados; backfill em andamento | ALESP tem 181.172 registros e 1.803 textos; SINJ-DF, 125.478 e 1.752 textos no retrato. |
| T14 — SAPL municipal/estadual | Em execução | 86 fontes SAPL no diretório; outras 503 configurações candidatas ainda precisam confirmar portal e catálogo real. |
| T15 — portais fora de SAPL | Integração pendente | Casas usam sistemas e formatos diferentes; cada portal requer descoberta, adapter e validação próprios. |
| T16 — busca | Funcional sobre o índice | Encontra normas indexadas; não encontrar algo não prova que a norma inexiste. |
| T17 — histórico | Funcional e parcial | Relações oficiais são mostradas; comparação só é gerada quando existem versões textuais verificáveis. |
| T18/T19 — vigência e versões históricas | Parcial por dados de origem | Sem texto e data eficaz fornecidos por fonte confiável, não se afirma a redação vigente em uma data passada. |
| T20 — timeline/diff | Parcial, com evidência | Diff exige versões anterior e posterior; relações sem ambas não recebem diff fabricado. |
| T21 — autoria por dispositivo | Parcial | Autoria e relatoria da proposição piloto estão ligadas; atribuir autoria política a cada dispositivo exige relação documental explícita. |
| T22 — backfill de texto e histórico | Em andamento no worker | Às 09:15 havia 7.176 jobs ativos do Senado. Mais de 818 mil registros pendentes nos catálogos medidos continuam dependendo de processamento; os universos se sobrepõem. |
| T23/T24 — proposições, emendas e votos | Piloto funcional; cobertura incompleta | Integração Senado/Câmara comprovada para PL 1604/2022; ainda não cobre todos os processos de todas as leis. |
| T25 — frescor e alertas | Atualização ativa; alertas incompletos | Há sincronização recorrente; faltam metas e alertas por fonte publicados ao usuário. |
| T26 — Railway | Saudável | Web, worker, Postgres, Redis e backup estão online; deploys atuais web/worker em `SUCCESS`. |
| T27 — documentação | Atualizada nesta execução | Este relatório registra métricas, comprovações e limites observados. |

## O que impede declarar “todas as leis completas”

1. Não existe um endpoint nacional único que enumere e entregue o texto consolidado de todas as leis federais, estaduais e municipais. O índice de 833.109 registros não prova cobertura nacional.
2. O backfill continua grande: 216.717 textos pendentes no catálogo do Senado e 601.723 na soma dos catálogos subnacionais integrados. Os dois números podem se sobrepor. O worker continua ativo e foi dimensionado para 24 jobs de texto simultâneos, mas isso não termina instantaneamente.
3. Quinhentos e onze registros do Senado e quatro do SINJ-DF estão marcados indisponíveis pela fonte integrada. Sem texto oficial publicado ou outro acesso autorizado, não há conteúdo legítimo para materializar.
4. O SRU do LexML devolveu desafio anti-bot em vez de resultados. É preciso uma rota autorizada, acesso concedido ou outra fonte oficial.
5. Muitos portais legislativos não SAPL ainda precisam de integração individual; 503 configurações candidatas SAPL também não foram confirmadas como catálogos ativos. Este trabalho é tecnicamente possível por adapters, mas exige localizar e validar cada fonte, e não se resolve por um download nacional.
6. Relações históricas nem sempre trazem duas redações, data de efeito e autoria completa. Sem esses dados, histórico textual, vigência passada e autoria por dispositivo não podem ser inferidos com segurança.

A pipeline, interface e APIs podem operar agora e as fontes integradas continuarão sendo colhidas. Declarar o corpus completo antes de acabar esses backfills, integrar os portais restantes e obter os textos ausentes seria uma afirmação falsa.
