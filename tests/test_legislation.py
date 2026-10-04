import hashlib
import json
from pathlib import Path

from app.sources.planalto import parse_legal_nodes, source_note_for_law
from app.sources.senado import parse_relation_xml


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
