# LeiAberta — Prompt Mestre para Agent

Você é o **engenheiro principal responsável por construir, testar e colocar em produção o MVP completo do LeiAberta**.

Não quero apenas planejamento, arquitetura, análise ou sugestões. Quero **execução autônoma de ponta a ponta**.

Inspecione o repositório fornecido, entenda a estrutura atual, pesquise a documentação oficial necessária, implemente, teste, corrija erros, faça commits, configure o Railway, faça deploy e valide a aplicação em produção.

O objetivo é que, quando eu voltar, exista uma aplicação **real, navegável, funcional, bonita e publicamente acessível**.

---

# 1. Produto

Nome:

**LeiAberta**

Tagline principal:

> **Veja o que mudou. Quem mudou. E por quê.**

O LeiAberta é uma plataforma pública para tornar a legislação brasileira compreensível, pesquisável e auditável.

A inspiração conceitual é:

> **GitHub/Git aplicado à legislação.**

A pessoa deve conseguir:

- pesquisar qualquer norma brasileira;
- abrir uma lei/norma;
- ler seu texto atual;
- navegar por artigos, parágrafos, incisos, alíneas e demais dispositivos;
- visualizar versões anteriores;
- descobrir exatamente o que foi alterado;
- visualizar um diff entre versões;
- descobrir qual norma provocou determinada alteração;
- descobrir, quando os dados permitirem:
  - qual projeto legislativo deu origem à alteração;
  - autores;
  - relatorias;
  - emendas;
  - substitutivos;
  - tramitação;
  - votações;
  - votos individuais;
  - sanções e vetos;
- acessar as fontes oficiais usadas pelo LeiAberta;
- entender quando determinada informação não está disponível ou não pôde ser determinada com segurança.

A longo prazo, o LeiAberta deve funcionar como um sistema de **versionamento público da legislação brasileira**.

---

# 2. Princípio central

A prioridade é:

> **FUNCIONAR > PERFEIÇÃO ARQUITETURAL**

Se existir uma escolha entre:

A) construir uma arquitetura extremamente sofisticada que não ficará pronta;

ou

B) entregar uma versão simples, correta, extensível, bonita e funcionando em produção;

escolha **B**.

Não introduza complexidade desnecessária.

Não use Kafka, Kubernetes, Databricks, OpenSearch, Elasticsearch ou sistemas similares no MVP sem necessidade real.

Para este MVP, a stack abaixo é suficiente:

- PostgreSQL
- Redis
- Python / FastAPI
- Next.js
- Tailwind
- Railway

---

# 3. Cobertura: Brasil inteiro

O produto deve nascer com a ambição de cobrir:

- legislação federal;
- legislação estadual;
- legislação do Distrito Federal;
- legislação municipal.

Porém, **não tente pré-processar profundamente todas as normas brasileiras antes do lançamento**.

O modelo correto é:

> **catálogo nacional pré-indexado + materialização profunda sob demanda.**

---

# 4. Estratégia de cobertura nacional

Arquitetura conceitual:

```text
TODAS AS NORMAS DO BRASIL
        ↓
catálogo nacional leve
        ↓
usuário pesquisa
        ↓
resolver identifica a norma
        ↓
já está materializada?
   ├── sim → retorna imediatamente
   └── não → hidrata/processa
                    ↓
              salva em banco/cache
                    ↓
              próximas visitas
              são instantâneas
```

O catálogo nacional deve ser o mais abrangente possível, mas com ingestão leve.

Armazene inicialmente metadados como:

- jurisdição;
- esfera;
- UF;
- município;
- órgão;
- tipo normativo;
- número;
- ano;
- título;
- descrição;
- data de publicação;
- status;
- aliases;
- fonte oficial;
- identificador externo;
- URL oficial;
- hash/checksum quando aplicável.

Exemplo:

```json
{
  "jurisdiction": "federal",
  "type": "lei",
  "number": 13709,
  "year": 2018,
  "title": "Lei Geral de Proteção de Dados Pessoais",
  "aliases": ["LGPD", "Lei de Proteção de Dados"]
}
```

Exemplo municipal:

```json
{
  "jurisdiction": "municipal",
  "state": "SP",
  "municipality": "Piracicaba",
  "type": "lei complementar",
  "number": 224,
  "year": 2008
}
```

---

# 5. Materialização sob demanda

Quando uma norma ainda não tiver sido profundamente processada, faça:

```text
localizar fonte oficial
↓
baixar documento
↓
armazenar snapshot bruto
↓
parsear texto
↓
extrair estrutura jurídica
↓
identificar versões
↓
buscar normas modificadoras
↓
reconstruir histórico
↓
calcular diff
↓
resolver provenance
↓
buscar projetos/votações quando houver
↓
persistir resultado
↓
cachear
```

