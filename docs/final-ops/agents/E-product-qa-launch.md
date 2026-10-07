# E — QA de produto e lançamento

**Execução:** 2026-10-06 17:26 UTC; captura complementar 17:28 UTC

**Ambiente:** produção `https://web-production-12e95.up.railway.app`

**SHA do app observado pela coordenação:** `eb7cea7ddf22737b30bd4f21285f7ea15e26891d` (`main`)

**Branch desta entrega:** `codex/final-product-qa`, baseada em `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`

**Escopo:** QA somente de leitura na produção; correção de texto e teste local isolado nesta branch. Nenhuma alteração de produção ou de dados jurídicos.

> O resultado e o bloqueio descritos abaixo registram a captura de 2026-10-06. A seção “Revalidação de produção — 2026-10-07” ao fim deste arquivo substitui o estado de produção daquele retrato.

## Resultado de produção

### Disponibilidade e APIs

Às 17:26:48 UTC, todas as rotas consultadas responderam HTTP 200:

| Rota | Latência | Evidência observada |
|---|---:|---|
| `/health`, `/ready`, `/worker-health` | 432–468 ms | JSON de saúde, prontidão e worker |
| `/api/stats` | 512 ms | 1.927.120 itens catalogados; 14.107 normas com texto; 51.360 artigos estruturados; 376 alterações documentadas |
| `/api/sources` | 1.512 ms | 620 registros de fonte |
| `/api/search?q=LGDP` | 430 ms | sugestão aproximada para Lei 13.709/2018 (LGPD), `suggestion=true` |
| `/api/laws/10406-2002` | 513 ms | Código Civil, Lei 10.406/2002; fonte de texto Planalto; cobertura parcial |
| `/api/laws/10406-2002/history` | 1.117 ms | histórico parcial, 255 referências aguardam texto comparável |
| `/api/laws/10406-2002/blame?node_id=art%3A389&limit=5` | 491 ms | uma evidência selecionada para Art. 389 |
| `/api/laws/10406-2002/nodes/art%3A389/provenance` | 447 ms | `status=verified`, `evidence.level=verified_source` |
| `/api/changes/be3a1531-edaa-5a78-94ca-70c6544e3853` | 639 ms | comparação do Art. 389; `evidence.level=verified_source`, `source_host=normas.leg.br` |
| `/fontes`, `/cobertura`, `/sobre` | 417–493 ms | shell HTML servido; os dados de fontes/cobertura são carregados pelo cliente |
| `/openapi.json`, `/sitemap.xml` | 785 ms, 532 ms | JSON 11.092 bytes; XML 18.152 bytes |

`/cobertura` carregou 1.927.120 registros, 14.107 normas com texto e 616 fontes enumeradas. As telas `/fontes`, `/cobertura` e a busca aproximada renderizaram os dados após as chamadas de API. A tela de fontes mostra 620 registros.

### Código Civil, Art. 389

O deep link `/lei/10406-2002/artigo/389` respondeu e renderizou a norma; o artigo oferece “Por que este artigo está assim?”. O painel Blame liga o dispositivo à Lei 14.905/2024 e leva ao diff `be3a1531-edaa-5a78-94ca-70c6544e3853`. A página de comparação mostra os textos anterior e posterior e links para a versão comparada e para o texto do Código Civil no Planalto.

O caveat já aparece claramente na página Diff: a comparação está registrada na versão citada do Normas.leg.br, a transcrição é classificada pelo portal como valor jurídico não oficial e a data do registro não confirma vigência. A API confirma essa distinção: `source_url` aponta para Normas.leg.br e `evidence.level` é `verified_source`, não `verified_primary`; os metadados da lei informam `legal_value=UnofficialLegalValue` e pedem confirmação das datas de vigência. O Planalto é o link do texto atual do Código Civil, mas esta QA não comprovou nele os trechos exatos anterior e posterior.

**Falha encontrada na produção:** o painel Why/Blame para esse mesmo dispositivo ainda dizia “O ato abaixo tem comparação de texto registrada em fonte oficial” e chamava o link de “Abrir norma modificadora oficial”. Isso contradiz a classificação da evidência e o caveat presente no Diff. Capturas de produção antes da correção local:

