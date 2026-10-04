"""Paginated synchronization of the official SINJ-DF norms catalog."""
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


SINJ_WEB = "https://www.sinj.df.gov.br/sinj"
SINJ_RESULTS = f"{SINJ_WEB}/ashx/Datatable/ResultadoDePesquisaNormaDatatable.ashx"
SINJ_SEARCH = f"{SINJ_WEB}/ResultadoDePesquisa?tipo_pesquisa=norma"
SOURCE_ID = "state:DF:sinj"
SOURCE_NAME = "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF"
PAGE_SIZE = 5000
MAX_CATALOG_BYTES = 25_000_000
MAX_AGE = timedelta(days=7)


@dataclass(frozen=True)
class SinjCatalogNorm:
    remote_id: str
    document_id: str
    law_type: str
    number: str
    year: int
    signed_at: date
    published_at: date | None
    title: str
    description: str
    status: str
    source_url: str
    text_attachment_types: tuple[str, ...]


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _page_form(offset: int, size: int) -> dict[str, str]:
    props = ["_score", "_score", "nm_tipo_norma", "dt_assinatura", "origens",
             "ds_ementa", "nm_situacao", "7", "8"]
    form = {
        "bbusca": "sinj_norma", "iColumns": "9", "sColumns": ",,,,,,,,",
        "iDisplayStart": str(offset), "iDisplayLength": str(size), "sSearch": "",
        "bRegex": "false", "iSortCol_0": "3", "sSortDir_0": "desc",
        "iSortingCols": "1", "tipo_pesquisa": "norma", "all": "",
    }
    for i, prop in enumerate(props):
        form.update({f"mDataProp_{i}": prop, f"sSearch_{i}": "", f"bRegex_{i}": "false",
                     f"bSearchable_{i}": "true" if i in (0, 1, 2, 3, 6) else "false"})
    return form


