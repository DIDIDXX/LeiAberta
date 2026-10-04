import json
from pathlib import Path

from app.catalog_sync.alesp import parse_catalog_page, sync_catalog_page
from app.models import Jurisdiction, Law


FIXTURES = Path(__file__).parent / "fixtures" / "official"


def test_alesp_page_parser_preserves_type_number_dates_and_official_text_url():
    payload = {
        "number": 0,
        "size": 2,
        "content": [
            {"idNorma": "213020", "tipo": "Decreto", "nuNorma": "70916", "data": "02/10/2026",
             "dataPublicacao": "02/10/2026", "nomeNorma": "Decreto nº 70.916, de 02/10/2026",
             "idTipo": "3", "dsEmenta": "Ementa do decreto.",
             "urlIntegraListaPesquisa": "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2026/a.html"},
            {"idNorma": "140825", "tipo": "Resolução", "nuNorma": "57", "data": "05/04/1870",
             "dataPublicacao": None, "nomeNorma": "Resolução nº 57, de 05/04/1870",
             "idTipo": "14", "dsEmenta": "Ementa histórica.", "urlIntegraListaPesquisa": None},
        ],
    }

    records = parse_catalog_page(payload)

    assert [(item.remote_id, item.law_type, item.number, item.year) for item in records] == [
        ("213020", "Decreto", "70.916", 2026), ("140825", "Resolução", "57", 1870),
    ]
    assert records[0].published_at.isoformat() == "2026-10-02"
    assert records[0].source_url.endswith("/norma/213020")
    assert records[0].text_url.endswith("/repositorio/legislacao/decreto/2026/a.html")
    assert records[1].published_at is None
    assert records[1].text_url is None


def test_alesp_catalog_page_sync_is_idempotent_and_scoped_to_sp(db_session):
    db_session.add(Jurisdiction(id="state:SP", kind="state", name="São Paulo", uf="SP",
                                legislature_eligible=True, territorial_status="active",
                                source_url="https://servicodados.ibge.gov.br/api/v1/localidades/estados"))
    db_session.commit()
    payload = {
        "number": 0, "size": 1,
        "content": [{"idNorma": "213020", "tipo": "Decreto", "nuNorma": "70916", "data": "02/10/2026",
                     "dataPublicacao": "02/10/2026", "nomeNorma": "Decreto nº 70.916, de 02/10/2026",
                     "idTipo": "3", "dsEmenta": "Ementa.",
                     "urlIntegraListaPesquisa": "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2026/a.html"}],
    }
    [record] = parse_catalog_page(payload)
    from datetime import datetime, timezone

    first = sync_catalog_page(db_session, [record], observed_at=datetime.now(timezone.utc))
    db_session.commit()
    second = sync_catalog_page(db_session, [record], observed_at=datetime.now(timezone.utc))

    law = db_session.get(Law, "sp-alesp-213020")
    assert first == {"added": 1, "refreshed": 0}
    assert second == {"added": 0, "refreshed": 1}
    assert law.external_source_id == "alesp:213020"
    assert (law.jurisdiction, law.state_code, law.municipality) == ("state", "SP", None)
    assert law.source_name == "Assembleia Legislativa do Estado de São Paulo — ALESP"
    assert law.materialization_status == "catalog"
