import hashlib
import uuid
from datetime import datetime, timezone
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import jobs
from app.models import HydrationJob, JobOutbox, Law, LawVersion, LegalNode, SenateProceeding, SourceSnapshot
from app.sources.planalto import ParsedNode
from app.sources.senado import SenateRelation
from app.sources.normas import NormasHistorySnapshot, NormasTextChange
from app.sources.history import OfficialRelation
from app.sources.alesp import AlespHistorySnapshot
from app.sources.sinj_df import SinjDFHistorySnapshot


def test_outbox_preserves_paused_jobs_and_resumes_them_by_mode(db_session, add_law, monkeypatch):
    laws = [add_law(slug=slug) for slug in (
        "interactive-outbox", "hot-outbox", "legacy-outbox", "cold-outbox", "unknown-outbox",
        "terminal-outbox",
    )]
    for law in laws:
        law.hot = False
    laws[1].hot = True
    jobs_to_queue = [
        HydrationJob(id="interactive-outbox-job", law_slug=laws[0].slug, job_type="history",
                     status="queued", stage_name="queued", message="Aguardando worker"),
        HydrationJob(id="hot-outbox-job", law_slug=laws[1].slug, job_type="hydrate",
                     status="queued", stage_name="queued",
                     message=jobs.BACKGROUND_BACKFILL_MARKER + "Aguardando hot"),
        HydrationJob(id="legacy-outbox-job", law_slug=laws[2].slug, job_type="hydrate",
                     status="queued", stage_name="queued", message="Aguardando varredura histórica em lote"),
        HydrationJob(id="cold-outbox-job", law_slug=laws[3].slug, job_type="hydrate",
                     status="queued", stage_name="queued",
                     message=jobs.BACKGROUND_BACKFILL_MARKER + "Aguardando cold"),
        HydrationJob(id="unknown-outbox-job", law_slug=laws[4].slug, job_type="hydrate",
                     status="queued", stage_name="retry_wait", message="Erro legado sem marcador"),
        HydrationJob(id="terminal-outbox-job", law_slug=laws[5].slug, job_type="hydrate",
                     status="succeeded", stage_name="complete", message="Concluído sem marcador"),
    ]
    db_session.add_all(laws + jobs_to_queue)
    db_session.flush()
    db_session.add_all([JobOutbox(job_id=item.id) for item in jobs_to_queue])
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    monkeypatch.setenv("REDIS_URL", "redis://fake")

    class FakeRedis:
        def __init__(self):
            self.messages = []

        def xadd(self, queue_name, fields):
            self.messages.append(fields["job_id"])

    fake_redis = FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)

    assert jobs.dispatch_outbox(mode="off") == 2
    assert set(fake_redis.messages) == {"interactive-outbox-job", "terminal-outbox-job"}
    db_session.expire_all()
    assert db_session.query(JobOutbox).filter_by(job_id="legacy-outbox-job").one().dispatched_at is None
    assert db_session.query(JobOutbox).filter_by(job_id="unknown-outbox-job").one().dispatched_at is None

    assert jobs.dispatch_outbox(mode="hot") == 1
    assert fake_redis.messages[-1] == "hot-outbox-job"
    assert jobs.dispatch_outbox(mode="continuous") == 3
    assert set(fake_redis.messages) == {item.id for item in jobs_to_queue}


def test_senate_provenance_job_archives_sources_and_persists_dossier(db_session, add_law, monkeypatch):
    law = add_law(slug="14550-2023", number="14.550", year=2023)
    law.source_name = "Senado Federal — Dados Abertos Legislativos"
    db_session.add(law)
    job = HydrationJob(id="senate-provenance-job", law_slug=law.slug, job_type="provenance", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0, error="",
                       created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    from app.sources.senado_proceedings import OfficialJsonDocument
    document = OfficialJsonDocument("https://legis.senado.leg.br/dadosabertos/processo?tipoNorma=LEI",
                                   b'{"id":8272922}', {"id": 8272922})
    payload = {"status": "complete", "matching_processes_found": 1, "processes_loaded": 1,
               "processes": [{"process": {"identificacao": "PL 1604/2022"}, "amendments": [{"id": 1}],
                              "committee_votes": [{"votes": [{"NomeParlamentar": "Simone Tebet"}]}],
                              "plenary_votes": [], "source_urls": [document.url]}]}

    def fake_fetch(_law_type, _number, _year, *, on_document=None):
        on_document(document)
        return payload, [document]

    monkeypatch.setattr("app.sources.senado_proceedings.fetch_senate_proceedings", fake_fetch)
    assert jobs.process_hydration_job(job.id) is True

    db_session.expire_all()
    persisted_job = db_session.get(HydrationJob, job.id)
    dossier = db_session.get(SenateProceeding, law.slug)
    snapshot = db_session.query(SourceSnapshot).filter_by(law_slug=law.slug).one()
    assert persisted_job.status == "succeeded"
    assert dossier.status == "complete"
    assert dossier.data["processes"][0]["process"]["identificacao"] == "PL 1604/2022"
    assert law.coverage["senate_provenance"] == "complete"
    assert snapshot.raw_body == document.body


def test_interactive_queue_selection_skips_bulk_and_delayed_retry_jobs(db_session, add_law, monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        ("bulk", "hydrate", "queued", "queued", "Aguardando captura do texto legislativo", 0),
        ("manual-hydrate", "hydrate", "queued", "queued", "Aguardando worker", 1),
        ("manual-history", "history", "queued", "queued", "Aguardando worker", 2),
        ("retry-history", "history", "queued", "retry_wait", "Fonte temporariamente indisponível", 3),
    ]
    jobs_by_name = {}
    for slug, job_type, status, stage, message, offset in rows:
        db_session.add(add_law(slug=f"interactive-{slug}"))
        job = HydrationJob(
            id=slug, law_slug=f"interactive-{slug}", job_type=job_type,
            status=status, stage=0, stage_name=stage, message=message, attempts=0,
            error="", created_at=now.replace(microsecond=offset), updated_at=now,
        )
        db_session.add(job)
        jobs_by_name[slug] = job.id
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))

    assert jobs.queued_interactive_job_ids(limit=16) == [
        jobs_by_name["manual-hydrate"], jobs_by_name["manual-history"],
    ]
    assert jobs.queued_interactive_job_ids(limit=24) == [
        jobs_by_name["manual-hydrate"], jobs_by_name["manual-history"],
    ]


