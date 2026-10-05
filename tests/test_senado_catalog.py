from pathlib import Path

from app.catalog_sync.senado import parse_law_catalog, sync_law_catalog
from app.models import Law, SourceRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "official"


def _senado_list_record(*, remote_id="12345", year=2026, number="",
                        title="Decreto de 21/04/2026"):
    return (
        f"<Lista><documentos><documento id='{remote_id}'>"
        f"<anoassinatura>{year}</anoassinatura><numero>{number}</numero>"
        f"<normaNome>{title}</normaNome><ementa>Norma oficial de teste.</ementa>"
        f"<dataassinatura>21/04/{year}</dataassinatura><norma/>"
        f"</documento></documentos></Lista>"
    ).encode()


def test_senado_list_parser_preserves_official_identity_and_signature_date():
    body = (FIXTURES / "senado-list-lei14550-2023.xml").read_bytes()
    [record] = parse_law_catalog(body, minimum_records=1)
    assert record.remote_id == "36981001"
    assert record.number == "14.550"
    assert record.year == 2023
    assert record.signed_at.isoformat() == "2023-04-19"
    assert record.title == "Lei nº 14.550 de 19/04/2023"
    assert record.source_url.endswith("/legislacao/36981001")
    assert record.type_code == "LEI"
    assert record.law_type == "Lei"


def test_senado_catalog_deduplicates_exact_duplicate_rows_but_rejects_conflicts():
    import pytest

    record = _senado_list_record()
    body = b"<Lista><documentos>" + record.split(b"<documentos>", 1)[1].rsplit(b"</documentos>", 1)[0] * 2 + b"</documentos></Lista>"
    parsed = parse_law_catalog(body, type_code="DEC-sn", minimum_records=2)
    assert len(parsed) == 1

    conflict = body.replace(b"Norma oficial de teste.", b"Norma oficial conflitante.", 1)
    with pytest.raises(ValueError, match="metadados conflitantes"):
        parse_law_catalog(conflict, type_code="DEC-sn", minimum_records=2)


def test_senado_catalog_parses_other_normative_types_and_measure_sequences():
    lcp = parse_law_catalog((FIXTURES / "senado-list-lcp237-2026.xml").read_bytes(),
                            type_code="LCP", minimum_records=1)[0]
    emc = parse_law_catalog((FIXTURES / "senado-list-emc138-2025.xml").read_bytes(),
                            type_code="EMC", minimum_records=1)[0]
    mpv = parse_law_catalog((FIXTURES / "senado-list-mpv2206-2001.xml").read_bytes(),
                            type_code="MPV", minimum_records=1)
    assert (lcp.law_type, lcp.number, lcp.year) == ("Lei Complementar", "237", 2026)
    assert (emc.law_type, emc.number, emc.year) == ("Emenda Constitucional", "138", 2025)
    sequence = next(item for item in mpv if item.title.startswith("Medida Provisória nº 2.206-1"))
    assert sequence.number == "2.206-1"
    assert sequence.remote_id == "559113"


def test_senado_catalog_parses_additional_and_unnumbered_official_classes():
    [decree] = parse_law_catalog(
        _senado_list_record(), type_code="DEC-sn", minimum_records=1,
    )
    assert (decree.type_code, decree.law_type, decree.number, decree.year) == (
        "DEC-sn", "Decreto não Numerado", "s/n", 2026,
    )

    [delegated] = parse_law_catalog(
        _senado_list_record(remote_id="12346", year=1992, number="13",
                            title="Lei Delegada nº 13 de 27/08/1992"),
        type_code="LDL", minimum_records=1,
    )
    assert (delegated.law_type, delegated.number, delegated.year) == ("Lei Delegada", "13", 1992)


def test_senado_year_partition_parser_allows_empty_year_and_rejects_wrong_year():
    assert parse_law_catalog(
        b"<documentos />", type_code="DEC-n", minimum_records=0,
        expected_year=1800, allow_empty=True,
    ) == []

    import pytest

    with pytest.raises(ValueError, match="partição Senado de 2025 contém registro de 2026"):
        parse_law_catalog(
            _senado_list_record(), type_code="DEC-n", minimum_records=0,
            expected_year=2025, allow_empty=True,
        )


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


def test_senado_normative_catalog_uses_type_identity_without_colliding(db_session):
    [record] = parse_law_catalog((FIXTURES / "senado-list-lcp237-2026.xml").read_bytes(),
                                  type_code="LCP", minimum_records=1)
    result = sync_law_catalog(db_session, [record])
    assert result["added"] == 1
    law = db_session.query(Law).filter_by(external_source_id=record.remote_id).one()
    assert law.law_type == "Lei Complementar"
    assert law.number == "237"
    source = db_session.get(SourceRegistry, "federal:senado:lcp")
    assert source.scope["senate_type_code"] == "LCP"


def test_chunked_catalog_sync_keeps_interrupted_import_unfresh_until_final_chunk(db_session):
    records = [
        *parse_law_catalog((FIXTURES / "senado-list-lei13709-2018.xml").read_bytes(), minimum_records=1),
        *parse_law_catalog((FIXTURES / "senado-list-lei14550-2023.xml").read_bytes(), minimum_records=1),
    ]
    assert len(records) == 2
    sync_law_catalog(db_session, records[:1], type_code="LEI", total_records=2,
                     records_committed=1, final_chunk=False)
    source = db_session.get(SourceRegistry, "federal:senado:leis")
    assert source.status == "syncing"
    assert source.scope["records_committed"] == 1

    sync_law_catalog(db_session, records[1:], type_code="LEI", total_records=2,
                     records_committed=2, final_chunk=True)
    assert source.status == "enumerated"
    assert source.scope["records_committed"] == 2
