"""Fetch Senate catalog entries' text from the Congress's Normas.leg.br API."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError

from bs4 import BeautifulSoup

from app.sources.senado import TYPE_CODES
from app.sources.planalto import article_label, canonical_article_number

SENATE_DATA_HOST = "legis.senado.leg.br"
NORMAS_HOST = "normas.leg.br"
MAX_SOURCE_BYTES = 20_000_000


class SourceDocumentUnavailable(ValueError):
    """The official catalog entry has no supported full-text representation."""


@dataclass(frozen=True)
class SenateDocument:
    body: bytes
    source_url: str
    representation: str
    version: str
    legal_value: str
    notice: str


@dataclass(frozen=True)
class NormasTextChange:
    node_id: str
    node_label: str
    operation: str
    before_text: str
    after_text: str
    changed_at: date
    source_law_label: str
    source_law_number: str
    source_law_year: int
    source_url: str
    source_urn: str


@dataclass(frozen=True)
class NormasHistorySnapshot:
    urn: str
    body: bytes
    source_url: str
    changes: list[NormasTextChange]


def _fetch(url: str, *, accept: str, timeout: int, maximum: int = MAX_SOURCE_BYTES) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": "LeiAberta/0.3 (+fontes oficiais)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(maximum + 1)
            if response.status != 200:
                raise SourceDocumentUnavailable(f"A fonte oficial respondeu HTTP {response.status}.")
            if len(body) > maximum:
                raise SourceDocumentUnavailable("A resposta oficial excede o limite de tamanho permitido.")
            return body, response.geturl(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        if exc.code in {400, 404, 410, 422}:
            raise SourceDocumentUnavailable(f"A fonte oficial não disponibiliza este documento (HTTP {exc.code}).") from exc
        raise


def _expected_identity(law_type: str, number: str, year: int) -> tuple[str, str, int]:
    type_code = TYPE_CODES.get(law_type)
    if not type_code:
        raise SourceDocumentUnavailable(f"O tipo {law_type!r} não está mapeado no catálogo do Senado.")
    display_number = re.sub(r"[^\d-]", "", number)
    if not display_number:
        raise SourceDocumentUnavailable("A identidade da norma não contém número reconhecível.")
    return type_code, display_number, year


def _document_urn(source_url: str, expected: tuple[str, str, int], *, timeout: int) -> str:
    return _urn_from_senado_xml(_fetch_senado_detail(source_url, expected, timeout=timeout), expected)


def _fetch_senado_detail(source_url: str, expected: tuple[str, str, int], *, timeout: int) -> bytes:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != SENATE_DATA_HOST or not re.fullmatch(
        r"/dadosabertos/legislacao/\d+", parsed.path
    ):
        raise SourceDocumentUnavailable("A URL de identidade não aponta para um registro individual do Senado.")
    body, final_url, _content_type = _fetch(source_url, accept="application/xml", timeout=timeout)
    if urllib.parse.urlparse(final_url).hostname != SENATE_DATA_HOST:
        raise SourceDocumentUnavailable("O Senado redirecionou para um domínio não reconhecido.")
    return body


def _urn_from_senado_xml(body: bytes, expected: tuple[str, str, int]) -> str:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise SourceDocumentUnavailable("O detalhe do Senado não veio em XML válido.") from exc
    documents = root.findall("./documentos/documento")
    if len(documents) != 1:
        raise SourceDocumentUnavailable(f"O detalhe do Senado não identifica um único documento ({len(documents)} encontrados).")
    identity = documents[0].find("identificacao")
    if identity is None:
        raise SourceDocumentUnavailable("O detalhe do Senado não inclui a identificação da norma.")

    type_code, expected_number, expected_year = expected
    actual_type = (identity.findtext("tipo") or "").strip().split("-", 1)[0]
    actual_base = "".join(char for char in (identity.findtext("numero") or "") if char.isdigit())
    actual_reissue = "".join(char for char in (identity.findtext("reedicao") or "") if char.isdigit())
    actual_number = f"{actual_base}-{actual_reissue}" if actual_reissue else actual_base
    date_text = (identity.findtext("dataassinatura") or "").strip()
    year_match = re.search(r"\b(\d{4})\b", date_text)
    actual_year = int(year_match.group(1)) if year_match else None
    if actual_type != type_code or actual_number != expected_number or actual_year != expected_year:
        raise SourceDocumentUnavailable(
            f"A identidade retornada pelo Senado diverge da norma pedida: "
            f"{actual_type} {actual_number}/{actual_year} != {type_code} {expected_number}/{expected_year}."
        )

    document_url = (identity.findtext("urlDocumento") or "").strip()
    document = urllib.parse.urlparse(document_url)
    if document.scheme != "https" or document.hostname != NORMAS_HOST or document.path != "/":
        raise SourceDocumentUnavailable("O registro do Senado não aponta para uma URN pública do Normas.leg.br.")
    urn = urllib.parse.parse_qs(document.query).get("urn", [""])[0]
    if not urn.startswith(("urn:lex:br:federal:", "urn:lex:br:senado.federal:")):
        raise SourceDocumentUnavailable("O registro não contém uma URN de legislação reconhecida.")
    return urn


def _fetch_normas_metadata(urn: str, *, timeout: int) -> tuple[dict, bytes, str]:
    if not urn.startswith(("urn:lex:br:federal:", "urn:lex:br:senado.federal:")):
        raise SourceDocumentUnavailable("A consulta não contém uma URN de legislação reconhecida.")
    metadata_url = "https://normas.leg.br/api/public/normas?" + urllib.parse.urlencode(
        {"urn": urn, "tipo_documento": "maior-detalhe"}
    )
    try:
        metadata_body, metadata_final_url, _content_type = _fetch(
            metadata_url, accept="application/json", timeout=timeout
        )
        metadata = json.loads(metadata_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceDocumentUnavailable("O Normas.leg.br retornou metadados JSON inválidos.") from exc
    if urllib.parse.urlparse(metadata_final_url).hostname != NORMAS_HOST or not isinstance(metadata, dict):
        raise SourceDocumentUnavailable("O Normas.leg.br retornou metadados de domínio ou formato inesperado.")
    returned_urn = metadata.get("legislationIdentifier") or metadata.get("urn")
    if returned_urn != urn:
        raise SourceDocumentUnavailable("Os metadados do Normas.leg.br não correspondem à URN solicitada.")
    return metadata, metadata_body, metadata_final_url


def fetch_normas_history(
    source_url: str,
    law_type: str,
    number: str,
    year: int,
    *,
    senate_detail_xml: bytes | None = None,
    timeout: int = 30,
) -> NormasHistorySnapshot:
    expected = _expected_identity(law_type, number, year)
    urn = _urn_from_senado_xml(senate_detail_xml, expected) if senate_detail_xml is not None else _document_urn(
        source_url, expected, timeout=timeout
    )
    metadata, body, metadata_url = _fetch_normas_metadata(urn, timeout=timeout)
    return NormasHistorySnapshot(urn, body, metadata_url, parse_normas_text_changes(metadata))


def _representations(metadata: dict) -> list[dict]:
    values = metadata.get("encoding", [])
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def fetch_senado_document(
    source_url: str,
    law_type: str,
    number: str,
    year: int,
    *,
    timeout: int = 30,
) -> SenateDocument:
    """Resolve one exact Senate identity to its best available full text.

    Normas.leg.br may provide an original transcription, an editorial current
    compilation, both, or no textual representation. The returned metadata
    retains the portal's legal-value classification so callers can label the
    result honestly.
    """
    expected = _expected_identity(law_type, number, year)
    senate_detail = _fetch_senado_detail(source_url, expected, timeout=timeout)
    urn = _urn_from_senado_xml(senate_detail, expected)
    metadata, _metadata_body, _metadata_url = _fetch_normas_metadata(urn, timeout=timeout)

    representations = [
        value for value in _representations(metadata)
        if value.get("contentUrl") and "text/html" in str(value.get("encodingFormat", "")).casefold()
    ]
    # A current compilation is the best reading when present. Otherwise, keep
    # the original publication as the body: a later erratum is a correction to
    # that publication, not a replacement for the complete legal text.
    def representation_rank(value: dict) -> tuple[int, int, int, str]:
        version = str(value.get("version") or "").casefold()
        name = str(value.get("name") or value.get("additionalType") or "").casefold()
        is_erratum = any(term in f"{name} {version}" for term in ("retificacao", "retificação", "erratum"))
        is_current = version == "current"
        is_original = version == "original" or any(term in name for term in ("publicacaooriginal", "publicação original", "original publication"))
        return (int(is_current), int(is_original and not is_erratum), int(not is_erratum),
                str(value.get("datePublished", "")))

    representations.sort(key=lambda value: (
        representation_rank(value),
        value.get("legislationLegalValue") == "OfficialLegalValue",
    ), reverse=True)
    if not representations:
        if expected[0] == "RSF":
            from app.sources.dou import fetch_senado_dou_document

            try:
                return fetch_senado_dou_document(senate_detail, number=number, year=year, timeout=timeout)
            except SourceDocumentUnavailable as exc:
                raise SourceDocumentUnavailable(
                    "O Normas.leg.br não tem texto e o leitor do DOU não forneceu correspondência exata: "
                    + str(exc)
                ) from exc
        raise SourceDocumentUnavailable("O registro oficial não possui uma representação HTML de texto integral.")
    chosen = representations[0]

    content = urllib.parse.urlparse(str(chosen["contentUrl"]))
    if content.scheme != "https" or content.hostname != NORMAS_HOST:
        raise SourceDocumentUnavailable("A representação textual aponta para um domínio não reconhecido.")
    if not re.fullmatch(r"/api/(?:public/)?binario/[0-9a-f-]+/texto", content.path, re.I):
        raise SourceDocumentUnavailable("A URL do texto não corresponde ao endpoint de conteúdo do Normas.leg.br.")
    content_url = urllib.parse.urlunparse(content._replace(path=content.path.replace("/api/binario/", "/api/public/binario/")))
    body, final_url, content_type = _fetch(content_url, accept="text/html", timeout=timeout)
    if urllib.parse.urlparse(final_url).hostname != NORMAS_HOST:
        raise SourceDocumentUnavailable("A fonte do texto redirecionou para um domínio não reconhecido.")
    if "text/html" not in content_type.casefold() or b"<html" not in body[:8192].lower():
        raise SourceDocumentUnavailable("A representação oficial não retornou HTML de texto integral.")

    representation = str(chosen.get("name") or chosen.get("additionalType") or "Texto legislativo")
    version = str(chosen.get("version") or "Original")
    legal_value = str(chosen.get("legislationLegalValue") or "UnclassifiedLegalValue")
    if legal_value != "OfficialLegalValue":
        notice = "Transcrição legislativa disponibilizada pelo Normas.leg.br e classificada pelo portal como valor jurídico não oficial."
    else:
        notice = "Representação classificada como valor jurídico oficial pelo Normas.leg.br."
    return SenateDocument(body, final_url, representation, version, legal_value, notice)


def _node_identity(identifier: str) -> tuple[str, str] | None:
    path = identifier.split("!", 1)[1].split(",", 1)[0] if "!" in identifier else ""
    match = re.match(r"^art(\d{1,3}(?:\.\d{3})+|\d+)([a-z])?((?:_.*)?)$", path, re.I)
    if not match:
        return None
    article_number = canonical_article_number(match.group(1) + (match.group(2) or ""))
    node_id = f"art:{article_number}"
    label = article_label(article_number)
    components = match.group(3).strip("_").split("_") if match.group(3) else []
    for component in components:
        if component == "cpt":
            continue
        paragraph = re.fullmatch(r"par(\d+)(u?)", component, re.I)
        if paragraph:
            value = "unico" if paragraph.group(2) else str(int(paragraph.group(1)))
            node_id += f".par:{value}"
            label += ", parágrafo único" if value == "unico" else f", § {value}º"
            continue
        inciso = re.fullmatch(r"inc(\d+)", component, re.I)
        if inciso:
            value = _roman(int(inciso.group(1)))
            node_id += f".inciso:{value}"
            label += f", inciso {value}"
            continue
        alinea = re.fullmatch(r"ali(\d+)|al([a-z])", component, re.I)
        if alinea:
            value = chr(ord("a") + int(alinea.group(1)) - 1) if alinea.group(1) else alinea.group(2).casefold()
            node_id += f".alinea:{value}"
            label += f", alínea {value}"
            continue
        return None
    return node_id, label


def _roman(value: int) -> str:
    if not 1 <= value <= 3999:
        return str(value)
    parts = []
    for amount, numeral in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                            (5, "V"), (4, "IV"), (1, "I")):
        while value >= amount:
            parts.append(numeral)
            value -= amount
    return "".join(parts)


def _source_identity(source: dict) -> tuple[str, str, int, str] | None:
    source_id = str(source.get("@id") or "")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(source_id).query)
    source_urn = query.get("urn", [""])[0]
    base_urn = re.split(r"[@!]", source_urn, maxsplit=1)[0]
    match = re.fullmatch(r"urn:lex:br:federal:[^:]+:(\d{4})-\d{2}-\d{2};(\d+(?:-\d+)?)", base_urn)
    if not match:
        return None
    year, raw_number = match.groups()
    base, separator, suffix = raw_number.partition("-")
    digits = re.sub(r"\D", "", base)
    groups = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    number = ".".join(reversed(groups)) + (separator + suffix if separator else "")
    return number, int(year), source_urn, source_id


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(value, "html.parser").get_text(" ", strip=True)).strip()


def parse_normas_text_changes(metadata: dict) -> list[NormasTextChange]:
    """Extract only dated, source-linked per-device changes with before/after text."""
    versions_by_node: dict[str, dict[str, dict]] = {}
    seen_versions: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            examples = value.get("workExample")
            if isinstance(examples, dict):
                examples = [examples]
            if isinstance(examples, list):
                for example in examples:
                    if not isinstance(example, dict) or not example.get("text"):
                        continue
                    identifier = str(example.get("legislationIdentifier") or "")
                    identity = _node_identity(identifier)
                    if not identity:
                        continue
                    stable = identifier + "\n" + str(example.get("text"))
                    if stable in seen_versions:
                        continue
                    seen_versions.add(stable)
                    node_id, node_label = identity
                    versions_by_node.setdefault(node_id, {})[stable] = {
                        "record": example, "node_label": node_label,
                    }
            for key, child in value.items():
                if key != "workExample":
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(metadata.get("hasPart", []))
    changes: dict[tuple[str, str, int], NormasTextChange] = {}
    for node_id, versions in versions_by_node.items():
        entries = list(versions.values())
        dated = []
        for item in entries:
            record = item["record"]
            try:
                when = date.fromisoformat(str(record.get("legislationDate") or ""))
            except ValueError:
                continue
            dated.append((when, record, item["node_label"]))
        dated.sort(key=lambda item: item[0])
        for changed_at, record, node_label in dated:
            operation = str(record.get("additionalType") or "")
            if operation not in {"Text_Change", "Insertion", "Repeal"}:
                continue
            source = record.get("legislationConsolidates")
            if isinstance(source, list):
                source = next((item for item in source if isinstance(item, dict)), {})
            if not isinstance(source, dict):
                continue
            source_identity = _source_identity(source)
            if not source_identity:
                continue
            source_number, source_year, source_urn, source_url = source_identity
            after_text = _text(str(record.get("text") or ""))
            previous = [
                (when, prior, label) for when, prior, label in dated
                if when < changed_at and prior.get("text")
            ]
            if operation == "Insertion":
                before_text = ""
            elif previous:
                _before_date, before_record, _before_label = max(previous, key=lambda item: item[0])
                before_text = _text(str(before_record.get("text") or ""))
            else:
                continue
            if operation == "Repeal" and not after_text:
                after_text = "(Revogado)"
            if not after_text or before_text == after_text:
                continue
            change = NormasTextChange(
                node_id=node_id, node_label=node_label, operation=operation,
                before_text=before_text, after_text=after_text, changed_at=changed_at,
                source_law_label=str(source.get("name") or source_number),
                source_law_number=source_number, source_law_year=source_year,
                source_url=source_url, source_urn=source_urn,
            )
            key = (node_id, source_number, source_year)
            prior = changes.get(key)
            if prior is None or change.changed_at > prior.changed_at:
                changes[key] = change
    return sorted(changes.values(), key=lambda change: (change.changed_at, change.node_id, change.source_law_number))
