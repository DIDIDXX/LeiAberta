# Execução do plano LeiAberta — Luna 6

Atualizado em 05/10/2026. O release #7 está no `main` (`21e5fda147508dd20882ae475b9ad50ab6c9d066`) e em produção Railway. Os serviços web e worker chegaram a `SUCCESS`; o health endpoint responde 200 e a migration `0008` está aplicada. A branch desta revisão acrescenta SAPL/Manaus, backfill gradual de textos subnacionais e retry para falhas transitórias do Senado/DOU; esse incremento ainda aguarda publicação.

## Trabalho concluído nesta revisão

O release #7 integrou ALESP e SINJ-DF em produção. Esta revisão acrescenta SAPL/Manaus, conecta o texto PDF oficial e relações do SAPL, agenda backfill limitado dos anexos textuais declarados e repete falhas temporárias de rede com atraso curto.

| Acervo oficial | Registros enumerados | Paginação | Verificação | Texto e histórico |
|---|---:|---:|---|---|
| Senado Federal | 47.316 em produção; validação local anterior encontrou 47.327 | 6 categorias oficiais | Catálogo listado em produção | Planalto, Normas.leg.br e fallback exato do DOU para RSF; relações e comparações quando os textos anterior/posterior existem. A produção está fazendo backfill; última leitura: 2.831 com texto, 397 jobs ativos. |
| ALESP — SP | API declara 181.172; 120.000 em produção na última leitura | 37 páginas de até 5.000 | Sync de produção ainda em curso; validação isolada completa igualou o total, IDs sem repetição, checksum `06002b97a80ffcc82e91e2d033e35a690419c85a1f1c36bf97723c284f097035` | Texto oficial por identidade exata; anotações de alteração, revogação e metadados legislativos ligados ao histórico. Backfill automático entra no próximo release. |
| SINJ-DF | 125.478 em produção e na validação isolada | 26 páginas de até 5.000 | Total e IDs completos; checksum `c1d7ad6d4a1ed0b3c05ef0a0a1d5b2a2ea96559988c15271b2ac994610293af0` | HTML, PDF, PDF digitalizado com OCR português e DOCX; relações oficiais ligadas ao histórico. Backfill automático entra no próximo release. |
| SAPL — Câmara Municipal de Manaus | API declara 9.846 | 99 páginas de 100 | API, identidade municipal, 12 tipos e PDF da Lei 115/1949 validados ao vivo; sincronização de produção ainda não iniciada | Adapter local implementado para catálogo, PDF/OCR, relações e job persistido; publicação e sync seguem nesta revisão. |

As contagens ALESP/SINJ acima vêm de produção e de validação isolada, com diferenças de snapshot já identificadas. O SINJ varia seus metadados entre consultas; no segundo snapshot completo, 120.294 de 125.478 registros declaravam ao menos um anexo, 1.242 incluíam PDF (139 também tinham HTML), três incluíam DOCX e 5.184 não declaravam arquivo textual. O suporte PDF/DOCX/OCR obtém texto dos formatos publicados e preserva o arquivo bruto. O parser mantém cobertura parcial até a auditoria documental passar.

Uma norma judicial SINJ-DF com PDF oficial atualizado foi buscada ao vivo. O download de 214.701 bytes foi preservado e extraído em 33.031 bytes de HTML de leitura. Também passaram testes de PDF textual, caminho OCR para página digitalizada e extração de parágrafos/tabelas DOCX. O container Railway instala Tesseract com idioma português para esse caminho.

O histórico agora usa adapters por fonte. ALESP publica 33 anotações de alteração para a Lei estadual 10.261/1968, além de uma proposição e autoria. SINJ-DF publica 103 relações incidentes no Decreto 36.222/2014. Esses dados são links e relações oficiais; não são apresentados como diff por dispositivo quando a fonte não fornece as duas redações.

O release #7 também incluiu: migration para números longos do catálogo SINJ; fila e catálogo independentes para SP/DF no worker; contadores de cobertura em `/api/stats`; proteção contra o IBGE apagar estados de cobertura; fontes e fixtures oficiais versionadas. A branch atual acrescenta o registro municipal de Manaus e backfill federado/subnacional em lotes limitados.

