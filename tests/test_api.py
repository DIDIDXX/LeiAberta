from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Law


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
