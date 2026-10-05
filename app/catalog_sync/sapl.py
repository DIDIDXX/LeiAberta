"""Paginated catalog synchronization for Câmara Municipal de Manaus SAPL."""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Jurisdiction, Law, SourceRegistry


SAPL_HOST = "https://sapl.cmm.am.gov.br"
SAPL_API = f"{SAPL_HOST}/api/norma"
NORMS_URL = f"{SAPL_API}/normajuridica/"
TYPES_URL = f"{SAPL_API}/tiponormajuridica/"
SOURCE_ID = "municipality:1302603:sapl"
SOURCE_NAME = "Câmara Municipal de Manaus — SAPL"
PAGE_SIZE = 100
MAX_BYTES = 10_000_000
MAX_AGE = timedelta(days=7)


@dataclass(frozen=True)
class SaplCatalogNorm:
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


def _get_json(url: str, *, timeout: int = 45) -> tuple[dict, str]:
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "LeiAberta/1.0 (+fontes oficiais)",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            final_url = response.geturl()
            status = response.status
    except HTTPError as exc:
        raise ValueError(f"O SAPL de Manaus respondeu HTTP {exc.code}.") from exc
    parsed = urllib.parse.urlparse(final_url)
    if status != 200 or len(body) > MAX_BYTES or parsed.scheme != "https" or parsed.hostname != "sapl.cmm.am.gov.br":
        raise ValueError("A API SAPL de Manaus falhou, excedeu o limite ou redirecionou para domínio desconhecido.")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("O SAPL de Manaus não retornou JSON válido.") from exc
    if not isinstance(payload, dict):
        raise ValueError("A API SAPL de Manaus retornou objeto inesperado.")
    return payload, final_url


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _official_media_url(value: object) -> str | None:
    if not value:
        return None
    url = urllib.parse.urlparse(str(value).strip())
    if (url.scheme == "https" and url.hostname == "sapl.cmm.am.gov.br"
            and url.path.startswith("/media/sapl/public/normajuridica/") and not url.query and not url.fragment):
        return urllib.parse.urlunparse(url)
    return None


def fetch_type_names(*, timeout: int = 45) -> dict[str, str]:
    url = TYPES_URL + "?" + urllib.parse.urlencode({"page_size": 100, "page": 1})
    payload, _ = _get_json(url, timeout=timeout)
    pagination = payload.get("pagination") or {}
    total = pagination.get("total_entries")
    pages = pagination.get("total_pages")
    if not isinstance(total, int) or not isinstance(pages, int) or pages < 1:
        raise ValueError("O catálogo de tipos SAPL não informa paginação verificável.")
    records: dict[str, str] = {}
    for page in range(1, pages + 1):
        current = payload if page == 1 else _get_json(
            TYPES_URL + "?" + urllib.parse.urlencode({"page_size": 100, "page": page}), timeout=timeout,
        )[0]
        if (current.get("pagination") or {}).get("total_entries") != total:
            raise ValueError("O total de tipos SAPL mudou durante a paginação.")
        for item in current.get("results", []):
            if not isinstance(item, dict) or not str(item.get("id", "")).isdigit() or not item.get("__str__"):
                raise ValueError("A lista de tipos SAPL contém item sem identidade.")
            key = str(item["id"])
            if key in records:
                raise ValueError(f"O catálogo de tipos SAPL repetiu o identificador {key}.")
            records[key] = str(item["__str__"]).strip()
    if len(records) != total:
        raise ValueError(f"O catálogo de tipos SAPL retornou {len(records)} de {total} tipos.")
    return records


def fetch_catalog_page(page: int, *, page_size: int = PAGE_SIZE, timeout: int = 45) -> tuple[dict, str]:
    if page < 1 or not 1 <= page_size <= PAGE_SIZE:
        raise ValueError("Página ou tamanho inválido para o catálogo SAPL.")
    url = NORMS_URL + "?" + urllib.parse.urlencode({"page_size": page_size, "page": page})
    payload, final_url = _get_json(url, timeout=timeout)
    parsed = urllib.parse.urlparse(final_url)
    if parsed.path != "/api/norma/normajuridica/":
        raise ValueError("A lista SAPL redirecionou para caminho inesperado.")
    pagination = payload.get("pagination")
    if not isinstance(pagination, dict) or pagination.get("page") != page:
        raise ValueError(f"A API SAPL retornou uma página diferente da solicitada: {page}.")
    if not isinstance(pagination.get("total_entries"), int) or not isinstance(pagination.get("total_pages"), int):
        raise ValueError("A paginação SAPL não informa total de registros e páginas.")
    if not isinstance(payload.get("results"), list):
        raise ValueError("A lista SAPL não retornou results.")
    return payload, final_url


