# Mídia de lançamento

As três capturas `launch/assets/*20261007.png` foram geradas por Playwright contra a produção depois do deploy `c6e74a3c47fa7b5edb4a596ecf10c59a27860370`. O teste mediu `scrollWidth` igual à largura do viewport e não capturou erro de console, falha de request ou resposta 5xx. As capturas mostram a interface e dados reais; não simulam evidência jurídica.

| Uso | Arquivo | Texto alternativo |
|---|---|---|
| Comparação desktop | [Diff do art. 389 — desktop, 1440 px](assets/art389-diff-desktop-20261007.png) | Comparação do art. 389 do Código Civil antes e depois da Lei 14.905/2024, com a nota de que a transcrição histórica do Normas.leg.br é classificada como valor jurídico não oficial. |
| Leitor mobile | [Art. 389 — mobile, 390 px](assets/art389-mobile-20261007.png) | Tela mobile real mostrando o texto do art. 389, link para explicar a proveniência e artigo seguinte; o texto separa “advogado.” de “Produção de efeitos”. |
| Histórico e proveniência | [Blame do art. 389 — desktop, 1440 px](assets/art389-blame-desktop-20261007.png) | Painel real do Blame que relaciona o art. 389 à comparação registrada e explica que a transcrição citada não é oficial e que a data registrada não confirma vigência. |
| Home mobile | [Home — mobile, 390 px](../final-ops/evidence/2026-10-07-home-390.png) | Página inicial real com navegação, hero e campo de busca em largura mobile. |
| Contexto do produto | [Home — desktop, 1440 px](../final-ops/evidence/2026-10-07-home-1440.png) | Página inicial do LeiAberta com busca e acesso ao catálogo de legislação. Capturada na interface de produção durante o QA de 07/10. |
| Captura adicional do diff | [Diff anterior — mobile, 390 px](../final-ops/evidence/2026-10-07-diff-390.png) | Comparação do art. 389 em painéis empilhados com ressalva jurídica visível; capturada antes do deploy final. |
| Demonstração em vídeo | [demo.webm](../assets/launch/demo.webm) | Gravação da interface real percorrendo busca, texto da lei, histórico e comparação antes/depois. |

A interface exibe cobertura parcial. A imagem não deve ser legendada como prova primária dos trechos anterior e posterior do art. 389. O produto continua exibindo que a comparação histórica usa a transcrição do Normas.leg.br classificada como não oficial.