Esse processo deve rodar em background.

A requisição HTTP não deve ficar presa por dezenas de segundos.

---

# 6. Experiência quando a norma está sendo preparada

Se o usuário abrir uma norma ainda não materializada, mostre metadata imediatamente.

Exemplo:

```text
Lei Municipal nº 8.291/2019

Estamos preparando o histórico desta norma.

✓ Fonte localizada
✓ Texto obtido
● Reconstruindo alterações
○ Calculando histórico
```

Use polling simples, SSE ou outra abordagem apropriada.

Não complique sem necessidade.

Quando terminar:

```text
Pronto.
```

---

# 7. Hot / Warm / Cold

Implemente conceitualmente três níveis:

## HOT

Normas muito populares:

- Constituição Federal
- CLT
- Código Civil
- Código Penal
- Código de Defesa do Consumidor
- ECA
- Marco Civil da Internet
- LGPD
- Lei de Licitações
- Lei de Improbidade
- Lei Maria da Penha
- Lei da Ficha Limpa

Essas devem ficar pré-materializadas e atualizadas com prioridade.

## WARM

Normas já consultadas por usuários.

Devem permanecer materializadas e ser verificadas periodicamente.

## COLD

Normas nunca acessadas.

Podem existir apenas no catálogo até a primeira consulta.

---

# 8. Busca é P0

A busca do LeiAberta é uma feature central.

Ela precisa funcionar mesmo quando o usuário:

- escreve errado;
- omite acentos;
- troca letras;
- usa nome popular;
- usa sigla;
- usa só o número;
- usa número + ano;
- escreve artigo + nome da lei;
- usa um termo temático;
- escreve uma consulta ambígua.

Exemplos que devem funcionar:

```text
lgpd
LGDP
lei 13709
13709/18
lei geral de dados
lei de proteçao de dado
art 7 lgdp
maria da penha
lei do barulho campinas
lei cachorro piracicaba
```

---

# 9. Normalização da busca

Normalize queries removendo ou ajustando:

- acentos;
- caixa;
- pontuação;
- espaços duplicados;
- `nº`;
- `n.`;
- `numero`;
- variações de `/`;
- zeros irrelevantes.

Exemplo:

```text
"Lei nº 13.709 / 2018"
```

vira algo equivalente a:

```text
lei 13709 2018
```

---

# 10. Parser jurídico da query

Tente reconhecer padrões como:

```text
lei 13709/2018
lei 13709/18
art 7 lgpd
decreto 1234
lei complementar 224 piracicaba
```

Exemplo:

```json
{
  "type": "lei",
  "number": 13709,
  "year": 2018
}
```

Se existir match exato por tipo + número + ano, dê prioridade máxima.

---

# 11. Aliases

Crie uma tabela de aliases.

Exemplo conceitual:

```text
law_aliases

law_id
alias
alias_normalized
type
weight
```

Pesos sugeridos:

```text
OFFICIAL_TITLE        100
NUMBER_YEAR           100
ACRONYM                95
POPULAR_NAME           90
GENERATED_ALIAS        60
```

Exemplos:

```text
LGPD
Lei Geral de Proteção de Dados
Lei 13.709/2018
13709/2018
13709
```

---

# 12. Fuzzy search

Use PostgreSQL antes de qualquer motor externo.

Ative/extenda:

- `unaccent`
- `pg_trgm`
- PostgreSQL Full Text Search

Exemplo:

```text
LGDP
```

deve sugerir:

```text
LGPD
```

Mostre algo como:

> Você quis dizer **LGPD**?

Não dependa só de `ILIKE`.

---

# 13. Ranking da busca

Combine sinais como:

- match exato de número;
- match exato de número + ano;
- sigla;
- alias;
- título oficial;
- similaridade trigram;
- full text;
- jurisdição;
- popularidade;
- recência;
- contexto geográfico quando fornecido.

Uma consulta:

```text
lei do barulho campinas
```

deve favorecer legislação municipal de Campinas relacionada ao termo.

---

# 14. Ambiguidade

Não force um resultado errado.

Exemplo:

```text
art 121
```

Pode existir em várias normas.

Nesse caso, mostre múltiplas opções.

Exemplo:

```text
Encontramos vários Art. 121

Código Penal
Art. 121 — Matar alguém

Código Tributário Nacional
Art. 121 — Sujeito passivo...
```

---

# 15. Fontes oficiais

Use prioritariamente fontes oficiais.

