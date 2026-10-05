# Checklist de lançamento

## Produto e demo
- [x] Home explica o valor e oferece CTA direto para um antes/depois real: Código Civil, art. 389.
- [x] A comparação apresenta as duas redações, o ato relacionado e a origem da transcrição.
- [x] A interface identifica o texto histórico de Normas.leg.br como valor jurídico não oficial e não afirma vigência com base apenas na data registrada.
- [x] Blame e proveniência não inventam autoria pessoal; estados desconhecidos e parciais ficam explícitos.
- [x] Busca tolera `LGDP`, artigos têm deep links e páginas de fontes, cobertura e sobre consultam dados atuais.
- [x] O escopo do exemplo e a cobertura parcial da lei estão descritos sem alegar completude.

## Novas normas
- [x] Refresh, TTLs e retry revalidados para os adapters que existem.
- [x] Fixture verifica descoberta, upsert idempotente, busca, elegibilidade para hidratação e recuperação depois de falha.
- [x] Falha temporária mantém registros persistidos; catálogo, texto e histórico são estados distintos.
- [x] Fontes sem adapter ativo e os limites da atualização automática estão documentados.

## Engenharia e produção
- [x] CI verde para Python, imagem Docker e Playwright nos PRs de produto.
- [x] PR #71 launch polish, PR #72 correção mobile, PR #73 troca do hero para a comparação real; todos integrados.
- [x] Railway web, worker e backup `SUCCESS`; PostgreSQL e Redis online.
- [x] `/health`, `/ready` e `/worker-health` respondem 200.
- [x] 150 testes Python e 2 E2E aprovados; matrix browser de 36 combinações (9 rotas × 4 larguras) sem overflow, falhas de rede ou erros JS.
- [x] Smoke de produção confirma busca, artigo, histórico, diff, Blame, fontes e documentação.

## OSS e material de lançamento
- [x] README, API, arquitetura, contribuição, changelog e exemplos atualizados.
- [x] Relatório final, fact sheet, case, roteiro de demo e cópias sociais preparados.
- [x] 9 screenshots, imagem OG, captura dedicada do diff e demo WebM registrados na produção.
- [x] Conteúdo de redes sociais não foi publicado.
- [x] Release/tag [v0.1.0](https://github.com/DIDIDXX/LeiAberta/releases/tag/v0.1.0) publicada após integrar os assets.

## Bloqueios externos / opcionais
- [!] Descrição, homepage e topics do repositório: GitHub respondeu 403 `Resource not accessible by integration`; requer permissão administrativa.
- [!] Railway tem uma remoção destrutiva preexistente staged para `pg-diagnostic`; ficou sem aplicar e fora do deploy do app.
- [ ] Domínio próprio é opcional; o domínio Railway de produção funciona.
- [ ] Custos de billing não foram verificados porque a fatura não estava acessível.
