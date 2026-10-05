from http.client import IncompleteRead

import pytest

from app.sources import normas


def _detail_xml(*, remote_id="35691158", type_code="DEC-sn", number="",
                signed="21/04/2022", urn="urn:lex:br:federal:decreto:2022-04-21;seq-sf-0"):
    return (
        f"<Legislacao><documentos><documento id='{remote_id}'><identificacao>"
        f"<tipo>{type_code}</tipo><numero>{number}</numero><reedicao/>"
        f"<dataassinatura>{signed}</dataassinatura>"
        f"<urlDocumento>https://normas.leg.br/?urn={urn}</urlDocumento>"
        f"</identificacao></documento></documentos></Legislacao>"
    ).encode()


def test_senado_detail_fetch_validates_non_numbered_identity_by_remote_id(monkeypatch):
    body = _detail_xml()
    monkeypatch.setattr(
        normas, "_fetch",
        lambda url, **kwargs: (body, url, "application/xml; charset=utf-8"),
    )
    source_url = "https://legis.senado.leg.br/dadosabertos/legislacao/35691158"

    result = normas.fetch_senado_detail_xml(
        source_url, "Decreto não Numerado", "s/n", 2022,
    )

    assert result == body


def test_senado_aggregate_law_type_accepts_non_numbered_subtype(monkeypatch):
    body = _detail_xml(
        remote_id="573009", type_code="LEI-sn", signed="29/11/1832",
        urn="urn:lex:br:federal:lei:1832-11-29;seq-sf-0",
    )
    monkeypatch.setattr(
        normas, "_fetch",
        lambda url, **kwargs: (body, url, "application/xml; charset=utf-8"),
    )

    result = normas.fetch_senado_detail_xml(
        "https://legis.senado.leg.br/dadosabertos/legislacao/573009",
        "Lei", "s/n", 1832,
    )

    assert result == body


def test_senado_detail_fetch_rejects_remote_id_mismatch(monkeypatch):
    body = _detail_xml(remote_id="99999")
    monkeypatch.setattr(
        normas, "_fetch",
        lambda url, **kwargs: (body, url, "application/xml; charset=utf-8"),
    )

    with pytest.raises(normas.SourceDocumentUnavailable, match="identificador remoto solicitado"):
        normas.fetch_senado_detail_xml(
            "https://legis.senado.leg.br/dadosabertos/legislacao/35691158",
            "Decreto não Numerado", "s/n", 2022,
        )


def test_normas_fetch_retries_when_chunked_response_body_is_incomplete(monkeypatch):
    class Response:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self):
            self.read_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            self.read_count += 1
            if self.read_count == 1:
                raise IncompleteRead(b"partial", 5)
            return b"<html>complete text</html>"

        def geturl(self):
            return "https://normas.leg.br/text"

    response = Response()
    calls = []

    def open_url(_request, *, timeout):
        calls.append(timeout)
        return response

    monkeypatch.setattr(normas.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(normas.time, "sleep", lambda _delay: None)

    body, final_url, content_type = normas._fetch(
        "https://normas.leg.br/text", accept="text/html", timeout=7,
    )

    assert body == b"<html>complete text</html>"
    assert final_url == "https://normas.leg.br/text"
    assert content_type.startswith("text/html")
    assert calls == [7, 7]