Investigue a documentação atual antes de implementar.

Fontes esperadas:

## Federal

- Câmara dos Deputados — Dados Abertos
- Senado Federal — Dados Abertos / serviços legislativos
- Planalto / Presidência
- LexML
- Diário Oficial / INLABS quando aplicável

## Estadual / DF

Descubra e implemente adapters conforme disponibilidade.

Fontes podem incluir:

- portais legislativos;
- assembleias legislativas;
- diários oficiais;
- SAPL;
- APIs específicas;
- HTML;
- XML;
- JSON;
- PDFs oficiais.

## Municipal

A realidade é heterogênea.

Municípios podem utilizar:

- SAPL;
- portal próprio;
- API;
- HTML;
- XML;
- PDF;
- Diário Oficial;
- sistemas legados.

Crie adapters por família/fonte.

Não tente construir 5.570 integrações manuais uma por uma antes de lançar.

Priorize padrões reutilizáveis.

---

# 16. Adapters de fontes

Estrutura conceitual:

```text
sources/
    camara/
    senado/
    planalto/
    lexml/
    sapl/
    state/
    municipal/
```

Cada adapter deve esconder detalhes externos.

O restante da aplicação deve trabalhar com modelos normalizados internos.

---

# 17. Qualidade e cobertura da fonte

O LeiAberta deve aceitar que nem todas as jurisdições possuem o mesmo nível de transparência.

Modele cobertura.

Exemplo:

```text
Fonte oficial             ✓
Texto estruturado         ✓
Histórico completo        ✓
Autoria                   ✓
Votação nominal           ✓
```

Ou:

```text
Fonte oficial             ✓
Texto disponível          ✓
Histórico                 parcial
Autoria                   indisponível
Votação nominal           indisponível
```

Mostre um indicador de cobertura/qualidade.

Pode ser percentual, score ou níveis.

Exemplo:

> Cobertura desta norma: 74%

Ao abrir detalhes, explique o que foi ou não localizado.

Nunca transforme ausência de dado em dado fictício.

---

# 18. Regra fundamental sobre dados

**NUNCA apresente inferência como fato.**

Cada informação importante deve ter provenance/source.

Exemplos:

> Alterado pela Lei X

precisa ter fonte.

> Originado do PL Y

precisa ter fonte.

> Deputado Z apresentou esta emenda

precisa ter fonte.

Se um vínculo não puder ser determinado com segurança:

> Informação ainda não identificada.

Não use LLM como fonte da verdade para reconstruir relações jurídicas.

LLM pode auxiliar futuramente em classificação/enriquecimento, mas relações legislativas devem vir de dados/documentos verificáveis.

---

# 19. Arquitetura

Use preferencialmente:

## Frontend

- Next.js
- TypeScript
- Tailwind
- componentes acessíveis
- shadcn/ui se fizer sentido

## Backend

- FastAPI
- Python

## Banco

- PostgreSQL

## ORM / migrations

- SQLAlchemy + Alembic
- ou equivalente sólido

## Queue / jobs

- Redis
- worker Python
- biblioteca simples e robusta de jobs
- Railway cron quando necessário

Não use infraestrutura mais complexa sem necessidade.

---

# 20. Arquitetura Railway

Projeto esperado:

```text
web
api
worker
postgres
redis
```

Só crie outros serviços se houver necessidade clara.

O `worker` será responsável por tarefas como:

```text
hydrate_law(law_id)
refresh_law(law_id)
sync_catalog(source)
rebuild_history(law_id)
```

Use rede privada do Railway entre serviços.

Configure health checks.

Configure migrations.

Configure restart policy adequada.

---

# 21. Monorepo

Estrutura recomendada:

```text
/
  apps/
    web/
    api/
    worker/

  packages/
    legislation/
    sources/
    parsing/
    diff/
    provenance/
    search/

  scripts/
    seed/
    ingestion/
    catalog/
```

Adapte à estrutura existente se o repositório já tiver uma boa organização.

Não destrua código existente desnecessariamente.

---

# 22. Modelo de dados

Modele o domínio pensando em versionamento.

Não trate uma lei apenas como um blob gigante.

Estrutura conceitual:

```text
Law
 └── LawVersion
      └── LegalNode
           ├── Article
           ├── Paragraph
           ├── Item
           └── Subitem
```

Exemplo:

```text
Art. 5º
  § 1º
  § 2º
     I
     II
        a
        b
```

Tabelas conceituais:

