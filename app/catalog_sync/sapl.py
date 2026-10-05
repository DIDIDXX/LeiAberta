"""Paginated catalog synchronization for verified state and municipal SAPL installations."""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Jurisdiction, Law, SourceRegistry
from app.sources.network import RETRYABLE_HTTP_CODES


PAGE_SIZE = 100
MAX_BYTES = 10_000_000
MAX_AGE = timedelta(days=7)
logger = logging.getLogger("leiaberta.sapl_catalog")


@dataclass(frozen=True)
class SaplInstance:
    ibge_code: str
    municipality: str
    state_code: str
    host: str
    source_id: str
    source_name: str
    authority_url: str
    scope_kind: str = "municipality"
    federation_scope_filter: str | None = None

    @property
    def api(self) -> str:
        return f"{self.host}/api/norma"

    @property
    def norms_url(self) -> str:
        return f"{self.api}/normajuridica/"

    @property
    def types_url(self) -> str:
        return f"{self.api}/tiponormajuridica/"

    @property
    def jurisdiction_id(self) -> str:
        if self.scope_kind == "state":
            return f"state:{self.state_code}"
        return f"municipality:{self.ibge_code}"

    @property
    def external_namespace(self) -> str:
        # Preserve the identifiers already assigned to the production Manaus corpus.
        if self.ibge_code == "1302603":
            return "manaus"
        if self.scope_kind == "state":
            return f"state-{self.state_code.lower()}"
        return self.ibge_code

    @property
    def slug_prefix(self) -> str:
        if self.ibge_code == "1302603":
            return "manaus-sapl"
        if self.scope_kind == "state":
            return f"sapl-state-{self.state_code.lower()}"
        return f"sapl-{self.ibge_code}"


SAPL_INSTANCES = (
    # Verified from the Assembly's official site, which links to this SAPL instance.
    SaplInstance(
        ibge_code="27", municipality="", state_code="AL",
        host="https://sapl.al.al.leg.br", source_id="state:AL:sapl",
        source_name="Assembleia Legislativa do Estado de Alagoas — SAPL",
        authority_url="https://www.al.al.leg.br/", scope_kind="state", federation_scope_filter="E",
    ),
    SaplInstance(
        ibge_code="1302603", municipality="Manaus", state_code="AM",
        host="https://sapl.cmm.am.gov.br", source_id="municipality:1302603:sapl",
        source_name="Câmara Municipal de Manaus — SAPL", authority_url="https://www.cmm.am.gov.br/",
    ),
    SaplInstance(
        ibge_code="5201108", municipality="Anápolis", state_code="GO",
        host="https://sapl.anapolis.go.leg.br", source_id="municipality:5201108:sapl",
        source_name="Câmara Municipal de Anápolis — SAPL", authority_url="https://anapolis.go.leg.br/",
    ),
    SaplInstance(
        ibge_code="2504009", municipality="Campina Grande", state_code="PB",
        host="https://sapl.campinagrande.pb.leg.br", source_id="municipality:2504009:sapl",
        source_name="Câmara Municipal de Campina Grande — SAPL", authority_url="https://www.camaracg.pb.gov.br/",
    ),
    SaplInstance(
        ibge_code="3170404", municipality="Unaí", state_code="MG",
        host="https://sapl.unai.mg.leg.br", source_id="municipality:3170404:sapl",
        source_name="Câmara Municipal de Unaí — SAPL", authority_url="https://www.unai.mg.leg.br/",
    ),
    SaplInstance(
        ibge_code="3549102", municipality="São João da Boa Vista", state_code="SP",
        host="https://sapl.saojoaodaboavista.sp.leg.br", source_id="municipality:3549102:sapl",
        source_name="Câmara Municipal de São João da Boa Vista — SAPL",
        authority_url="https://www.saojoaodaboavista.sp.leg.br/",
    ),
    SaplInstance(
        ibge_code="2408102", municipality="Natal", state_code="RN",
        host="https://sapl.natal.rn.leg.br", source_id="municipality:2408102:sapl",
        source_name="Câmara Municipal de Natal — SAPL", authority_url="https://www.cmnat.rn.gov.br/",
    ),
    SaplInstance(
        ibge_code="22", municipality="", state_code="PI",
        host="https://sapl.al.pi.leg.br", source_id="state:PI:sapl",
        source_name="Assembleia Legislativa do Estado do Piauí — SAPL",
        authority_url="https://www.al.pi.leg.br/", scope_kind="state", federation_scope_filter="E",
    ),
)
SAPL_INSTANCES_BY_SOURCE = {item.source_id: item for item in SAPL_INSTANCES}
SAPL_INSTANCES_BY_HOST = {urllib.parse.urlparse(item.host).hostname: item for item in SAPL_INSTANCES}
SAPL_SOURCE_NAMES = frozenset(item.source_name for item in SAPL_INSTANCES)
DEFAULT_SAPL_INSTANCE = SAPL_INSTANCES[0]

