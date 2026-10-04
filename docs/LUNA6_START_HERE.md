# Luna 6 — estado da execução

O pedido é entregar o máximo do LeiAberta funcionando em produção: busca, leitura, histórico apoiado por fonte, catálogo amplo e backfill contínuo. A instrução mais recente pede execução completa e que só fiquem impossibilidades técnicas.

Leia:

1. [Plano e requisitos completos](LEIABERTA_LUNA6_EXECUTION_PLAN.md)
2. [Requisitos originais](LEIABERTA_ORIGINAL_REQUIREMENTS.md)
3. [Relatório atualizado por tarefa](reports/execution-status.md)
4. [Pesquisa e limites de fontes](research/2026-10-04-source-findings.json)

## Código preparado nesta execução

Base local: commit `b42466a` na branch `main`; as alterações desta execução ainda aguardam publicação. Incluem catálogo Senado para `LEI`, `LCP`, `EMC`, `MPV`, `DLG`, `RSF`; procura por número/ano e reedições MPV; captura Normas.leg.br; histórico com diferenças comprovadas; arquivo bruto antes de parsing; auditoria estrutural; worker para hidratar 100 textos por lote a cada cinco minutos; estatísticas de cobertura.

Evidência local: **42 testes unitários e 4 E2E passaram**. O catálogo real isolado enumerou **47.327 entradas** sem erros; uma segunda sincronização não duplicou identidades. A integração LGPD guardou **54 comparações de antes/depois** e preservou **98 relações sem texto histórico** como pendentes. A captura de `MPV 2.206-1/2001` estruturou 10 artigos e 35 nós. Transcrições do Normas.leg.br são classificadas pelo próprio portal como valor jurídico não oficial.

## Publicação

Depois de atualizar esta documentação e os manifests finais, publique no GitHub e espere os serviços web/worker do Railway em `SUCCESS`. O endereço conhecido é https://web-production-12e95.up.railway.app. Confirme `/health`, `/api/stats`, busca de uma lei, busca de uma MPV com sufixo, o estado de um texto em backfill e histórico da LGPD. Atualize `reports/execution-status.md` com SHA e deployment IDs reais. Não copie contagens locais como se fossem produção.

## Impedimentos comprovados

- Railway Hobby tem `maxBackupsCount=0`, e as ferramentas conectadas não dão shell, CLI ou GraphQL para exportar/dumpar ou duplicar ambiente. Nenhum backup restaurável ou staging foi criado nesta execução.
- A API do Senado entrega seis tipos catalogáveis, não todo o universo de leis brasileiras. Não existe endpoint nacional único para os acervos estaduais e municipais.
- Normas.leg.br oferece conteúdo utilizável, mas o próprio portal marca essas transcrições/compilações como valor jurídico não oficial.
- Relações históricas nem sempre possuem redação anterior/posterior e data de vigência; texto ausente permanece pendente, nunca inventado.

As tarefas de Câmara, assembleias, câmaras municipais, anexos/PDF, autoria, projetos e votos não estão implementadas neste lote. Consulte a matriz de execução para a fonte específica que precisa ser confirmada em cada família. Não afirme que essas tarefas estão concluídas ou que o Brasil inteiro foi sincronizado.