```text
laws
law_aliases
law_versions
legal_nodes
node_versions
node_changes
source_documents
source_snapshots
propositions
legislative_events
people
proposition_authors
amendments
votes
vote_members
provenance_edges
ingestion_runs
hydration_jobs
jurisdictions
municipalities
coverage_status
search_popularity
```

Os nomes podem mudar.

---

# 23. IDs estáveis dos dispositivos

Esse ponto é crítico.

Tente manter identidade lógica estável ao longo das versões.

Exemplo:

```text
art:7
art:7.par:2
art:7.par:2.inciso:I
```

Não dependa somente do texto para identidade.

Precisamos conseguir saber que:

```text
versão A:
Art. 7 §2 = texto X

versão B:
Art. 7 §2 = texto Y
```

representa:

```text
MODIFY
```

e não:

```text
DELETE + ADD
```

sempre que possível.

---

# 24. Tipos de alteração

Suporte conceitualmente:

```text
ADD
MODIFY
REVOKE
RESTORE
RENUMBER
MOVE
```

Para o MVP, pelo menos:

```text
ADD
MODIFY
REVOKE
```

---

# 25. Diff engine

Feature central.

Quero comparação:

- entre versões da norma;
- por dispositivo;
- estrutural;
- com alterações visuais claras.

Não quero um simples diff do HTML bruto.

Exemplo:

```diff
Art. 7º — § 3º

- O tratamento de dados poderá ocorrer quando...
+ O tratamento de dados pessoais poderá ocorrer quando...
```

Frontend:

- verde = adicionado;
- vermelho = removido;
- não dependa exclusivamente de cor;
- use `+` e `-`/labels;
- mantenha legibilidade jurídica.

---

# 26. Blame jurídico

Crie uma seção:

**Blame**

Objetivo:

mostrar qual norma/alteração é responsável pelo texto atual de cada dispositivo.

Exemplo:

```text
2018 | Lei 13.709 | Art. 1º | texto...
2019 | Lei 13.853 | Art. 3º | texto...
2026 | Lei XXXXX  | Art. 5º | texto...
```

Ao clicar/hover:

mostrar detalhes da alteração.

IMPORTANTE:

Não diga simplesmente que um parlamentar "escreveu aquela linha".

A cadeia pode envolver:

- autor do projeto;
- autor de emenda;
- relator;
- substitutivo;
- Câmara;
- Senado;
- sanção;
- veto.

Modele provenance corretamente.

---

# 27. Provenance

Quero conseguir representar algo semelhante a:

```text
Dispositivo
↓
Lei modificadora
↓
Projeto de Lei
↓
Emenda/Substitutivo
↓
Autor
↓
Relator
↓
Câmara
↓
Senado
↓
Sanção
```

Nem todos os casos terão toda essa informação.

Tudo bem.

Use modelo extensível.

Exemplo:

```text
AMENDED_BY
ORIGINATED_FROM
AUTHORED_BY
REPORTED_BY
SUPERSEDES
VOTED_IN
SANCTIONED_BY
VETOED_BY
```

---

# 28. Catálogo nacional

O catálogo deve existir separadamente da materialização profunda.

Objetivo:

permitir pesquisar uma norma brasileira mesmo antes de ela ser processada.

A primeira versão do catálogo pode ser construída incrementalmente por fontes.

Não bloqueie o projeto esperando cobertura perfeita de todos os municípios.

O sistema deve aceitar:

- cobertura completa;
- cobertura parcial;
- fonte conhecida mas ainda não processada;
- fonte indisponível;
- município ainda não integrado.

---

# 29. Páginas P0

Precisa existir:

- Home
- Busca
- Página da norma
- Texto atual
- Histórico
- Diff
- Fontes
- Status de cobertura
- Status de materialização

---

# 30. Home

Quero uma home limpa.

Conceito:

```text
LeiAberta

Veja o que mudou.
Quem mudou.
E por quê.

[ Pesquise uma lei, artigo, município ou assunto... ]

Constituição
CLT
LGPD
Código Penal
Código Civil
Marco Civil

Alterações recentes
```

Nada de portal governamental antigo.

Nada carregado.

Nada de dezenas de cards coloridos.

---

# 31. Design

Referências de qualidade:

- Linear
- Vercel
- GitHub
- Stripe Docs

Mas não clone nenhuma delas.

Crie identidade própria para o LeiAberta.

Visual:

- minimalista;
- editorial;
- técnico;
- elegante;
- extremamente legível;
- civic-tech moderno.

Background:

- branco;
- off-white;
- branco levemente quente.

Texto:

- quase preto.

Bordas:

- sutis.

Sombras:

- mínimas.

Cantos:

- moderados.

Não transforme tudo em card.

---

# 32. Identidade

