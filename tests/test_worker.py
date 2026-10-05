from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.db
import app.worker as worker
from app.worker import hydration_concurrency, wait_for_database_schema


def test_worker_waits_for_the_current_alembic_head(db_session, monkeypatch):
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_heads()[0]
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(text("INSERT INTO alembic_version(version_num) VALUES (:head)"), {"head": head})
    db_session.commit()
    monkeypatch.setattr(app.db, "engine", db_session.get_bind())

    wait_for_database_schema(timeout=0.1, interval=0.01)


def test_hydration_concurrency_can_scale_to_sixteen_but_stays_bounded(monkeypatch):
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "12")
    assert hydration_concurrency() == 12
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "32")
    assert hydration_concurrency() == 16
    monkeypatch.setenv("HYDRATION_CONCURRENCY", "0")
    assert hydration_concurrency() == 1


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
    redis = FakeRedis()
    with ThreadPoolExecutor(max_workers=2) as executor:
        worker.process_queue_messages(redis, [
            ("message-1", {"job_id": "law-1"}),
            ("message-2", {"job_id": "law-2"}),
        ], executor)

    assert set(completed) == {"law-1", "law-2"}
    assert {message_id for _, _, message_id in redis.acked} == {"message-1", "message-2"}
