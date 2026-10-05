"""Retrieve official legislation text and recorded relations from verified SAPL installations."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError

from bs4 import BeautifulSoup

from app.catalog_sync.sapl import DEFAULT_SAPL_INSTANCE, SaplInstance, sapl_instance_for_url
from app.sources.attachments import docx_to_html, pdf_to_html
from app.sources.history import OfficialRelation
from app.sources.network import open_with_retry
from app.sources.normas import SourceDocumentUnavailable

MAX_BYTES = 25_000_000
logger = logging.getLogger("leiaberta.sources.sapl")


@dataclass(frozen=True)
class SaplDocument:
    body: bytes
    source_url: str
    representation: str
    version: str = "Original"
    parsed_body: bytes | None = None
    raw_content_type: str = "application/pdf"
    legal_value: str = "UnclassifiedLegalValue"
    notice: str = "Texto obtido do SAPL oficial da Câmara Municipal; classificação jurídica não informada pelo portal."


@dataclass(frozen=True)
class SaplHistorySnapshot:
    body: bytes
    source_url: str
    relations: list[OfficialRelation]


def _instance_for_source_url(source_url: str) -> SaplInstance:
    try:
        return sapl_instance_for_url(source_url)
    except ValueError as exc:
        raise SourceDocumentUnavailable(str(exc)) from exc


def _fetch(url: str, *, accept: str, timeout: int) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "LeiAberta/1.0 (+fontes oficiais)",
    })
    try:
        with open_with_retry(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            if response.status != 200 or len(body) > MAX_BYTES:
                raise SourceDocumentUnavailable("A resposta oficial SAPL falhou ou excedeu o limite permitido.")
            return body, response.geturl(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        if exc.code in {400, 404, 410, 422}:
            raise SourceDocumentUnavailable(f"O SAPL não disponibiliza este documento (HTTP {exc.code}).") from exc
        raise


def _law_id(source_url: str) -> str:
    instance = _instance_for_source_url(source_url)
    parsed = urllib.parse.urlparse(source_url)
    match = re.fullmatch(r"/api/norma/normajuridica/(\d+)/?", parsed.path)
    if parsed.hostname != urllib.parse.urlparse(instance.host).hostname or not match or parsed.query:
        raise SourceDocumentUnavailable("A URL não identifica um registro individual de uma instalação SAPL verificada.")
    return match.group(1)


def _json(url: str, *, timeout: int, instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> tuple[dict, str]:
    body, final_url, content_type = _fetch(url, accept="application/json", timeout=timeout)
    location = urllib.parse.urlparse(final_url)
    if (location.scheme != "https"
            or location.hostname != urllib.parse.urlparse(instance.host).hostname):
        raise SourceDocumentUnavailable("A API SAPL redirecionou para domínio não reconhecido.")
    if "json" not in content_type.casefold() and not body.lstrip().startswith(b"{"):
        raise SourceDocumentUnavailable("A API SAPL não retornou JSON.")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceDocumentUnavailable("A ficha SAPL não contém JSON válido.") from exc
    if not isinstance(payload, dict):
        raise SourceDocumentUnavailable("A ficha SAPL não representa uma norma individual.")
    return payload, final_url


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _type_name(type_id: object, *, timeout: int, instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> str:
    if not str(type_id or "").isdigit():
        raise SourceDocumentUnavailable("A ficha SAPL não informa o tipo da norma.")
    payload, _ = _json(f"{instance.api}/tiponormajuridica/{int(type_id)}/",
                       timeout=timeout, instance=instance)
    name = str(payload.get("__str__") or payload.get("descricao") or "").strip()
    if not name:
        raise SourceDocumentUnavailable("O SAPL não reconhece o tipo cadastrado para esta norma.")
    return name


def _verified_detail(source_url: str, law_type: str, number: str, year: int, *, timeout: int) -> tuple[str, dict]:
    instance = _instance_for_source_url(source_url)
    requested_id = _law_id(source_url)
    detail, final_url = _json(f"{instance.api}/normajuridica/{requested_id}/",
                              timeout=timeout, instance=instance)
    parsed = urllib.parse.urlparse(final_url)
    returned_id = str(detail.get("id") or "")
    if (parsed.path.rstrip("/") != f"/api/norma/normajuridica/{requested_id}"
            or parsed.hostname != urllib.parse.urlparse(instance.host).hostname
            or returned_id != requested_id or detail.get("esfera_federacao") != "M"):
        raise SourceDocumentUnavailable("A ficha SAPL retornou outro registro ou outra esfera federativa.")
    actual_type = _type_name(detail.get("tipo"), timeout=timeout, instance=instance)
    actual_number = str(detail.get("numero") or "s/n").strip() or "s/n"
    signed = _date(detail.get("data"))
    expected_digits = re.sub(r"\D", "", number)
    actual_digits = re.sub(r"\D", "", actual_number)
    if (actual_type.casefold() != law_type.strip().casefold()
            or actual_digits != expected_digits or signed is None
            or int(detail.get("ano") or 0) != year):
        raise SourceDocumentUnavailable(
            f"A identidade SAPL diverge da norma pedida: {actual_type} {actual_number}/{signed.year if signed else '?'}.")
    return requested_id, detail


def _validated_media_url(value: object, *, instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> str:
    raw = str(value or "").strip()
    if raw.startswith((
        "/media/sapl/public/normajuridica/", "/sapl_documentos/norma_juridica/",
        "media/sapl/public/normajuridica/", "sapl_documentos/norma_juridica/",
    )):
        raw = urllib.parse.urljoin(f"{instance.host}/", raw)
    url = urllib.parse.urlparse(raw)
    valid_path = (url.path.startswith("/media/sapl/public/normajuridica/")
                  or url.path.startswith("/sapl_documentos/norma_juridica/"))
    if (url.scheme not in {"https", "http"}
            or url.hostname != urllib.parse.urlparse(instance.host).hostname
            or not valid_path or url.query or url.fragment):
        raise SourceDocumentUnavailable("A ficha SAPL não oferece anexo integral em endereço oficial reconhecido.")
    return urllib.parse.urlunparse(url._replace(scheme="https"))


def _validate_document_text(parsed_body: bytes, law_type: str, number: str, year: int) -> None:
    text = BeautifulSoup(parsed_body, "html.parser").get_text(" ", strip=True)
    digits = re.sub(r"\D", "", text)
    expected = re.sub(r"\D", "", number)
    normalize = lambda value: "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    if (len(text) < 80 or str(year) not in text
            or (expected and expected not in digits)
            or normalize(law_type.split()[0]) not in normalize(text)):
        raise SourceDocumentUnavailable("O anexo SAPL não contém texto legível com identidade compatível com a norma.")


def fetch_sapl_document(source_url: str, law_type: str, number: str, year: int, *, timeout: int = 30) -> SaplDocument:
    instance = _instance_for_source_url(source_url)
    _remote_id, detail = _verified_detail(source_url, law_type, number, year, timeout=timeout)
    media_url = detail.get("texto_integral")
    if not media_url:
        # The public API occasionally serves a ficha before its attachment
        # metadata is visible through the same endpoint. Re-read once before
        # classifying a law as having no official full text.
        _remote_id, detail = _verified_detail(source_url, law_type, number, year, timeout=timeout)
        media_url = detail.get("texto_integral")
    try:
        text_url = _validated_media_url(media_url, instance=instance)
    except SourceDocumentUnavailable:
        logger.warning("sapl_document_attachment_unavailable remote_id=%s value=%r", _remote_id, media_url)
        raise
    try:
        body, final_url, content_type = _fetch(text_url, accept="application/pdf, text/html, application/vnd.openxmlformats-officedocument.wordprocessingml.document", timeout=timeout)
    except SourceDocumentUnavailable:
        raise
    except Exception as exc:
        raise SourceDocumentUnavailable(f"O anexo integral SAPL não pôde ser lido: {exc}") from exc
    location = urllib.parse.urlparse(final_url)
    valid_path = (location.path.startswith("/media/sapl/public/normajuridica/")
                  or location.path.startswith("/sapl_documentos/norma_juridica/"))
    if (location.scheme != "https"
            or location.hostname != urllib.parse.urlparse(instance.host).hostname
            or not valid_path):
        raise SourceDocumentUnavailable("O anexo SAPL redirecionou para domínio ou caminho não reconhecido.")
    content_type = content_type.casefold()
    if body.startswith(b"%PDF-") or "application/pdf" in content_type:
        parsed_body = pdf_to_html(body)
        media_type = "application/pdf"
    elif "html" in content_type and b"<html" in body[:8192].lower():
        parsed_body = body
        media_type = "text/html"
    elif "wordprocessingml.document" in content_type or final_url.casefold().endswith(".docx"):
        parsed_body = docx_to_html(body)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise SourceDocumentUnavailable(f"O SAPL publicou um formato integral não suportado ({content_type or 'desconhecido'}).")
    _validate_document_text(parsed_body, law_type, number, year)
    return SaplDocument(body=body, source_url=final_url,
                        representation=f"Texto integral oficial disponibilizado pelo SAPL de {instance.municipality}"
                        + (" (PDF com extração/OCR quando necessário)" if media_type == "application/pdf" else ""),
                        parsed_body=parsed_body, raw_content_type=content_type or media_type,
                        notice=(f"Texto obtido do SAPL oficial da Câmara Municipal de {instance.municipality}; "
                                "classificação jurídica não informada pelo portal."))


def _paged_relations(field: str, remote_id: str, *, timeout: int,
                     instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> list[dict]:
    rows: list[dict] = []
    page_size = 100
    first_url = f"{instance.api}/normarelacionada/?" + urllib.parse.urlencode(
        {field: remote_id, "page_size": page_size, "page": 1})
    first, _ = _json(first_url, timeout=timeout, instance=instance)
    pagination = first.get("pagination") or {}
    total, pages = pagination.get("total_entries"), pagination.get("total_pages")
    if not isinstance(total, int) or not isinstance(pages, int) or pages < 1:
        raise SourceDocumentUnavailable("O histórico SAPL não informa paginação verificável.")
    for page in range(1, pages + 1):
        payload = first if page == 1 else _json(
            f"{instance.api}/normarelacionada/?" + urllib.parse.urlencode(
                {field: remote_id, "page_size": page_size, "page": page}),
            timeout=timeout, instance=instance)[0]
        current = payload.get("pagination") or {}
        if current.get("total_entries") != total or current.get("page") != page:
            raise SourceDocumentUnavailable("O total de relações SAPL mudou durante a paginação.")
        result = payload.get("results")
        if not isinstance(result, list):
            raise SourceDocumentUnavailable("O SAPL retornou relações em formato inesperado.")
        rows.extend(item for item in result if isinstance(item, dict))
    if len(rows) != total:
        raise SourceDocumentUnavailable(f"O histórico SAPL retornou {len(rows)} de {total} relações.")
    return rows


def _relation_type(type_id: object, *, timeout: int,
                   instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> str:
    if isinstance(type_id, dict):
        return str(type_id.get("__str__") or type_id.get("descricao") or "").strip()
    if not str(type_id or "").isdigit():
        return "Relação oficial"
    payload, _ = _json(f"{instance.api}/tipovinculonormajuridica/{int(type_id)}/",
                       timeout=timeout, instance=instance)
    return str(payload.get("__str__") or payload.get("descricao") or "Relação oficial").strip()


def fetch_sapl_history(source_url: str, law_type: str, number: str, year: int, *, timeout: int = 30) -> SaplHistorySnapshot:
    instance = _instance_for_source_url(source_url)
    remote_id, _detail = _verified_detail(source_url, law_type, number, year, timeout=timeout)
    incoming = _paged_relations("norma_principal", remote_id, timeout=timeout, instance=instance)
    outgoing = _paged_relations("norma_relacionada", remote_id, timeout=timeout, instance=instance)
    records: dict[tuple[str, str], OfficialRelation] = {}
    incoming_url = f"{instance.api}/normarelacionada/?" + urllib.parse.urlencode(
        {"norma_principal": remote_id, "page_size": 100})
    outgoing_url = f"{instance.api}/normarelacionada/?" + urllib.parse.urlencode(
        {"norma_relacionada": remote_id, "page_size": 100})
    serialized = {"queries": {"incoming": incoming_url, "outgoing": outgoing_url},
                  "incoming": incoming, "outgoing": outgoing}
    relation_types: dict[str, str] = {}
    for direction, rows in (("norma_principal", incoming), ("norma_relacionada", outgoing)):
        for row in rows:
            principal = str(row.get("norma_principal") or "").strip()
            related = str(row.get("norma_relacionada") or "").strip()
            if not principal.isdigit() or not related.isdigit():
                continue
            if (direction == "norma_principal" and principal != remote_id
                    or direction == "norma_relacionada" and related != remote_id):
                continue
            other = related if direction == "norma_principal" else principal
            type_key = json.dumps(row.get("tipo_vinculo"), ensure_ascii=False, sort_keys=True)
            if type_key not in relation_types:
                relation_types[type_key] = _relation_type(row.get("tipo_vinculo"), timeout=timeout,
                                                          instance=instance)
            relation_type = relation_types[type_key]
            summary = str(row.get("resumo") or "").strip()
            # Related records are official references only. The API does not
            # provide before/after device text, so no textual diff is inferred.
            event_url = f"{instance.api}/normajuridica/{other}/"
            event_label = summary or str(row.get("__str__") or f"Norma relacionada SAPL #{other}").strip()
            signed_at = None
            publication = None
            source_id = str(row.get("id") or f"{principal}:{related}")
            relation = OfficialRelation(
                source_id=f"sapl:{source_id}", device_ref="", relation=relation_type[:120],
                event_label=event_label[:240], event_url=event_url, signed_at=signed_at,
                publication_date=publication,
                evidence=(f"Relação oficial SAPL: {relation_type}. Norma vinculada ID {other}. "
                          + (f"Resumo cadastrado: {summary}" if summary else "")
                          + " O cadastro não fornece redações anterior e posterior para comparação.")[:4000],
            )
            records[(relation.source_id, relation.event_url)] = relation
    body = json.dumps(serialized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    source_url = f"{instance.api}/normarelacionada/?norma_principal={remote_id}"
    return SaplHistorySnapshot(body=body, source_url=source_url,
                               relations=sorted(records.values(), key=lambda item: item.event_label))
