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

## Situação de fechamento 2026-10-07 15:09 UTC

- A execução do runner de backup novo foi iniciada pelo agendador em uma cadência temporária de verificação e terminou com dump/manifest verificados e restore isolado. Cron live voltou a 03:00 UTC; a próxima execução diária normal deve ser observada antes de anunciar backup automático validado para o calendário diário.
- A hidratação interativa já rodou em worker real para uma norma fria. A fonte SAPL de Manaus excedeu o timeout após cinco tentativas; o produto não obteve texto estruturado. Foi identificado e corrigido localmente o bug que enfileirava nova tentativa em toda leitura da página durante cooldown. A correção ainda precisa passar CI, deploy e smoke de produção, portanto **não publicar antes de receber confirmação do coordenador de que o deploy e o soak passaram**.
- Mesmo que o app fique saudável, a retirada do Postgres antigo continua bloqueada por falta de prova de que seus dados jurídicos exclusivos foram preservados. Ele segue conectado a um volume quase cheio; não apagar via dashboard. O custo estimado cai cerca de US$9.81/mês quando for seguro e autorizado, mas os dados atuais não satisfazem o gate.
- Sessão do GitHub não autenticada impede salvar About daqui. Essa é a ação manual concreta de configuração indicada no item 1; não é preciso mexer nos issues/Dependabot.
- Os textos e mídias estão prontos em `POSTS.md` e `MEDIA.md`; permanecem não publicados. A publicação deve ocorrer somente depois de a decisão atualizada mudar de NO-GO para GO.
- O patch local de retry do worker/UI e as três capturas estão no branch `codex/launch-hydration-cooldown-20261007`, mas ainda não foram publicados no GitHub: o conector falhou em chamadas de escrita, HTTPS push não tem credencial, SSH não tem public key e a aba autenticada não está logada. Se a integração continuar indisponível, a única ação humana necessária para destravar o restante é desbloquear o Mac e autenticar GitHub na sessão; depois o branch pode ser enviado para CI, PR revisado e deploy/soak feitos pelo coordenador.
