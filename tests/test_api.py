from datetime import datetime, timezone

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
    assert "https://leiaberta.example/lei/13709-2018" in response.text
    assert "leiaberta.up.railway.app" not in response.text


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
