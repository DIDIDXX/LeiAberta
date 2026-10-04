# Luna 6 — comece aqui

## Pedido do usuário

“Quero tudo funcionando”, incluindo histórico real e leis completas de todas as jurisdições. Usar o Railway disponível. Este handoff foi preparado após auditoria do código e pesquisa de fontes oficiais em 04/10/2026.

## Leia nesta ordem

1. [Plano completo de execução](LEIABERTA_LUNA6_EXECUTION_PLAN.md).
2. [Requisitos originais do produto](LEIABERTA_ORIGINAL_REQUIREMENTS.md).
3. [Resultados da pesquisa oficial](research/2026-10-04-source-findings.json).
4. README e eventuais `AGENTS.md` aplicáveis.

O plano completo contém 28 tarefas T00–T27, dependências, modelo de dados, contratos de API, reconstrução histórica, ingestão nacional, testes, runbook Railway e seis portões de aceite. Os comandos novos descritos nele ainda precisam ser implementados.

## Três fatos que devem orientar a execução

- O histórico atual é uma regra específica para três acréscimos da Lei Maria da Penha. Nas demais normas, “está sendo preparado” pode aparecer sem job de histórico.
- O parser do Código Civil extraiu 1.007 artigos e concatenou 174.903 caracteres em `art:1`; a fonte contém o Art. 2.046. Corrigir milhares, IDs, componentes e completude antes de confiar em `ready`.
- A API Senado entrega relações por dispositivo e publicações. A ficha Câmara confirma Lei14.550/2023 → PL1604/2022 e publicação20/04/2023, diferente da assinatura19/04 usada atualmente no campo de publicação.

## Primeira sessão de execução

1. Fazer T00: verificar SHA, ambiente, serviços, dados atuais e instruções.
2. Fazer T01: backup e staging com restauração demonstrada.
3. Fazer T02/T03: estados verdadeiros e jobs duráveis.
4. Continuar T04–T08: arquivo oficial e texto integral corrigido/auditado das14 normas.
5. Prosseguir catálogo nacional T09–T16 e histórico genérico T17–T22 conforme dependências.
6. Concluir origem/votos, operação contínua e releases T23–T27.

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

Esta entrega contém planejamento e pesquisa. Ela não implantou as correções propostas. O seu trabalho é executar, validar e colocar os resultados em produção, documentando precisamente o que já funciona e o que ainda falta.
