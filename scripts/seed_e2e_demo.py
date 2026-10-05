"""Populate only the isolated Playwright database with an archived demo case."""
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Law, LawChange, LawVersion, LegalNode

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/launch/lmp-art19-par4.json"


def main():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with SessionLocal() as session:
        law = session.get(Law, data["law_slug"])
        if law is None:
            raise RuntimeError("Playwright seed must create the Maria da Penha catalog entry first")
        change = session.get(LawChange, data["id"])
        if change is not None:
            return
        version = session.scalar(select(LawVersion).where(
            LawVersion.law_slug == law.slug, LawVersion.checksum == "e2e-launch-case-v1",
        ))
        if version is None:
            version = LawVersion(
                law_slug=law.slug, version_name="Playwright fixture; derived from recorded official evidence",
                source_url=data["law_source_url"], checksum="e2e-launch-case-v1",
                parser_version="fixture-v1", article_count=1,
            )
            session.add(version)
            session.flush()
            law.current_version_id = version.id
            law.materialization_status = "partial"
            law.coverage = {**(law.coverage or {}), "structured_text": "partial", "history": "partial"}
            session.add(LegalNode(
                law_slug=law.slug, version_id=version.id, node_id=data["node_id"],
                parent_node_id="art:19", node_type="paragraph", label="§ 4º",
                text=data["after_text"], order_index=1,
            ))
        session.add(LawChange(
            id=data["id"], law_slug=law.slug, node_id=data["node_id"],
            change_type=data["change_type"], summary=data["summary"],
            changed_at=date.fromisoformat(data["changed_at"]),
            source_law_label=data["source_law_label"], source_law_number=data["source_law_number"],
            source_law_year=data["source_law_year"], source_url=data["source_url"],
            law_source_url=data["law_source_url"], before_text=data["before_text"],
            after_text=data["after_text"], evidence_marker=data["evidence_marker"],
        ))
        session.commit()


if __name__ == "__main__":
    main()