- [Diff do Art. 389 em 390 px](../evidence/2026-10-06-diff-390.png)
- [Why/Blame do Art. 389 em 390 px — texto inconsistente atual em produção](../evidence/2026-10-06-why-390.png)
- [Página inicial em 390 px](../evidence/2026-10-06-home-390.png)
- [Diff do Art. 389 em 1440 px](../evidence/2026-10-06-diff-1440.png)
- [Why/Blame do Art. 389 em 1440 px — texto inconsistente atual em produção](../evidence/2026-10-06-why-1440.png)
- [Página inicial em 1440 px](../evidence/2026-10-06-home-1440.png)

Não alterei a classificação jurídica dos dados nem promovi o diff a evidência primária.

## Correção local desta branch

Em [static/app.js](../../static/app.js), o painel selecionado agora escolhe o texto pela origem da evidência. Para `normas.leg.br`, explica que a transcrição é classificada como não oficial e que a data não confirma vigência; o link é rotulado como versão da comparação no Normas.leg.br. Fontes primárias verificadas e comparações registradas em outras fontes recebem texto diferente. A descrição da página também deixou de declarar genericamente que todos os atos mostrados são verificados.

Atualizei o E2E em [core-flow.spec.js](../../e2e/core-flow.spec.js) para verificar o caveat, conferir que o painel não diz “em fonte oficial” e validar o rótulo/link do Normas.leg.br. Esse teste usa fixture no servidor local e não altera produção.

Após a revalidação de 2026-10-07, também acrescentei um separador de apresentação antes do marcador anexado `Produção de efeitos`, sem mudar o payload/API ou texto armazenado. O teste local de renderização injeta o marcador somente na resposta da fixture de teste; isso não simula cobertura ou evidência jurídica.

**Teste focalizado:**

```text
npm run test:e2e -- --grep 'real existing article|federal article|renders a separator'
3 passed (5.2s)
git diff --check — passou
```

O E2E local ainda exerce a fixture arquivada do Art. 389; ele não demonstra validação jurídica independente nem substitui o smoke da produção. Nenhum deploy foi feito nesta branch.

## Layout, navegação e console

- Diff do Art. 389 carregado integralmente em 390, 430, 768 e 1440 px. `scrollWidth == clientWidth` em cada largura; sem overflow horizontal.
- Página inicial observada sem overflow em 390, 430, 768 e 1440 px.
- Fontes, cobertura, sobre e busca com typo renderizados sem overflow em 390 e 1440 px.
- Em 390 px, artigo, histórico, blame e Why carregaram seus dados e continuaram sem overflow.
- Sem `pageerror`, mensagens `console.error` ou respostas HTTP 5xx nos percursos de navegador medidos.
- Primeiro Tab na página inicial de produção leva ao link “Pular para o conteúdo”, com outline sólido de 3 px. A primeira tentativa anterior focou o logo por ter clicado nele antes de Tab; a verificação final sem clique confirmou o skip link.
- Os três controles de cópia em Diff, artigo e Why copiaram o URL canônico da página e anunciaram “Link copiado.”.

As capturas de Diff mostram a comparação em duas colunas no desktop e em painéis empilhados no mobile; o caveat continua legível. Não foi executada hidratação cold: testar isso em produção criaria/enfileiraria trabalho e sairia do escopo de QA estritamente read-only definido pela coordenação.

## Handoff, riscos e rollback

- QA de produto: rotas, APIs, busca typo, navegação, layout e links profundos estão funcionais no SHA de produção acima.
- **Bloqueio para GO:** a produção ainda contém a redação enganosa do Why/Blame mostrada nas capturas. A correção local precisa ser revisada, integrada, implantada e revalidada em produção antes de declarar esse caveat uniforme entre Diff e Blame.
- Também não houve teste end-to-end de hidratação sob demanda nem confirmação de trechos anterior/posterior em fonte primária; manter esses limites explícitos.
- Rollback do patch: reverter somente o commit desta branch que altera `static/app.js` e `e2e/core-flow.spec.js`; nenhuma migration ou dado foi alterado.

