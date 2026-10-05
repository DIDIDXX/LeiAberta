from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session, load_only

from app.models import Law, LegalNode

ARTICLE_QUERY_RE = re.compile(r"\b(?:art(?:igo)?\.?\s*)(\d+[a-z]?)\b", re.I)
NUMBER_YEAR_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})*|\d{4,8})(?:-(\d+))?\s*(?:/|\s+de\s+|\s+)(\d{2,4})(?!\d)", re.I)
NUMBER_ONLY_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})+|\d{4,8})(?:-(\d+))?(?!\d)")


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\b(?:numero|no|n)\b|\bn[.]\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def _query_type(value: str) -> str | None:
    normalized = normalize_query(value)
    for phrase, canonical in (
        ("lei complementar", "Lei Complementar"),
        ("emenda constitucional", "Emenda Constitucional"),
        ("medida provisoria", "Medida Provisória"),
        ("decreto legislativo", "Decreto Legislativo"),
        ("resolucao do senado federal", "Resolução do Senado Federal"),
        ("resolucao senado", "Resolução do Senado Federal"),
        ("decreto lei", "Decreto-Lei"),
        ("constituicao", "Constituição"),
        (r"\blc\b", "Lei Complementar"),
        (r"\blcp\b", "Lei Complementar"),
        (r"\bmpv\b", "Medida Provisória"),
        (r"\bemc\b", "Emenda Constitucional"),
        (r"\bec\b", "Emenda Constitucional"),
        (r"\bdlg\b", "Decreto Legislativo"),
        (r"\brsf\b", "Resolução do Senado Federal"),
    ):
        if phrase.startswith("\\b"):
            if re.search(phrase, normalized):
                return canonical
        elif phrase in normalized:
            return canonical
    if re.search(r"\blei\b", normalized):
        return "Lei"
    return None


def parse_query(value: str) -> dict:
    article = ARTICLE_QUERY_RE.search(value)
    reference = NUMBER_YEAR_RE.search(value)
    number = year = number_sequence = None
    if reference:
        number = digits_only(reference.group(1))
        number_sequence = reference.group(2)
        year_text = reference.group(3)
        year = int(year_text)
        if len(year_text) == 2:
            year += 2000 if year < 50 else 1900
    else:
        plain = NUMBER_ONLY_RE.search(value)
        if plain:
            number = digits_only(plain.group(1))
            number_sequence = plain.group(2)
    cleaned = ARTICLE_QUERY_RE.sub(" ", value)
    if reference:
        cleaned = cleaned.replace(reference.group(0), " ")
    elif number:
        cleaned = re.sub(r"(?<!\d)" + re.escape(number) + r"(?!\d)", " ", cleaned)
    cleaned = re.sub(r"\b(lei|decreto|decreto lei|artigo|art|n|no|numero|de)\b", " ", cleaned, flags=re.I)
    return {
        "article": article.group(1).lower() if article else None,
        "number": number,
        "number_sequence": number_sequence,
        "law_type": _query_type(value),
        "year": year,
        "terms": normalize_query(cleaned),
    }


def _similarity(query: str, candidate: str) -> float:
    q = normalize_query(query)
    c = normalize_query(candidate)
    if not q or not c:
        return 0.0
    ratio = SequenceMatcher(None, q, c).ratio()
    q_tokens, c_tokens = q.split(), c.split()
    if q_tokens and all(any(SequenceMatcher(None, token, item).ratio() >= 0.72 for item in c_tokens) for token in q_tokens):
        ratio = max(ratio, 0.7)
    return ratio


def _adjacent_transpositions(value: str) -> set[str]:
    if not 4 <= len(value) <= 20 or not value.isalpha():
        return set()
    variants = set()
    for index in range(len(value) - 1):
        if value[index] == value[index + 1]:
            continue
        chars = list(value)
        chars[index], chars[index + 1] = chars[index + 1], chars[index]
        variants.add("".join(chars))
    return variants