# Compatibility aliases for existing callers and fixtures.
SAPL_HOST = DEFAULT_SAPL_INSTANCE.host
SAPL_API = DEFAULT_SAPL_INSTANCE.api
NORMS_URL = DEFAULT_SAPL_INSTANCE.norms_url
TYPES_URL = DEFAULT_SAPL_INSTANCE.types_url
SOURCE_ID = DEFAULT_SAPL_INSTANCE.source_id
SOURCE_NAME = DEFAULT_SAPL_INSTANCE.source_name


def sapl_instance_for_url(url: str) -> SaplInstance:
    parsed = urllib.parse.urlparse(url)
    instance = SAPL_INSTANCES_BY_HOST.get(parsed.hostname or "")
    if parsed.scheme != "https" or instance is None:
        raise ValueError("A URL não corresponde a uma instalação SAPL verificada.")
    return instance


@dataclass(frozen=True)
class SaplCatalogNorm:
    remote_id: str
    federation_scope: str
    law_type: str
    number: str
    year: int
    signed_at: date
    published_at: date | None
    title: str
    description: str
    source_url: str
    text_url: str | None


def _get_json(url: str, *, timeout: int = 45,
              instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> tuple[dict, str]:
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "LeiAberta/1.0 (+fontes oficiais)",
        "Connection": "close",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # urllib applies the timeout while opening the response. Set it
                # on the body socket too, so a stalled keep-alive read cannot
                # leave the catalog thread in "syncing" forever.
                response_file = getattr(response, "fp", None)
                raw_socket = getattr(getattr(response_file, "raw", None), "_sock", None)
                if raw_socket is None:
                    raw_socket = getattr(response_file, "_sock", None)
                if raw_socket is not None:
                    raw_socket.settimeout(timeout)
                body = response.read(MAX_BYTES + 1)
                final_url = response.geturl()
                status = response.status
            parsed = urllib.parse.urlparse(final_url)
            if (status != 200 or len(body) > MAX_BYTES or parsed.scheme != "https"
                    or parsed.hostname != urllib.parse.urlparse(instance.host).hostname):
                raise ValueError(f"A API SAPL de {instance.source_name} falhou, excedeu o limite ou redirecionou para domínio desconhecido.")
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                if attempt == 2:
                    raise ValueError(f"O SAPL de {instance.source_name} não retornou JSON válido após três tentativas.") from exc
                time.sleep(0.5 * (2 ** attempt))
                continue
            if not isinstance(payload, dict):
                raise ValueError(f"A API SAPL de {instance.source_name} retornou objeto inesperado.")
            return payload, final_url
        except HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_CODES and attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise ValueError(f"O SAPL de {instance.source_name} respondeu HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, ConnectionError, OSError, http.client.HTTPException) as exc:
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise ValueError(f"Falha de rede/leitura na API SAPL de {instance.source_name} após três tentativas: {str(exc)[:240]}") from exc
    raise ValueError(f"A API SAPL de {instance.source_name} não respondeu após três tentativas.")


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _official_media_url(value: object, *, instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> str | None:
    if not value:
        return None
    raw_url = str(value).strip()
    absolute_url = urllib.parse.urljoin(instance.host + "/", raw_url)
    url = urllib.parse.urlparse(absolute_url)
    allowed_path = (url.path.startswith("/media/sapl/public/normajuridica/")
                    or url.path.startswith("/sapl_documentos/norma_juridica/"))
    if (url.scheme in {"https", "http"}
            and url.hostname == urllib.parse.urlparse(instance.host).hostname
            and allowed_path and not url.query and not url.fragment):
        return urllib.parse.urlunparse(url._replace(scheme="https"))
    return None


def fetch_type_names(*, timeout: int = 45,
                     instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> dict[str, str]:
    url = instance.types_url + "?" + urllib.parse.urlencode({"page_size": 100, "page": 1})
    payload, _ = _get_json(url, timeout=timeout, instance=instance)
    pagination = payload.get("pagination") or {}
    total = pagination.get("total_entries")
    pages = pagination.get("total_pages")
    if not isinstance(total, int) or not isinstance(pages, int) or pages < 1:
        raise ValueError("O catálogo de tipos SAPL não informa paginação verificável.")
    records: dict[str, str] = {}
    for page in range(1, pages + 1):
        current = payload if page == 1 else _get_json(
            instance.types_url + "?" + urllib.parse.urlencode({"page_size": 100, "page": page}),
            timeout=timeout, instance=instance,
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


def fetch_catalog_page(page: int, *, page_size: int = PAGE_SIZE, timeout: int = 45,
                       instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> tuple[dict, str]:
    if page < 1 or not 1 <= page_size <= PAGE_SIZE:
        raise ValueError("Página ou tamanho inválido para o catálogo SAPL.")
    params = {"page_size": page_size, "page": page}
    if instance.federation_scope_filter:
        params["esfera_federacao"] = instance.federation_scope_filter
    url = instance.norms_url + "?" + urllib.parse.urlencode(params)
    payload, final_url = _get_json(url, timeout=timeout, instance=instance)
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


def parse_catalog_page(payload: dict, type_names: dict[str, str], *,
                       instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> list[SaplCatalogNorm]:
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
        # SAPL's ``ano`` is part of the norm's official designation and does not
        # always equal its signature date year (e.g. Emenda à Loman 6/1994,
        # signed on 1995-02-21). Preserve both official fields independently.
        federation_scope = str(item.get("esfera_federacao") or "").strip().upper()
        # Municipal SAPL installations can publish other spheres, while state
        # installations can expose municipal records without municipality
        # identity. Keep only records matching a configured API scope filter.
        if (not remote_id.isdigit() or len(remote_id) > 24 or not law_type or signed_at is None
                or federation_scope not in {"", "M", "E", "F"} or len(number) > 96
                or (instance.federation_scope_filter and federation_scope != instance.federation_scope_filter)):
            raise ValueError(f"Registro SAPL sem identidade ou abrangência verificável: id={remote_id!r}.")
        title = str(item.get("__str__") or f"{law_type} {number}/{year}").strip()
        records.append(SaplCatalogNorm(
            remote_id=remote_id, federation_scope=federation_scope,
            law_type=law_type, number=number, year=year, signed_at=signed_at,
            published_at=_date(item.get("data_publicacao")), title=title[:300],
            description=str(item.get("ementa") or "").strip(),
            source_url=f"{instance.norms_url}{remote_id}/",
            text_url=_official_media_url(item.get("texto_integral"), instance=instance),
        ))
    ids = [record.remote_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Página SAPL contém identificador remoto duplicado.")
    return records


def sync_catalog_page(session: Session, records: list[SaplCatalogNorm], *, observed_at: datetime,
                     instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> dict:
    if not records:
        raise ValueError("Não é permitido persistir uma página SAPL vazia.")
    external_ids = [f"sapl:{instance.external_namespace}:{item.remote_id}" for item in records]
    existing = list(session.scalars(select(Law).where(Law.external_source_id.in_(external_ids))))
    by_external = {law.external_source_id: law for law in existing}
    added = refreshed = 0
    for item in records:
        external_id = f"sapl:{instance.external_namespace}:{item.remote_id}"
        law = by_external.get(external_id)
        jurisdiction = {"M": "municipality", "E": "state", "F": "federal"}.get(
            item.federation_scope, instance.scope_kind,
        )
        state_code = instance.state_code if jurisdiction in {"state", "municipality"} else None
        municipality = instance.municipality if jurisdiction == "municipality" else None
        coverage = {
            "official_source": f"sapl_{instance.scope_kind}",
            "sapl_source_ibge_code": instance.ibge_code,
            "sapl_source_scope_kind": instance.scope_kind,
            "sapl_federation_scope": item.federation_scope or "not_declared",
            "jurisdiction_basis": "sapl_esfera_federacao" if item.federation_scope else "official_sapl_instance",
            "source_id": item.remote_id,
            "text_url_in_catalog": bool(item.text_url),
            "structured_text": "not_materialized", "history": "not_requested",
            "catalog_observed_at": observed_at.isoformat(),
        }
        if jurisdiction == "municipality":
            coverage["municipality_ibge_code"] = instance.ibge_code
        if law is None:
            law = Law(
                slug=f"{instance.slug_prefix}-{item.remote_id}", jurisdiction=jurisdiction,
                state_code=state_code, municipality=municipality,
                law_type=item.law_type, number=item.number, year=item.year,
                external_source_id=external_id, signed_at=item.signed_at, title=item.title,
                description=item.description, status="Não verificado", published_at=item.published_at,
                aliases=[external_id], source_name=instance.source_name, source_url=item.source_url,
                fetch_url=item.text_url or item.source_url, hot=False, materialization_status="catalog",
                current_version_id=None, coverage=coverage,
            )
            session.add(law)
            by_external[external_id] = law
            added += 1
        else:
            if law.source_name != instance.source_name:
                raise ValueError(f"Identificador SAPL {item.remote_id} já pertence a outra fonte.")
            law.jurisdiction = jurisdiction
            law.state_code = state_code
            law.municipality = municipality
            law.law_type, law.number, law.year = item.law_type, item.number, item.year
            law.signed_at, law.published_at = item.signed_at, item.published_at
            law.title, law.description = item.title, item.description
            law.source_url, law.fetch_url = item.source_url, item.text_url or item.source_url
            previous_coverage = dict(law.coverage or {})
            coverage.update(previous_coverage)
            coverage.update({
                "sapl_source_ibge_code": instance.ibge_code,
                "sapl_source_scope_kind": instance.scope_kind,
                "sapl_federation_scope": item.federation_scope or "not_declared",
                "jurisdiction_basis": "sapl_esfera_federacao" if item.federation_scope else "official_sapl_instance",
                "source_id": item.remote_id,
                "text_url_in_catalog": bool(item.text_url),
            })
            if jurisdiction == "municipality":
                coverage["municipality_ibge_code"] = instance.ibge_code
            else:
                coverage.pop("municipality_ibge_code", None)
            # Keep catalog_observed_at on new records only. SourceRegistry
            # tracks refresh time; rewriting unrelated coverage can conflict
            # with a hydration job updating the same row.
            if coverage != previous_coverage:
                law.coverage = coverage
            # Keep catalog_observed_at on new records only. SourceRegistry
            # tracks refresh time; rewriting each law's shared coverage JSON
            # collides with hydration jobs updating that same row.
            refreshed += 1
    return {"added": added, "refreshed": refreshed}


def _limit_catalog_page_transaction(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(text("SET LOCAL lock_timeout = '15s'"))
    session.execute(text("SET LOCAL statement_timeout = '90s'"))


def _source_is_fresh(instance: SaplInstance = DEFAULT_SAPL_INSTANCE) -> bool:
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, instance.source_id)
        checked = registry.last_checked_at if registry else None
        if registry is None or registry.status != "enumerated" or checked is None:
            return False
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked > datetime.now(timezone.utc) - MAX_AGE


def sync_sapl_catalog(instance: SaplInstance = DEFAULT_SAPL_INSTANCE, *, force: bool = False) -> dict:
    if not force and _source_is_fresh(instance):
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, instance.source_id)
            return {"source_id": instance.source_id, "skipped_fresh": True,
                    "records": (registry.scope or {}).get("records_enumerated", 0)}
    observed_at = datetime.now(timezone.utc)
    types = fetch_type_names(instance=instance)
    first, catalog_url = fetch_catalog_page(1, instance=instance)
    pagination = first["pagination"]
    total, pages = pagination["total_entries"], pagination["total_pages"]
    if total < 1 or pages < 1 or pages > total:
        raise ValueError("O catálogo SAPL retornou universo ou paginação inválida.")
    logger.info("sapl_catalog_sync_started source=%s source_id=%s expected_records=%s expected_pages=%s",
                instance.source_name, instance.source_id, total, pages)
    scope = {"universe": f"Registros normajuridica publicados na instalação SAPL oficial da {instance.source_name}; a esfera declarada por registro é preservada.",
             "records_expected": total, "pages_expected": pages, "page_size": PAGE_SIZE,
             "type_count": len(types), "federation_scope_filter": instance.federation_scope_filter,
             "records_enumerated": 0, "started_at": observed_at.isoformat()}
    if instance.scope_kind == "municipality":
        scope["municipality_ibge_code"] = instance.ibge_code
    else:
        scope["state_ibge_code"] = instance.ibge_code
    with SessionLocal() as session:
        registry = session.get(SourceRegistry, instance.source_id)
        if registry is None:
            registry = SourceRegistry(id=instance.source_id, name=instance.source_name,
                                      adapter="sapl_catalog", base_url=instance.norms_url,
                                      evidence_url=instance.authority_url, status="syncing", scope={})
            session.add(registry)
        registry.jurisdiction_id = instance.jurisdiction_id if session.get(Jurisdiction, instance.jurisdiction_id) else None
        registry.name, registry.adapter, registry.base_url = instance.source_name, "sapl_catalog", catalog_url
        registry.evidence_url, registry.status, registry.scope, registry.last_error = instance.authority_url, "syncing", scope, ""
        registry.last_checked_at = observed_at
        session.commit()

    seen: set[str] = set()
    digest = hashlib.sha256()
    added = refreshed = enumerated = 0
    federation_counts = {"M": 0, "E": 0, "F": 0, "not_declared": 0}
    try:
        for page in range(1, pages + 1):
            logger.info("sapl_catalog_page_fetch_started page=%s total_pages=%s", page, pages)
            payload = first if page == 1 else fetch_catalog_page(page, instance=instance)[0]
            current = payload["pagination"]
            if current["total_entries"] != total or current["total_pages"] != pages:
                raise ValueError("O total SAPL mudou durante a paginação.")
            records = parse_catalog_page(payload, types, instance=instance)
            logger.info("sapl_catalog_page_fetched page=%s records=%s", page, len(records))
            if page < pages and len(records) != PAGE_SIZE:
                raise ValueError(f"Página SAPL truncada {page}: {len(records)} de {PAGE_SIZE}.")
            for item in records:
                if item.remote_id in seen:
                    raise ValueError(f"Identificador SAPL repetido entre páginas: {item.remote_id}.")
                seen.add(item.remote_id)
                digest.update(item.remote_id.encode() + b"\n")
                federation_counts[item.federation_scope or "not_declared"] += 1
            with SessionLocal() as session:
                # Bound waits so one stalled write cannot strand the source
                # registry in "syncing" indefinitely.
                _limit_catalog_page_transaction(session)
                logger.info("sapl_catalog_page_persist_started page=%s records=%s", page, len(records))
                counts = sync_catalog_page(session, records, observed_at=observed_at, instance=instance)
                logger.info("sapl_catalog_page_flush_started page=%s", page)
                session.flush()
                logger.info("sapl_catalog_page_rows_flushed page=%s added=%s refreshed=%s",
                            page, counts["added"], counts["refreshed"])
                added += counts["added"]
                refreshed += counts["refreshed"]
                enumerated += len(records)
                registry = session.get(SourceRegistry, instance.source_id)
                registry.scope = {**scope, "records_enumerated": enumerated, "last_page": page,
                                  "records_by_federation_scope": dict(federation_counts),
                                  "catalog_ids_sha256_partial": digest.hexdigest()}
                registry.last_checked_at = observed_at
                logger.info("sapl_catalog_page_commit_started page=%s enumerated=%s", page, enumerated)
                session.commit()
            logger.info("sapl_catalog_page_committed page=%s enumerated=%s", page, enumerated)
    except Exception as exc:
        with SessionLocal() as session:
            registry = session.get(SourceRegistry, instance.source_id)
            if registry:
                registry.status, registry.last_error = "failed", str(exc)[:1000]
                registry.scope = {**(registry.scope or {}), "records_enumerated": enumerated,
                                  "records_by_federation_scope": dict(federation_counts),
                                  "last_page": max(0, len(seen) // PAGE_SIZE),
                                  "last_attempt_at": datetime.now(timezone.utc).isoformat()}
                registry.last_checked_at = datetime.now(timezone.utc)
                session.commit()
        raise
    if enumerated != total or len(seen) != total:
        raise ValueError(f"Catálogo SAPL incompleto: {enumerated} de {total} registros.")
    with SessionLocal() as session:
        external_prefix = f"sapl:{instance.external_namespace}:%"
        db_total = session.scalar(select(func.count()).select_from(Law).where(Law.external_source_id.like(external_prefix))) or 0
        registry = session.get(SourceRegistry, instance.source_id)
        registry.status = "enumerated"
        registry.scope = {**scope, "records_enumerated": enumerated, "records_in_database": db_total,
                          "records_by_federation_scope": dict(federation_counts),
                          "last_page": pages, "catalog_ids_sha256": digest.hexdigest(),
                          "observed_at": datetime.now(timezone.utc).isoformat()}
        registry.last_checked_at = datetime.now(timezone.utc)
        registry.last_error = ""
        session.commit()
    return {"source_id": instance.source_id, "records": enumerated, "expected": total, "pages": pages, "added": added,
            "refreshed": refreshed, "catalog_ids_sha256": digest.hexdigest()}


def sync_sapl_manaus_catalog(*, force: bool = False) -> dict:
    """Compatibility wrapper for the original SAPL adapter entrypoint."""
    return sync_sapl_catalog(DEFAULT_SAPL_INSTANCE, force=force)


def sync_all_sapl_catalogs(*, force: bool = False) -> dict:
    results = []
    errors = []
    for instance in SAPL_INSTANCES:
        try:
            results.append(sync_sapl_catalog(instance, force=force))
        except Exception as exc:
            error = str(exc)[:500]
            errors.append({"source_id": instance.source_id, "error": error})
            logger.exception("sapl_catalog_sync_failed source_id=%s source=%s",
                             instance.source_id, instance.source_name)
    return {"synced": results, "errors": errors,
            "records": sum(row.get("records", 0) for row in results),
            "skipped_fresh": sum(bool(row.get("skipped_fresh")) for row in results)}