Nome:

**LeiAberta**

Evite clichês:

- bandeira;
- brasão;
- martelo de juiz;
- balança da justiça;
- Congresso desenhado;
- verde/amarelo exagerado.

A marca deve parecer:

> infraestrutura pública moderna / civic tech.

Pode existir uma cor de acento discreta.

---

# 33. Tipografia

Use:

- Geist;
- Inter;
- ou equivalente moderno.

Para texto jurídico, priorize leitura.

Não use monospace para toda a lei.

Use monospace somente onde fizer sentido:

- IDs;
- diff;
- metadados técnicos;
- hashes.

---

# 34. Página da norma

Exemplo:

```text
Lei nº 13.709 / 2018

Lei Geral de Proteção de Dados Pessoais

EM VIGOR

Publicada em 14 ago 2018

[ Texto ] [ Histórico ] [ Diff ] [ Blame ]

------------------------------------------------

Art. 1º

Esta Lei dispõe sobre...

------------------------------------------------

Art. 2º

A disciplina da proteção de dados pessoais...

I — ...
II — ...

------------------------------------------------
```

Na lateral/contexto:

```text
Última alteração
Lei X / ano

[Ver alteração]
```

O texto da norma é o protagonista.

---

# 35. Histórico

Crie timeline.

Exemplo:

```text
2026
● Lei X
  Alterou Art. 7 §3

2024
● Lei Y
  Acrescentou Art. 18-A

2019
● Lei 13.853
  41 alterações

2018
● Lei 13.709
  Texto original
```

Cada evento deve abrir detalhes.

---

# 36. Detalhe da alteração

Exemplo:

```text
Alteração do Art. 7º §3º

ANTES

texto anterior

DEPOIS

texto novo

Origem

Lei XXXXX/2026
↓
PL XXXX/2025
↓
Emenda XX
↓
Relator X

Câmara
342 SIM
101 NÃO
5 ABSTENÇÕES

Senado
58 SIM
17 NÃO

[ Fonte oficial ]
[ Projeto ]
[ Votação ]
[ Documento ]
```

Só mostre dados existentes.

---

# 37. Votações

Quando houver:

- resumo;
- total de votos;
- votação nominal;
- parlamentar + voto.

Exemplo:

```text
Fulano da Silva       SIM
Beltrano Souza        NÃO
Ciclano               SIM
```

Adicione filtro simples se for fácil.

Não bloqueie o MVP por isso.

---

# 38. Fontes oficiais na UI

Toda página de alteração/provenance deve ter:

**Fontes**

Com links para as fontes oficiais.

Exemplo:

- Câmara dos Deputados
- Senado Federal
- Planalto
- LexML
- Diário Oficial
- Assembleia Legislativa
- Câmara Municipal
- SAPL

Transparência é parte central do produto.

---

# 39. Disclaimer

Inclua discretamente no footer:

> O LeiAberta organiza e apresenta informações provenientes de fontes públicas oficiais. Não substitui a publicação oficial da legislação brasileira.

---

# 40. URLs

Use URLs legíveis.

Exemplos:

```text
/lei/13709-2018
/lei/13709-2018/artigo/7
/lei/13709-2018/historico
/lei/13709-2018/blame
/diff/...
/pl/...
```

Para normas estaduais/municipais, inclua contexto suficiente para evitar colisões.

---

# 41. Ingestão

Implemente pipeline reproduzível:

```text
source
↓
raw response/snapshot
↓
parser
↓
normalized domain model
↓
database
```

Guarde:

- `source_url`
- `retrieved_at`
- `checksum`
- `source_identifier`
- `raw_format`
- `parser_version`

quando aplicável.

---

# 42. Idempotência

Rodar ingestão duas vezes não pode duplicar tudo.

Use:

- external IDs;
- constraints;
- upsert;
- hashes;
- timestamps.

Jobs devem ser idempotentes.

---

# 43. Cache

Legislação muda lentamente.

Use cache agressivo.

Exemplos:

```text
law:{id}:current
law:{id}:history
law:{id}:blame
law:{id}:coverage
search:{normalized_query}
```

Invalide quando detectar mudança.

Não cacheie erro permanentemente.

---

# 44. Atualização

Estratégia sugerida:

```text
HOT        → verificar diariamente
WARM       → periodicamente
COLD       → sob demanda / baixa frequência
recentes   → mais frequência
antigas    → menos frequência
```

Não precisa ser exatamente isso se houver abordagem melhor.

---

# 45. Falhas das fontes

Fontes públicas podem ficar offline ou mudar formato.

A aplicação não deve quebrar.

