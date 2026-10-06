# Agent

`product-hero-evidence` (Agente 4)

# Branch

`codex/product-hero-evidence`

# Base SHA

`22ab2262678e040879f6220bae4f5c4c23afc4aa`

## Findings

- O hero vigente é o art. 389 do Código Civil (Lei 10.406/2002), atualizado pela Lei 14.905/2024. O par é claro, conhecido, curto o suficiente para um diff legível e representa um artigo que existia antes da alteração.
- A comparação armazenada pelo app continua apontando para uma versão do Normas.leg.br. A interface corretamente chama o registro de “Comparação registrada” e informa que o próprio Normas classifica a transcrição como valor jurídico não oficial. Isso não deve virar “Fonte primária confirmada” apenas por haver outros links oficiais na página.
- A pesquisa encontrou fontes legislativas primárias para auditar independentemente os dois lados do art. 389: a publicação/republicação oficial da Lei 10.406 na Câmara preserva a redação anterior, e a publicação original da Lei 14.905 na Câmara, além da página da lei no Planalto, é o ato modificador e contém a redação nova. Isso permite construir um caso de alta qualidade sem trocar de dispositivo; falta que o produto armazene e apresente essas referências distintas como evidência do lado anterior, do lado posterior e do ato.
- A produção estava em falha no momento desta inspeção: `/health`, `/api/stats`, `/api/laws/10406-2002`, `/api/laws/10406-2002/history` e `/api/changes/be3a1531-edaa-5a78-94ca-70c6544e3853` retornaram HTTP 500 em amostras de 06/10/2026 UTC. Por isso, não validei deep links, status legal ou comportamento mobile no site ao vivo. Não fiz alterações de produção.
- Produto: existiam deep links endereçáveis para lei/artigo, diff e evidência em Blame; faltava uma ação acessível para copiar o URL dessas três páginas. O diff também não oferecia um caminho direto ao artigo atual.

## Measurements

