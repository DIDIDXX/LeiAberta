from datetime import datetime, timedelta, timezone

from app.models import LegalNode, Law
from app.search import _adjacent_transpositions, normalize_query, parse_query, search_laws


def test_normalizes_accents_numbers_and_punctuation():
    assert normalize_query("Lei nº 13.709 / 2018") == "lei 13 709 2018"


def test_parses_number_and_two_digit_year():
    parsed = parse_query("Lei nº 13.709/18")
    assert parsed["number"] == "13709"
    assert parsed["number_sequence"] is None
    assert parsed["year"] == 2018


def test_adjacent_transposition_candidates_cover_common_typo():
    assert "lgpd" in _adjacent_transpositions("lgdp")


def test_exact_number_year_wins_and_typo_suggests_lgpd(db_session, add_law):
    law = add_law(aliases=["LGPD", "lei geral de dados"])
    db_session.add(law)
    db_session.commit()

    exact = search_laws(db_session, "13709/18")
    alias = search_laws(db_session, "lei geral de dados")
    fuzzy = search_laws(db_session, "LGDP")

    assert exact["results"][0]["slug"] == "13709-2018"
    assert exact["results"][0]["score"] >= 1000
    assert alias["results"][0]["slug"] == "13709-2018"
    assert alias["suggestion"] is False
    assert fuzzy["results"][0]["title"] == "Lei Geral de Proteção de Dados Pessoais"
    assert fuzzy["suggestion"] is True


def test_fuzzy_candidates_prioritize_recent_hot_laws_over_alphabetical_catalog(db_session, add_law):
    older = datetime.now(timezone.utc) - timedelta(days=30)
    fillers = [Law(
        slug=f"catalog-{index}", jurisdiction="federal", law_type="Lei", number=str(index + 1),
        year=2000, title=f"A catalog law {index:04d}", description="", status="Não verificado",
        aliases=[], source_name="Senado", source_url="https://senado.example",
        fetch_url="https://senado.example", hot=True, materialization_status="catalog",
        coverage={}, last_hydrated_at=older,
    ) for index in range(2_001)]
    lgpd = add_law(aliases=["LGPD"], title="Lei Geral de Proteção de Dados Pessoais")
    lgpd.last_hydrated_at = datetime.now(timezone.utc)
    db_session.add_all([*fillers, lgpd])
    db_session.commit()

    result = search_laws(db_session, "LGDP")

    assert result["results"][0]["slug"] == "13709-2018"
    assert result["suggestion"] is True


def test_transposed_alias_wins_over_literal_false_positive(db_session, add_law):
    distractor = Law(
        slug="false-lgdp-match", jurisdiction="federal", law_type="Lei", number="1", year=2000,
        title="LGDP reference without the LGPD alias", description="", status="Não verificado",
        aliases=[], source_name="Senado", source_url="https://senado.example",
        fetch_url="https://senado.example", hot=False, materialization_status="catalog", coverage={},
    )
    target = add_law(aliases=["LGPD"])
    db_session.add_all([distractor, target])
    db_session.commit()

    result = search_laws(db_session, "LGDP")

    assert result["results"][0]["slug"] == "13709-2018"
    assert result["suggestion"] is True


def test_hyphenated_official_number_resolves_the_exact_measure_sequence(db_session):
    from app.models import Law

    common = dict(jurisdiction="federal", law_type="Medida Provisória", year=2001,
                  description="", status="Não verificado", aliases=[], source_name="Senado",
                  source_url="https://senado.example", fetch_url="https://senado.example",
                  hot=False, materialization_status="catalog", coverage={})
    db_session.add_all([
        Law(slug="mpv-2206", number="2.206", title="Medida Provisória nº 2.206", **common),
        Law(slug="mpv-2206-1", number="2.206-1", title="Medida Provisória nº 2.206-1", **common),
    ])
    db_session.commit()

    exact = search_laws(db_session, "MPV 2.206-1/2001")
    base = search_laws(db_session, "MPV 2.206/2001")

    assert exact["parsed"]["number"] == "2206"
    assert exact["parsed"]["number_sequence"] == "1"
    assert [item["slug"] for item in exact["results"]] == ["mpv-2206-1"]
    assert {item["slug"] for item in base["results"]} == {"mpv-2206", "mpv-2206-1"}


def test_short_number_with_year_is_not_treated_as_a_fuzzy_title_query(db_session):
    from app.models import Law

    db_session.add(Law(slug="lcp-237-2026", jurisdiction="federal", law_type="Lei Complementar",
                       number="237", year=2026, title="Lei Complementar nº 237 de 15/09/2026",
                       description="", status="Não verificado", aliases=[], source_name="Senado",
                       source_url="https://senado.example", fetch_url="https://senado.example",
                       hot=False, materialization_status="catalog", coverage={}))
    db_session.commit()

    result = search_laws(db_session, "Lei Complementar 237/2026")

    assert result["parsed"]["number"] == "237"
    assert result["parsed"]["year"] == 2026
    assert result["parsed"]["law_type"] == "Lei Complementar"
    assert [item["slug"] for item in result["results"]] == ["lcp-237-2026"]


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
    assert result["suggestion"] is False
