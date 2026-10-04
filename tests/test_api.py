from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Jurisdiction, Law


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
