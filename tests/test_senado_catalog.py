from pathlib import Path

from app.catalog_sync.senado import parse_law_catalog, sync_law_catalog
from app.models import Law, SourceRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "official"


def test_senado_list_parser_preserves_official_identity_and_signature_date():
    body = (FIXTURES / "senado-list-lei14550-2023.xml").read_bytes()
    [record] = parse_law_catalog(body, minimum_records=1)
    assert record.remote_id == "36981001"
    assert record.number == "14.550"
    assert record.year == 2023
    assert record.signed_at.isoformat() == "2023-04-19"
    assert record.title == "Lei nº 14.550 de 19/04/2023"
    assert record.source_url.endswith("/legislacao/36981001")


def test_senado_catalog_attaches_seed_and_inserts_new_record_idempotently(db_session, add_law):
    seeded = add_law(slug="14550-2023", number="14.550", year=2023)
    db_session.add(seeded)
    db_session.commit()
    lmp = parse_law_catalog((FIXTURES / "senado-list-lei14550-2023.xml").read_bytes(), minimum_records=1)
    lgpd = parse_law_catalog((FIXTURES / "senado-list-lei13709-2018.xml").read_bytes(), minimum_records=1)

    first = sync_law_catalog(db_session, [*lmp, *lgpd])
    assert first["attached_to_seed"] == 1
    assert first["added"] == 1
    seeded = db_session.get(Law, "14550-2023")
    assert seeded.external_source_id == "36981001"
    assert seeded.signed_at.isoformat() == "2023-04-19"
    assert seeded.published_at is None
    assert seeded.source_url.startswith("https://www.planalto.gov.br/")
    imported = db_session.query(Law).filter_by(external_source_id=lgpd[0].remote_id).one()
    assert imported.source_name == "Senado Federal — Dados Abertos Legislativos"
    assert imported.materialization_status == "catalog"
    assert imported.published_at is None
    source = db_session.get(SourceRegistry, "federal:senado:leis")
    assert source.status == "enumerated"
    assert source.scope["records_enumerated"] == 2

    second = sync_law_catalog(db_session, [*lmp, *lgpd])
    assert second["added"] == 0
    assert second["refreshed"] == 2
    assert db_session.query(Law).filter_by(external_source_id=lgpd[0].remote_id).count() == 1