Se uma integração falhar:

- logue;
- preserve dados existentes;
- marque sync como falho/parcial;
- retente depois;
- continue servindo o site.

---

# 46. Dados reais

A aplicação pública não pode parecer vazia.

Pré-materialize pelo menos as principais normas federais.

Idealmente:

- Constituição
- CLT
- Código Civil
- Código Penal
- CDC
- ECA
- LGPD
- Marco Civil
- Lei Maria da Penha
- Lei de Licitações

Se alguma não puder ser materializada corretamente no tempo disponível, priorize qualidade.

---

# 47. Sem mock em produção

Mocks podem existir em testes.

Dados visíveis na produção devem ser reais.

Se algo não estiver disponível:

> Informação ainda não identificada.

---

# 48. Git como conceito, não dependência operacional

PostgreSQL é a source of truth operacional.

Não faça o site depender de manipular um repositório Git em runtime.

Se sobrar tempo:

exporte representação versionável:

```text
laws/
  federal/
    2018/
      lei-13709/
        metadata.json
        current.md
        structure.json
```

Isso é P2.

---

# 49. API

Crie API organizada.

Endpoints conceituais:

```text
GET /laws
GET /laws/{id}
GET /laws/{id}/versions
GET /laws/{id}/structure
GET /laws/{id}/history
GET /laws/{id}/blame
GET /laws/{id}/diff
GET /laws/{id}/coverage
POST /laws/{id}/hydrate
GET /hydration/{job_id}
GET /changes/{id}
GET /propositions/{id}
GET /votes/{id}
GET /search
```

Adapte conforme necessário.

---

# 50. Frontend states

Implemente:

- loading;
- empty;
- partial;
- hydration in progress;
- source unavailable;
- error;
- 404.

Nunca mostre JSON cru.

---

# 51. Responsividade

Teste:

- desktop;
- mobile;
- tablet.

Especial atenção a:

- busca;
- leitura da norma;
- diff;
- timeline;
- provenance.

---

# 52. Acessibilidade

Use HTML semântico.

Bom contraste.

Keyboard navigation.

ARIA quando necessário.

Não dependa somente de cor.

---

# 53. Performance

Não carregue uma norma gigantesca inteira desnecessariamente.

Use:

- server components;
- SSR;
- cache;
- paginação/lazy rendering;
- anchors;
- carregamento progressivo.

Não faça premature optimization.

---

# 54. SEO

Implemente:

- title;
- description;
- canonical;
- OpenGraph;
- sitemap;
- robots.txt;
- URLs indexáveis;
- metadata adequada.

Exemplo:

```text
Lei 13.709/2018 — LGPD | LeiAberta
```

---

# 55. Testes obrigatórios

## Backend

Unit tests para:

- parsing;
- normalização;
- query parser;
- stable node IDs;
- diff;
- ingestion;
- idempotência;
- ranking;
- fuzzy search;
- hydration jobs.

## Frontend

Teste fluxos críticos.

## E2E

Use Playwright.

Teste pelo menos:

1. abrir home;
2. buscar `LGPD`;
3. buscar `LGDP` e ainda encontrar/sugerir LGPD;
4. buscar `13709/18`;
5. abrir resultado;
6. navegar para histórico;
7. abrir alteração;
8. visualizar diff;
9. acessar fonte oficial;
10. abrir uma norma ainda não materializada e validar fluxo de hidratação.

---

# 56. Teste em produção

Depois do deploy:

abra a URL pública.

Teste de verdade.

Não considere deploy concluído só porque Railway mostrou verde.

Valide:

- home;
- busca;
- fuzzy search;
- API;
- banco;
- worker;
- Redis;
- hydration;
- histórico;
- diff;
- fontes;
- navegação;
- mobile;
- console;
- erros HTTP;
- assets.

Corrija o que encontrar.

---

# 57. Migrations

Use migrations reais.

Deploy novo deve conseguir:

```text
migrate
↓
start
```

Não dependa de criação manual de tabelas.

---

# 58. Bootstrap / seed

Crie scripts claros.

Exemplos:

```bash
make seed
make ingest-hot-laws
make sync-catalog
```

ou equivalentes.

Documente no README.

---

# 59. Environment variables

Crie `.env.example`.

Não commite segredos.

Se uma integração exigir credencial não fornecida:

- não bloqueie o projeto;
- implemente adapter;
- use fallback;
- documente a variável.

---

# 60. Observabilidade

Logs estruturados básicos.

Quero enxergar:

- source;
- job;
- jurisdiction;
- law_id;
- duration;
- fetched;
- created;
- updated;
- skipped;
- errors.

