# Execução do plano LeiAberta — Luna 6

Atualizado em 04/10/2026. Este relatório registra o código preparado nesta execução, evidências observadas e limites de cobertura. O commit base em `main` é `b42466a`; as alterações descritas abaixo ainda precisam ser publicadas e passar pelo deploy Railway antes de constarem como produção.

## Resultado desta execução

O histórico passou a usar duas fontes oficiais complementares: relações por dispositivo da API do Senado e registros de versões/textos do Normas.leg.br ligados pela URN fornecida pelo Senado. Uma execução real isolada para a LGPD consultou 146 relações e encontrou 54 mudanças com textos anterior e posterior. Persistiu 54 comparações e deixou 98 relações sem redação histórica conferida. A resposta registra `partial`, pendências e datas de vigência não verificadas. A página do histórico exibe comparações e relações pendentes em linhas distintas.

O catálogo federal validado pelo Senado cresceu para seis tipos: `LEI`, `LCP`, `EMC`, `MPV`, `DLG` e `RSF`. Uma sincronização real atual importou 47.327 registros, sem erros; uma segunda execução não adicionou identidades duplicadas. A interface de catálogo não confunde metadados com texto: documentos frios podem ser preparados pelo worker, e `/api/stats` separa total, textos obtidos, indisponíveis, pendentes e jobs ativos. Ao publicar esta versão, o worker continuará a enfileirar 100 textos por lote a cada cinco minutos até esgotar o catálogo disponível.

As fontes do Senado encaminham para HTML de texto integral no Normas.leg.br. O portal classifica as representações analisadas como `UnofficialLegalValue`; a API preserva essa classificação e a exibe. Uma resposta HTML parseável não prova que o texto consolidado é oficial nem que anexos foram incluídos.

## Matriz de execução

| Itens do plano | Situação | Evidência / limite atual |
|---|---|---|
| T00 linha de base | concluído na entrega anterior | Aplicação e serviços Railway identificados; a produção existente segue em `https://web-production-12e95.up.railway.app`. |
| T01 backup e staging | bloqueado pela conta/ferramentas desta sessão | Railway informa workspace Hobby com `maxBackupsCount=0`; backup de volume não pode ser criado nesse plano. O Railway MCP desta sessão não fornece shell do serviço, `pg_dump`, mutação GraphQL nem comando de duplicação de ambiente; o CLI também não está instalado. Nenhuma credencial foi exposta, nenhum serviço de produção foi reiniciado e nenhum backup foi declarado como feito. O usuário teria de habilitar backups/Pro ou fornecer um caminho de CLI/execução. |
| T02 estados de histórico | implementado | Estados e cobertura diferenciam não solicitado, em fila, concluído parcialmente, referência encontrada e comparação textual comprovada. |
| T03 fila e outbox | implementado | Fila Redis Streams, outbox durável, deduplicação, retomada e espera pelo schema Alembic; 42 testes passaram. |
| T04 arquivo de fontes | implementado no código | Migration 0006 permite arquivar bytes brutos antes do parse e associá-los à versão depois. Auditoria em lote percorre capturas antigas. Ainda não está implantado nesta revisão. |
| T05 parsing e identidade | implementado para estruturas cobertas | Corrige milhar, ordinal, sufixos de reedição como `MPV 2.206-1`, variantes repetidas e separação Constituição/ADCT; fixtures oficiais e testes passam. |
| T06 PDF e anexos | sem suporte nesta entrega | O texto HTML ligado pelo catálogo não garante anexos; não foi encontrada uma relação uniforme e verificável para baixar/processar todos os anexos. Não se apresenta texto HTML como pacote documental completo. |
| T07 auditoria documental | auditor implementado; cobertura ainda parcial | API `/audit` compara segmentos HTML identificáveis com nós parseados. É uma checagem estrutural conservadora; não prova completude jurídica, anexos, notas ou tabelas. |
| T08 leitura progressiva | parcial | Busca, detalhe, artigos e progresso por job funcionam. Navegação integral de anexos e todo tipo de subdivisão editorial depende da fonte e parser. |
| T09 jurisdições e registro de fontes | parcial | IBGE fornece diretório territorial, não catálogo de normas. 27 UFs e 5.571 localidades não significam leis municipais sincronizadas. |
| T10 sync retomável | implementado para o catálogo do Senado | Tipos podem ser sincronizados separadamente; commits em blocos, frescor de 24 horas e identidade remota tornam a reexecução segura. |
| T11 Senado/Câmara | Senado implementado para seis tipos; Câmara não | Os seis endpoints do Senado enumeraram 47.327 itens. O conjunto não prova todos os atos federais; catálogo da Câmara não está integrado. |
| T12 LexML | sem adapter funcional | A busca SRU testada respondeu desafio HTML em vez de resultado utilizável. O portal não foi tratado como catálogo sincronizado. |
| T13 ALESP/SINJ-DF | registro inicial de fonte | Há entrypoints identificados, mas sem contrato de paginação e adapter validado nesta execução. |
| T14 SAPL e piloto municipal | não concluído | Existem implementações SAPL reutilizáveis em upstream, mas os hosts/escopos locais ainda precisam ser confirmados um a um; não há um endpoint oficial único para municípios. |
| T15 catálogo nacional | limitado pelas fontes integradas | Não existe feed único consultado que enumere todos os atos estaduais/municipais. Cada assembleia e câmara municipal exige descoberta/adapter próprio. |
| T16 busca | implementado para dados locais | Consulta exata, fuzzy e identidade número/ano/sufixo têm cobertura de teste; não implica catálogo nacional. |
| T17/T19 histórico e versões | histórico textual genérico para registros Normas disponíveis | Em teste real da LGPD: 54 comparações de 146 relações. 98 relações continuam sem antes/depois. Vigência por dispositivo não foi inferida. |
| T18 tempo jurídico | parcial | Datas de assinatura e publicação são mantidas separadas; a vigência efetiva continua não verificada quando a fonte não a prova. |
| T20 timeline/diff | implementado para evidência existente | Diff aparece apenas com textos anterior e posterior. Referências sem comparação permanecem identificadas como pendentes. |
| T21 provenance/blame | parcial | Cada diff guarda ato alterador, fonte e texto comparado; autoria de trechos e processo legislativo não vêm automaticamente do registro de dispositivo. |
| T22 histórico em lote | implementado para textos do Senado; histórico em lote amplo não | O worker enfileira materialização de textos do catálogo. O processamento de relações/diffs históricos é sob demanda por norma. |
| T23/T24 autoria, processos e votos | fontes identificadas, produto não implementado | Existem endpoints legislativos para tramitação e votação, mas vínculo confiável de cada alteração da lei ao processo, emendas, autoria e votos é uma integração separada não concluída. |
| T25 scheduler e freshness | parcial implementado | Worker verifica atualizações do catálogo e IBGE e agenda backfill de texto. Ainda faltam alertas/métricas de cobertura por cada jurisdição. |
| T26 release Railway | aguarda publicação desta revisão | Os serviços atuais estão online. O deploy do código descrito aqui só será marcado completo após merge, deploy `SUCCESS` do web/worker e smoke público. Migrations desta revisão são aditivas: nulabilidade/arquivo e índice. |
| T27 documentação | atualizado junto à implementação | README, achados de fontes, manifesto do catálogo, este relatório e handoff do Luna devem acompanhar a publicação final. |

