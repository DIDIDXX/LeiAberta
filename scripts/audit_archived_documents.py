"""Refresh conservative completeness diagnostics for archived current texts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.audit import audit_archived_document
from app.db import SessionLocal
from app.models import Law, LawVersion, LegalNode, SourceSnapshot
from app.storage.source_snapshots import read_source_snapshot


def audit_archived_catalog(*, limit: int = 1_000) -> dict:
    if not 1 <= limit <= 10_000:
        raise ValueError("O limite de auditoria deve ficar entre 1 e 10.000.")
    session = SessionLocal()
    audited = skipped_without_snapshot = 0
    try:
        laws = list(session.scalars(select(Law).where(Law.current_version_id.is_not(None)).order_by(Law.slug).limit(limit)))
        for law in laws:
            version = session.get(LawVersion, law.current_version_id)
            snapshot = session.scalar(select(SourceSnapshot).where(
                SourceSnapshot.law_slug == law.slug,
                SourceSnapshot.checksum == version.checksum,
            ).limit(1)) if version else None
            if not version or not snapshot:
                skipped_without_snapshot += 1
                continue
            nodes = list(session.scalars(select(LegalNode).where(
                LegalNode.version_id == version.id,
            ).order_by(LegalNode.order_index)))
            coverage = dict(law.coverage or {})
            coverage["document_audit"] = audit_archived_document(read_source_snapshot(snapshot), nodes)
            coverage["document_audit"]["source_checksum"] = snapshot.checksum
            coverage["document_audit"]["audited_at"] = snapshot.retrieved_at.isoformat()
            law.coverage = coverage
            audited += 1
            if audited % 100 == 0:
                session.commit()
        session.commit()
        return {"examined": len(laws), "audited": audited,
                "skipped_without_snapshot": skipped_without_snapshot,
                "limit": limit, "completeness_certified": 0}
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1_000)
    args = parser.parse_args()
    print(json.dumps(audit_archived_catalog(limit=args.limit), ensure_ascii=False, indent=2))