Não adicione Datadog/Sentry apenas por adicionar.

---

# 61. Admin

Não faça painel administrativo complexo.

Se útil, crie scripts/endpoints internos para:

- executar sync;
- executar hydration;
- visualizar último ingest;
- listar falhas.

P2.

---

# 62. IA

Não quero chatbot no MVP.

Não quero IA por moda.

A feature futura:

> Por que este artigo existe?

é ótima.

Mas só depois de:

- texto;
- histórico;
- diff;
- provenance;
- sources

estarem sólidos.

---

# 63. Segurança

Aplicação pública read-only.

No MVP:

- sem login;
- sem contas;
- sem pagamento;
- sem autenticação pública.

Proteja apenas endpoints administrativos/internos se necessário.

---

# 64. Integridade política

LeiAberta deve ser politicamente neutro.

Não atribua julgamento a:

- parlamentares;
- partidos;
- governos;
- projetos;
- votos.

Mostre fatos.

Bom:

> A proposta foi aprovada por 312 votos a 118.

Ruim:

> O Congresso aprovou controversamente...

A menos que exista contexto editorial claramente citado, o que não faz parte deste MVP.

---

# 65. Copy

Todo conteúdo público em PT-BR.

Tom:

- claro;
- neutro;
- moderno;
- institucional sem burocratês.

Exemplos:

- Texto atual
- Histórico
- Alterações
- Blame
- Fonte oficial
- Ver votação
- Ver projeto
- Este dispositivo foi alterado por...
- Informação ainda não identificada.
- Estamos preparando esta norma pela primeira vez.

---

# 66. Prioridades

## P0 — TEM QUE ESTAR PRONTO

- app publicada;
- home bonita;
- catálogo funcional;
- busca nacional;
- aliases;
- fuzzy search;
- parser de número/ano;
- dados reais;
- página da norma;
- estrutura de artigos;
- hydration on demand;
- status de processamento;
- histórico básico;
- diff;
- fontes oficiais;
- cobertura/qualidade;
- PostgreSQL;
- Redis;
- backend/API;
- worker;
- mobile;
- tratamento de erros;
- README;
- testes principais;
- smoke test em produção.

## P1 — FAÇA SE P0 ESTIVER BOM

- blame;
- provenance detalhada;
- PL relacionado;
- autores;
- votações;
- voto individual;
- timeline sofisticada;
- sincronização cron avançada;
- mais adapters estaduais/municipais.

## P2 — SOMENTE SE SOBRAR TEMPO

- export Git das leis;
- provenance graph visual;
- dark mode;
- IA;
- painel admin;
- analytics avançado.

Nunca sacrifique P0 por P1/P2.

---

# 67. Não termine cedo

Não considere concluído porque:

- scaffold foi criado;
- home abriu;
- API respondeu;
- banco conectou;
- deploy ocorreu;
- tabela foi criada.

A tarefa só está concluída quando existe um fluxo real:

```text
HOME
↓
BUSCA
↓
NORMA REAL
↓
ARTIGO
↓
HISTÓRICO
↓
ALTERAÇÃO/DIFF
↓
FONTE OFICIAL
```

E também:

```text
BUSCA POR NORMA AINDA NÃO MATERIALIZADA
↓
NORMA É IDENTIFICADA
↓
HYDRATION JOB
↓
STATUS VISÍVEL
↓
NORMA FICA DISPONÍVEL
```

---

# 68. UX crítica de busca

Antes de considerar pronto, teste:

```text
LGPD
LGDP
13709
13709/18
Lei Geral de Dados
maria da penha
art 7 lgpd
art 121
```

Não aceite uma busca frágil.

---

# 69. Qualidade visual

Não aceite apenas "funciona".

Revise página por página.

Procure:

- espaçamento inconsistente;
- largura ruim;
- fonte pequena;
- cards demais;
- bordas demais;
- diff confuso;
- mobile quebrado;
- loading feio;
- hydration sem feedback;
- timeline pesada;
- busca pouco clara.

Refine.

Quero uma aplicação que eu possa abrir e mostrar sem precisar dizer:

> é só um protótipo.

---

# 70. Commits

Faça commits lógicos.

Exemplos:

```text
feat: scaffold LeiAberta application
feat: add national legislation catalog
feat: add search normalization and fuzzy resolver
feat: add legislation domain model
feat: add official source adapters
feat: add structured law parser
feat: add on-demand hydration pipeline
feat: add law history and diff engine
feat: build law reader interface
feat: add provenance and coverage views
test: add ingestion search and diff coverage
chore: deploy production railway services
```

---

# 71. README

