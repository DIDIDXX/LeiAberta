# LeiAberta — status final de execução

Data: 2026-10-05. Repositório: `DIDIDXX/LeiAberta`. URL pública: https://web-production-12e95.up.railway.app.

## Produção confirmada após PR #62

- SHA implantado: `81982a28d36836563acf83b7115af355b31ea830` (`Prevent horizontal overflow on mobile law pages`).
- Deploys SUCCESS: web `679ff153-080e-4ee1-9e88-27b2a52c7a77`; worker `034f637d-1546-461e-9d36-a69861d7582c`; backup `6c2e5d02-39cb-4b38-a08f-56acab1cd3bc`. Web e worker estão online, uma réplica cada; Postgres e Redis seguem SUCCESS.
- Playwright real em viewport 390px e 1440px: busca “LGDP” encontrou Lei 13.709/2018, Art. 7 abriu, scroll width = viewport width, sem erros de console, pageerror ou request.
- Smoke público: `/health` 200 em 0,395s; typo search 200 em 0,390s; busca `art 7 LGPD` 200 em 2,705s sob execução concorrente; lei HTML 200 em 0,396s; nodes Art. 7 200 em 0,409s; histórico Maria da Penha 200 em 0,416s; sitemap index 200 em 0,485s; stats 200 em 0,896s. São amostras individuais, não p95.
- A UI de histórico agora permite solicitar preparação e apresenta evidência parcial com transparência. Maria da Penha permanece parcial: 65 relações, 62 sem texto pareado; nenhum diff foi inventado para essas relações.

## Correções acumuladas integradas

- Corrigidos os gargalos comprovados de `/api/stats`, sugestões typo e sitemap; adicionados canonical/metadata e conteúdo sem JavaScript limitado.
- Melhorias de busca mantêm o alias oficial da LGPD acima do falso positivo “LGDP”.
- Adicionados headers básicos, CSP, imagem Docker non-root, CI, Dependabot, licença MIT, guias OSS e runbook de backup/restore.
- Corrigido overflow de textos longos na página mobile de lei; CI do PR #62 passou (Python, E2E, imagem Docker).
- Testes locais do hardening complementar atual: 138 Python e 5 Playwright E2E passaram; uma advertência upstream de depreciação Starlette/httpx continua.

## Hardening complementar em andamento

O hardening PR #63 (`f31a06e`) já está implantado: CSP, `/ready` (DB + Alembic heads) e limite Planalto 25 MB. Browser encontrou o Google Fonts bloqueado pela CSP; PR #64 ajusta a política para permitir somente `fonts.googleapis.com` e `fonts.gstatic.com` em estilos/fontes. A validação final desse ajuste ainda precisa CI, deploy e novo smoke sem erros.

## Pendências reais e limites

1. **“Todas as leis” do Brasil não é uma meta verificável com as fontes disponíveis:** não há denominador nacional único e o inventário inclui leis federais e integrações estaduais/municipais selecionadas, com cobertura e materialização incompletas. Expandir estados/municípios exige descoberta e validação fonte a fonte; nunca apresentar catálogo parcial como completo.
2. **Accesso de auditoria:** Railway connector não oferece SQL read-only/EXPLAIN nem fatura; tamanhos por tabela/índice, conexões, queue age, invoice e p95 controlado não foram medidos. Volume Postgres observado: 3,053/5 GB na baseline. São limitações de ferramenta/sessão, não prova de ausência de risco.
3. **Identidade de cliente e rate limit:** a origem confiável de client IP no proxy Railway ainda não foi comprovada; limiter por IP baseado em `X-Forwarded-For` sem essa validação seria spoofável. Dedupe e limites da fila seguem ativos.
4. **Redirect dos fetchers:** Planalto agora tem cap de corpo; validação uniforme de host final/scheme e limites de todos os adapters ainda requer fixtures de cada fonte oficial/mirror.
5. **Recurso diagnóstico Railway:** remoção está staged, mas efetivação exige 2FA via Railway Dashboard; a ferramenta MCP recusou por falta de 2FA. Serviço sem volume e fora do caminho do produto.
6. **Heartbeat do worker:** Railway mostra o worker Online; falta heartbeat de aplicação separado com regra de frescor.

## Próxima ação

Concluir CI/merge/deploy do hardening complementar, validar `/ready` em produção e repetir o smoke mobile. Depois publicar este status com o SHA final. Aplicar a exclusão staged do serviço diagnóstico no Dashboard com 2FA quando o responsável acessar a conta.
