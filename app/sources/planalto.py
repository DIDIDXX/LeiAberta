from __future__ import annotations

import re
import urllib.request
import codecs
from dataclasses import dataclass

from bs4 import BeautifulSoup

PARSER_VERSION = "2.1"
ARTICLE_RE = re.compile(r"^Art\.\s*((?:\d{1,3}(?:\.\d{3})+|\d+)(?:[A-NP-Za-np-z]|-(?:\d+|[A-Za-z]))?(?:\s*(?:º|°|o))?(?:-[A-Za-z0-9]+)?)\s*[.\-–—]?\s*(.*)$", re.I)
PARAGRAPH_RE = re.compile(r"^(§\s*(\d+)\s*(?:º|°|o)?|Parágrafo único)\s*[.\-–—]?\s*(.*)$", re.I)
INCISO_RE = re.compile(r"^([IVXLCDM]{1,8})\s*[-–—]\s*(.+)$", re.I)
ALINEA_RE = re.compile(r"^([a-z])\)\s*(.+)$", re.I)
NOTE_RE = re.compile(r"\s*\((?=(?:Redação dada|Incluído|Revogado|Vigência|Vide|Acrescentado)[^)]{0,260}(?:Lei|Medida Provisória|Emenda Constitucional))[^)]*\)\s*(?:Vigência)?", re.I)
BOUNDARY_RE = re.compile(
    r"(?=(?:Art\.\s*\d+[A-Za-z]?(?:-[A-Za-z])?\s*(?:º|°|o)?\s*[.\-–—]?|"
    r"§\s*\d+\s*(?:º|°|o)?|Parágrafo único|[IVXLCDM]{1,8}\s*[-–—]|[a-z]\)\s))",
    re.I,
)


@dataclass
class ParsedNode:
    node_id: str
    parent_node_id: str | None
    node_type: str
    label: str
    text: str
    source_note: str
    order_index: int


