"""Paginated synchronization of the official ALESP legislation catalog."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Jurisdiction, Law, SourceRegistry


ALESP_API = "https://baleg-api-prd.al.sp.gov.br"
ALESP_LIST_URL = f"{ALESP_API}/normas"
ALESP_WEB = "https://www.al.sp.gov.br"
ALESP_PAGE_SIZE = 5000
ALESP_MAX_BYTES = 20_000_000
ALESP_MAX_AGE = timedelta(days=7)
SOURCE_ID = "state:SP:alesp"
SOURCE_NAME = "Assembleia Legislativa do Estado de São Paulo — ALESP"


@dataclass(frozen=True)
class AlespCatalogNorm:
    remote_id: str
    law_type: str
    number: str
    year: int
    signed_at: date
    published_at: date | None
    title: str
    description: str
    source_url: str
    text_url: str | None
    source_type_id: str


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _number(number: str, title: str) -> str:
    match = re.search(r"\bn[º°o]?\s*([\d.]+(?:-\d+)?)\s*,?\s*(?:de|,)", title, re.I)
    if match:
        return match.group(1).strip(".")
    return number.strip() or "s/n"


def _same_number(left: str, right: str) -> bool:
    return re.sub(r"[^\d-]", "", left) == re.sub(r"[^\d-]", "", right)


def _parse_record(item: dict) -> AlespCatalogNorm:
    remote_id = str(item.get("idNorma") or "").strip()
    law_type = str(item.get("tipo") or "").strip()
    title = str(item.get("nomeNorma") or "").strip()
    signed_at = _date(item.get("data"))
    raw_number = str(item.get("nuNorma") or "").strip()
    if not remote_id.isdigit() or not law_type or not title or signed_at is None:
        raise ValueError(f"Registro ALESP sem identidade mínima: id={remote_id!r} tipo={law_type!r} data={item.get('data')!r}")
    text_url = str(item.get("urlIntegraListaPesquisa") or "").strip() or None
    if text_url:
        parsed = urllib.parse.urlparse(text_url)
        if (parsed.scheme != "https" or parsed.hostname != "www.al.sp.gov.br"
                or not parsed.path.startswith("/repositorio/legislacao/")):
            text_url = None
    return AlespCatalogNorm(
        remote_id=remote_id,
        law_type=law_type,
        number=_number(raw_number, title),
        year=signed_at.year,
        signed_at=signed_at,
        published_at=_date(item.get("dataPublicacao")),
        title=title[:300],
        description=str(item.get("dsEmenta") or "").strip(),
        source_url=f"{ALESP_WEB}/norma/{remote_id}",
        text_url=text_url,
        source_type_id=str(item.get("idTipo") or ""),
    )


def fetch_catalog_page(page: int, *, size: int = ALESP_PAGE_SIZE, timeout: int = 60) -> tuple[dict, str]:
    if page < 0 or not 1 <= size <= ALESP_PAGE_SIZE:
        raise ValueError("Página ou tamanho inválido para o catálogo ALESP.")
    url = f"{ALESP_LIST_URL}?" + urllib.parse.urlencode({"page": page, "size": size})
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "LeiAberta/0.3 (+fontes oficiais)",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(ALESP_MAX_BYTES + 1)
            if response.status != 200 or len(body) > ALESP_MAX_BYTES:
                raise ValueError("Resposta ALESP inválida ou acima do limite de tamanho.")
            final_url = response.geturl()
    except HTTPError as exc:
        raise ValueError(f"A API oficial ALESP respondeu HTTP {exc.code} na página {page}.") from exc
    parsed = urllib.parse.urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname != "baleg-api-prd.al.sp.gov.br":
        raise ValueError("A lista ALESP redirecionou para domínio não reconhecido.")
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("A lista ALESP não retornou JSON válido.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise ValueError("A API ALESP retornou paginação em formato inesperado.")
    if data.get("number") != page or data.get("size") != size:
        raise ValueError(f"A API ALESP retornou página/tamanho divergente: {data.get('number')}/{data.get('size')}.")
    if not isinstance(data.get("totalElements"), int) or not isinstance(data.get("totalPages"), int):
        raise ValueError("A paginação ALESP não informa o total de registros e páginas.")
    return data, final_url


def parse_catalog_page(data: dict) -> list[AlespCatalogNorm]:
    content = data.get("content")
    if not isinstance(content, list):
        raise ValueError("Página ALESP sem lista content.")
    records = [_parse_record(item) for item in content if isinstance(item, dict)]
    if len(records) != len(content):
        raise ValueError("Página ALESP contém registro em formato inesperado.")
    ids = [record.remote_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Página ALESP contém identificador remoto duplicado.")
    return records


def sync_catalog_page(session: Session, records: list[AlespCatalogNorm], *, observed_at: datetime) -> dict:
    if not records:
        raise ValueError("Não é permitido persistir uma página ALESP vazia.")
    remote_ids = [f"alesp:{record.remote_id}" for record in records]
    existing_rows = list(session.scalars(select(Law).where(Law.external_source_id.in_(remote_ids))))
    by_remote = {law.external_source_id: law for law in existing_rows}
    added = refreshed = 0
    for record in records:
        external_id = f"alesp:{record.remote_id}"
        law = by_remote.get(external_id)
        if law is None:
            law = Law(
                slug=f"sp-alesp-{record.remote_id}", jurisdiction="state", state_code="SP",
                municipality=None, law_type=record.law_type, number=record.number, year=record.year,
                external_source_id=external_id, signed_at=record.signed_at,
                title=record.title, description=record.description, status="Não verificado",
                published_at=record.published_at, aliases=[f"alesp:{record.remote_id}"],
                source_name=SOURCE_NAME, source_url=record.source_url,
                fetch_url=record.text_url or record.source_url, hot=False,
                materialization_status="catalog", current_version_id=None,
                coverage={
                    "official_source": "alesp_legislation_api", "state_code": "SP",
                    "source_id": record.remote_id, "source_type_id": record.source_type_id,
                    "text_url_in_catalog": bool(record.text_url), "structured_text": "not_materialized",
                    "history": "not_requested", "catalog_observed_at": observed_at.isoformat(),
                },
            )
            session.add(law)
            by_remote[external_id] = law
            added += 1
        else:
            if law.source_name != SOURCE_NAME or law.jurisdiction != "state" or law.state_code != "SP":
                raise ValueError(f"Identificador ALESP {record.remote_id} já pertence a outro escopo.")
            law.law_type = record.law_type
            law.number = record.number
            law.year = record.year
            law.signed_at = record.signed_at
            law.published_at = record.published_at
            law.title = record.title
            law.description = record.description
            law.source_url = record.source_url
            law.fetch_url = record.text_url or record.source_url
            coverage = dict(law.coverage or {})
            coverage.update({"source_type_id": record.source_type_id,
                             "text_url_in_catalog": bool(record.text_url),
                             "catalog_observed_at": observed_at.isoformat()})
            law.coverage = coverage
            refreshed += 1
    return {"added": added, "refreshed": refreshed}


def _source_is_fresh(*, max_age: timedelta = ALESP_MAX_AGE) -> bool:
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, SOURCE_ID)
        if not registry or registry.status != "enumerated" or not registry.last_checked_at:
            return False
        checked = registry.last_checked_at
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked > datetime.now(timezone.utc) - max_age


def sync_alesp_catalog(*, force: bool = False, page_size: int = ALESP_PAGE_SIZE) -> dict:
    """Import every page, checkpointing each page and rejecting changing/truncated totals."""
    if not 1 <= page_size <= ALESP_PAGE_SIZE:
        raise ValueError(f"page_size precisa estar entre 1 e {ALESP_PAGE_SIZE}.")
    if not force and _source_is_fresh():
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            return {"skipped_fresh": True, "records": (registry.scope or {}).get("records_enumerated", 0),
                    "observed_at": registry.last_checked_at.isoformat()}

    started_at = datetime.now(timezone.utc)
    added = refreshed = enumerated = 0
    id_digest = hashlib.sha256()
    seen_ids: set[str] = set()
    try:
        first_page, catalog_url = fetch_catalog_page(0, size=page_size)
        expected_total = first_page["totalElements"]
        expected_pages = first_page["totalPages"]
        if expected_total < 1 or expected_pages < 1:
            raise ValueError("A API ALESP retornou catálogo vazio.")
        registry_scope = {
            "types": [], "records_expected": expected_total, "pages_expected": expected_pages,
            "page_size": page_size, "records_enumerated": 0, "started_at": started_at.isoformat(),
            "universe": "Registros retornados pelo endpoint oficial ALESP /normas; atos estaduais de SP.",
        }
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            if registry is None:
                registry = SourceRegistry(
                    id=SOURCE_ID, jurisdiction_id="state:SP", name=SOURCE_NAME,
                    adapter="alesp_catalog", base_url=ALESP_LIST_URL,
                    evidence_url="https://www.al.sp.gov.br/norma/", status="syncing", scope={}, last_error="",
                )
                session.add(registry)
            registry.jurisdiction_id = "state:SP" if session.get(Jurisdiction, "state:SP") else None
            registry.name = SOURCE_NAME
            registry.adapter = "alesp_catalog"
            registry.base_url = catalog_url
            registry.evidence_url = "https://www.al.sp.gov.br/norma/"
            registry.status = "syncing"
            registry.scope = registry_scope
            registry.last_error = ""
            registry.last_checked_at = started_at
            session.commit()

        for page_number in range(expected_pages):
            data = first_page if page_number == 0 else fetch_catalog_page(page_number, size=page_size)[0]
            if data["totalElements"] != expected_total or data["totalPages"] != expected_pages:
                raise ValueError("O total do catálogo ALESP mudou durante a paginação; a execução foi interrompida para nova reconciliação.")
            records = parse_catalog_page(data)
            if page_number < expected_pages - 1 and len(records) != page_size:
                raise ValueError(f"Página ALESP truncada {page_number}: {len(records)} de {page_size} itens.")
            for record in records:
                if record.remote_id in seen_ids:
                    raise ValueError(f"Identificador ALESP repetido entre páginas: {record.remote_id}.")
                seen_ids.add(record.remote_id)
                id_digest.update(record.remote_id.encode())
                id_digest.update(b"\n")
            with SessionLocal() as session:
                counts = sync_catalog_page(session, records, observed_at=started_at)
                added += counts["added"]
                refreshed += counts["refreshed"]
                enumerated += len(records)
                registry = session.get(SourceRegistry, SOURCE_ID)
                registry.scope = {**registry_scope, "records_enumerated": enumerated,
                                  "last_page": page_number, "catalog_ids_sha256_partial": id_digest.hexdigest()}
                registry.last_checked_at = started_at
                session.commit()
        if enumerated != expected_total or len(seen_ids) != expected_total:
            raise ValueError(f"Paginação ALESP incompleta: enumerados={enumerated}, ids={len(seen_ids)}, esperado={expected_total}.")
        with SessionLocal() as session:
            db_total = session.scalar(select(func.count()).select_from(Law).where(
                Law.external_source_id.like("alesp:%"))) or 0
            registry = session.get(SourceRegistry, SOURCE_ID)
            registry.status = "enumerated"
            registry.scope = {
                **registry_scope, "records_enumerated": enumerated, "records_in_database": db_total,
                "last_page": expected_pages - 1, "catalog_ids_sha256": id_digest.hexdigest(),
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            registry.last_checked_at = datetime.now(timezone.utc)
            registry.last_error = ""
            session.commit()
        return {"records": enumerated, "expected": expected_total, "pages": expected_pages,
                "added": added, "refreshed": refreshed, "catalog_ids_sha256": id_digest.hexdigest(),
                "observed_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            if registry:
                registry.status = "failed"
                registry.last_error = str(exc)[:1000]
                registry.scope = {**(registry.scope or {}), "records_enumerated": enumerated,
                                  "last_page": max(-1, len(seen_ids) // page_size),
                                  "last_attempt_at": datetime.now(timezone.utc).isoformat()}
                registry.last_checked_at = datetime.now(timezone.utc)
                session.commit()
        raise
