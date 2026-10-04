import hashlib
import io
import json
from pathlib import Path

import pytest

from app.sources.alesp import fetch_alesp_document, fetch_alesp_history
from app.sources.normas import SourceDocumentUnavailable


FIXTURES = Path(__file__).parent / "fixtures" / "official"


def test_alesp_source_fetches_verified_official_html(monkeypatch):
    manifest = json.loads((FIXTURES / "alesp-norma-213020-manifest.json").read_text())
    metadata = (FIXTURES / "alesp-norma-213020.json").read_bytes()
    body = (FIXTURES / "alesp-norma-213020.html").read_bytes()
    for name, spec in manifest["files"].items():
        fixture = (FIXTURES / name).read_bytes()
        assert len(fixture) == spec["bytes"]
        assert hashlib.sha256(fixture).hexdigest() == spec["sha256"]
    calls = []

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/json"}

        def __init__(self, content, url, content_type):
            super().__init__(content)
            self.url = url
            self.headers = {"Content-Type": content_type}

        def geturl(self):
            return self.url

    def fake_urlopen(request, timeout=25):
        url = request.full_url
        calls.append(url)
        if url == manifest["urls"]["metadata"]:
            return Response(metadata, url, "application/json")
        if url == manifest["urls"]["text"]:
            return Response(body, url, "text/html; charset=utf-8")
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr("app.sources.alesp.urllib.request.urlopen", fake_urlopen)
    document = fetch_alesp_document(
        manifest["urls"]["human_record"], "Decreto", "70.916", 2026,
    )

    assert document.version == "Original"
    assert document.legal_value == "UnclassifiedLegalValue"
    assert document.representation == "Texto original no repositório ALESP"
    assert document.source_url == manifest["urls"]["text"]
    assert len(calls) == 2


def test_alesp_source_rejects_metadata_for_a_different_identity(monkeypatch):
    metadata = json.loads((FIXTURES / "alesp-norma-213020.json").read_text())
    metadata["nuNorma"] = "70917"
    payload = json.dumps(metadata).encode()

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/json"}

        def geturl(self):
            return "https://baleg-api-prd.al.sp.gov.br/normas/213020"

    monkeypatch.setattr("app.sources.alesp.urllib.request.urlopen", lambda *_a, **_kw: Response(payload))
    with pytest.raises(SourceDocumentUnavailable, match="identidade ALESP diverge"):
        fetch_alesp_document("https://www.al.sp.gov.br/norma/213020", "Decreto", "70.917", 2026)


def test_alesp_history_reads_official_amendment_annotations(monkeypatch):
    manifest = json.loads((FIXTURES / "alesp-norma-10261-1968-manifest.json").read_text())
    metadata = (FIXTURES / "alesp-norma-10261-1968.json").read_bytes()
    spec = manifest["files"]["alesp-norma-10261-1968.json"]
    assert len(metadata) == spec["bytes"]
    assert hashlib.sha256(metadata).hexdigest() == spec["sha256"]

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/json"}

        def geturl(self):
            return manifest["urls"]["metadata"]

    monkeypatch.setattr("app.sources.alesp.urllib.request.urlopen", lambda *_a, **_kw: Response(metadata))
    snapshot = fetch_alesp_history("https://www.al.sp.gov.br/norma/28593", "Lei", "10.261", 1968)
    assert snapshot.provenance["proposition"] == "PL 118/1968"
    assert len(snapshot.provenance["authors"]) == 1
    assert len(snapshot.relations) == 33
    assert snapshot.relations[0].event_url == "https://www.al.sp.gov.br/norma/212702"
    assert "Alteração" in snapshot.relations[0].relation
    assert "Trecho cadastrado" in snapshot.relations[0].evidence