- Referências oficiais do art. 389:
  - Redação anterior: [Câmara — republicação atualizada da Lei 10.406/2002](https://www2.camara.leg.br/legin/fed/lei/2002/lei-10406-10-janeiro-2002-432893-republicacaoatualizada-1-pl.html). O resultado da busca contém o texto anterior integral do art. 389.
  - Ato e redação nova: [Câmara — publicação original da Lei 14.905/2024](https://www2.camara.leg.br/legin/fed/lei/2024/lei-14905-28-junho-2024-795872-publicacaooriginal-172245-pl.html).
  - Confirmação do ato: [Planalto — Lei 14.905/2024](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/lei/l14905.htm).
  - Texto consolidado atual: [Planalto — Código Civil](https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm).
- Candidatos avaliados (evidence level abaixo descreve os documentos oficiais encontrados; não afirma que o banco de produção já guarda essas comparações):

  | Caso | Fontes primárias localizadas | Evidência | Avaliação para o hero |
  | --- | --- | --- | --- |
  | Código Civil, art. 389 — Lei 14.905/2024 | Câmara, republicação oficial da Lei 10.406/2002 para o antes; Câmara, publicação original da Lei 14.905/2024 e Planalto para o ato/depois | Alta para auditar o par com fontes oficiais. O registro persistido usado pelo app ainda é Normas, de valor jurídico não oficial | **Manter.** Caso conciso, existente antes, par já validado pelo produto e sem precisar afirmar vigência/autoria. Requer ligar explicitamente cada lado à publicação oficial antes de chamar o diff de primário. |
  | CLT, art. 477 — Lei 13.467/2017 | [Câmara — republicação atualizada da CLT](https://www2.camara.leg.br/legin/fed/declei/1940-1949/decreto-lei-5452-1-maio-1943-415500-normaatualizada-pe.html); [Câmara — publicação original da Lei 13.467/2017](https://www2.camara.leg.br/legin/fed/lei/2017/lei-13467-13-julho-2017-785204-publicacaooriginal-153369-pl.html); [tramitação oficial do PL 6.787/2016](https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2129283) | Alta para ato/after e processo; a página oficial da CLT traz a redação vigente com nota da Lei 13.467. Antes deve ser reconstruído da versão pré-vigência, e o artigo tem várias alterações/revogações | Forte reconhecimento, mas amplo e difícil de sintetizar no screenshot. Exige escolher um parágrafo/segmento exato e reconciliar alterações colaterais. |
  | Constituição, art. 201, § 7º, I — EC 103/2019 | [Planalto — EC 103/2019](https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc103.htm); [Câmara — texto constitucional atualizado e anotações](https://www.camara.leg.br/internet/infdoc/novoconteudo/html/leginfra/ArtCF2262.htm); [Câmara — processo da PEC 6/2019](https://www2.camara.leg.br/atividade-legislativa/discursos-e-notas-taquigraficas/discursos-em-destaque/pec-6-2019/proposta-de-emenda-a-constituicao-no-6-de-2019-reforma-da-previdencia) | Alta para emenda e texto pós-alteração; a Câmara registra as redações dadas em 1998 e 2019. Para o antes exato, precisa fixar versão constitucional imediatamente anterior à EC 103 e distinguir a regra transitória do art. 19 da emenda | Maior força de história legislativa e interesse público, porém há transição, judicialização e versão prévia a reconstruir. Não há evidência nesta execução de que o diff esteja disponível no catálogo do produto. |
  | CTB, art. 147 — Lei 14.071/2020 | [Câmara — publicação original da Lei 14.071/2020](https://www2.camara.leg.br/legin/fed/lei/2020/lei-14071-13-outubro-2020-790722-publicacaooriginal-161648-pl.html); [Câmara — promulgação de vetos](https://www2.camara.leg.br/legin/fed/lei/2020/lei-14071-13-outubro-2020-790722-promulgacaodevetos-162546-pl.html); [PL 3.267/2019](https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2206203) | Alta para ato promulgado e processo; caput do art. 147 passou por veto, rejeição e promulgação posterior | Reconhecível, mas a história do veto/promulgação complica o antes/depois e cria risco de apresentar um texto vetado como vigente. Não supera o CC. |

- Validação local: `npm run test:e2e` — 2 passaram. O E2E agora visita o diff do art. 389, copia e confere seu deep link, abre o artigo atual pelo caminho direto, copia o link do artigo, segue para a evidência e copia o deep link selecionado. O fluxo da comparação e da evidência roda a 390 px e verifica ausência de overflow horizontal.
- `node --check static/app.js`, `node --check e2e/core-flow.spec.js` e `git diff --check` passaram.

## Decisions

- Manter o art. 389 no hero. As alternativas são interessantes, mas nenhuma foi provada como um par oficial melhor já consumível por este produto; mudar o artigo só pelo apelo da narrativa enfraqueceria a aceitação legal.
- A próxima melhoria de evidência deve guardar links/trechos/checksums por lado (`before`, `after`) e o link oficial do ato, mantendo a referência do Normas identificada como transcrição não oficial. Só então o badge pode subir para evidência primária.
- Adicionar a ação `Copiar link` ao artigo aberto, diff e evidência de Blame; usar a URL atual completa para preservar `node` e demais parâmetros. Acrescentar ao diff um link direto ao artigo atual.
- A falha de produção foi reportada ao coordenador; não fazer alteração Railway, produção, worker, ingestão ou banco neste branch.

## Changes

- Incluída ação de cópia de URL nos artigos direcionados, páginas de comparação e páginas Blame com dispositivo selecionado.
- Cópia usa Clipboard API, com fallback de seleção para browser/contexto sem Clipboard API, e confirma sucesso/erro em região acessível `role=status` / `aria-live=polite`.
- O diff agora aponta diretamente para a página atual do artigo afetado.
- E2E cobre cópia do URL do diff, artigo e evidência e testa largura móvel no diff e Blame.

## Files touched

- `static/app.js`
- `static/styles.css`
- `e2e/core-flow.spec.js`
- `docs/swarm/product-hero-evidence.md`

## Tests

- `npm run test:e2e` — passou (2/2) em ambiente local seedado.
- `node --check static/app.js` — passou.
- `node --check e2e/core-flow.spec.js` — passou.
- `git diff --check` — passou.
- Produção não validada: as chamadas observadas retornaram HTTP 500.

## Production impact

Nenhum. Não acessei nem alterei configuração ou dados de produção. O coordenador deve revalidar produção depois da estabilização do incidente P0.

## Migration impact

Nenhum.

## Cost impact

Negligível; sem serviços, chamadas de rede ou persistência adicionais.

## Risks

- Clipboard API pode ser bloqueada pelo navegador/permissões; há fallback `execCommand` e mensagem acessível explicando como copiar o endereço manualmente.
- Para transformar art. 389 em hero primário, não basta adicionar mais um link: é necessário registrar qual fonte sustenta exatamente o texto anterior e o posterior e manter a ressalva do registro original enquanto isso não for feito.
- Os 500 em produção impedem validar os deep links e o conteúdo real durante esta execução.

## Rollback

Reverter o commit/PR deste branch restaura as páginas sem os controles de cópia. Nenhum dado de produção ou migration precisa de rollback.

## Dependencies on other agents

- Coordenador/SRE deve recuperar e validar a API de produção antes da integração e do smoke do fluxo público.
- A equipe que mantém histórico/evidência deve, se decidir promover a força do hero, armazenar as fontes distintas para o antes, depois e ato. Este branch não mexe nesses dados.

## PR / commit

A criar após validar o commit local.
