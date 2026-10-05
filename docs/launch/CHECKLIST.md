# Checklist persistente do launch

Estados: `[ ]` pendente, `[~]` em andamento, `[x]` concluído, `[!]` bloqueio técnico/externo demonstrado.

## Inspeção e nova norma
- [x] SHA/serviços/health e dados de produção revalidados.
- [x] Políticas de refresh e freshness por adapter mapeadas.
- [x] Teste adapter real com fixture: novo registro, upsert repetido, falha preservando dados, retry, busca e hidratação elegível.
- [x] Cobertura não integrada não é apresentada como automática.

## Produto
- [x] Home em 10 segundos, busca, exemplos e CTA para case real.
- [x] Explain/Blame por dispositivo, partial e não identificado.
- [x] Diff legível, before/after, ato e fonte.
- [x] `/fontes`, `/cobertura`, `/sobre`; freshness e lacunas sem implicar cobertura integral.
- [x] URL profunda por artigo com canonical e OpenGraph server-side.
- [ ] Smoke e browser matrix no deploy final.

## OSS/kit
- [x] README, API, quickstart, inglês, contribuição e diagrama.
- [x] Fact sheet, case study, hero case, roteiros, posts não publicados e manual actions.
- [x] Playwright local fixtureado e E2E hero/typo/mobile.
- [ ] Screenshots e PNG OG finais.
- [ ] PR, CI, merge, deploy e release decision.

## Segurança/produção
- [x] Nenhuma migration; rate limits de leitura/job existentes mantidos.
- [x] CSP, headers, allowlists, worker heartbeat e sitemap mantidos.
- [x] Heartbeat emitido fora do loop de jobs; teste impede falsa staleness durante processamento longo.
- [ ] Railway web/worker `SUCCESS` no SHA final e smoke pós-deploy.
- [!] Build de Docker no executor local falha porque o proxy TLS interceptado não é confiado pelo container; gate de imagem segue no CI remoto.
- [!] Um patch destrutivo pré-existente (remoção `pg-diagnostic`) está staged em Railway produção; não foi aceito com o deploy do app.
