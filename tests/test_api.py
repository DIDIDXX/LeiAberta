from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import HydrationJob, Jurisdiction, Law, LawVersion, LegalNode, SenateProceeding, SourceSnapshot


def test_search_endpoint_handles_typo(db_session, add_law):
    db_session.add(add_law())
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/search?q=LGDP")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestion"] is True
    assert payload["results"][0]["slug"] == "13709-2018"


def test_public_responses_include_baseline_security_headers():
    response = TestClient(app).get("/robots.txt", headers={"x-forwarded-proto": "https"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_readiness_requires_current_alembic_schema(db_session):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    expected_heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
        {"head": expected_heads[0]},
    )
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_rejects_missing_alembic_schema(db_session):
    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503


def test_public_rate_limit_returns_429_and_retry_after(monkeypatch):
    from app import main

    monkeypatch.setenv("REDIS_URL", "redis://unused")
    monkeypatch.setattr(main, "_consume_rate_budget", lambda *_args: (601, 17))
    response = TestClient(app).get("/api/search?q=anything")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    assert response.headers["cache-control"] == "no-store"


def test_rate_limit_policy_covers_enqueue_routes_without_trusting_forwarded_ip():
    from app.main import _rate_limit_policy

    assert _rate_limit_policy("GET", "/api/search") == ("search", 600, 60)
    assert _rate_limit_policy("GET", "/api/laws/13709-2018/nodes") == ("law-detail", 240, 60)
    assert _rate_limit_policy("POST", "/api/laws/11340-2006/history/prepare") == ("job-prepare", 60, 60)
    assert _rate_limit_policy("POST", "/api/laws/13709-2018/hydrate") == ("job-prepare", 60, 60)
    assert _rate_limit_policy("GET", "/api/stats") is None


def test_planalto_fetch_rejects_oversized_response(monkeypatch):
    from app.sources import planalto

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size):
            assert size == planalto.MAX_SOURCE_BYTES + 1
            return b"x" * size

        def geturl(self):
            return "https://www.planalto.gov.br/ccivil_03/leis/l13709.htm"

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(planalto.urllib.request, "build_opener", lambda *_args: Opener())
    with pytest.raises(ValueError, match="excede o limite"):
        planalto.fetch_official_html("https://www.planalto.gov.br/ccivil_03/leis/l13709.htm")


def test_planalto_fetch_rejects_untrusted_url_without_network(monkeypatch):
    from app.sources import planalto

    def network_must_not_run(*_args, **_kwargs):
        raise AssertionError("unexpected network request")

    monkeypatch.setattr(planalto.urllib.request, "build_opener", network_must_not_run)
    with pytest.raises(ValueError, match="domínio HTTPS oficial"):
        planalto.fetch_official_html("https://example.org/law")


def test_planalto_redirect_handler_blocks_external_and_downgrade_redirects():
    from app.sources.planalto import _PlanAltoRedirectHandler
    from urllib.request import Request

    handler = _PlanAltoRedirectHandler()
    req = Request("https://www.planalto.gov.br/lei")
    for destination in ["https://example.org/", "http://www.planalto.gov.br/lei"]:
        with pytest.raises(ValueError, match="redirecionar"):
            handler.redirect_request(req, object(), 302, "Found", {}, destination)


def test_planalto_fetch_upgrades_http_url_to_official_https(monkeypatch):
    from app.sources import planalto

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b"<html><body>Official</body></html>"

        def geturl(self):
            return "https://www.planalto.gov.br/lei"

    class Opener:
        def open(self, req, timeout):
            assert req.full_url == "https://www.planalto.gov.br/lei"
            assert timeout == 25
            return Response()

    monkeypatch.setattr(planalto.urllib.request, "build_opener", lambda *_args: Opener())
    body, final_url = planalto.fetch_official_html("http://www.planalto.gov.br/lei")
    assert body.startswith(b"<html>")
    assert final_url == "https://www.planalto.gov.br/lei"


