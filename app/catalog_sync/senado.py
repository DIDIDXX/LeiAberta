"""Enumerate the federal laws exposed by the Senate's official API."""
from __future__ import annotations

import hashlib
import http.client
import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Jurisdiction, Law, SourceRegistry

SENATE_LIST_BASE = "https://legis.senado.leg.br/dadosabertos/legislacao/lista"
MAX_CATALOG_BYTES = 20_000_000
CATALOG_MAX_AGE = timedelta(hours=24)
SENADO_DECRETO_START_YEAR = 1800
YEAR_PARTITIONED_TYPES = frozenset({"DEC-n"})
logger = logging.getLogger(__name__)

# These exact type codes were confirmed against the official Senate API. The
# endpoint also exposes administrative documents and subnational categories;
# this list limits ingestion to enacted federal norms and constituent acts.
TYPE_LABELS = {
    "LEI": "Lei",
    "LCP": "Lei Complementar",
    "EMC": "Emenda Constitucional",
    "MPV": "Medida Provisória",
    "DLG": "Decreto Legislativo",
    "RSF": "Resolução do Senado Federal",
    "DEL": "Decreto-Lei",
    "LCT": "Lei Constitucional",
    "LDL": "Lei Delegada",
    "RCN": "Resolução do Congresso Nacional",
    "RCD": "Resolução da Câmara dos Deputados",
    "RRC": "Resolução da Revisão Constitucional",
    "EMR": "Emenda Constitucional de Revisão",
    "ACP": "Ato Complementar",
    "DEC-n": "Decreto",
    "DEC-sn": "Decreto não Numerado",
    "DLN": "Decreto Legislativo do Congresso Nacional",
    "CON-v": "Constituição Federal vigente",
    "CON-nv": "Constituição Federal anterior",
    "ADCT": "Ato das Disposições Constitucionais Transitórias",
    "RAC": "Regimento Interno da Assembleia Constituinte",
    "RISF": "Regimento Interno do Senado Federal",
    "AILEI": "Ato Internacional com Força de Lei",
    "AIEMC": "Ato Internacional com Força de Emenda Constitucional",
}
MINIMUM_RECORDS = {
    "LEI": 1_000, "LCP": 100, "EMC": 100, "MPV": 1_000, "DLG": 5_000, "RSF": 1_000,
    "DEL": 10_000, "LCT": 15, "LDL": 10, "RCN": 60, "RCD": 1_500,
    "RRC": 2, "EMR": 4, "ACP": 80, "DEC-n": 0, "DEC-sn": 10_000,
    "DLN": 150, "CON-v": 1, "CON-nv": 5, "ADCT": 1, "RAC": 2,
    "RISF": 1, "AILEI": 800, "AIEMC": 4,
}


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


def fetch_law_catalog(type_code: str = "LEI", *, year: int | None = None,
                      timeout: int = 60) -> tuple[bytes, str]:
    if type_code not in TYPE_LABELS:
        raise ValueError(f"Tipo do catálogo Senado não validado: {type_code}")
    query = {"tipo": type_code}
    if year is not None:
        if not 1800 <= year <= datetime.now(timezone.utc).year:
            raise ValueError(f"Ano de partição do Senado fora do intervalo suportado: {year}")
        query["ano"] = str(year)
    url = f"{SENATE_LIST_BASE}?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/xml", "User-Agent": "LeiAberta/0.3 (+fontes oficiais)"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(MAX_CATALOG_BYTES + 1)
                final_url = response.geturl()
                status = response.status
            if status != 200 or len(body) > MAX_CATALOG_BYTES:
                raise ValueError("A lista federal do Senado excedeu o limite de tamanho ou falhou.")
            try:
                ET.fromstring(body)
            except ET.ParseError as exc:
                if attempt == 2:
                    raise ValueError("O Senado retornou XML incompleto ou inválido após três tentativas.") from exc
                time.sleep(0.5 * (2 ** attempt))
                continue
            return body, final_url
        except HTTPError as exc:
            if exc.code not in {408, 425, 429, 500, 502, 503, 504} or attempt == 2:
                raise ValueError(f"A lista federal do Senado respondeu HTTP {exc.code}.") from exc
        except (http.client.HTTPException, TimeoutError, ConnectionError, OSError) as exc:
            if attempt == 2:
                raise ValueError(f"Resposta incompleta da lista federal do Senado após três tentativas: {str(exc)[:240]}") from exc
        time.sleep(0.5 * (2 ** attempt))
    raise ValueError("A lista federal do Senado não respondeu após três tentativas.")


