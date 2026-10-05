# Execução do plano LeiAberta — Luna 6

Atualizado em 05/10/2026; contagens de produção coletadas às 01:16 UTC. O commit d258fcaf3acb9b7c46904b9423d68cc292f4fc1c está no main. Railway web deployment 6fa27e27-b3d1-486b-8ad5-902f8d61e452 e worker deployment c7d9fb3a-d44b-4713-95f6-604bbc964c30 estão em SUCCESS. /api/health responde 200; a migration 0008 está aplicada.

## Catálogos e backfill

| Fonte oficial | Catálogo | Estado confirmado | Texto / histórico |
|---|---:|---|---|
| Senado Federal | 47.316 | Seis categorias oficiais enumeradas | 3.299 textos, 203 indisponíveis na última tentativa, 43.814 pendentes e 4.679 jobs ativos. Os contadores mudam durante o backfill. |
| ALESP — SP | 181.172 | Completo: 37 páginas, 181.172 registros no banco | Texto por identidade oficial; 38 materializados na medição. Relações de alteração e revogação disponíveis. |
| SINJ-DF | 125.478 | Completo: 26 páginas, IDs reconciliados | HTML, PDF, OCR português e DOCX; 33 materializados na medição. Relações oficiais disponíveis. |
| SAPL — Manaus | 9.846 esperados | API, 12 tipos e identidade municipal conferidos. Sync de produção em andamento: 3.300/9.846, página 33/99 na medição. O banco preservava 8.000 registros de uma execução anterior. | PDF/OCR e relações do SAPL implementados. Uma lei municipal já tem texto materializado; o restante depende da sync e do backfill. |

O catálogo combinado tinha 361.980 normas indexadas, 3.385 textos estruturados, 24.029 dispositivos e 57 alterações documentadas. O worker executa oito hidratações concorrentes. A carga federal/subnacional continua em lotes limitados; catálogo completo não significa que todo texto já foi baixado nem que toda norma tenha anexo disponível.

A API oficial do SAPL Manaus publica 9.846 normas. A Lei 115/1949 foi conferida como PDF oficial, extraída e testada. A ALESP concluiu a enumeração de todos os 181.172 itens; o SINJ-DF tem 125.478 registros enumerados.

## Correção e prova do DOU

O DOU rotula resoluções senatoriais recentes como “Resolução”, embora preserve a hierarquia “Atos do Senado Federal”. O filtro anterior só aceitava “Resolução do Senado Federal” e rejeitava publicações válidas. O release atual permite o rótulo genérico apenas com hierarquia exata, página/data e identidade número/ano; verifica ainda a ementa integral do artigo.

Três publicações oficiais de 12/09/2024 foram baixadas e processadas ao vivo:

| Norma | Página do DOU | Dispositivos | Caracteres estruturados | Job em produção |
|---|---:|---:|---:|---|
| RSF 24/2024 | 4 | 27 | 4.443 | concluído |
| RSF 25/2024 | 5 | 27 | 5.221 | concluído |
| RSF 27/2024 | 5 | 25 | 4.181 | concluído |

O teste focal da classificação genérica passou localmente e cobre também o caso de hierarquia de outra instituição, que continua rejeitado.

O histórico da Lei Maria da Penha conclui em estado parcial, com 65 itens: 62 referências oficiais do Senado e 3 comparações textuais verificadas. As 62 referências sem os dois textos necessários permanecem sem diff. A API não deixa o histórico preso em “preparando”.

## Estado do plano por tarefa

