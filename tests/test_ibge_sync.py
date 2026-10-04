from app.catalog_sync.ibge import _uf


def test_ibge_municipality_uf_resolves_nested_current_payload():
    assert _uf({"regiao-imediata": {"regiao-intermediaria": {"UF": {"sigla": "SP"}}}}) == "SP"


def test_ibge_state_payload_returns_its_own_uf():
    assert _uf({"id": 35, "sigla": "SP"}) == "SP"


def test_ibge_missing_uf_is_not_guessed():
    assert _uf({"id": 9999999, "nome": "Desconhecida"}) is None
