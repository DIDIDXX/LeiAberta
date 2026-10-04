from datetime import date

import sys
import logging
import os
from sqlalchemy import select

from app.catalog import CATALOG
from app.db import SessionLocal
from app.models import Law, LawVersion
from app.jobs import queue_hydration
from app.sources.planalto import PARSER_VERSION

logger = logging.getLogger("leiaberta.seed")


def seed_catalog() -> int:
    session = SessionLocal()
    inserted = 0
    try:
        for entry in CATALOG:
            existing = session.get(Law, entry["slug"])
            values = dict(entry)
            values["published_at"] = date.fromisoformat(values["published_at"]) if values.get("published_at") else None
            values["coverage"] = {
                "official_source": "available", "structured_text": "not_materialized",
                "history": "not_materialized", "attribution": "not_identified",
                "authors": "not_available", "votes": "not_available",
            }
            if existing is None:
                session.add(Law(**values))
                inserted += 1
            else:
                # Update catalog fields without resetting materialization state or coverage.
                for key, value in values.items():
                    if key in {"coverage", "materialization_status", "last_hydrated_at", "current_version_id"}:
                        continue
                    setattr(existing, key, value)
        session.commit()
        if "--enqueue-hot" in sys.argv and os.getenv("REDIS_URL"):
            for entry in CATALOG:
                law = session.get(Law, entry["slug"])
                version = session.get(LawVersion, law.current_version_id) if law and law.current_version_id else None
                needs_first_hydration = bool(law and entry.get("hot") and version is None)
                needs_reparse = bool(version and version.parser_version != PARSER_VERSION)
                if law and (needs_first_hydration or needs_reparse):
                    job = queue_hydration(law)
                    logger.info("hot_law_queued law_id=%s job=%s reason=%s", law.slug, job.id,
                                "parser_refresh" if needs_reparse else "priority_hydration")
        return inserted
    finally:
        session.close()


if __name__ == "__main__":
    count = seed_catalog()
    print(f"Catalog synchronized: {count} new federal norms; {len(CATALOG)} indexed in total.")
