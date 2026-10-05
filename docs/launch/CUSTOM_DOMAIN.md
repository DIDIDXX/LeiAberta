# Domínio próprio

Produção continua em https://web-production-12e95.up.railway.app; domínio próprio não é necessário para o launch.

Se o mantenedor registrar `leiaberta.org`:

1. No Railway, abra o serviço `web` em produção e adicione o domínio `leiaberta.org` e, opcionalmente, `www.leiaberta.org`.
2. Copie os registros DNS exibidos pelo Railway no provedor do domínio. Não reutilize IP/alvo de exemplo.
3. Aguarde propagação e certificado TLS ficar ativo; valide redirects HTTPS, `/health`, `/ready` e `/sitemap.xml`.
4. Configure `PUBLIC_BASE_URL=https://leiaberta.org` no serviço web e valide canonical, sitemap, OpenGraph e URLs da API.
5. Remova o domínio antigo somente depois de verificar domínio/TLS e links compartilhados.

