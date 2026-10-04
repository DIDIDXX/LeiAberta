from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from xml.sax.saxutils import escape

from app.db import get_session
from app.jobs import queue_history, queue_hydration
from app.models import HistoryEvent, HydrationJob, Jurisdiction, Law, LawChange, LawVersion, LegalNode, SourceRegistry
from app.search import search_laws

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.api")
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="LeiAberta", version="0.1.0", description="Catálogo e histórico público de legislação brasileira.")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


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


@app.get("/api/health")
def api_health(session: Session = Depends(get_session)):
    return health(session)


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    indexed = session.scalar(select(func.count()).select_from(Law)) or 0
    materialized = session.scalar(select(func.count()).select_from(Law).where(Law.materialization_status == "ready")) or 0
    articles = session.scalar(select(func.count()).select_from(LegalNode).where(LegalNode.node_type == "article")) or 0
    changes = session.scalar(select(func.count()).select_from(LawChange)) or 0
    return {"indexed_laws": indexed, "materialized_laws": materialized, "structured_articles": articles, "documented_changes": changes}


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
    materializable = law.source_name == "Presidência da República — Planalto"
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
        if law.source_name != "Presidência da República — Planalto":
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
    if active_job is None:
        # Text ingestion can produce independently verified diff rows while the history page is open.
        active_job = session.scalar(select(HydrationJob).where(
            HydrationJob.law_slug == slug, HydrationJob.job_type == "hydrate",
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
    } for item in events)
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
    try:
        job = queue_history(law)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível registrar o job de histórico.") from exc
    return {"id": job.id, "status": job.status, "stage": job.stage_name, "message": job.message,
            "job_type": job.job_type, "attempts": job.attempts}


@app.get("/api/laws/{slug}/coverage")
def law_coverage(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    return {"law": _law_summary(law), "coverage": law.coverage or {}}


@app.post("/api/laws/{slug}/hydrate", status_code=202)
def hydrate_law(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if law.source_name != "Presidência da República — Planalto":
        raise HTTPException(status_code=409, detail="O catálogo só encontrou metadados oficiais; o adapter para obter o texto integral desta fonte ainda não está disponível.")
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
    slugs = list(session.scalars(select(Law.slug).order_by(Law.slug)))
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
        base_url = f"{scheme}://{host}"
    urls = [base_url, *[f"{base_url}/lei/{slug}" for slug in slugs]]
    body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(f"<url><loc>{escape(url)}</loc></url>" for url in urls) + "</urlset>"
    return Response(body, media_type="application/xml")


@app.get("/{path:path}", include_in_schema=False)
def public_app(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    index = ROOT / "static" / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Interface não encontrada."}, status_code=500)
    return FileResponse(index)
