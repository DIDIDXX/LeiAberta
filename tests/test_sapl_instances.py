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


def test_sapl_preserves_declared_scope_and_allows_legacy_missing_scope():
    legacy = {"results": [{
        "id": 6156, "__str__": "Lei Complementar nº 379, de 21 de junho de 2018", "tipo": 2,
        "texto_integral": "http://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2018/6156/6156_texto_integral.pdf",
        "numero": "379", "ano": 2018, "esfera_federacao": "", "data": "2018-06-21",
        "ementa": "Altera norma municipal.",
    }]}
    [item] = parse_catalog_page(legacy, {"2": "Lei Complementar"}, instance=ANAPOLIS)
    assert item.remote_id == "6156"
    assert item.federation_scope == ""

    state_rows = {"results": [{**legacy["results"][0], "id": 1449, "esfera_federacao": "E"}]}
    [state_law] = parse_catalog_page(state_rows, {"2": "Lei Complementar"}, instance=ANAPOLIS)
    assert state_law.federation_scope == "E"

    federal_rows = {"results": [{**legacy["results"][0], "id": 1448, "esfera_federacao": "F"}]}
    [federal_law] = parse_catalog_page(federal_rows, {"2": "Lei Complementar"}, instance=ANAPOLIS)
    assert federal_law.federation_scope == "F"

    invalid_scope = {"results": [{**legacy["results"][0], "esfera_federacao": "X"}]}
    try:
        parse_catalog_page(invalid_scope, {"2": "Lei Complementar"}, instance=ANAPOLIS)
    except ValueError as exc:
        assert "abrangência verificável" in str(exc)
    else:
        raise AssertionError("The SAPL connector accepted an unknown federation scope")


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

    state_item = parse_catalog_page({"results": [{
        "id": 1449, "__str__": "Lei nº 2.726, de 05 de abril de 2001", "tipo": 2,
        "texto_integral": "http://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2001/1449/1449_texto_integral.pdf",
        "numero": "2726", "ano": 2001, "esfera_federacao": "E", "data": "2001-04-05",
        "data_publicacao": None, "ementa": "Norma estadual publicada nesta instalação SAPL.",
    }]}, {"2": "Lei Complementar"}, instance=ANAPOLIS)[0]
    sync_catalog_page(db_session, [state_item], observed_at=datetime.now(timezone.utc), instance=ANAPOLIS)
    db_session.commit()
    state_law = db_session.get(Law, "sapl-5201108-1449")
    assert (state_law.jurisdiction, state_law.state_code, state_law.municipality) == ("state", "GO", None)
    assert state_law.coverage["sapl_federation_scope"] == "E"

    federal_item = parse_catalog_page({"results": [{
        "id": 1448, "__str__": "Lei Federal nº 100, de 05 de abril de 2001", "tipo": 1,
        "texto_integral": "http://sapl.anapolis.go.leg.br/media/sapl/public/normajuridica/2001/1448/lei.pdf",
        "numero": "100", "ano": 2001, "esfera_federacao": "F", "data": "2001-04-05",
        "data_publicacao": None, "ementa": "Norma federal publicada nesta instalação SAPL.",
    }]}, {"1": "Lei"}, instance=ANAPOLIS)[0]
    sync_catalog_page(db_session, [federal_item], observed_at=datetime.now(timezone.utc), instance=ANAPOLIS)
    db_session.commit()
    federal_law = db_session.get(Law, "sapl-5201108-1448")
    assert (federal_law.jurisdiction, federal_law.state_code, federal_law.municipality) == ("federal", None, None)
    assert federal_law.coverage["sapl_federation_scope"] == "F"


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

ALAGOAS = next(item for item in SAPL_INSTANCES if item.source_id == "state:AL:sapl")

