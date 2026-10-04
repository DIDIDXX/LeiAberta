"""Enumerate the federal laws exposed by the Senate's official API."""
from __future__ import annotations

import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Jurisdiction, Law, SourceRegistry

SENATE_LIST_BASE = "https://legis.senado.leg.br/dadosabertos/legislacao/lista"
MAX_CATALOG_BYTES = 20_000_000
CATALOG_MAX_AGE = timedelta(hours=24)

# These exact type codes were confirmed against the official Senate API. This is
# a broad federal catalog, not a claim that the Senate endpoint covers every
# executive or subnational act.
TYPE_LABELS = {
    "LEI": "Lei",
    "LCP": "Lei Complementar",
    "EMC": "Emenda Constitucional",
    "MPV": "Medida Provisória",
    "DLG": "Decreto Legislativo",
    "RSF": "Resolução do Senado Federal",
}
MINIMUM_RECORDS = {"LEI": 1_000, "LCP": 100, "EMC": 100, "MPV": 1_000, "DLG": 5_000, "RSF": 1_000}


@dataclass(frozen=True)
class SenadoCatalogLaw:
    remote_id: str
    type_code: str
    law_type: str
    number: str
    year: int
    signed_at: date | None
    title: str
    description: str
    source_url: str
    source_urn: str


def _date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date() if value.strip() else None
    except ValueError:
        return None


