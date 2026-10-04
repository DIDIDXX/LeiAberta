from scripts import queue_history_batch as history_batch
from app.models import Law


def test_history_batch_dry_run_is_bounded_resumable_and_skips_partial(db_session, monkeypatch):
    common = dict(jurisdiction="federal", law_type="Lei", year=2024, number="1",
                  description="", status="Não verificado", aliases=[],
                  source_url="https://official.example", fetch_url="https://official.example",
                  hot=False, materialization_status="catalog")
    db_session.add_all([
        Law(slug="a-unrequested", title="A", source_name="Senado Federal — Dados Abertos Legislativos",
            coverage={"history": "not_requested"}, **common),
        Law(slug="b-partial", title="B", source_name="Senado Federal — Dados Abertos Legislativos",
            coverage={"history": "partial"}, **common),
        Law(slug="c-other", title="C", source_name="Portal local", coverage={},
            jurisdiction="municipality", law_type="Lei", year=2024, number="2", description="",
            status="Não verificado", aliases=[], source_url="https://local.example",
            fetch_url="https://local.example", hot=False, materialization_status="catalog"),
    ])
    db_session.commit()
    monkeypatch.setattr(history_batch, "SessionLocal", lambda: db_session)

    result = history_batch.queue_history_batch(limit=1, dry_run=True)

    assert result["queued_count"] == 1
    assert result["jobs"] == [{"slug": "a-unrequested", "job_id": None, "status": "would_queue"}]
    assert result["next_slug"] == "a-unrequested"
    assert result["has_more"] is True


def test_senado_text_batch_is_bounded_idempotent_and_persists_outbox(db_session, monkeypatch):
    from app import jobs
    from app.models import HydrationJob, JobOutbox

    common = dict(jurisdiction="federal", law_type="Lei", year=2024, number="1",
                  description="", status="Não verificado", aliases=[],
                  source_url="https://legis.senado.leg.br/dadosabertos/legislacao/12345",
                  fetch_url="https://legis.senado.leg.br/dadosabertos/legislacao/12345",
                  hot=False, materialization_status="catalog")
    db_session.add_all([
        Law(slug="senado-1", title="Lei 1", source_name="Senado Federal — Dados Abertos Legislativos", **common),
        Law(slug="senado-2", title="Lei 2", source_name="Senado Federal — Dados Abertos Legislativos", **common),
        Law(slug="planalto-3", title="Lei 3", source_name="Presidência da República — Planalto", **common),
    ])
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)

    first = jobs.queue_senado_text_batch(limit=1)
    second = jobs.queue_senado_text_batch(limit=500)

    assert first["queued_count"] == 1
    assert second["queued_count"] == 1
    assert db_session.query(HydrationJob).filter_by(job_type="hydrate").count() == 2
    assert db_session.query(JobOutbox).count() == 2
    assert db_session.get(Law, "planalto-3").materialization_status == "catalog"
