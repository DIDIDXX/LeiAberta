# API pública

Estado: beta de leitura. A API pode evoluir; endpoints de escrita/prepare são limitados e enfileiram jobs duráveis.

Base pública: `https://web-production-12e95.up.railway.app`. OpenAPI: `/openapi.json`.

## Exemplos

```bash
curl 'https://web-production-12e95.up.railway.app/api/search?q=LGDP'
curl 'https://web-production-12e95.up.railway.app/api/laws/13709-2018/history'
curl 'https://web-production-12e95.up.railway.app/api/laws/11340-2006/blame?limit=20&offset=0'
curl 'https://web-production-12e95.up.railway.app/api/laws/11340-2006/nodes/art%3A19.par%3A4/provenance'
```

## Endpoints principais

| Método | Endpoint | Uso |
| --- | --- | --- |
| GET | `/api/stats` | Métricas agregadas e contagens por catálogo |
| GET | `/api/search?q=...&limit=...` | Busca; limite de 30 |
| GET | `/api/laws` | Listagem; limite de 100 |
| GET | `/api/laws/{slug}` | Metadata, versão atual e elegibilidade de texto |
| GET | `/api/laws/{slug}/nodes?article=7` | Dispositivos estruturados |
| GET | `/api/laws/{slug}/history` | Diffs e relações oficiais, distinguidos por `kind` e `comparison_available` |
| GET | `/api/laws/{slug}/blame?limit=100&offset=0&node_id=...` | Lista em lote de dispositivos e ato associado quando há comparação verificada |
| GET | `/api/laws/{slug}/nodes/{node_id}/provenance` | Texto atual, alteração verificada mais recente e relações do dispositivo |
| GET | `/api/changes/{change_id}` | Antes/depois, marcadores e nível de evidência |
| GET | `/api/laws/{slug}/proceedings` | Dossiê processual, se consultado/disponível |
| GET | `/api/sources` | Estado, freshness, limites de consulta, contagens observadas e erros por fonte |
| GET | `/api/laws/{slug}/coverage` | Estado de cobertura de uma norma |
| GET | `/api/jurisdictions` | Diretório territorial, não equivalente à cobertura legislativa |

## Paginação e limites

`/api/laws/{slug}/blame` aceita `limit` de 1 a 500 e `offset` >= 0, retorna `count`, `has_more`, `limit` e `offset`. Busca aceita limite de 1 a 30. A lista de leis aceita limite de 1 a 100. `GET /api/sources` devolve registros configurados/encontrados; não significa que todos tenham adapter de catálogo.

Os GET de busca e detalhe usam budgets Redis por janela. Rotas de preparação POST têm budget de jobs e deduplicação própria. Durante indisponibilidade temporária do Redis, leituras continuam; limites de fila e dedupe independentes continuam ativos.

## Semântica jurídica

- `verified_primary`: há comparação de texto e o endereço do ato modificador usa domínio de fonte primária reconhecido.
- `verified_source`: há comparação registrada, mas o domínio não está classificado como fonte primária nessa regra de interface.
- `partial`: há referência/ato localizado sem comparação de texto suficiente.
- `not_identified`: as fontes consultadas não permitiram atribuir com segurança a origem do dispositivo. Não quer dizer que nunca houve alteração.
- Uma relação oficial sem before/after continua sendo relação, não diff.
- `last_checked_at` é a tentativa mais recente. `last_success_at` é a última enumeração concluída registrada; contagens delta podem estar ausentes em registros antigos até a próxima sincronização.
- `request_policy` expõe page size, byte cap, timeout e tentativas máximas onde o adapter define esses limites; um registro sem política publicada não tem adapter de catálogo ativo.
- `retrieved_at` é captura, não vigência. Autoria da proposição/emenda/relatoria não é autoria de cada linha do texto aprovado.

## Estados de dados e erros

Uma norma pode estar catalogada e ainda sem texto. `/api/laws/{slug}` informa `materializable`, `version` e job quando aplicável. 404 indica identidade não encontrada; 409 indica fluxo/fonte não compatível; 429 inclui `Retry-After`; 503 indica indisponibilidade de operação que registra job ou banco/schema.

## Cobertura

`indexed_laws` representa registros catalogados em fontes integradas. Não equivale à totalidade das leis brasileiras. `materialized_laws` e `structured_articles` são contagens distintas. A lista territorial do IBGE enumera jurisdições, mas não prova que seus diários ou portais legislativos estejam integrados.