def _format_number(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    if not digits:
        return "s/n"
    groups = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    return ".".join(reversed(groups))


def _official_number(number: str, title: str) -> str:
    # Several temporary measures use a final sequence (`2.206-1`). Prefer the
    # official number embedded in normaNome, then fall back to grouping digits.
    match = re.search(r"\bn[º°o]?\s*([\d.]+(?:-\d+)?)\s+de\b", title, re.I)
    return match.group(1).strip(".") if match else _format_number(number)


def _source_id(type_code: str) -> str:
    return "federal:senado:leis" if type_code == "LEI" else f"federal:senado:{type_code.casefold()}"


def fetch_law_catalog(type_code: str = "LEI", *, timeout: int = 60) -> tuple[bytes, str]:
    if type_code not in TYPE_LABELS:
        raise ValueError(f"Tipo do catálogo Senado não validado: {type_code}")
    url = f"{SENATE_LIST_BASE}?tipo={type_code}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/xml", "User-Agent": "LeiAberta/0.3 (+fontes oficiais)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_CATALOG_BYTES + 1)
        if response.status != 200 or len(body) > MAX_CATALOG_BYTES:
            raise ValueError("A lista federal do Senado excedeu o limite de tamanho ou falhou.")
        return body, response.geturl()


def parse_law_catalog(body: bytes, *, type_code: str = "LEI",
                      base_url: str = "https://legis.senado.leg.br/dadosabertos",
                      minimum_records: int | None = None) -> list[SenadoCatalogLaw]:
    if type_code not in TYPE_LABELS:
        raise ValueError(f"Tipo do catálogo Senado não validado: {type_code}")
    minimum_records = MINIMUM_RECORDS[type_code] if minimum_records is None else minimum_records
    if not body or len(body) > MAX_CATALOG_BYTES:
        raise ValueError("A lista federal do Senado está vazia ou excede o limite de tamanho.")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("O Senado retornou catálogo XML inválido.") from exc
    entries = root.findall("./documentos/documento")
    if len(entries) < minimum_records:
        raise ValueError(f"A lista integral do Senado veio vazia ou truncada: {len(entries)} documentos.")
    results = []
    seen = set()
    for entry in entries:
        remote_id = (entry.get("id") or "").strip()
        year_text = (entry.findtext("anoassinatura") or "").strip()
        number = entry.findtext("numero") or ""
        year = int(year_text) if year_text.isdigit() else None
        title = (entry.findtext("normaNome") or "").strip()
        if not remote_id.isdigit() or year is None or not 1800 <= year <= 2200 or not title:
            raise ValueError(f"O catálogo Senado contém um registro sem identidade mínima: id={remote_id!r} ano={year_text!r}")
        if remote_id in seen:
            raise ValueError(f"Identificador Senado duplicado no catálogo: {remote_id}")
        seen.add(remote_id)
        source_urn = (entry.findtext("norma") or "").strip()
        results.append(SenadoCatalogLaw(
            remote_id=remote_id, type_code=type_code, law_type=TYPE_LABELS[type_code],
            number=_official_number(number, title), year=year,
            signed_at=_date(entry.findtext("dataassinatura") or ""),
            title=title[:300], description=(entry.findtext("ementa") or "").strip(),
            source_url=f"{base_url.rstrip('/')}/legislacao/{remote_id}", source_urn=source_urn,
        ))
    if not results:
        raise ValueError("Nenhuma lei do Senado tinha identidade mínima válida.")
    return results


def sync_law_catalog(session: Session, records: list[SenadoCatalogLaw], *,
                     type_code: str | None = None, catalog_url: str | None = None,
                     total_records: int | None = None, records_committed: int | None = None,
                     final_chunk: bool = True) -> dict:
    """Idempotently sync list metadata; does not claim the Senate list is every federal act."""
    if not records:
        raise ValueError("Não é permitido sincronizar um catálogo vazio.")
    codes = {record.type_code for record in records}
    if type_code is None:
        if len(codes) != 1:
            raise ValueError("Uma execução de sincronização deve conter exatamente um tipo normativo.")
        type_code = next(iter(codes))
    if type_code not in TYPE_LABELS or codes != {type_code}:
        raise ValueError("Os registros não correspondem ao tipo normativo solicitado.")
    catalog_url = catalog_url or f"{SENATE_LIST_BASE}?tipo={type_code}"
    laws = list(session.scalars(select(Law)))
    by_remote = {law.external_source_id: law for law in laws if law.external_source_id}
    by_identity: dict[tuple[str, str, int], list[Law]] = {}
    for law in laws:
        digits = re.sub(r"\D", "", law.number)
        by_identity.setdefault((law.law_type.casefold(), digits, law.year), []).append(law)
    added = attached = refreshed = 0
    now = datetime.now(timezone.utc)
    new_laws = []
    for record in records:
        existing = by_remote.get(record.remote_id)
        if existing:
            if (existing.source_name.startswith("Senado Federal") and
                    existing.law_type.casefold() != record.law_type.casefold()):
                raise ValueError(f"O identificador remoto {record.remote_id} apareceu em dois tipos Senado distintos.")
            existing.signed_at = record.signed_at
            if existing.source_name.startswith("Senado Federal"):
                existing.law_type = record.law_type
                existing.title = record.title[:300]
                existing.description = record.description
                existing.source_url = record.source_url
                existing.fetch_url = record.source_url
                aliases = list(existing.aliases or [])
                if record.source_urn:
                    aliases.append(record.source_urn)
                existing.aliases = list(dict.fromkeys(aliases))
            refreshed += 1
            continue

        identity = (record.law_type.casefold(), re.sub(r"\D", "", record.number), record.year)
        candidates = by_identity.get(identity, [])
        seed = next((row for row in candidates if row.external_source_id is None), None) if len(candidates) == 1 else None
        if seed:
            seed.external_source_id = record.remote_id
            seed.signed_at = record.signed_at
            aliases = list(seed.aliases or [])
            if record.source_urn:
                aliases.append(record.source_urn)
            seed.aliases = list(dict.fromkeys(aliases))
            attached += 1
            by_remote[record.remote_id] = seed
            continue

        slug = f"senado-{record.remote_id}"
        aliases = [record.source_urn] if record.source_urn else []
        law = Law(
            slug=slug, jurisdiction="federal", law_type=record.law_type, number=record.number,
            year=record.year, external_source_id=record.remote_id, signed_at=record.signed_at,
            title=record.title[:300], description=record.description,
            status="Não verificado", published_at=None, aliases=aliases,
            source_name="Senado Federal — Dados Abertos Legislativos",
            source_url=record.source_url, fetch_url=record.source_url,
            hot=False, materialization_status="catalog", current_version_id=None,
            coverage={"official_source": "senado_metadata", "structured_text": "not_materialized",
                      "history": "not_requested", "senado_urn": record.source_urn,
                      "catalog_observed_at": now.isoformat()},
        )
        new_laws.append(law)
        by_remote[record.remote_id] = law
        by_identity.setdefault(identity, []).append(law)
        added += 1
    session.add_all(new_laws)
    source_id = _source_id(type_code)
    registry = session.get(SourceRegistry, source_id)
    if registry is None:
        registry = SourceRegistry(
            id=source_id, name=f"Senado Federal — catálogo {record.law_type}",
            adapter="senado_catalog", base_url=catalog_url,
            evidence_url="https://legis.senado.leg.br/dadosabertos/v3/api-docs",
            scope={}, status="discovered", last_error="",
        )
        session.add(registry)
    registry.jurisdiction_id = "federal" if session.get(Jurisdiction, "federal") else None
    registry.name = f"Senado Federal — catálogo {TYPE_LABELS[type_code]}"
    registry.adapter = "senado_catalog"
    registry.base_url = catalog_url
    registry.evidence_url = "https://legis.senado.leg.br/dadosabertos/v3/api-docs"
    registry.scope = {"normative_class": TYPE_LABELS[type_code], "senate_type_code": type_code,
                      "records_enumerated": total_records or len(records),
                      "records_committed": records_committed or len(records),
                      "last_remote_id": records[-1].remote_id,
                      "universe": f"Senado API records returned by tipo={type_code}; excludes types not listed and subnational jurisdictions"}
    registry.status = "enumerated" if final_chunk else "syncing"
    registry.last_checked_at = now
    registry.last_error = ""
    session.commit()
    digest = hashlib.sha256("\n".join(record.remote_id for record in records).encode()).hexdigest()
    return {"source": catalog_url, "type_code": type_code, "listed": len(records), "added": added,
            "attached_to_seed": attached, "refreshed": refreshed,
            "catalog_ids_sha256": digest, "observed_at": now.isoformat()}


def _catalog_is_fresh(type_code: str, *, max_age=CATALOG_MAX_AGE) -> bool:
    from app.db import SessionLocal

    source_id = _source_id(type_code)
    with SessionLocal() as session:
        row = session.get(SourceRegistry, source_id)
        if not row or not row.last_checked_at or row.status != "enumerated":
            return False
        checked_at = row.last_checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        return checked_at > datetime.now(timezone.utc) - max_age


def sync_senado_law_catalog(type_codes: tuple[str, ...] = tuple(TYPE_LABELS), *, force: bool = False) -> dict:
    from app.db import SessionLocal

    results = []
    errors = []
    skipped = []
    for type_code in type_codes:
        if type_code not in TYPE_LABELS:
            errors.append({"type_code": type_code, "error": "tipo não validado"})
            continue
        if not force and _catalog_is_fresh(type_code):
            skipped.append(type_code)
            continue
        try:
            body, url = fetch_law_catalog(type_code)
            records = parse_law_catalog(body, type_code=type_code,
                                        base_url="https://legis.senado.leg.br/dadosabertos")
            counts = {"added": 0, "attached_to_seed": 0, "refreshed": 0}
            chunk_size = 1_000
            for start in range(0, len(records), chunk_size):
                chunk = records[start:start + chunk_size]
                final_chunk = start + len(chunk) == len(records)
                with SessionLocal() as session:
                    result = sync_law_catalog(
                        session, chunk, type_code=type_code, catalog_url=url,
                        total_records=len(records), records_committed=start + len(chunk),
                        final_chunk=final_chunk,
                    )
                for key in counts:
                    counts[key] += result[key]
            result.update(counts)
            result["listed"] = len(records)
            result["catalog_ids_sha256"] = hashlib.sha256("\n".join(item.remote_id for item in records).encode()).hexdigest()
            result["source_response_sha256"] = hashlib.sha256(body).hexdigest()
            results.append(result)
        except Exception as exc:
            error = str(exc)[:300]
            errors.append({"type_code": type_code, "error": error})
            with SessionLocal() as session:
                registry = session.get(SourceRegistry, _source_id(type_code))
                if registry:
                    registry.status = "stale"
                    registry.last_error = error
                    session.commit()
    return {"synced": results, "skipped_fresh": skipped, "errors": errors,
            "listed": sum(item["listed"] for item in results),
            "added": sum(item["added"] for item in results),
            "observed_at": datetime.now(timezone.utc).isoformat()}
