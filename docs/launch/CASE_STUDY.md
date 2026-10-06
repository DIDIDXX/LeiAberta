# Construindo um “Git blame” para a legislação brasileira

## Problema

Em código, um blame mostra qual commit introduziu uma linha. Em legislação, um vínculo para uma lei relacionada não basta: é preciso obter textos comparáveis, identificar o dispositivo estável e localizar a evidência oficial que sustenta a mudança.

## Dados e arquitetura

Portais distintos expõem catálogos, HTML, PDF, identificadores e níveis de cobertura diferentes. O LeiAberta sincroniza metadados por adapters incrementais, armazena normas no PostgreSQL, captura documentos oficiais, calcula SHA-256 e guarda parser/versionamento. Dispositivos recebem IDs estruturados; jobs de texto, histórico e tramitação passam pelo Redis Streams e um worker.

O desafio não é baixar HTML. É saber quando a fonte oficial permite afirmar que um dispositivo realmente mudou.

## Semântica primeiro

- Relação legislativa não é diff textual.
- `retrieved_at` é a hora de captura, não a vigência.
- Proponente, autor de emenda, relator, Casa, votação e sanção são papéis diferentes; nenhum identifica automaticamente quem redigiu cada linha.
- A comparação exige before/after observáveis. Onde falta texto pareado, o sistema diz que a relação foi localizada e a reconstrução está pendente.

## Engenharia de dados

O pipeline usa upsert idempotente por identidade oficial, checkpoint de paginação quando disponível, snapshots imutáveis, checksum, versões de parser, IDs de dispositivo, jobs deduplicados, budgets de fila, retry limitado e agregações por fonte. A busca fuzzy limita candidatos em SQL em vez de percorrer o catálogo de milhões de linhas em Python.

Métricas de produção são agregadas em `/api/stats`. Os números variam e não representam o universo legal brasileiro.

## Filosofia operacional e custo

O objetivo econômico é desacoplar descoberta de conteúdo e materialização profunda: preservar a atualização automática de catálogos e usar capacidade limitada para hidratações acionadas por leitura/pedido, com backfill em lote pausável e limitado. A implementação e o comportamento efetivo devem ser confirmados no commit de produção e nos logs antes de apresentar essa arquitetura como resultado.

Não há número de custo real certificado neste estudo. A fatura/plano Railway e uma medição pós-mudança comparável ainda são necessárias; qualquer valor calculado por médias de CPU/RAM ou tarifas públicas é uma projeção, não a conta do serviço. Também não se declara redução de incidentes ou crescimento de disco evitado sem séries observadas antes e depois. Observações pontuais — como um timeout de endpoint ou um healthcheck 503 — devem ser descritas com horário, fonte e recuperação observada, sem generalizar para uma taxa de incidente nem atribuir causa sem evidência.

## Escala, segurança e custo

FastAPI serve interface HTML/CSS/JS e API. PostgreSQL guarda estado, Redis Streams distribui jobs e Railway hospeda API/worker/dados gerenciados. A ingestão usa limites de bytes, timeout, allowlists, validação de redirects e concorrência por fonte. Não adicionamos mecanismo de busca distribuído nem serviço recorrente pago para a demonstração. O custo financeiro não foi confirmado por fatura.

## Limitações e próximos passos

Catálogos federais e subnacionais têm denominadores e modelos diferentes. Muitas jurisdições brasileiras ainda não estão integradas; texto e histórico podem ficar pendentes mesmo após catalogação. Prioridades: ampliar adapters com fixtures verificáveis, auditar completude documental, reconstruir versões históricas e associar processos/votos somente quando a identidade oficial fechar.
