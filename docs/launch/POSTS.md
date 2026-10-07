# Posts para revisão — não publicados

## LinkedIn (PT-BR)

**Entenda como uma lei chegou ao texto atual.**

Foi com essa pergunta que comecei a construir o LeiAberta. O texto consolidado de uma lei é fácil de encontrar; reconstruir por que um dispositivo mudou, qual ato está relacionado à mudança e que evidência sustenta essa comparação é bem mais difícil.

O LeiAberta reúne catálogos de fontes legislativas integradas, textos disponíveis, histórico e comparações quando há evidência suficiente. Na demonstração, o art. 389 do Código Civil permite navegar entre a redação atual, uma comparação associada à Lei 14.905/2024 e a proveniência registrada. A transcrição histórica usada nessa comparação vem do Normas.leg.br, que a classifica como valor jurídico não oficial. A interface deixa essa ressalva explícita e não trata a data registrada como prova de vigência.

O projeto usa Python, FastAPI, PostgreSQL, Redis Streams, workers assíncronos e armazenamento S3 compatível para snapshots com verificação SHA-256. Ingestão, deduplicação e proveniência são parte central do trabalho: uma relação legislativa, sozinha, não prova que cada trecho foi alterado.

A cobertura é parcial e varia por fonte. O LeiAberta não promete reunir toda a legislação brasileira nem inventa históricos quando faltam documentos comparáveis.

Quero que mais pessoas testem, apontem problemas e contribuam com adaptadores de fontes, parsers, evidências e documentação. Abra uma issue ou envie uma contribuição:

- Demo: https://web-production-12e95.up.railway.app
- Código e documentação: https://github.com/DIDIDXX/LeiAberta
- Release: https://github.com/DIDIDXX/LeiAberta/releases/tag/v0.1.0

## X — post único (267 caracteres com URLs contadas como 23 caracteres)

Como um artigo de lei mudou — e qual ato prova isso?

LeiAberta liga texto, histórico e fontes; no art. 389, identifica a transcrição histórica como não oficial. Cobertura parcial, sem inventar histórico.

Demo: https://web-production-12e95.up.railway.app
Código: https://github.com/DIDIDXX/LeiAberta

## X — thread curta (opcional)

1/ Entenda como uma lei chegou ao texto atual. Essa pergunta virou o LeiAberta.

2/ O desafio não é só baixar o texto. É ligar uma alteração ao ato certo e mostrar a evidência sem confundir relação legislativa com comparação de redações.

3/ Na demo, o art. 389 do Código Civil tem uma comparação associada à Lei 14.905/2024. A transcrição histórica do Normas.leg.br é identificada como valor jurídico não oficial; a data registrada não é apresentada como vigência.

4/ Catálogos e textos estão disponíveis para um conjunto parcial de fontes integradas. Quando a evidência não sustenta uma conclusão, o projeto mostra a lacuna.

5/ Python, FastAPI, PostgreSQL, Redis Streams, workers e snapshots S3 compatíveis com SHA-256. Teste, abra uma issue ou contribua: https://web-production-12e95.up.railway.app · https://github.com/DIDIDXX/LeiAberta
