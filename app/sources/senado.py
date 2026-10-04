"""Read official federal norm relations from the Senate's open-data XML API."""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
from dataclasses import dataclass
from datetime import date

BASE_URL = "https://legis.senado.leg.br/dadosabertos"
TYPE_CODES = {
    "Lei": "LEI", "Lei Complementar": "LCP", "Medida Provisória": "MPV",
    "Emenda Constitucional": "EMC", "Decreto Legislativo": "DLG",
    "Resolução do Senado Federal": "RSF",
    "Decreto-Lei": "DEL", "Constituição": "CF",
}
CHANGE_WORDS = ("altera", "acréscimo", "acrescimo", "revogação", "revogacao", "restabelecimento")


@dataclass(frozen=True)
class SenateRelation:
    source_id: str
    device_ref: str
    relation: str
    event_label: str
    signed_at: date | None
    publication_date: date | None
    evidence: str


def _text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    return (child.text or "").strip() if child is not None else ""


def _date(value: str) -> date | None:
    if not value:
        return None
    from datetime import datetime
    try:
        return date.fromisoformat(value) if "-" in value else datetime.strptime(value, "%d/%m/%Y").date()
    except (ValueError, TypeError):
        return None


def fetch_norm_xml(law_type: str, number: str, year: int, *, timeout: int = 25) -> tuple[bytes, str]:
    type_code = TYPE_CODES.get(law_type)
    if not type_code:
        raise ValueError(f"Tipo normativo ainda não mapeado no catálogo Senado: {law_type}")
    # MPVs and a few historical norms distinguish multiple sequences with a
    # hyphen (e.g. 2.206-1). The list endpoint filters on the base number, so
    # resolve its returned records by the displayed official identity and then
    # fetch the unique record by Senate ID.
    normalized_display = re.sub(r"[^\d-]", "", number)
    normalized_number = normalized_display.split("-", 1)[0]
    if not normalized_number:
        raise ValueError("O catálogo Senado exige número para resolver esta norma.")
    headers = {"User-Agent": "LeiAberta/0.2 (+fontes oficiais)", "Accept": "application/xml"}
    list_url = f"{BASE_URL}/legislacao/lista?" + urllib.parse.urlencode({"tipo": type_code, "numero": normalized_number, "ano": year})
    request = urllib.request.Request(list_url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        listing = response.read()
        if response.status != 200 or len(listing) > 20_000_000:
            raise ValueError("Resposta inválida da lista legislativa do Senado.")
    try:
        root = ET.fromstring(listing)
    except ET.ParseError as exc:
        raise ValueError("O Senado retornou lista XML inválida.") from exc
    entries = root.findall("./documentos/documento")
    expected_key = normalized_display.casefold()
    matching = []
    for entry in entries:
        actual_year = _text(entry, "anoassinatura")
        actual_base = "".join(ch for ch in _text(entry, "numero") if ch.isdigit())
        official_name = _text(entry, "normaNome")
        displayed = re.search(r"\bn[º°o]?\s*([\d.]+(?:-\d+)?)\s+de\b", official_name, re.I)
        actual_display = re.sub(r"[^\d-]", "", displayed.group(1) if displayed else actual_base)
        if actual_year == str(year) and actual_base == normalized_number and actual_display.casefold() == expected_key:
            matching.append(entry)
    if len(matching) != 1:
        raise ValueError(f"Esperada uma identidade Senado {law_type} {number}/{year}; encontrados {len(matching)}.")
    entry = matching[0]
    source_id = (entry.get("id") or "").strip()
    if not source_id.isdigit():
        raise ValueError("A lista do Senado retornou identidade sem código numérico.")
    detail_url = f"{BASE_URL}/legislacao/{source_id}"
    request = urllib.request.Request(detail_url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.status != 200 or len(body) > 20_000_000:
            raise ValueError("Resposta inválida do detalhe legislativo do Senado.")
        return body, response.geturl()


def parse_relation_xml(body: bytes, *, expected_number: str | None = None) -> list[SenateRelation]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("O Senado retornou XML inválido.") from exc
    documents = root.findall("./documentos/documento")
    if len(documents) != 1:
        raise ValueError(f"Esperado um documento normativo; encontrados {len(documents)}.")
    document = documents[0]
    identity = document.find("identificacao")
    if identity is None:
        raise ValueError("O documento do Senado não inclui identificação normativa.")
    actual_number = "".join(ch for ch in _text(identity, "numero") if ch.isdigit())
    actual_reissue = "".join(ch for ch in _text(identity, "reedicao") if ch.isdigit())
    actual_display = f"{actual_number}-{actual_reissue}" if actual_reissue else actual_number
    expected_display = re.sub(r"[^\d-]", "", expected_number or "")
    if expected_display and actual_display != expected_display:
        raise ValueError(f"Identidade divergente na resposta do Senado: {actual_display} != {expected_display}.")

    relations: dict[tuple[str, str], SenateRelation] = {}
    for item in document.findall("./disps/disp"):
        device = _text(item, "nomeDispositivo")
        refs = item.findall("./refs/ref")
        for ref in refs:
            commentary = _text(ref, "comentario")
            if not any(word in commentary.casefold() for word in CHANGE_WORDS):
                continue
            source_id = _text(ref, "codNormaPosterior")
            label = _text(ref, "dispositivo")
            if not source_id or not label:
                continue
            signed = _date(_text(ref, "datAssinatura"))
            if signed is None:
                signed_match = re.search(r"\bde\s+(\d{2}/\d{2}/\d{4})\b", label)
                signed = _date(signed_match.group(1)) if signed_match else None
            published = _date(_text(ref, "datapub"))
            key = (source_id, device)
            relations[key] = SenateRelation(source_id, device, commentary, label, signed, published, f"{device}: {commentary}")
    return list(relations.values())
