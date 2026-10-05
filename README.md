# LeiAberta

**Veja o que mudou. Quem mudou. E por quê.**

LeiAberta é um acervo público para pesquisar legislação brasileira, ler dispositivos e seguir alterações até suas fontes oficiais. A aplicação ainda não contém todas as leis do país. A API mostra separadamente o que foi enumerado, baixado, estruturado e historicamente comprovado.

## O que está no MVP

- Busca em português com normalização de acentos e pontuação, siglas, números e anos, nomes populares e aproximação para erros comuns como `LGDP`.
- Catálogo federal com 24 classes normativas enumeradas na API oficial do Senado. O conjunto não cobre necessariamente todos os atos federais nem os acervos da Câmara dos Deputados.
- Adaptadores/configurações para ALESP (SP), SINJ-DF, oito assembleias estaduais SAPL e 581 câmaras municipais SAPL. Na medição de 05/10/2026 às 08:33 UTC, 75 registros SAPL estavam enumerados, um sincronizando e dois com falha; as demais configurações ainda não tinham um registro de sincronização concluída na produção. As APIs dos lotes municipais anunciaram 1.169.606 itens em snapshots anteriores; fontes podem se sobrepor, então esse número não é um total de leis brasileiras. Instalações também podem conter registros estaduais, federais ou sem esfera declarada; a classificação da fonte é preservada.
- Leitura por artigo e subdivisões, com IDs estáveis como `art:7.par:2.inciso:I`.
- Preparação sob demanda com job persistido, fila Redis Streams com confirmação/retomada, snapshots oficiais, checksum SHA-256 e registro da versão consultada. Para desenvolvimento local, execução inline exige `LOCAL_INLINE_JOBS=1`.
- Histórico com relações e fontes próprias do Senado, ALESP, SINJ-DF e SAPL municipal. Diferenças textuais só aparecem quando antes/depois foram verificados. Relações oficiais sem redação histórica ficam identificadas como pendentes, sem comparação inventada.
- Captura de textos do Planalto, Normas.leg.br, ALESP, SINJ-DF e SAPL municipal por pedido e por backfill gradual de anexos declarados pelas fontes. PDFs são extraídos e páginas digitalizadas passam por OCR em português; DOCX também é convertido para leitura. A resposta bruta oficial continua arquivada com checksum.
- Tramitação sob demanda para normas federais que o Senado consegue identificar exatamente. A consulta traz processo, autoria, emendas, deliberações e votos nominais; só consulta a Câmara quando o registro do Senado contém uma referência cruzada oficial e a identidade da proposição confere. As respostas brutas são arquivadas. Esse piloto ainda não cobre todos os processos ou casas legislativas.
- Indicadores de cobertura que distinguem texto encontrado, histórico parcial e informações ainda não identificadas.

O catálogo não representa cobertura nacional completa. O diretório territorial sincroniza as 27 UFs e localidades do IBGE, mas o cadastro territorial não significa que suas leis já foram descobertas. As fontes conectadas incluem o Senado, a ALESP/SP, o SINJ-DF, oito SAPL estaduais e 581 SAPL municipais. A maioria das Casas Legislativas ainda não está coberta; cada acervo precisa ser descoberto, verificado e enumerado por fonte. Tramitação, autores e votos seguem como conjuntos de dados separados.

## Arquitetura

- FastAPI serve a API e uma interface editorial responsiva em HTML, CSS e JavaScript.
- SQLAlchemy e Alembic guardam normas, versões, dispositivos, snapshots, alterações e jobs em PostgreSQL.
- Redis transporta pedidos do worker Python.
- Railway executa `web`, `worker`, `Postgres` e `Redis`. `web` e `worker` compartilham o Dockerfile; a web aplica migrations, executa seed e inicia a API. O worker atualiza catálogos e processa texto e histórico em segundo plano.
- Processos e votos são mantidos separados do texto normativo e ligados somente por identidade oficial verificada. Dado ausente na fonte continua ausente; não é inferido.

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
- `GET /api/laws/{slug}/proceedings`
- `POST /api/laws/{slug}/proceedings/prepare` (aceita `?refresh=true`)
- `GET /api/jurisdictions?kind=municipality&uf=SP`
- `GET /api/sources`
- `GET /api/laws/{slug}/coverage`
- `GET /api/stats`
- `POST /api/laws/{slug}/hydrate`
- `GET /api/hydration/{job_id}`
- `GET /api/changes/{change_id}`
- `GET /health`, `GET /robots.txt`, `GET /sitemap.xml` e fragmentos `GET /sitemap-laws-{page}.xml`

