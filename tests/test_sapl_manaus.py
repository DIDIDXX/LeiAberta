from datetime import date, datetime, timezone

import pytest

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
