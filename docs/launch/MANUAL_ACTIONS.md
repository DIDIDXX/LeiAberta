# Ações manuais restantes

Atualizado em 2026-10-07 com revalidação de produção, backup diário e inspeção do repositório.

## Antes da divulgação

1. **GitHub About:** o repositório está público, mas descrição, homepage e topics permanecem vazios. O navegador e o token local não estão autenticados; não consegui gravar esses metadados. Com uma sessão GitHub autenticada, abrir `https://github.com/DIDIDXX/LeiAberta` → About → Edit e salvar:
   - Description: `Open-source platform for exploring Brazilian legislation, verified amendments and legal provenance.`
   - Website: `https://web-production-12e95.up.railway.app`
   - Topics: `brazil`, `legislation`, `civic-tech`, `open-data`, `legaltech`, `data-engineering`, `fastapi`, `postgresql`, `open-source`.
2. Revisar os textos em [POSTS.md](POSTS.md) e as mídias em [MEDIA.md](MEDIA.md). O proprietário publica no LinkedIn e no X; nenhum post foi publicado.
3. Não excluir o serviço `Postgres` antigo agora. A tentativa read-only encontrou o serviço em recovery e os manifests antigos não identificam o banco de origem nem incluem chaves/checksums suficientes para provar que seus dados exclusivos estejam preservados. O serviço e o volume seguem intactos.

## Evidência atual importante

- Release pública `v0.1.0`: https://github.com/DIDIDXX/LeiAberta/releases/tag/v0.1.0.
- Cinco issues abertas e dez PRs de Dependabot foram preservados para colaboração e revisão individual; nenhum foi fechado/mesclado em massa.
- O site não apresenta cobertura nacional completa. A comparação arquivada do art. 389 continua com a ressalva explícita de que a transcrição do Normas.leg.br é classificada como valor jurídico não oficial.
- O backup diário de 2026-10-07 terminou com dump e manifesto lidos de volta, SHA-256 válidos e restore isolado `restore_verified=true`. A validação de conteúdo do Art. 389 será incluída na rodada pós-deploy da correção do runner.
- As faturas Railway não estão disponíveis pelas ferramentas conectadas; os custos registrados são estimativas calculadas com métricas de 24 h e tarifas públicas.
