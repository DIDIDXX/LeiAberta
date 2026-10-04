# Execução do plano LeiAberta — Luna 6

Atualizado em 04/10/2026. Base confirmada no GitHub: `main` em `5c0a80454838772588b340b401372524f57e19ab`. A nova entrega ainda está em validação local nesta revisão; o Railway continua no release anterior até o merge e o deploy serem confirmados.

## Trabalho concluído nesta revisão

Além do catálogo federal e do histórico do Senado já publicados, esta revisão integrou dois grandes acervos subnacionais, conectou suas fontes de texto/histórico e corrigiu a atualização de cobertura pelo sincronizador do IBGE.

| Acervo oficial | Registros enumerados | Paginação | Verificação | Texto e histórico |
|---|---:|---:|---|---|
| Senado Federal | 47.327 em seis categorias | 6 partições oficiais | Segunda sync sem duplicatas | Planalto, Normas.leg.br e fallback exato do DOU para RSF; relações e comparações quando os textos anterior/posterior existem. |
| ALESP — SP | 181.172 normas | 37 páginas de até 5.000 | Total da API igual ao importado; IDs sem repetição; checksum `06002b97a80ffcc82e91e2d033e35a690419c85a1f1c36bf97723c284f097035` | Texto oficial por identidade exata; anotações de alteração, revogação e metadados legislativos ligados ao histórico. |
| SINJ-DF | 125.478 normas | 26 páginas de até 5.000 | Total final igual ao importado; IDs sem repetição; checksum `c1d7ad6d4a1ed0b3c05ef0a0a1d5b2a2ea96559988c15271b2ac994610293af0` | HTML, PDF, PDF digitalizado com OCR português e DOCX; relações oficiais ligadas ao histórico. |

Os totais subnacionais vêm de sincronizações completas isoladas, não da produção Railway. O SINJ varia seus metadados entre consultas; no segundo snapshot completo, 120.294 de 125.478 registros declaravam ao menos um anexo, 1.242 incluíam PDF (139 também tinham HTML), três incluíam DOCX e 5.184 não declaravam arquivo textual. O suporte PDF/DOCX/OCR foi acrescentado para obter texto dos formatos efetivamente publicados, sem substituir o arquivo bruto arquivado. O parser mantém cobertura parcial até a auditoria documental passar.

Uma norma judicial SINJ-DF com PDF oficial atualizado foi buscada ao vivo. O download de 214.701 bytes foi preservado e extraído em 33.031 bytes de HTML de leitura. Também passaram testes de PDF textual, caminho OCR para página digitalizada e extração de parágrafos/tabelas DOCX. O container Railway instala Tesseract com idioma português para esse caminho.

O histórico agora usa adapters por fonte. ALESP publica 33 anotações de alteração para a Lei estadual 10.261/1968, além de uma proposição e autoria. SINJ-DF publica 103 relações incidentes no Decreto 36.222/2014. Esses dados são links e relações oficiais; não são apresentados como diff por dispositivo quando a fonte não fornece as duas redações.

Também foram incluídos: migration para números longos do catálogo SINJ; fila e catálogo independentes para SP/DF no worker; contadores de cobertura subnacional em `/api/stats`; proteção contra sincronização do IBGE apagar o estado de cobertura dos catálogos; fontes e fixtures oficiais versionadas.

## Estado do plano por tarefa