## Revalidação de produção — 2026-10-07

**Janela observada:** 13:55–14:03 UTC. Nenhuma mudança de produção foi feita.

O inventário Railway indicou `web` na branch `main`, deploy `SUCCESS` `e161e005-7ead-456b-b92a-4a5f5829e994`, SHA `a17ad2c415d9f036096d07719c710d9be58f1a08`, região `asia-southeast1-eqsg3a`; não havia mudança staged. O deploy foi criado em 2026-10-06 20:28:52Z. Esse deploy contém a correção local da ressalva descrita acima.

### Smokes HTTP e APIs

Às 13:55:58 UTC, todas as 16 rotas consultadas responderam HTTP 200: `/`, `/health`, `/ready`, `/worker-health`, `/api/stats`, `/api/sources`, `/api/search?q=LGDP`, `/api/laws/10406-2002`, histórico, blame selecionado, provenance, change `be3a1531-edaa-5a78-94ca-70c6544e3853`, `/fontes`, `/cobertura`, `/sobre`, `/openapi.json` e `/sitemap.xml`. As latências medidas ficaram entre 449 ms e 1.550 ms; `/api/sources` retornou cerca de 2,75 MB.

Às 13:59:54 UTC, a API publicou 1.927.327 registros catalogados, 14.108 normas com texto, 51.360 artigos estruturados, 376 alterações documentadas, 620 fontes configuradas e 612 enumeradas. `/api/sources` retornou 620 itens. A busca `LGDP` continuou sugerindo Lei 13.709/2018 (LGPD). O histórico do Código Civil permanece parcial, com redações anteriores ainda pendentes em parte das referências.

O provenance de Art. 389 continua `status=verified`, `evidence.level=verified_source`, `source_host=normas.leg.br`; a API da comparação também não a classifica como `verified_primary`. O metadado `legal_value=UnofficialLegalValue` e a ressalva de vigência permanecem visíveis.

### Navegador real e imagens

Playwright headless abriu 10 rotas públicas (home, busca, Código Civil, Art. 389, histórico, Why/Blame, Diff, fontes, cobertura e sobre) nos viewports 390, 430, 768 e 1440 px: 40 combinações. Todas receberam HTTP 200, encontraram o conteúdo esperado e apresentaram `scrollWidth == clientWidth`. Não houve `pageerror`, `console.error`, request failed ou HTTP 5xx nos percursos finais.

Fluxos exercitados: hero da home → Diff; Diff → evidência Why/Blame; Art. 389 → link Why; histórico → Diff específico do Art. 389; busca aproximada com typo; cópia de deep links do artigo, comparação e evidência. Os três botões anunciaram “Link copiado.” e a área de transferência recebeu o URL correto. Primeiro Tab na home focou “Pular para o conteúdo”, com outline sólido de 3 px.

As capturas de tela são do site público no deploy `a17ad2c`:

- 390 px: [home](../evidence/2026-10-07-home-390.png), [Diff Art. 389](../evidence/2026-10-07-diff-390.png), [Why/Blame](../evidence/2026-10-07-why-390.png)
- 1440 px: [home](../evidence/2026-10-07-home-1440.png), [Diff Art. 389](../evidence/2026-10-07-diff-1440.png), [Why/Blame](../evidence/2026-10-07-why-1440.png)

### Limite observado

O corpo atual do Art. 389 é servido pela API com “...honorários de advogado.Produção de efeitos”, sem espaço ou quebra entre o texto e a anotação. A captura de produção reproduz essa junção tanto no artigo quanto em Why/Blame. Acrescentei nesta branch um separador somente de apresentação; não alterei o parser, payload/API nem texto armazenado. A alteração continua local e não foi implantada.

Hidratação de norma fria/job de usuário continua sem teste de produção: qualquer POST poderia criar fila e gravar dados, fora do escopo read-only desta revalidação.

## Rechecagem de lançamento — 2026-10-07

