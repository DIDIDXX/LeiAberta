# Luna 6 — estado da execução

O objetivo ativo é deixar busca, leitura e histórico funcionais, ampliar o corpus e publicar no Railway. Só limitações externas comprovadas ficam como bloqueios; adapters ainda não construídos continuam trabalho executável.

Leia:

1. [Plano e requisitos completos](LEIABERTA_LUNA6_EXECUTION_PLAN.md)
2. [Requisitos originais](LEIABERTA_ORIGINAL_REQUIREMENTS.md)
3. [Relatório atualizado por tarefa](reports/execution-status.md)
4. [Pesquisa e limites de fontes](research/2026-10-04-source-findings.json)

## Código e validação

`main` está no release #7 (`21e5fda147508dd20882ae475b9ad50ab6c9d066`), já implantado no Railway. A branch desta revisão acrescenta o adapter SAPL/Manaus, backfill gradual de textos oficiais e retry transitório para o Senado/DOU. A API SAPL declarou 9.846 normas; a Lei 115/1949 foi baixada como PDF e extraída localmente.

Validação local: **80 testes passaram**, **4 E2E passaram**, `compileall` e `git diff --check` passaram. A migration `0008` está aplicada em produção. A Lei SAPL 115/1949 e um PDF SINJ-DF foram extraídos; páginas digitalizadas seguem o caminho Tesseract português no container Docker.

## Publicação em curso

Publicar a branch SAPL no `main`, aguardar web/worker Railway em `SUCCESS` e conferir `/health`, `/api/stats`, sincronização de 9.846 normas, hidratação PDF, relações do SAPL e backfill ALESP/SINJ. Acompanhar também ALESP em produção, que estava em 120 mil de 181.172 registros na última verificação.

## Estado de cobertura

Produção enumera 47.316 registros do Senado e 125.478 do SINJ-DF; ALESP continua importando (181.172 esperados). A sync completa isolada da ALESP confirmou 181.172. SAPL/Manaus é o novo adapter preparado para enumerar 9.846 normas. O worker enfileira textos em lotes com limites e continua após reinícios; `with_text` cresce durante o backfill.

Esses acervos não correspondem a todas as leis do Brasil. Não existe um endpoint nacional oficial demonstrado que liste os acervos de todas as jurisdições; cada assembleia, Câmara municipal e repositório exige identificação e reconciliação próprios. O adapter SAPL prova a integração de Manaus, sem declarar os demais municípios atendidos.

## Limitações externas verificadas

- Railway Hobby informa `maxBackupsCount=0`. O conjunto de conectores desta sessão não oferece shell, `pg_dump` ou duplicação/restauração de ambiente; backup restaurável/staging não foi demonstrado.
- O probe da rota LexML SRU recebeu página de desafio anti-automação em vez de registros. Requer uma rota autorizada acessível ou mudança no acesso do portal.
- Relações de alteração nem sempre incluem redações anteriores/atuais por dispositivo ou data de vigência. Essas entradas aparecem como relação oficial sem diff inventado.
- O SINJ-DF não anunciava anexo textual para 5.184 registros do snapshot observado; buscar diários/repositórios oficiais alternativos é trabalho pendente.
- Normas.leg.br declara valor jurídico não oficial para muitas transcrições e compilações. O produto conserva o rótulo da fonte.

Não declarar que “todas as leis” estão no catálogo enquanto as jurisdições e seus acervos não forem enumerados e reconciliados individualmente.
