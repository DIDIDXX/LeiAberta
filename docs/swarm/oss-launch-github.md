# Agente 5 — OSS, GitHub e custo

Data da revisão: 06/10/2026. Worktree `codex/oss-launch-github`, base `22ab2262678e040879f6220bae4f5c4c23afc4aa`.

## Revisão e alterações

- README mantém links para o demo, diff real, API, contribuição, captura e vídeo; links internos de rotas públicas (`fontes`, `cobertura`, `sobre`) agora usam a URL absoluta da produção para funcionar também no GitHub.
- README ganhou uma política operacional de custo: manter a descoberta automática do catálogo, controlar materialização profunda/backfill, medir antes/depois em janelas comparáveis e não chamar projeção por tarifa de custo observado.
- README direciona relatos de erros jurídicos ao formulário de issues existente. Não afirma que há provedor de pagamento nem que o CTA `SUPPORT_URL` já existe.
- O estudo de caso e a análise de custo separam preço-modelo de custo faturado e evitam afirmar economia, prevenção de incidente ou estabilidade sem séries pós-mudança e evidência correspondente.
- A release pública `v0.1.0` foi confirmada por `gh release list`; esta rodada documental não altera nem sobrescreve essa release.

## Estado do custo

O custo real segue **desconhecido até medir o uso após as mudanças e conferir a fatura/plano Railway**. A análise existente contém um proxy de recursos baseado em janela de 24 horas e tarifas públicas, aproximadamente US$ 28,08/mês de compute na fotografia utilizada, mais storage/egress estimados. Isso não é invoice, preço atual confirmado, economia pós-mudança ou run rate. Dados de uso, fatura e medições equivalentes precisam ser coletados para qualquer comparação Before/After.

A política que deve guiar operações é preservar descoberta automática de metadados, limitar hidratação pesada, deixar backfill pausável e priorizar pedidos interativos quando há contenção. O estado em produção deve ser verificado no commit final do Agente 2 antes de o README/case study apresentar uma mudança operacional como concluída.

## Evidência sobre falhas e incidentes

Não introduzi alegações de incidente, causa-raiz ou taxa de falha sem evidência observável. Os documentos de auditoria contêm ocorrências pontuais rastreáveis, como o timeout de `/api/stats` na janela indicada em `docs/audits/production-baseline.md`, o healthcheck 503 observado às 22:07 UTC em `docs/launch/WORKLOG.md` e duas falhas de deploy monitoradas em `docs/reports/post-audit-status.md`; cada item está descrito com momento/contexto e posterior recuperação quando observada. Esses registros não demonstram uma taxa de incidentes nem, sozinhos, causalidade. Uma afirmação de melhoria deve citar métricas/logs comparáveis depois da alteração.

## Metadados do repositório — aplicar manualmente

A leitura pela integração confirmou que descrição, website e topics estão vazios. A edição anterior retornou `403 Resource not accessible by integration`. Com permissão administrativa, o mantenedor pode abrir **Settings → General** em <https://github.com/DIDIDXX/LeiAberta/settings> e preencher exatamente:

- **Description:** `Open-source traceability layer for Brazilian legislation: text, amendments, provenance and official sources.`
- **Website:** `https://web-production-12e95.up.railway.app`
- **Topics:** `brazil`, `legislation`, `civic-tech`, `open-data`, `legaltech`, `data-engineering`, `fastapi`, `postgresql`, `open-source`.

Salvar e confirmar visualmente os três campos. Não retentei escrita com a integração sem permissão.

## Suporte opcional

O código da base deste worktree não usa `SUPPORT_URL`, e o repositório não contém `.github/CODEOWNERS`. Esta tarefa não alterou runtime. O comportamento esperado, se o responsável pela interface incorporar a opção, é esconder o CTA quando `SUPPORT_URL` estiver ausente/vazio e exibir link discreto somente com uma URL válida. Não criar conta de pagamento. O destino existente para suporte comunitário/erros é o issue chooser do GitHub: <https://github.com/DIDIDXX/LeiAberta/issues/new/choose>.

## Handoff operacional

- P0: aplicação não está pronta: Railway mostra os containers como Online/SUCCESS, mas o smoke público mais recente retornou `/health` 500 e `/ready` 503; a home `/` retornou 200. A exclusão staged antiga de `pg-diagnostic` foi descartada; não houve remoção nem alteração desse serviço ativo.
- A tentativa autorizada de `accept-deploy` limpou a alteração staged sem redimensionar o volume. A leitura atual confirma nenhum staged change, `postgres-volume` ainda em 5.000 MB e métrica recente de 4,9965 GB ocupados. O bloqueio manual agora é o proprietário ajustar o volume para 6.500 MB pelo Dashboard com 2FA; revisar o preview e aplicar somente se a única mudança for esse resize. Nenhum outro serviço ou dado foi alterado. Health/readiness e rota pública continuam pendentes de recuperação. Instruções estão em `docs/launch/MANUAL_ACTIONS.md`.
- Railway Pro Observability Disk Usage em 70/80/85% envia alertas ao Dashboard, mas não pausa o worker; isso é aviso, não controle automático. O runbook `docs/runbooks/postgres-disk-budget.md` foi copiado sem alteração para este PR e está linkado em `docs/launch/MANUAL_ACTIONS.md`.

## Limites desta entrega

- Não modifiquei runtime, Railway, secrets, metadados remotos nem release.
- A hipótese de nova arquitetura econômica depende do trabalho e da validação pós-deploy do agente de worker/custo.
- Não medi faturamento, armazenamento pós-mudança ou custo steady-state.
