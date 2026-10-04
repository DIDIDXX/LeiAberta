from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Law, LegalNode

ARTICLE_QUERY_RE = re.compile(r"\b(?:art(?:igo)?\.?\s*)(\d+[a-z]?)\b", re.I)
NUMBER_YEAR_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})+|\d{4,8})\s*(?:/|\s+de\s+|\s+)(\d{2,4})(?!\d)", re.I)
NUMBER_ONLY_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})+|\d{4,8})(?!\d)")


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\b(?:numero|no|n)\b|\bn[.]\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def parse_query(value: str) -> dict:
    article = ARTICLE_QUERY_RE.search(value)
    reference = NUMBER_YEAR_RE.search(value)
    number = year = None
    if reference:
        number = digits_only(reference.group(1))
        year_text = reference.group(2)
        year = int(year_text)
        if len(year_text) == 2:
            year += 2000 if year < 50 else 1900
    else:
        plain = NUMBER_ONLY_RE.search(value)
        if plain:
            number = digits_only(plain.group(1))
    cleaned = ARTICLE_QUERY_RE.sub(" ", value)
    if reference:
        cleaned = cleaned.replace(reference.group(0), " ")
    elif number:
        cleaned = re.sub(r"(?<!\d)" + re.escape(number) + r"(?!\d)", " ", cleaned)
    cleaned = re.sub(r"\b(lei|decreto|decreto lei|artigo|art|n|no|numero|de)\b", " ", cleaned, flags=re.I)
    return {
        "article": article.group(1).lower() if article else None,
        "number": number,
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


def search_laws(session: Session, query: str, limit: int = 10) -> dict:
    parsed = parse_query(query)
    normalized_query = normalize_query(query)
    laws = list(session.scalars(select(Law)))
    scored: list[tuple[int, float, Law, bool]] = []

    for law in laws:
        aliases = [law.title, *law.aliases, f"{law.law_type} {law.number}/{law.year}", f"{law.number}/{law.year}", law.number]
        normalized_aliases = {normalize_query(alias) for alias in aliases}
        normalized_number = digits_only(law.number)
        score = 0
        exact = False

        if parsed["number"] and parsed["number"] == normalized_number:
            score = 950 if parsed["year"] is None else (1100 if parsed["year"] == law.year else 0)
            exact = bool(score)
        if normalized_query in normalized_aliases:
            score = max(score, 900)
            exact = True
        terms = parsed["terms"]
        if terms:
            if terms in normalized_aliases:
                score = max(score, 900)
                exact = True
            else:
                best = max((_similarity(terms, alias) for alias in aliases), default=0.0)
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
            "description": law.description,
            "source_url": law.source_url,
            "materialization_status": law.materialization_status,
            "article": parsed["article"] if parsed["article"] else None,
            "suggestion": not exact and score < 820,
            "score": score,
        })
    return {"query": query, "parsed": parsed, "results": results, "suggestion": bool(results and results[0]["suggestion"])}
