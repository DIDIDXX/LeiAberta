# Ações manuais para o lançamento

**Estado:** 7 de outubro de 2026. A produção está no SHA `73a2216b47d1e077777902f45197c8f2b5feccb8`; o produto passou os smokes e o teste visual descritos no relatório final. 

## Configuração pública do repositório

1. **Completar o About do GitHub.** A página pública ainda mostra “No description, website, or topics provided”. A sessão conectada está deslogada e a credencial local do `gh` é inválida. Desbloqueie o Mac e autentique GitHub no navegador; então salve e confirme visualmente estes valores:
   - Description: `Open-source platform for exploring Brazilian legislation, verified amendments and legal provenance.`
   - Website: `https://web-production-12e95.up.railway.app`
   - Topics: `brazil`, `legislation`, `civic-tech`, `open-data`, `legaltech`, `data-engineering`, `fastapi`, `postgresql`, `open-source`

Depois de salvar o About, não resta etapa técnica de lançamento indicada por esta execução. A decisão atual é **NO-GO estrito até a confirmação visual do About**.

## Recursos preservados

O serviço antigo `Postgres` e o volume `postgres-volume` permanecem ativos. Web, worker e backup apontam para `postgres-blue`; nenhum TCP proxy está configurado. O volume antigo segue em `4.9965/5 GB`, e o banco ficou indisponível para comparação íntegra após um erro de disco. Como manifests históricos não provam que todos os dados jurídicos únicos foram copiados, o banco foi preservado. Isso não bloqueia o produto, e não deve ser excluído até que a prova de unicidade esteja disponível.

O custo estimado do ambiente atual é aproximadamente US$ 29.99/mês mais egress; sem o banco antigo seria aproximadamente US$ 20.18/mês mais egress, usando as tarifas documentadas e sem acesso a invoice real. Nenhum upgrade ou serviço pago foi contratado.
