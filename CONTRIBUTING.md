# Contribuindo

Obrigado por ajudar a tornar a legislação verificável. Preserve a distinção entre catálogo, texto capturado, estrutura interpretada, relação oficial e diff validado.

## Ambiente e testes

Use Python 3.12+, PostgreSQL/SQLite local e, para o worker distribuído, Redis. Siga a seção “Rodar localmente” do README. Instale os navegadores Playwright com `npx playwright install chromium` depois de `npm ci`.

Antes de abrir PR:

```bash
pytest -q
npm ci
npm run test:e2e
git diff --check
```

Não rode sincronização ou backfill contra produção para validar código. Use fixtures oficiais arquivadas, banco isolado e respostas mockadas. Uma migration deve ser aditiva, testada em PostgreSQL isolado e acompanhada de impacto de lock/disk e rollback.

## Adaptadores e dados jurídicos

- Use fonte oficial e documente URL, órgão, identificador remoto, data consultada e limitações.
- Verifique que a identidade normativa retornada corresponde ao pedido. Uma URL ou título parecido não comprova identidade.
- Preserve respostas brutas/checksum e versão do parser quando possível.
- Não invente redação, vigência, autoria, votação, histórico ou equivalência. Se a fonte não permite verificar, use estado explícito de lacuna.
- Adicione fixture pequena e autorizada para resposta normal, erro, redirect e corpo inválido/grande.
- Respeite limites e termos do órgão de origem; inclua timeout, retry limitado, byte cap e concorrência por domínio.
- IDs de dispositivos devem ser estáveis e explicados. Mudanças de parsing precisam testar normas com artigos repetidos, parágrafos, incisos, vetos e redação revogada.

## Pull requests

PRs devem dizer: objetivo, arquivos/camada, evidência/fonte, migration/impacto em dados, testes executados, observabilidade e rollback. Mudanças de dado jurídico devem incluir URLs oficiais e explicar o que está comprovado e o que permanece parcial. Não incluir secrets, dumps de produção ou dados pessoais em commits/fixtures.

Issues e PRs usam os templates em `.github/`. Mudanças grandes de arquitetura devem incluir uma ADR curta em `docs/audits/`.
