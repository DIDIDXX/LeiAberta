# Ações manuais pendentes

Este arquivo substitui a fotografia desatualizada do início do incidente. O retrato medido em 06/10/2026 mostra `web`, `/ready` e o worker respondendo; confirme novamente após cada deploy.

## Antes de anunciar lançamento público

- Revalidar produção depois do deploy final: caveat do Why/Blame, rotas/APIs, sincronização incremental limitada e uma hidratação sob demanda concluída pelo worker real.
- Conferir os resultados completos da auditoria SHA dos 14.201 objetos do bucket e do backup/restore com a nova verificação de schema.
- Observar ao menos 30–60 minutos sob sync representativo, registrar crescimento do volume, e manter a janela de 24 horas antes de encerrar o fallback.
- Definir e comprovar retenção, versionamento ou cópia recuperável dos snapshots no bucket antes de qualquer `raw_body = NULL`.
- Verificar a fatura Railway real quando o mantenedor tiver acesso. A estimativa atual é aproximadamente US$ 40,20–40,70/mês com o banco antigo e US$ 32,90–33,40/mês depois de uma eventual aposentadoria; a meta aspiracional US$ 10–15/mês ainda não foi atingida.

## Aprovação explícita necessária

O Postgres antigo continua conectado ao volume de 5 GB, quase cheio em 4,9965 GB, e seus logs registram `No space left on device`. Ele está preservado para inspeção, mas não é um fallback confiável no estado atual.

Após os gates de backup, restore, estabilidade e observação, o proprietário deve decidir se autoriza excluir o serviço **Postgres** antigo e seu volume `postgres-volume` no Railway. A autorização para esta execução não inclui essa exclusão; nenhum serviço ou volume antigo foi apagado. Se aprovado, revise as mudanças pendentes do Railway e confirme que removem apenas o serviço/volume antigos esperados. Não inclua outros recursos na mesma aplicação.

## Limites desta etapa

- Não comprar domínio, migrar para VPS, fazer upgrade pago nem publicar posts em redes sociais.
- A comparação arquivada do Art. 389 continua baseada em transcrição do Normas.leg.br classificada como não oficial. Os trechos exatos anterior e posterior ainda não foram comprovados em documentos primários armazenados.
- A integração GitHub havia recusado com 403 a edição de descrição/homepage/topics. Se ainda desejar esses metadados, o mantenedor pode atualizá-los nas configurações do repositório; isso não bloqueia o funcionamento da aplicação.
