# LeiAberta — plano completo de execução para Luna 6

Data da investigação: 04/10/2026. Responsável pela execução: Luna 6.
Repositório: https://github.com/DIDIDXX/LeiAberta.
Base auditada: `16c78fe888b3507409dbfda0dc951f06d28e0d50`.
Produção existente: https://web-production-12e95.up.railway.app.

## 1. Missão e resultado exigido

Transformar o MVP em um acervo nacional utilizável: encontrar normas de todas as jurisdições, abrir o texto integral, navegar dispositivos, consultar versões históricas comprovadas, comparar alterações e seguir a origem oficial. Implementar os fluxos completos; retirar mensagens que prometem processamento inexistente. Usar o Railway existente.

Este documento é um plano de implementação, não um relatório de funcionalidades já entregues. Os módulos, comandos e endpoints identificados como **novos** precisam ser implementados antes de serem usados. Os achados do código e os resultados de pesquisa são fatos observados; as escolhas de arquitetura abaixo são propostas concretas para execução.

### 1.1 O que significa “TODAS”

O catálogo de 14 normas não é o produto final. Remover qualquer teto artificial, filtro apenas de normas famosas ou exigência de inclusão manual no `CATALOG`. Fazer descoberta, catalogação, ingestão integral e atualização contínuas de todos os atos normativos encontrados nos acervos oficiais integrados, inclusive revogados e históricos.

Abranger União, 26 estados, DF e localidades municipais do cadastro oficial atualizado. Incluir constituições, leis orgânicas, leis ordinárias/complementares/delegadas, emendas, decretos/decretos-leis, medidas provisórias, decretos legislativos, resoluções e outros atos normativos presentes nos acervos. Classificar tipos e deixar o usuário filtrar; não excluir documentos sem número ou de períodos antigos. Proposições são outra entidade, vinculada às normas quando houver evidência.

Separar quatro entregas mensuráveis:

1. **Inventário territorial:** cada jurisdição tem registro, fontes descobertas, estado de integração e lacunas.
2. **Catálogo:** cada registro enumerado pelas fontes integradas entra no banco, com identidade, metadados e referências.
3. **Texto integral:** cada documento acessível e seus anexos são arquivados e apresentados sem perdas; a estrutura só recebe selo completo depois de auditoria.
4. **Histórico:** cada intervalo declarado reconstruído tem texto inicial e cadeia de alterações verificados. Intervalos desconhecidos permanecem explicitamente desconhecidos.

Não existe, na pesquisa realizada, uma API única demonstrada que garanta todas as leis brasileiras e todas as redações históricas. A meta é nacional e integral; a execução precisa publicar o denominador, os acervos percorridos e o saldo de lacunas. “100% dos registros enumerados de uma fonte” não equivale a “100% das leis do Brasil”. Não preencher documentos ausentes com conteúdo gerado. Não encerrar o projeto na fase piloto: continuar os lotes nacionais e apresentar bloqueios externos individualmente.

### 1.2 Invariantes obrigatórios

- Cada afirmação jurídica tem documento oficial e localização de evidência.
- Data de assinatura, publicação, início de vigência e coleta são campos diferentes.
- Texto baixado não implica texto completo; texto completo não implica estrutura completa; estrutura completa não implica histórico completo.
- Nenhuma versão ou fonte arquivada é apagada durante reprocessamento.
- Nenhum job é anunciado como em execução sem registro persistido e progresso verificável.
- Falha de atualização mantém a última versão validada disponível, com aviso de desatualização.
- Histórico parcial pode mostrar eventos comprovados; não pode apresentar redação integral por data em intervalo não comprovado.
- “Sem alterações” só é permitido para intervalo efetivamente verificado. “Não encontramos alterações” significa investigação incompleta.
- Conteúdo jurídico não é reescrito por LLM. LLM pode auxiliar triagem, nunca substituir evidência ou validar sozinho uma operação histórica.
- Autoria de projeto, relatoria, sanção, autoria de emenda e origem de dispositivo são relações distintas.
- Todas as entregas devem funcionar via API, interface, jobs e produção, com evidência de conclusão.

## 2. Diagnóstico da base atual

### 2.1 Falhas prioritárias confirmadas

| Prioridade | Local atual | Achado | Consequência / ação |
|---|---|---|---|
| P0 | `static/app.js`, `renderHistory` | Lista vazia sempre vira “O histórico está sendo preparado”. Não há pipeline genérico de histórico. | Corrigir estado e implementar job próprio; não basta trocar a frase. |
| P0 | `app/jobs.py`, `_verified_lmp_changes`; `app/catalog.py`, `AMENDING_LAWS` | Só há regras especiais para três acréscimos da LMP pela Lei 14.550/2023. | Substituir por descoberta e reconstrução genéricas, mantendo os exemplos como fixtures reais. |
| P0 | `app/sources/planalto.py`, `ARTICLE_RE` | Numeração como `Art. 1.000` não é reconhecida como artigo 1000. | Corrigir identificação, preservar número e impedir colisões. |
| P0 | Mesmo parser, `add` | IDs repetidos concatenam textos sem denunciar conflito. | Distinguir escopos e variantes; duplicata conflitante bloqueia publicação. |
| P0 | Mesmo parser | Remove texto riscado antes de preservá-lo semanticamente; remove pontuação com `.strip(" ... .;")`. | Arquivar marcação e texto original; separar redações; preservar pontuação legislativa. |
| P0 | Mesmo parser | Não representa livros/títulos/capítulos/seções, anexos, tabelas e componentes constitucionais. | Representação documental integral e namespaces por componente. |
| P0 | `app/jobs.py` | Qualquer lista não vazia de nós pode marcar norma `ready`. | Auditoria de completude obrigatória antes da troca da versão pública. |
| P0 | `app/models.py`, `Law.status` | Situação jurídica nasce como “Em vigor”, sem evidência. | Migrar para desconhecida quando não comprovada; importar situação oficial e fonte. |
| P0 | `app/catalog.py` | 14 registros federais fixos. | Catálogo nacional sincronizado e resolução de normas fora da lista. |
| P1 | `app/search.py` | Carrega catálogo em Python, faz consultas por norma e busca artigos em versões não necessariamente atuais. | Busca SQL indexada, paginação e filtro de versão. |
| P1 | `static/app.js`, `navigateSearch` | Enter pode navegar ao primeiro resultado em consulta ambígua. | Tela de candidatos; abrir diretamente somente resolução inequívoca. |
| P1 | `app/worker.py` | Redis BLPOP remove trabalho antes de processá-lo; não há ACK/lease/recuperação. | Fila durável, idempotência, retomada e reaper. |
| P1 | `app/jobs.py` | Verificação de job ativo sem garantia transacional; fallback de thread local; pronto não permite refresh real. | Deduplicação no banco, refresh explícito e execução somente por worker em produção. |
| P1 | `app/jobs.py`, `LawVersion` | Reprocessamento de parser pode substituir nós da mesma versão. | Nova representação imutável e promoção atômica após validação. |
| P1 | `SourceSnapshot` | Fonte bruta só é gravada no caminho de parsing bem sucedido e depende de versão. | Arquivo de fonte independente, inclusive falha de parsing. |
| P1 | `static/app.js` | Leitor carrega todos os nós; rota de artigo só rola o documento. | Leitura por dispositivo, sumário e carregamento progressivo. |
| P1 | `README.md` | Roadmap ainda pede E2E já existente; descrição não explicita falhas de completude. | Atualizar documentação conforme validações reais. |

### 2.2 Evidência concreta de texto incompleto

Em 04/10/2026 foi baixado o Código Civil diretamente do Planalto e aplicado o parser atual:

- Fonte: https://www.planalto.gov.br/ccivil_03/leis/2002/L10406compilada.htm.
- HTML recebido: 923.899 bytes nessa coleta.
- Artigos extraídos: **1.007**.
- O documento oficial contém referência textual ao **Art. 2.046**.
- `art:1` resultou em **174.903 caracteres**, evidência de concatenação indevida.
- Os últimos nós incluíam Art. 999 e Art. 1337; a sequência posterior não foi corretamente representada.

Isto prova que o contador atual de artigos e o status `ready` não asseguram texto estruturado completo. Não usar “2046 artigos” como regra cega: existem dispositivos acrescidos, revogados e variantes. A validação correta compara inventário do documento, escopos e conteúdo preservado.

Na Constituição, o documento contém ADCT, enquanto os IDs atuais são `art:n` sem escopo. Art. 1 da Constituição e Art. 1 do ADCT não podem compartilhar identidade. Na LC 135/2010, distinguir dispositivos da própria LC das redações da LC 64/1990 citadas dentro dela.

### 2.3 Estado técnico a preservar

FastAPI + SQLAlchemy + Alembic + PostgreSQL + Redis + Docker; interface em HTML/CSS/JS. Não há necessidade demonstrada de reescrever em Next.js para cumprir a missão. Evoluir essa base com separação de módulos e contratos. Reavaliar framework apenas se uma limitação medida exigir.

As contagens anteriores de 14 normas, 3.786 nós de artigo e três alterações documentadas são observações do MVP, não certificados de integridade. Recapturar a linha de base antes de mudar produção. A suíte existente tem testes de unidade/API e E2E; ampliar pelos casos abaixo, sem interpretar uma suíte pequena verde como garantia jurídica.

## 3. Pesquisa de fontes e caminhos de implementação

O relatório complementar `research/2026-10-04-source-findings.json` registra URLs, resultados e limitações. Revalidar documentação na execução: APIs e portais podem mudar.

### 3.1 Senado: catálogo, relações normativas e processos

Documentação oficial:

- https://legis.senado.leg.br/dadosabertos/docs/
- OpenAPI confirmado: https://legis.senado.leg.br/dadosabertos/v3/api-docs.
- Configuração Swagger: https://legis.senado.leg.br/dadosabertos/v3/api-docs/swagger-config.

Rotas encontradas na especificação atual:

```text
GET /dadosabertos/legislacao/tiposNorma
GET /dadosabertos/legislacao/lista
GET /dadosabertos/legislacao/{tipo}/{numdata}/{anoseq}
GET /dadosabertos/legislacao/{codigo}
GET /dadosabertos/legislacao/urn?urn=...
GET /dadosabertos/processo
GET /dadosabertos/processo/{id}
GET /dadosabertos/processo/documento
GET /dadosabertos/processo/emenda
GET /dadosabertos/processo/relatoria
GET /dadosabertos/votacao
```

Não usar a rota suposta `/norma/pesquisa/lista`: ela retornou 404. Muitas rotas antigas de `/materia` estão marcadas deprecated. Preferir `/processo` e registrar fallback legado apenas quando indispensável e testado.

Requisições confirmadas:

1. `https://legis.senado.leg.br/dadosabertos/legislacao/LEI/13709/2018` retorna XML, HTTP 200. Na coleta, 96.602 bytes, com identificação, URN, publicações, vínculos e declarações por dispositivo.
2. `https://legis.senado.leg.br/dadosabertos/legislacao/lista?tipo=LEI&numero=14550&ano=2023` retorna a Lei 14.550/2023 em XML.
3. Consulta de processo por número/ano retornou PL 1604/2022, `id=8272922`, `codigoMateria=153558`, `normaGerada=Lei nº 14.550 de 19/04/2023`. Na execução usar o parâmetro documentado `sigla=PL`; não assumir que parâmetro desconhecido `tipo=PL` filtra o resultado.

O XML da LGPD já contém relações de alterações permanentes/provisórias, revogações, vetos e referências a dispositivos. Há relações recentes até 2026. Portanto, não congelar a implementação em exemplos de 2019. Esses metadados são uma base excelente para descobrir eventos, mas **não são automaticamente o texto antes/depois nem a comprovação da vigência**. Baixar os documentos ligados, conferir dispositivo, publicação e regra temporal.

Implementação: parser XML seguro, schemas internos tipados, persistência de IDs externos, extração de `publicacoes`, `vides` e relações por dispositivo; resolver URLs oficiais vinculadas. Validar os nomes reais das tags e lidar com campos opcionais/duplicados. Não usar regex genérica em XML.

Para enumeração nacional federal, testar limites da rota `lista` antes de assumir paginação. Enumerar tipos e períodos documentados; salvar contagens por partição. Se resposta estiver truncada, subdividir períodos ou recorrer a exportação oficial. `numero` é inteiro na API, mas a identidade interna deve suportar atos sem número e reedições.

### 3.2 Câmara: textos originais, fichas e tramitação

Fontes oficiais confirmadas:

- Pesquisa: https://www.camara.leg.br/legislacao.
- Formulário: https://www.camara.leg.br/legislacao/pesquisa-avancada.
- Ação observada no formulário: `GET https://www.camara.leg.br/legislacao/busca`.
- Parâmetros observados: `abrangencia`, `tipo`, `numero`, `ano`, `geral`, `dataInicio`, `dataFim`, `origem`, `situacao`.
- A busca mostra paginação `pagina` e exportação **limitada a 300 documentos**. Percorrer páginas/partições; uma única exportação não prova cobertura.
- Dados abertos para proposições: https://dadosabertos.camara.leg.br/swagger/api.html.

Ficha confirmada por descoberta na busca, não por ID adivinhado:

https://www2.camara.leg.br/legin/fed/lei/2023/lei-14550-19-abril-2023-794072-norma-pl.html

Ela declara:

- Proposição originária: **PL 1604/2022**.
- Publicação original: **DOU, Seção 1, 20/04/2023, página 1**.
- Situação: **“Não consta revogação expressa”**, que não deve virar automaticamente “Em vigor”.
- Link relativo para o texto da publicação original: `lei-14550-19-abril-2023-794072-publicacaooriginal-167635-pl.html`.

O catálogo atual usa 19/04/2023 em campo chamado `published_at`; essa é a data de assinatura da norma, enquanto a ficha informa publicação em 20/04. Auditar todos os campos semelhantes e revalidar a data de eficácia das três alterações existentes.

Fluxo: descoberta da norma → ficha → texto original/publicações/retificações → vínculo explícito com proposição → resolver ID da proposição por tipo+número+ano+Casa → endpoints de detalhes, autores, tramitações, relacionados, votações e votos descritos na documentação vigente. Validar URLs com fixtures reais antes de implementar.

Não pesquisar `numero=14550&ano=2023` em `/proposicoes` para encontrar a origem da Lei 14.550. Essa consulta retornou lista vazia; número de lei e número de PL não são intercambiáveis. Não associar matérias das duas Casas apenas por coincidência de número/ano.

### 3.3 Planalto: texto original e consolidado

Manter o adapter, reconstruindo a extração. URLs já verificadas em `app/catalog.py` são sementes de regressão. Descobrir variantes original/compilada e atos modificadores por links oficiais; não supor que trocar sufixo da URL sempre funciona.

Texto compilado serve para leitura atual e reconciliação; publicação original serve de base histórica. HTML pode trazer redações riscadas, notas, dispositivos citados, tabelas e anexos externos. Arquivar tudo antes de parsear. A presença de `<html>` não prova que é uma norma: páginas de erro e bloqueio também são HTML.

Preservar texto oficial e exibir a data de consulta. Não transformar a data de coleta em data legal da redação. Guardar HTTP headers úteis, charset, redirects, checksum bruto e resultado da validação documental.

### 3.4 LexML: descoberta nacional e identificadores

Fontes:

- https://www.lexml.gov.br/
- https://www.lexml.gov.br/desc_acervo.html
- Pesquisa avançada: https://www.lexml.gov.br/busca/search?smode=advanced.

O acervo consultado lista provedores federais, estaduais, distrital e municipais; Campinas consta entre eles. Também lista jurisprudência e doutrina: filtrar a classe documental normativa e preservar identificadores de origem. Quantidade de documentos/links de um provedor não é quantidade de leis únicas.

A tentativa de SRU em `/busca/SRU` retornou HTTP 200 com **página de verificação de segurança do Senado**, não XML de resultados. A documentação de projeto redirecionou para login. Consequências:

- Não tratar HTTP 200 como sucesso do adapter.
- Não presumir que o SRU está utilizável nesta infraestrutura.
- Confirmar protocolo oficial de exportação/colheita e permissões de acesso antes de automatizar.
- Usar fontes diretas como caminho paralelo; LexML não pode ser dependência única do catálogo.
- Se necessário acesso institucional/credencial, abrir um bloqueio específico e seguir ingestão das demais fontes.
- Não contornar CAPTCHA ou apresentar resultado fabricado para ocultar indisponibilidade.

URN LexML pode ajudar deduplicação e ligação de referências; não é garantia universal de presença, identidade perfeita nem texto integral. Provedores diferentes podem descrever o mesmo ato; preservar equivalências e conflitos.

### 3.5 Diário Oficial e INLABS

https://inlabs.in.gov.br/ redireciona para `/acessar.php`; acesso exige cadastro/login. O portal informa XML de dados abertos e ressalva que esse formato não substitui a publicação certificada.

Implementar adapter opcional com credenciais externas, nunca no repositório. Confirmar documentação de download, abrangência temporal, edição extra, seção, retificações e disponibilidade real. Guardar referência para a edição certificada; XML auxilia processamento. Para períodos não cobertos, usar publicação original da Câmara, arquivo oficial do DOU ou outro acervo oficial demonstrado. Não supor que INLABS possui todo o passado.

### 3.6 Estados e DF

Pilotos oficiais respondendo HTTP 200 nesta pesquisa:

- ALESP: https://www.al.sp.gov.br/norma/ — portal de legislação estadual, pesquisa e coletâneas.
- SINJ-DF: https://www.sinj.df.gov.br/sinj/ — pesquisa de normas/diários, histórico e texto.

Ainda não foi demonstrado contrato de API completo desses portais. Investigar formulário, links de resultados, documentos e eventual exportação; produzir fixture real e validar paginação antes de declarar adapter pronto. Não inferir endpoint por nome de arquivo JavaScript.

Depois dos pilotos, implementar cadastro e fonte validada para **cada um dos 26 estados e o DF**. Fontes complementares: assembleia, executivo e diário oficial. Cada fonte recebe alcance por tipo, período, órgão e qualidade. Se um portal não traz originais/anexos, procurar outro oficial para complementar. Um adapter estadual em São Paulo não significa cobertura estadual nacional.

### 3.7 Municípios e SAPL

Base territorial oficial:

- https://servicodados.ibge.gov.br/api/docs/localidades.
- https://servicodados.ibge.gov.br/api/v1/localidades/estados.
- https://servicodados.ibge.gov.br/api/v1/localidades/municipios.

A última rota retornou **5.571 registros** em 04/10/2026. Importar dinamicamente; não fixar 5.570. O cadastro de localidades inclui particularidades como Brasília e Fernando de Noronha: classificar a natureza administrativa antes de transformar cada registro em legislatura municipal independente. Manter também jurisdições históricas/extintas e mudanças de denominação quando presentes em acervos.

Repositório SAPL oficial: https://github.com/interlegis/sapl.
Commit inspecionado: `ecfd65a8b353be5368bce5ff624d19f4b95d3491`.

Confirmado no código upstream:

- `sapl/api/urls.py`: schema `/api/schema/`, interfaces `/api/schema/swagger-ui/` e `/api/schema/redoc/`; router construído dinamicamente.
- `sapl/norma/models.py`: `texto_integral`, vínculo `materia`, `data_vigencia`, relação `texto_articulado` e modelos de anexos.
- Cada instalação pode ter versão diferente, API pública limitada, dados incompletos ou apenas PDF.

Procedimento para adapter SAPL:

1. Comprovar o host por link no portal oficial da Câmara/prefeitura; domínio imaginado não basta.
2. Ler o schema da instalação; quando inacessível, usar rotas efetivamente publicadas e documentação da versão.
3. Confirmar listagem de normas e paginação — o padrão candidato `/api/norma/normajuridica/` precisa ser validado em cada família/versão.
4. Importar tipos, detalhes, arquivo integral, anexos, relações normativas e matéria vinculada quando disponibilizados.
5. Descobrir texto articulado publicável e permissões; nunca importar conteúdo privado.
6. Guardar ID da instalação + ID remoto. Nunca deduplicar pelo ID numérico sozinho.
7. Adaptar fallback para páginas públicas e PDFs oficiais quando a API não entregar o texto.

O host candidato `sapl.campinas.sp.leg.br` não foi confirmado como fonte oficial; probes retornaram 403/503. **Não usar esse teste como comprovação de que Campinas usa SAPL.** Descobrir o portal real de Campinas e de Piracicaba seguindo links oficiais; usar como cenários de busca municipal do pedido original. O LexML confirma acervo de Campinas, mas não confirma essa URL candidata.

Além de SAPL: criar famílias configuráveis para portais HTML, APIs específicas e diários/PDFs. Priorizar reutilização; registrar configurações por host, seletores, limites e períodos. Portais terceirizados só entram como fonte da jurisdição quando o órgão oficial os indica e sua proveniência é arquivada.

## 4. Arquitetura alvo e contratos

### 4.1 Organização sugerida de código

```text
app/
  domain/                  # identidades, estados, schemas internos, regras temporais
  sources/
    base.py                # contratos, capabilities, erros tipados
    http.py                # fetch, limites, redirects, decompression, cache
    planalto.py            # evoluir arquivo atual
    senado.py              # XML/JSON oficial
    camara.py              # ficha/texto + API proposições
    lexml.py               # somente protocolo confirmado
    sapl.py                # configuração/versionamento por instalação
    alesp.py
    sinj.py
    official_pdf.py
    registries/            # configs de fontes oficiais, sem segredos
  catalog_sync/            # descoberta, particionamento, cursores, reconciliação
  parsing/                 # documento integral, estrutura, tabelas, evidência
  history/
    relations.py           # descoberta e resolução de atos modificadores
    operations.py          # comandos legais estruturados com evidência
    temporal.py            # assinatura/publicação/efeitos/vigência
    reconstruct.py         # aplicação, conflitos, intervalos comprovados
    validate.py            # reconciliação independente
    diff.py                # comparação textual/estrutural
    blame.py               # última origem comprovada por dispositivo/trecho
  provenance/              # processos, autores, emendas, relatorias, votações
  jobs/                    # evolução do atual jobs.py, fachada compatível
  search.py                # SQL/ranking/query parser
  main.py                  # API, ou dividir routers sem mudar contratos existentes
scripts/
  audit_catalog.py
  sync_jurisdictions.py
  sync_catalog.py
  backfill_texts.py
  backfill_history.py
  reconcile_sources.py
  coverage_report.py
tests/fixtures/official/   # documentos reais e manifesto de origem
docs/reports/              # execução, lacunas, comparações e rollout
```

Criar arquivos gradualmente conforme tarefas. Evitar migração de estrutura sem entrega funcional. Compatibilizar imports ao transformar `app/jobs.py` em pacote.

### 4.2 Modelo de dados

Adicionar migrations incrementais após `20261004_0001_initial_schema.py`. Começar com colunas/tabelas novas; migrar dados; mudar leitura/escrita; remover legado apenas após validação e janela de rollback.

| Entidade | Campos e responsabilidade essenciais |
|---|---|
| `Jurisdiction` | UUID, kind, código IBGE externo, UF, nome, nomes históricos, validade territorial, jurisdição pai; distinguir DF e localidades especiais. |
| `Authority` | Órgão emissor, jurisdição, aliases oficiais e vigência institucional. |
| `SourceRegistry` | Host/URLs oficiais, prova do vínculo, adapter/version, capabilities, períodos, tipos, rate limit, credencial requerida, estado de integração e erro atual. |
| `SourceSyncRun` | Fonte, partição, cursor/checkpoint, início/fim, registros previstos/observados, truncamento, checksum de manifestos, contadores e falhas. |
| `Norm` / evolução de `Law` | UUID interno; tipo, número textual/normalizado, data de assinatura, ano, autoridade/jurisdição, ementa, situação com evidência, URNs e IDs externos; sem estado jurídico presumido. |
| `NormAlias` / `PublicSlug` | Aliases normalizados/indexados e rotas legadas; unicidade contextual; slugs legíveis com esfera/UF/código municipal/tipo/número/ano. |
| `ExternalIdentifier` | Fonte+ID remoto únicos, URN e equivalências comprovadas; preservar conflitos de identidade. |
| `Publication` | Documento/edição/seção/página, data, tipo original/republicação/retificação/promulgação, URL, evidência. |
| `SourceDocument` | URL solicitada/resolvida, fetch time/status/headers, MIME/charset, sha bruto, tamanho, objeto privado, identificação e função do documento; independe de parse bem sucedido. |
| `DocumentRepresentation` | Documento, parser/version, AST/checksum semântico, texto integral, diagnóstico, segmentos mapeados/não mapeados; imutável. |
| `DocumentComponent` | Corpo principal, ADCT, anexo, tabela, preâmbulo, assinatura, redação citada; ordem e escopo próprios. |
| `LogicalNode` | UUID lógico estável, norma/componente, identidade jurídica; não se resume ao rótulo numérico. |
| `NodeVersion` | Versão jurídica/representação, UUID lógico, pai, tipo, rótulo/citação, ordem, texto exato, status, fonte/offset/selector/bbox e checksum. |
| `NormativeRelation` | Origem/destino, tipo altera/revoga/acrescenta/regulamenta/converte/cita/etc., dispositivo alvo, evidência, confirmação, ambiguidades. |
| `AmendmentOperation` | Ato/dispositivo que ordena mudança, operação, alvo, antes/depois, datas de efeitos, evidência e pré-condições. |
| `LegalVersion` | Norma, intervalo de validade conhecido, evento gerador, texto/AST imutável, reconstruída ou consolidação observada, completude e evidência. |
| `HistoricalCoverage` | Intervalos comprovados e desconhecidos, documentos/eventos esperados/processados, data de última reconciliação, conflitos impeditivos. |
| `Change` / evolução `LawChange` | Versões antes/depois, operação e UUID de dispositivo, fonte, publicação, efeito legal; múltiplos itens por ato. |
| `LegislativeProcess` | IDs por Casa/órgão, tipo/número/ano, correspondências comprovadas, vínculo com norma, autoria e documentos. |
| `VoteSession` / `IndividualVote` | Casa, votação/evento/objeto/fase/data, tipo nominal/simbólica, resultado oficial, parlamentar/voto/partido/UF à época, fonte. |
| `Job`, `JobAttempt`, `Outbox` | Tipo, payload versionado, chave de idempotência, prioridade, estado, lease/heartbeat, tentativas, cursor, erro, próximo retry, resultado, mensagens a publicar. |
| `CoverageIssue` | Norma/jurisdição/fonte, categoria, evidência, severidade, resolução/retentativa, responsável e estado. |

Não é obrigatório criar uma tabela para cada linha no primeiro commit. É obrigatório preservar as responsabilidades e restrições antes de declarar suas funcionalidades completas.

Restrições mínimas: IDs externos únicos por fonte; unicidade contextual da norma sem fundir homônimas; um job ativo por chave; um nó por identidade/versão/componente; referências de pai válidas; promoção de versão atual transacional; chave estrangeira para versão atual; integridade entre mudanças e versões.

Para variantes de parser da mesma fonte, criar novas representações. Para snapshots de HTML editorialmente diferentes mas juridicamente iguais, manter ambos os documentos e reutilizar a mesma versão jurídica após comparação semântica conservadora. Mudança em pontuação ou texto legal não é ruído editorial.

### 4.3 Estados independentes

Modelar e retornar estado **por capacidade**, com erro e evidência:

```text
catalog: unknown | discovered | indexed | failed
text: not_requested | queued | running | complete | partial | unavailable | failed
structure: not_requested | running | complete | partial | failed
history: not_requested | queued | discovering | fetching | reconstructing |
         validating | complete | partial | unavailable | failed
provenance: not_requested | running | complete | partial | unavailable | failed
freshness: current_as_of | stale | unknown
```

`complete` exige escopo explícito: qual documento, qual intervalo, quais fontes e até qual data. Valores vazios não são estado. Jobs usam `queued/running/succeeded/failed/cancelled` e fases separadas; progresso contém quantidades reais, não percentuais inventados.

Exemplo de resposta nova para histórico:

```json
{
  "status": "partial",
  "job": {"id": "uuid", "status": "running", "stage": "fetching", "completed": 12, "total_known": 18},
  "coverage": {"verified_intervals": [], "checked_through": "2026-10-04", "unresolved_events": 2},
  "items": [],
  "issues": [{"code": "ORIGINAL_TEXT_MISSING", "message": "Publicação original ainda não localizada"}]
}
```

Dados ilustrativos de contrato; não inserir esses números como dados reais. `total_known` pode ser nulo quando descoberta está em curso.

### 4.4 Fila e processamento confiáveis

Escolha para esta base: **PostgreSQL como registro durável + outbox transacional + Redis Streams como transporte**, processamento pelo menos uma vez.

1. API grava `Job` e `Outbox` na mesma transação, com chave única de deduplicação.
2. Dispatcher publica no stream e marca outbox publicada. Repetição deve ser inofensiva.
3. Worker usa consumer group, reserva job com lease no banco e registra tentativa.
4. Faz fetch/parse/validação e grava resultados idempotentes em transações curtas.
5. Só confirma `XACK` depois do resultado persistido. Queda antes disso permite redelivery.
6. Reaper recupera mensagens pendentes e leases vencidos; job persistido sem mensagem também é reenviado.
7. Retry exponencial com jitter, respeito a `Retry-After`, orçamento por fonte/tipo, erro permanente distinguido de transitório e fila de falhas.
8. Job longo tem heartbeat, checkpoints e etapas separadas; retomar sem baixar tudo de novo.