def fetch_catalog_page(offset: int, *, size: int = PAGE_SIZE, timeout: int = 60) -> tuple[dict, str]:
    if offset < 0 or not 1 <= size <= PAGE_SIZE:
        raise ValueError("Offset ou tamanho inválido para o catálogo SINJ-DF.")
    request = urllib.request.Request(
        SINJ_RESULTS,
        urllib.parse.urlencode(_page_form(offset, size)).encode(),
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": SINJ_SEARCH, "User-Agent": "LeiAberta/0.3 (+fontes oficiais)",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_CATALOG_BYTES + 1)
            final_url = response.geturl()
            status = response.status
    except HTTPError as exc:
        raise ValueError(f"O SINJ-DF respondeu HTTP {exc.code} na página com offset {offset}.") from exc
    parsed_url = urllib.parse.urlparse(final_url)
    if status != 200 or len(body) > MAX_CATALOG_BYTES:
        raise ValueError("A resposta do SINJ-DF falhou ou excedeu o limite de tamanho.")
    if parsed_url.scheme != "https" or parsed_url.hostname != "www.sinj.df.gov.br" or parsed_url.path != "/sinj/ashx/Datatable/ResultadoDePesquisaNormaDatatable.ashx":
        raise ValueError("A lista do SINJ-DF redirecionou para domínio ou caminho não reconhecido.")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("O SINJ-DF não retornou JSON válido para o catálogo.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("aaData"), list):
        raise ValueError("O SINJ-DF retornou paginação em formato inesperado.")
    try:
        reported_offset = int(payload.get("offset", -1))
        total = int(payload.get("iTotalDisplayRecords", -1))
    except (TypeError, ValueError) as exc:
        raise ValueError("A resposta do SINJ-DF não inclui offset e total válidos.") from exc
    if reported_offset != offset or total < 1:
        raise ValueError(f"A paginação SINJ-DF diverge: offset={reported_offset}, total={total}.")
    return payload, final_url


def parse_catalog_page(payload: dict) -> list[SinjCatalogNorm]:
    rows = payload.get("aaData")
    if not isinstance(rows, list):
        raise ValueError("Página SINJ-DF sem lista aaData.")
    result: list[SinjCatalogNorm] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("_source"), dict):
            raise ValueError("Página SINJ-DF contém registro em formato inesperado.")
        source = row["_source"]
        remote_id = str(source.get("ch_norma") or "").strip().lower()
        document_id = str(row.get("_id") or "").strip()
        law_type = str(source.get("nm_tipo_norma") or "").strip()
        raw_number = str(source.get("nr_norma") or "").strip()
        signed_at = _date(source.get("dt_assinatura"))
        if not re.fullmatch(r"(?:[0-9a-f]{32}|[0-9]{1,24})", remote_id) or not document_id.isdigit() or not law_type or signed_at is None:
            raise ValueError(f"Registro SINJ-DF sem identidade mínima: hash={remote_id!r}, id={document_id!r}.")
        number = raw_number if raw_number and raw_number != "0" else "s/n"
        if len(law_type) > 48 or len(number) > 96:
            raise ValueError(f"Registro SINJ-DF excede o tamanho permitido: {law_type!r} {number!r}.")
        sources = source.get("fontes") if isinstance(source.get("fontes"), list) else []
        published_at = next((_date(item.get("dt_publicacao")) for item in sources
                             if isinstance(item, dict) and _date(item.get("dt_publicacao"))), None)
        attachments = []
        for item in sources:
            if isinstance(item, dict) and isinstance(item.get("ar_fonte"), dict):
                mimetype = str(item["ar_fonte"].get("mimetype") or "").strip().lower()
                if mimetype:
                    attachments.append(mimetype)
        updated_text = source.get("ar_atualizado")
        if isinstance(updated_text, dict):
            mimetype = str(updated_text.get("mimetype") or "").strip().lower()
            if mimetype:
                attachments.append(mimetype)
        title = f"{law_type} {number} de {signed_at:%d/%m/%Y}"
        result.append(SinjCatalogNorm(
            remote_id=remote_id, document_id=document_id, law_type=law_type, number=number,
            year=signed_at.year, signed_at=signed_at, published_at=published_at,
            title=title[:300], description=str(source.get("ds_ementa") or "").strip(),
            status=(str(source.get("nm_situacao") or "Não verificado").strip() or "Não verificado")[:48],
            source_url=f"{SINJ_WEB}/DetalhesDeNorma.aspx?id_doc={document_id}",
            text_attachment_types=tuple(sorted(set(attachments))),
        ))
    ids = [record.remote_id for record in result]
    document_ids = [record.document_id for record in result]
    if len(ids) != len(set(ids)) or len(document_ids) != len(set(document_ids)):
        raise ValueError("Página SINJ-DF contém identificador remoto duplicado.")
    return result


def sync_catalog_page(session: Session, records: list[SinjCatalogNorm], *, observed_at: datetime) -> dict:
    if not records:
        raise ValueError("Não é permitido persistir uma página SINJ-DF vazia.")
    ids = [f"sinj:{record.remote_id}" for record in records]
    existing = list(session.scalars(select(Law).where(Law.external_source_id.in_(ids))))
    by_remote = {law.external_source_id: law for law in existing}
    added = refreshed = 0
    for record in records:
        external_id = f"sinj:{record.remote_id}"
        law = by_remote.get(external_id)
        coverage = {
            "official_source": "sinj_df_norms_catalog", "state_code": "DF",
            "source_hash": record.remote_id, "document_id": record.document_id,
            "text_attachment_types": list(record.text_attachment_types),
            "structured_text": "not_materialized", "history": "not_requested",
            "catalog_observed_at": observed_at.isoformat(),
        }
        if law is None:
            law = Law(
                slug=f"df-sinj-{record.remote_id}", jurisdiction="state", state_code="DF",
                municipality=None, law_type=record.law_type, number=record.number, year=record.year,
                external_source_id=external_id, signed_at=record.signed_at,
                title=record.title, description=record.description, status=record.status,
                published_at=record.published_at, aliases=[external_id], source_name=SOURCE_NAME,
                source_url=record.source_url, fetch_url=record.source_url, hot=False,
                materialization_status="catalog", current_version_id=None, coverage=coverage,
            )
            session.add(law)
            by_remote[external_id] = law
            added += 1
        else:
            if law.source_name != SOURCE_NAME or law.jurisdiction != "state" or law.state_code != "DF":
                raise ValueError(f"Identificador SINJ-DF {record.remote_id} já pertence a outro escopo.")
            law.law_type = record.law_type
            law.number = record.number
            law.year = record.year
            law.signed_at = record.signed_at
            law.published_at = record.published_at
            law.title = record.title
            law.description = record.description
            law.status = record.status
            law.source_url = record.source_url
            law.fetch_url = record.source_url
            previous = dict(law.coverage or {})
            law.coverage = {**previous, **coverage}
            refreshed += 1
    return {"added": added, "refreshed": refreshed}


def _source_is_fresh() -> bool:
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, SOURCE_ID)
        if not registry or registry.status != "enumerated" or not registry.last_checked_at:
            return False
        checked = registry.last_checked_at
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked > datetime.now(timezone.utc) - MAX_AGE


