# LeiAberta

**Veja o que mudou. Quem mudou. E por quê.**

LeiAberta é um acervo público para pesquisar legislação brasileira, ler dispositivos e seguir alterações até suas fontes oficiais. O catálogo começa por normas federais e aprofunda o texto quando a norma é acessada.

## O que está no MVP

- Busca em português com normalização de acentos e pontuação, siglas, números e anos, nomes populares e aproximação para erros comuns como `LGDP`.
- Catálogo inicial de treze normas federais: Constituição Federal, CLT, Código Civil, Código Penal, Código Tributário Nacional, CDC, ECA, Marco Civil da Internet, LGPD, Lei Maria da Penha, Lei de Licitações, Lei de Improbidade Administrativa e Lei da Ficha Limpa.
- Leitura por artigo e subdivisões, com IDs estáveis como `art:7.par:2.inciso:I`.
- Preparação sob demanda com estado visível, worker Redis, snapshots oficiais, checksum SHA-256 e registro da versão consultada.
- Histórico e comparação para alterações que têm uma referência verificável na fonte. A Lei Maria da Penha inclui um exemplo de dispositivo acrescentado pela Lei nº 14.550/2023, após conferir o texto no documento da norma modificadora e no texto consolidado.
- Indicadores de cobertura que distinguem texto encontrado, histórico parcial e informações ainda não identificadas.

O catálogo não representa cobertura nacional completa. Nesta primeira versão, as fontes de texto integradas são os documentos federais HTML do Planalto. Leis estaduais e municipais, dados de projetos e votações nominais ainda precisam de adapters e catálogos próprios.

## Arquitetura

- FastAPI serve a API e uma interface editorial responsiva em HTML, CSS e JavaScript.
- SQLAlchemy e Alembic guardam normas, versões, dispositivos, snapshots, alterações e jobs em PostgreSQL.
- Redis transporta pedidos do worker Python.
- Railway executa `web`, `worker`, `Postgres` e `Redis`. `web` contém a API e a interface na mesma unidade de deploy para manter o MVP pequeno.
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

Abra `http://localhost:8000`. Sem `REDIS_URL`, a API executa o job de preparação em uma thread local. Para rodar o worker separado, configure `REDIS_URL` e use `python -m app.worker`.

## Migrations, catálogo e ingestão

```bash
alembic upgrade head
python -m app.seed
```

No deploy, `scripts/start-web.sh` aplica as migrations e sincroniza os metadados do catálogo. Quando Redis está configurado, os destaques do catálogo entram na fila de hidratação. A pessoa também pode abrir qualquer norma fria para prepará-la sob demanda. O processo pode ser repetido sem duplicar versões com o mesmo checksum.

O adapter `app/sources/planalto.py` baixa HTML oficial, remove marcação editorial de texto riscado, reconhece artigos, parágrafos, incisos e alíneas e conserva o documento bruto para auditoria. Falhas não apagam versões já armazenadas.

## Endpoints

- `GET /api/search?q=LGDP`
- `GET /api/laws` e `GET /api/laws/{slug}`
- `GET /api/laws/{slug}/nodes`
- `GET /api/laws/{slug}/history`
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

Os testes cobrem normalização, parsing de número/ano, fuzzy search, ambiguidade, IDs estáveis, referência de emenda e API de busca. `npm run test:e2e` cobre busca, leitura de dispositivo, fonte oficial e diff. O parser depende da forma HTML publicada pelo Planalto; falhas ficam marcadas como indisponíveis e preservam o snapshot anterior.

## Fontes e limitações

- Fonte integrada no MVP: Presidência da República — Planalto, textos HTML da legislação federal.
- A linha do tempo é parcial e aparece apenas quando a indicação de alteração e o texto foram conferidos em documento oficial.
- O vínculo entre lei e projeto legislativo, a autoria de dispositivos, relatorias, emendas e votos individuais ainda não está implementado.
- A expansão estadual e municipal requer adapters por família de fonte (por exemplo, SAPL e portais legislativos), além de metadados oficiais para o catálogo.
- A interface usa HTML, CSS e JavaScript simples servidos pela API; Next.js e Tailwind não foram necessários para este MVP enxuto.

## Próximos passos

1. Ingerir e versionar em lote as treze normas de destaque.
2. Adaptar a busca nacional à Rede LexML e a catálogos oficiais da Câmara e do Senado.
3. Criar adapters SAPL e expandir para assembleias e câmaras municipais.
4. Relacionar alterações a proposições e tramitação com provenance oficial.
5. Adicionar E2E Playwright e cobertura visual para os fluxos de busca, histórico e diff.
