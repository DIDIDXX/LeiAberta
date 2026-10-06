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

- A exclusão antiga staged de `pg-diagnostic` foi descartada pelo coordenador; não houve remoção nem alteração do serviço em execução.
- O único bloqueio manual Railway atual é revisar/aplicar via Dashboard, com 2FA do proprietário, o resize não destrutivo do volume persistente Postgres de 5.000 MB para 6.500 MB. Antes de aplicar, confirmar que Pending Changes contém somente esse resize. Instruções estão em `docs/launch/MANUAL_ACTIONS.md`.

## Limites desta entrega

- Não modifiquei runtime, Railway, secrets, metadados remotos nem release.
- A hipótese de nova arquitetura econômica depende do trabalho e da validação pós-deploy do agente de worker/custo.
- Não medi faturamento, armazenamento pós-mudança ou custo steady-state.