| Tarefas | Estado nesta revisão | Evidência / lacuna |
|---|---|---|
| T00 linha de base | concluído | GitHub, produção Railway, serviços, migrações, fonte e estatísticas foram identificados sem exportar segredos. |
| T01 backup restaurável e staging | bloqueio de infraestrutura da conta | O Railway Hobby informa `maxBackupsCount=0`; o conector não fornece shell/execução SQL/`pg_dump` nem duplicação restaurável. Não foi criado um backup nem feita migração não aditiva sem restore demonstrado. |
| T02 estados de job/cobertura | implementado | Busca, hidratação e histórico têm estados distintos; erros e ausência de texto não são mascarados por “preparando”. |
| T03 fila e recuperação | implementado | Outbox, Redis Streams, deduplicação, retomada e worker concorrente. |
| T04 arquivo bruto | implementado no código | Captura e checksum são gravados antes de parsear; migration `0006`. Deploy e produção precisam ser confirmados nesta revisão. |
| T05 identidade/parser | implementado nos formatos cobertos | Números, reedições, artigos, variantes e namespaces CF/ADCT; o parser continua conservador fora dos modelos cobertos. |
| T06 PDF, tabelas e anexos | PDF/OCR/DOCX implementado para SINJ-DF | PDF bruto é arquivado; texto extraído/OCR alimenta a leitura. Anexos sem link nos metadados oficiais continuam sem caminho automático. |
| T07 auditoria de completude | parcial | Auditoria estrutural existe, mas não certifica que um HTML/PDF contenha todos os anexos, notas ou texto juridicamente válido. |
| T08 leitor progressivo | parcial | Busca, dispositivo e progresso de job funcionam. Leitura de anexos em todos os formatos/famílias ainda depende de adapters adicionais. |
| T09 jurisdições e fontes | parcial | Diretório IBGE cobre 27 UFs e 5.571 localidades; catálogo normativo não está conectado a cada jurisdição. Registry de fontes mantém escopo e estado sem o IBGE sobrescrevê-los. |
| T10 sync retomável | implementado para Senado, ALESP e SINJ-DF | Páginas, checkpoints, totais, IDs, dedupe e janela de frescor. |
| T11 catálogo federal | parcial | Senado enumerou seis categorias; Câmara documenta tramitação, autoria e votação, mas falta catálogo federal reconciliado completo por Casa. |
| T12 LexML | bloqueio de acesso externo observado | A rota SRU respondeu desafio HTML anti-automação HTTP 200 no probe executado. Não há chave/rota autenticada nesta sessão. As integrações diretas continuam independentes. |
| T13 ALESP/SINJ-DF | implementado em código; deploy pendente de confirmação | Catálogos completos isolados, texto e histórico oficial integrados. Estatísticas públicas de produção serão atualizadas depois do deploy. |
| T14 SAPL/municípios | não concluído, sem impossibilidade demonstrada | Não existe endpoint oficial único e os hosts/schema/permissões variam. Continuar descoberta de portais e adapters; Campinas ainda não tem host SAPL comprovado. |
| T15 26 UFs e municípios | em andamento, incompleto | Somente ALESP/SP e SINJ-DF foram integrados entre as jurisdições subnacionais. Ainda não há denominador oficial nacional de leis por fonte/jurisdição. |
| T16 busca | implementado sobre catálogo armazenado | Após deploy e sync, verificar pesquisas reais em SP/DF e produção. A busca só pode encontrar registros presentes no corpus conectado. |
| T17 relações/histórico | implementado em adapters, cobertura parcial | Senado + Normas, ALESP e SINJ-DF publicam relações oficiais. Ausência de redação anterior/posterior mantém o evento pendente. |
| T18/T19 semântica temporal e reconstrução | parcial | Datas são preservadas por campo; nenhuma vigência por dispositivo é inventada quando as fontes não a demonstram. |
| T20 timeline/diff | implementado para evidência disponível | Comparação textual é exibida somente quando ambos os textos foram verificados. |
| T21 autoria/blame | parcial | Metadados ALESP incluem proposição/autoria, mas autoria de cada dispositivo e relações políticas completas não são inferidas. |
| T22 backfill histórico nacional | parcial | Texto federal é enfileirado em lotes; histórico de relações é sob demanda. Não foram criados centenas de milhares de jobs sem respeitar limites das fontes. |
| T23/T24 processo e votos | não concluído | APIs Câmara/Senado existem; vínculo confiável entre cada mudança normativa, proposição, emenda, autores e votos exige resolução adicional. |
| T25 scheduler/freshness | implementado parcialmente | Worker agenda atualizações dos três catálogos e IBGE, além dos textos federais. Faltam alertas/SLAs por jurisdição e métricas de cobertura em produção. |
| T26 release Railway | aguardando publicação desta revisão | Produção permanece no `main` `5c0a804` até merge. Smoke público, migrations, contagens SP/DF e histórico por fonte serão registrados após o deploy real. |
| T27 documentação | esta revisão atualiza evidências e lacunas | Este estado distingue medições isoladas de produção e não declara cobertura nacional completa. |

## Validação desta revisão

Após integrar com o último `main` e incluir as provas PDF/DOCX/OCR: `.venv/bin/pytest -q` passou com **71 testes**; `npm run test:e2e` passou com **4 casos**; `compileall` e `git diff --check` passaram. O leitor ao vivo do PDF SINJ-DF extraiu texto. A migration `0008` e o build/deploy Railway ainda precisam da validação pós-merge.

A migração `0008` amplia `Law.number` de 24 para 96 caracteres. O downgrade recusa truncar valores longos. Aplicar a migration e testar health, busca, hidratação e histórico na produção são passos pós-merge obrigatórios.

## Limites técnicos comprovados e trabalho restante

1. **Backup/restore Railway:** o plano atual não fornece backup de volume e as ferramentas Railway ligadas não permitem criar/validar cópia restaurável. É uma limitação do produto/plano/acesso desta sessão; uma operação de conta precisa habilitar mecanismo de backup ou execução de `pg_dump`/restore. As migrations desta entrega são aditivas.
2. **Enumeração nacional:** não foi demonstrada uma API nacional oficial que enumere todas as leis e redações das 27 UFs e 5.571 localidades. Isso não torna a integração impossível: exige inventário e adapters por portal, e continua sendo trabalho em aberto. Catálogos SP/DF não equivalem a cobertura nacional.
3. **Textos e anexos ausentes na fonte consultada:** 5.184 registros SINJ no snapshot não anunciavam anexo textual; o texto precisa ser procurado em diário oficial ou repositório alternativo. Outros fontes podem completar parte desse conjunto.
4. **Histórico sem redações/datas:** links de alteração não garantem texto antes/depois por dispositivo nem vigência. A UI marca esses eventos como relações sem comparação e a cobertura permanece `partial`.
5. **Classificação jurídica:** o Normas.leg.br rotula muitas compilações/transcrições como valor jurídico não oficial. O acervo oficial original ou uma certificação oficial tem de ser localizado; o LeiAberta não pode atribuir status jurídico que a fonte não declara.
6. **LexML SRU:** o endpoint testado respondeu uma página de desafio em vez de registros. A rota testada fica bloqueada até o portal disponibilizar acesso não desafiante ou documentação/autorização de integração.

Nenhum desses itens deve ser confundido com entrega nacional concluída. Também não se classificam como “impossibilidade técnica” os adapters ainda não construídos: eles seguem no backlog executável.
