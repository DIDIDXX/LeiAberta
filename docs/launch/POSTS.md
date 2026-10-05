# Social copy — pronto para revisão, não publicado

## LinkedIn (PT-BR)

Passei os últimos dias transformando o LeiAberta em uma espécie de Git blame para legislação brasileira.

O ponto difícil não é baixar o texto de uma lei. É provar que um dispositivo mudou, ligar a mudança ao ato correto e deixar a fonte oficial a um clique — sem confundir processo legislativo com diff, nem atribuir uma linha a uma pessoa sem evidência.

Na demo principal, o art. 389 do Código Civil mostra as redações anterior e posterior associadas à Lei 14.905/2024. A comparação vem de uma versão do Normas.leg.br, que classifica a transcrição como valor jurídico não oficial; o LeiAberta explicita essa ressalva e não apresenta a data registrada como vigência. O texto consolidado consultado também fica ligado na tela.

O acervo observado tinha cerca de 1,36 milhão de registros catalogados, 26,2 mil normas com texto materializado e 537 alterações documentadas. São números dinâmicos das fontes integradas, não “todas as leis do Brasil”.

Demo: https://web-production-12e95.up.railway.app
GitHub: https://github.com/DIDIDXX/LeiAberta

O projeto é open source (MIT). Contribuições de adapters, fixtures e revisão de cobertura são bem-vindas.

## X — post curto

Eu queria um git blame para leis brasileiras. Então comecei a construir um.

O desafio é provar quando um dispositivo mudou e mostrar a fonte oficial — sem confundir relação legislativa com diff nem inventar autoria.

Demo real com antes e depois: art. 389 do Código Civil → Lei 14.905/2024 → versão comparada no Normas.leg.br. A transcrição histórica é identificada como não oficial.
https://web-production-12e95.up.railway.app

## X — thread

1/ Eu queria um Git blame para leis brasileiras. Então comecei a construir um: LeiAberta.
2/ A parte difícil não é baixar HTML. É saber se a fonte oficial permite afirmar que um dispositivo realmente mudou.
3/ Relação oficial não é diff. Data de captura não é vigência. Autor de projeto não é autor de cada linha aprovada.
4/ A demo mostra o art. 389 do Código Civil antes e depois da alteração associada à Lei 14.905/2024. O registro histórico do Normas.leg.br aparece classificado como valor jurídico não oficial.
5/ O histórico geral continua parcial. A interface deixa isso visível em vez de preencher a lacuna com uma conclusão.
6/ O pipeline combina catálogos incrementais, PostgreSQL, Redis Streams, worker, snapshots com SHA-256 e dispositivos estruturados.
7/ O catálogo medido tem mais de 1,3 milhão de registros nas fontes integradas. Isso não significa cobertura de todas as leis brasileiras.
8/ É open source MIT. Demo: https://web-production-12e95.up.railway.app · Código: https://github.com/DIDIDXX/LeiAberta

## Comunidades dev (PT-BR)

Estou trabalhando no LeiAberta, um catálogo open source que tenta responder como a redação de um dispositivo mudou e qual fonte sustenta a comparação. A demo mostra antes/depois do art. 389 do Código Civil; a versão do Normas.leg.br é identificada como transcrição de valor jurídico não oficial. O histórico geral continua parcial. Busco contribuições de fontes oficiais, fixtures e parsers: https://github.com/DIDIDXX/LeiAberta

## Developer communities (EN)

I’m building LeiAberta, an open source project that links Brazilian legal provisions to amendment evidence. The demo shows the before and after text recorded for Article 389 of Brazil’s Civil Code. Its historical transcription comes from Normas.leg.br and is clearly labeled as non-official legal text; the consolidated text source is linked separately. Broader legal history remains partial. Contributions for source adapters and parser fixtures are welcome: https://github.com/DIDIDXX/LeiAberta
