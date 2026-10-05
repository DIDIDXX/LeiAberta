from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.catalog_sync import senado
from app.catalog_sync.senado import parse_law_catalog
from app.db import get_session
from app.main import app
from app.models import Law, LawChange, LawVersion, LegalNode, SourceRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "official"


def _client_for(db_session):
    def override_session():
        yield db_session
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_new_senate_norm_catalog_search_hydration_and_retry_are_idempotent(db_session, monkeypatch):
    """A fixture stands in for a new official catalog row arriving between refreshes."""
    fixture = (FIXTURES / "senado-list-lei13709-2018.xml").read_bytes()
    [record] = parse_law_catalog(fixture, minimum_records=1)
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    monkeypatch.setitem(senado.MINIMUM_RECORDS, "LEI", 1)
    monkeypatch.setattr(senado, "fetch_law_catalog", lambda type_code: (fixture, "https://fixture.invalid/catalog"))
    first = senado.sync_senado_law_catalog(type_codes=("LEI",), force=True)
    assert first["added"] == 1
    law = db_session.query(Law).filter_by(external_source_id=record.remote_id).one()
    assert law.materialization_status == "catalog"
    assert db_session.query(Law).filter_by(external_source_id=record.remote_id).count() == 1

    monkeypatch.setattr(senado, "fetch_law_catalog", lambda type_code: (_ for _ in ()).throw(TimeoutError("fixture source unavailable")))
    failed = senado.sync_senado_law_catalog(type_codes=("LEI",), force=True)
    assert failed["errors"]
    assert db_session.query(Law).filter_by(external_source_id=record.remote_id).count() == 1

    monkeypatch.setattr(senado, "fetch_law_catalog", lambda type_code: (fixture, "https://fixture.invalid/catalog"))
    retry = senado.sync_senado_law_catalog(type_codes=("LEI",), force=True)
    assert retry["errors"] == []
    assert retry["added"] == 0
    assert db_session.query(Law).filter_by(external_source_id=record.remote_id).count() == 1

    monkeypatch.setattr("app.main.queue_hydration", lambda law, refresh=False: SimpleNamespace(
        id="fixture-hydration", status="queued", stage=0, message="Aguardando worker",
    ))
    client = _client_for(db_session)
    try:
        search = client.get("/api/search?q=13709").json()
        detail = client.get(f"/api/laws/{law.slug}")
    finally:
        app.dependency_overrides.clear()
    assert search["results"][0]["slug"] == law.slug
    assert detail.status_code == 200
    assert detail.json()["materializable"] is True
    assert detail.json()["job"]["id"] == "fixture-hydration"


def test_blame_and_node_provenance_distinguish_verified_partial_and_unknown(db_session, add_law):
    law = add_law()
    db_session.add(law)
    version = LawVersion(law_slug=law.slug, version_name="atual", source_url=law.source_url,
                         checksum="a" * 64, parser_version="test", article_count=2)
    db_session.add(version)
    db_session.flush()
    law.current_version_id = version.id
    law.materialization_status = "ready"
    nodes = [
        LegalNode(law_slug=law.slug, version_id=version.id, node_id="art:1", node_type="article",
                  label="Art. 1º", text="Texto com alteração verificada.", order_index=1),
        LegalNode(law_slug=law.slug, version_id=version.id, node_id="art:2", node_type="article",
                  label="Art. 2º", text="Texto sem origem localizada.", order_index=2),
    ]
    db_session.add_all(nodes)
    db_session.add(LawChange(
        id="verified-change", law_slug=law.slug, node_id="art:1", change_type="ADD",
        summary="Incluído por alteração", changed_at=None, source_law_label="Lei nº 14.550/2023",
        source_law_number="14.550", source_law_year=2023,
        source_url="https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/L14550.htm",
        law_source_url=law.source_url, before_text="", after_text="Texto com alteração verificada.",
        evidence_marker="Incluído pela Lei nº 14.550, de 2023",
    ))
    db_session.commit()
    client = _client_for(db_session)
    try:
        blame_response = client.get(f"/api/laws/{law.slug}/blame?limit=10")
        page_two_response = client.get(f"/api/laws/{law.slug}/blame?limit=1&offset=1")
        verified_response = client.get(f"/api/laws/{law.slug}/nodes/art%3A1/provenance")
        unknown_response = client.get(f"/api/laws/{law.slug}/nodes/art%3A2/provenance")
        assert blame_response.status_code == 200, blame_response.text
        assert page_two_response.status_code == 200, page_two_response.text
        assert verified_response.status_code == 200, verified_response.text
        assert unknown_response.status_code == 200, unknown_response.text
        blame, page_two, verified, unknown = (blame_response.json(), page_two_response.json(),
                                               verified_response.json(), unknown_response.json())
    finally:
        app.dependency_overrides.clear()
    assert len(blame["items"]) == 2
    assert page_two["items"][0]["node_id"] == "art:2"
    assert blame["items"][0]["responsible_act"]["label"] == "Lei nº 14.550/2023"
    assert blame["items"][1]["origin_status"] == "not_identified"
    assert verified["status"] == "verified"
    assert verified["last_verified_change"]["before_text"] == ""
    assert unknown["status"] == "not_identified"


def test_sources_api_exposes_success_freshness_and_delta_fields(db_session):
    old = datetime.now(timezone.utc) - timedelta(days=9)
    db_session.add(SourceRegistry(
        id="state:SP:test", jurisdiction_id=None, name="Fonte teste", adapter="sapl_catalog",
        base_url="https://example.invalid", evidence_url="https://example.invalid/official",
        status="stale", last_checked_at=datetime.now(timezone.utc),
        scope={"last_success_at": old.isoformat(), "new_records": 4,
               "updated_records": 2, "sync_failures": 1}, last_error="Timeout recente",
    ))
    db_session.commit()
    client = _client_for(db_session)
    try:
        response = client.get("/api/sources")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["last_success_at"] == old.isoformat()
    assert item["freshness_status"] == "stale"
    assert (item["new_records"], item["updated_records"], item["failed_records"], item["sync_failures"]) == (4, 2, None, 1)
    assert item["request_policy"]["page_size"] == 100
