# E — QA de produto e lançamento

**Execução:** 2026-10-06 17:26 UTC; captura complementar 17:28 UTC

**Ambiente:** produção `https://web-production-12e95.up.railway.app`

**SHA do app observado pela coordenação:** `eb7cea7ddf22737b30bd4f21285f7ea15e26891d` (`main`)

**Branch desta entrega:** `codex/final-product-qa`, baseada em `eb7cea7ddf22737b30bd4f21285f7ea15e26891d`

**Escopo:** QA somente de leitura na produção; correção de texto e teste local isolado nesta branch. Nenhuma alteração de produção ou de dados jurídicos.

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

**Teste focalizado:**

```text
npm run test:e2e -- --grep 'real existing article|federal article'
2 passed (3.5s)
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
