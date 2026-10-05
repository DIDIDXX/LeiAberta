from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from html import escape as html_escape
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from anyio import to_thread
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from xml.sax.saxutils import escape

from app.db import get_session
from app.audit import audit_archived_document
from app.jobs import queue_history, queue_hydration, queue_provenance
from app.catalog_sync.sapl import SAPL_SOURCE_NAMES
from app.models import HistoryEvent, HydrationJob, Jurisdiction, Law, LawChange, LawVersion, LegalNode, SenateProceeding, SourceRegistry, SourceSnapshot
from app.search import search_laws

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.api")
ROOT = Path(__file__).resolve().parent.parent
TEXT_SOURCE_NAMES = {
    "Presidência da República — Planalto",
    "Senado Federal — Dados Abertos Legislativos",
    "Assembleia Legislativa do Estado de São Paulo — ALESP",
    "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
    "Câmara Municipal de Manaus — SAPL",
} | set(SAPL_SOURCE_NAMES)
app = FastAPI(title="LeiAberta", version="0.1.0", description="Catálogo e histórico público de legislação brasileira.")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@lru_cache(maxsize=1)
def _rate_limit_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


def _rate_limit_policy(method: str, path: str) -> tuple[str, int, int] | None:
    if method == "GET" and path == "/api/search":
        return "search", 600, 60
    parts = path.strip("/").split("/")
    if method == "GET" and len(parts) >= 3 and parts[:2] == ["api", "laws"]:
        if len(parts) == 3 or parts[-1] in {"nodes", "blame", "provenance"} or "provenance" in parts:
            return "law-detail", 240, 60
    if method == "POST" and len(parts) == 5 and parts[:2] == ["api", "laws"]:
        if parts[3:] in (["history", "prepare"], ["proceedings", "prepare"]):
            return "job-prepare", 60, 60
    if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "laws"] and parts[3] == "hydrate":
        return "job-prepare", 60, 60
    return None


def _consume_rate_budget(scope: str, limit: int, window_seconds: int, now: int | None = None) -> tuple[int, int]:
    current = int(time.time()) if now is None else now
    bucket = current // window_seconds
    retry_after = window_seconds - (current % window_seconds)
    key = f"leiaberta:rate-limit:{scope}:{bucket}"
    count = int(_rate_limit_redis(os.environ["REDIS_URL"]).eval(_RATE_LIMIT_SCRIPT, 1, key, retry_after + 2))
    return count, retry_after


def _public_base_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if configured:
        return configured
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{scheme}://{host}"


