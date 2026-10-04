"""Conservative, repeatable diagnostics for an archived official document."""
from __future__ import annotations

from collections import Counter
import re

from bs4 import BeautifulSoup

from app.sources.planalto import ARTICLE_RE, canonical_article_number, decode_html, extract_paragraphs


def _component_heading(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value).strip(" .:").casefold()
    return normalized in {
        "ato das disposições constitucionais transitórias",
        "disposições constitucionais transitórias",
    }


def audit_archived_document(raw_body: bytes, nodes) -> dict:
    """Compare article markers in the stored source with parser output.

    This catches obvious omissions and flags attachments, but deliberately never
    certifies legal completeness: headings outside supported markup, tables,
    annexes and editorial scope still need review against the official source.
    """
    paragraphs = extract_paragraphs(raw_body)
    component = "body"
    source_ids: list[str] = []
    empty_ids: list[str] = []
    for paragraph, _raw in paragraphs:
        if _component_heading(paragraph):
            component = "adct"
            continue
        match = ARTICLE_RE.match(paragraph)
        if not match:
            continue
        number, text = match.groups()
        article_number = canonical_article_number(number)
        prefix = "adct:art" if component == "adct" else "art"
        node_id = f"{prefix}:{article_number}"
        source_ids.append(node_id)
        if not text.strip():
            empty_ids.append(node_id)

    parsed_ids = {node.node_id for node in nodes if node.node_type == "article"}
    source_unique = set(source_ids)
    parsed_missing = sorted(source_unique - parsed_ids)
    unsupported_or_unexpected = sorted(parsed_ids - source_unique)
    repeated = sorted(identifier for identifier, count in Counter(source_ids).items() if count > 1)

    soup = BeautifulSoup(decode_html(raw_body), "html.parser")
    pdf_links = []
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        if re.search(r"\.pdf(?:$|[?#])", href, re.I):
            pdf_links.append({"href": href, "label": " ".join(link.stripped_strings)[:160]})
    struck_passages = len(soup.find_all(["s", "strike", "del"])) + len(
        soup.find_all(style=re.compile(r"line-through", re.I))
    )
    extracted_characters = sum(len(text) for text, _raw in paragraphs)
    structured_characters = sum(len(node.text or "") for node in nodes)
    has_gaps = bool(parsed_missing or empty_ids)
    return {
        "audit_version": 1,
        "assessment": "gaps_detected" if has_gaps else "review_required",
        "completeness_certified": False,
        "reason": "A comparação de marcadores não substitui a revisão integral do documento e dos anexos oficiais.",
        "source_article_occurrences": len(source_ids),
        "source_unique_article_count": len(source_unique),
        "parsed_article_count": len(parsed_ids),
        "missing_parsed_articles": parsed_missing,
        "unexpected_parsed_articles": unsupported_or_unexpected,
        "repeated_source_article_markers": repeated,
        "empty_article_headings": sorted(set(empty_ids)),
        "source_paragraph_count": len(paragraphs),
        "source_extractable_characters": extracted_characters,
        "structured_node_count": len(nodes),
        "structured_node_characters": structured_characters,
        "detected_pdf_attachments": pdf_links,
        "struck_or_deleted_markup_count": struck_passages,
    }