def parse_catalog_page(payload: dict, type_names: dict[str, str]) -> list[SaplCatalogNorm]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Página SAPL sem lista results.")
    records = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Página SAPL contém registro em formato inesperado.")
        remote_id = str(item.get("id") or "").strip()
        law_type = type_names.get(str(item.get("tipo") or ""), "")
        number = str(item.get("numero") or "s/n").strip() or "s/n"
        try:
            year = int(item.get("ano"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Registro SAPL {remote_id!r} sem ano válido.") from exc
        signed_at = _date(item.get("data"))
        if (not remote_id.isdigit() or len(remote_id) > 24 or not law_type or signed_at is None
                or signed_at.year != year or item.get("esfera_federacao") != "M" or len(number) > 96):
            raise ValueError(f"Registro SAPL sem identidade municipal verificável: id={remote_id!r}.")
        title = str(item.get("__str__") or f"{law_type} {number}/{year}").strip()
        records.append(SaplCatalogNorm(
            remote_id=remote_id, law_type=law_type, number=number, year=year, signed_at=signed_at,
            published_at=_date(item.get("data_publicacao")), title=title[:300],
            description=str(item.get("ementa") or "").strip(),
            source_url=f"{NORMS_URL}{remote_id}/", text_url=_official_media_url(item.get("texto_integral")),
        ))
    ids = [record.remote_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Página SAPL contém identificador remoto duplicado.")
    return records


def sync_catalog_page(session: Session, records: list[SaplCatalogNorm], *, observed_at: datetime) -> dict:
    if not records:
        raise ValueError("Não é permitido persistir uma página SAPL vazia.")
    external_ids = [f"sapl:manaus:{item.remote_id}" for item in records]
    existing = list(session.scalars(select(Law).where(Law.external_source_id.in_(external_ids))))
    by_external = {law.external_source_id: law for law in existing}
    added = refreshed = 0
    for item in records:
        external_id = f"sapl:manaus:{item.remote_id}"
        law = by_external.get(external_id)
        if law is None:
            law = Law(
                slug=f"manaus-sapl-{item.remote_id}", jurisdiction="municipality", state_code="AM",
                municipality="Manaus", law_type=item.law_type, number=item.number, year=item.year,
                external_source_id=external_id, signed_at=item.signed_at, title=item.title,
                description=item.description, status="Não verificado", published_at=item.published_at,
                aliases=[external_id], source_name=SOURCE_NAME, source_url=item.source_url,
                fetch_url=item.text_url or item.source_url, hot=False, materialization_status="catalog",
                current_version_id=None,
                coverage={"official_source": "sapl_manaus", "municipality_ibge_code": "1302603",
                          "source_id": item.remote_id, "text_url_in_catalog": bool(item.text_url),
                          "structured_text": "not_materialized", "history": "not_requested",
                          "catalog_observed_at": observed_at.isoformat()},
            )
            session.add(law)
            by_external[external_id] = law
            added += 1
        else:
            if (law.source_name != SOURCE_NAME or law.jurisdiction != "municipality"
                    or law.state_code != "AM" or law.municipality != "Manaus"):
                raise ValueError(f"Identificador SAPL {item.remote_id} já pertence a outro escopo.")
            law.law_type, law.number, law.year = item.law_type, item.number, item.year
            law.signed_at, law.published_at = item.signed_at, item.published_at
            law.title, law.description = item.title, item.description
            law.source_url, law.fetch_url = item.source_url, item.text_url or item.source_url
            coverage = dict(law.coverage or {})
            coverage.update({"text_url_in_catalog": bool(item.text_url), "catalog_observed_at": observed_at.isoformat()})
            law.coverage = coverage
            refreshed += 1
    return {"added": added, "refreshed": refreshed}


def _source_is_fresh() -> bool:
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, SOURCE_ID)
        checked = registry.last_checked_at if registry else None
        if registry is None or registry.status != "enumerated" or checked is None:
            return False
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked > datetime.now(timezone.utc) - MAX_AGE


def sync_sapl_manaus_catalog(*, force: bool = False) -> dict:
    if not force and _source_is_fresh():
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            return {"skipped_fresh": True, "records": (registry.scope or {}).get("records_enumerated", 0)}
    observed_at = datetime.now(timezone.utc)
    types = fetch_type_names()
    first, catalog_url = fetch_catalog_page(1)
    pagination = first["pagination"]
    total, pages = pagination["total_entries"], pagination["total_pages"]
    if total < 1 or pages < 1 or pages > total:
        raise ValueError("O catálogo SAPL retornou universo ou paginação inválida.")
    scope = {"universe": "API oficial normajuridica da Câmara Municipal de Manaus; atos municipais cadastrados no SAPL.",
             "records_expected": total, "pages_expected": pages, "page_size": PAGE_SIZE,
             "type_count": len(types), "records_enumerated": 0, "started_at": observed_at.isoformat()}
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, SOURCE_ID)
        if registry is None:
            registry = SourceRegistry(id=SOURCE_ID, name=SOURCE_NAME, adapter="sapl_catalog",
                                      base_url=NORMS_URL, evidence_url=SAPL_HOST, status="syncing", scope={})
            session.add(registry)
        registry.jurisdiction_id = "municipality:1302603" if session.get(Jurisdiction, "municipality:1302603") else None
        registry.name, registry.adapter, registry.base_url = SOURCE_NAME, "sapl_catalog", catalog_url
        registry.evidence_url, registry.status, registry.scope, registry.last_error = SAPL_HOST, "syncing", scope, ""
        registry.last_checked_at = observed_at
        session.commit()

    seen: set[str] = set()
    digest = hashlib.sha256()
    added = refreshed = enumerated = 0
    try:
        for page in range(1, pages + 1):
            payload = first if page == 1 else fetch_catalog_page(page)[0]
            current = payload["pagination"]
            if current["total_entries"] != total or current["total_pages"] != pages:
                raise ValueError("O total SAPL mudou durante a paginação.")
            records = parse_catalog_page(payload, types)
            if page < pages and len(records) != PAGE_SIZE:
                raise ValueError(f"Página SAPL truncada {page}: {len(records)} de {PAGE_SIZE}.")
            for item in records:
                if item.remote_id in seen:
                    raise ValueError(f"Identificador SAPL repetido entre páginas: {item.remote_id}.")
                seen.add(item.remote_id)
                digest.update(item.remote_id.encode() + b"\n")
            with SessionLocal() as session:
                counts = sync_catalog_page(session, records, observed_at=observed_at)
                added += counts["added"]
                refreshed += counts["refreshed"]
                enumerated += len(records)
                registry = session.get(SourceRegistry, SOURCE_ID)
                registry.scope = {**scope, "records_enumerated": enumerated, "last_page": page,
                                  "catalog_ids_sha256_partial": digest.hexdigest()}
                registry.last_checked_at = observed_at
                session.commit()
    except Exception as exc:
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            if registry:
                registry.status, registry.last_error = "failed", str(exc)[:1000]
                registry.scope = {**(registry.scope or {}), "records_enumerated": enumerated,
                                  "last_page": max(0, len(seen) // PAGE_SIZE),
                                  "last_attempt_at": datetime.now(timezone.utc).isoformat()}
                registry.last_checked_at = datetime.now(timezone.utc)
                session.commit()
        raise
    if enumerated != total or len(seen) != total:
        raise ValueError(f"Catálogo SAPL incompleto: {enumerated} de {total} registros.")
    with SessionLocal() as session:
        db_total = session.scalar(select(func.count()).select_from(Law).where(Law.external_source_id.like("sapl:manaus:%"))) or 0
        registry = session.get(SourceRegistry, SOURCE_ID)
        registry.status = "enumerated"
        registry.scope = {**scope, "records_enumerated": enumerated, "records_in_database": db_total,
                          "last_page": pages, "catalog_ids_sha256": digest.hexdigest(),
                          "observed_at": datetime.now(timezone.utc).isoformat()}
        registry.last_checked_at = datetime.now(timezone.utc)
        registry.last_error = ""
        session.commit()
    return {"records": enumerated, "expected": total, "pages": pages, "added": added,
            "refreshed": refreshed, "catalog_ids_sha256": digest.hexdigest()}
