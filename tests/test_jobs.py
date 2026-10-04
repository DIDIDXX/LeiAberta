import hashlib
import uuid
from datetime import datetime, timezone
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import jobs
from app.models import HydrationJob, JobOutbox, Law, LawVersion, LegalNode, SourceSnapshot
from app.sources.planalto import ParsedNode
from app.sources.senado import SenateRelation
from app.sources.normas import NormasHistorySnapshot, NormasTextChange


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

    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "fetch_official_html", lambda _url: (body, law.source_url))
    monkeypatch.setattr(jobs, "parse_legal_nodes", lambda _body: [
        ParsedNode("art:1", None, "article", "Art. 1º", "New parsed text.", "", 0),
    ])

    assert jobs.process_hydration_job(job.id) is True
    db_session.expire_all()
    versions = list(db_session.scalars(select(LawVersion).where(LawVersion.law_slug == law.slug).order_by(LawVersion.id)))
    assert len(versions) == 2
    assert versions[0].parser_version == "1.0"
    assert versions[0].is_current is False
    assert db_session.get(LegalNode, old_node.id).text == "Old parsed text."
    assert versions[1].parser_version == jobs.PARSER_VERSION
    assert versions[1].is_current is True
    assert db_session.get(Law, law.slug).current_version_id == versions[1].id
    assert db_session.query(SourceSnapshot).filter_by(law_slug=law.slug, checksum=checksum).count() == 1


def test_hydration_archives_official_bytes_before_a_parse_failure(db_session, add_law, monkeypatch):
    law = add_law(slug="archive-before-parse")
    db_session.add(law)
    job = HydrationJob(id=str(uuid.uuid4()), law_slug=law.slug, job_type="hydrate", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0,
                       error="", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.add(JobOutbox(job_id=job.id))
    db_session.commit()

    body = b'<html><body><p>Art. 1o Texto oficial.</p></body></html>'
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "fetch_official_html", lambda _url: (body, "https://official.example/law"))
    monkeypatch.setattr(jobs, "parse_legal_nodes", lambda _body: (_ for _ in ()).throw(ValueError("parse broke")))

    assert jobs.process_hydration_job(job.id) is False
    db_session.expire_all()
    archive = db_session.query(SourceSnapshot).filter_by(law_slug=law.slug).one()
    assert archive.version_id is None
    assert archive.raw_body == body
    assert archive.checksum == hashlib.sha256(body).hexdigest()
    assert db_session.get(HydrationJob, job.id).status == "queued"


def test_hydration_keeps_full_text_when_no_legal_articles_are_recognized(db_session, add_law, monkeypatch):
    law = add_law(slug="unstructured-source")
    db_session.add(law)
    job = HydrationJob(id=str(uuid.uuid4()), law_slug=law.slug, job_type="hydrate", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0,
                       error="", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.add(JobOutbox(job_id=job.id))
    db_session.commit()

    body = b"<html><body><p>Clausula primeira. A norma continua disponivel integralmente.</p>"
    body += b"<p>Clausula segunda. Estrutura legal ainda nao reconhecida.</p></body></html>"
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "fetch_official_html", lambda _url: (body, "https://official.example/law"))

    assert jobs.process_hydration_job(job.id) is True
    db_session.expire_all()

    stored_law = db_session.get(Law, law.slug)
    stored_job = db_session.get(HydrationJob, job.id)
    version = db_session.query(LawVersion).filter_by(law_slug=law.slug).one()
    node = db_session.query(LegalNode).filter_by(version_id=version.id).one()
    archive = db_session.query(SourceSnapshot).filter_by(law_slug=law.slug).one()
    assert stored_job.status == "succeeded"
    assert stored_law.materialization_status == "partial"
    assert stored_law.coverage["structured_text"] == "unstructured"
    assert "estrutura não reconhecida" in version.version_name
    assert node.node_type == "document"
    assert "Clausula primeira" in node.text and "Clausula segunda" in node.text
    assert archive.version_id == version.id
    assert archive.raw_body == body


def test_history_job_persists_official_before_after_and_marks_relation_compared(db_session, add_law, monkeypatch):
    law = add_law(slug="13709-2018")
    db_session.add(law)
    job = HydrationJob(id="history-compare-job", law_slug=law.slug, job_type="history", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0,
                       error="", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.add(JobOutbox(job_id=job.id))
    db_session.commit()

    relation = SenateRelation(
        source_id="31172769", device_ref="Art. 7, caput, Inciso 8 [Lei nº 13.709 de 14/08/2018]",
        relation="Alteração (Declaração de Alteração Permanente)",
        event_label="Lei nº 13.853 de 08/07/2019", signed_at=date(2019, 7, 8),
        publication_date=None, evidence="Art. 7, inciso VIII: alteração oficial.",
    )
    change = NormasTextChange(
        node_id="art:7.inciso:VIII", node_label="Art. 7º, inciso VIII", operation="Text_Change",
        before_text="Texto anterior comprovado.", after_text="Texto posterior comprovado.",
        changed_at=date(2019, 7, 8), source_law_label="Lei nº 13.853 de 08/07/2019",
        source_law_number="13.853", source_law_year=2019,
        source_url="https://normas.leg.br/?urn=urn:lex:br:federal:lei:2019-07-08;13853",
        source_urn="urn:lex:br:federal:lei:2019-07-08;13853@2019-07-08!art2_cpt_alt1_art7_cpt_inc8",
    )
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)
    monkeypatch.setattr("app.sources.senado.fetch_norm_xml", lambda *_args, **_kwargs: (b"<senado />", "https://legis.senado.leg.br/dadosabertos/legislacao/13709"))
    monkeypatch.setattr("app.sources.senado.parse_relation_xml", lambda *_args, **_kwargs: [relation])
    monkeypatch.setattr("app.sources.normas.fetch_normas_history", lambda *_args, **_kwargs: NormasHistorySnapshot(
        urn="urn:lex:br:federal:lei:2018-08-14;13709", body=b"{}",
        source_url="https://normas.leg.br/api/public/normas?urn=lgpd", changes=[change],
    ))

    assert jobs.process_hydration_job(job.id) is True
    db_session.expire_all()

    stored_change = db_session.query(jobs.LawChange).filter_by(law_slug=law.slug).one()
    stored_event = db_session.query(jobs.HistoryEvent).filter_by(law_slug=law.slug).one()
    coverage = db_session.get(Law, law.slug).coverage
    assert stored_change.before_text == "Texto anterior comprovado."
    assert stored_change.after_text == "Texto posterior comprovado."
    assert stored_change.change_type == "UPDATE"
    assert stored_event.status == "compared"
    assert coverage["history_events_pending_text"] == 0
    assert coverage["history_comparison_count"] == 1
    assert db_session.get(HydrationJob, job.id).status == "succeeded"
