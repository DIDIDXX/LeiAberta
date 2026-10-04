# Luna 6 — estado da execução

O pedido é entregar o máximo do LeiAberta funcionando em produção: busca, leitura, histórico apoiado por fonte, catálogo amplo e backfill contínuo. A instrução mais recente pede execução completa e que só fiquem impossibilidades técnicas.

Leia:

1. [Plano e requisitos completos](LEIABERTA_LUNA6_EXECUTION_PLAN.md)
2. [Requisitos originais](LEIABERTA_ORIGINAL_REQUIREMENTS.md)
3. [Relatório atualizado por tarefa](reports/execution-status.md)
4. [Pesquisa e limites de fontes](research/2026-10-04-source-findings.json)

## Código preparado nesta execução

Release principal: SHA `1cd6efd` em `main`, deploy web `a93562ef-8f8e-4eaa-ba7c-1976a8be6d2b` e worker `9cbd77e7-a25c-497f-8301-ad23dc86d49c`, ambos `SUCCESS`. O patch seguinte corrige a indicação de job histórico e usa duas capturas simultâneas por worker; valide e publique esse patch antes de encerrar.

O release inclui catálogo Senado para `LEI`, `LCP`, `EMC`, `MPV`, `DLG`, `RSF`; procura por número/ano e reedições MPV; captura Normas.leg.br; histórico com diferenças comprovadas; arquivo bruto antes de parsing; auditoria estrutural; backfill de 100 textos por lote a cada cinco minutos; estatísticas de cobertura.

Validação: **44 testes unitários e 4 E2E passaram**. O catálogo real isolado enumerou **47.327 entradas** sem erros; a segunda sincronização não duplicou identidades. Em produção, `/api/stats` mostrou 47.330 normas, 47.316 do Senado, 135 textos obtidos e 5 indisponíveis no ponto consultado. O job real da LGPD concluiu: **146 referências, 54 comparações antes/depois e 98 relações pendentes**. A busca pública distingue `MPV 2.206/2001` e `MPV 2.206-1/2001`; a reedição estruturou 10 artigos. Transcrições do Normas.leg.br são classificadas pelo próprio portal como valor jurídico não oficial.

## Publicação

Depois de atualizar esta documentação e os manifests finais, publique no GitHub e espere os serviços web/worker do Railway em `SUCCESS`. O endereço conhecido é https://web-production-12e95.up.railway.app. Confirme `/health`, `/api/stats`, busca de uma lei, busca de uma MPV com sufixo, o estado de um texto em backfill e histórico da LGPD. Atualize `reports/execution-status.md` com SHA e deployment IDs reais. Não copie contagens locais como se fossem produção.

## Impedimentos comprovados

- Railway Hobby tem `maxBackupsCount=0`, e as ferramentas conectadas não dão shell, CLI ou GraphQL para exportar/dumpar ou duplicar ambiente. Nenhum backup restaurável ou staging foi criado nesta execução.
- A API do Senado entrega seis tipos catalogáveis, não todo o universo de leis brasileiras. Não existe endpoint nacional único para os acervos estaduais e municipais.
- Normas.leg.br oferece conteúdo utilizável, mas o próprio portal marca essas transcrições/compilações como valor jurídico não oficial.
- Relações históricas nem sempre possuem redação anterior/posterior e data de vigência; texto ausente permanece pendente, nunca inventado.

As tarefas de Câmara, assembleias, câmaras municipais, anexos/PDF, autoria, projetos e votos não estão implementadas neste lote. Consulte a matriz de execução para a fonte específica que precisa ser confirmada em cada família. Não afirme que essas tarefas estão concluídas ou que o Brasil inteiro foi sincronizado.
