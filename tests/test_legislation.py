import hashlib
import json
from pathlib import Path

from app.sources.planalto import parse_legal_nodes, source_note_for_law
from app.sources.senado import fetch_norm_xml, parse_relation_xml


def test_parser_assigns_stable_hierarchical_ids():
    html = """<html><body>
    <p>Art. 7º O tratamento de dados pessoais somente podera ser realizado nas seguintes hipoteses:</p>
    <p>I - mediante o fornecimento de consentimento pelo titular;</p>
    <p>§ 2º A forma de disponibilizacao devera observar os principios.</p>
    <p>II - para o cumprimento de obrigacao legal;</p>
    <p>a) quando exigido em lei;</p>
    </body></html>""".encode("windows-1252")
    nodes = parse_legal_nodes(html)
    by_id = {node.node_id: node for node in nodes}

    assert by_id["art:7"].node_type == "article"
    assert by_id["art:7.inciso:I"].parent_node_id == "art:7"
    assert by_id["art:7.par:2"].parent_node_id == "art:7"
    assert by_id["art:7.par:2.inciso:II"].parent_node_id == "art:7.par:2"
    assert by_id["art:7.par:2.inciso:II.alinea:a"].parent_node_id == "art:7.par:2.inciso:II"


def test_parser_treats_lowercase_o_after_article_number_as_ordinal():
    html = "<html><head><meta charset='utf-8'></head><body><p>Art. 2o. Texto jurídico.</p><p>Art. 3º Texto seguinte.</p></body></html>".encode("utf-8")
    articles = [node for node in parse_legal_nodes(html) if node.node_type == "article"]
    assert [(node.node_id, node.text) for node in articles] == [
        ("art:2", "Texto jurídico."),
        ("art:3", "Texto seguinte."),
    ]


def test_parser_preserves_article_suffix_after_ordinal_marker():
    html = "<html><head><meta charset='utf-8'></head><body><p>Art. 1º-A. Dispositivo com sufixo.</p></body></html>".encode()
    article = next(node for node in parse_legal_nodes(html) if node.node_type == "article")
    assert article.node_id == "art:1-a"
    assert article.label == "Art. 1º-A"
    assert article.text == "Dispositivo com sufixo."


def test_source_annotation_extracts_amending_law():
    assert source_note_for_law("(Incluído pela Lei nº 14.550, de 2023)") == ("14.550", 2023)


def test_parser_handles_thousands_scoped_adct_and_preserves_punctuation():
    html = """<html><body>
      <p>Art. 1º Texto do corpo constitucional.</p>
      <p>Art. 1.000-A. Texto completo termina com pontuação;</p>
      <p>ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS</p>
      <p>Art. 1º Texto do ADCT.</p>
    </body></html>""".encode("windows-1252")
    nodes = parse_legal_nodes(html)
    by_id = {node.node_id: node for node in nodes}
    assert by_id["art:1000-a"].text == "Texto completo termina com pontuação;"
    assert by_id["art:1"].text == "Texto do corpo constitucional."
    assert by_id["adct:art:1"].text == "Texto do ADCT."
    assert by_id["art:1"].node_id != by_id["adct:art:1"].node_id


def test_parser_records_duplicate_article_as_variant_instead_of_merging():
    html = b"<p>Art. 1. Primeira redacao.</p><p>Art. 1. Segunda redacao.</p>"
    nodes = parse_legal_nodes(html)
    first = next(node for node in nodes if node.node_id == "art:1")
    variant = next(node for node in nodes if node.node_type == "variant")
    assert first.text == "Primeira redacao."
    assert variant.text == "Segunda redacao."
    assert variant.parent_node_id == "art:1"


def test_parser_preserves_marked_repealed_text():
    html = b"<p>Art. 1. Texto atual e <del>trecho alterado</del>.</p>"
    article = next(node for node in parse_legal_nodes(html) if node.node_id == "art:1")
    assert "trecho alterado" in article.text
    assert "MARCADA COMO REVOGADA" in article.text