def test_planalto_fetch_retries_transient_https_503(monkeypatch):
    from app.sources import planalto
    from urllib.error import HTTPError

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b"<html><body>Official</body></html>"

        def geturl(self):
            return "https://www.planalto.gov.br/lei"

    class Opener:
        calls = 0

        def open(self, _request, timeout):
            self.calls += 1
            assert timeout == 25
            if self.calls == 1:
                raise HTTPError("https://www.planalto.gov.br/lei", 503, "Unavailable", {"Retry-After": "0"}, None)
            return Response()

    opener = Opener()
    monkeypatch.setattr(planalto.urllib.request, "build_opener", lambda *_args: opener)
    monkeypatch.setattr(planalto.time, "sleep", lambda _delay: None)
    body, _ = planalto.fetch_official_html("https://www.planalto.gov.br/lei")
    assert body.startswith(b"<html>")
    assert opener.calls == 2


def test_sitemap_uses_configured_public_url(db_session, add_law, monkeypatch):
    db_session.add(add_law())
    db_session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leiaberta.example/")

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/sitemap.xml")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "https://leiaberta.example/sitemap-laws-0.xml" in response.text
    assert "leiaberta.up.railway.app" not in response.text

    app.dependency_overrides[get_session] = override_session
    try:
        fragment = TestClient(app).get("/sitemap-laws-0.xml")
    finally:
        app.dependency_overrides.clear()
    assert fragment.status_code == 200
    assert "https://leiaberta.example/lei/13709-2018" in fragment.text


def test_sitemap_fragment_rejects_pages_outside_catalog(db_session):
    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/sitemap-laws-0.xml")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_law_page_has_canonical_metadata_and_no_script_content(db_session, add_law, monkeypatch):
    db_session.add(add_law())
    db_session.commit()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leiaberta.example/")

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/lei/13709-2018")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '<title>Lei Geral de Proteção de Dados Pessoais — LeiAberta</title>' in response.text
    assert 'href="https://leiaberta.example/lei/13709-2018"' in response.text
    assert "<noscript>" in response.text
    assert "https://www.planalto.gov.br/" in response.text


def test_law_page_canonical_uses_forwarded_https_when_config_is_absent(db_session, add_law, monkeypatch):
    db_session.add(add_law())
    db_session.commit()
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get(
            "/lei/13709-2018",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "leiaberta.example"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'href="https://leiaberta.example/lei/13709-2018"' in response.text


def test_stats_reports_aggregated_catalog_counts(db_session, add_law):
    law = add_law()
    db_session.add(law)
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/stats")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["indexed_laws"] == 1
    assert response.json()["materialized_laws"] == 0


def test_history_is_explicitly_not_requested_until_a_real_job_exists(db_session, add_law):
    db_session.add(add_law())
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/laws/13709-2018/history")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_requested"
    assert payload["job"] is None


def test_senate_proceedings_endpoint_returns_persisted_official_dossier(db_session, add_law):
    law = add_law()
    db_session.add(law)
    db_session.flush()
    db_session.add(SenateProceeding(
        law_slug=law.slug, status="complete", checked_at=datetime.now(timezone.utc),
        data={"status": "complete", "matching_processes_found": 1,
              "processes": [{"process": {"identificacao": "PL 1604/2022"}, "amendments": [],
                             "committee_votes": [], "plenary_votes": [], "source_urls": []}]},
    ))
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get(f"/api/laws/{law.slug}/proceedings")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["matching_processes_found"] == 1
    assert payload["processes"][0]["process"]["identificacao"] == "PL 1604/2022"


def test_senate_proceedings_prepare_queues_a_durable_priority_job(db_session, add_law, monkeypatch):
    from types import SimpleNamespace

    law = add_law()
    db_session.add(law)
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.main.queue_provenance", lambda stored_law, refresh=False: SimpleNamespace(
        id="senate-provenance-job", status="queued", stage_name="queued", message="Aguardando worker",
        job_type="provenance", attempts=0,
    ))
    try:
        response = TestClient(app).post(f"/api/laws/{law.slug}/proceedings/prepare")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["id"] == "senate-provenance-job"
    assert response.json()["job_type"] == "provenance"


