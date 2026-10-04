"""Queue a bounded, resumable batch of official federal history lookups."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import SessionLocal
from app.jobs import queue_history
from app.models import HydrationJob, Law
from app.sources.senado import TYPE_CODES

PLATFORM_SOURCES = {
    "Presidência da República — Planalto",
    "Senado Federal — Dados Abertos Legislativos",
}


def queue_history_batch(*, limit: int = 100, after_slug: str | None = None,
                        include_partial: bool = False, dry_run: bool = False) -> dict:
    if not 1 <= limit <= 500:
        raise ValueError("O lote deve conter de 1 a 500 normas.")
    session = SessionLocal()
    queued: list[dict] = []
    skipped = 0
    visited = 0
    next_slug = after_slug
    try:
        statement = select(Law).where(Law.jurisdiction == "federal").order_by(Law.slug)
        if after_slug:
            statement = statement.where(Law.slug > after_slug)
        # Fetch a bounded scan window. The cursor is the last examined slug,
        # so a run can resume even when some entries were already processed.
        candidates = list(session.scalars(statement.limit(limit * 20)))
        for law in candidates:
            if len(queued) >= limit:
                break
            visited += 1
            next_slug = law.slug
            if law.source_name not in PLATFORM_SOURCES or law.law_type not in TYPE_CODES:
                skipped += 1
                continue
            history = (law.coverage or {}).get("history")
            if history in {"partial", "complete"} and not include_partial:
                skipped += 1
                continue
            active = session.scalar(select(HydrationJob.id).where(
                HydrationJob.law_slug == law.slug,
                HydrationJob.job_type == "history",
                HydrationJob.status.in_(["queued", "running"]),
            ).limit(1))
            if active:
                skipped += 1
                continue
            if not dry_run:
                job = queue_history(law)
                queued.append({"slug": law.slug, "job_id": job.id, "status": job.status})
            else:
                queued.append({"slug": law.slug, "job_id": None, "status": "would_queue"})
        more = visited < len(candidates) or len(candidates) == limit * 20
        return {"limit": limit, "visited": visited, "queued_count": len(queued),
                "skipped": skipped, "next_slug": next_slug if more else None,
                "has_more": more, "dry_run": dry_run, "jobs": queued}
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, help="Máximo de jobs para enfileirar (até 500).")
    parser.add_argument("--after-slug", help="Retoma depois do último slug retornado pela execução anterior.")
    parser.add_argument("--include-partial", action="store_true", help="Atualiza históricos já marcados como parciais.")
    parser.add_argument("--dry-run", action="store_true", help="Lista o lote sem registrar jobs.")
    args = parser.parse_args()
    print(json.dumps(queue_history_batch(limit=args.limit, after_slug=args.after_slug,
                                         include_partial=args.include_partial,
                                         dry_run=args.dry_run), ensure_ascii=False, indent=2))
