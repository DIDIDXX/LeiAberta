from app.models import LegalNode
from app.search import normalize_query, parse_query, search_laws


def test_normalizes_accents_numbers_and_punctuation():
    assert normalize_query("Lei nº 13.709 / 2018") == "lei 13 709 2018"


def test_parses_number_and_two_digit_year():
    parsed = parse_query("Lei nº 13.709/18")
    assert parsed["number"] == "13709"
    assert parsed["year"] == 2018


def test_exact_number_year_wins_and_typo_suggests_lgpd(db_session, add_law):
    law = add_law()
    db_session.add(law)
    db_session.commit()

    exact = search_laws(db_session, "13709/18")
    fuzzy = search_laws(db_session, "LGDP")

    assert exact["results"][0]["slug"] == "13709-2018"
    assert exact["results"][0]["score"] >= 1000
    assert fuzzy["results"][0]["title"] == "Lei Geral de Proteção de Dados Pessoais"
    assert fuzzy["suggestion"] is True


def test_article_query_returns_matching_law(db_session, add_law):
    law = add_law()
    db_session.add(law)
    db_session.flush()
    db_session.add(LegalNode(
        law_slug=law.slug, version_id=1, node_id="art:7", parent_node_id=None,
        node_type="article", label="Art. 7º", text="Texto do artigo.", order_index=1,
    ))
    db_session.commit()

    result = search_laws(db_session, "art 7 LGDP")
    assert result["parsed"]["article"] == "7"
    assert result["results"][0]["slug"] == law.slug


def test_article_only_keeps_ambiguous_norms_as_multiple_options(db_session, add_law):
    first = add_law(slug="2848-1940", title="Código Penal", number="2.848", year=1940, aliases=["CP"])
    second = add_law(slug="5172-1966", title="Código Tributário Nacional", number="5.172", year=1966, aliases=["CTN"])
    db_session.add_all([first, second])
    db_session.flush()
    db_session.add_all([
        LegalNode(law_slug=first.slug, version_id=1, node_id="art:121", parent_node_id=None,
                  node_type="article", label="Art. 121", text="Texto penal.", order_index=1),
        LegalNode(law_slug=second.slug, version_id=2, node_id="art:121", parent_node_id=None,
                  node_type="article", label="Art. 121", text="Texto tributário.", order_index=1),
    ])
    db_session.commit()

    result = search_laws(db_session, "art. 121")
    assert {item["slug"] for item in result["results"]} == {first.slug, second.slug}
