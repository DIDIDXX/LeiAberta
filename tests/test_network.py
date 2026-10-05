from urllib.error import HTTPError

import pytest

from app.sources import network


def test_open_with_retry_recovers_from_transient_503(monkeypatch):
    responses = [HTTPError("https://official.example", 503, "busy", {}, None), object()]
    calls = []

    def open_url(request, timeout):
        calls.append((request, timeout))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(network.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(network.time, "sleep", lambda _seconds: None)
    assert network.open_with_retry("request", timeout=3, attempts=3, base_delay=0) is not None
    assert len(calls) == 2


def test_open_with_retry_does_not_retry_permanent_http_errors(monkeypatch):
    calls = []

    def open_url(_request, timeout):
        calls.append(timeout)
        raise HTTPError("https://official.example", 404, "missing", {}, None)

    monkeypatch.setattr(network.urllib.request, "urlopen", open_url)
    with pytest.raises(HTTPError):
        network.open_with_retry("request", timeout=3, attempts=3, base_delay=0)
    assert calls == [3]
