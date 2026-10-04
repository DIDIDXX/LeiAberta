# LeiAberta — linha de base T00

Coleta: 04/10/2026 UTC. Repositório: `DIDIDXX/LeiAberta`. Branch local de execução: `docs/luna6-next-steps`.

## Código e validação anterior

- Base principal auditada: `16c78fe888b3507409dbfda0dc951f06d28e0d50`.
- O branch `docs/luna6-next-steps` foi aberto a partir da base e recebeu o plano pesquisado em `6d32fd8debbdef62fd205ebde102ac30ab8400e7`.
- Stack: FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis, HTML/CSS/JS, Docker.
- Catálogo inicial fixo: 14 normas federais.
- Suíte já presente: pytest e Playwright E2E.

## Produção Railway

- Projeto `LeiAberta`: `ac5c9188-a792-4d4a-99d6-512740aec73e`.
- Único ambiente observado: `production`, ID `b415a556-41ec-4f33-994f-1f5d38b633a1`.
- Serviços: `web` (`549c7526-c99d-4b45-bdee-42462bdf6fa6`), `worker` (`d00c4b89-3d35-4c86-afe6-c5c87c70d2f5`), Postgres (`94ed1c2a-cc3f-4a39-b458-ba7d04d15b43`) e Redis (`6557bcd8-4609-40d7-ab23-7f0bfef0f5d1`). Cada um reportava deployment `SUCCESS` e uma réplica.
- PostgreSQL e Redis têm volumes persistentes de 5.000 MB, região `asia-southeast1-eqsg3a`.
- Domínio: `https://web-production-12e95.up.railway.app`, roteado à porta 8080.
- Saúde pública verificada com HTTP 200 em `/health`.
- `/api/stats` na captura base: 14 normas no catálogo, 14 normas marcadas materializadas, 3.786 artigos estruturados e 3 alterações documentadas. Esses totais não certificam completude.
- Variáveis existem nos serviços e o Railway MCP mascara valores sensíveis. Nenhum segredo foi exportado.
- Sem bucket. Sem staging observado. Railway CLI não está instalada no shell. Esta sessão não tem credenciais PostgreSQL locais para `pg_dump` e o Railway MCP disponível não expõe snapshot/restore nem criação de ambiente.
- As alterações desta execução não foram implantadas em production.

## Principais riscos de integridade identificados

- O status “Em vigor” era preenchido sem fonte de confirmação.
- Uma resposta HTML parseável podia virar `ready` sem auditoria de completude.
- Código Civil apresentava concatenação indevida: Art. 1 com 174.903 caracteres e só 1.007 nós de artigo na versão anterior do parser, apesar da referência ao Art. 2.046 na fonte oficial.
- Lista vazia de histórico aparecia como mensagem genérica de preparação, sem job real.
- Histórico específico de alteração textual existia apenas para três alterações verificadas da LMP.
- Catálogo e provedores disponíveis não cobriam Brasil inteiro.

## Fontes verificadas

Os detalhes, URLs e hashes da pesquisa estão em [`../research/2026-10-04-source-findings.json`](../research/2026-10-04-source-findings.json). Em resumo: OpenAPI/API de legislação do Senado e detalhe LGPD funcionaram; busca/ficha de legislação da Câmara funcionaram; IBGE retornou 27 UFs e 5.571 localidades; páginas oficiais ALESP e SINJ-DF abriram, mas seus contratos de catálogo não foram implementados; tentativa LexML SRU retornou página challenge, não XML; INLABS exigiu login; host SAPL candidato a Campinas não foi confirmado.

## Contagem de cobertura

Território não equivale ao universo de leis. A linha de base tem 14 metadados federais e 14 textos previamente marcados como materializados, sem inventário de denominações por jurisdição. Após os novos testes de parser e diretório, veja [`execution-status.md`](execution-status.md) para distinguir resultados locais da produção.
