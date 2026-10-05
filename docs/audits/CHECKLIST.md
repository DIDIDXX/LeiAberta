# LeiAberta Luna 6 — checklist persistente

Estados: `[ ]` não iniciado, `[~]` em andamento, `[x]` concluído, `[!]` bloqueado com evidência.

## Fase 0 — bootstrap

- [x] Ler integralmente o prompt autônomo (A–Z e auditoria 1–67).
- [x] Preservar mudanças anteriores sem as reaplicar cegamente.
- [x] Criar branch isolada a partir do `main` atualizado.
- [x] Criar este `WORKLOG.md` e `CHECKLIST.md` antes das mudanças de comportamento.
- [x] Registrar leitura de README, plano, relatórios, migrations, código, testes e configuração.

## Fase 1 — baseline sem mudar comportamento

- [x] Confirmar branch, SHA, SHA implantado e deploys Railway.
- [x] Confirmar configuração/estado de web, worker, Redis, Postgres, backup, volumes, buckets, réplicas e região.
- [x] Medir CPU, RAM, disco e rede de cada serviço.
- [x] Medir latências de health, busca, lei, nodes, histórico, diff, fontes e sitemap.
- [!] Tamanho de tabelas/índices/raw bodies e conexões requer SQL read-only, não exposto pelo Railway connector; volume é proxy documentado.
- [!] Profundidade/idade da fila requer Redis/SQL query access, não exposto no Railway connector.
- [x] Examinar deploys e logs; disponibilidade completa por fonte permanece parcial.
- [x] Executar testes existentes e registrar duração/avisos.
- [x] Smoke público desktop concluído; Playwright desktop/mobile passou localmente.
- [x] Criar `docs/audits/production-baseline.md` com valores, hora, fontes e incertezas.

## Fase 2 — auditoria técnica: achados com problema, evidência, impacto, severidade, arquivo, correção, custo/benefício, risco, teste e resultado esperado

- [x] 1. Veracidade jurídica: catálogo, texto, estrutura, auditoria, histórico, diff, provenance, vigência, autoria e cobertura revisados; limitações relatadas.
- [x] 2. Custo Railway: rate proxy e cenários 0, 1k, 10k, 100k req/dia e 10/100/1.000 hidratações/dia documentados; invoice/billing unavailable.
- [x] 3. Redis/worker versus fila PG e worker sob demanda avaliados; preservar arquitetura com outbox/Redis por evidência disponível.
- [x] 4. GET público, enqueue, dedupe/backpressure revisados; orçamento global Redis adicionado; client-IP fairness aguarda verificação do proxy.
- [x] 5. Startup revisado: migration e hot seed leves; full sync já está fora do startup.
- [x] 6. Corrida de migrations/schema gate/retry revisados; limites em technical audit.
- [x] 7. Backup/restore e policy revisados; runbook produzido; restore report anterior conferido.
- [x] 8. Regiões comparadas pela topologia; falta latency/cost probe para decisão, sem migração.
- [x] 9. Search scans e `SequenceMatcher` encontrados; typo fallback corrigido, PG `EXPLAIN` bloqueado por falta de query access.
- [x] 10. Sitemap index/shards implementados e testes adicionados.
- [x] 11. SEO sem JS corrigido com metadata/canonical e conteúdo limitado em noscript; validar pós-deploy.
- [x] 12. Cache/ETag revisado; adiar cache HTTP até especificar invalidação e estado dinâmico.
- [!] 13. Postgres storage: volume medido; relation size/bloat/connections indisponíveis via connector.
- [!] 14. Pool: configuração default encontrada; dimensionamento requer `max_connections`/`pg_stat_activity` indisponíveis.
- [x] 15. Fontes revisadas por famílias; Planalto agora rejeita corpos acima de 25 MB; limites Senado permanecem pendentes.
- [x] 16. Planalto: HTTPS/host allowlist, redirect handler e cap 25 MB adicionados/testados; contrato uniforme dos outros adapters permanece.
- [x] 17. Rate limit/abuso: budgets globais Redis (search/detail/job prepare) testados; fairness por IP não usa header não confiável.
- [x] 18. Headers e CSP same-origin aplicados com teste; raw query logging permanece sob revisão; nenhuma credencial exportada.
- [x] 19. Docker non-root, `.dockerignore`, build e container smoke executados.
- [~] 20. package-lock presente, Dependabot criado; Python requirements ainda não travados.
- [~] 21. CI PR workflow criado; aguarda branch remota e checks.
- [x] 22. Warning Alembic corrigido; Ruff/type checks ficam para evolução gradual.
- [x] 23. OSS: MIT, CONTRIBUTING, SECURITY, Code of Conduct, templates e ADR criados.
- [x] 24. CONTRIBUTING cobre setup, testes, migrations, adapters, provenance, jurisdições, fixtures e IDs.
- [x] 25. Templates de bug, problema de dado jurídico, nova fonte e PR criados.
- [~] 26. Dependabot e CI adicionados; branch ruleset, secret/code scanning precisam confirmação no GitHub.
- [x] 27. Reprodutibilidade/checksum/parser e limitações revisados no modelo e relatório.
- [x] 28. Famílias de adapters revisadas; contrato uniforme e byte caps ainda requerem implementação.
- [x] 29. Legalize docs/SPEC v0.4 pesquisados; compatibilidade é aditiva/roadmap, sem alegar conformidade.
- [x] 30. Leis.org tratado como benchmark; acesso direto 403, sem scraping/cópia.
- [x] 31. Provenance relacional revisada; não adicionar graph DB sem necessidade medida.
- [~] 32. Limites de query/docs revisados; API versioning/paginação e fairness por cliente permanecem no roadmap; budgets globais ativos.
- [~] 33. Queue observability não exposta pela integração; recomendações/limiares documentados.
- [~] 34. `/ready` confirma DB + Alembic heads em teste e produção; worker heartbeat separado permanece ausente.
- [x] 35. Startup sem sync longo; worker cuida de atualização em background.
- [~] 36. Fixtures/E2E cobrem funções-chave; concorrência e p50/p95 ainda sem ambiente de carga isolado.
- [x] 37. Sem framework, DB, fila, região ou vendor de observability novo.
- [x] 38. Hipóteses sobre cobertura, search, stats, sitemap, worker, disco, freshness e produto classificadas em `technical-audit.md`.