def fetch_official_html(url: str) -> tuple[bytes, str]:
    candidates = [url]
    if url.startswith("http://"):
        candidates.insert(0, "https://" + url[len("http://"):])
    last_error: Exception | None = None
    for candidate in candidates:
        request = urllib.request.Request(
            candidate,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
                markup_probe = body.lower().replace(b"\x00", b"")[:4096]
                if response.status != 200 or b"<html" not in markup_probe:
                    raise ValueError("A fonte oficial não retornou um documento HTML válido.")
                if "text/html" not in content_type.lower() and b"<html" not in markup_probe:
                    raise ValueError("Formato de fonte oficial não reconhecido.")
                return body, response.geturl()
        except Exception as exc:
            last_error = exc
    raise last_error or ValueError("Fonte oficial indisponível.")


def detect_raw_format(body: bytes) -> str:
    if body.startswith(b"\xff\xfe"):
        return "text/html; charset=utf-16le"
    if body.startswith(b"\xfe\xff"):
        return "text/html; charset=utf-16be"
    if body.startswith(b"\xef\xbb\xbf"):
        return "text/html; charset=utf-8"
    match = re.search(rb"<meta[^>]+charset\s*=\s*['\"]?([a-z0-9._-]+)", body[:4096], re.I)
    if match:
        try:
            return f"text/html; charset={codecs.lookup(match.group(1).decode('ascii')).name}"
        except (LookupError, UnicodeDecodeError):
            pass
    return "text/html; charset=iso-8859-1"


def decode_html(body: bytes) -> str:
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        return body.decode("utf-16", errors="replace")
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig", errors="replace")
    match = re.search(rb"<meta[^>]+charset\s*=\s*['\"]?([a-z0-9._-]+)", body[:4096], re.I)
    if match:
        try:
            return body.decode(codecs.lookup(match.group(1).decode("ascii")).name, errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return body.decode("windows-1252", errors="replace")


def extract_paragraphs(html: bytes) -> list[tuple[str, str]]:
    soup = BeautifulSoup(decode_html(html), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(["s", "strike", "del"]):
        tag.insert_before(" ⟦REDAÇÃO MARCADA COMO REVOGADA NA FONTE: ")
        tag.insert_after("⟧ ")
        tag.unwrap()
    for tag in soup.find_all(style=re.compile(r"line-through", re.I)):
        tag.insert_before(" ⟦REDAÇÃO MARCADA COMO REVOGADA NA FONTE: ")
        tag.insert_after("⟧ ")
        tag.attrs.pop("style", None)

    paragraphs: list[tuple[str, str]] = []
    for element in soup.find_all(["p", "li"]):
        value = " ".join(element.stripped_strings)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            paragraphs.append((value, element.get_text(" ", strip=True)))
    if not paragraphs:
        text = soup.get_text("\n", strip=True)
        paragraphs = [(re.sub(r"\s+", " ", line).strip(), line) for line in text.splitlines() if line.strip()]
    return paragraphs


def _strip_source_note(value: str) -> tuple[str, str]:
    notes = [match.group(0).strip() for match in NOTE_RE.finditer(value)]
    text = NOTE_RE.sub("", value)
    text = re.sub(r"\s+Vigência\s*$", "", text, flags=re.I).strip()
    return text, " ".join(notes)


def _split_candidates(value: str) -> list[str]:
    # Planalto publishes each structural unit in its own paragraph. Keeping the
    # paragraph boundary intact avoids splitting a Roman numeral such as "II"
    # into a false "I" item during zero-width regex splitting.
    value = value.strip()
    return [value] if value else []


def canonical_article_number(value: str) -> str:
    """Normalize the article marker while preserving legal suffixes such as 1-A."""
    without_ordinal = re.sub(r"(?<=\d)\s*(?:º|°|o)(?=\s*(?:-|$))", "", value, flags=re.I)
    return re.sub(r"[.\s]", "", without_ordinal).casefold()


def article_label(value: str) -> str:
    number = canonical_article_number(value)
    if "-" in number:
        base, suffix = number.split("-", 1)
        return f"Art. {base}º-{suffix.upper()}"
    return f"Art. {number}º"


def parse_legal_nodes(html: bytes) -> list[ParsedNode]:
    """Extract stable article, paragraph, item and subitem identifiers from a Planalto HTML text."""
    nodes: list[ParsedNode] = []
    nodes_by_id: dict[str, ParsedNode] = {}
    current_article: str | None = None
    current_parent: str | None = None
    current_item: str | None = None
    component = "body"
    order = 0

    def add(node_id: str, parent: str | None, kind: str, label: str, text: str, note: str = "") -> None:
        nonlocal order
        clean = re.sub(r"\s+", " ", text).strip()
        if not clean and kind != "article":
            return
        if node_id in nodes_by_id:
            existing = nodes_by_id[node_id]
            if clean == existing.text:
                existing.source_note = " ".join(part for part in (existing.source_note, note) if part)
                return
            # Preserve duplicate source passages as separately reviewable variants instead of
            # silently concatenating them into an unrelated article.
            variant_id = f"{node_id}.source-variant:{order + 1}"
            parent_id = node_id if kind == "article" else parent
            order += 1
            nodes.append(ParsedNode(variant_id, parent_id, "variant", f"{label} — redação alternativa na fonte",
                                    clean, "Passagem repetida no mesmo documento oficial; escopo precisa de revisão. " + note, order))
            return
        order += 1
        node = ParsedNode(node_id, parent, kind, label, clean, note, order)
        nodes.append(node)
        nodes_by_id[node_id] = node

    paragraphs = extract_paragraphs(html)
    normalized = [re.sub(r"\s+", " ", paragraph).strip(" .:").casefold() for paragraph, _raw in paragraphs]
    adct_headings = [i for i, value in enumerate(normalized)
                     if value in {"ato das disposições constitucionais transitórias", "disposições constitucionais transitórias"}]
    adct_start = max(adct_headings, default=-1)
    for paragraph_index, (paragraph, _raw) in enumerate(paragraphs):
        if paragraph_index == adct_start:
            component = "adct"
            current_article = None
            current_parent = None
            current_item = None
            continue
        for candidate in _split_candidates(paragraph):
            candidate, note = _strip_source_note(candidate)
            if not candidate:
                if note and nodes and nodes[-1].node_id == current_parent:
                    nodes[-1].source_note = (nodes[-1].source_note + " " + note).strip()
                continue
            article = ARTICLE_RE.match(candidate)
            if article:
                printed_number, body = article.groups()
                number = canonical_article_number(printed_number)
                prefix = "adct:art" if component == "adct" else "art"
                current_article = f"{prefix}:{number.lower()}"
                current_parent = current_article
                current_item = None
                add(current_article, None, "article", article_label(printed_number), body, note)
                continue
            if current_article is None:
                continue
            section = PARAGRAPH_RE.match(candidate)
            if section:
                marker, number, body = section.groups()
                if marker.lower().startswith("parágrafo"):
                    node_id = f"{current_article}.par:unico"
                    label = "Parágrafo único"
                else:
                    node_id = f"{current_article}.par:{int(number)}"
                    label = f"§ {int(number)}º"
                current_parent = node_id
                current_item = None
                add(node_id, current_article, "paragraph", label, body, note)
                continue
            inciso = INCISO_RE.match(candidate)
            if inciso:
                number, body = inciso.groups()
                parent = current_parent or current_article
                node_id = f"{parent}.inciso:{number.upper()}"
                current_item = node_id
                add(node_id, parent, "item", number.upper(), body, note)
                continue
            alinea = ALINEA_RE.match(candidate)
            if alinea:
                letter, body = alinea.groups()
                parent = current_item or current_parent or current_article
                node_id = f"{parent}.alinea:{letter.lower()}"
                add(node_id, parent, "subitem", letter.lower(), body, note)
                continue
            parent_node = nodes_by_id.get(current_parent or "")
            if parent_node and candidate not in parent_node.text:
                parent_node.text = (parent_node.text + " " + candidate).strip()

    return nodes


def source_note_for_law(note: str) -> tuple[str, int] | None:
    match = re.search(r"Lei\s+n[º°o]?\s*([\d.]+)\s*,?\s*de\s*(\d{4})", note, re.I)
    if not match:
        return None
    return match.group(1), int(match.group(2))