| Tarefas | Estado | Evidência / lacuna |
|---|---|---|
| T00 linha de base | concluído | GitHub, Railway, serviços, fontes e migrações identificados. |
| T01 backup/restauração e staging | bloqueio de infraestrutura da conta | Railway Hobby informa maxBackupsCount=0; os conectores não permitem pg_dump/restore. Não houve backup restaurável nem cópia para staging. |
| T02 estados de job/cobertura | implementado | Estados distintos para busca, hidratação e histórico; falhas não ficam mascaradas como “preparando”. |
| T03 fila e recuperação | implementado | Outbox, Redis Streams, deduplicação e worker concorrente. |
| T04 arquivo bruto | implementado | Captura oficial, checksum e arquivo bruto antes da extração; migration 0006. |
| T05 identidade/parser | implementado nos formatos cobertos | Identidade oficial e dispositivos estruturados com parser conservador. |
| T06 PDF, tabelas e anexos | parcial por fonte | PDF/OCR/DOCX cobertos no SINJ e SAPL; anexo não publicado requer outra fonte oficial. |
| T07 auditoria de completude | parcial | Auditoria estrutural não certifica validade jurídica ou anexos ausentes. |
| T08 leitor progressivo | parcial | Busca, dispositivos e progresso funcionam; famílias e anexos adicionais dependem de adapters. |
| T09 jurisdições e fontes | parcial | Diretório IBGE lista 27 UFs e localidades; a maior parte dos portais ainda não tem adapter. |
| T10 sync retomável | implementado para Senado, ALESP, SINJ-DF e SAPL/Manaus | Totais, paginação, deduplicação e checkpoints por página; Manaus está terminando a enumeração. |
| T11 catálogo federal | parcial | Senado enumera seis categorias; falta reconciliar todo o acervo federal das Casas. |
| T12 LexML | bloqueio observado de acesso | Probe SRU recebeu desafio HTML anti-automação sem registros. Outras integrações oficiais continuam independentes. |
| T13 ALESP/SINJ-DF | enumeração concluída | ALESP 181.172 e SINJ-DF 125.478 gravados; backfill textual segue ativo. |
| T14 SAPL/municípios | Manaus integrado, sync em andamento | Fonte oficial enumera 9.846 normas; texto PDF e relações implementados. Outros municípios ainda precisam de adapters. |
| T15 demais UFs e municípios | incompleto; trabalho executável | Não há uma API nacional única. A ausência de integração não é impossibilidade técnica comprovada: cada acervo requer descoberta, adapter e reconciliação. |
| T16 busca | implementado sobre o catálogo armazenado | A busca cobre somente os registros presentes nas fontes conectadas. |
| T17 relações/histórico | implementado nas fontes cobertas; parcial em conteúdo | Senado, ALESP, SINJ-DF e SAPL; relações sem redações pareadas não recebem diff inventado. |
| T18/T19 semântica temporal e reconstrução | parcial | Não se infere vigência por dispositivo quando a fonte não a demonstra. |
| T20 timeline/diff | implementado quando há prova | Diff aparece somente quando os dois textos foram verificados. |
| T21 autoria/blame | parcial | Autoria de dispositivo e relações políticas completas não são inferidas. |
| T22 backfill histórico nacional | backfill de textos ativo; relações sob demanda | Contadores de 01:16 UTC: 3.299 textos federais, 38 ALESP, 33 SINJ-DF e 1 SAPL. A cobertura depende do anexo e da resposta de cada portal. |
| T23/T24 processo e votos | não concluído | Falta vínculo confiável entre mudanças, proposições, emendas, autores e votos. |
| T25 atualização/frescor | implementado parcialmente | Worker agenda os catálogos conectados e backfill; faltam alertas/SLA por jurisdição. |
| T26 publicação Railway | concluído para o release atual | Web e worker em SUCCESS, saúde 200 e hidratações DOU testadas ao vivo. |
| T27 documentação | este relatório atualizado | Separa resultado em produção, pendência de integração e bloqueio externo. |

## Validação local e produção

Nesta entrega, o teste focal de DOU passou (1 teste). A integração real com as três RSFs baixou 88.856–89.998 bytes por publicação e extraiu os dispositivos listados. Os três jobs em produção ficaram em succeeded, com 27, 27 e 25 artigos. A API de histórico da Lei Maria da Penha, /api/health e estatísticas de produção foram consultadas ao vivo. Uma execução de suíte mais ampla anterior havia passado 85 testes; essa contagem não substitui o teste focal desta correção.

A migration 0008 amplia Law.number de 24 para 96 caracteres; o downgrade recusa truncar valores longos. Não houve alteração de banco neste release.

## Limites externos e trabalho restante

1. **Cobertura nacional:** não foi demonstrado um endpoint oficial único que enumere o corpus legislativo de todas as jurisdições. Só estão conectados Senado, ALESP/SP, SINJ-DF e Manaus. Os outros acervos continuam trabalho de integração, não podem ser declarados impossíveis nem concluídos.
2. **Anexos ausentes no SINJ:** no snapshot pesquisado, 5.184 registros não anunciavam arquivo textual. Procurar diários e repositórios oficiais alternativos segue pendente.
3. **Histórico sem redações ou vigência:** referências oficiais podem não incluir os textos anterior/posterior ou a data de vigência por dispositivo; o produto mostra a referência, sem inventar diff.
4. **LexML SRU:** o probe observado recebeu HTML de desafio em vez de registros. Essa rota requer acesso utilizável ou documentação da interface.
5. **Classificação jurídica:** Normas.leg.br classifica certas transcrições e compilações como não oficiais; LeiAberta preserva a classificação da fonte.
6. **Backup Railway:** o plano Hobby informa maxBackupsCount=0, e as ferramentas conectadas não oferecem execução de pg_dump/restore para demonstrar recuperação.

As 203 normas federais indisponíveis na medição não são um conjunto de impossibilidades permanentes: falhas transitórias podem ser repetidas e novos adapters podem cobrir novas fontes. A indicação “indisponível” descreve o resultado registrado na tentativa mais recente.