def sync_sinj_df_catalog(*, force: bool = False, page_size: int = PAGE_SIZE) -> dict:
    """Enumerate the complete result set; checkpoint each page and reject gaps or repeats."""
    if not 1 <= page_size <= PAGE_SIZE:
        raise ValueError(f"page_size precisa estar entre 1 e {PAGE_SIZE}.")
    if not force and _source_is_fresh():
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            return {"skipped_fresh": True, "records": (registry.scope or {}).get("records_enumerated", 0),
                    "observed_at": registry.last_checked_at.isoformat()}

    started = datetime.now(timezone.utc)
    enumerated = added = refreshed = 0
    seen: set[str] = set()
    digest = hashlib.sha256()
    try:
        first_page, base_url = fetch_catalog_page(0, size=page_size)
        expected_total = int(first_page["iTotalDisplayRecords"])
        expected_pages = (expected_total + page_size - 1) // page_size
        scope = {"records_expected": expected_total, "pages_expected": expected_pages,
                 "page_size": page_size, "records_enumerated": 0, "started_at": started.isoformat(),
                 "universe": "Todos os registros retornados pela busca oficial de normas do SINJ-DF, sem termo de pesquisa."}
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            if registry is None:
                registry = SourceRegistry(id=SOURCE_ID, jurisdiction_id="state:DF" if session.get(Jurisdiction, "state:DF") else None,
                                          name=SOURCE_NAME, adapter="sinj_df_catalog", base_url=base_url,
                                          evidence_url=SINJ_SEARCH, status="syncing", scope={}, last_error="")
                session.add(registry)
            registry.jurisdiction_id = "state:DF" if session.get(Jurisdiction, "state:DF") else None
            registry.name = SOURCE_NAME
            registry.adapter = "sinj_df_catalog"
            registry.base_url = base_url
            registry.evidence_url = SINJ_SEARCH
            registry.status = "syncing"
            registry.scope = scope
            registry.last_error = ""
            registry.last_checked_at = started
            session.commit()

        for page_number in range(expected_pages):
            offset = page_number * page_size
            payload = first_page if page_number == 0 else fetch_catalog_page(offset, size=page_size)[0]
            if int(payload.get("iTotalDisplayRecords", -1)) != expected_total or int(payload.get("offset", -1)) != offset:
                raise ValueError("O total ou offset do catálogo SINJ-DF mudou durante a paginação.")
            records = parse_catalog_page(payload)
            expected_length = min(page_size, expected_total - offset)
            if len(records) != expected_length:
                raise ValueError(f"Página SINJ-DF truncada no offset {offset}: {len(records)} de {expected_length} itens.")
            for record in records:
                if record.remote_id in seen:
                    raise ValueError(f"Identificador SINJ-DF repetido entre páginas: {record.remote_id}.")
                seen.add(record.remote_id)
                digest.update(record.remote_id.encode())
                digest.update(b"\n")
            with SessionLocal() as session:
                counts = sync_catalog_page(session, records, observed_at=started)
                added += counts["added"]
                refreshed += counts["refreshed"]
                enumerated += len(records)
                registry = session.get(SourceRegistry, SOURCE_ID)
                registry.scope = {**scope, "records_enumerated": enumerated, "last_page": page_number,
                                  "catalog_ids_sha256_partial": digest.hexdigest()}
                registry.last_checked_at = started
                session.commit()
        if enumerated != expected_total or len(seen) != expected_total:
            raise ValueError(f"Paginação SINJ-DF incompleta: enumerados={enumerated}, ids={len(seen)}, esperado={expected_total}.")
        with SessionLocal() as session:
            db_total = session.scalar(select(func.count()).select_from(Law).where(Law.external_source_id.like("sinj:%"))) or 0
            if db_total != expected_total:
                raise ValueError(f"Catálogo SINJ-DF no banco tem {db_total} registros; a fonte informa {expected_total}.")
            registry = session.get(SourceRegistry, SOURCE_ID)
            registry.status = "enumerated"
            registry.scope = {**scope, "records_enumerated": enumerated, "records_in_database": db_total,
                              "last_page": expected_pages - 1, "catalog_ids_sha256": digest.hexdigest(),
                              "observed_at": datetime.now(timezone.utc).isoformat()}
            registry.last_checked_at = datetime.now(timezone.utc)
            registry.last_error = ""
            session.commit()
        return {"records": enumerated, "expected": expected_total, "pages": expected_pages,
                "added": added, "refreshed": refreshed, "catalog_ids_sha256": digest.hexdigest(),
                "observed_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, SOURCE_ID)
            if registry:
                registry.status = "failed"
                registry.last_error = str(exc)[:1000]
                registry.scope = {**(registry.scope or {}), "records_enumerated": enumerated,
                                  "last_page": max(-1, len(seen) // page_size),
                                  "last_attempt_at": datetime.now(timezone.utc).isoformat()}
                registry.last_checked_at = datetime.now(timezone.utc)
                session.commit()
        raise
