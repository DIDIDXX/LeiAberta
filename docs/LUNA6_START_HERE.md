# Luna 6 — comece aqui

## Pedido do usuário

“Quero tudo funcionando”, incluindo histórico real e leis completas de todas as jurisdições. Usar o Railway disponível. Este handoff foi preparado após auditoria do código e pesquisa de fontes oficiais em 04/10/2026.

## Leia nesta ordem

1. [Plano completo de execução](LEIABERTA_LUNA6_EXECUTION_PLAN.md).
2. [Requisitos originais do produto](LEIABERTA_ORIGINAL_REQUIREMENTS.md).
3. [Resultados da pesquisa oficial](research/2026-10-04-source-findings.json).
4. README e eventuais `AGENTS.md` aplicáveis.

O plano completo contém 28 tarefas T00–T27, dependências, modelo de dados, contratos de API, reconstrução histórica, ingestão nacional, testes, runbook Railway e seis portões de aceite. Os comandos novos descritos nele ainda precisam ser implementados.

## Estado após execução e deploy (04/10/2026)

As primeiras entregas de execução já estão em `main` e em produção (PR #1, merge `197da4502a97786abca43d98f2f3f395c32ea648`). Web e worker Railway estão `SUCCESS`: https://web-production-12e95.up.railway.app. O catálogo sincronizou 16.883 leis federais do Senado; o diretório registrou 27 UFs e 5.571 localidades. O worker e a fila durável foram exercitados: preparar o histórico da LGPD em produção retornou 146 relações oficiais, com cobertura `partial`. Home, busca, detalhe, artigo, histórico e uso móvel passaram no smoke test.

“Todas as leis” continua incompleto. A lista do Senado ainda é somente `tipo=LEI`, e a maioria dos registros está no catálogo sem texto integral. Histórico textual genérico, Câmara, LexML, legislativos estaduais/municipais, anexos e auditoria integral continuam pendentes. Não foi possível demonstrar um backup restaurável ou ambiente staging nesta sessão. Consulte [`execution-status.md`](reports/execution-status.md) para números, IDs e evidências do deploy.

## Próximas tarefas de execução

1. Resolver T01 com credencial/CLI ou ações via Dashboard Railway: backup lógico verificável, ambiente staging isolado e restore testado antes de novas migrations em produção.
2. Continuar T04–T08: arquivar resposta de fonte antes do parse, baixar/analisar anexos e implementar auditoria documental por segmento para as leis prioritárias.
3. Ampliar catálogo federal para outros tipos e fontes Câmara; implementar adaptações LexML, ALESP/SINJ e uma jurisdição municipal de piloto, preservando checkpoints e origem.
4. Construir relações históricas e diffs textuais genéricos apenas com evidência de texto anterior/posterior e datas oficiais; medir a cobertura por jurisdição e tipo.
5. Completar operação contínua, scheduler, autoria/processos/votos e os portões restantes descritos no plano integral.

Não terminar depois dos pilotos. LMP/LGPD e fontes estaduais/municipais piloto validam algoritmos; o catálogo e os backfills precisam prosseguir para todas as normas descobertas. Não declarar cobertura nacional completa sem inventário e reconciliação por jurisdição.

## Registro persistente

Criar `docs/reports/execution-status.md` e manter por tarefa:

```text
Tarefa:
Estado: pending | running | complete | blocked
SHA / deployment:
Arquivos / migrations:
Fontes oficiais / IDs:
Dados e intervalos efetivamente processados:
Validações / resultados:
Lacunas e bloqueios específicos:
Checkpoint de retomada:
Próxima ação:
```

Não usar dados fictícios para preencher esse registro. Fontes inacessíveis viram bloqueios específicos; tarefas independentes continuam. Preservar versões/snapshots existentes e links públicos.

## Produção existente

- Repositório: https://github.com/DIDIDXX/LeiAberta.
- Base auditada: `16c78fe888b3507409dbfda0dc951f06d28e0d50`.
- Site: https://web-production-12e95.up.railway.app.
- Railway: web, worker, Postgres e Redis já provisionados; IDs no plano completo.
- Web atende `$PORT`; domínio atual aponta para8080.

Esta entrega já inclui implementação, merge, deploy e smoke público das entregas parciais listadas acima. O trabalho é retomar pelas tarefas restantes, ampliar as fontes sem mascarar lacunas e documentar precisamente o que funciona.
