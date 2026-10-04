# LeiAberta

**Veja o que mudou. Quem mudou. E por quê.**

LeiAberta é um acervo público para pesquisar legislação brasileira, ler dispositivos e seguir alterações até suas fontes oficiais. A aplicação ainda não contém todas as leis do país. A API mostra separadamente o que foi enumerado, baixado, estruturado e historicamente comprovado.

## O que está no MVP

- Busca em português com normalização de acentos e pontuação, siglas, números e anos, nomes populares e aproximação para erros comuns como `LGDP`.
- Catálogo-semente de quatorze normas federais. Ainda não é um inventário integral de normas brasileiras.
- Leitura por artigo e subdivisões, com IDs estáveis como `art:7.par:2.inciso:I`.
- Preparação sob demanda com job persistido, fila Redis Streams com confirmação/retomada, snapshots oficiais, checksum SHA-256 e registro da versão consultada. Para desenvolvimento local, execução inline exige `LOCAL_INLINE_JOBS=1`.
- Histórico com relações descobertas na API oficial do Senado e diferenças textuais apenas quando antes/depois foram verificados. Relações oficiais ainda sem redação histórica ficam marcadas como pendentes, não como comparação.
- Indicadores de cobertura que distinguem texto encontrado, histórico parcial e informações ainda não identificadas.

O catálogo não representa cobertura nacional completa. O diretório territorial sincroniza as 27 UFs e localidades do IBGE, mas o cadastro territorial não significa que suas leis já foram descobertas. As fontes de texto integradas nesta etapa são Planalto e metadados relacionais do Senado. Adapters estaduais/municipais, enumeração nacional e tramitação ainda estão pendentes.

## Arquitetura

- FastAPI serve a API e uma interface editorial responsiva em HTML, CSS e JavaScript.
- SQLAlchemy e Alembic guardam normas, versões, dispositivos, snapshots, alterações e jobs em PostgreSQL.
- Redis transporta pedidos do worker Python.
- Railway executa `web`, `worker`, `Postgres` e `Redis`. `web` e `worker` compartilham o Dockerfile; o worker inicia com `sh scripts/start-worker.sh`, enquanto a web aplica migrations, sincroniza o catálogo e inicia a API.
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

No deploy, `scripts/start-web.sh` aplica as migrations e sincroniza o catálogo-semente, o diretório territorial IBGE e as leis enumeradas pelo Senado. Falha temporária dos dois últimos provedores fica no log e mantém os dados anteriores. Quando Redis está configurado, os destaques entram na fila de hidratação. A pessoa também pode abrir qualquer norma Planalto fria para prepará-la sob demanda. O processo pode ser repetido sem duplicar identidades ou versões com o mesmo checksum. Em ambiente local, a fila não usa thread por padrão; defina `LOCAL_INLINE_JOBS=1` para habilitar esse modo de desenvolvimento.

Após `alembic upgrade head`, atualize o inventário territorial com `python scripts/sync_jurisdictions.py` e o catálogo federal leve de leis com `python scripts/sync_senado_catalog.py`. O primeiro lê os endpoints oficiais do IBGE; o segundo enumera os registros de `tipo=LEI` publicados pela API do Senado e faz upsert por identidade externa. Esse universo é o catálogo de leis enumeradas pelo Senado, não todos os atos normativos federais nem a legislação estadual/municipal. As entradas Senate-only mostram metadados e link oficial até existir adapter para buscar seu texto integral.

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

- Texto consolidado integrado: Presidência da República — Planalto, HTML de normas federais.
- Relações normativas: API oficial do Senado. Uma relação não demonstra, por si só, o conteúdo integral anterior/posterior nem a data de eficácia.
- A linha do tempo distingue diferença textual validada de referência oficial que ainda não tem comparação.
- O vínculo entre lei e projeto legislativo, a autoria de dispositivos, relatorias, emendas e votos individuais ainda não está implementado.
- A expansão estadual e municipal requer adapters por família de fonte (por exemplo, SAPL e portais legislativos), além de metadados oficiais para o catálogo.
- A interface usa HTML, CSS e JavaScript simples servidos pela API; Next.js e Tailwind não foram necessários para este MVP enxuto.

## Plano de expansão

O inventário executado, fontes pesquisadas, bloqueios e próximos lotes estão documentados em [`docs/LEIABERTA_LUNA6_EXECUTION_PLAN.md`](docs/LEIABERTA_LUNA6_EXECUTION_PLAN.md) e `docs/reports/execution-status.md`. A meta de “todas as leis” só pode ser declarada quando cada acervo oficial integrado publicar seu denominador, cobertura, lacunas e auditoria do texto; o estado atual ainda não atende essa meta.
