"""Exact-identity fallback to original Senate acts in the official DOU reader."""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.error import HTTPError

from bs4 import BeautifulSoup
from app.sources.network import open_with_retry


DOU_HOST = "www.in.gov.br"
MAX_DOU_BYTES = 20_000_000


def _flat(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isascii() and character.isalnum())


def _fetch(url: str, *, accept: str, timeout: int) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": "LeiAberta/0.3 (+fontes oficiais)"},
    )
    try:
        with open_with_retry(request, timeout=timeout) as response:
            body = response.read(MAX_DOU_BYTES + 1)
            if response.status != 200:
                raise ValueError(f"O DOU respondeu HTTP {response.status}.")
            if len(body) > MAX_DOU_BYTES:
                raise ValueError("A resposta do DOU excede o limite de tamanho permitido.")
            return body, response.geturl(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise ValueError(f"O DOU não disponibilizou a publicação (HTTP {exc.code}).") from exc


def _publication_metadata(detail_xml: bytes, *, number: str, year: int) -> tuple[str, str, str, str]:
    from app.sources.normas import SourceDocumentUnavailable

    try:
        root = ET.fromstring(detail_xml)
    except ET.ParseError as exc:
        raise SourceDocumentUnavailable("O detalhe do Senado não veio em XML válido para a busca no DOU.") from exc
    documents = root.findall("./documentos/documento")
    if len(documents) != 1:
        raise SourceDocumentUnavailable("O detalhe do Senado não identifica uma única publicação para conferência no DOU.")
    document = documents[0]
    identity = document.find("identificacao")
    if identity is None:
        raise SourceDocumentUnavailable("O detalhe do Senado não inclui identidade para conferência no DOU.")
    actual_type = (identity.findtext("tipo") or "").strip().split("-", 1)[0]
    actual_number = "".join(character for character in (identity.findtext("numero") or "") if character.isdigit())
    date_text = (identity.findtext("dataassinatura") or "").strip()
    try:
        actual_year = datetime.strptime(date_text, "%d/%m/%Y").year
    except ValueError:
        actual_year = None
    expected_number = "".join(character for character in number if character.isdigit())
    if actual_type != "RSF" or actual_number != expected_number or actual_year != year:
        raise SourceDocumentUnavailable(
            "A identidade do Senado não corresponde à Resolução do Senado pedida para conferência no DOU."
        )

    publications = []
    for item in document.findall("./publicacoes/publicacao"):
        if (item.findtext("tipo") or "").strip() != "PUB":
            continue
        source = (item.findtext("fonte") or "").strip()
        source_code = (item.findtext("siglaFonte") or "").strip()
        published = (item.findtext("data") or "").strip()
        page = (item.findtext("pagina") or "").strip()
        description = (item.findtext("dispositivo") or "").strip()
        if "diário oficial da união" not in source.casefold() or not source_code.startswith("DOU-"):
            continue
        try:
            parsed_date = datetime.strptime(published, "%d/%m/%Y")
        except ValueError:
            continue
        if not page.isdigit() or not 1 <= int(page) <= 10000:
            continue
        publications.append((published, str(int(page)), description, parsed_date.strftime("%d-%m-%Y")))
    original = [item for item in publications if "publicação original" in item[2].casefold()]
    choices = original or publications
    unique = list(dict.fromkeys(choices))
    if len(unique) != 1:
        raise SourceDocumentUnavailable(
            "O registro do Senado não identifica uma única publicação original do DOU com data e página verificáveis."
        )
    published, page, _description, date_url = unique[0]
    ementa = (document.findtext("ementa") or "").strip()
    if len(_flat(ementa)) < 40:
        raise SourceDocumentUnavailable("A ementa do Senado não é suficiente para validar a identidade no DOU.")
    return date_url, published, page, ementa


def fetch_senado_dou_document(
    detail_xml: bytes,
    *,
    number: str,
    year: int,
    timeout: int = 30,
):
    """Fetch the exact original Senate resolution from its DOU date and page."""
    from app.sources.normas import SenateDocument, SourceDocumentUnavailable

    date_url, published, page, ementa = _publication_metadata(detail_xml, number=number, year=year)
    reader_url = "https://www.in.gov.br/leiturajornal?" + urllib.parse.urlencode(
        {"data": date_url, "secao": "DO1"}
    )
    try:
        reader_body, reader_final_url, _content_type = _fetch(reader_url, accept="text/html", timeout=timeout)
    except ValueError as exc:
        raise SourceDocumentUnavailable(f"O leitor diário do DOU não pôde ser consultado: {exc}") from exc
    reader = urllib.parse.urlparse(reader_final_url)
    if reader.scheme != "https" or reader.hostname != DOU_HOST or reader.path != "/leiturajornal":
        raise SourceDocumentUnavailable("O leitor diário redirecionou para uma URL que não pertence ao DOU.")
    page_html = BeautifulSoup(reader_body, "html.parser")
    params = page_html.find("script", id="params")
    if not params or not params.string:
        raise SourceDocumentUnavailable("O leitor diário do DOU não apresentou o índice verificável da edição.")
    try:
        edition = json.loads(params.string)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SourceDocumentUnavailable("O índice da edição do DOU não veio em JSON válido.") from exc
    if edition.get("dateUrl") != date_url or edition.get("section") != "DO1":
        raise SourceDocumentUnavailable("O DOU retornou uma edição diferente da data/seção informada pelo Senado.")
    articles = edition.get("jsonArray")
    if not isinstance(articles, list):
        raise SourceDocumentUnavailable("O DOU não retornou a lista de atos da edição.")

    expected_number = "".join(character for character in number if character.isdigit())
    # NFKD maps the ordinal marker in "Nº" to "o" in the flattened heading.
    expected_heading = f"resolucaono{expected_number}de{year}"
    expected_ementa = _flat(ementa)
    candidates = []
    for item in articles:
        if not isinstance(item, dict):
            continue
        if item.get("artType") != "Resolução do Senado Federal":
            continue
        if str(item.get("numberPage", "")).strip() != page:
            continue
        if str(item.get("pubDate", "")).strip() != published:
            continue
        if "Atos do Senado Federal" not in (item.get("hierarchyStr") or ""):
            continue
        flattened = _flat(str(item.get("content") or ""))
        # The reader's index truncates the preview after a few hundred
        # characters. Verify the complete ementa against the fetched article
        # below; the index is used only to find the exact typed/page/heading row.
        if expected_heading not in flattened:
            continue
        url_title = str(item.get("urlTitle") or "")
        if not re.fullmatch(r"[a-z0-9-]+", url_title):
            continue
        candidates.append(url_title)
    if len(candidates) != 1:
        raise SourceDocumentUnavailable(
            f"A edição oficial do DOU não contém uma correspondência única para RSF {number}/{year} na página {page}."
        )

    article_url = f"https://www.in.gov.br/web/dou/-/{candidates[0]}"
    try:
        body, final_url, _content_type = _fetch(article_url, accept="text/html", timeout=timeout)
    except ValueError as exc:
        raise SourceDocumentUnavailable(f"A página oficial da publicação não pôde ser lida: {exc}") from exc
    article_location = urllib.parse.urlparse(final_url)
    if (article_location.scheme != "https" or article_location.hostname != DOU_HOST
            or not article_location.path.startswith("/web/dou/-/")):
        raise SourceDocumentUnavailable("A publicação redirecionou para uma URL que não pertence ao DOU.")
    article_html = BeautifulSoup(body, "html.parser")
    text_container = article_html.select_one("div.texto-dou")
    if not text_container:
        raise SourceDocumentUnavailable("A página do DOU não contém o texto integral do ato.")
    article_text = _flat(text_container.get_text(" ", strip=True))
    if expected_heading not in article_text or expected_ementa not in article_text:
        raise SourceDocumentUnavailable("O texto publicado no DOU não confere com a identidade/ementa do Senado.")
    return SenateDocument(
        body=body,
        source_url=final_url,
        representation="Publicação original no Diário Oficial da União",
        version="Original",
        legal_value="OfficialLegalValue",
        notice=f"Texto extraído da publicação original do DOU de {published}, página {page}.",
    )