def test_interactive_queue_rejects_batches_above_worker_capacity():
    with pytest.raises(ValueError, match="1 a 24 jobs"):
        jobs.queued_interactive_job_ids(limit=25)


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


def _run_source_specific_history_job(db_session, add_law, monkeypatch, *, source_name, source_url,
                                     snapshot, fetch_path, slug):
    law = add_law(slug=slug, number="10.261", year=1968)
    law.source_name = source_name
    law.source_url = source_url
    law.fetch_url = source_url
    db_session.add(law)
    job = HydrationJob(id=f"history-{slug}", law_slug=law.slug, job_type="history", status="queued",
                       stage=0, stage_name="queued", message="Aguardando worker", attempts=0,
                       error="", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.add(JobOutbox(job_id=job.id))
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)
    monkeypatch.setattr(fetch_path, lambda *_args, **_kwargs: snapshot)

    assert jobs.process_hydration_job(job.id) is True
    db_session.expire_all()
    return db_session.get(Law, slug), db_session.query(jobs.HistoryEvent).filter_by(law_slug=slug).one()


def test_alesp_history_job_persists_annotations_and_provenance(db_session, add_law, monkeypatch):
    relation = OfficialRelation(
        source_id="alesp:68804", device_ref="", relation="Alteração",
        event_label="Lei nº 18.473, de 03/06/2026", event_url="https://www.al.sp.gov.br/norma/212702",
        signed_at=date(2026, 6, 3), publication_date=None, evidence="Anotação oficial ALESP.",
    )
    snapshot = AlespHistorySnapshot(
        body=b"{\"official\":true}", source_url="https://baleg-api-prd.al.sp.gov.br/normas/28593",
        relations=[relation], provenance={"proposition": "PL 118/1968", "authors": [{"name": "Governador"}]},
    )
    law, event = _run_source_specific_history_job(
        db_session, add_law, monkeypatch,
        source_name="Assembleia Legislativa do Estado de São Paulo — ALESP",
        source_url="https://www.al.sp.gov.br/norma/28593", snapshot=snapshot,
        fetch_path="app.sources.alesp.fetch_alesp_history", slug="sp-history-test",
    )
    assert event.event_url == relation.event_url
    assert event.source_id == "alesp:68804"
    assert law.coverage["history_source"] == "alesp"
    assert law.coverage["source_provenance"]["proposition"] == "PL 118/1968"


def test_sinj_df_history_job_persists_official_incoming_relations(db_session, add_law, monkeypatch):
    relation = OfficialRelation(
        source_id="sinj:79c7c4d19f0b447fb50ffaf84c524cae", device_ref="", relation="Alterado",
        event_label="Portaria 87 de 17/06/2015",
        event_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_norma=bf2320463ed3455e8e31265f896be797",
        signed_at=date(2015, 6, 17), publication_date=None, evidence="Relação oficial incidente sobre a norma.",
    )
    snapshot = SinjDFHistorySnapshot(
        body=b"<html><script>var json_norma = {};</script></html>",
        source_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_doc=83583", relations=[relation],
    )
    law, event = _run_source_specific_history_job(
        db_session, add_law, monkeypatch,
        source_name="Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
        source_url=snapshot.source_url, snapshot=snapshot,
        fetch_path="app.sources.sinj_df.fetch_sinj_df_history", slug="df-history-test",
    )
    assert event.event_url == relation.event_url
    assert event.relation == "Alterado"
    assert law.coverage["history_source"] == "sinj_df"
    assert law.coverage["history_events_pending_text"] == 1