Não prometer exactly once. Garantir resultados idempotentes, locks de promoção e unicidade de efeitos. Migração: drenar a lista antiga, registrar jobs não concluídos, enviar ao transporte novo e conferir saldo. Não excluir a fila anterior sem reconciliação.

Threads locais ficam apenas em modo de desenvolvimento explicitamente ativado. Em produção sem Redis, outbox permanece pendente e UI informa fila indisponível; nunca perder job nem iniciar thread efêmera.

Prioridades: pedidos interativos > normas populares desatualizadas > atualizações > catálogo > backfill. Reservar capacidade para o backfill para evitar starvation. Respeitar limites por domínio em todas as réplicas; um limite por processo não protege uma fonte contra o conjunto de workers.

### 4.5 Arquivo documental e fetch

Usar armazenamento de objetos privado compatível com o ambiente Railway, depois de confirmar recurso/credenciais disponíveis. Banco guarda metadados e referências; manter blobs existentes até migração com checksum comprovado. Se bucket ainda não estiver disponível, usar solução persistente explícita, nunca disco efêmero de container como acervo.

- Chave imutável por SHA-256, deduplicação de bytes e manifesto de origem.
- Arquivar resposta antes do parser; separar erro HTTP de documento legal validado.
- MIME, charset/BOM, gzip, redirects e tamanho máximo configurável por tipo.
- A API IBGE já retornou conteúdo gzip nesta pesquisa; tratar compressão corretamente.
- Retry com timeout, backoff, `ETag`/`Last-Modified` quando disponíveis e validação de mudança.
- Allowlist de fontes/redirects e bloqueio de destinos privados; API pública recebe IDs, nunca URL arbitrária para fetch.
- Distinguir challenge, login, 404 com HTTP 200, página de resultados e norma.
- Sanear HTML para exibição; manter original privado. Não executar scripts da fonte.
- PDFs: arquivo completo, todas as páginas/anexos, extração com mapeamento de página; OCR somente quando necessário e qualidade explícita.
- OCR insuficiente permite leitura do fac-símile, mas não selo de transcrição/estrutura integral validada.
- Referências públicas sempre para fonte oficial; acesso ao arquivo arquivado conforme política apropriada, sem expor bucket/credenciais.

## 5. Algoritmo para texto integral e estrutura

### 5.1 Pipeline documental

1. Validar identidade do documento: epígrafe, tipo, número/data, autoridade e título.
2. Arquivar bytes e links de anexos/representações oficiais.
3. Delimitar conteúdo jurídico e elementos editoriais sem apagar evidência.
4. Inventariar todos os segmentos em ordem: títulos, dispositivos, notas, anexos, tabelas, imagens, assinaturas e blocos ainda não classificados.
5. Separar componentes e redações alternativas/citadas.
6. Construir AST jurídica com referências de origem.
7. Publicar documento integral mesmo quando algum segmento só pode ser mostrado como bloco fiel, com estrutura marcada parcial.
8. Validar inventário, texto, identidade e hierarquia; promover versão apenas após aprovação dos invariantes.

### 5.2 Numeração e escopos

Reconhecer `Art. 1º`, `Art. 10.`, `Art. 1.000`, `Art. 1.000-A`, `Art. 121-A`, `§ 10`, parágrafo único, incisos romanos, alíneas e itens numerados. Normalizar número para comparação sem remover o rótulo literal. Não confundir citação no meio de frase com abertura de artigo.

IDs de citação ilustrativos:

```text
body:art:1
body:art:1000
body:art:121-a.par:2.inciso:III.alinea:b.item:1
adct:art:1
annex:1.art:1
quoted-replacement:<operation-id>:art:1
```

UUID lógico e citação pública são campos distintos. Renumeração/movimentação pode conservar identidade jurídica quando comprovada e criar aliases históricos. Não usar posição no HTML como identidade jurídica permanente. Links antigos `art:1` precisam resolver ao corpo principal, mantendo compatibilidade sem fundir ADCT.

Hierarquia usa pilha de contexto (livro/título/capítulo/seção/subseção/artigo/parágrafo/inciso/alínea/item). Continuação pertence ao nó certo. Um `<p>` pode ter várias unidades, e uma unidade pode ocupar vários `<p>`; segmentar por DOM+contexto, não depender apenas da tag. Conteúdo de `<table>` deve conservar linhas, colunas e cabeçalhos, sem ser convertido em artigos falsos.

### 5.3 Auditoria de completude

Gerar para cada representação:

- Inventário de componentes/documentos/anexos esperados e recebidos.
- Quantidade de segmentos jurídicos, mapeados e não classificados, com localização.
- Texto de leitura reconstruído comparado ao texto oficial normalizado somente por espaços/markup permitido.
- Inventário de rótulos, duplicatas, saltos e variantes; salto sozinho não é prova de perda.
- Nós órfãos, ciclos e colisões de IDs.
- Todas as páginas de PDFs e anexos preservadas.
- Caracteres de substituição/encoding e qualidade OCR.
- Conflitos entre redações e fontes, com decisão documentada.

**Portão de texto integral:** 100% dos segmentos jurídicos e documentos necessários estão representados no leitor ou no fac-símile, com anexos acessíveis. Segmento não classificado pode permanecer bloco literal identificado; não pode desaparecer.

**Portão de estrutura completa:** nenhum segmento jurídico sem classificação estrutural pertinente e nenhuma colisão/hierarquia inválida. Notas editoriais e imagens podem ter tipos próprios; não precisam virar dispositivos.

Reprovar dados com concatenações patológicas, artigos truncados ou conteúdo sem proveniência. Comparar com segunda fonte oficial quando disponível e registrar divergências. Um percentual aproximado de caracteres não basta para certificar integralidade: a ausência de uma palavra de negação pode ser material.

## 6. Histórico real: reconstrução e versões

### 6.1 Resultado funcional

Timeline com texto original, alterações por ato e dispositivo, datas explicadas, fontes, detalhe antes/depois, comparação entre versões e seleção de redação por data dentro de intervalos verificados. O histórico não depende de uma regra específica por lei nem apenas de observações feitas após 2026.

### 6.2 Descoberta dos eventos

Para cada norma:

1. Localizar publicação original e posteriores republicações/retificações/promulgações.
2. Importar relações oficiais do Senado, Câmara e fontes locais.
3. Extraír do consolidado notas e anchors: redação dada, incluído, revogado, restabelecido, vigência, conversão, veto, etc.
4. Distinguir **altera** de “vide”, regulamenta, menciona e jurisprudência.
5. Resolver identidade do ato modificador por tipo+autoridade+jurisdição+número+data/ano/ID oficial.
6. Baixar cada ato e identificar seu comando legal e alvo exato.
7. Descobrir modificações no próprio ato modificador e referências necessárias para datas/eficácia.
8. Percorrer grafo com prevenção de ciclos, deduplicação e checkpoint. Limite operacional não pode virar falso selo de histórico completo.
9. Registrar evento descoberto mesmo quando seu texto ou alvo não pode ser resolvido; ele vira lacuna impeditiva.

A lei que altera pode conter dispositivo novo próprio e bloco de redação da lei alterada. Manter esses escopos separados. O texto riscado do compilado é evidência auxiliar, não suficiente por si só para ordenar e datar todas as versões anteriores.

### 6.3 Operações jurídicas estruturadas

Implementar operações: `ADD`, `REPLACE`, `REPEAL`, `RENUMBER`, `MOVE`, `REINSTATE`, `CORRECT`, e eventos `VETO`, `PROMULGATION`, `TEMPORARY_EFFECT`, `CONVERSION`, `LOSS_OF_EFFECT` quando comprovados. Relações informativas não aplicam patch.

Cada operação contém:

- Ato e dispositivo que ordenam a operação.
- Alvo e escopo resolvidos, texto do comando e trecho da redação nova.
- Documento, selector/offset/página e checksum da evidência.
- Texto anterior esperado ou condição estrutural comprovável.
- Texto posterior e data de efeitos; confiança por dimensão, não nota genérica.
- Ambiguidades, conflitos, necessidade de revisão e estado de aplicação.

Não eliminar pontuação para dizer que textos são equivalentes. Normalização para alinhamento é separada da prova de igualdade. Operação com alvo ambíguo ou pré-condição não satisfeita fica pendente e não é aplicada silenciosamente.

### 6.4 Semântica temporal

Modelar pelo menos:

- `signed_on`: assinatura/promulgação.
- `published_on`: publicação oficial, edição/seção.
- `effective_from` / `effective_until`: efeitos jurídicos comprovados, podendo variar por dispositivo.
- `observed_at`: quando LeiAberta coletou a evidência.
- `knowledge_valid_from/until`: quando a afirmação entrou/foi corrigida no sistema, se implementado bitemporalmente.

Vacatio legis, efeitos diferidos, regimes transitórios, vigência por dispositivo, retroatividade expressa, eficácia temporária e perda de eficácia de MP precisam de regras/evidência. Não somar “45 dias” indiscriminadamente; regra temporal depende do ato e contexto. A expressão “entra em vigor na data de sua publicação” requer a publicação, não a assinatura.

Eventos no mesmo dia podem exigir ordenação documental; na falta dela registrar conflito. Não atribuir hora arbitrária. Separar redação promulgada, publicada e vigente. Dispositivo vetado não entra como texto vigente só porque apareceu no projeto. Veto rejeitado e promulgação posterior exigem publicação própria.

Decisões judiciais/suspensões de aplicação devem ser camada separada com fonte e alcance. Não reescrever texto legislativo nem inferir revogação tácita por comparação textual. Casos complexos sem evidência suficiente permanecem anotados/pendentes; aplicar conservadoramente, sem fabricar conclusão jurídica.

