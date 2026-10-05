# Execução do plano LeiAberta — Luna 6

Atualizado em 05/10/2026 às 06:35 UTC, com leitura dos endpoints de produção. O código ativo é `main` no commit `9ebcb8ef64fffce38dcdfe0e56ae68b0f20032af`; Railway web e worker estão em `SUCCESS` nos deploys `04d247fc-28a5-4b9f-97cc-e8ad93e1decb` e `54b872be-eea9-43db-be81-d921d473ec59`. O PR de expansão seguinte ainda não foi publicado quando esta medição foi feita.

## Estado de produção

| Medida | Produção às 06:35 UTC |
|---|---:|
| Normas indexadas | 584.446 |
| Normas com texto estruturado | 11.402 |
| Dispositivos estruturados | 44.227 |
| Alterações documentadas | 376 |
| Jobs ativos | 5.106 |
| Senado: itens de catálogo | 170.607 |
| Senado: texto disponível / pendente | 8.935 / 161.404 |
| ALESP: itens / texto disponível | 181.172 / 1.247 |
| SINJ-DF: itens / texto disponível | 125.478 / 1.203 |

As contagens mudam enquanto os workers trabalham. “Pendente” significa que o texto ainda não foi materializado; pode haver anexo ausente ou indisponível na própria fonte.

### SAPL já carregado antes desta expansão

Na medição, a produção tinha 15 registros SAPL: 12 concluídos, dois falhos e um em sincronização. Fortaleza tinha 14.329/14.329; a sincronização de Pelotas avançava em 2.100/3.942. João Pessoa havia parado na página 90 por um HTTP 404 transitório. São João da Boa Vista havia parado por repetição do ID 9.231 entre páginas. O PR pendente corrige a ordenação para `o=id`, repete 404 limitadamente e retoma checkpoints confirmados; depois do deploy as duas fontes serão reprocessadas pelo worker.

## Histórico e texto

- `GET /api/laws/11340-2006/history` responde com 65 eventos: três comparações textuais verificadas e 62 relações oficiais sem redações suficientes para diff. O estado é `partial`, sem job ativo; a tela não fica presa em “está sendo preparado”.
- O histórico de onze outras leis-semente também já foi consultado e retorna `partial`; o CTN, a Constituição e a LAI estavam em nova tentativa/na fila na última verificação. O job da LAI 12.527/2011 foi registrado como `9c4f20d9-6aa1-453d-b037-780fd0cc0937`.
- A Lei SAPL 115/1949 foi processada com seis nós e quatro artigos extraídos. A auditoria de 241.460 caracteres da fonte a mantém em `review_required`; isso não certifica que o texto extraído reproduza o PDF integral.
- O backfill captura texto publicado e estrutura artigos quando a fonte disponibiliza documento legível. A relação oficial de alteração sem texto antigo e novo não basta para inventar um diff.

## Trabalho executado no próximo PR

- Acrescenta 312 fontes municipais SAPL após nova tentativa em 640 hosts que antes falhavam. 427 passaram a responder; 312 tinham API paginada válida, total positivo e host/cidade/UF coincidentes com o IBGE. A página inicial identificou explicitamente Câmara e município em 287; nos outros 25 o título era genérico ou a página estava indisponível, mas o hostname legislativo e a API conferida coincidem exatamente com o cadastro IBGE.
- Somadas às 246 inclusões do lote anterior, são 558 novas fontes municipais. Elas anunciam 1.169.606 registros nos snapshots; contagens de fontes podem se sobrepor e não constituem denominador nacional. O total de configurações passará a 581 municípios e oito assembleias SAPL estaduais.
- A sincronização SAPL passa a persistir hash e limites de cada página, conferir a página de fronteira ao retomar, verificar IDs numericamente crescentes dentro e entre páginas, rejeitar página truncada e repetir 404 transitório.
- O backfill subnacional alterna as fontes entre lotes quando há mais fontes do que vagas, evitando que os primeiros nomes do catálogo monopolizem a fila.
- Foi incluído um serviço de backup isolado para gerar `pg_dump` customizado, validar uma restauração local e enviar dump/manifesto para S3 compatível com checksum e retenção. O container de backup ainda precisa ser criado/configurado no Railway e sua execução restaurável precisa ser observada antes de marcar T01 como concluída.

## Verificações

- Suíte Python completa: 114 testes passaram, com três avisos de depreciação.
- Playwright local: os quatro fluxos E2E já passaram na revisão anterior (busca, diff verificado, hidratação e consulta ambígua).
- `py_compile` e `git diff --check` passaram.
- A primeira construção Docker local do container de backup bateu no certificado TLS de interceptação do ambiente ao baixar `boto3` do PyPI. É uma condição da rede de desenvolvimento; a construção Railway ainda precisa confirmar a imagem.

## Estado por tarefa