- Produção `a17ad2c` revalidada: 16+ rotas/APIs usadas no smoke responderam 200. Stats: 1.927.327 indexados, 14.108 materializados, 51.360 artigos, 376 alterações, 620 fontes configuradas/612 enumeradas. Busca `LGDP` apresentou sugestão para LGPD.
- Playwright real: 10 rotas × 390/430/768/1440 = 40 casos, zero overflow, console/page error, request failure ou HTTP 5xx. Art.389/Why/Blame/History/Diff, fonte, keyboard skip link e cópia de deep links passaram. Capturas de 07/10 estão em `docs/final-ops/evidence/2026-10-07-*.png`.
- Caveat Normas.leg.br está agora explícito no Why/Blame e Diff como transcrição de valor jurídico não oficial; trechos exatos primários anterior/posterior não foram comprovados.
- Correção local separa a anotação visual `Produção de efeitos`; não modifica texto, parser, API ou fonte. E2E focal da agente: 3 passed. Também é preciso integrar/deploy e verificar essa tela de produção.
- Hidratação fria real `manaus-sapl-2198`, job `b5104e15-f6ec-41c7-a16b-f295dcf8bfad`: worker iniciou o fetch com backfill OFF e a fonte oficial time-out às 14:13:47Z; status permaneceu `retry_wait` na última amostra 14:19:31Z. Coordenador identificou gate do retry interativo e preparou patch local. A resposta final permanece pendente de deploy/retry até status terminal.
- Site público e release `v0.1.0` estão ativos, mas About GitHub ainda não tem metadados; a sessão GitHub disponível está deslogada e a credencial local `gh` inválida. Posts não foram publicados.

## Revalidação do coordenador — 2026-10-07 15:09 UTC

- Produção agora está no SHA `c6e74a3c47fa7b5edb4a596ecf10c59a27860370`; o browser passou pelo art. 389, Why/Blame/Diff e caveat Normas.leg.br não oficial. As capturas visuais publicáveis foram regeneradas pós-deploy e adicionadas à pasta `docs/launch/assets/` (Diff desktop, Blame desktop, artigo mobile), com alt text em `docs/launch/MEDIA.md`.
- O teste controlado da lei fria `manaus-sapl-2198` chegou ao worker e falhou honestamente após cinco tentativas por timeout SAPL, sem texto ou artigos estruturados. O código revalida o job real como `failed`, mas a interface escondia o estado: GET seguinte criava outro job durante cooldown de seis horas. Isso foi corrigido localmente em `app/main.py`/`static/app.js`; o patch só será considerado validado quando o PR chegar à produção, a interface mostrar falha da fonte e o GET subsequente não criar job. O botão de retry explícito continua possível.
- Regressões locais desse patch: pytest total 212 passed, Playwright 7 passed, incluindo renderização de timeout terminal com API local roteada, compileall e diff check passaram. Nenhum desses testes locais substitui o smoke visual na produção após deploy.
- Registros, contagens jurídicas ou evidências não foram alterados para maquiar o timeout; a fonte Manaus permanece linkada para consulta e o status tem de dizer que nenhum texto estruturado foi obtido.
- **Handoff atual:** code patch e screenshots aguardam PR/deploy; About GitHub ainda depende de sessão autenticada. GO continua bloqueado até o novo comportamento ser verificado visualmente e houver janela de soak pós-deploy. Não há post publicado.

## Integração final — 2026-10-07 15:20 UTC

- O patch está no branch de trabalho local `codex/launch-hydration-cooldown-20261007`; E2E de regressão adicional cobre a tela local (falha terminal visível, sem falso progresso e sem polling repetido). Python 212/212 e E2E 7/7 passaram antes do commit local.
- A atualização não chegou a produção: serviço live permanece no commit `c6e74a3`. GitHub app write deu erro interno em blob/file; HTTPS push não autenticado e SSH sem public key. Não foi aberto PR nem disparado CI. Sessão web mostrou “Sign in”; Mac bloqueado.
- Job real de Manaus em produção falhou após timeout externo e foi novamente enfileirado sob código anterior, confirmação do bug de apresentação/retry que a regressão cobre localmente. É necessária integração autenticada para revisar/deployar e então repetir o browser QA na lei fria sem criar novas tentativas por GET.
- Decisão permanece NO-GO. Nenhum artigo, fonte ou evidência jurídica foi modificado; nenhum post publicado.
