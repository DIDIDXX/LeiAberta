# Ações manuais

- **Domínio próprio:** nenhum domínio foi comprado ou alterado. Se o mantenedor decidir usar `leiaberta.org`, registrar o domínio fora do Railway e então seguir [CUSTOM_DOMAIN.md](CUSTOM_DOMAIN.md) para verificar DNS/TLS. Não bloqueia a publicação atual em `up.railway.app`.
- **Posts:** textos em `POSTS.md` estão prontos, mas não foram publicados.
- **Billing:** o conector desta sessão não expôs fatura; por isso o fact sheet não estima preço mensal.
- **Patch Railway preexistente:** há uma alteração staged de produção para remover o serviço `pg-diagnostic-8187f5d5-103d-45b9-992c-d60926ae3276` (marcada como destrutiva no Railway). Deixei-a sem commit ao publicar o app, pois não é necessária ao lançamento e o estado/uso do serviço não pôde ser inspecionado (`describe-service` respondeu `INVALID_ARGUMENT`). Se a remoção ainda for desejada, revisar o serviço e concluir o patch separadamente no Railway.

Não há outra ação manual necessária para o fluxo técnico de merge/deploy se CI e permissões GitHub/Railway permanecerem disponíveis.
