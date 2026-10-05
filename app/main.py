from __future__ import annotations

import logging
import os
from html import escape as html_escape
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
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


def _public_base_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if configured:
        return configured
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{scheme}://{host}"


@app.middleware("http")
async def baseline_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; connect-src 'self'; font-src 'self' data:; "
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
        "id": item.id, "kind": "diff", "node_id": item.node_id, "change_type": item.change_type,
        "summary": item.summary, "changed_at": item.changed_at.isoformat() if item.changed_at else None,
        "source_law_label": item.source_law_label, "source_url": item.source_url,
        "comparison_available": True,
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
        return {"items": [{"name": "Presidência da República — Planalto", "url": "https://www.planalto.gov.br/ccivil_03/", "jurisdiction": "Federal", "status": "integrated"}]}
    return {"items": [{"id": row.id, "name": row.name, "adapter": row.adapter, "base_url": row.base_url,
                       "jurisdiction_id": row.jurisdiction_id, "status": row.status, "scope": row.scope,
                       "evidence_url": row.evidence_url, "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
                       "last_error": row.last_error} for row in rows], "count": len(rows)}


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
def law_page(slug: str, request: Request, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    canonical_base = _public_base_url(request)
    canonical = f"{canonical_base}/lei/{slug}"
    title = f"{law.title} — LeiAberta"
    description = law.description or f"{law.law_type} {law.number}/{law.year} — consulte o registro oficial e a cobertura disponível."
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
    page = page.replace("<title>LeiAberta — veja o que mudou</title>", f"<title>{html_escape(title)}</title>")
    page = page.replace(
        '<meta name="description" content="Pesquise legislação brasileira e acompanhe o texto, as fontes oficiais e as alterações documentadas." />',
        f'<meta name="description" content="{html_escape(description, quote=True)}" />',
    )
    page = page.replace(
        '<meta property="og:title" content="LeiAberta — legislação com histórico" />',
        f'<meta property="og:title" content="{html_escape(title, quote=True)}" />',
    )
    page = page.replace(
        '<meta property="og:description" content="Veja o que mudou. Quem mudou. E por quê." />',
        f'<meta property="og:description" content="{html_escape(description, quote=True)}" />',
    )
    page = page.replace('<link rel="canonical" href="/" />', f'<link rel="canonical" href="{html_escape(canonical, quote=True)}" />')
    page = page.replace(
        '<main id="main" tabindex="-1"><div class="page-loading"><span class="spinner"></span> Abrindo o acervo</div></main>',
        '<main id="main" tabindex="-1"><div class="page-loading"><span class="spinner"></span> Abrindo o acervo</div>'
        f'<noscript><section class="content-shell">{"".join(no_script)}</section></noscript></main>',
    )
    return HTMLResponse(page)


@app.get("/{path:path}", include_in_schema=False)
def public_app(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    index = ROOT / "static" / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Interface não encontrada."}, status_code=500)
    return FileResponse(index)
