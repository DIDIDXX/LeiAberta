from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.db
import app.worker as worker
from app.worker import catalog_concurrency, hydration_concurrency, wait_for_database_schema


def test_worker_waits_for_the_current_alembic_head(db_session, monkeypatch):
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_heads()[0]
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(text("INSERT INTO alembic_version(version_num) VALUES (:head)"), {"head": head})
    db_session.commit()
    monkeypatch.setattr(app.db, "engine", db_session.get_bind())

    wait_for_database_schema(timeout=0.1, interval=0.01)


def test_database_schema_retry_uses_capped_exponential_backoff_and_sparse_logs(monkeypatch, caplog):
    caplog.set_level("INFO", logger="leiaberta.worker")
    clock = {"now": 0.0}
    delays = []

    def unavailable_inspect(_engine):
        raise RuntimeError("database unavailable; password=do-not-log-this")

    def fake_sleep(seconds):
        delays.append(seconds)
        clock["now"] += seconds
        if len(delays) == 10:
            clock["now"] = 600.0

    monkeypatch.setattr(app.db, "engine", object())
    monkeypatch.setattr("sqlalchemy.inspect", unavailable_inspect)
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(worker.time, "sleep", fake_sleep)

    with pytest.raises(SystemExit, match="before timeout") as error:
        wait_for_database_schema(timeout=600, interval=3)

    assert delays == [3, 6, 12, 24, 30, 30, 30, 30, 30, 30]
    assert caplog.text.count("worker_waiting_for_database_schema") == 2
    assert "attempt=1" in caplog.text
    assert "attempt=10" in caplog.text
    assert "do-not-log-this" not in caplog.text
    assert "do-not-log-this" not in str(error.value)


def test_transient_worker_errors_back_off_and_summarize_suppressed_repeats():
    from sqlalchemy.exc import OperationalError

    retryable = OperationalError("SELECT 1", {}, RuntimeError("server closed the connection"))
    non_transient = OperationalError("SELECT 1", {}, RuntimeError("disk is full"))
    policy = worker.WorkerLoopBackoff()

    assert worker.is_transient_worker_error(retryable) is True
    assert worker.is_transient_worker_error(non_transient) is False
    assert worker.is_transient_worker_error(ValueError("bad configuration")) is False

    results = [policy.on_error(retryable) for _ in range(10)]
    assert [result[0] for result in results] == [3, 6, 12, 24, 30, 30, 30, 30, 30, 30]
    assert results[0] == (3, 1, 0)
    assert results[1][2] == -1
    assert results[9] == (30, 10, 8)

    policy.on_success()
    assert policy.on_error(retryable) == (3, 1, 0)
    assert policy.on_error(non_transient) is None
    assert policy.on_error(retryable) == (3, 1, 0)


def test_hydration_concurrency_can_scale_to_twenty_four_but_stays_bounded(monkeypatch):
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "12")
    assert hydration_concurrency() == 12
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "32")
    assert hydration_concurrency() == 24
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "0")
    assert hydration_concurrency() == 1


def test_catalog_writers_are_serial_by_default_and_can_be_bounded(monkeypatch):
    monkeypatch.delenv("CATALOG_SYNC_CONCURRENCY", raising=False)
    assert catalog_concurrency() == 1
    monkeypatch.setenv("CATALOG_SYNC_CONCURRENCY", "3")
    assert catalog_concurrency() == 3
    monkeypatch.setenv("CATALOG_SYNC_CONCURRENCY", "20")
    assert catalog_concurrency() == 4


def test_background_backfill_mode_defaults_off_and_rejects_unknown_values(monkeypatch):
    monkeypatch.delenv("BACKGROUND_BACKFILL_MODE", raising=False)
    assert worker.background_backfill_mode() == "off"
    for mode in ("off", "hot", "continuous"):
        assert worker.background_backfill_mode(mode) == mode
    monkeypatch.setenv("BACKGROUND_BACKFILL_MODE", "sometimes")
    with pytest.raises(ValueError, match="BACKGROUND_BACKFILL_MODE"):
        worker.background_backfill_mode()


