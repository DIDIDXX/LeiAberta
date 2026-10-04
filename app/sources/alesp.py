"""Official ALESP metadata and legislative text retrieval."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from urllib.error import HTTPError

from app.catalog_sync.alesp import ALESP_API, ALESP_MAX_BYTES, ALESP_WEB
from app.sources.history import OfficialRelation


@dataclass(frozen=True)
class AlespDocument:
    body: bytes
    source_url: str
    representation: str
    version: str
    legal_value: str = "UnclassifiedLegalValue"
    notice: str = "Texto obtido do repositório oficial da Assembleia Legislativa do Estado de São Paulo."


@dataclass(frozen=True)
class AlespHistorySnapshot:
    body: bytes
    source_url: str
    relations: list[OfficialRelation]
    provenance: dict


def _fetch(url: str, *, accept: str, timeout: int) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "LeiAberta/0.3 (+fontes oficiais)",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(ALESP_MAX_BYTES + 1)
            if response.status != 200 or len(body) > ALESP_MAX_BYTES:
                raise ValueError("A resposta ALESP falhou ou excede o limite de tamanho permitido.")
            return body, response.geturl(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise ValueError(f"A fonte ALESP respondeu HTTP {exc.code}.") from exc


def _source_id(source_url: str) -> str:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme != "https":
        raise ValueError("A ficha ALESP precisa usar HTTPS.")
    if parsed.hostname == "www.al.sp.gov.br":
        match = re.fullmatch(r"/norma/(\d+)/?", parsed.path)
    elif parsed.hostname == "baleg-api-prd.al.sp.gov.br":
        match = re.fullmatch(r"/normas/(\d+)/?", parsed.path)
    else:
        match = None
    if not match:
        raise ValueError("A URL não identifica uma ficha de norma ALESP conhecida.")
    return match.group(1)


def _official_number(record: dict) -> str:
    title = str(record.get("nomeNorma") or "")
    match = re.search(r"\bn[º°o]?\s*([\d.]+(?:-\d+)?)\s*,?\s*(?:de|,)", title, re.I)
    return match.group(1).strip(".") if match else str(record.get("nuNorma") or "s/n").strip()


def _flat_number(value: str) -> str:
    return re.sub(r"[^\d-]", "", value)


def fetch_alesp_document(
    source_url: str,
    law_type: str,
    number: str,
    year: int,
    *,
    timeout: int = 30,
) -> AlespDocument:
    from app.sources.normas import SourceDocumentUnavailable

    remote_id = _source_id(source_url)
    metadata_url = f"{ALESP_API}/normas/{remote_id}"
    try:
        metadata_body, metadata_final_url, _metadata_type = _fetch(
            metadata_url, accept="application/json", timeout=timeout,
        )
        metadata = json.loads(metadata_body)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceDocumentUnavailable(f"A ficha ALESP não pôde ser lida: {exc}") from exc
    metadata_location = urllib.parse.urlparse(metadata_final_url)
    if metadata_location.scheme != "https" or metadata_location.hostname != "baleg-api-prd.al.sp.gov.br":
        raise SourceDocumentUnavailable("A ficha ALESP redirecionou para domínio não reconhecido.")
    if not isinstance(metadata, dict) or str(metadata.get("idNorma")) != remote_id:
        raise SourceDocumentUnavailable("A ficha ALESP não corresponde ao identificador remoto solicitado.")
    signed = None
    if metadata.get("data"):
        try:
            signed = datetime.strptime(str(metadata["data"]), "%d/%m/%Y").date()
        except ValueError:
            pass
    actual_number = _official_number(metadata)
    if (str(metadata.get("tipo") or "").strip().casefold() != law_type.strip().casefold()
            or _flat_number(actual_number) != _flat_number(number) or signed is None or signed.year != year):
        raise SourceDocumentUnavailable(
            f"A identidade ALESP diverge da norma pedida: {metadata.get('tipo')} {actual_number}/{signed.year if signed else None}."
        )

    updated_url = metadata.get("urlTextoAtualizado") or metadata.get("urlIntegraAtualizada")
    original_url = (metadata.get("urlIntegraListaPesquisa") or metadata.get("urlIntegraOriginal")
                    or metadata.get("urlTextoOriginal"))
    candidates = [(str(updated_url), "Current")] if updated_url else []
    if original_url:
        candidates.append((str(original_url), "Original"))
    selected = None
    for candidate, version in candidates:
        parsed = urllib.parse.urlparse(candidate)
        if (parsed.scheme == "https" and parsed.hostname == "www.al.sp.gov.br"
                and parsed.path.startswith("/repositorio/legislacao/") and not parsed.path.lower().endswith(".pdf")):
            selected = (candidate, version)
            break
    if not selected:
        raise SourceDocumentUnavailable("A ficha ALESP não oferece HTML de texto integral num caminho oficial reconhecido.")
    content_url, version = selected
    try:
        body, final_url, content_type = _fetch(content_url, accept="text/html", timeout=timeout)
    except ValueError as exc:
        raise SourceDocumentUnavailable(f"O texto ALESP não pôde ser lido: {exc}") from exc
    location = urllib.parse.urlparse(final_url)
    if (location.scheme != "https" or location.hostname != "www.al.sp.gov.br"
            or not location.path.startswith("/repositorio/legislacao/")):
        raise SourceDocumentUnavailable("O texto ALESP redirecionou para domínio ou caminho não reconhecido.")
    if "text/html" not in content_type.casefold() or b"<html" not in body[:8192].lower():
        raise SourceDocumentUnavailable("O repositório ALESP não retornou HTML de texto integral.")
    label = "Texto atualizado no repositório ALESP" if version == "Current" else "Texto original no repositório ALESP"
    return AlespDocument(body=body, source_url=final_url, representation=label, version=version)


def _source_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            continue
    return None


def fetch_alesp_history(
    source_url: str,
    law_type: str,
    number: str,
    year: int,
    *,
    timeout: int = 30,
) -> AlespHistorySnapshot:
    """Read the Assembly's official annotation feed for amendments and repeals."""
    from bs4 import BeautifulSoup

    from app.sources.normas import SourceDocumentUnavailable

    remote_id = _source_id(source_url)
    metadata_url = f"{ALESP_API}/normas/{remote_id}"
    try:
        body, final_url, _content_type = _fetch(metadata_url, accept="application/json", timeout=timeout)
        metadata = json.loads(body)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceDocumentUnavailable(f"O histórico ALESP não pôde ser lido: {exc}") from exc
    location = urllib.parse.urlparse(final_url)
    if (location.scheme != "https" or location.hostname != "baleg-api-prd.al.sp.gov.br"
            or location.path != f"/normas/{remote_id}" or not isinstance(metadata, dict)
            or str(metadata.get("idNorma")) != remote_id):
        raise SourceDocumentUnavailable("A resposta ALESP não corresponde à ficha de norma solicitada.")
    try:
        signed = datetime.strptime(str(metadata.get("data") or ""), "%d/%m/%Y").date()
    except ValueError as exc:
        raise SourceDocumentUnavailable("A ficha ALESP não informa uma data de assinatura válida.") from exc
    actual_number = _official_number(metadata)
    if (str(metadata.get("tipo") or "").strip().casefold() != law_type.strip().casefold()
            or _flat_number(actual_number) != _flat_number(number) or signed.year != year):
        raise SourceDocumentUnavailable(
            f"A identidade ALESP diverge da norma pedida: {metadata.get('tipo')} {actual_number}/{signed.year}."
        )

    changes = []
    for group_name in ("anotacoesAlteracao", "anotacaoOutras"):
        group = metadata.get(group_name)
        if not isinstance(group, list):
            continue
        for index, annotation in enumerate(group):
            if not isinstance(annotation, dict):
                continue
            relation_type = str(annotation.get("tipoAnotacao") or "").strip()
            if not any(word in relation_type.casefold() for word in ("alter", "revog", "restaur", "repristin", "retific")):
                continue
            annotator_id = str(annotation.get("idNormaAnotadora") or "").strip()
            annotation_id = str(annotation.get("idAnotacao") or f"{annotator_id}-{index}").strip()
            if not annotator_id.isdigit() or not annotation_id.isdigit():
                continue
            annotation_url = str(annotation.get("anotadoraDsUrl") or "").strip()
            parsed_annotation_url = urllib.parse.urlparse(annotation_url)
            if (parsed_annotation_url.scheme != "https" or parsed_annotation_url.hostname != "www.al.sp.gov.br"
                    or parsed_annotation_url.path.rstrip("/") != f"/norma/{annotator_id}"):
                annotation_url = f"{ALESP_WEB}/norma/{annotator_id}"
            event_label = str(annotation.get("nomeNorma") or "").strip()
            if not event_label:
                event_label = " ".join(part for part in (
                    str(annotation.get("anotadoraTpNorma") or "").strip(),
                    str(annotation.get("anotadoraNuNorma") or "").strip(),
                ) if part)
            raw_text = str(annotation.get("anotadoraTxNorma") or "")
            excerpt = " ".join(BeautifulSoup(raw_text, "html.parser").get_text(" ", strip=True).split())
            evidence = f"ALESP: anotação oficial classificada como {relation_type}."
            if excerpt:
                evidence += f" Trecho cadastrado: {excerpt[:1600]}"
            changes.append(OfficialRelation(
                source_id=f"alesp:{annotation_id}", device_ref="", relation=relation_type,
                event_label=event_label[:240], event_url=annotation_url,
                signed_at=_source_date(annotation.get("anotadoraDtNorma") or annotation.get("dataOrdenacao")),
                publication_date=_source_date(annotation.get("anotadoraDtPublicacao")), evidence=evidence[:4000],
            ))
    unique = {(item.source_id, item.event_url): item for item in changes}
    changes = sorted(unique.values(), key=lambda item: item.signed_at or date.min, reverse=True)
    authors = metadata.get("autores") if isinstance(metadata.get("autores"), list) else []
    provenance = {
        "proposition_id": str(metadata.get("idPropositura") or "") or None,
        "proposition": str(metadata.get("nomePropositura") or "") or None,
        "authors": authors,
    }
    return AlespHistorySnapshot(body=body, source_url=final_url, relations=changes, provenance=provenance)
