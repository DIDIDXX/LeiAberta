# Ações externas

- **Metadados GitHub:** tentei definir descrição, homepage e topics do repositório; a integração retornou 403 `Resource not accessible by integration`. Com permissão de administrador, abra `https://github.com/DIDIDXX/LeiAberta/settings` → **General** e aplique:
  - **Description:** `Open-source traceability layer for Brazilian legislation: text, amendments, provenance and official sources.`
  - **Website:** `https://web-production-12e95.up.railway.app`
  - **Topics:** `brazil`, `legislation`, `civic-tech`, `open-data`, `legaltech`, `data-engineering`, `fastapi`, `postgresql`, `open-source`.
  Confirme que Website abre a produção e que cada topic foi adicionado antes de salvar.
- **Railway — único bloqueio manual atual:** a exclusão staged de `pg-diagnostic` foi descartada pelo coordenador; o serviço ativo não foi removido nem alterado. O único change staged agora é o aumento não destrutivo do volume persistente do Postgres de **5.000 MB para 6.500 MB**, aguardando autenticação 2FA do proprietário. No Railway Dashboard, abra o projeto **LeiAberta** → ambiente **production** → **Review Changes / Pending Changes**. Antes de aplicar, confirme que há exatamente uma mudança: serviço **Postgres**, volume **5.000 → 6.500 MB**. Se aparecer qualquer outra alteração — especialmente uma exclusão de serviço — não aplique e peça revisão. Se a lista tiver somente esse resize, o proprietário pode autenticar com 2FA, revisar o impacto de custo/limites do plano e selecionar **Apply Changes**. Depois, confirme no Dashboard que o serviço e o volume estão saudáveis. Esta sessão não aplicou a mudança.
- **Domínio próprio:** opcional. Nenhum domínio foi comprado ou alterado; a produção em `up.railway.app` funciona. Para usar domínio próprio, o mantenedor deve registrá-lo e configurar DNS/TLS conforme [CUSTOM_DOMAIN.md](CUSTOM_DOMAIN.md).
- **Billing/custo real:** a fatura e o plano não estavam disponíveis. O custo efetivo é desconhecido até medir o uso após as mudanças e conferir a fatura. Valores por CPU/RAM e tarifas publicadas são estimativas, não custo confirmado.
- **Redes sociais:** os textos em `POSTS.md` estão prontos e não foram publicados.

Não há ação manual necessária para usar o app ou acessar a demo pública.