README deve explicar:

- o que é LeiAberta;
- arquitetura;
- como rodar local;
- como executar migrations;
- como sincronizar catálogo;
- como materializar uma norma;
- fontes;
- busca;
- aliases;
- fuzzy search;
- hydration;
- versionamento;
- diff;
- cobertura;
- testes;
- deploy;
- limitações;
- roadmap curto.

---

# 72. Limitações

Documente claramente:

- municípios sem fonte acessível;
- histórico parcial;
- votações não nominais;
- PDFs sem estrutura;
- mudanças de formato dos portais;
- ausência de vínculo automático entre norma e PL;
- diferença entre autor do projeto e autor do texto final.

Nunca diga:

> Parlamentar X escreveu este dispositivo

sem evidência apropriada.

---

# 73. Definition of Done

Considere concluído somente quando:

- [ ] código está no repo;
- [ ] aplicação compila;
- [ ] migrations funcionam;
- [ ] banco de produção existe;
- [ ] Redis funciona;
- [ ] worker funciona;
- [ ] catálogo possui dados reais;
- [ ] busca funciona;
- [ ] busca tolera erros;
- [ ] aliases funcionam;
- [ ] página de norma funciona;
- [ ] artigos são navegáveis;
- [ ] hydration sob demanda funciona;
- [ ] status de hydration aparece;
- [ ] histórico funciona;
- [ ] existe pelo menos um diff real;
- [ ] fontes oficiais funcionam;
- [ ] cobertura/qualidade aparece;
- [ ] layout mobile funciona;
- [ ] testes principais passam;
- [ ] E2E passa;
- [ ] deploy Railway funciona;
- [ ] aplicação pública foi testada;
- [ ] README está atualizado;
- [ ] não há dados fictícios em produção.

---

# 74. Fluxo mínimo de sucesso

Eu quero conseguir abrir o LeiAberta e fazer:

```text
buscar "LGDP"
↓
receber LGPD como sugestão
↓
abrir Lei 13.709/2018
↓
abrir Art. 7º
↓
clicar Histórico
↓
ver alteração
↓
ver ANTES / DEPOIS
↓
clicar Fonte oficial
```

E também:

```text
pesquisar uma norma municipal/estadual ainda não materializada
↓
LeiAberta identifica a norma
↓
mostra metadata
↓
inicia preparação
↓
mostra progresso
↓
materializa
↓
passa a servir instantaneamente
```

Se esses dois fluxos estiverem bons, o MVP está no caminho certo.

---

# 75. Comportamento durante execução

Não fique me perguntando decisões pequenas.

Tome decisões sensatas.

Não interrompa para pedir confirmação sobre:

- nomes de tabela;
- bibliotecas;
- estrutura de pasta;
- pequenas escolhas visuais;
- naming interno;
- refactors;
- migrations;
- deploys normais;
- health checks;
- escolha entre polling/SSE;
- detalhes de cache.

Você é responsável por levar o produto até produção.

Somente pare se existir um bloqueio externo realmente impossível de superar.

Mesmo assim:

avance em todo o restante antes de parar.

---

# 76. Ao final

Entregue resumo objetivo com:

1. URL pública do LeiAberta;
2. o que foi implementado;
3. cobertura atual do catálogo;
4. quais normas estão pré-materializadas;
5. quais fontes oficiais estão sendo usadas;
6. qual exemplo é melhor para demonstrar histórico/diff;
7. quais adapters estaduais/municipais foram implementados;
8. serviços criados no Railway;
9. testes executados e resultados;
10. limitações conhecidas;
11. próximos 5 passos mais valiosos;
12. commits relevantes.

Se algo P1/P2 não foi implementado, diga claramente.

Não esconda limitações.

---

# 77. Princípio final

A visão correta é:

> **Legislação brasileira inteira pesquisável desde o primeiro dia.  
> Processamento profundo sob demanda.**

Não tente reconstruir milhões de normas antecipadamente.

Construa:

```text
CATÁLOGO AMPLO
+
BUSCA INTELIGENTE
+
HYDRATION SOB DEMANDA
+
CACHE
+
VERSIONAMENTO
+
DIFF
+
PROVENANCE
+
FONTES OFICIAIS
```

Essa é a base do LeiAberta.

Agora comece.

Não responda apenas com um plano.

Inspecione o repositório e o Railway fornecidos abaixo e execute o projeto até produção.

---

# REPOSITÓRIO

COLE AQUI O REPOSITÓRIO / LINK / CONTEXTO

---

# RAILWAY

COLE AQUI O PROJETO RAILWAY / LINK / CONTEXTO
