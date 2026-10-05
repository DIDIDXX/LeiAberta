# Social copy — pronto para revisão, não publicado

## LinkedIn (PT-BR)

Passei os últimos dias transformando o LeiAberta em uma espécie de Git blame para legislação brasileira.

O ponto difícil não é baixar o texto de uma lei. É provar que um dispositivo mudou, ligar a mudança ao ato correto e deixar a fonte oficial a um clique — sem confundir processo legislativo com diff, nem atribuir uma linha a uma pessoa sem evidência.

Na demo, o § 4º do art. 19 da Lei Maria da Penha é ligado à Lei 14.550/2023 e ao texto publicado no Planalto. O histórico completo da lei continua parcial; a interface mostra essa limitação.

O acervo observado tinha cerca de 1,33 milhão de registros catalogados, 25,9 mil normas com texto materializado e 537 alterações documentadas. São números dinâmicos das fontes integradas, não “todas as leis do Brasil”.

Demo: https://web-production-12e95.up.railway.app
GitHub: https://github.com/DIDIDXX/LeiAberta

O projeto é open source (MIT). Contribuições de adapters, fixtures e revisão de cobertura são bem-vindas.

## X — post curto

Eu queria um git blame para leis brasileiras. Então comecei a construir um.

O desafio é provar quando um dispositivo mudou e mostrar a fonte oficial — sem confundir relação legislativa com diff nem inventar autoria.

Demo real: Lei Maria da Penha → Lei 14.550/2023 → Planalto.
https://web-production-12e95.up.railway.app

## X — thread

1/ Eu queria um Git blame para leis brasileiras. Então comecei a construir um: LeiAberta.
2/ A parte difícil não é baixar HTML. É saber se a fonte oficial permite afirmar que um dispositivo realmente mudou.
3/ Relação oficial não é diff. Data de captura não é vigência. Autor de projeto não é autor de cada linha aprovada.
4/ A demo segue a inclusão do art. 19, § 4º, da Lei Maria da Penha pela Lei 14.550/2023 até as publicações do Planalto.
5/ O histórico geral continua parcial. A interface deixa isso visível em vez de preencher a lacuna com uma conclusão.
6/ O pipeline combina catálogos incrementais, PostgreSQL, Redis Streams, worker, snapshots com SHA-256 e dispositivos estruturados.
7/ O catálogo medido tem mais de 1,3 milhão de registros nas fontes integradas. Isso não significa cobertura de todas as leis brasileiras.
8/ É open source MIT. Demo: https://web-production-12e95.up.railway.app · Código: https://github.com/DIDIDXX/LeiAberta

## Comunidades dev (PT-BR)

Estou trabalhando no LeiAberta, um catálogo open source que tenta resolver uma pergunta específica: qual ato oficial sustenta a redação atual de um dispositivo? A primeira demo acompanha uma inclusão na Lei Maria da Penha até o Planalto. O histórico geral ainda é parcial, e essa distinção está no produto. Busco contribuições de fontes oficiais, fixtures e parsers: https://github.com/DIDIDXX/LeiAberta

## Developer communities (EN)

I’m building LeiAberta, an open source project that links Brazilian legal provisions to verified amendments and official sources. The demo traces a real addition in the Maria da Penha Law to the official publication. The broader history is still partial, and the UI says so. Contributions for official source adapters and parser fixtures are welcome: https://github.com/DIDIDXX/LeiAberta

