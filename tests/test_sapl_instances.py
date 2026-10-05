from datetime import date, datetime, timezone

from app.catalog_sync.sapl import SAPL_INSTANCES, parse_catalog_page, sync_catalog_page
from app.models import Jurisdiction, Law
from app.sources import sapl


ANAPOLIS = next(item for item in SAPL_INSTANCES if item.ibge_code == "5201108")
CAMPINA_GRANDE = next(item for item in SAPL_INSTANCES if item.ibge_code == "2504009")


def test_verified_installations_parse_their_own_urls_and_ids():
    payload = {"results": [{
        "id": 8223, "__str__": "Decreto nº 1.232, de 16 de setembro de 2026", "tipo": 5,
        "texto_integral": "http://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2026/8223/decreto.pdf",
        "numero": "1232", "ano": 2026, "esfera_federacao": "M", "data": "2026-09-16",
        "data_publicacao": None, "ementa": "Decreto municipal.",
    }]}
    [item] = parse_catalog_page(payload, {"5": "Decreto"}, instance=ANAPOLIS)

    assert item.source_url == "https://sapl.anapolis.go.leg.br/api/norma/normajuridica/8223/"
    assert item.text_url == "https://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2026/8223/decreto.pdf"
    assert (item.law_type, item.number, item.year, item.signed_at) == (
        "Decreto", "1232", 2026, date(2026, 9, 16),
    )


def test_new_official_sapl_municipalities_have_stable_ibge_and_source_identity():
    by_code = {item.ibge_code: item for item in SAPL_INSTANCES}
    expected = {
        "3170404": ("Unaí", "MG", "https://sapl.unai.mg.leg.br"),
        "3549102": ("São João da Boa Vista", "SP", "https://sapl.saojoaodaboavista.sp.leg.br"),
        "2408102": ("Natal", "RN", "https://sapl.natal.rn.leg.br"),
    }
    for code, identity in expected.items():
        item = by_code[code]
        assert (item.municipality, item.state_code, item.host) == identity
        assert item.source_id == f"municipality:{code}:sapl"
        assert item.authority_url.startswith("https://")


def test_verified_installation_sync_keeps_catalog_rows_separate_by_municipality(db_session):
    db_session.add_all([
        Jurisdiction(id="state:GO", kind="state", name="Goiás", uf="GO", source_url="https://go.gov.br/"),
        Jurisdiction(id=ANAPOLIS.jurisdiction_id, kind="municipality", name="Anápolis",
                     ibge_code=ANAPOLIS.ibge_code, uf="GO", parent_id="state:GO",
                     source_url=ANAPOLIS.authority_url),
    ])
    db_session.commit()
    [item] = parse_catalog_page({"results": [{
        "id": 8223, "__str__": "Decreto nº 1.232, de 16 de setembro de 2026", "tipo": 5,
        "texto_integral": "https://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2026/8223/decreto.pdf",
        "numero": "1232", "ano": 2026, "esfera_federacao": "M", "data": "2026-09-16",
        "data_publicacao": None, "ementa": "Decreto municipal.",
    }]}, {"5": "Decreto"}, instance=ANAPOLIS)

    result = sync_catalog_page(db_session, [item], observed_at=datetime.now(timezone.utc), instance=ANAPOLIS)
    db_session.commit()
    law = db_session.get(Law, "sapl-5201108-8223")
    assert result == {"added": 1, "refreshed": 0}
    assert law.external_source_id == "sapl:5201108:8223"
    assert (law.state_code, law.municipality, law.source_name) == (
        "GO", "Anápolis", "Câmara Municipal de Anápolis — SAPL",
    )


def test_media_urls_are_canonicalized_only_within_the_configured_sapl_instance():
    raw = "http://sapl.anapolis.go.leg.br/sapl_documentos/norma_juridica/6034_texto_integral"
    assert sapl._validated_media_url(raw, instance=ANAPOLIS) == raw.replace("http://", "https://")
    assert sapl._validated_media_url(
        "/media/sapl/public/normajuridica/2026/1000799/res_107_2026.pdf", instance=CAMPINA_GRANDE,
    ) == "https://sapl.campinagrande.pb.leg.br/media/sapl/public/normajuridica/2026/1000799/res_107_2026.pdf"
    assert sapl._validated_media_url(
        "media/sapl/public/normajuridica/2026/1000799/res_107_2026.pdf", instance=CAMPINA_GRANDE,
    ) == "https://sapl.campinagrande.pb.leg.br/media/sapl/public/normajuridica/2026/1000799/res_107_2026.pdf"


def test_sapl_text_identity_check_accepts_ocr_without_portuguese_diacritics():
    body = ("<html><body><p>RESOLUCAO N. 107/2026</p>"
            "<p>Define data da eleicao da Mesa Diretora da Camara Municipal. "
            "Art. 1. Norma aprovada em sessao realizada pela Casa Legislativa.</p></body></html>").encode()
    sapl._validate_document_text(body, "RESOLUÇÃO", "107", 2026)


def test_sapl_history_uses_the_matching_municipal_api_host(monkeypatch):
    monkeypatch.setattr(sapl, "_verified_detail", lambda *_args, **_kwargs: ("1000799", {}))
    monkeypatch.setattr(sapl, "_paged_relations", lambda *_args, **_kwargs: [])
    snapshot = sapl.fetch_sapl_history(
        "https://sapl.campinagrande.pb.leg.br/api/norma/normajuridica/1000799/",
        "RESOLUÇÃO", "107", 2026,
    )
    assert "sapl.campinagrande.pb.leg.br" in snapshot.source_url
    assert b"sapl.campinagrande.pb.leg.br" in snapshot.body