MUNICIPAL_SAPL_EXPECTED = {
    "2301000": ("Aquiraz", "CE", "sapl.aquiraz.ce.leg.br"),
    "2302800": ("Canindé", "CE", "sapl.caninde.ce.leg.br"),
    "2304285": ("Eusébio", "CE", "sapl.eusebio.ce.leg.br"),
    "2307650": ("Maracanaú", "CE", "sapl.maracanau.ce.leg.br"),
    "2507507": ("João Pessoa", "PB", "sapl.joaopessoa.pb.leg.br"),
    "2304400": ("Fortaleza", "CE", "sapl.fortaleza.ce.leg.br"),
    "3303906": ("Petrópolis", "RJ", "sapl.petropolis.rj.leg.br"),
    "4314407": ("Pelotas", "RS", "sapl.pelotas.rs.leg.br"),
    "4104204": ("Campo Largo", "PR", "sapl.campolargo.pr.leg.br"),
    "1506807": ("Santarém", "PA", "sapl.santarem.pa.leg.br"),
    "1500602": ("Altamira", "PA", "sapl.altamira.pa.leg.br"),
    "1505536": ("Parauapebas", "PA", "sapl.parauapebas.pa.leg.br"),
    "3143302": ("Montes Claros", "MG", "sapl.montesclaros.mg.leg.br"),
    "3170701": ("Varginha", "MG", "sapl.varginha.mg.leg.br"),
    "3122306": ("Divinópolis", "MG", "sapl.divinopolis.mg.leg.br"),
    "1721000": ("Palmas", "TO", "sapl.palmas.to.leg.br"),
    "1100122": ("Ji-Paraná", "RO", "sapl.jiparana.ro.leg.br"),
}


def test_verified_municipal_sapl_installations_keep_ibge_identity():
    municipalities = {
        item.ibge_code: item
        for item in SAPL_INSTANCES
        if item.scope_kind == "municipality" and item.ibge_code in MUNICIPAL_SAPL_EXPECTED
    }
    assert municipalities.keys() == MUNICIPAL_SAPL_EXPECTED.keys()
    for ibge_code, (name, uf, host) in MUNICIPAL_SAPL_EXPECTED.items():
        item = municipalities[ibge_code]
        assert (item.municipality, item.state_code, item.host) == (
            name, uf, f"https://{host}",
        )
        assert item.source_id == f"municipality:{ibge_code}:sapl"
        assert item.jurisdiction_id == f"municipality:{ibge_code}"
        assert item.federation_scope_filter is None


STATE_SAPL_EXPECTED = {
    "AC": ("sapl.al.ac.leg.br", "https://www.al.ac.leg.br/"),
    "AL": ("sapl.al.al.leg.br", "https://www.al.al.leg.br/"),
    "AM": ("sapl.al.am.leg.br", "https://www.aleam.gov.br/"),
    "MT": ("sapl.al.mt.leg.br", "https://www.al.mt.gov.br/"),
    "PB": ("sapl.al.pb.leg.br", "https://www.al.pb.leg.br/"),
    "PI": ("sapl.al.pi.leg.br", "https://www.al.pi.leg.br/"),
    "RO": ("sapl.al.ro.leg.br", "https://www.al.ro.leg.br/"),
    "TO": ("sapl.al.to.leg.br", "https://www.al.to.leg.br/"),
}


def test_verified_state_sapl_installations_are_scoped_to_their_uf():
    states = {item.state_code: item for item in SAPL_INSTANCES if item.scope_kind == "state"}
    assert set(STATE_SAPL_EXPECTED) <= states.keys()
    for uf, (host, authority_url) in STATE_SAPL_EXPECTED.items():
        item = states[uf]
        assert item.host == f"https://{host}"
        assert item.authority_url == authority_url
        assert item.source_id == f"state:{uf}:sapl"
        assert item.jurisdiction_id == f"state:{uf}"
        assert item.federation_scope_filter == "E"


def test_alagoas_state_sapl_keeps_only_verified_state_records():
    assert ALAGOAS.jurisdiction_id == "state:AL"
    assert ALAGOAS.host == "https://sapl.al.al.leg.br"
    assert ALAGOAS.federation_scope_filter == "E"

    payload = {"results": [{
        "id": 4071, "__str__": "Lei Ordinária nº 10.064, de 17 de setembro de 2026",
        "tipo": 1, "texto_integral": "http://sapl.al.al.leg.br/media/sapl/public/normajuridica/2026/4071/lei.pdf",
        "numero": "10064", "ano": 2026, "esfera_federacao": "E", "data": "2026-09-17",
        "data_publicacao": "2026-09-18", "ementa": "Norma estadual.",
    }]}
    [law] = parse_catalog_page(payload, {"1": "Lei Ordinária"}, instance=ALAGOAS)
    assert law.text_url == "https://sapl.al.al.leg.br/media/sapl/public/normajuridica/2026/4071/lei.pdf"

    out_of_scope = {"results": [{**payload["results"][0], "esfera_federacao": "M"}]}
    try:
        parse_catalog_page(out_of_scope, {"1": "Lei Ordinária"}, instance=ALAGOAS)
    except ValueError as exc:
        assert "abrangência verificável" in str(exc)
    else:
        raise AssertionError("The Alagoas state catalog accepted a municipal record")
