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


def test_senado_text_batch_retries_only_known_pre_patch_failures(db_session, monkeypatch):
    from datetime import datetime, timezone

    from app import jobs
    from app.models import HydrationJob

    common = dict(jurisdiction="federal", law_type="Resolução do Senado Federal", year=2017, number="8",
                  description="", status="Não verificado", aliases=[],
                  source_url="https://legis.senado.leg.br/dadosabertos/legislacao/12345",
                  fetch_url="https://legis.senado.leg.br/dadosabertos/legislacao/12345",
                  hot=False, materialization_status="unavailable")
    retryable = Law(slug="senado-retry", title="Resolução antiga", source_name="Senado Federal — Dados Abertos Legislativos", **common)
    dou_retryable = Law(slug="senado-dou-retry", title="Sem representação Normas", source_name="Senado Federal — Dados Abertos Legislativos", **common)
    permanent = Law(slug="senado-permanent", title="Sem fonte conferida", source_name="Senado Federal — Dados Abertos Legislativos", **common)
    active = Law(slug="senado-active", title="Em fila", source_name="Senado Federal — Dados Abertos Legislativos", **common)
    db_session.add_all([retryable, dou_retryable, permanent, active])
    now = datetime.now(timezone.utc)
    db_session.add_all([
        HydrationJob(id="old-parser-error", law_slug=retryable.slug, job_type="hydrate", status="failed",
                     attempts=5, error="A fonte respondeu, mas nenhum dispositivo jurídico foi reconhecido.",
                     stage_name="failed", message="Falhou", created_at=now, updated_at=now),
        HydrationJob(id="permanent-source-error", law_slug=permanent.slug, job_type="hydrate", status="failed",
                     attempts=1, error="O Normas.leg.br não tem texto e o leitor do DOU não forneceu correspondência exata: sem publicação.",
                     stage_name="failed", message="Sem texto", created_at=now, updated_at=now),
        HydrationJob(id="dou-fallback-error", law_slug=dou_retryable.slug, job_type="hydrate", status="failed",
                     attempts=1, error="O registro oficial não possui uma representação HTML de texto integral.",
                     stage_name="failed", message="Sem texto", created_at=now, updated_at=now),
        HydrationJob(id="already-active", law_slug=active.slug, job_type="hydrate", status="queued",
                     attempts=0, error="", stage_name="queued", message="Na fila", created_at=now, updated_at=now),
    ])
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)

    first = jobs.queue_senado_text_batch(limit=10)
    second = jobs.queue_senado_text_batch(limit=10)

    assert first["queued_count"] == 2
    assert {item["slug"] for item in first["jobs"]} == {retryable.slug, dou_retryable.slug}
    assert second["queued_count"] == 0


def test_subnational_text_backfill_is_fair_and_skips_unpublished_text(db_session, monkeypatch):
    from app import jobs
    from app.models import HydrationJob, JobOutbox

    shared = dict(year=2024, number="1", description="", status="Não verificado", aliases=[],
                  signed_at=None, published_at=None, hot=False, materialization_status="catalog",
                  current_version_id=None)
    db_session.add_all([
        Law(slug="sp-alesp-1", jurisdiction="state", state_code="SP", municipality=None,
            law_type="Lei", title="Lei SP", source_name="Assembleia Legislativa do Estado de São Paulo — ALESP",
            source_url="https://www.al.sp.gov.br/norma/1", fetch_url="https://www.al.sp.gov.br/norma/1",
            coverage={"text_url_in_catalog": True}, **shared),
        Law(slug="df-sinj-a", jurisdiction="state", state_code="DF", municipality=None,
            law_type="Lei", title="Lei DF sem anexo", source_name="Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
            source_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_doc=1",
            fetch_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_doc=1",
            coverage={"text_attachment_types": []}, **shared),
        Law(slug="df-sinj-b", jurisdiction="state", state_code="DF", municipality=None,
            law_type="Lei", title="Lei DF", source_name="Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
            source_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_doc=2",
            fetch_url="https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_doc=2",
            coverage={"text_attachment_types": ["application/pdf"]}, **shared),
        Law(slug="manaus-sapl-1", jurisdiction="municipality", state_code="AM", municipality="Manaus",
            law_type="Lei Ordinária", title="Lei Manaus", source_name="Câmara Municipal de Manaus — SAPL",
            source_url="https://sapl.cmm.am.gov.br/api/norma/normajuridica/1/",
            fetch_url="https://sapl.cmm.am.gov.br/api/norma/normajuridica/1/",
            coverage={"text_url_in_catalog": True}, **shared),
    ])
    db_session.commit()
    monkeypatch.setattr(jobs, "_SUBNATIONAL_BACKFILL_CURSORS", {})
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(jobs, "dispatch_outbox", lambda limit=100: 0)

    result = jobs.queue_subnational_text_batch(limit=3)

    assert result["queued_count"] == 3
    assert set(result["queued_by_source"].values()) == {1}
    assert {item["slug"] for item in result["jobs"]} == {"sp-alesp-1", "df-sinj-b", "manaus-sapl-1"}
    assert db_session.query(HydrationJob).filter_by(job_type="hydrate").count() == 3
    assert db_session.query(JobOutbox).count() == 3
    assert db_session.get(Law, "df-sinj-a").materialization_status == "catalog"