## Validação desta revisão

- `.venv/bin/pytest -q`: **42 passed** (3 avisos de depreciação/configuração).
- `npm run test:e2e`: **4 passed**, incluindo busca, leitura, histórico com diff oficial, hidratação sob demanda e desambiguação por artigo.
- `python -m compileall -q app migrations tests scripts` e `git diff --check`: passaram.
- Alembic 0001–0007 aplicado numa base SQLite descartável.
- Catálogo real: 47.327 registros nos seis tipos, zero erros; segunda execução: zero novas identidades e 47.327 atualizadas.
- Histórico LGPD em DB isolado: 146 relações, 54 diffs com antes/depois, 98 pendências; status `partial`, datas de vigência não verificadas.
- Hidratação real de `MPV 2.206-1/2001` em DB isolado: job concluído, 10 artigos, 35 nós estruturados; classificação jurídica não oficial e auditoria em revisão.
- Estas provas locais não são contagens da base de produção. A expansão só será contabilizada na produção após o próximo deploy.

## Bloqueios técnicos específicos

1. **Backup restaurável e staging Railway:** a conta Hobby não oferece backups de volume e as ferramentas desta sessão não têm CLI/shell/GraphQL para exportar Postgres ou duplicar ambiente. Não há um jeito seguro de fingir um restore validado. O código e as migrations aditivas continuam publicáveis; a proteção de backup operacional exige acesso/plano habilitado.
2. **“Todas as leis” do Brasil:** não há uma API oficial nacional única que enumere leis e atos das 27 UFs e 5.571 localidades. Os endpoints consultados enumeram apenas os seis tipos indicados do Senado. Cada órgão exige fonte, identidade, paginação, política de acesso e verificação próprias; um número total nacional não pode ser demonstrado pelas fontes disponíveis.
3. **Texto juridicamente oficial consolidado:** o Normas.leg.br entrega transcrições e compilações cuja própria classificação inclui valor jurídico não oficial. O LeiAberta guarda e mostra esse rótulo; não pode convertê-las em publicação oficial consolidada sem uma fonte que certifique isso.
4. **Histórico integral e vigência:** relações identificam atos candidatos, mas muitas versões por dispositivo não têm texto anterior/posterior nem data de eficácia verificável. O sistema apresenta 98 pendências reais no teste LGPD e não cria comparações sintéticas.
5. **Anexos e documentos digitalizados:** sem link oficial e conteúdo efetivamente obtido, OCR ou parse não é possível. A auditoria permanece parcial até as fontes documentais serem enumeradas.

Não declarar cobertura nacional completa. O próximo estado de produção deve ser acrescentado aqui com SHA do merge, IDs de deploy, contadores ao vivo e resultado de buscas/hidratações públicas.
