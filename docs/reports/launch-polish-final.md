# LeiAberta — relatório final de launch polish

Data da validação: 05/10/2026. Produção: <https://web-production-12e95.up.railway.app>.

## O que foi entregue

- Home com CTA para uma alteração já existente do art. 389 do Código Civil e apresentação do before/after completo.
- Página de diff, leitor, histórico, busca, Blame/proveniência, fontes e cobertura com estados parciais/ausentes explícitos.
- README, documentação API/arquitetura, changelog, fact sheet, roteiro, case, checklist, captura automatizada, 9 screenshots, OG PNG e vídeo WebM.
- Fixture de nova norma e E2E para descoberta, deduplicação, busca, elegibilidade de hidratação, falha temporária e recuperação.
- Cinco issues abertas para ampliar fontes, auditar completude e melhorar acessibilidade.

## Caso da demo e limites jurídicos

A redação anterior e posterior do art. 389 está registrada no Normas.leg.br e relacionada à Lei nº 14.905/2024. A página exibe a ressalva de que a transcrição tem valor jurídico não oficial, aponta separadamente para o texto consolidado do Código Civil no Planalto e não apresenta a data da comparação como data de vigência. Não é atribuída autoria individual ao texto. Este exemplo comprova o par registrado, não a completude histórica do Código Civil.

## Produção

O SHA de código do hero validado em Railway é `c66c0138f03b1a83310c07089c265654785706ae`. PRs #71 (launch polish), #72 (overflow mobile) e #73 (hero real) foram integrados. Web, worker e backup estavam `SUCCESS`; PostgreSQL e Redis online. `/health`, `/ready` e `/worker-health` retornaram 200. O smoke cobriu home, busca, leitor, histórico, diff, Blame, fontes, cobertura, OpenAPI, sitemap e APIs relacionadas.

A amostra de dados de produção em `FACTS.md` é variável e não representa a totalidade das leis brasileiras. Freshness desconhecido continua explícito. O worker cobre somente adaptadores ativos; integrar cada portal não é automático.

## Verificação

- `pytest -q`: 150 aprovados; aviso upstream de depreciação Starlette/httpx.
- `npm run test:e2e`: 2 aprovados.
- CI: Python, imagem Docker e Playwright aprovados nos PRs de produto.
- Browser: 36 combinações (9 rotas × 390, 430, 768 e 1440 px), sem overflow horizontal, erro JS/console, request falho ou imagem quebrada.
- Amostras de latência e respectivas ressalvas estão em `docs/launch/FACTS.md`; não são benchmark estatístico.

## Pendências que realmente não foram concluídas

- Atualização da descrição, homepage e topics GitHub foi rejeitada com 403 `Resource not accessible by integration`; requer acesso administrativo do mantenedor.
- O patch Railway destrutivo preexistente que removeria `pg-diagnostic` permaneceu intocado; não era necessário para publicar o produto e não pôde ser inspecionado.
- Domínio customizado e fatura/billing são ações externas opcionais; o serviço está público no domínio Railway.
- Não se afirma cobertura integral de leis nem histórico completo para cada norma. A ampliação para todas as jurisdições exige adapters, fontes oficiais acessíveis, processamento e auditoria específica.