def parse_law_catalog(body: bytes, *, type_code: str = "LEI",
                      base_url: str = "https://legis.senado.leg.br/dadosabertos",
                      minimum_records: int | None = None, expected_year: int | None = None,
                      allow_empty: bool = False) -> list[SenadoCatalogLaw]:
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
    seen: dict[str, SenadoCatalogLaw] = {}
    for entry in entries:
        remote_id = (entry.get("id") or "").strip()
        year_text = (entry.findtext("anoassinatura") or "").strip()
        number = entry.findtext("numero") or ""
        year = int(year_text) if year_text.isdigit() else None
        title = (entry.findtext("normaNome") or "").strip()
        if not remote_id.isdigit() or year is None or not 1800 <= year <= 2200 or not title:
            raise ValueError(f"O catálogo Senado contém um registro sem identidade mínima: id={remote_id!r} ano={year_text!r}")
        if expected_year is not None and year != expected_year:
            raise ValueError(f"A partição Senado de {expected_year} contém registro de {year} (id={remote_id}).")
        source_urn = (entry.findtext("norma") or "").strip()
        record = SenadoCatalogLaw(
            remote_id=remote_id, type_code=type_code, law_type=TYPE_LABELS[type_code],
            number=_official_number(number, title), year=year,
            signed_at=_date(entry.findtext("dataassinatura") or ""),
            title=title[:300], description=(entry.findtext("ementa") or "").strip(),
            source_url=f"{base_url.rstrip('/')}/legislacao/{remote_id}", source_urn=source_urn,
        )
        duplicate = seen.get(remote_id)
        if duplicate is not None:
            if duplicate != record:
                raise ValueError(f"Identificador Senado duplicado com metadados conflitantes: {remote_id}")
            continue
        seen[remote_id] = record
        results.append(record)
    if not results and not allow_empty:
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
    remote_ids = [record.remote_id for record in records]
    record_years = {record.year for record in records}
    record_types = {record.law_type.casefold() for record in records}
    identity_numbers = {record.number for record in records}
    identity_numbers.update(re.sub(r"\D", "", record.number) for record in records
                            if re.search(r"\d", record.number))
    laws_by_slug = {
        law.slug: law
        for law in session.scalars(select(Law).where(or_(
            Law.external_source_id.in_(remote_ids),
            # Include only possible identity collisions. The Python check below
            # still compares normalized number digits before attaching a seed.
            (func.lower(Law.law_type).in_(record_types)
             & Law.year.in_(record_years)
             & Law.number.in_(identity_numbers)),
        )))
    }
    laws = list(laws_by_slug.values())
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
            partition_years: list[int] = []
            if type_code in YEAR_PARTITIONED_TYPES:
                first_year = SENADO_DECRETO_START_YEAR
                last_year = datetime.now(timezone.utc).year
                records = []
                partition_digests = []
                seen_remote_ids = set()
                for year in range(first_year, last_year + 1):
                    body, _partition_url = fetch_law_catalog(type_code, year=year)
                    year_records = parse_law_catalog(
                        body, type_code=type_code,
                        base_url="https://legis.senado.leg.br/dadosabertos",
                        minimum_records=0, expected_year=year, allow_empty=True,
                    )
                    for record in year_records:
                        if record.remote_id in seen_remote_ids:
                            raise ValueError(f"Identificador Senado repetido entre partições anuais: {record.remote_id}")
                        seen_remote_ids.add(record.remote_id)
                    records.extend(year_records)
                    partition_years.append(year)
                    partition_digests.append(f"{year}:{hashlib.sha256(body).hexdigest()}")
                    if year % 10 == 0 or year == last_year:
                        logger.info("senado_catalog_year_partition_finished type=%s year=%s records=%s",
                                    type_code, year, len(year_records))
                if not records:
                    raise ValueError(f"O catálogo Senado não retornou registros para tipo={type_code}.")
                records.sort(key=lambda item: (item.year, item.remote_id))
                url = f"{SENATE_LIST_BASE}?tipo={type_code}"
                source_response_sha256 = hashlib.sha256("\n".join(partition_digests).encode()).hexdigest()
            else:
                body, url = fetch_law_catalog(type_code)
                records = parse_law_catalog(body, type_code=type_code,
                                            base_url="https://legis.senado.leg.br/dadosabertos")
                source_response_sha256 = hashlib.sha256(body).hexdigest()
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
            result["source_response_sha256"] = source_response_sha256
            if partition_years:
                result["partition_year_start"] = partition_years[0]
                result["partition_year_end"] = partition_years[-1]
                result["partitions_completed"] = len(partition_years)
                with SessionLocal() as session:
                    registry = session.get(SourceRegistry, _source_id(type_code))
                    if registry:
                        scope = dict(registry.scope or {})
                        scope.update({
                            "partition_strategy": "signature_year",
                            "partition_year_start": partition_years[0],
                            "partition_year_end": partition_years[-1],
                            "partitions_completed": len(partition_years),
                            "catalog_ids_sha256": result["catalog_ids_sha256"],
                            "source_responses_sha256": source_response_sha256,
                        })
                        registry.scope = scope
                        session.commit()
            results.append(result)
        except Exception as exc:
            error = str(exc)[:300]
            errors.append({"type_code": type_code, "error": error})
            logger.exception("senado_catalog_type_sync_failed type_code=%s", type_code)
            with SessionLocal() as session:
                registry = session.get(SourceRegistry, _source_id(type_code))
                if registry is None:
                    registry = SourceRegistry(
                        id=_source_id(type_code), name=f"Senado Federal — catálogo {TYPE_LABELS[type_code]}",
                        adapter="senado_catalog", base_url=f"{SENATE_LIST_BASE}?tipo={type_code}",
                        evidence_url="https://legis.senado.leg.br/dadosabertos/v3/api-docs",
                        scope={"normative_class": TYPE_LABELS[type_code], "senate_type_code": type_code},
                        status="failed", last_error=error,
                    )
                    session.add(registry)
                else:
                    registry.status = "stale"
                    registry.last_error = error
                session.commit()
    return {"synced": results, "skipped_fresh": skipped, "errors": errors,
            "listed": sum(item["listed"] for item in results),
            "added": sum(item["added"] for item in results),
            "observed_at": datetime.now(timezone.utc).isoformat()}
