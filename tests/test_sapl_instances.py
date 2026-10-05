from datetime import date, datetime, timezone

from sqlalchemy.exc import OperationalError

from app.catalog_sync.sapl import (
    SAPL_INSTANCES,
    _is_retryable_catalog_lock,
    parse_catalog_page,
    sync_catalog_page,
)
from app.models import Jurisdiction, Law
from app.sources import sapl


ANAPOLIS = next(item for item in SAPL_INSTANCES if item.ibge_code == "5201108")
CAMPINA_GRANDE = next(item for item in SAPL_INSTANCES if item.ibge_code == "2504009")


def test_sapl_catalog_retries_only_transient_postgres_lock_errors():
    lock_timeout = OperationalError("insert", {}, Exception("lock timeout"))
    lock_timeout.orig.sqlstate = "55P03"
    unique_violation = OperationalError("insert", {}, Exception("duplicate key"))
    unique_violation.orig.sqlstate = "23505"

    assert _is_retryable_catalog_lock(lock_timeout)
    assert not _is_retryable_catalog_lock(unique_violation)


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


def test_sapl_keeps_catalog_records_when_the_official_signature_date_is_missing():
    campo_largo = next(item for item in SAPL_INSTANCES if item.ibge_code == "4104204")
    payload = {"results": [{
        "id": 198, "__str__": "Lei nº 99, de ", "tipo": 1,
        "texto_integral": "http://sapl.campolargo.pr.leg.br/media/sapl/public/normajuridica/1967/198/198_texto_integral.html",
        "numero": "99", "ano": 1967, "esfera_federacao": "", "data": None,
        "data_publicacao": None, "ementa": "Dispõe sobre os cemitérios públicos municipais.",
    }]}

    [item] = parse_catalog_page(payload, {"1": "Lei"}, instance=campo_largo)

    assert item.remote_id == "198"
    assert item.year == 1967
    assert item.signed_at is None
    assert item.number == "99"


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


def test_expanded_sapl_directory_has_unique_identity_for_all_configured_municipalities():
    municipalities = [item for item in SAPL_INSTANCES if item.scope_kind == "municipality"]
    assert len(municipalities) == 581
    assert len({item.ibge_code for item in municipalities}) == 581
    assert len({item.source_id for item in SAPL_INSTANCES}) == len(SAPL_INSTANCES)
    assert len({item.host for item in SAPL_INSTANCES}) == len(SAPL_INSTANCES)
    assert len({item.source_name for item in SAPL_INSTANCES}) == len(SAPL_INSTANCES)

    recovered = next(item for item in municipalities if item.ibge_code == "1101708")
    assert recovered.host == "https://sapl.urupa.ro.leg.br"
    assert recovered.source_id == "municipality:1101708:sapl"


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


