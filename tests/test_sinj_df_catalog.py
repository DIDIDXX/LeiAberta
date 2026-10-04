from datetime import datetime, timezone

from app.catalog_sync.sinj_df import parse_catalog_page, sync_catalog_page
from app.models import Jurisdiction, Law


def _payload(number="6139"):
    return {
        "offset": "0", "iTotalDisplayRecords": "1",
        "aaData": [{
            "_id": "93048",
            "_source": {
                "ch_norma": "4b03e650ad54469a8802d8dcf24ccd11",
                "nr_norma": number, "nr_sequencial": 0,
                "dt_assinatura": "03/05/2018", "ds_ementa": "Ementa oficial.",
                "nm_tipo_norma": "Lei", "nm_situacao": "Sem Revogação Expressa",
                "fontes": [{"dt_publicacao": "03/05/2018", "ar_fonte": {"mimetype": "text/html"}}],
            },
        }],
    }


def test_sinj_catalog_parser_captures_official_identity_and_text_availability():
    [record] = parse_catalog_page(_payload())
    assert (record.remote_id, record.document_id, record.law_type, record.number, record.year) == (
        "4b03e650ad54469a8802d8dcf24ccd11", "93048", "Lei", "6139", 2018,
    )
    assert record.source_url.endswith("DetalhesDeNorma.aspx?id_doc=93048")
    assert record.text_attachment_types == ("text/html",)
    assert record.published_at.isoformat() == "2018-05-03"


def test_sinj_catalog_preserves_numberless_norms_as_s_n():
    [record] = parse_catalog_page(_payload(number=""))
    assert record.number == "s/n"
    assert record.title == "Lei s/n de 03/05/2018"


def test_sinj_catalog_counts_updated_text_attachment_when_no_publication_file():
    payload = _payload()
    source = payload["aaData"][0]["_source"]
    source["fontes"] = []
    source["ar_atualizado"] = {"id_file": "current-file", "mimetype": "text/html"}
    [record] = parse_catalog_page(payload)
    assert record.text_attachment_types == ("text/html",)


def test_sinj_catalog_page_sync_is_idempotent_and_scoped_to_df(db_session):
    db_session.add(Jurisdiction(id="state:DF", kind="state", name="Distrito Federal", uf="DF",
                                legislature_eligible=True, territorial_status="active",
                                source_url="https://servicodados.ibge.gov.br/api/v1/localidades/estados"))
    db_session.commit()
    [record] = parse_catalog_page(_payload())
    now = datetime.now(timezone.utc)
    first = sync_catalog_page(db_session, [record], observed_at=now)
    db_session.commit()
    second = sync_catalog_page(db_session, [record], observed_at=now)
    law = db_session.get(Law, "df-sinj-4b03e650ad54469a8802d8dcf24ccd11")
    assert first == {"added": 1, "refreshed": 0}
    assert second == {"added": 0, "refreshed": 1}
    assert (law.jurisdiction, law.state_code, law.municipality) == ("state", "DF", None)
    assert law.external_source_id == "sinj:4b03e650ad54469a8802d8dcf24ccd11"
    assert law.materialization_status == "catalog"