### 6.5 Construção das versões

1. Parsear e validar texto original como versão de publicação, inclusive marcações de veto.
2. Montar ledger de operações, ordenar por efeitos comprovados e dependências.
3. Aplicar operações à AST, validando pré-condições e hierarquia a cada passo.
4. Criar versão imutável em cada fronteira temporal que efetivamente altera redação/estado.
5. Agrupar mudanças por ato na timeline sem perder cada operação de dispositivo.
6. Comparar resultado final com consolidado oficial do mesmo recorte temporal/documental.
7. Registrar divergências em nível de dispositivo; procurar ato/retificação omitido.
8. Só declarar intervalo completo quando original, cadeia necessária e reconciliação estão aprovados.

Se a reconstrução integral não for possível, mostrar eventos confirmados e lacunas. Uma data fora dos intervalos verificados recebe resposta explícita de indisponibilidade, nunca a versão mais próxima fingindo ser exata. A versão “observada na fonte em X” continua acessível como tal.

### 6.6 Pilotos e expansão obrigatória

Primeiro LMP e LGPD; depois todas as 14 normas atuais; depois amostras estaduais/DF/municipais e todas as normas descobertas por lote. Esta ordem valida algoritmos, não restringe escopo final.

- **LMP:** preservar os três acréscimos existentes, descobrir todos os demais eventos oficiais, corrigir datas por publicação/efeitos, remover hardcode após equivalência demonstrada.
- **LGPD:** XML Senado fornece cadeia extensa, MP 869/2018, Lei 13.853/2019 e outros atos posteriores; conferir textos originais, vetos e vigências diferentes. Verificar relações recentes de 2025/2026, sem confiar apenas nos exemplos antigos.
- **Código Civil/Constituição/CLT/Código Penal:** necessários para escala e estruturas complexas. Não declarar todos os 14 históricos completos se os códigos longos estiverem só com eventos recentes.
- **LC 135/2010 + LC 64/1990:** validar lei modificadora versus norma modificada; incluir LC 64 no catálogo pelo resolver.
- **Norma estadual/DF/municipal:** escolher atos reais descobertos com pelo menos uma alteração comprovada; registrar IDs e fontes antes de fixar fixtures.

## 7. API, busca e interface funcionando

### 7.1 Contratos novos e compatibilidade

Manter rotas existentes e acrescentar contratos documentados:

```text
GET  /api/jurisdictions?kind=&uf=&q=&cursor=
GET  /api/sources?jurisdiction_id=&status=&cursor=
GET  /api/coverage?jurisdiction_id=&source_id=
GET  /api/laws?q=&jurisdiction_id=&type=&year=&status=&cursor=
GET  /api/laws/{slug}/document?version_id=&component=
GET  /api/laws/{slug}/toc?version_id=
GET  /api/laws/{slug}/nodes?version_id=&article=&component=&cursor=
GET  /api/laws/{slug}/versions?cursor=
GET  /api/laws/{slug}/version-at?date=YYYY-MM-DD
GET  /api/laws/{slug}/history?node_id=&cursor=
POST /api/laws/{slug}/history/prepare
POST /api/laws/{slug}/hydrate
GET  /api/jobs/{id}
GET  /api/laws/{slug}/diff?from_version=&to_version=&node_id=
GET  /api/laws/{slug}/blame?version_id=&node_id=
GET  /api/changes/{id}
GET  /api/processes/{id}
GET  /api/votations/{id}
POST /api/resolve                  # query tipada, fontes cadastradas, rate limit
```

Rotas propostas; Luna implementa e publica OpenAPI. Refresh forçado, resync global, reprocessamento e administração exigem autorização técnica. Acesso público a preparar texto/histórico continua deduplicado e limitado. Não tornar toda reingestão administrativa pública.

Resposta `202` só com job real, `200` para resultado disponível, erro tipado para fonte inacessível. Normas inexistentes e rotas inválidas devem dar 404 real; a SPA não pode mascarar tudo como HTML 200. Paginação com cursor estável e limites; nunca carregar corpus nacional em uma requisição.

### 7.2 Busca nacional

- PostgreSQL com `pg_trgm`, `unaccent`/normalização materializada e FTS `tsvector` indexado. Confirmar permissões das extensões no Railway.
- Aliases em tabela indexada, nomes populares e siglas comprovados/curados.
- Ranking: identidade contextual exata > alias exato > número/ano/tipo > título/ementa > dispositivo > aproximação.
- Fuzzy só sugere correção quando não há resolução exata; mostrar o que foi interpretado.
- Parser: número curto/longos/pontos, `LC 135/2010`, artigos com sufixo, §, inciso, alínea, UF, município e órgão.
- Escopo de dispositivo na versão atual validada ou versão/data escolhida; não misturar versões antigas por acaso.
- Índice de texto pode cobrir documentos integrais e nós, mas identificar origem/versionamento.
- `art. 1` mostra candidatos com título, esfera/local, número/ano, trecho e link direto do dispositivo.
- Enter em consulta ambígua abre resultados; clique explícito escolhe candidato.
- Nome municipal contextualiza a busca; municípios homônimos exigem UF/seleção.
- Se busca local não resolve identificador claro, `resolve` consulta fontes apropriadas, persiste metadados e dispara hidratação. Evitar fanout síncrono a milhares de hosts.
- Diferenciar “nenhuma norma encontrada nas fontes consultadas” de “localidade sem fonte integrada”.
- Paginação, cache por parâmetros/versão, consultas sem N+1 e medição com corpus representativo.

### 7.3 Leitor integral

Sumário por componentes/estrutura; texto como protagonista; rota por artigo carrega artigo+descendentes e contexto, sem baixar códigos inteiros. Modo texto completo carrega progressivamente e oferece exportação/arquivo integral. Preservar acessibilidade, seleção, busca no documento, âncoras, copiar link e navegação teclado/mobile.

Mostrar artigos revogados/vetados com marcação e fonte no recorte escolhido, sem desaparecer da estrutura. Anexos/tabelas têm navegação e visualização próprias. Oferecer fac-símile/PDF oficial e arquivo quando estrutura for parcial. Mostrar título/jurisdição/data da versão para impedir leitura de documento homônimo.

### 7.4 Histórico, diff e blame

Estados de tela:

| Estado | Comportamento |
|---|---|
| Não solicitado | Explicar e permitir preparar histórico; opcionalmente enfileirar automaticamente com política clara. |
| Enfileirado/executando | Mostrar fase, job, progresso real e atualização; texto já disponível continua legível. |
| Completo | Timeline original+eventos e seletor temporal dentro do intervalo verificado. |
| Parcial | Eventos comprovados, lacunas e limites temporais; nenhuma promessa falsa. |
| Sem eventos em intervalo completo | Declarar ausência de alterações **nesse intervalo**, com data da verificação. |
| Falha | Erro compreensível, última tentativa, retry deduplicado; nada de spinner infinito. |
| Fonte indisponível | Fonte/link e capacidade afetada; outras capacidades continuam disponíveis. |

Polling termina conforme estado terminal e pode retomar pelo job persistido. Timeout de UI não muda job para sucesso/falha; informa que continua em fila e permite voltar. SSE é opcional, não requisito para funcionar.

Timeline agrupa ato/data, lista dispositivos e abre detalhe. Antes/depois vêm de versões comprovadas; adição/revogação usam ausência semântica, não texto vazio fingindo redação. Comparação entre duas versões deve excluir ruído editorial, destacar texto literal e detectar mudança estrutural/renumeração; nunca usar diff bruto de HTML como alteração jurídica.

Blame mínimo por dispositivo: último ato comprovado que alterou a redação, fonte e evento. Origem por trecho exige alinhamento verificável; se não houver, mostrar nível de dispositivo. Autores políticos só aparecem via origem documental específica e com papel correto.

## 8. Projetos, autores, emendas, relatorias e votos

Implementar depois que texto e histórico genérico estiverem validados, mantendo o escopo original do produto.

1. Extrair vínculo norma→proposição da ficha/relação oficial.
2. Resolver processo em cada Casa com IDs e equivalências documentadas; números podem mudar entre Casas.
3. Importar autores e coautores de projeto, iniciativa executiva/popular e autores de emendas como papéis distintos.
4. Importar tramitação, documentos, pareceres, emendas e relatorias.
5. Relacionar operação de dispositivo com emenda/substitutivo/documento apenas se evidência específica demonstrar origem.
6. Importar votações pertinentes ao projeto, emenda, destaque, substitutivo ou veto, com fase/objeto.
7. Quando nominal, importar votos individuais e identificação do parlamentar à época. Quando simbólica, indicar modalidade; não fabricar votos individuais.
8. Comparar totais oficiais com agregações, distinguindo ausências, obstrução, abstenção, presidência e categorias da fonte.
9. UI mostra evento/contexto e links; voto favorável ao projeto não prova autoria de cada trecho.

Piloto concreto pesquisado: Lei 14.550/2023 → PL 1604/2022; processo Senado retornou `8272922` / matéria `153558`. Confirmar endpoint com `sigla=PL`, identidade e vínculo antes de persistir. Autoria informada pelo processo foi Senadora Simone Tebet (MDB/MS); guardar fonte e papel, não atribuir automaticamente os parágrafos individualmente à parlamentar. Não pré-preencher votos: a pesquisa não validou uma votação nominal específica.

Estados `unavailable` precisam explicar: votação simbólica, registro não disponibilizado, dado histórico faltante ou ainda não processado. São situações diferentes.

## 9. Backlog executável, dependências e critérios de saída

Executar na ordem abaixo. Cada item tem commit revisável, evidência em `docs/reports/`, testes pertinentes e resumo de lacunas. Nenhuma fase termina só porque existe um arquivo novo ou endpoint retorna 200.

### Fase 0 — linha de base e proteção do acervo

**T00 — Recapturar ambiente e instruções.**

