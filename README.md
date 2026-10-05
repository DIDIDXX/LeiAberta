# LeiAberta

**Veja o que mudou. Quem mudou. E por quê.**

LeiAberta é um acervo público para pesquisar legislação brasileira, ler dispositivos e seguir alterações até suas fontes oficiais. A aplicação ainda não contém todas as leis do país. A API mostra separadamente o que foi enumerado, baixado, estruturado e historicamente comprovado.

## O que está no MVP

- Busca em português com normalização de acentos e pontuação, siglas, números e anos, nomes populares e aproximação para erros comuns como `LGDP`.
- Catálogo federal com 24 classes normativas enumeradas na API oficial do Senado. O conjunto não cobre necessariamente todos os atos federais nem os acervos da Câmara dos Deputados.
- Catálogos oficiais da ALESP (SP), SINJ-DF e seis câmaras que usam SAPL: Manaus, Anápolis, Campina Grande, Unaí, São João da Boa Vista e Natal. As APIs consultadas em 05/10/2026 anunciavam 181.172 registros na ALESP, 125.478 no SINJ-DF e 62.031 no conjunto SAPL. São os acervos enumerados nessas fontes, não um denominador de todas as leis brasileiras.
- Leitura por artigo e subdivisões, com IDs estáveis como `art:7.par:2.inciso:I`.
- Preparação sob demanda com job persistido, fila Redis Streams com confirmação/retomada, snapshots oficiais, checksum SHA-256 e registro da versão consultada. Para desenvolvimento local, execução inline exige `LOCAL_INLINE_JOBS=1`.
- Histórico com relações e fontes próprias do Senado, ALESP, SINJ-DF e SAPL municipal. Diferenças textuais só aparecem quando antes/depois foram verificados. Relações oficiais sem redação histórica ficam identificadas como pendentes, sem comparação inventada.
- Captura de textos do Planalto, Normas.leg.br, ALESP, SINJ-DF e SAPL municipal por pedido e por backfill gradual de anexos declarados pelas fontes. PDFs são extraídos e páginas digitalizadas passam por OCR em português; DOCX também é convertido para leitura. A resposta bruta oficial continua arquivada com checksum.
- Indicadores de cobertura que distinguem texto encontrado, histórico parcial e informações ainda não identificadas.

O catálogo não representa cobertura nacional completa. O diretório territorial sincroniza as 27 UFs e localidades do IBGE, mas o cadastro territorial não significa que suas leis já foram descobertas. As fontes legislativas conectadas abrangem o Senado, a ALESP/SP, o SINJ-DF e seis municípios com SAPL. Os demais acervos estaduais e municipais precisam ser enumerados por fonte. Tramitação, autores e votos seguem como conjuntos de dados separados.

## Arquitetura

- FastAPI serve a API e uma interface editorial responsiva em HTML, CSS e JavaScript.
- SQLAlchemy e Alembic guardam normas, versões, dispositivos, snapshots, alterações e jobs em PostgreSQL.
- Redis transporta pedidos do worker Python.
- Railway executa `web`, `worker`, `Postgres` e `Redis`. `web` e `worker` compartilham o Dockerfile; a web aplica migrations, executa seed e inicia a API. O worker atualiza catálogos e processa texto e histórico em segundo plano.
- As relações de autoria e votação são marcadas como indisponíveis; não são inferidas.

## Rodar localmente

Requer Python 3.12+ e, opcionalmente, Redis. SQLite permite iniciar sem serviços externos.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

Abra `http://localhost:8000`. Para rodar jobs inline durante o desenvolvimento, defina `LOCAL_INLINE_JOBS=1`; o padrão não inicia threads locais. Para rodar o worker separado, configure `REDIS_URL` e use `python -m app.worker`.

## Migrations, catálogo e ingestão

```bash
alembic upgrade head
python -m app.seed
python scripts/sync_jurisdictions.py
python scripts/sync_senado_catalog.py
```

No deploy, `scripts/start-web.sh` aplica migrations e seed e inicia a API sem esperar varreduras longas. O worker atualiza os tipos federais do Senado, ALESP, SINJ-DF, SAPL municipal e IBGE em segundo plano, registrando contagens e estado por fonte. Ele enfileira textos federais e subnacionais com limites por lote; a fila persiste os pedidos e prioriza consultas interativas. A origem seleciona a publicação ou compilação disponível e preserva sua classificação jurídica. `/api/stats` informa a cobertura de cada catálogo; `with_text` cresce conforme o worker captura e confere as fontes. Em ambiente local, a fila não usa thread por padrão; defina `LOCAL_INLINE_JOBS=1` para habilitar esse modo de desenvolvimento.

