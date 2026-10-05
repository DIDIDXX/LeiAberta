# LeiAberta — estado da execução

Atualizado em 05/10/2026 às 02:16 UTC. Código em produção: main 953b10f10e7e9daca53cab215e72e8b728308a4c. Railway web e worker estão em SUCCESS; /api/health responde 200. Deploys: web 552576e2-b37b-41eb-a53a-573f0a3dae33; worker 77a4d645-b3f1-4422-ab0a-1742df97f863.

## Entregas verificadas

- Busca, leitura por dispositivo e histórico da Lei Maria da Penha funcionam. O histórico retorna 65 itens: 3 diffs textuais conferidos e 62 relações oficiais sem redações pareadas; não há job preso em preparação.
- A correção do leitor DOU recuperou as RSF 24, 25 e 27/2024. Os três jobs em produção concluíram com 27, 27 e 25 dispositivos.
- Catálogo ALESP/SP: 181.172 registros enumerados e gravados.
- Catálogo SINJ-DF: 125.478 registros enumerados e gravados.
- Catálogo SAPL/Manaus: 9.846 de 9.846 registros conferidos em 99 páginas; 9.846 registros no banco.
- Backfill de texto segue ativo. Na medição acima havia 4.397 normas com texto estruturado, 29.902 dispositivos e 5.205 jobs ativos. O worker foi ampliado para 16 tarefas simultâneas; logo após o deploy concluiu 80 hidratações em cerca de 88 segundos.
- A Lei municipal 115/1949 foi localizada, hidratada e teve histórico consultado. O histórico terminou sem job ativo e sem relações retornadas pela fonte; a auditoria textual exige revisão e não certifica completude.
- Validação local: 88 testes passaram; 4 cenários E2E passaram, incluindo leitura, busca e diff histórico.

## Cobertura que existe hoje

O catálogo inclui seis categorias federais do Senado, ALESP/SP, SINJ-DF e SAPL/Manaus. Isso é uma ampliação confirmada, não um catálogo de todas as leis brasileiras. A integração dos demais órgãos estaduais e municipais ainda precisa ser construída e validada fonte por fonte.

O relatório detalhado está em [reports/execution-status.md](reports/execution-status.md). O plano completo e seus critérios continuam em [LEIABERTA_LUNA6_EXECUTION_PLAN.md](LEIABERTA_LUNA6_EXECUTION_PLAN.md).

## Limitações observadas e trabalho que continua

- Não foi demonstrado um endpoint oficial nacional que enumere todas as jurisdições e redações. Isso não torna impossível integrar as fontes locais; os adapters ainda não construídos são trabalho executável.
- A rota SRU do LexML devolveu desafio HTML anti-automação, sem registros utilizáveis.
- No snapshot consultado do SINJ-DF, 5.184 normas não anunciavam arquivo textual. Encontrar fonte oficial alternativa para elas continua pendente.
- Uma referência de alteração sem os textos anterior e posterior não pode gerar diff jurídico confiável.
- Railway Hobby informa maxBackupsCount=0, e as ferramentas conectadas não permitem executar ou validar pg_dump/restore. Backup restaurável e staging permanecem bloqueados por plano/acesso.

Os contadores de hidratação mudam continuamente. Texto baixado, texto completo, estrutura completa e histórico completo são estados distintos. Nenhuma norma recebe selo de completude apenas por ter sido processada.