## Configuração

Veja `.env.example`. Em Railway, `DATABASE_URL` deve referenciar `Postgres.DATABASE_URL` e `REDIS_URL` deve referenciar `Redis.REDIS_URL` nos serviços web e worker. As credenciais são provisionadas pelo Railway.

## Testes

```bash
pytest
```

Os testes cobrem normalização, parsing de número/ano, fuzzy search, ambiguidade, IDs estáveis, casos de estrutura/variantes, API, job durável, diretório territorial e a consulta processual Senado/Câmara por identidade cruzada. A suíte Python passou com 131 testes neste branch; ela não comprova a completude de todas as fontes ou leis brasileiras. O fluxo Playwright está em `npm run test:e2e`.

## Fontes e limitações

- Catálogo federal e textos integrados: Presidência da República — Planalto, Senado, ALESP, SINJ-DF e fontes SAPL registradas; a hidratação segue por lotes. Existem 589 configurações SAPL verificadas no código (581 municipais e oito estaduais), mas só 78 linhas SAPL aparecem no registro da produção na medição acima. O snapshot SINJ de 04/10/2026 tinha 125.478 registros; 120.294 anunciavam pelo menos um anexo textual, PDF ou DOCX e 5.184 não anunciavam arquivo. Esses casos continuam em pesquisa por diários e repositórios oficiais alternativos.
- A API do Senado enumera classes normativas do Senado, mas não certifica que todos os atos federais estejam cobertos. A expansão subnacional continua incompleta: 581 dos 5.569 legislativos municipais do cadastro e dez jurisdições estaduais/DF têm fonte SAPL/ALESP/SINJ conectada; os demais acervos ainda precisam de descoberta e integração.
- O Normas.leg.br classifica muitas transcrições/compilações como valor jurídico não oficial. O LeiAberta preserva essa classificação e não converte transcrição em publicação oficial consolidada.
- Relações normativas: API do Senado, anotações ALESP e relações do SINJ-DF. Uma relação não demonstra, por si só, o conteúdo integral anterior/posterior nem a data de eficácia.
- A linha do tempo distingue diferença textual validada de referência oficial que ainda não tem comparação.
- O piloto de processo cobre apenas vínculos localizados na API do Senado e, na Câmara, referências que o próprio Senado relaciona. Autoria por dispositivo, relatorias em todas as Casas e cobertura em lote continuam incompletas.
- A expansão estadual e municipal requer registrar, enumerar e conferir os portais oficiais de cada jurisdição, além de desenvolver adapters para famílias não SAPL e reconciliar coberturas. A configuração SAPL abrange 581 municípios, mas a sincronização de produção ainda não enumerou todas essas fontes; o cadastro IBGE contém 5.569 legislativos municipais elegíveis.
- A interface usa HTML, CSS e JavaScript simples servidos pela API; Next.js e Tailwind não foram necessários para este MVP enxuto.

## Plano de expansão

O inventário, cobertura, riscos de produção, custo, escala, segurança, proveniência, backup/restore e decisões estão em [`docs/audits`](docs/audits/production-baseline.md). Procedimentos de operação ficam em [`docs/runbooks/backup-restore.md`](docs/runbooks/backup-restore.md). Contribuição e disclosure estão em [`CONTRIBUTING.md`](CONTRIBUTING.md) e [`SECURITY.md`](SECURITY.md). A meta de “todas as leis” só pode ser declarada quando cada acervo oficial integrado publicar seu denominador, cobertura, lacunas e auditoria do texto; o estado atual ainda não atende essa meta.