| Tarefa | Estado atual | Evidência e próximo passo |
|---|---|---|
| T00 — linha de base | concluído | Repositório, APIs, banco e serviços Railway inspecionados. |
| T01 — backup e restauração | em execução | Código do backup pronto; provisionar bucket e serviço agendado no Railway, fazer uma cópia e validar a restauração antes de configurar retenção diária. |
| T02 — estados de job e cobertura | implementado | Job persistido governa o estado; falha, espera e texto ausente não aparecem como preparo eterno. |
| T03 — fila durável | implementado | Outbox, Redis Streams, recuperação de mensagens e prioridade interativa. |
| T04 — proveniência | implementado para fontes integradas | Snapshot bruto, checksum e referência oficial são preservados. |
| T05 — identidade e parsing | implementado nos formatos cobertos | Dados ausentes não viram número, vigência ou status jurídico presumido. |
| T06 — PDF, OCR, DOCX e tabelas | parcial por fonte | Extração funciona nas fontes cobertas; portais sem anexo requerem outro repositório oficial. |
| T07 — auditoria de completude | parcial | Detecta divergências; não substitui revisão jurídica/documental. |
| T08 — leitor progressivo | implementado sobre os dados disponíveis | Busca, navegação, origem, histórico e estado do job funcionam; faltam documentos de fontes não integradas. |
| T09 — inventário territorial | diretório IBGE concluído; leis parciais | 27 UFs e 5.571 localidades são conhecidas; jurisdição conhecida não significa acervo legal importado. |
| T10 — sincronização retomável | parcial até o deploy deste PR | Os quatro adapters anteriores têm checkpoints; a mudança acrescenta retoma por página ao SAPL multi-instância. |
| T11 — catálogo federal | parcial | Senado lista 24 tipos no adapter e enumera classes em atualização; cobertura do Senado não prova que todo ato federal esteja representado. |
| T12 — LexML | acesso automatizado bloqueado nesta sessão | SRU devolveu página anti-automação em HTTP 200, não resultados. Seguir com fontes oficiais diretas e obter rota de colheita permitida. |
| T13 — ALESP e SINJ-DF | enumeração do snapshot concluída; texto em backfill | SP: 181.172; DF: 125.478. |
| T14 — SAPL/municípios | expansão publicada após merge pendente | 581 municípios configurados; API de cada fonte ainda será enumerada pelo worker. |
| T15 — demais UFs e municípios | trabalho de integração ativo | A lista descoberta não oferece denominador legislativo oficial; muitas Casas usam portais diferentes de SAPL. |
| T16 — busca | implementado sobre o catálogo indexado | Resultados fora do acervo importado não aparecem. |
| T17 — histórico | parcial e baseado em prova | Relações aparecem sem diff quando faltam textos comparáveis; Maria da Penha já retorna eventos e não fica em preparo. |
| T18/T19 — vigência e versões históricas | parcial | Não inferir vigência por dispositivo sem publicação, redação e data eficaz demonstráveis. |
| T20 — timeline/diff | parcial | Diff só aparece com as duas redações verificadas. |
| T21 — autoria por dispositivo | parcial | Autoria de alterações e cadeia política exigem ligar com segurança proposição, relatoria, emenda e dispositivo. |
| T22 — backfill de textos | ativo | Senado, ALESP, SINJ e SAPL continuam em lotes; priorização e alternância reduzem starvation, mas anexos dependem dos portais. |
| T23/T24 — proposições, emendas e votos | não concluído | Requer um adapter oficial da Câmara e reconciliação independente de IDs entre Casas. |
| T25 — frescor/alertas | parcial | Há refresh periódico; ainda faltam alertas e metas de frescor por fonte. |
| T26 — Railway | saudável | Web e worker em SUCCESS e endpoints públicos respondendo. |
| T27 — documentação | em atualização | Este relatório e o inventário de fontes serão atualizados após deploy e medição. |

## Limites que dependem de terceiros ou de evidência

1. O plano Hobby não oferece backup gerenciado; será substituído por cópia própria ao bucket Railway, mas a restauração ainda tem de ser executada e observada.
2. O endpoint SRU consultado no LexML bloqueou automação com desafio HTML. Não se tentou contornar a proteção.
3. Alguns registros SINJ, Senado ou municipais não têm texto/anexo disponível na API. A lacuna só fecha com publicação em outro acervo oficial.
4. Relações sem versões anterior/posterior ou data de eficácia não permitem reconstrução histórica completa; o sistema publica a relação e marca a comparação ausente.
5. Não foi demonstrado um endpoint nacional único com o conjunto de normas de todas as Casas. 581 municípios e nove estados mais o DF têm pelo menos uma fonte conectada após a expansão; o restante ainda requer pesquisa e integração. Isso é trabalho incompleto, não impossibilidade técnica comprovada.

O sistema ainda não contém “todas as leis”. A medição atual tem 584.446 registros indexados e 11.402 com texto estruturado; o total também não é um denominador nacional. O próximo marco verificável é publicar as novas fontes, confirmar contagens por instalação, concluir a cópia/restauração no Railway e manter o backfill ativo sem classificar lacunas como cobertura completa.