## Fase 3 — decisão e ADRs

- [x] Classificar achados P0/P1/P2/P3 sem inflação de severidade.
- [x] Provar P1 de performance/SEO/security e registrar evidência, impacto, risco, teste e rollback.
- [x] Criar ADR curta para decisões arquiteturais relevantes.
- [x] Evitar mudança em custo/serviço/região sem justificativa concreta.

## Fases 4–5 — correções P0/P1

- [x] Corrigir P1 operacionais seguros: stats, typo, sitemap, SEO, CSP, readiness, container/OSS/CI; limites de fonte aplicados ao Planalto.
- [x] Aplicar P1 de alto ROI/baixo risco: stats, fuzzy bound, sitemap, SEO, headers/CSP, readiness, container/OSS/CI.
- [x] Para mudanças, adicionar teste, documentar risco/rollback; commit e CI aguardam PR.
- [x] Nenhuma migration; evitar risco de lock/disk e não fazer backfill no startup.
- [~] API/E2E/container/hydration/history passaram; falhas Redis/PG/restart/concurrency permanecem para testes futuros.

## Fase 6 — diferenciação e produto

- [x] Auditar proveniência do dispositivo até proposição/votação/fonte; lacunas documentadas.
- [x] Registrar estados parcial/desconhecido sem inferir fatos nem converter relation em diff.
- [x] Auditar tipos de diff; extensões restantes entraram no roadmap.
- [x] Roadmap blame, timeline, versão em data e comparação incluído.
- [x] Preservar vínculo Câmara/Senado por referência e identidade oficial.
- [x] Documentar cobertura/freshness como produto e limitação.
- [x] Criar relatório de diferenciação; pesquisa Legalize; registrar bloqueio 403 do Leis.org sem scraping.
- [x] Exportação e compatibilidade Legalize avaliadas como oportunidade/roadmap.
- [x] URLs profundas atuais revisadas sem quebrar APIs.

## Fase 7 — custo/performance/escala finais

- [~] Código/endpoint local revistos; métricas de produção precisam novo deploy.
- [x] Gerar `docs/audits/cost-analysis.md` com rate proxy, premissas e cenários.
- [x] Gerar `docs/audits/scale-analysis.md` com operating point, limites e plano p50/p95.
- [x] Rever search, sitemap, DB, jobs e fontes; EXPLAIN/queue details indisponíveis.
- [x] Custos calculados com pricing oficial e limitados como estimate sem invoice.

## Fases 8–10 — merge, produção e fechamento (2026-10-05)

- [x] PRs #62–#68 integrados após Python/E2E/Docker verdes.
- [x] Código funcional validado no SHA `06646081480668017d288ad89e98545eead82a0c`.
- [x] Railway web/worker/backup/Redis/Postgres SUCCESS; uma réplica de cada service.
- [x] `/health`, `/ready` e `/worker-health` 200; heartbeat tem testes 200/503 e TTL de 90s.
- [x] Smoke público: LGDP, Art. 7, Maria da Penha history parcial, sitemap, stats.
- [x] Browser 390px/1440px: overflow 0, busca LGDP e Art. 7 ok, console/network limpos.
- [x] CSP, Planalto size/HTTPS/redirect allowlist, rate budgets Redis e 429/Retry-After implantados.
- [x] Relatórios, README, runbook, ADR, LICENSE, CONTRIBUTING, SECURITY, Code of Conduct, templates, CI/Dependabot atualizados.
- [x] Testes: Python 146 passed (1 aviso upstream), E2E 5/5 no CI, imagem Docker build ok.

## Pendências externas ou dependentes de dados

- [!] Não há denominator/fonte nacional que permita provar “todas as leis”; crescer cobertura requer novos catálogos oficiais por jurisdição.
- [!] SQL read-only/EXPLAIN e fatura não são expostos pelo Railway connector; não há medição precisa de índices/conexões/queue age/custo faturado.
- [!] `pg-diagnostic` com delete staged exige aceitar no Dashboard Railway usando 2FA; connector recusou autenticação incompleta.
- [~] Rate limit per-client aguarda validar identidade de IP fornecida pelo proxy; budgets globais Redis protegem o serviço no estado atual.
- [~] Harmonizar cap/redirect policy de todos os source adapters; Planalto já está fechado e testado.

O restante do checklist das fases 0–7 acima mantém evidências e decisões da auditoria original. Este bloco registra a conclusão após os deploys finais.