def _display_number(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    groups = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    return ".".join(reversed(groups))


def search_laws(session: Session, query: str, limit: int = 10) -> dict:
    parsed = parse_query(query)
    normalized_query = normalize_query(query)
    candidate_query = select(Law)
    if parsed["law_type"]:
        candidate_query = candidate_query.where(Law.law_type == parsed["law_type"])
    description_loaded = False
    if parsed["number"]:
        display_number = _display_number(parsed["number"])
        number_forms = {parsed["number"], display_number}
        if parsed["number_sequence"]:
            number_forms.add(f"{display_number}-{parsed['number_sequence']}")
            number_forms.add(f"{parsed['number']}-{parsed['number_sequence']}")
        if not parsed["number_sequence"]:
            exact = candidate_query.where(or_(Law.number.in_(number_forms),
                                              Law.number.like(f"{display_number}-%")))
        else:
            exact = candidate_query.where(Law.number.in_(number_forms))
        if parsed["year"]:
            exact = exact.where(Law.year == parsed["year"])
        laws = list(session.scalars(exact.limit(500)))
        description_loaded = bool(laws)
    else:
        laws = []
    terms = parsed["terms"]
    if not laws and terms:
        needle = f"%{terms}%"
        transposed_terms = _adjacent_transpositions(terms) if len(terms.split()) == 1 else set()
        search_patterns = [needle, *(f"%{variant}%" for variant in transposed_terms)]
        token_conditions = []
        for token in terms.split():
            if len(token) >= 4:
                token_needle = f"%{token}%"
                token_conditions.extend((Law.title.ilike(token_needle), Law.description.ilike(token_needle),
                                         cast(Law.aliases, String).ilike(token_needle)))
        candidate_conditions = [condition for pattern in search_patterns for condition in (
            Law.title.ilike(pattern), Law.description.ilike(pattern),
            cast(Law.aliases, String).ilike(pattern),
        )]
        candidates = candidate_query.where(or_(*candidate_conditions, *token_conditions)).limit(1000)
        laws = list(session.scalars(candidates))
        description_loaded = bool(laws)
    if not laws and terms.split():
        first_token = terms.split()[0]
        prefix = first_token[:2] if len(first_token) <= 4 else first_token[:3]
        prefix_needle = f"%{prefix}%"
        laws = list(session.scalars(candidate_query.where(or_(
            Law.title.ilike(prefix_needle), cast(Law.aliases, String).ilike(prefix_needle),
        )).limit(1000)))
        description_loaded = bool(laws)
    if parsed["number"] and not laws and not terms:
        return {"query": query, "parsed": parsed, "results": [], "suggestion": False}
    # Fuzzy typo suggestions are for the curated, high-demand catalog. Scanning
    # every catalog row here made a typo query load hundreds of thousands of
    # laws and run Python SequenceMatcher repeatedly.
    if not laws:
        laws = list(session.scalars(candidate_query.where(Law.hot.is_(True)).options(load_only(
            Law.slug, Law.jurisdiction, Law.state_code, Law.municipality, Law.law_type, Law.number,
            Law.year, Law.title, Law.status, Law.aliases, Law.source_url, Law.materialization_status,
            Law.hot,
        )).order_by(Law.last_hydrated_at.desc().nullslast(), Law.title).limit(2_000)))
    scored: list[tuple[int, float, Law, bool]] = []

    for law in laws:
        aliases = [law.title, *law.aliases, f"{law.law_type} {law.number}/{law.year}", f"{law.number}/{law.year}", law.number]
        normalized_aliases = {normalize_query(alias) for alias in aliases}
        number_match = re.match(r"^(.*?)(?:-(\d+))?$", law.number)
        law_number_base = digits_only(number_match.group(1)) if number_match else digits_only(law.number)
        law_number_sequence = number_match.group(2) if number_match else None
        score = 0
        exact = False

        if parsed["number"] and parsed["number"] == law_number_base and (
            parsed["number_sequence"] is None or parsed["number_sequence"] == law_number_sequence
        ):
            score = 950 if parsed["year"] is None else (1100 if parsed["year"] == law.year else 0)
            exact = bool(score)
        if normalized_query in normalized_aliases:
            score = max(score, 900)
            exact = True
        terms = parsed["terms"]
        if any(normalize_query(alias) in _adjacent_transpositions(terms) for alias in aliases):
            score = max(score, 840)
        if terms:
            if terms in normalized_aliases:
                score = max(score, 900)
                exact = True
            elif terms in normalize_query(law.description or "" if description_loaded else ""):
                score = max(score, 780)
            else:
                best = max((_similarity(terms, alias) for alias in aliases), default=0.0)
                query_tokens = terms.split()
                description_tokens = normalize_query(law.description or "" if description_loaded else "").split()
                if query_tokens and all(any(_similarity(token, word) >= 0.72 for word in description_tokens)
                                        for token in query_tokens):
                    best = max(best, 0.72)
                if terms in normalize_query(law.title):
                    score = max(score, 820)
                elif any(terms in normalize_query(alias) for alias in law.aliases):
                    score = max(score, 760)
                elif best >= 0.56:
                    score = max(score, int(best * 700))

        article_match = False
        if parsed["article"]:
            article_node = f"art:{parsed['article']}"
            article_match = session.scalar(
                select(LegalNode.id).where(LegalNode.law_slug == law.slug, LegalNode.node_id == article_node).limit(1)
            ) is not None
            if article_match:
                if terms:
                    if score:
                        score += 260
                else:
                    score = max(score, 600)
                    exact = True
            elif score:
                score += 30

        if score:
            scored.append((score, _similarity(terms or query, law.title), law, exact))

    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2].hot), reverse=True)
    if not parsed["article"] and any(entry[3] for entry in scored):
        # Once an exact identity/title/alias exists, typo candidates must not
        # clutter the exact search result page.
        scored = [entry for entry in scored if entry[3]]
    descriptions = {}
    if not description_loaded and scored:
        top_slugs = [entry[2].slug for entry in scored[:limit]]
        descriptions = dict(session.execute(select(Law.slug, Law.description).where(Law.slug.in_(top_slugs))).all())
    results = []
    for score, similarity, law, exact in scored[:limit]:
        results.append({
            "slug": law.slug,
            "title": law.title,
            "law_type": law.law_type,
            "number": law.number,
            "year": law.year,
            "jurisdiction": law.jurisdiction,
            "status": law.status,
            "description": law.description if description_loaded else descriptions.get(law.slug, ""),
            "source_url": law.source_url,
            "materialization_status": law.materialization_status,
            "article": parsed["article"] if parsed["article"] else None,
            "suggestion": not exact,
            "score": score,
        })
    return {"query": query, "parsed": parsed, "results": results, "suggestion": bool(results and results[0]["suggestion"])}