def test_sapl_catalog_pages_use_stable_primary_key_order(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from app.catalog_sync import sapl as sapl_catalog

    sao_joao = next(item for item in SAPL_INSTANCES if item.ibge_code == "3549102")
    payload = {"results": [], "pagination": {"page": 43, "total_entries": 12086, "total_pages": 121}}
    requested = {}

    def fake_get_json(url, *, timeout, instance):
        requested.update(url=url, timeout=timeout, instance=instance)
        return payload, url

    monkeypatch.setattr(sapl_catalog, "_get_json", fake_get_json)
    result, final_url = sapl_catalog.fetch_catalog_page(43, instance=sao_joao)

    assert result is payload
    assert final_url == requested["url"]
    assert requested["instance"] is sao_joao
    assert parse_qs(urlparse(final_url).query) == {
        "page_size": ["100"], "page": ["43"], "o": ["id"],
    }


def test_sapl_reader_retries_transient_page_404(monkeypatch):
    import io
    import json
    from urllib.error import HTTPError

    from app.catalog_sync import sapl as sapl_catalog

    instance = next(item for item in SAPL_INSTANCES if item.ibge_code == "2507507")
    url = instance.norms_url + "?page_size=100&page=91&o=id"
    payload = {"results": [], "pagination": {"page": 91, "total_entries": 22097, "total_pages": 221}}
    calls = []

    class Response(io.BytesIO):
        status = 200

        def geturl(self):
            return url

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(url, 404, "temporary page routing miss", {}, io.BytesIO())
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(sapl_catalog.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sapl_catalog.time, "sleep", lambda _seconds: None)

    result, final_url = sapl_catalog._get_json(url, timeout=5, instance=instance)

    assert result == payload
    assert final_url == url
    assert calls == [url, url]


def test_sapl_page_checkpoints_reject_nonascending_ids():
    from app.catalog_sync.sapl import _page_checkpoint

    try:
        _page_checkpoint([
            type("Norm", (), {"remote_id": "11"})(),
            type("Norm", (), {"remote_id": "10"})(),
        ])
    except ValueError as exc:
        assert "ordem estritamente crescente" in str(exc)
    else:
        raise AssertionError("A SAPL page checkpoint accepted descending IDs")


def test_sapl_catalog_sync_resumes_after_last_committed_page(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.catalog_sync import sapl as sapl_catalog
    from app.catalog_sync.sapl import SaplInstance
    from app.models import SourceRegistry

    instance = SaplInstance(
        ibge_code="9900001", municipality="Cidade de Teste", state_code="ZZ",
        host="https://sapl.teste.zz.leg.br", source_id="municipality:9900001:sapl",
        source_name="Câmara Municipal de Teste — SAPL", authority_url="https://camara.teste.zz/",
    )
    monkeypatch.setattr(sapl_catalog, "PAGE_SIZE", 2)
    monkeypatch.setattr(sapl_catalog, "SessionLocal", sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False,
    ))
    monkeypatch.setattr(sapl_catalog, "fetch_type_names", lambda **_kwargs: {"1": "Lei"})

    rows = {
        1: [(1, "Lei 1"), (2, "Lei 2")],
        2: [(3, "Lei 3"), (4, "Lei 4")],
    }
    calls = []
    fail_second_page_once = True

    def fetch_page(page, **_kwargs):
        nonlocal fail_second_page_once
        calls.append(page)
        if page == 2 and fail_second_page_once:
            fail_second_page_once = False
            raise RuntimeError("interrupção de teste")
        payload = {"pagination": {"page": page, "total_entries": 4, "total_pages": 2}, "results": []}
        for remote_id, title in rows[page]:
            payload["results"].append({
                "id": remote_id, "__str__": title, "tipo": 1, "numero": str(remote_id),
                "ano": 2024, "esfera_federacao": "M", "data": "2024-01-01",
                "data_publicacao": None, "ementa": title,
            })
        return payload, instance.norms_url

    monkeypatch.setattr(sapl_catalog, "fetch_catalog_page", fetch_page)

    import pytest
    with pytest.raises(RuntimeError, match="interrupção de teste"):
        sapl_catalog.sync_sapl_catalog(instance, force=True)

    registry = db_session.get(SourceRegistry, instance.source_id)
    assert registry.status == "failed"
    assert registry.scope["last_page"] == 1
    assert registry.scope["records_enumerated"] == 2
    assert len(registry.scope["page_checkpoints"]) == 1

    result = sapl_catalog.sync_sapl_catalog(instance)

    assert result["records"] == result["expected"] == 4
    assert result["added"] == 2
    assert calls == [1, 2, 1, 2]
    assert db_session.query(Law).filter_by(source_name=instance.source_name).count() == 4
    db_session.expire_all()
    registry = db_session.get(SourceRegistry, instance.source_id)
    assert registry.status == "enumerated"
    assert registry.scope["records_enumerated"] == 4
    assert registry.scope["catalog_ids_digest_algorithm"] == "sha256-of-ordered-page-sha256s-v1"