def test_queued_text_hydration_does_not_claim_history_is_being_prepared(db_session, add_law):
    db_session.add(add_law())
    db_session.flush()
    db_session.add(HydrationJob(
        id="text-job", law_slug="13709-2018", job_type="hydrate", status="queued",
        stage_name="queued", message="Aguardando texto", created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/laws/13709-2018/history")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_requested"
    assert payload["job"] is None


def test_history_prepare_creates_a_persisted_job(db_session, add_law, monkeypatch):
    import app.jobs as jobs
    from app.models import JobOutbox

    db_session.add(add_law())
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)
    job = jobs.queue_history(db_session.get(Law, "13709-2018"))
    assert job.id
    assert job.job_type == "history"
    assert job.status == "queued"
    assert db_session.query(JobOutbox).filter_by(job_id=job.id).one()


def test_jurisdictions_endpoint_filters_and_paginates(db_session):
    db_session.add_all([
        Jurisdiction(id="state:SP", kind="state", name="São Paulo", ibge_code="35", uf="SP",
                     parent_id="federal", legislature_eligible=True, territorial_status="active",
                     metadata_json={}, source_url="https://servicodados.ibge.gov.br/", observed_at=datetime.now(timezone.utc)),
        Jurisdiction(id="municipality:3509502", kind="municipality", name="Campinas", ibge_code="3509502", uf="SP",
                     parent_id="state:SP", legislature_eligible=True, territorial_status="active",
                     metadata_json={}, source_url="https://servicodados.ibge.gov.br/", observed_at=datetime.now(timezone.utc)),
    ])
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/jurisdictions?kind=municipality&uf=sp&limit=1")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == "municipality:3509502"
    assert payload["has_more"] is False


def test_senado_catalog_entry_can_queue_text_without_claiming_it_is_ready(db_session, monkeypatch):
    from types import SimpleNamespace

    row = Law(
        slug="senado-36981001", jurisdiction="federal", law_type="Lei", number="14.550", year=2023,
        external_source_id="36981001", title="Lei nº 14.550 de 19/04/2023",
        description="Altera a Lei Maria da Penha.", status="Não verificado", aliases=["LEI-14550-2023-04-19"],
        source_name="Senado Federal — Dados Abertos Legislativos",
        source_url="https://legis.senado.leg.br/dadosabertos/legislacao/36981001",
        fetch_url="https://legis.senado.leg.br/dadosabertos/legislacao/36981001",
        materialization_status="catalog", coverage={"official_source": "senado_metadata"},
    )
    db_session.add(row)
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.main.queue_hydration", lambda law, refresh=False: SimpleNamespace(
        id="senado-hydration-job", status="queued", stage=0, message="Aguardando worker",
    ))
    try:
        client = TestClient(app)
        detail = client.get("/api/laws/senado-36981001")
        nodes = client.get("/api/laws/senado-36981001/nodes")
        hydrate = client.post("/api/laws/senado-36981001/hydrate")
    finally:
        app.dependency_overrides.clear()
    assert detail.status_code == 200
    assert detail.json()["materializable"] is True
    assert detail.json()["job"]["id"] == "senado-hydration-job"
    assert nodes.json()["status"] == "catalog"
    assert nodes.json()["items"] == []
    assert hydrate.status_code == 202


def test_document_audit_uses_archived_source_and_never_certifies_completeness(db_session, add_law):
    import hashlib

    law = add_law()
    body = "<html><head><meta charset='utf-8'></head><body><p>Art. 1º Texto oficial.</p><a href='/anexo.pdf'>Anexo</a></body></html>".encode()
    checksum = hashlib.sha256(body).hexdigest()
    db_session.add(law)
    version = LawVersion(law_slug=law.slug, version_name="Consolidado", source_url=law.source_url,
                         retrieved_at=datetime.now(timezone.utc), checksum=checksum,
                         parser_version="2.0", is_current=True, article_count=1)
    db_session.add(version)
    db_session.flush()
    law.current_version_id = version.id
    db_session.add(LegalNode(law_slug=law.slug, version_id=version.id, node_id="art:1", parent_node_id=None,
                             node_type="article", label="Art. 1º", text="Texto oficial.", source_note="", order_index=1))
    db_session.add(SourceSnapshot(law_slug=law.slug, version_id=None, source_url=law.source_url,
                                  checksum=checksum, raw_format="text/html; charset=utf-8", raw_body=body,
                                  retrieved_at=datetime.now(timezone.utc)))
    db_session.commit()

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).get("/api/laws/13709-2018/audit")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["checksum"] == checksum
    assert payload["audit"]["source_unique_article_count"] == 1
    assert payload["audit"]["detected_pdf_attachments"]
    assert payload["audit"]["completeness_certified"] is False