def test_senate_official_fixture_has_auditable_relations():
    fixture = Path(__file__).parent / "fixtures/official/senado-lgpd-13709-2018.xml"
    manifest = json.loads(fixture.with_suffix(".json").read_text())
    body = fixture.read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["sha256"]
    relations = parse_relation_xml(body, expected_number="13.709")
    assert len(relations) >= 100
    assert any(item.event_label == "Lei nº 13.853 de 08/07/2019" and item.signed_at.isoformat() == "2019-07-08" for item in relations)


def test_senado_resolves_hyphenated_measure_by_official_remote_id(monkeypatch):
    import io
    from urllib.parse import parse_qs, urlparse
    import app.sources.senado as senado

    fixture = Path(__file__).parent / "fixtures/official/senado-list-mpv2206-2001.xml"
    catalog = fixture.read_bytes()
    calls = []

    class Response(io.BytesIO):
        status = 200

        def geturl(self):
            return calls[-1]

    def fake_urlopen(request, timeout=25):
        url = request.full_url
        calls.append(url)
        return Response(catalog if "lista?" in url else b"<documento />")

    monkeypatch.setattr(senado.urllib.request, "urlopen", fake_urlopen)
    body, detail_url = fetch_norm_xml("Medida Provisória", "2.206-1", 2001)

    assert parse_qs(urlparse(calls[0]).query)["numero"] == ["2206"]
    assert detail_url.endswith("/legislacao/559113")
    assert body == b"<documento />"


def test_senado_validates_official_reissue_suffix():
    fixture = Path(__file__).parent / "fixtures/official/senado-mpv-2206-1-2001.xml"
    manifest = json.loads(fixture.with_suffix(".json").read_text())
    body = fixture.read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["sha256"]

    assert parse_relation_xml(body, expected_number="2.206-1") == []
    try:
        parse_relation_xml(body, expected_number="2.206")
    except ValueError as exc:
        assert "2206-1 != 2206" in str(exc)
    else:
        raise AssertionError("O parser aceitou a identidade errada da MPV com reedição.")


def test_senado_text_adapter_fetches_and_parses_official_normas_transcription(monkeypatch):
    import io
    import urllib.parse

    from app.sources.normas import fetch_senado_document

    fixture_dir = Path(__file__).parent / "fixtures/official"
    detail = (fixture_dir / "senado-mpv-2206-1-2001.xml").read_bytes()
    metadata_path = fixture_dir / "normas-mpv-2206-1-2001.json"
    metadata = metadata_path.read_bytes()
    body = (fixture_dir / "normas-mpv-2206-1-2001.html").read_bytes()
    manifest = json.loads((fixture_dir / "normas-mpv-2206-1-2001-manifest.json").read_text())
    assert hashlib.sha256(metadata).hexdigest() == manifest["metadata_sha256"]
    assert hashlib.sha256(body).hexdigest() == manifest["content_sha256"]

    urls = []

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/xml"}

        def geturl(self):
            return urls[-1]

    def fake_urlopen(request, timeout=25):
        url = request.full_url
        urls.append(url)
        if "/dadosabertos/legislacao/559113" in url:
            return Response(detail)
        if "/api/public/normas?" in url:
            return Response(metadata)
        if "/api/public/binario/" in url:
            response = Response(body)
            response.headers = {"Content-Type": "text/html; charset=utf-8"}
            return response
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr("app.sources.normas.urllib.request.urlopen", fake_urlopen)
    document = fetch_senado_document(
        "https://legis.senado.leg.br/dadosabertos/legislacao/559113",
        "Medida Provisória", "2.206-1", 2001,
    )
    nodes = parse_legal_nodes(document.body)

    assert document.version == "Original"
    assert document.legal_value == "UnofficialLegalValue"
    assert "valor jurídico não oficial" in document.notice
    assert document.source_url.endswith("/api/public/binario/cbd5aed7-ad41-4252-a2c2-c128bffde4a3/texto")
    assert any(node.node_id == "art:2" for node in nodes)
    assert not any(node.node_id == "art:2o" for node in nodes)
    assert "urn:lex:br:federal:medida.provisoria:2001-09-06;2206-1" in urllib.parse.unquote(urls[1])


