from datetime import date, datetime, timezone

import pytest

import app.catalog_sync.sapl as sapl_catalog
from app.catalog_sync.sapl import parse_catalog_page, sync_catalog_page
from app.models import Jurisdiction, Law
from app.sources import sapl
from app.sources.normas import SourceDocumentUnavailable


def _catalog_payload(media="https://sapl.cmm.am.gov.br/media/sapl/public/normajuridica/1949/1/lei.pdf"):
    return {"results": [{
        "id": 1, "__str__": "Lei Ordinária nº 115, de 05 de janeiro de 1949", "tipo": 2,
        "texto_integral": media, "numero": "115", "ano": 1949, "esfera_federacao": "M",
        "data": "1949-01-05", "data_publicacao": None,
        "ementa": "Concede auxílio e dá outras providências.",
    }]}


def test_sapl_catalog_parser_captures_municipal_identity_and_attachment():
    [item] = parse_catalog_page(_catalog_payload(), {"2": "Lei Ordinária"})
    assert (item.remote_id, item.law_type, item.number, item.year, item.signed_at) == (
        "1", "Lei Ordinária", "115", 1949, date(1949, 1, 5),
    )
    assert item.source_url.endswith("/api/norma/normajuridica/1/")
    assert item.text_url.endswith("/1949/1/lei.pdf")


def test_sapl_json_reader_retries_response_body_timeout(monkeypatch):
    import io
    import json

    url = "https://sapl.cmm.am.gov.br/api/norma/normajuridica/?page_size=100&page=34"
    payload = {"results": [], "pagination": {"page": 34}}
    calls = []

    class Response(io.BytesIO):
        status = 200

        def __init__(self, body, *, fail_read=False):
            super().__init__(body)
            self.fail_read = fail_read

        def geturl(self):
            return url

        def read(self, size=-1):
            if self.fail_read:
                self.fail_read = False
                raise TimeoutError("body read timed out")
            return super().read(size)

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers.get("Connection")))
        return Response(json.dumps(payload).encode(), fail_read=len(calls) == 1)

    monkeypatch.setattr(sapl_catalog.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sapl_catalog.time, "sleep", lambda _seconds: None)

    result, final_url = sapl_catalog._get_json(url, timeout=7)

    assert result == payload
    assert final_url == url
    assert len(calls) == 2
    assert all(call[1:] == (7, "close") for call in calls)


def test_sapl_catalog_preserves_designation_year_when_signature_is_next_year():
    payload = _catalog_payload()
    record = payload["results"][0]
    record.update({
        "__str__": "Emenda à Loman nº 6, de 21 de fevereiro de 1995",
        "numero": "6", "ano": 1994, "data": "1995-02-21",
    })
    [item] = parse_catalog_page(payload, {"2": "Emenda à Lei Orgânica"})
    assert item.year == 1994
    assert item.signed_at == date(1995, 2, 21)


def test_sapl_catalog_rejects_wrong_federation_and_untrusted_attachment():
    payload = _catalog_payload("https://attacker.example/law.pdf")
    assert parse_catalog_page(payload, {"2": "Lei Ordinária"})[0].text_url is None
    payload["results"][0]["esfera_federacao"] = "E"
    with pytest.raises(ValueError, match="identidade municipal"):
        parse_catalog_page(payload, {"2": "Lei Ordinária"})


def test_sapl_catalog_page_sync_is_idempotent_and_scoped_to_manaus(db_session):
    db_session.add_all([
        Jurisdiction(id="state:AM", kind="state", name="Amazonas", uf="AM", source_url="https://example.gov/am"),
        Jurisdiction(id="municipality:1302603", kind="municipality", name="Manaus", ibge_code="1302603",
                     uf="AM", parent_id="state:AM", source_url="https://servicodados.ibge.gov.br/"),
    ])
    db_session.commit()
    [item] = parse_catalog_page(_catalog_payload(), {"2": "Lei Ordinária"})
    first = sync_catalog_page(db_session, [item], observed_at=datetime.now(timezone.utc))
    db_session.commit()
    second = sync_catalog_page(db_session, [item], observed_at=datetime.now(timezone.utc))
    law = db_session.get(Law, "manaus-sapl-1")
    assert first == {"added": 1, "refreshed": 0}
    assert second == {"added": 0, "refreshed": 1}
    assert (law.jurisdiction, law.state_code, law.municipality) == ("municipality", "AM", "Manaus")
    assert law.external_source_id == "sapl:manaus:1"
    assert law.materialization_status == "catalog"


def test_sapl_document_archives_pdf_and_materializes_identity_checked_text(monkeypatch):
    raw = b"%PDF-1.7 original official bytes"
    extracted = ("<!doctype html><html><body><p>Lei Ordinária nº 115, de 05 de janeiro de 1949.</p>"
                 "<p>Art. 1º Concede auxílio para as despesas do evento municipal.</p></body></html>").encode()
    monkeypatch.setattr(sapl, "_verified_detail", lambda *a, **k: ("1", {
        "texto_integral": "https://sapl.cmm.am.gov.br/media/sapl/public/normajuridica/1949/1/lei.pdf",
    }))
    monkeypatch.setattr(sapl, "_fetch", lambda *a, **k: (
        raw, "https://sapl.cmm.am.gov.br/media/sapl/public/normajuridica/1949/1/lei.pdf", "application/pdf"))
    monkeypatch.setattr(sapl, "pdf_to_html", lambda _body: extracted)
    result = sapl.fetch_sapl_document("https://sapl.cmm.am.gov.br/api/norma/normajuridica/1/",
                                      "Lei Ordinária", "115", 1949)
    assert result.body == raw
    assert result.parsed_body == extracted
    assert result.source_url.endswith("/lei.pdf")