## Estado do plano por tarefa

| Tarefas | Estado nesta revisão | Evidência / lacuna |
|---|---|---|
| T00 linha de base | concluído | GitHub, produção Railway, serviços, migrações, fonte e estatísticas foram identificados sem exportar segredos. |
| T01 backup restaurável e staging | bloqueio de infraestrutura da conta | O Railway Hobby informa `maxBackupsCount=0`; o conector desta sessão não fornece shell/execução SQL/`pg_dump` nem duplicação restaurável. Não foi criado um backup nem feita migração não aditiva sem restore demonstrado. |
| T02 estados de job/cobertura | implementado | Busca, hidratação e histórico têm estados distintos; erros e ausência de texto não são mascarados por “preparando”. |
| T03 fila e recuperação | implementado | Outbox, Redis Streams, deduplicação, retomada e worker concorrente. |
| T04 arquivo bruto | implementado no código | Captura e checksum são gravados antes de parsear; migration `0006`. Deploy e produção precisam ser confirmados nesta revisão. |
| T05 identidade/parser | implementado nos formatos cobertos | Números, reedições, artigos, variantes e namespaces CF/ADCT; o parser continua conservador fora dos modelos cobertos. |
| T06 PDF, tabelas e anexos | PDF/OCR/DOCX implementado para SINJ-DF | PDF bruto é arquivado; texto extraído/OCR alimenta a leitura. Anexos sem link nos metadados oficiais continuam sem caminho automático. |
| T07 auditoria de completude | parcial | Auditoria estrutural existe, mas não certifica que um HTML/PDF contenha todos os anexos, notas ou texto juridicamente válido. |
| T08 leitor progressivo | parcial | Busca, dispositivo e progresso de job funcionam. Leitura de anexos em todos os formatos/famílias ainda depende de adapters adicionais. |
| T09 jurisdições e fontes | parcial | Diretório IBGE cobre 27 UFs e 5.571 localidades; catálogo normativo não está conectado a cada jurisdição. Registry de fontes mantém escopo e estado sem o IBGE sobrescrevê-los. |
| T10 sync retomável | implementado para Senado, ALESP, SINJ-DF e SAPL/Manaus | Páginas, checkpoints, totais, IDs, dedupe e janela de frescor. A sync ALESP de produção está em 120 mil/181.172. |
| T11 catálogo federal | parcial | Senado enumerou seis categorias; Câmara documenta tramitação, autoria e votação, mas falta catálogo federal reconciliado completo por Casa. |
| T12 LexML | bloqueio de acesso externo observado | A rota SRU respondeu desafio HTML anti-automação HTTP 200 no probe executado. Não há chave/rota autenticada nesta sessão. As integrações diretas continuam independentes. |
| T13 ALESP/SINJ-DF | release #7 implantado; sync ALESP em curso | DF completo em produção com 125.478. ALESP registrava 120.000/181.172 na última leitura; validação isolada já completou os 181.172. |
| T14 SAPL/municípios | adapter Manaus validado localmente; produção aguarda release #8 | API SAPL oficial da Câmara Municipal de Manaus enumera 9.846 normas, 12 tipos e publica texto PDF. Campinas continua não comprovada; não foi tratada como fonte. |
| T15 26 UFs e municípios | em andamento, incompleto | Somente ALESP/SP e SINJ-DF foram integrados entre as jurisdições subnacionais. Ainda não há denominador oficial nacional de leis por fonte/jurisdição. |
| T16 busca | implementado sobre catálogo armazenado | Após deploy e sync, verificar pesquisas reais em SP/DF e produção. A busca só pode encontrar registros presentes no corpus conectado. |
| T17 relações/histórico | implementado em adapters, cobertura parcial | Senado + Normas, ALESP, SINJ-DF e SAPL/Manaus expõem relações. Ausência de redação anterior/posterior mantém o evento como referência oficial sem diff. Retry curto foi adicionado após 503/queda transitória no Senado/DOU. |
| T18/T19 semântica temporal e reconstrução | parcial | Datas são preservadas por campo; nenhuma vigência por dispositivo é inventada quando as fontes não a demonstram. |
| T20 timeline/diff | implementado para evidência disponível | Comparação textual é exibida somente quando ambos os textos foram verificados. |
| T21 autoria/blame | parcial | Metadados ALESP incluem proposição/autoria, mas autoria de cada dispositivo e relações políticas completas não são inferidas. |
| T22 backfill histórico nacional | backfill de texto automático em release #8; histórico de relações continua sob demanda | A produção atual tem 2.831 dos 47.316 textos federais materializados e ainda não iniciou os textos subnacionais. O próximo release enfileira anexos que as fontes publicam, com limite de 100 a cada 5 minutos; o ritmo de conclusão depende das fontes e da fila. Relações/histórico são coletados quando solicitados para evitar chamadas sem limite. |
| T23/T24 processo e votos | não concluído | APIs Câmara/Senado existem; vínculo confiável entre cada mudança normativa, proposição, emenda, autores e votos exige resolução adicional. |
| T25 scheduler/freshness | implementado parcialmente | Worker agenda catálogos IBGE, Senado, ALESP, SINJ-DF e SAPL/Manaus, além de lotes federais. Faltam alertas/SLAs por jurisdição. |
| T26 release Railway | release #7 confirmado; release #8 aguardando publicação | Web e worker do release #7 chegaram a `SUCCESS`; `/health` 200 e migration `0008` aplicada. O próximo deploy será verificado após merge do adapter Manaus e backfill. |
| T27 documentação | esta revisão atualiza evidências e lacunas | Este estado distingue medições isoladas de produção e não declara cobertura nacional completa. |

