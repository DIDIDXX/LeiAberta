from app.audit import audit_archived_document
from app.sources.planalto import ParsedNode


def test_document_audit_detects_missing_articles_and_pdf_attachments():
    body = """<html><head><meta charset='utf-8'></head><body>
    <p>Art. 1º Texto presente.</p>
    <p>Art. 2º </p>
    <a href='/anexo.pdf?download=1'>Anexo I</a>
    <del>Redação suprimida.</del>
    </body></html>""".encode()
    nodes = [ParsedNode("art:1", None, "article", "Art. 1º", "Texto presente.", "", 1)]

    result = audit_archived_document(body, nodes)

    assert result["assessment"] == "gaps_detected"
    assert result["completeness_certified"] is False
    assert result["missing_parsed_articles"] == ["art:2"]
    assert result["empty_article_headings"] == ["art:2"]
    assert result["detected_pdf_attachments"][0]["href"] == "/anexo.pdf?download=1"
    assert result["struck_or_deleted_markup_count"] == 1


def test_document_audit_keeps_adct_article_ids_in_a_separate_component():
    body = "<html><head><meta charset='utf-8'></head><body><p>Art. 1º Constituição.</p><p>ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS</p><p>Art. 1º Transição.</p></body></html>".encode()
    nodes = [
        ParsedNode("art:1", None, "article", "Art. 1º", "Constituição.", "", 1),
        ParsedNode("adct:art:1", None, "article", "Art. 1º", "Transição.", "", 2),
    ]

    result = audit_archived_document(body, nodes)

    assert result["source_unique_article_count"] == 2
    assert result["missing_parsed_articles"] == []
    assert result["unexpected_parsed_articles"] == []
    assert result["completeness_certified"] is False