def test_sapl_detail_accepts_designation_year_different_from_signature_year(monkeypatch):
    detail = {
        "id": 6518, "esfera_federacao": "M", "tipo": 5, "numero": "6", "ano": 1994,
        "data": "1995-02-21", "texto_integral": "https://sapl.cmm.am.gov.br/media/sapl/public/normajuridica/1994/6518/emenda.pdf",
    }
    monkeypatch.setattr(sapl, "_json", lambda *_args, **_kwargs: (detail, "https://sapl.cmm.am.gov.br/api/norma/normajuridica/6518/"))
    monkeypatch.setattr(sapl, "_type_name", lambda *_args, **_kwargs: "Emenda à Lei Orgânica")
    remote_id, verified = sapl._verified_detail(
        "https://sapl.cmm.am.gov.br/api/norma/normajuridica/6518/", "Emenda à Lei Orgânica", "6", 1994,
        timeout=1,
    )
    assert remote_id == "6518"
    assert verified["data"] == "1995-02-21"


def test_sapl_document_refetches_detail_when_attachment_metadata_is_temporarily_missing(monkeypatch):
    url = "https://sapl.cmm.am.gov.br/api/norma/normajuridica/9910/"
    base = {"id": 9910, "esfera_federacao": "M", "tipo": 14, "numero": "6920", "ano": 2026, "data": "2026-09-28"}
    first = {**base, "texto_integral": None}
    second = {**base, "texto_integral": "https://sapl.cmm.am.gov.br/media/sapl/public/normajuridica/2026/9910/decreto.pdf"}
    details = iter((first, second))
    monkeypatch.setattr(sapl, "_verified_detail", lambda *_args, **_kwargs: ("9910", next(details)))
    monkeypatch.setattr(sapl, "_fetch", lambda *_args, **_kwargs: (
        b"%PDF-original", second["texto_integral"], "application/pdf",
    ))
    monkeypatch.setattr(sapl, "pdf_to_html", lambda _body: (
        b"<html><body><p>Decreto Executivo 6.920/2026. Art. 1. Norma para desapropriacao municipal do imovel mencionado.</p></body></html>"
    ))

    document = sapl.fetch_sapl_document(url, "Decreto Executivo", "6920", 2026)
    assert document.source_url.endswith("/decreto.pdf")


def test_sapl_media_url_canonicalizes_official_relative_and_http_urls():
    path = "/media/sapl/public/normajuridica/2026/9910/decreto.pdf"
    assert sapl._validated_media_url(path) == "https://sapl.cmm.am.gov.br" + path
    assert sapl._validated_media_url("http://sapl.cmm.am.gov.br" + path) == "https://sapl.cmm.am.gov.br" + path


def test_sapl_document_rejects_media_url_outside_official_host(monkeypatch):
    monkeypatch.setattr(sapl, "_verified_detail", lambda *a, **k: ("1", {"texto_integral": "https://evil.example/law.pdf"}))
    with pytest.raises(SourceDocumentUnavailable, match="endereço oficial"):
        sapl.fetch_sapl_document("https://sapl.cmm.am.gov.br/api/norma/normajuridica/1/",
                                 "Lei Ordinária", "115", 1949)


def test_sapl_history_returns_official_relations_without_fabricated_diffs(monkeypatch):
    monkeypatch.setattr(sapl, "_verified_detail", lambda *a, **k: ("1", {}))
    rows = {
        "norma_principal": [{"id": 65, "norma_principal": 1, "norma_relacionada": 2,
                             "tipo_vinculo": 2, "resumo": "Altera a Lei Ordinária 115/1949"}],
        "norma_relacionada": [{"id": 66, "norma_principal": 3, "norma_relacionada": 1,
                               "tipo_vinculo": 2, "resumo": "Revoga parcialmente a Lei Ordinária 115/1949"}],
    }
    monkeypatch.setattr(sapl, "_paged_relations", lambda field, _id, **_kwargs: rows[field])
    monkeypatch.setattr(sapl, "_relation_type", lambda _type_id, **_kwargs: "Altera")
    snapshot = sapl.fetch_sapl_history("https://sapl.cmm.am.gov.br/api/norma/normajuridica/1/",
                                      "Lei Ordinária", "115", 1949)
    assert len(snapshot.relations) == 2
    assert {item.event_url.rsplit("/", 2)[-2] for item in snapshot.relations} == {"2", "3"}
    assert all(item.signed_at is None and item.device_ref == "" for item in snapshot.relations)
    assert all("não fornece redações anterior e posterior" in item.evidence for item in snapshot.relations)
