# Checklist persistente do launch

Estados: `[ ]` pendente, `[~]` em andamento, `[x]` concluído, `[!]` bloqueio técnico/externo demonstrado.

## Inspeção e novas normas
- [x] SHA, serviços, health e dados de produção revalidados.
- [x] Políticas de refresh e freshness por adapter mapeadas.
- [x] Fixture cobre descoberta, upsert repetido, falha preservando dados, retry, busca e hidratação elegível.
- [x] Fontes sem adapter ficam fora da promessa de atualização automática.

## Produto e demo
- [x] Home explica valor em 10 segundos e aponta para alteração real.
- [x] Hero: Código Civil, art. 389, com texto anterior e posterior existentes.
- [x] A página identifica Normas.leg.br como transcrição não oficial e não chama a data de vigência.
- [x] Explicação/Blame por dispositivo com evidência parcial e desconhecida explícitas.
- [x] `/fontes`, `/cobertura`, `/sobre`; freshness e lacunas sem implicar cobertura integral.
- [x] Deep link de artigo com canonical e OpenGraph server-side.
- [x] Busca `LGDP` encontra a LGPD.

## Produção e engenharia
- [x] E2E local: 2 passaram, incluindo antes/depois e home mobile com métricas grandes.
- [x] Suíte Python: 150 passaram.
- [x] CI GitHub (python, image, e2e) verde.
- [x] Railway web, worker e backup `SUCCESS`; PostgreSQL e Redis online no SHA `c66c0138f03b1a83310c07089c265654785706ae`.
- [x] `/health`, `/ready`, `/worker-health` respondem 200.
- [x] Browser matrix: 36 combinações (9 páginas × 4 larguras: 390/430/768/1440 px), sem overflow, erro JS/console, falha de rede ou imagem quebrada.
- [x] Limites, CSP, headers, sitemap e heartbeat preservados.
- [x] Sem migrations nem serviço pago novo.

## OSS e kit
- [x] README, API, quickstart, inglês, contribuição e diagrama.
- [x] Fact sheet, case study, hero case, roteiros de demonstração e ações de configuração.
- [x] 9 screenshots reais do deploy, OG PNG e demo WebM em `docs/assets/launch/`.
- [x] Cinco issues úteis com rótulos `good first issue` e outros rótulos existentes.
- [x] Release/tag [v0.1.0](https://github.com/DIDIDXX/LeiAberta/releases/tag/v0.1.0), apontada ao commit de produção com o kit integrado.
- [!] Descrição/homepage/topics: GitHub retornou 403 `Resource not accessible by integration`; exige mantenedor com permissão administrativa.

## Ações externas separadas
- [!] Railway tem um patch destrutivo staged, anterior a esta rodada, que remove `pg-diagnostic`. Não foi aplicado junto com o deploy do app.
- [ ] Domínio próprio opcional; produção atual no domínio Railway funciona.
- [ ] Conferir fatura/custo; billing não estava acessível nesta sessão.