def test_paused_backfill_queue_messages_remain_unacked(monkeypatch):
    processed = []

    class FakeRedis:
        def __init__(self):
            self.acked = []

        def xack(self, queue_name, group, message_id):
            self.acked.append(message_id)

    monkeypatch.setattr(worker, "should_process_job",
                        lambda job_id, mode=None: job_id == "interactive" or mode == "continuous")
    monkeypatch.setattr(worker, "process_hydration_job", lambda job_id: processed.append(job_id))
    redis = FakeRedis()
    with ThreadPoolExecutor(max_workers=2) as executor:
        worker.process_queue_messages(redis, [
            ("bulk-message", {"job_id": "bulk"}),
            ("interactive-message", {"job_id": "interactive"}),
        ], executor, backfill_mode="off")

    assert processed == ["interactive"]
    assert redis.acked == ["interactive-message"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker.process_queue_messages(redis, [
            ("bulk-message", {"job_id": "bulk"}),
        ], executor, backfill_mode="continuous")
    assert set(processed) == {"interactive", "bulk"}
    assert set(redis.acked) == {"interactive-message", "bulk-message"}


def test_backfill_policy_pauses_legacy_jobs_and_hot_mode_only_allows_hot_laws(db_session, monkeypatch):
    from app import jobs
    from app.models import HydrationJob, Law

    common = dict(jurisdiction="federal", law_type="Lei", year=2024, number="1",
                  description="", status="Não verificado", aliases=[],
                  source_name="Senado Federal — Dados Abertos Legislativos",
                  source_url="https://example.test", fetch_url="https://example.test",
                  materialization_status="catalog")
    db_session.add_all([
        Law(slug="hot-law", title="Hot", hot=True, **common),
        Law(slug="cold-law", title="Cold", hot=False, **common),
        Law(slug="interactive-law", title="Interactive", hot=False, **common),
        Law(slug="unknown-law", title="Unknown", hot=False, **common),
    ])
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all([
        HydrationJob(id="hot-backfill", law_slug="hot-law", job_type="hydrate", status="queued",
                     stage_name="queued", message="Aguardando captura do texto legislativo",
                     created_at=now, updated_at=now),
        HydrationJob(id="cold-backfill", law_slug="cold-law", job_type="hydrate", status="queued",
                     stage_name="queued", message="[background-backfill] Aguardando lote",
                     created_at=now, updated_at=now),
        HydrationJob(id="interactive", law_slug="interactive-law", job_type="history", status="queued",
                     stage_name="queued", message="Aguardando worker", created_at=now, updated_at=now),
        HydrationJob(id="unknown-legacy", law_slug="unknown-law", job_type="hydrate", status="queued",
                     stage_name="retry_wait", message="Falha antiga sem marcador", created_at=now, updated_at=now),
    ])
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)

    assert jobs.should_process_job("hot-backfill", mode="off") is False
    assert jobs.should_process_job("hot-backfill", mode="hot") is True
    assert jobs.should_process_job("cold-backfill", mode="hot") is False
    assert jobs.should_process_job("cold-backfill", mode="continuous") is True
    assert jobs.should_process_job("interactive", mode="off") is True
    assert jobs.should_process_job("unknown-legacy", mode="off") is False
    tagged = db_session.get(HydrationJob, "cold-backfill")
    assert jobs._job_message(tagged, "retrying").startswith(jobs.BACKGROUND_BACKFILL_MARKER)
    promoted = jobs.queue_job("unknown-law", "hydrate", priority=True)
    assert promoted.message == "Aguardando worker"
    assert jobs.should_process_job(promoted.id, mode="off") is True


def test_terminal_jobs_ack_stale_stream_entries_but_ambiguous_queued_jobs_stay_pending(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app import jobs
    from app.models import HydrationJob, Law

    common = dict(jurisdiction="federal", law_type="Lei", year=2024, number="1",
                  description="", status="Não verificado", aliases=[],
                  source_name="Senado Federal — Dados Abertos Legislativos",
                  source_url="https://example.test", fetch_url="https://example.test",
                  hot=False, materialization_status="catalog")
    statuses = ("succeeded", "failed", "cancelled", "queued")
    db_session.add_all([Law(slug=f"terminal-{status}", title=status, **common) for status in statuses])
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all([
        HydrationJob(id=f"terminal-{status}-job", law_slug=f"terminal-{status}",
                     job_type="hydrate", status=status, stage_name="complete" if status != "queued" else "retry_wait",
                     message="Finalização antiga sem marcador", created_at=now, updated_at=now)
        for status in statuses
    ])
    db_session.commit()
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))

    class FakeRedis:
        def __init__(self):
            self.acked = []

        def xack(self, queue_name, group, message_id):
            self.acked.append(message_id)

    redis = FakeRedis()
    messages = [(f"message-{status}", {"job_id": f"terminal-{status}-job"}) for status in statuses]
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker.process_queue_messages(redis, messages, executor, backfill_mode="off")

    assert set(redis.acked) == {"message-succeeded", "message-failed", "message-cancelled"}
    assert jobs.should_process_job("terminal-queued-job", mode="off") is False


def test_worker_processes_independent_jobs_concurrently_and_acks_afterwards(monkeypatch):
    barrier = Barrier(2)
    completed = []

    def process(job_id):
        barrier.wait(timeout=2)
        completed.append(job_id)
        return True

    class FakeRedis:
        def __init__(self):
            self.acked = []

        def xack(self, queue_name, group, message_id):
            self.acked.append((queue_name, group, message_id))

    monkeypatch.setattr(worker, "process_hydration_job", process)
    monkeypatch.setattr(worker, "should_process_job", lambda job_id, mode=None: True)
    redis = FakeRedis()
    with ThreadPoolExecutor(max_workers=2) as executor:
        worker.process_queue_messages(redis, [
            ("message-1", {"job_id": "law-1"}),
            ("message-2", {"job_id": "law-2"}),
        ], executor)

    assert set(completed) == {"law-1", "law-2"}
    assert {message_id for _, _, message_id in redis.acked} == {"message-1", "message-2"}


def test_worker_publishes_expiring_heartbeat():
    class FakeRedis:
        def set(self, key, value, ex):
            self.record = (key, value, ex)

    redis = FakeRedis()
    now = datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc)
    timestamp = worker.publish_worker_heartbeat(redis, "worker-test", 8, now)
    assert redis.record == ("leiaberta:worker:heartbeat", timestamp, 90)
    assert timestamp == "2026-10-05T17:00:00+00:00"


def test_worker_heartbeat_loop_runs_independently_until_stopped():
    class FakeRedis:
        def __init__(self):
            self.records = []

        def set(self, key, value, ex):
            self.records.append((key, value, ex))

    class StopAfterOneHeartbeat:
        def is_set(self):
            return False

        def wait(self, seconds):
            assert seconds == 30
            return True

    redis = FakeRedis()
    worker.worker_heartbeat_loop(redis, "worker-test", 8, StopAfterOneHeartbeat())
    assert len(redis.records) == 1
    assert redis.records[0][0] == "leiaberta:worker:heartbeat"
    assert redis.records[0][2] == 90
