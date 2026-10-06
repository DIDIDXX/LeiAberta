# Ações externas

- **Metadados GitHub:** tentei definir descrição, homepage e topics do repositório; a integração retornou 403 `Resource not accessible by integration`. Com permissão de administrador, abra `https://github.com/DIDIDXX/LeiAberta/settings` → **General** e aplique:
  - **Description:** `Open-source traceability layer for Brazilian legislation: text, amendments, provenance and official sources.`
  - **Website:** `https://web-production-12e95.up.railway.app`
  - **Topics:** `brazil`, `legislation`, `civic-tech`, `open-data`, `legaltech`, `data-engineering`, `fastapi`, `postgresql`, `open-source`.
  Confirme que Website abre a produção e que cada topic foi adicionado antes de salvar.
- **Patch Railway preexistente:** uma remoção destrutiva de `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276` estava staged. Não a apliquei porque não pertence ao deploy do produto e o serviço não pôde ser inspecionado (`describe-service` retornou `INVALID_ARGUMENT`). É preciso revisar o serviço no Dashboard antes de decidir a remoção.
- **Domínio próprio:** opcional. Nenhum domínio foi comprado ou alterado; a produção em `up.railway.app` funciona. Para usar domínio próprio, o mantenedor deve registrá-lo e configurar DNS/TLS conforme [CUSTOM_DOMAIN.md](CUSTOM_DOMAIN.md).
- **Billing/custo real:** a fatura e o plano não estavam disponíveis. O custo efetivo é desconhecido até medir o uso após as mudanças e conferir a fatura. Valores por CPU/RAM e tarifas publicadas são estimativas, não custo confirmado.
- **Redes sociais:** os textos em `POSTS.md` estão prontos e não foram publicados.

Não há ação manual necessária para usar o app ou acessar a demo pública.
