from datetime import datetime, timezone

from app.catalog_sync.ibge import _seed_sources, _uf
from app.models import Jurisdiction, SourceRegistry


def test_ibge_municipality_uf_resolves_nested_current_payload():
    assert _uf({"regiao-imediata": {"regiao-intermediaria": {"UF": {"sigla": "SP"}}}}) == "SP"


def test_ibge_state_payload_returns_its_own_uf():
    assert _uf({"id": 35, "sigla": "SP"}) == "SP"


def test_ibge_missing_uf_is_not_guessed():
    assert _uf({"id": 9999999, "nome": "Desconhecida"}) is None


def test_ibge_source_seeding_preserves_catalog_sync_coverage(db_session):
    db_session.add_all([
        Jurisdiction(id="state:SP", kind="state", name="São Paulo", uf="SP", source_url="https://example.gov/sp"),
        Jurisdiction(id="state:DF", kind="state", name="Distrito Federal", uf="DF", source_url="https://example.gov/df"),
    ])
    checked = datetime(2026, 1, 2, tzinfo=timezone.utc)
    registry = SourceRegistry(
        id="state:DF:sinj", jurisdiction_id="state:DF", name="SINJ-DF", adapter="sinj_df_catalog",
        base_url="https://www.sinj.df.gov.br/sinj/ashx/Datatable/ResultadoDePesquisaNormaDatatable.ashx",
        evidence_url="https://www.sinj.df.gov.br/sinj/ResultadoDePesquisa?tipo_pesquisa=norma",
        status="enumerated", scope={"records_enumerated": 125478}, last_checked_at=checked,
    )
    db_session.add(registry)
    db_session.commit()

    _seed_sources(db_session, datetime(2026, 10, 4, tzinfo=timezone.utc))

    db_session.expire_all()
    preserved = db_session.get(SourceRegistry, "state:DF:sinj")
    assert preserved.status == "enumerated"
    assert preserved.scope == {"records_enumerated": 125478}
    assert preserved.adapter == "sinj_df_catalog"
    assert preserved.name == "SINJ-DF"
    assert preserved.last_checked_at.replace(tzinfo=timezone.utc) == checked