Após `alembic upgrade head`, atualize o inventário territorial com `python scripts/sync_jurisdictions.py` e o catálogo federal com `python scripts/sync_senado_catalog.py`. Use `--type MPV --type LCP` para selecionar categorias ou `--force` para ignorar a janela de frescor. O sincronizador faz upsert por identidade oficial, preservando reedições como `2.206-1`. O worker atualiza os conectores SAPL verificados e enfileira textos em lotes; `/api/stats` mostra avanço e pendências.

O adapter `app/sources/planalto.py` baixa HTML oficial, preserva redações marcadas como revogadas, separa namespaces da Constituição/ADCT e guarda variantes de artigos repetidos. Até existir auditoria independente de completude documental, o resultado é publicado como parcial. Falhas não apagam snapshots já armazenados.

## Endpoints

- `GET /api/search?q=LGDP`
- `GET /api/laws` e `GET /api/laws/{slug}`
- `GET /api/laws/{slug}/nodes`
- `GET /api/laws/{slug}/history`
- `POST /api/laws/{slug}/history/prepare` e `GET /api/jobs/{job_id}`
- `GET /api/jurisdictions?kind=municipality&uf=SP`
- `GET /api/sources`
- `GET /api/laws/{slug}/coverage`
- `POST /api/laws/{slug}/hydrate`
- `GET /api/hydration/{job_id}`
- `GET /api/changes/{change_id}`
- `GET /health`, `GET /robots.txt`, `GET /sitemap.xml`

## Configuração

Veja `.env.example`. Em Railway, `DATABASE_URL` deve referenciar `Postgres.DATABASE_URL` e `REDIS_URL` deve referenciar `Redis.REDIS_URL` nos serviços web e worker. As credenciais são provisionadas pelo Railway.

## Testes

```bash
pytest
```

Os testes cobrem normalização, parsing de número/ano, fuzzy search, ambiguidade, IDs estáveis, casos de estrutura/variantes, API, job durável e diretório de jurisdições. `npm run test:e2e` cobre busca, leitura, fonte oficial, histórico, diff e artigo em consulta ambígua. A suíte não comprova a completude de todas as fontes ou leis brasileiras.

## Fontes e limitações

- Catálogo e texto integrados: Presidência da República — Planalto, Senado, ALESP, SINJ-DF e seis instalações SAPL municipais. O snapshot SINJ de 04/10/2026 tinha 125.478 registros; 120.294 anunciavam pelo menos um anexo textual, PDF ou DOCX e 5.184 não anunciavam arquivo. Esses casos continuam em pesquisa por diários e repositórios oficiais alternativos.
- A API do Senado enumera classes normativas do Senado, mas não certifica que todos os atos federais estejam cobertos. A expansão subnacional continua incompleta: faltam fontes para a maior parte dos estados e municípios.
- O Normas.leg.br classifica muitas transcrições/compilações como valor jurídico não oficial. O LeiAberta preserva essa classificação e não converte transcrição em publicação oficial consolidada.
- Relações normativas: API do Senado, anotações ALESP e relações do SINJ-DF. Uma relação não demonstra, por si só, o conteúdo integral anterior/posterior nem a data de eficácia.
- A linha do tempo distingue diferença textual validada de referência oficial que ainda não tem comparação.
- O vínculo entre lei e projeto legislativo, a autoria de dispositivos, relatorias, emendas e votos individuais ainda não está implementado.
- A expansão estadual e municipal requer confirmar os portais oficiais de cada jurisdição e desenvolver adapters para as demais famílias e instalações, além de reconciliar coberturas e metadados. A integração SAPL reutilizável já valida seis municípios, mas isso ainda representa uma fração pequena das 5.569 localidades com legislativo municipal.
- A interface usa HTML, CSS e JavaScript simples servidos pela API; Next.js e Tailwind não foram necessários para este MVP enxuto.

## Plano de expansão

O inventário executado, fontes pesquisadas, bloqueios e próximos lotes estão documentados em [`docs/LEIABERTA_LUNA6_EXECUTION_PLAN.md`](docs/LEIABERTA_LUNA6_EXECUTION_PLAN.md) e `docs/reports/execution-status.md`. A meta de “todas as leis” só pode ser declarada quando cada acervo oficial integrado publicar seu denominador, cobertura, lacunas e auditoria do texto; o estado atual ainda não atende essa meta.
