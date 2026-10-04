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
from app.jobs import queue_hydration
from app.models import HydrationJob, Law, LawChange, LawVersion, LegalNode
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
    if law.materialization_status != "ready":
        job = queue_hydration(law)
    version = session.get(LawVersion, law.current_version_id) if law.current_version_id else None
    return {
        "law": _law_summary(law, article_count or 0),
        "version": {
            "id": version.id, "name": version.version_name, "source_url": version.source_url,
            "retrieved_at": version.retrieved_at.isoformat(), "checksum": version.checksum,
        } if version else None,
        "job": {"id": job.id, "status": job.status, "stage": job.stage, "message": job.message} if job else None,
    }


@app.get("/api/laws/{slug}/nodes")
def law_nodes(slug: str, article: str | None = None, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    if law.materialization_status != "ready" or not law.current_version_id:
        job = queue_hydration(law)
        return {"status": law.materialization_status, "job_id": job.id, "items": []}
    statement = select(LegalNode).where(LegalNode.version_id == law.current_version_id)
    if article:
        prefix = f"art:{article.lower()}"
        statement = statement.where((LegalNode.node_id == prefix) | LegalNode.node_id.startswith(prefix + "."))
    items = list(session.scalars(statement.order_by(LegalNode.order_index)))
    return {"status": "ready", "items": [_node_payload(node) for node in items]}


@app.get("/api/laws/{slug}/history")
def law_history(slug: str, session: Session = Depends(get_session)):
    law = session.get(Law, slug)
    if not law:
        raise HTTPException(status_code=404, detail="Norma não encontrada no catálogo.")
    changes = list(session.scalars(select(LawChange).where(LawChange.law_slug == slug).order_by(LawChange.changed_at.desc(), LawChange.node_id)))
    return {
        "law": _law_summary(law),
        "coverage": (law.coverage or {}).get("history", "not_materialized"),
        "items": [{
            "id": item.id, "node_id": item.node_id, "change_type": item.change_type,
            "summary": item.summary, "changed_at": item.changed_at.isoformat() if item.changed_at else None,
            "source_law_label": item.source_law_label, "source_url": item.source_url,
        } for item in changes],
    }


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
    job = queue_hydration(law)
    return {"job_id": job.id, "status": job.status, "stage": job.stage, "message": job.message}


@app.get("/api/hydration/{job_id}")
def hydration_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(HydrationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Preparação não encontrada.")
    return {"id": job.id, "law_slug": job.law_slug, "status": job.status, "stage": job.stage,
            "message": job.message, "error": job.message if job.status == "failed" else "",
            "updated_at": job.updated_at.isoformat()}


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
def sources():
    return {"items": [{"name": "Presidência da República — Planalto", "url": "https://www.planalto.gov.br/ccivil_03/", "jurisdiction": "Federal"}]}


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