- Ler `AGENTS.md` aplicável, README, prompt original e este documento.
- Conferir branch/SHA, alterações locais, esquema Alembic e serviços Railway.
- Capturar `/api/stats`, `/api/laws`, estados de cobertura e jobs da produção.
- Registrar fonte/data/quantidade; não exportar segredos.
- Saída: `docs/reports/00-baseline.md` com links e inventário reproduzível.

**T01 — Backup e staging.** Depende T00.

- Confirmar backup Postgres e estratégia de restauração; exportar arquivo bruto existente com manifestos/checksums.
- Criar ambiente staging Railway com banco/Redis separados e variáveis de referência desse ambiente.
- Copiar dados de forma controlada para auditar parser; não fazer migração destrutiva na produção.
- Validar restauração em staging antes de backfill/migração nacional.
- Saída: recuperação demonstrada e identificação dos recursos, sem credenciais no relatório.

### Fase 1 — estados honestos e infraestrutura durável

**T02 — Corrigir histórico e cobertura independentes.** Depende T00.

- Alterar `models`, migration, serialização API e `static/app.js`.
- Histórico vazio sem job vira não reconstruído, com ação que cria job real.
- Existing LMP fica parcial até reconstrução completa; demais prontas não ficam spinner infinito.
- Atualização da norma não rebaixa texto válido; freshness/erro separados.
- Saída: telas/API para cada estado, inclusive falha/retry; não existe “preparando” sem job.

**T03 — Fila, outbox, idempotência e recuperação.** Depende T02.

- Implementar seção 4.4; migration jobs/outbox, dispatcher, consumers/reaper e observabilidade.
- Dedupe concorrente; refresh administrativo real; migrar pendências antigas.
- Desligar fallback efêmero em produção.
- Saída: reinício/queda de worker e Redis não perdem trabalhos; duplicatas não duplicam versões/operações.

**T04 — Arquivo de fonte independente.** Depende T01/T03.

- Implementar `SourceDocument`, armazenamento persistente e fetch seguro.
- Migrar snapshots sem apagar os antigos; confirmar byte checksum e contagem.
- Arquivar antes de parsing, preservar falhas úteis e não publicar challenge como norma.
- Saída: documento recuperável e reprocessável sem novo download; dedupe/cobertura comprovados.

### Fase 2 — corrigir texto integral das normas existentes

**T05 — Modelo documental e IDs.** Depende T04.

- AST com componentes, identidade lógica e aliases de rotas antigas.
- Corrigir milhares/sufixos, hierarquia, continuação, aspas/citações e duplicatas.
- Preservar pontuação, redações riscadas, notas, links e conteúdo extra-articular.
- Saída: Código Civil Art. 1000/2046 endereçáveis e Art. 1 sem concatenação; CF/ADCT separados.

**T06 — Anexos, tabelas e PDF.** Depende T05.

- Capturar documentos ligados; representar conteúdo integral e páginas oficiais.
- Criar extração PDF/OCR com fonte por página e diagnóstico.
- Saída: leitor integral sem perda de segmentos e cobertura de estrutura fiel às capacidades reais.

**T07 — Auditor de completude e promoção.** Depende T05/T06.

- Implementar seção 5.3; tornar validação pré-condição de publicação.
- Criar relatório máquina+humano por representação; comparar original/compilado e fonte alternativa quando possível.
- Reprocessar **as 14 normas existentes**, não apenas o Código Civil.
- Saída: quadro por norma com texto/anexos/estrutura/gaps; nenhum selo pronto para extração defeituosa.

**T08 — Leitor e rotas por dispositivo.** Depende T05/T07.

- Sumário, componentes, artigo/subdivisão, fac-símile, fonte e recorte temporal.
- Paginar/carregar progressivamente; manter URLs e layout mobile.
- Saída: acesso direto a dispositivo/anexo correto e leitura de todo o conteúdo disponível.

### Fase 3 — catálogo nacional, fontes e descoberta

**T09 — Jurisdições, identidades, registro de fontes.** Depende T04/T05.

- Importar IBGE com versão/data; naturezas administrativas, UF e nomes históricos.
- Criar autoridade, ID externo, alias e slugs contextualizados, com redirects legados.
- Tabela pública de integração/lacunas para União, 26 estados, DF e localidades.
- Saída: nenhuma colisão entre normas homônimas; cada território tem estado explícito.

**T10 — Contrato de adapters e sync retomável.** Depende T09/T03.

- Capabilities, erros tipados, descoberta, páginas/partições, documentos, relações, cursores e reconciliação.
- Sync inicial completo + incremental + rescan periódico com overlap.
- Saída: interrupção retoma; não perde registros por paginação/truncamento; desaparecimento remoto não apaga norma.

**T11 — Senado + Câmara federais.** Depende T10.

- Implementar rotas/documentos confirmados nesta pesquisa; enumeração completa por tipo/período conforme limites reais.
- Normalizar campos, deduplicar com evidência e preservar situação literal.
- Planalto enriquece texto; Câmara originais; Senado relações/publicações.
- Saída: catálogo federal fora das 14 sementes, manifestos de partições e normas recentes/antigas/revogadas encontráveis.
- Implementação em produção: o catálogo do Senado usa 24 classes normativas validadas, partições anuais para DEC-n e deduplicação somente quando linhas repetidas têm metadados idênticos. A reconciliação continua necessária; na coleta de 05/10, AIEMC falhava porque seu rótulo oficial excede 48 caracteres e DEC-n recebeu XML truncado. A migração para `law_type` de 128 caracteres e o retry validado de respostas incompletas estão preparados para publicação. A Câmara continua fora da enumeração integrada; as fontes locais não provam totalidade federal.

**T12 — LexML complementar.** Depende T10; não bloqueia T11/T13.

- Revalidar acesso, protocolo/colheita e escopo. Integrar só contrato confirmado.
- Registrar bloqueio se houver challenge; ingestão direta continua.
- Saída: discovery real e dedupe com fontes, ou bloqueio documentado sem marcar integração concluída.

**T13 — ALESP e SINJ-DF pilotos.** Depende T10/T06.

- Descobrir e validar search/pagination/detail/documents/relations dos portais oficiais.
- Fixtures reais com ato original, alteração e anexo quando existir.
- Saída: catálogo/texto reais de SP e DF, sem limitar piloto a uma norma manual.

**T14 — SAPL e famílias municipais.** Depende T10/T06.

- Confirmar hosts por portais oficiais; implementar adapter versionado/configurável.
- Descobrir portais reais de Campinas/Piracicaba; integrar suas famílias adequadas.
- Incluir instalações SAPL oficiais variadas, não assumir campos/permissões iguais.
- Saída: enumeração completa das fontes piloto e resolver municipal funcionando.
- Execução 05/10/2026: adapter reutilizável validado em Manaus, Anápolis, Campina Grande, Unaí, São João da Boa Vista e Natal. As seis APIs informaram 62.031 registros agregados na consulta; páginas, tipos, identificadores, anexos PDF e endereços oficiais foram conferidos. O campo SAPL de esfera pode declarar Município/Estado/Federal ou ficar vazio; cada lei mantém essa evidência e a jurisdição é atribuída segundo o campo, inferindo a localidade do portal apenas quando ele está vazio. Após o deploy, Manaus (9.846), Anápolis (8.173) e Natal (9.353) já foram enumeradas; Campina Grande retomou a sincronização em páginas persistidas. Unaí e São João da Boa Vista precisam completar nova tentativa sob o parser de esfera publicado. Acompanhar `/api/sources` até todas as seis registrarem `enumerated`.

**T15 — Expansão dos 26 estados e localidades.** Depende T11/T13/T14.

- Job de descoberta assistida por inventários oficiais/LexML e verificação dos vínculos.
- Por jurisdição: registrar todas as fontes normativas relevantes, período/tipos, limites e responsabilidades complementares.
- Classificar por família e implementar famílias faltantes; rodar catálogo/texto em lotes com checkpoints.
- Priorizar lacunas por abrangência, mantendo todos os territórios no inventário e backlog.
- Saída: inventário nacional completo de estados/localidades; fontes confirmadas enumeradas; saldo de não integradas/inacessíveis visível e trabalho contínuo, sem limite14.
- Condição para alegar cobertura nacional integral: reconciliação e denominador suficiente **para cada jurisdição**, não mera existência de uma linha no registro.

**T16 — Busca SQL e resolver nacional.** Depende T09/T11; completar T13–T15 progressivamente.

- Implementar seção 7.2, filtros, snippets, índices e resolução fora do catálogo.
- Corrigir Enter ambíguo e link de dispositivo em todos os tipos de resultado.
- Saída: consultas municipais/estaduais/federais verdadeiras; busca sem N+1 nem corpus todo em memória.

### Fase 4 — histórico genérico, diff e blame

**T17 — Relações normativas e ledger de eventos.** Depende T11/T05.

- Importar relações Senado/notas/anchors/fichas, resolver atos, distinguir tipos e guardar evidências.
- Baixar original e modificadoras recursivamente; jobs por norma com checkpoints.
- Saída: LMP/LGPD com eventos além do hardcode, identificados e auditáveis.

**T18 — Operações e semântica temporal.** Depende T17/T07.

- Implementar seções 6.3/6.4, pré-condições, conflitos e data por dispositivo.
- Corrigir publicação vs assinatura das sementes e eventos legados.
- Saída: ADD/REPLACE/REPEAL e casos temporais reais aplicados com evidência; casos incertos bloqueados explicitamente.

**T19 — Reconstrução e reconciliação de versões.** Depende T18.

- Implementar seção 6.5, intervalos verificados e versões imutáveis.
- Pilotos LMP/LGPD; depois todas as 14 normas e fontes locais.
- Saída: redação anterior/posterior reproduzível, atual reconciliada e nenhuma data fora de cobertura apresentada como exata.

**T20 — Timeline, detalhe, seletor de data e diff.** Depende T19/T08.

