# Luna 6 — estado da execução

O objetivo ativo é deixar busca, leitura e histórico funcionais, ampliar o corpus e publicar no Railway. Só limitações externas comprovadas ficam como bloqueios; adapters ainda não construídos continuam trabalho executável.

Leia:

1. [Plano e requisitos completos](LEIABERTA_LUNA6_EXECUTION_PLAN.md)
2. [Requisitos originais](LEIABERTA_ORIGINAL_REQUIREMENTS.md)
3. [Relatório atualizado por tarefa](reports/execution-status.md)
4. [Pesquisa e limites de fontes](research/2026-10-04-source-findings.json)

## Código e validação desta revisão

Base do GitHub: `main` em `5c0a80454838772588b340b401372524f57e19ab`. A implementação local integra ALESP/SP (181.172 registros) e SINJ-DF (125.478), adapters de texto/histórico, PDF/DOCX/OCR, migration para identificadores longos e contadores de cobertura. Os números estaduais/distritais foram conferidos em bancos isolados e não devem ser descritos como produção antes do deploy.

Validação local após reconciliar o código com o `main`: **71 testes passaram**, **4 E2E passaram**, `compileall` e `git diff --check` passaram. Um PDF oficial SINJ de 214.701 bytes foi extraído para texto legível; páginas digitalizadas seguem o caminho Tesseract português no container Docker.

## Próxima ação imediata

Criar PR contra o SHA atual de `main`, mesclar após conferir arquivos/manifestos, aguardar os deploys web e worker do Railway, verificar migration e `/health`, `/api/stats`, busca SP/DF, hidratação PDF e histórico ALESP/SINJ. Registrar os IDs e contagens de produção em `reports/execution-status.md`.

## Estado de cobertura

O Senado enumerou 47.327 entradas em seis categorias; ALESP enumerou 181.172 registros e SINJ-DF 125.478. O portal SINJ variou metadados entre snapshots; no segundo, 5.184 registros não declaravam anexo textual. A sincronização de catálogos não pré-processa todo o conteúdo: captura de texto é sob demanda e o worker alimenta lotes federais com backpressure.

Esses três acervos não correspondem a todas as leis do Brasil. Integração dos outros 25 estados, Câmara dos Deputados, municípios/SAPL e fontes oficiais alternativas continua aberta. Não classificar esse trabalho como impossibilidade técnica antes de verificar os portais de cada jurisdição.

## Limitações externas verificadas

- Railway Hobby informa `maxBackupsCount=0`. O conjunto de conectores desta sessão não oferece shell, `pg_dump` ou duplicação/restauração de ambiente; backup restaurável/staging não foi demonstrado.
- O probe da rota LexML SRU recebeu página de desafio anti-automação em vez de registros. Requer uma rota autorizada acessível ou mudança no acesso do portal.
- Relações de alteração nem sempre incluem redações anteriores/atuais por dispositivo ou data de vigência. Essas entradas continuam relações pendentes, sem texto fabricado.
- O SINJ-DF não anunciava anexo textual para 5.184 registros do snapshot observado; buscar diários/repositórios oficiais alternativos é trabalho pendente.
- Normas.leg.br declara valor jurídico não oficial para muitas transcrições e compilações. O produto conserva o rótulo da fonte.

Não declarar que “todas as leis” estão no catálogo enquanto as jurisdições e seus acervos não forem enumerados e reconciliados individualmente.
