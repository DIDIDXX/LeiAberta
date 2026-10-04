from app.sources.planalto import parse_legal_nodes, source_note_for_law


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