- Implementar API/UI seção 7.4, estados independentes e comparações estrutural/textual.
- Saída: abrir Histórico → evento → antes/depois → fonte; comparar versões reais; reload preserva estado e deep link.

**T21 — Blame por dispositivo e origem específica.** Depende T19/T20.

- Mostrar último ato por nó e nível da evidência; alinhamento por trecho só quando verificável.
- Saída: link para evento e fonte correspondente; não atribuir autoria política sem T23.

**T22 — Histórico em lote nacional.** Depende T19/T13/T14.

- Enfileirar normas acessíveis por prioridade, descobrindo todos os atos necessários.
- Medir fila, conflitos e intervalos; expandir regras para famílias documentais adicionais.
- Saída: todas as normas descobertas têm pedido/processamento/resultado rastreável; completas somente quando portão passa; parciais têm lacunas específicas, não genérico “em preparação”.

### Fase 5 — origem legislativa e votos

**T23 — Processos, autores, emendas e relatorias.** Depende T17/T19.

- Modelos/API e importadores Câmara/Senado/SAPL conforme vínculo explícito.
- Piloto LMP comprovado; expansão para corpus com relações disponíveis.
- Saída: origens documentadas, papéis distintos e indisponibilidade explicada.

**T24 — Votações e votos.** Depende T23.

- Importar eventos/votos, modalidade/contexto e totais oficiais, com paginação.
- UI nominal/simbólica, filtros e links às Casas/fontes.
- Saída: votos reais vinculados ao objeto correto; nenhuma contagem/nominal inventada.

### Fase 6 — operação contínua e conclusão verificável

**T25 — Scheduler, freshness e observabilidade.** Depende T10/T22.

- Scheduler único com lock e outbox; incrementais diários ou frequência permitida por fonte; rescan periódico completo.
- Web/worker separados; implementar cron/serviço scheduler no Railway se necessário.
- Métricas: idade da fila, throughput por fonte, retries, erros, heartbeat, gaps, freshness, custos/storage.
- Saída: nova norma/alteração entra sem deploy do código; nenhuma fonte falha silenciosamente.

**T26 — Validação e release Railway.** Depende entregas do lote.

- Executar matriz seção 10 e runbook seção 11; liberar por portões, não por tamanho do commit.
- Validar produção com SHA/deployment terminal e fluxos públicos.
- Saída: relatório com dados reais, screenshots/URLs, testes, falhas e rollback disponível.

**T27 — Documentação e prestação de contas.** Depende todos os itens executados.

- README, env examples, OpenAPI, adapters/coverage, runbooks, limites e próximos bloqueios específicos.
- Resumo por requisito, jurisdição/corpus processado, texto/histórico/origem/votos e saldo.
- Saída: usuário consegue distinguir entrega concluída, lote em andamento e fonte externa indisponível.

### 9.1 Ordem prática e caminho crítico

```text
T00 → T01
T00 → T02 → T03 → T04 → T05 → T06/T07 → T08
T04/T05 → T09 → T10 → T11 → T17 → T18 → T19 → T20 → T21
T10 → T12 + T13 + T14 → T15
T09/T11 → T16
T19/T13/T14 → T22 → T25
T17/T19 → T23 → T24
Cada lote validado → T26 → T27 atualizado
```

Executar uma tarefa por vez quando houver dependência. Frentes independentes podem ser organizadas separadamente, mas este plano não exige agentes paralelos. Luna 6 deve manter uma checklist persistida e retomar do último checkpoint.

## 10. Matriz de testes e portões de qualidade

Os testes abaixo fazem parte da **implementação futura**. Esta entrega de planejamento não executou a nova suíte nem implantou correções.

### 10.1 Fixtures oficiais

Guardar documentos reais com manifesto: URL solicitada/resolvida, data de coleta, MIME, sha bruto, norma/componentes, extração e expectativas revisadas. A expectativa não pode ser gerada pelo mesmo parser sob teste sem conferência independente.

Fixtures mínimas: Código Civil, CF+ADCT, CLT, Código Penal, LC135 com redação citada da LC64, LMP original/modificadoras, LGPD original/alterações/vetos, HTML com múltiplas unidades por parágrafo, tabela/anexo, PDF textual, PDF escaneado, XML Senado e respostas SAPL reais. Exemplos sintéticos podem testar falhas, mas nunca virar corpus público nem prova de cobertura real.

### 10.2 Parsing e integridade

- Art. 1 versus 10/100/1000; `1.000-A`; rótulos e pontuação conservados.
- `art:1` CF diferente de `art:1` ADCT/anexo; nenhuma concatenação silenciosa.
- Repetição de redação antiga/atual separada, não IDs duplicados fundidos.
- Dispositivo citado dentro de ato modificador não vira dispositivo autônomo da lei errada.
- Inciso/alínea/item e continuação com pai correto; hierarquia acíclica.
- Capítulos/tabelas/preâmbulo/assinatura/anexos não desaparecem.
- Charset/BOM/gzip; detecção de login/challenge e falha de identidade.
- Parser novo cria representação nova, mantendo antiga reproduzível.
- Completude reprova ausência de fragmento, inclusive pontuação material.

### 10.3 Histórico e datas

- Adição, modificação e revogação com documentos oficiais antes/depois.
- LMP 14.550: assinatura19/04 versus publicação20/04 e vigência confirmada no ato.
- LGPD com vigência por dispositivo, MPs e atos posteriores; veto/promulgação quando aplicável.
- Renumeração/movimentação mantendo vínculo lógico comprovado.
- Eventos no mesmo dia sem ordenação: conflito explícito.
- Original faltante: timeline parcial e `version-at` sem falsa resposta exata.
- Ato descoberto não processado impede completo.
- Igualdade semântica de redação versus mudanças editoriais de HTML.
- Reconciliação final reproduzível e divergência apontando nó/evidência.
- Lei sem alteração: ausência só no intervalo verificado.

### 10.4 Banco, fila e ingestão

- Usar PostgreSQL/Redis reais em integração; SQLite não verifica locks, índices e consumer groups.
- Requests concorrentes criam um job ativo; duplicata de mensagem não duplica efeito.
- Queda antes/depois de commit/ACK; recuperação de pendentes/outbox/leases.
- Redis indisponível mantém pedido persistido; retomada publica.
- Retry transitório, erro permanente, dead letter e retentativa administrativa.
- Paginação incompleta, exportação300, cursor expirado, atualização enquanto enumera e rescan com overlap.
- Norma desaparecida da fonte não é excluída do acervo.
- Refresh falho mantém versão pública anterior e freshness correto.
- Migrations e restores preservam snapshots/links legados.

### 10.5 Busca, UI e produto

- LGPD, LGDP, CF/88, LC135/2010, número com ponto, lei curta e ato sem número.
- `art. 7 LGPD`, §/inciso e `art. 1` ambíguo.
- Enter não escolhe primeiro candidato arbitrariamente.
- Query federal/estadual/municipal com colisão de número/ano.
- Campinas e Piracicaba com normas reais descobertas; não criar exemplo para passar teste.
- Norma fora das14 é resolvida, catalogada, hidratada e volta pronta após reload.
- Texto completo e anexo disponíveis; artigo carrega só recorte necessário.
- Histórico pronto/parcial/falha/não solicitado; nenhuma mensagem enganosa ou polling infinito.
- Original→evento→diff→fonte; seleção por data e deep links.
- Blame informa nível de evidência; origem/votos reais ou motivo de ausência.
- Desktop/mobile, teclado, contraste, foco e leitores de tela.
- 404, URLs antigos, sitemap paginado/index e metadados coerentes com cobertura.

### 10.6 Performance e escala

Medir com corpora reais crescentes: amostra federal, fonte estadual completa, fontes municipais variadas, depois catálogo nacional. Registrar p50/p95, quantidade de queries, RAM, filas, bytes e tempo de ingestão. Definir orçamento antes do teste e ajustar por dados medidos.

Meta inicial de produto em staging com recursos identificados: busca local p95 até 500 ms e páginas/API de artigo p95 até 1 s sem hidratação externa. Esses números são metas propostas, não resultados existentes. Fetch oficial tem latência própria e fica assíncrono. Teste de carga deve respeitar fontes; usar fixtures/cache para não sobrecarregar portais públicos.

Não estimar prazo de “todas as leis” sem medir tamanho dos acervos e limites. Modelo de capacidade: documentos pendentes × tamanho médio; fetch/parse médios; concurrency efetiva por domínio; retries/OCR; storage de originais+representações+versões+backups. Publicar estimativa com intervalo e recalcular por lote. Evitar milhares de versões integrais duplicadas sem avaliar armazenamento; snapshots/persistência estrutural compartilhada podem reduzir custo preservando imutabilidade.

## 11. Railway: execução e release

### 11.1 Recursos atuais conhecidos

| Recurso | Identificador |
|---|---|
| Workspace | `852d7672-340b-427b-a162-252b8021462c` — DIDIXX’s Projects |
| Projeto | `ac5c9188-a792-4d4a-99d6-512740aec73e` |
| Ambiente production | `b415a556-41ec-4f33-994f-1f5d38b633a1` |
| Web | `549c7526-c99d-4b45-bdee-42462bdf6fa6` |
| Worker | `d00c4b89-3d35-4c86-afe6-c5c87c70d2f5` |
| Redis | `6557bcd8-4609-40d7-ab23-7f0bfef0f5d1` |
| Postgres | `94ed1c2a-cc3f-4a39-b458-ba7d04d15b43` |
| Domínio | `web-production-12e95.up.railway.app` |

Revalidar IDs/configuração com Railway conectado antes de executar. Região observada: `asia-southeast1-eqsg3a`. Medir latência para Brasil; alteração de região exige avaliar migração de dados/serviços e custo, não é requisito automático deste plano.

Configuração importante já aprendida:

- Railway injeta `PORT=8080` para web; domínio encaminha para **8080**. Docker `EXPOSE 8000` não substitui `$PORT`.
- Web usa `sh scripts/start-web.sh`; worker `sh scripts/start-worker.sh`.
- Variáveis de referência para Postgres/Redis devem ser resolvidas no ambiente correto, por exemplo `${{Postgres.DATABASE_URL}}` e `${{Redis.REDIS_URL}}` conforme nomes atuais.
- A tentativa anterior de configuração por `railway.toml` foi rejeitada/deprecated na ferramenta usada. Confirmar suporte atual e usar API/CLI/configuração de serviço oficial; não reintroduzir arquivo sem comprovação de aplicação.
- `/health` atual verifica banco; acrescentar readiness operacional e heartbeat de worker em endpoint/métrica separados.

### 11.2 Runbook por lote

1. Conferir branch, SHA e worktree; registrar lote e migrations.
2. Backup/checksums e restore validado conforme T01.
3. Criar/aplicar alterações aditivas em staging. Serializar migrations com lock; não deixar cada réplica migrar e disparar backfill no startup.
4. Provisionar armazenamento/scheduler só quando necessário; verificar referências/segredos sem imprimi-los.
5. Migrar corpus existente em staging e executar matriz do lote.
6. Conferir versão nova versus antiga e links históricos; produzir relatório de divergências.
7. Fazer deploy web/worker compatíveis com esquema misto; expand-contract.
8. Esperar deploy terminal de sucesso do SHA correto, conferir logs/health/readiness, domínio8080 e worker heartbeat.
9. Liberar funcionalidades por flags/configuração verificadas quando precisar migração gradual.
10. Rodar piloto de ingestão em produção e confirmar estados reais pela API/UI.
11. Abrir os fluxos públicos em desktop/mobile, links oficiais e histórico/diff.
12. Aumentar lotes progressivamente, monitorando erro, fila, banco, RAM, storage e limites por host.
13. Registrar métricas e coverage. Se erro material, suspender promoção/backfill afetado e aplicar rollback de aplicação; preservar dados/evidência.

Rollback não deve apagar versões/fontes. Manter aplicação anterior compatível com colunas novas; reversão destrutiva de migration só se houver plano explícito validado. Não ligar nova indexação ao tráfego sem plano de criação de índices que evite bloqueios longos.

### 11.3 Variáveis esperadas

Além de `DATABASE_URL`, `REDIS_URL`, `PORT`, `LOG_LEVEL` e variáveis atuais, adicionar exemplos sem valores reais para:

```text
APP_ENV
SOURCE_ARCHIVE_BUCKET / SOURCE_ARCHIVE_ENDPOINT / credenciais via Railway
JOB_LEASE_SECONDS / JOB_MAX_ATTEMPTS / WORKER_CONCURRENCY
SOURCE_FETCH_TIMEOUT / SOURCE_MAX_BYTES / SOURCE_RATE_LIMIT_DEFAULT
CATALOG_SYNC_ENABLED / HISTORY_BACKFILL_ENABLED
INLABS_LOGIN / INLABS_PASSWORD    # somente se acesso autorizado estiver disponível
ADMIN_AUTH_SECRET               # mecanismo administrativo escolhido
```

Confirmar nomes e defaults na implementação. Nenhuma variável é credencial exigida só para começar texto/histórico federal: fontes públicas já confirmadas permitem progresso independente do INLABS/LexML.

## 12. Comandos e operação reproduzível

### 12.1 Comandos existentes

Executar na raiz do repositório, em ambiente configurado e com DB adequado:

```bash
git status --short
git rev-parse HEAD
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
alembic current
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker existente: `python -m app.worker`, com Redis configurado. Testes existentes: `pytest` e `npm run test:e2e`, após instalação das dependências/browser descrita no projeto. Não executar migrations/backfill em produção por engano ao verificar localmente; identificar o ambiente nos relatórios.

### 12.2 Interface de comandos a implementar

Criar estes comandos ou equivalentes documentados; **ainda não existem**:

```bash
python -m scripts.sync_jurisdictions --source ibge --report docs/reports/jurisdictions.json
python -m scripts.sync_catalog --source senado --resume --report docs/reports/senado-sync.json
python -m scripts.sync_catalog --source camara --resume --report docs/reports/camara-sync.json
python -m scripts.audit_catalog --scope existing --report docs/reports/current-laws-audit.json
python -m scripts.backfill_texts --scope existing --resume
python -m scripts.backfill_history --law 11340-2006 --resume
python -m scripts.backfill_history --law 13709-2018 --resume
python -m scripts.backfill_history --scope existing --resume
python -m scripts.reconcile_sources --jurisdiction federal --report docs/reports/federal-reconciliation.json
python -m scripts.backfill_texts --scope all-discovered --resume --batch-size 100
python -m scripts.backfill_history --scope all-discovered --resume --batch-size 100
python -m scripts.coverage_report --all --output docs/reports/national-coverage.json
```

`batch-size 100` é um exemplo ajustável, não limite total do corpus. Cada comando suporta dry run, confirmação do ambiente técnico, checkpoint, idempotência, limites por fonte, saída JSON/humana e código de saída para falhas. `scope existing` refere-se às14 normas atuais para regressão inicial, não restringe catálogo posterior. Não introduzir uma confirmação interativa por lote que impeça automação já autorizada.

## 13. Portões de aceite final

### G1 — funcionamento básico e veracidade

- [ ] Nenhum histórico diz preparando sem job ativo persistido.
- [ ] Jobs/falhas/progresso/retry funcionam na UI e após reload.
- [ ] Atualização falha não destrói versão anterior.
- [ ] Não há default jurídico “Em vigor” sem evidência.

### G2 — texto integral

- [ ] Todas as14 normas atuais auditadas e reprocessadas.
- [ ] Código Civil com milhares corretamente identificados, inclusive Art.2046.
- [ ] Constituição e ADCT separados, sem colisões.
- [ ] Anexos, tabelas, preâmbulos e conteúdo não articulado preservados.
- [ ] Nenhum fragmento jurídico desaparece; selo de estrutura tem evidência própria.
- [ ] Fontes/representações antigas preservadas e reproduzíveis.

### G3 — catálogo e cobertura nacional

- [ ] União, 26 estados, DF e localidades oficiais registradas, com natureza administrativa correta.
- [ ] Todos os registros enumerados de cada fonte integrada catalogados sem teto artificial.
- [ ] Paginação, partições, limites de exportação e denominadores reconciliados.
- [ ] Normas fora das14, antigas/revogadas/sem número, são resolvidas e apresentadas.
- [ ] Busca federal/estadual/municipal funciona com contexto e ambiguidades.
- [ ] Cada lacuna territorial/documental tem estado, motivo e caminho de resolução.
- [ ] Alegação de “todas” só acompanha escopo/denominador verificado; não confundir descoberta parcial com totalidade jurídica nacional.

### G4 — histórico, diff e blame

- [ ] Pipeline genérico substitui hardcode.
- [ ] Texto original e cadeia por norma são descobertos e arquivados.
- [ ] Datas de assinatura/publicação/efeitos são distintas e verificadas.
- [ ] LMP/LGPD têm timeline, antes/depois e recortes reais além do exemplo inicial.
- [ ] Todas as14 têm resultado auditado; lacunas dos códigos não são escondidas.
- [ ] Versões por data só em intervalos comprovados; eventos não processados impedem completo.
- [ ] Diff por versões e blame por dispositivo ligam evidências corretas.
- [ ] Backfill nacional registra cada norma e prossegue de forma retomável.

### G5 — origem e votação

- [ ] Norma→processo liga por prova oficial, não por número igual.
- [ ] Autores/relatores/emendas têm papéis distintos e fontes.
- [ ] Votações estão ligadas ao objeto/fase correta.
- [ ] Votos individuais só quando nominais e disponíveis; indisponibilidade é explicada.

### G6 — produção operável

- [ ] PostgreSQL/Redis/worker/outbox/scheduler e arquivo durável funcionando.
- [ ] Backup/restore, migrações e rollback demonstrados.
- [ ] Suíte pertinente e fluxos públicos validados no SHA implantado.
- [ ] Métricas, freshness e alertas de fonte/fila cobrem falhas reais.
- [ ] Documentação/coverage correspondem aos dados em produção.

## 14. Instrução de handoff para Luna 6

Leia este plano integralmente, o README, `docs/LEIABERTA_ORIGINAL_REQUIREMENTS.md` e as instruções locais. Execute T00 em diante, respeitando dependências e os portões. O trabalho inclui implementação, testes pertinentes, migrações, ingestão real, deploy Railway e validação pública. Não entregue outro plano como substituto da execução.

Antes de cada tarefa, confirme os contratos externos relevantes e identifique seus arquivos, migration e critérios de saída. Depois, implemente uma unidade concreta, valide com evidência oficial, registre resultados e faça commit. Mantenha `docs/reports/execution-status.md` com tarefa/estado/SHA/deploy/contagens/erros/próxima ação e os checkpoints duráveis dos jobs.

Retome até cumprir os requisitos. Uma fonte bloqueada deve gerar issue específica, não interromper tarefas independentes nem virar dado sintético. Um histórico incompleto deve exibir os eventos confirmados e a lacuna, enquanto o pipeline tenta fontes alternativas. A interface precisa parar de prometer trabalho inexistente desde T02, mas o objetivo permanece implementar o histórico real.

Priorize correção de texto e histórico antes de enriquecimento político. Não declarar “tudo funcionando” usando apenas HTTP200, health verde ou quantidade de artigos. A evidência exigida é o fluxo completo com conteúdo correto, intervalos históricos verificados, corpus reconciliado e limites visíveis.

Em cada atualização ao usuário, diga o que concluiu, o que validou, o que está processando e qual bloqueio específico existe. No relatório final, listar os portões G1–G6, resultado de cada um, cobertura efetivamente alcançada e saldo nacional. Se ainda há lacunas ou backfill em andamento, continuar ou declarar exatamente o saldo; nunca encerrar como cobertura integral sem prova.
