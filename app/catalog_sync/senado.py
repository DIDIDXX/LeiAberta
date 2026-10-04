"""Enumerate the federal laws exposed by the Senate's official API."""
from __future__ import annotations

import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Jurisdiction, Law, SourceRegistry

SENATE_LIST_URL = "https://legis.senado.leg.br/dadosabertos/legislacao/lista?tipo=LEI"
MAX_CATALOG_BYTES = 20_000_000


@dataclass(frozen=True)
class SenadoCatalogLaw:
    remote_id: str
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


def fetch_law_catalog(*, timeout: int = 60) -> tuple[bytes, str]:
    request = urllib.request.Request(
        SENATE_LIST_URL,
        headers={"Accept": "application/xml", "User-Agent": "LeiAberta/0.3 (+fontes oficiais)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_CATALOG_BYTES + 1)
        if response.status != 200 or len(body) > MAX_CATALOG_BYTES:
            raise ValueError("A lista federal do Senado excedeu o limite de tamanho ou falhou.")
        return body, response.geturl()


def parse_law_catalog(body: bytes, *, base_url: str = "https://legis.senado.leg.br/dadosabertos",
                      minimum_records: int = 1_000) -> list[SenadoCatalogLaw]:
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
        number = re.sub(r"\D", "", (entry.findtext("numero") or ""))
        year = int(year_text) if year_text.isdigit() else None
        title = (entry.findtext("normaNome") or "").strip()
        if not remote_id.isdigit() or year is None or not 1800 <= year <= 2200 or not title:
            raise ValueError(f"O catálogo Senado contém um registro sem identidade mínima: id={remote_id!r} ano={year_text!r}")
        if remote_id in seen:
            raise ValueError(f"Identificador Senado duplicado no catálogo: {remote_id}")
        seen.add(remote_id)
        source_urn = (entry.findtext("norma") or "").strip()
        results.append(SenadoCatalogLaw(
            remote_id=remote_id, number=_format_number(number), year=year,
            signed_at=_date(entry.findtext("dataassinatura") or ""),
            title=title[:300], description=(entry.findtext("ementa") or "").strip(),
            source_url=f"{base_url.rstrip('/')}/legislacao/{remote_id}", source_urn=source_urn,
        ))
    if not results:
        raise ValueError("Nenhuma lei do Senado tinha identidade mínima válida.")
    return results


def sync_law_catalog(session: Session, records: list[SenadoCatalogLaw]) -> dict:
    """Idempotently sync list metadata; does not claim the Senate list is every federal act."""
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
            existing.signed_at = record.signed_at
            if existing.source_name.startswith("Senado Federal"):
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

        identity = ("lei", re.sub(r"\D", "", record.number), record.year)
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
            slug=slug, jurisdiction="federal", law_type="Lei", number=record.number,
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
    registry = session.get(SourceRegistry, "federal:senado:leis")
    if registry is None:
        registry = SourceRegistry(
            id="federal:senado:leis", name="Senado Federal — catálogo de leis",
            adapter="senado_catalog", base_url=SENATE_LIST_URL,
            evidence_url="https://legis.senado.leg.br/dadosabertos/v3/api-docs",
            scope={}, status="discovered", last_error="",
        )
        session.add(registry)
    registry.jurisdiction_id = "federal" if session.get(Jurisdiction, "federal") else None
    registry.name = "Senado Federal — catálogo de leis"
    registry.adapter = "senado_catalog"
    registry.base_url = SENATE_LIST_URL
    registry.evidence_url = "https://legis.senado.leg.br/dadosabertos/v3/api-docs"
    registry.scope = {"normative_class": "Lei", "records_enumerated": len(records),
                      "universe": "Senado API records returned by tipo=LEI; excludes other normative type codes and jurisdictions"}
    registry.status = "enumerated"
    registry.last_checked_at = now
    registry.last_error = ""
    session.commit()
    digest = hashlib.sha256("\n".join(record.remote_id for record in records).encode()).hexdigest()
    return {"source": SENATE_LIST_URL, "listed": len(records), "added": added,
            "attached_to_seed": attached, "refreshed": refreshed,
            "catalog_ids_sha256": digest, "observed_at": now.isoformat()}


def sync_senado_law_catalog() -> dict:
    from app.db import SessionLocal

    body, url = fetch_law_catalog()
    records = parse_law_catalog(body, base_url=url.rsplit("/legislacao/", 1)[0])
    with SessionLocal() as session:
        result = sync_law_catalog(session, records)
        result["source_response_sha256"] = hashlib.sha256(body).hexdigest()
        return result