## Validação local e produção

Após integrar o último `main`, `.venv/bin/pytest -q` passou com **80 testes**; `npm run test:e2e` passou com **4 casos**; `compileall` e `git diff --check` passaram. O E2E primeiro capturou HTTP 503 temporário do Senado e o job permaneceu `queued`; após retry curto, a mesma jornada terminou e exibiu o diff oficial com 62 relações. A API SAPL foi consultada ao vivo; a Lei 115/1949 (PDF de 439.668 bytes) foi baixada e extraída em 2.161 bytes de texto. Release #8 ainda requer merge e verificação no Railway.

A migração `0008` amplia `Law.number` de 24 para 96 caracteres. O downgrade recusa truncar valores longos. Aplicar a migration e testar health, busca, hidratação e histórico na produção são passos pós-merge obrigatórios.

## Limites técnicos comprovados e trabalho restante

1. **Backup/restore Railway:** Hobby informa `maxBackupsCount=0`, e as ferramentas conectadas não permitem criar/validar backup restaurável nem executar `pg_dump`/restore. As migrations aplicadas são aditivas; produção não foi copiada para staging.
2. **Cobertura nacional:** os portais brasileiros publicam seus próprios catálogos, sem um endpoint nacional oficial que enumere todas as leis e redações das 27 UFs e 5.571 municípios. Os acervos fora dos conectados ainda exigem adapters específicos, portanto o corpus não pode ser declarado nacionalmente completo.
3. **Textos não anexados no SINJ:** 5.184 registros observados não anunciavam anexo. O adapter só obtém os arquivos publicados no registro; falta provar e implementar fontes oficiais alternativas para cada item.
4. **Histórico sem redações/datas:** relações registradas por Senado, ALESP, SINJ ou SAPL não garantem texto antes/depois por dispositivo nem vigência. A UI apresenta a relação sem inventar um diff.
5. **Acesso intermitente a fontes públicas:** o leitor do DOU encerrou conexões em jobs de produção e o E2E observou HTTP 503 do Senado. Há retry curto; quando o próprio host não responde, o texto/histórico daquele documento não pode ser obtido até a fonte voltar.
6. **LexML SRU:** a rota probe respondeu HTML de desafio anti-automação, sem registros. Essa interface fica bloqueada até haver acesso não desafiante ou documentação/autorização de integração.
7. **Classificação jurídica:** Normas.leg.br classifica algumas compilações/transcrições como valor jurídico não oficial. O LeiAberta conserva a classificação da fonte e não pode atribuir valor jurídico que ela não declara.

Nenhum desses itens deve ser confundido com entrega nacional concluída. Também não se classificam como “impossibilidade técnica” os adapters ainda não construídos: eles seguem no backlog executável.
