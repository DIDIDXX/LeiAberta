import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import jobs
from app.models import HydrationJob, Law, LawVersion, LegalNode, SourceSnapshot
from app.sources.planalto import ParsedNode


def test_reparse_creates_immutable_representation_and_keeps_old_nodes(db_session, add_law, monkeypatch):
    law = add_law(slug="1234-2024")
    body = b"<html><body>new parser source</body></html>"
    checksum = hashlib.sha256(body).hexdigest()
    db_session.add(law)
    old = LawVersion(law_slug=law.slug, version_name="Old parser result", source_url=law.source_url,
                     checksum=checksum, parser_version="1.0", is_current=True, article_count=1)
    db_session.add(old)
    db_session.flush()
    law.current_version_id = old.id
    old_node = LegalNode(law_slug=law.slug, version_id=old.id, node_id="art:1", parent_node_id=None,
                         node_type="article", label="Art. 1º", text="Old parsed text.", source_note="", order_index=0)
    job = HydrationJob(id=str(uuid.uuid4()), law_slug=law.slug, job_type="hydrate", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0,
                       error="", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add_all([old_node, job])
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(jobs, "fetch_official_html", lambda _url: (body, law.source_url))
    monkeypatch.setattr(jobs, "parse_legal_nodes", lambda _body: [
        ParsedNode("art:1", None, "article", "Art. 1º", "New parsed text.", "", 0),
    ])

    assert jobs.process_hydration_job(job.id) is True
    versions = list(db_session.scalars(select(LawVersion).where(LawVersion.law_slug == law.slug).order_by(LawVersion.id)))
    assert len(versions) == 2
    assert versions[0].parser_version == "1.0"
    assert versions[0].is_current is False
    assert db_session.get(LegalNode, old_node.id).text == "Old parsed text."
    assert versions[1].parser_version == jobs.PARSER_VERSION
    assert versions[1].is_current is True
    assert db_session.get(Law, law.slug).current_version_id == versions[1].id
    assert db_session.query(SourceSnapshot).filter_by(law_slug=law.slug, checksum=checksum).count() == 1