def test_senado_text_adapter_prefers_original_over_later_erratum(monkeypatch):
    import io
    import json

    from app.sources.normas import fetch_senado_document

    detail = (Path(__file__).parent / "fixtures/official/senado-mpv-2206-1-2001.xml").read_bytes()
    original_url = "https://normas.leg.br/api/binario/11111111-1111-1111-1111-111111111111/texto"
    erratum_url = "https://normas.leg.br/api/binario/22222222-2222-2222-2222-222222222222/texto"
    metadata = json.dumps({
        "legislationIdentifier": "urn:lex:br:federal:medida.provisoria:2001-09-06;2206-1",
        "encoding": [
            {"contentUrl": erratum_url, "encodingFormat": "text/html", "version": "Intermediate",
             "name": "Retificacao", "datePublished": "2017-05-25", "legislationLegalValue": "UnofficialLegalValue"},
            {"contentUrl": original_url, "encodingFormat": "text/html", "version": "Original",
             "name": "PublicacaoOriginal", "datePublished": "2017-05-22", "legislationLegalValue": "UnofficialLegalValue"},
        ],
    }).encode()
    body_original = b"<html><body><p>Art. 1. Texto integral original.</p></body></html>"
    body_erratum = b"<html><body><p>RETIFICACAO na pagina 4, onde se le: assinatura, leia-se: outra.</p></body></html>"
    calls = []

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/xml"}

        def geturl(self):
            return calls[-1]

    def fake_urlopen(request, timeout=25):
        url = request.full_url
        calls.append(url)
        if "/dadosabertos/legislacao/559113" in url:
            return Response(detail)
        if "/api/public/normas?" in url:
            return Response(metadata)
        if "11111111-1111-1111-1111-111111111111" in url:
            response = Response(body_original)
            response.headers = {"Content-Type": "text/html; charset=utf-8"}
            return response
        if "22222222-2222-2222-2222-222222222222" in url:
            response = Response(body_erratum)
            response.headers = {"Content-Type": "text/html; charset=utf-8"}
            return response
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr("app.sources.normas.urllib.request.urlopen", fake_urlopen)
    document = fetch_senado_document(
        "https://legis.senado.leg.br/dadosabertos/legislacao/559113",
        "Medida Provisória", "2.206-1", 2001,
    )

    assert document.version == "Original"
    assert document.representation == "PublicacaoOriginal"
    assert b"Texto integral original" in document.body


def test_senado_accepts_its_federal_urn_namespace():
    from app.sources.normas import _expected_identity, _urn_from_senado_xml

    body = b"""<DetalheDocumento><documentos><documento><identificacao>
      <tipo>RSF</tipo><numero>8</numero><dataassinatura>31/05/2017</dataassinatura>
      <urlDocumento>https://normas.leg.br/?urn=urn:lex:br:senado.federal:resolucao:2017-05-31;8</urlDocumento>
    </identificacao></documento></documentos></DetalheDocumento>"""
    assert _urn_from_senado_xml(body, _expected_identity("Resolução do Senado Federal", "8", 2017)) == (
        "urn:lex:br:senado.federal:resolucao:2017-05-31;8"
    )


def test_parser_returns_no_false_articles_for_unrecognized_document_structure():
    html = b"<html><body><p>Clausula primeira. Texto do ato sem artigo.</p></body></html>"
    assert parse_legal_nodes(html) == []


def test_normas_history_extracts_exact_device_text_and_source_event():
    from app.sources.normas import parse_normas_text_changes

    fixture = Path(__file__).parent / "fixtures/official/normas-lgpd-history.json"
    manifest = json.loads(fixture.with_name("normas-lgpd-history-manifest.json").read_text())
    body = fixture.read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["sha256"]
    changes = parse_normas_text_changes(json.loads(body))

    change = next(item for item in changes if item.node_id == "art:7.inciso:VIII" and item.source_law_number == "13.853")
    assert change.operation == "Text_Change"
    assert change.changed_at.isoformat() == "2019-07-08"
    assert "profissionais da área da saúde" in change.before_text
    assert "exclusivamente" in change.after_text
    assert change.source_law_year == 2019
    assert "lei:2019-07-08;13853" in change.source_urn