@app.middleware("http")
async def public_rate_limit(request: Request, call_next):
    policy = _rate_limit_policy(request.method, request.url.path)
    redis_url = os.getenv("REDIS_URL")
    if policy and redis_url:
        scope, limit, window_seconds = policy
        try:
            count, retry_after = await to_thread.run_sync(
                _consume_rate_budget, scope, limit, window_seconds,
            )
            if count > limit:
                return JSONResponse(
                    {"detail": "Limite temporário de solicitações atingido."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
        except RedisError:
            # Reads and job endpoints remain available during Redis outages;
            # queue dedupe/backpressure are the independent fallback.
            logger.warning("rate_limit_store_unavailable scope=%s", scope)
    return await call_next(request)


@app.middleware("http")
async def baseline_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; connect-src 'self'; font-src 'self' data: https://fonts.gstatic.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    )
    if request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


def _law_summary(law: Law, article_count: int | None = None) -> dict:
    return {
        "slug": law.slug,
        "title": law.title,
        "law_type": law.law_type,
        "number": law.number,
        "year": law.year,
        "jurisdiction": law.jurisdiction,
        "state_code": law.state_code,
        "municipality": law.municipality,
        "status": law.status,
        "description": law.description,
        "published_at": law.published_at.isoformat() if law.published_at else None,
        "signed_at": law.signed_at.isoformat() if law.signed_at else None,
        "external_source_id": law.external_source_id,
        "source_name": law.source_name,
        "source_url": law.source_url,
        "aliases": law.aliases,
        "hot": law.hot,
        "materialization_status": law.materialization_status,
        "last_hydrated_at": law.last_hydrated_at.isoformat() if law.last_hydrated_at else None,
        "coverage": law.coverage or {},
        "article_count": article_count,
    }


def _node_payload(node: LegalNode) -> dict:
    return {
        "id": node.node_id,
        "parent_id": node.parent_node_id,
        "type": node.node_type,
        "label": node.label,
        "text": node.text,
        "order": node.order_index,
    }


def _change_evidence(item: LawChange) -> dict:
    """Describe stored text comparisons without upgrading a catalog link to primary evidence."""
    try:
        host = (urlsplit(item.source_url).hostname or "").lower()
    except ValueError:
        host = ""
    primary_hosts = (
        "planalto.gov.br", "legis.senado.leg.br", "camara.leg.br",
        "al.sp.gov.br", "sinj.df.gov.br",
    )
    primary = any(host == domain or host.endswith("." + domain) for domain in primary_hosts)
    comparison = bool(item.after_text) and (bool(item.before_text) or item.change_type == "ADD")
    return {
        "level": "verified_primary" if primary and comparison else "verified_source" if comparison else "partial",
        "label": "Fonte primária confirmada" if primary and comparison else "Comparação registrada" if comparison else "Evidência parcial",
        "comparison_available": comparison,
        "source_host": host,
        "evidence_marker": item.evidence_marker,
    }


@app.get("/health", include_in_schema=False)
def health(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "service": "leiaberta-api"}


@app.get("/ready", include_in_schema=False)
def readiness(session: Session = Depends(get_session)):
    """Readiness check: the database is reachable and has the current schema."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    try:
        applied_heads = set(session.scalars(text("SELECT version_num FROM alembic_version")).all())
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database schema is unavailable") from exc
    expected_heads = set(ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads())
    if applied_heads != expected_heads:
        raise HTTPException(status_code=503, detail="Database schema is not current")
    return {"status": "ready", "service": "leiaberta-api"}


@app.get("/worker-health", include_in_schema=False)
def worker_health():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise HTTPException(status_code=503, detail="Worker heartbeat is unavailable")
    try:
        heartbeat = _rate_limit_redis(redis_url).get("leiaberta:worker:heartbeat")
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Worker heartbeat is unavailable") from exc
    try:
        heartbeat_at = datetime.fromisoformat(heartbeat) if heartbeat else None
    except ValueError:
        heartbeat_at = None
    if heartbeat_at is None or (datetime.now(timezone.utc) - heartbeat_at).total_seconds() > 90:
        raise HTTPException(status_code=503, detail="Worker heartbeat is stale")
    return {"status": "ok", "service": "leiaberta-worker", "heartbeat_at": heartbeat_at.isoformat()}


@app.get("/api/health")
def api_health(session: Session = Depends(get_session)):
    return health(session)


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    # One grouped pass replaces one COUNT per discovered SAPL instance. With
    # hundreds of source registries, the old per-source loop rescanned the
    # large laws table hundreds of times and made this public endpoint stall.
    law_counts = session.execute(select(
        Law.source_name,
        func.count().label("total"),
        func.sum(case((Law.current_version_id.is_not(None), 1), else_=0)).label("materialized"),
        func.sum(case((Law.materialization_status == "unavailable", 1), else_=0)).label("unavailable"),
    ).group_by(Law.source_name)).all()
    counts_by_source = {
        source_name: {"total": int(total), "with_text": int(with_text or 0), "unavailable": int(unavailable or 0)}
        for source_name, total, with_text, unavailable in law_counts
    }
    indexed = sum(row["total"] for row in counts_by_source.values())
    materialized = sum(row["with_text"] for row in counts_by_source.values())
    articles = session.scalar(select(func.count()).select_from(LegalNode).join(
        Law, LegalNode.law_slug == Law.slug,
    ).where(LegalNode.node_type == "article", LegalNode.version_id == Law.current_version_id)) or 0
    changes = session.scalar(select(func.count()).select_from(LawChange)) or 0
    source_registry_count = session.scalar(select(func.count()).select_from(SourceRegistry)) or 0
    integrated_source_count = session.scalar(select(func.count()).select_from(SourceRegistry).where(
        SourceRegistry.status == "enumerated",
    )) or 0
    senate = counts_by_source.get("Senado Federal — Dados Abertos Legislativos", {})
    senate_total = senate.get("total", 0)
    senate_with_text = senate.get("with_text", 0)
    senate_unavailable = senate.get("unavailable", 0)
    senate_active = session.scalar(select(func.count()).select_from(HydrationJob).join(
        Law, HydrationJob.law_slug == Law.slug,
    ).where(
        Law.source_name == "Senado Federal — Dados Abertos Legislativos",
        HydrationJob.job_type == "hydrate", HydrationJob.status.in_(["queued", "running"]),
    )) or 0
    subnational_catalogs = {}
    for source_id, source_name in (
        ("state:SP:alesp", "Assembleia Legislativa do Estado de São Paulo — ALESP"),
        ("state:DF:sinj", "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF"),
        ("municipality:1302603:sapl", "Câmara Municipal de Manaus — SAPL"),
    ):
        counts = counts_by_source.get(source_name, {})
        total, with_text, unavailable = counts.get("total", 0), counts.get("with_text", 0), counts.get("unavailable", 0)
        subnational_catalogs[source_id] = {
            "source_name": source_name, "catalog_laws": total, "with_text": with_text,
            "unavailable": unavailable, "pending": max(0, total - with_text - unavailable),
        }
    known_catalog_ids = set(subnational_catalogs)
    for registry in session.scalars(select(SourceRegistry).where(SourceRegistry.adapter == "sapl_catalog")):
        if registry.id in known_catalog_ids:
            continue
        counts = counts_by_source.get(registry.name, {})
        total, with_text, unavailable = counts.get("total", 0), counts.get("with_text", 0), counts.get("unavailable", 0)
        subnational_catalogs[registry.id] = {
            "source_name": registry.name, "catalog_laws": total, "with_text": with_text,
            "unavailable": unavailable, "pending": max(0, total - with_text - unavailable),
        }
    return {
        "indexed_laws": indexed,
        "materialized_laws": materialized,
        "structured_articles": articles,
        "documented_changes": changes,
        "configured_sources": source_registry_count,
        "enumerated_sources": integrated_source_count,
        "senado_text": {
            "catalog_laws": senate_total,
            "with_text": senate_with_text,
            "unavailable": senate_unavailable,
            "pending": max(0, senate_total - senate_with_text - senate_unavailable),
            "active_jobs": senate_active,
        },
        "subnational_catalogs": subnational_catalogs,
    }


@app.get("/api/laws")
def list_laws(q: str = "", limit: int = Query(50, ge=1, le=100), session: Session = Depends(get_session)):
    if q.strip():
        results = search_laws(session, q, limit=limit)["results"]
        return {"items": results, "count": len(results)}
    laws = list(session.scalars(select(Law).order_by(Law.hot.desc(), Law.title).limit(limit)))
    return {"items": [_law_summary(law) for law in laws], "count": len(laws)}


@app.get("/api/jurisdictions")
def list_jurisdictions(kind: str | None = None, uf: str | None = None, q: str = "",
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                       session: Session = Depends(get_session)):
    statement = select(Jurisdiction)
    count_statement = select(func.count()).select_from(Jurisdiction)
    if kind:
        statement = statement.where(Jurisdiction.kind == kind)
        count_statement = count_statement.where(Jurisdiction.kind == kind)
    if uf:
        statement = statement.where(Jurisdiction.uf == uf.upper())
        count_statement = count_statement.where(Jurisdiction.uf == uf.upper())
    if q.strip():
        match = f"%{q.strip()}%"
        statement = statement.where(Jurisdiction.name.ilike(match))
        count_statement = count_statement.where(Jurisdiction.name.ilike(match))
    total = session.scalar(count_statement) or 0
    rows = list(session.scalars(statement.order_by(Jurisdiction.kind, Jurisdiction.name).offset(offset).limit(limit)))
    return {"items": [{"id": row.id, "kind": row.kind, "name": row.name, "ibge_code": row.ibge_code,
                        "uf": row.uf, "parent_id": row.parent_id, "legislature_eligible": row.legislature_eligible,
                        "territorial_status": row.territorial_status, "metadata": row.metadata_json,
                        "source_url": row.source_url, "observed_at": row.observed_at.isoformat()} for row in rows],
            "count": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


@app.get("/api/search")
def search(q: str = Query("", max_length=180), limit: int = Query(10, ge=1, le=30), session: Session = Depends(get_session)):
    if not q.strip():
        return {"query": q, "parsed": {}, "results": [], "suggestion": False}
    result = search_laws(session, q, limit=limit)
    logger.info("search query=%s results=%s", q[:100], len(result["results"]))
    return result


@app.get("/api/laws/{slug}")
def law_detail(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    article_count = session.scalar(select(func.count()).select_from(LegalNode).where(
        LegalNode.law_slug == slug, LegalNode.node_type == "article",
        LegalNode.version_id == law.current_version_id,
    )) if law.current_version_id else 0
    job = None
    materializable = law.source_name in TEXT_SOURCE_NAMES
    if not law.current_version_id and materializable:
        job = queue_hydration(law)
    version = session.get(LawVersion, law.current_version_id) if law.current_version_id else None
    return {
        "law": _law_summary(law, article_count or 0),
        "version": {
            "id": version.id, "name": version.version_name, "source_url": version.source_url,
            "retrieved_at": version.retrieved_at.isoformat(), "checksum": version.checksum,
        } if version else None,
        "job": {"id": job.id, "status": job.status, "stage": job.stage, "message": job.message} if job else None,
        "materializable": materializable,
    }


@app.get("/api/laws/{slug}/nodes")
def law_nodes(slug: str, article: str | None = None, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if not law.current_version_id:
        if law.source_name not in TEXT_SOURCE_NAMES:
            return {"status": "catalog", "source_url": law.source_url, "items": []}
        job = queue_hydration(law)
        return {"status": law.materialization_status, "job_id": job.id, "items": []}
    statement = select(LegalNode).where(LegalNode.version_id == law.current_version_id)
    if article:
        prefix = f"art:{article.lower()}"
        statement = statement.where((LegalNode.node_id == prefix) | LegalNode.node_id.startswith(prefix + "."))
    items = list(session.scalars(statement.order_by(LegalNode.order_index)))
    return {"status": law.materialization_status, "items": [_node_payload(node) for node in items]}


@app.get("/api/laws/{slug}/blame")
def law_blame(slug: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               node_id: str | None = None, session: Session = Depends(get_session)):
    """Batch view of verified responsible acts; never attributes prose to a person."""
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if not law.current_version_id:
        return {"law": _law_summary(law), "status": "not_materialized", "items": [], "count": 0,
                "limit": limit, "offset": offset, "has_more": False}
    base = select(LegalNode).where(LegalNode.version_id == law.current_version_id)
    count_query = select(func.count()).select_from(LegalNode).where(LegalNode.version_id == law.current_version_id)
    if node_id:
        base = base.where(LegalNode.node_id == node_id)
        count_query = count_query.where(LegalNode.node_id == node_id)
    total = session.scalar(count_query) or 0
    nodes = list(session.scalars(base.order_by(LegalNode.order_index).offset(offset).limit(limit)))
    ids = [node.node_id for node in nodes]
    changes = list(session.scalars(select(LawChange).where(
        LawChange.law_slug == slug, LawChange.node_id.in_(ids),
    ).order_by(LawChange.changed_at.desc().nullslast(), LawChange.created_at.desc()))) if ids else []
    newest = {}
    for change in changes:
        newest.setdefault(change.node_id, change)
    items = []
    for node in nodes:
        change = newest.get(node.node_id)
        evidence = _change_evidence(change) if change else None
        confirmed = bool(change and evidence["comparison_available"])
        items.append({
            "node_id": node.node_id, "label": node.label, "node_type": node.node_type,
            "current_text": node.text,
            "origin_status": "verified_change" if confirmed else "not_identified",
            "responsible_act": ({"label": change.source_law_label, "number": change.source_law_number,
                                 "year": change.source_law_year, "url": change.source_url,
                                 "changed_at": change.changed_at.isoformat() if change.changed_at else None}
                                if change else None),
            "change_id": change.id if change else None,
            "evidence_level": evidence["level"] if evidence else "not_identified",
            "source_url": change.source_url if change else None,
        })
    return {"law": _law_summary(law), "status": "available", "items": items, "count": total,
            "limit": limit, "offset": offset, "has_more": offset + len(items) < total}


@app.get("/api/laws/{slug}/nodes/{node_id:path}/provenance")
def node_provenance(slug: str, node_id: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if not law.current_version_id:
        return {"law": _law_summary(law), "status": "not_materialized", "node": None,
                "current_text": None, "evidence": {"level": "not_identified", "label": "Ainda não identificado"},
                "last_verified_change": None, "relations": []}
    node = session.scalar(select(LegalNode).where(
        LegalNode.version_id == law.current_version_id, LegalNode.node_id == node_id,
    ).limit(1))
    if not node:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado nesta versão.")
    changes = list(session.scalars(select(LawChange).where(
        LawChange.law_slug == slug, LawChange.node_id == node_id,
    ).order_by(LawChange.changed_at.desc().nullslast(), LawChange.created_at.desc())))
    verified = next((change for change in changes if _change_evidence(change)["comparison_available"]), None)
    partial = changes[0] if changes else None
    selected = verified or partial
    events = list(session.scalars(select(HistoryEvent).where(
        HistoryEvent.law_slug == slug, HistoryEvent.device_ref == node_id,
    ).order_by(HistoryEvent.signed_at.desc().nullslast())))
    evidence = _change_evidence(selected) if selected else {
        "level": "not_identified", "label": "Ainda não identificado", "comparison_available": False,
        "source_host": "", "evidence_marker": "",
    }
    change_payload = None
    if selected:
        change_payload = {
            "id": selected.id, "change_type": selected.change_type, "summary": selected.summary,
            "changed_at": selected.changed_at.isoformat() if selected.changed_at else None,
            "source_law_label": selected.source_law_label, "source_law_number": selected.source_law_number,
            "source_law_year": selected.source_law_year, "source_url": selected.source_url,
            "law_source_url": selected.law_source_url, "before_text": selected.before_text,
            "after_text": selected.after_text, "evidence_marker": selected.evidence_marker,
        }
    return {"law": _law_summary(law), "status": "verified" if verified else "partial" if selected or events else "not_identified",
            "node": _node_payload(node), "current_text": node.text, "evidence": evidence,
            "last_verified_change": change_payload,
            "relations": [{"label": event.event_label, "relation": event.relation,
                           "signed_at": event.signed_at.isoformat() if event.signed_at else None,
                           "source_url": event.event_url,
                           "notice": "Relação oficial localizada; texto histórico ainda não reconstruído."}
                          for event in events]}


@app.get("/api/laws/{slug}/history")
def law_history(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    changes = list(session.scalars(select(LawChange).where(LawChange.law_slug == slug).order_by(LawChange.changed_at.desc(), LawChange.node_id)))
    events = list(session.scalars(select(HistoryEvent).where(HistoryEvent.law_slug == slug).order_by(HistoryEvent.signed_at.desc().nullslast(), HistoryEvent.event_label)))
    active_job = session.scalar(select(HydrationJob).where(
        HydrationJob.law_slug == slug, HydrationJob.job_type == "history",
        HydrationJob.status.in_(["queued", "running"]),
    ).order_by(HydrationJob.created_at.desc()).limit(1))
    coverage = dict(law.coverage or {})
    status = active_job.status if active_job else (coverage.get("history") or "not_requested")
    items = [{
        "id": item.id, "kind": "diff" if _change_evidence(item)["comparison_available"] else "relation",
        "node_id": item.node_id, "change_type": item.change_type,
        "summary": item.summary, "changed_at": item.changed_at.isoformat() if item.changed_at else None,
        "source_law_label": item.source_law_label, "source_url": item.source_url,
        "comparison_available": _change_evidence(item)["comparison_available"],
        "evidence": _change_evidence(item),
    } for item in changes]
    items.extend({
        "id": item.id, "kind": "relation", "node_id": item.device_ref, "change_type": item.relation,
        "summary": f"Referência oficial: {item.event_label}",
        "changed_at": item.signed_at.isoformat() if item.signed_at else None,
        "source_law_label": item.event_label, "source_url": item.event_url,
        "comparison_available": False, "evidence": item.evidence,
    } for item in events if item.status != "compared")
    items.sort(key=lambda item: item["changed_at"] or "0000-01-01", reverse=True)
    return {
        "law": _law_summary(law),
        "status": status,
        "coverage": status,
        "job": {"id": active_job.id, "status": active_job.status, "stage": active_job.stage_name,
                "message": active_job.message, "attempts": active_job.attempts} if active_job else None,
        "checked_at": coverage.get("history_checked_at"),
        "events_pending_text": coverage.get("history_events_pending_text", 0),
        "error": coverage.get("history_error"),
        "items": items,
    }


@app.post("/api/laws/{slug}/history/prepare", status_code=202)
def prepare_history(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    supported_sources = {
        "Presidência da República — Planalto",
        "Senado Federal — Dados Abertos Legislativos",
        "Assembleia Legislativa do Estado de São Paulo — ALESP",
        "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
        "Câmara Municipal de Manaus — SAPL",
    } | set(SAPL_SOURCE_NAMES)
    if law.source_name not in supported_sources:
        raise HTTPException(status_code=409, detail="Esta fonte ainda não fornece relações oficiais para reconstruir o histórico.")
    try:
        job = queue_history(law)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível registrar o job de histórico.") from exc
    return {"id": job.id, "status": job.status, "stage": job.stage_name, "message": job.message,
            "job_type": job.job_type, "attempts": job.attempts}


@app.get("/api/laws/{slug}/proceedings")
def law_proceedings(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    active_job = session.scalar(select(HydrationJob).where(
        HydrationJob.law_slug == slug, HydrationJob.job_type == "provenance",
        HydrationJob.status.in_(["queued", "running"]),
    ).order_by(HydrationJob.created_at.desc()).limit(1))
    dossier = session.get(SenateProceeding, slug)
    status = active_job.status if active_job else (dossier.status if dossier else "not_requested")
    return {
        "law": _law_summary(law),
        "status": status,
        "checked_at": dossier.checked_at.isoformat() if dossier and dossier.checked_at else None,
        "error": dossier.error if dossier and dossier.error else (law.coverage or {}).get("senate_provenance_error"),
        "job": {"id": active_job.id, "status": active_job.status, "stage": active_job.stage_name,
                "message": active_job.message, "attempts": active_job.attempts} if active_job else None,
        "processes": (dossier.data or {}).get("processes", []) if dossier else [],
        "notice": (dossier.data or {}).get("notice") if dossier else None,
        "matching_processes_found": (dossier.data or {}).get("matching_processes_found", 0) if dossier else 0,
        "truncated": (dossier.data or {}).get("truncated", False) if dossier else False,
    }


@app.post("/api/laws/{slug}/proceedings/prepare", status_code=202)
def prepare_law_proceedings(slug: str, refresh: bool = Query(False), session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    from app.sources.senado import TYPE_CODES
    if law.jurisdiction != "federal" or law.law_type not in TYPE_CODES:
        raise HTTPException(status_code=409, detail="A consulta de tramitação está disponível para normas federais com identidade compatível com o Senado.")
    try:
        job = queue_provenance(law, refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível registrar o job de tramitação.") from exc
    return {"id": job.id, "status": job.status, "stage": job.stage_name, "message": job.message,
            "job_type": job.job_type, "attempts": job.attempts}


@app.get("/api/laws/{slug}/coverage")
def law_coverage(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    return {"law": _law_summary(law), "coverage": law.coverage or {}}


@app.get("/api/laws/{slug}/audit")
def law_document_audit(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    version = session.get(LawVersion, law.current_version_id) if law.current_version_id else None
    if not version:
        raise HTTPException(status_code=409, detail="A norma ainda não tem uma versão estruturada para auditar.")
    snapshot = session.scalar(select(SourceSnapshot).where(
        SourceSnapshot.law_slug == law.slug, SourceSnapshot.checksum == version.checksum,
    ).limit(1))
    if not snapshot:
        raise HTTPException(status_code=409, detail="A captura da fonte oficial desta versão não está arquivada.")
    nodes = list(session.scalars(select(LegalNode).where(
        LegalNode.version_id == version.id,
    ).order_by(LegalNode.order_index)))
    return {
        "law": _law_summary(law),
        "version_id": version.id,
        "parser_version": version.parser_version,
        "source": {"url": snapshot.source_url, "format": snapshot.raw_format,
                   "checksum": snapshot.checksum, "retrieved_at": snapshot.retrieved_at.isoformat()},
        "audit": audit_archived_document(snapshot.raw_body, nodes),
    }


@app.post("/api/laws/{slug}/hydrate", status_code=202)
def hydrate_law(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if law.source_name not in {
        "Presidência da República — Planalto",
        "Senado Federal — Dados Abertos Legislativos",
        "Assembleia Legislativa do Estado de São Paulo — ALESP",
        "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
        "Câmara Municipal de Manaus — SAPL",
    }:
        raise HTTPException(status_code=409, detail="O catálogo só encontrou metadados oficiais; esta fonte ainda não fornece texto integral pelo LeiAberta.")
    refresh = False
    job = queue_hydration(law, refresh=refresh)
    return {"job_id": job.id, "status": job.status, "stage": job.stage, "message": job.message}


@app.get("/api/hydration/{job_id}")
@app.get("/api/jobs/{job_id}")
def hydration_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(HydrationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Preparação não encontrada.")
    return {"id": job.id, "law_slug": job.law_slug, "job_type": job.job_type,
            "status": job.status, "stage": job.stage_name, "progress": job.stage,
            "message": job.message, "error": job.error if job.status == "failed" else "",
            "attempts": job.attempts, "updated_at": job.updated_at.isoformat()}


@app.get("/api/changes/{change_id}")
def change_detail(change_id: str, session: Session = Depends(get_session)):
    item = session.get(LawChange, change_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alteração não encontrada.")
    law = session.get(Law, item.law_slug)
    node = session.scalar(select(LegalNode).where(
        LegalNode.law_slug == item.law_slug, LegalNode.node_id == item.node_id,
        LegalNode.version_id == law.current_version_id,
    ).limit(1)) if law and law.current_version_id else None
    return {
        "id": item.id, "law": _law_summary(law), "node_id": item.node_id,
        "node_label": node.label if node else item.node_id,
        "change_type": item.change_type, "summary": item.summary,
        "changed_at": item.changed_at.isoformat() if item.changed_at else None,
        "source_law_label": item.source_law_label, "source_url": item.source_url,
        "law_source_url": item.law_source_url, "before_text": item.before_text,
        "after_text": item.after_text, "evidence_marker": item.evidence_marker,
        "evidence": _change_evidence(item),
    }


@app.get("/api/sources")
def sources(jurisdiction_id: str | None = None, status: str | None = None,
            session: Session = Depends(get_session)):
    statement = select(SourceRegistry).order_by(SourceRegistry.jurisdiction_id, SourceRegistry.name)
    if jurisdiction_id:
        statement = statement.where(SourceRegistry.jurisdiction_id == jurisdiction_id)
    if status:
        statement = statement.where(SourceRegistry.status == status)
    rows = list(session.scalars(statement))
    if not rows:
        return {"items": [], "count": 0, "checked_at": datetime.now(timezone.utc).isoformat()}
    names = list(dict.fromkeys(row.name for row in rows))
    jurisdiction_ids = list({row.jurisdiction_id for row in rows if row.jurisdiction_id})
    jurisdiction_names = dict(session.execute(select(Jurisdiction.id, Jurisdiction.name).where(
        Jurisdiction.id.in_(jurisdiction_ids),
    )).all()) if jurisdiction_ids else {}
    counts = {}
    if names:
        law_counts = session.execute(select(
            Law.source_name, func.count(Law.slug),
            func.sum(case((Law.current_version_id.is_not(None), 1), else_=0)),
        ).where(Law.source_name.in_(names)).group_by(Law.source_name)).all()
        counts = {name: {"cataloged_laws": total or 0, "with_text": with_text or 0}
                  for name, total, with_text in law_counts}
    freshness = {"senado": 86400, "senado_catalog": 86400, "ibge_localities": 86400,
                 "ibge_jurisdictions": 86400,
                 "alesp_catalog": 604800, "sinj_df_catalog": 604800, "sapl_catalog": 604800}
    request_policies = {
        "senado_catalog": {"max_response_bytes": 20_000_000, "timeout_seconds": 60, "max_attempts": 3},
        "alesp_catalog": {"page_size": 5000, "max_response_bytes": 20_000_000, "timeout_seconds": 60},
        "sinj_df_catalog": {"page_size": 5000, "max_response_bytes": 25_000_000, "timeout_seconds": 60},
        "sapl_catalog": {"page_size": 100, "max_response_bytes": 10_000_000, "timeout_seconds": 45, "max_attempts": 3},
        "ibge_localities": {"timeout_seconds": 45},
        "ibge_jurisdictions": {"timeout_seconds": 45},
    }
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        checked = row.last_checked_at
        max_age = freshness.get(row.adapter)
        scope = row.scope or {}
        last_success = scope.get("last_success_at") or (checked.isoformat() if row.status == "enumerated" and checked else None)
        try:
            success_dt = datetime.fromisoformat(last_success) if last_success else None
        except ValueError:
            success_dt = None
        if success_dt and success_dt.tzinfo is None:
            success_dt = success_dt.replace(tzinfo=timezone.utc)
        success_age = now - success_dt if success_dt else None
        is_stale = bool(max_age and success_age and success_age.total_seconds() > max_age)
        freshness_status = "stale" if is_stale else "current" if success_dt and max_age else "unknown"
        source_counts = counts.get(row.name, {"cataloged_laws": None, "with_text": None})
        items.append({
            "id": row.id, "name": row.name, "adapter": row.adapter, "base_url": row.base_url,
            "jurisdiction_id": row.jurisdiction_id,
            "jurisdiction_name": jurisdiction_names.get(row.jurisdiction_id) or row.jurisdiction_id or "Jurisdição não classificada",
            "status": row.status, "scope": scope,
            "evidence_url": row.evidence_url,
            "last_checked_at": checked.isoformat() if checked else None,
            "last_success_at": last_success,
            "last_success_semantics": "Última enumeração concluída registrada" if last_success else None,
            "freshness_seconds": max_age,
            "freshness_status": freshness_status,
            "request_policy": request_policies.get(row.adapter),
            "cataloged_laws": source_counts["cataloged_laws"], "with_text": source_counts["with_text"],
            "new_records": scope.get("new_records"), "updated_records": scope.get("updated_records"),
            "failed_records": scope.get("failed_records"),
            "sync_failures": scope.get("sync_failures"),
            "last_error": row.last_error,
        })
    return {"items": items, "count": len(items), "checked_at": now.isoformat()}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request, session: Session = Depends(get_session)):
    base_url = _public_base_url(request)
    page_size = 10_000
    law_count = session.scalar(select(func.count()).select_from(Law)) or 0
    page_count = (law_count + page_size - 1) // page_size
    xml_header = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    if page_count:
        entries = [f"<sitemap><loc>{escape(base_url)}/sitemap-laws-{page}.xml</loc></sitemap>" for page in range(page_count)]
        body = xml_header + "<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(entries) + "</sitemapindex>"
    else:
        body = xml_header + f"<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"><url><loc>{escape(base_url)}</loc></url></urlset>"
    return Response(body, media_type="application/xml")


@app.get("/sitemap-laws-{page}.xml", include_in_schema=False)
def sitemap_laws(page: int, request: Request, session: Session = Depends(get_session)):
    page_size = 10_000
    law_count = session.scalar(select(func.count()).select_from(Law)) or 0
    if page < 0 or page * page_size >= law_count:
        raise HTTPException(status_code=404, detail="Fragmento do sitemap não encontrado.")
    base_url = _public_base_url(request)
    slugs = session.scalars(select(Law.slug).order_by(Law.slug).offset(page * page_size).limit(page_size))
    entries = [f"<url><loc>{escape(base_url)}/lei/{escape(slug)}</loc></url>" for slug in slugs]
    body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(entries) + "</urlset>"
    return Response(body, media_type="application/xml")


@app.get("/lei/{slug}", include_in_schema=False)
def law_page(slug: str, request: Request, session: Session = Depends(get_session), article: str | None = None):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    canonical_base = _public_base_url(request)
    canonical_path = f"/lei/{slug}/artigo/{article}" if article else f"/lei/{slug}"
    canonical = f"{canonical_base}{canonical_path}"
    number_label = law.title if law.law_type == "Constituição" else f"{law.law_type} nº {law.number}/{law.year}"
    title = f"Art. {article} da {number_label} — {law.title} | LeiAberta" if article else f"{number_label} — {law.title} | LeiAberta"
    description = (f"Art. {article} da {law.title}: texto, alterações verificadas e fontes oficiais."
                   if article else law.description or f"{number_label} — consulte o registro oficial e a cobertura disponível.")
    details = f"{law.law_type} {law.number}/{law.year} · {law.jurisdiction} · {law.status}"
    no_script = [f"<h1>{html_escape(law.title)}</h1>", f"<p>{html_escape(details)}</p>"]
    if law.description:
        no_script.append(f"<p>{html_escape(law.description)}</p>")
    if law.current_version_id:
        nodes = session.scalars(select(LegalNode).where(
            LegalNode.version_id == law.current_version_id,
            LegalNode.node_type == "article",
        ).order_by(LegalNode.order_index).limit(10))
        no_script.append("<section aria-label=\"Primeiros artigos estruturados\">")
        for node in nodes:
            no_script.append(
                f"<article id=\"{html_escape(node.node_id, quote=True)}\"><h2>{html_escape(node.label)}</h2>"
                f"<p>{html_escape(node.text[:3000])}</p></article>"
            )
        no_script.append("</section>")
    else:
        no_script.append("<p>O texto estruturado ainda não está disponível neste acervo.</p>")
    if law.source_url.startswith("https://"):
        no_script.append(
            f"<p><a rel=\"nofollow noopener\" href=\"{html_escape(law.source_url, quote=True)}\">"
            "Consultar fonte oficial</a></p>"
        )
    page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    page = page.replace("<title>LeiAberta — entenda como uma lei chegou ao texto atual</title>", f"<title>{html_escape(title)}</title>")
    page = page.replace(
        '<meta name="description" content="Pesquise legislação brasileira e acompanhe o texto, as fontes oficiais e as alterações documentadas." />',
        f'<meta name="description" content="{html_escape(description, quote=True)}" />',
    )
    page = page.replace(
        '<meta property="og:title" content="LeiAberta — entenda como uma lei chegou ao texto atual" />',
        f'<meta property="og:title" content="{html_escape(title, quote=True)}" />',
    )
    page = page.replace(
        '<meta property="og:description" content="Siga alterações verificadas até suas fontes oficiais." />',
        f'<meta property="og:description" content="{html_escape(description, quote=True)}" />',
    )
    page = page.replace(
        '<meta property="og:image" content="/static/og-image.png" />',
        f'<meta property="og:image" content="{html_escape(canonical_base + "/static/og-image.png", quote=True)}" />',
    ).replace(
        '<meta name="twitter:image" content="/static/og-image.png" />',
        f'<meta name="twitter:image" content="{html_escape(canonical_base + "/static/og-image.png", quote=True)}" />',
    )
    page = page.replace(
        '<meta name="twitter:title" content="LeiAberta — entenda como uma lei chegou ao texto atual" />',
        f'<meta name="twitter:title" content="{html_escape(title, quote=True)}" />',
    ).replace(
        '<meta name="twitter:description" content="Siga alterações verificadas até suas fontes oficiais." />',
        f'<meta name="twitter:description" content="{html_escape(description, quote=True)}" />',
    )
    page = page.replace('<link rel="canonical" href="/" />', f'<link rel="canonical" href="{html_escape(canonical, quote=True)}" />')
    page = page.replace(
        '<main id="main" tabindex="-1"><div class="page-loading"><span class="spinner"></span> Abrindo o acervo</div></main>',
        '<main id="main" tabindex="-1"><div class="page-loading"><span class="spinner"></span> Abrindo o acervo</div>'
        f'<noscript><section class="content-shell">{"".join(no_script)}</section></noscript></main>',
    )
    return HTMLResponse(page)


@app.get("/{path:path}", include_in_schema=False)
def public_app(path: str, request: Request, session: Session = Depends(get_session)):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "lei":
        article = parts[3] if len(parts) == 4 and parts[2] == "artigo" else None
        if len(parts) == 2 or article is not None or len(parts) > 2:
            return law_page(parts[1], request, session, article=article)
    index = ROOT / "static" / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Interface não encontrada."}, status_code=500)
    return FileResponse(index)
