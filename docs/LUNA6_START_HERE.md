# Luna 6 — estado atual

Atualizado em 05/10/2026, com medições de produção às 01:16 UTC. O commit d258fcaf3acb9b7c46904b9423d68cc292f4fc1c está no main. O Railway está com web e worker em SUCCESS; /api/health responde 200. O release inclui a correção do leitor DOU para as resoluções senatoriais recentes.

Leia:

1. [Plano e requisitos completos](LEIABERTA_LUNA6_EXECUTION_PLAN.md)
2. [Requisitos originais](LEIABERTA_ORIGINAL_REQUIREMENTS.md)
3. [Relatório detalhado por tarefa](reports/execution-status.md)
4. [Pesquisa de fontes](research/2026-10-04-source-findings.json)

## Evidência em produção

- Catálogo indexado: 361.980 normas.
- Texto estruturado: 3.385 normas, com 24.029 dispositivos.
- Senado: 47.316 registros; 3.299 com texto; 203 indisponíveis na tentativa mais recente; 43.814 pendentes; 4.679 jobs ativos.
- ALESP/SP: enumeração completa de 181.172 registros, todos gravados; backfill de texto em andamento.
- SINJ-DF: enumeração completa de 125.478 registros; backfill de texto em andamento.
- SAPL/Manaus: a fonte oficial declara 9.846 normas em 99 páginas; sync de produção retomou e registrava 3.300/9.846 na página 33.

Os jobs de hidratação das RSF 24, 25 e 27/2024 concluíram em produção após a correção DOU: 27, 27 e 25 dispositivos estruturados, respectivamente. O endpoint de histórico da Lei Maria da Penha conclui em estado parcial com 65 itens: 3 comparações textuais verificadas e 62 referências oficiais sem texto suficiente para diff; não permanece em “preparando”.

## Validação desta entrega

O teste focal do DOU passou. Uma leitura ao vivo no Senado e no DOU oficial também baixou e extraiu integralmente as três resoluções. Histórico, API de health, catálogos e jobs foram conferidos em produção. O backfill continua como trabalho do worker e não é uma confirmação de que cada texto do catálogo já foi processado.

## Limites e lacunas

- Não existe um único endpoint oficial nacional demonstrado que enumere todas as leis, redações e jurisdições brasileiras. Senado, ALESP, SINJ-DF e SAPL/Manaus têm integrações; os demais portais ainda exigem adapters e reconciliação próprios. Esse trabalho não é impossível em princípio e não deve ser apresentado como concluído.
- O LexML SRU respondeu um desafio anti-automação no probe observado. A interface não forneceu registros utilizáveis nessa sessão.
- Relações oficiais nem sempre vêm com redações anterior e posterior ou datas de vigência por dispositivo. Nessas situações o LeiAberta mostra a referência sem inventar diff.
- No snapshot do SINJ-DF, 5.184 registros não declaravam anexo textual. Fonte alternativa precisa ser identificada para cada item.
- Normas.leg.br classifica algumas transcrições/compilações como não oficiais; a classificação original é preservada.
- Railway Hobby informa maxBackupsCount=0 e as ferramentas conectadas não permitem validar pg_dump/restore. Backup restaurável e staging não foram demonstrados.

A indisponibilidade de um texto em uma tentativa não é necessariamente permanente: o worker pode repetir fontes transitórias. Contadores de pendência mudam enquanto o backfill avança.
